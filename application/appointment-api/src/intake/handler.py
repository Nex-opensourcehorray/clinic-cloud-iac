"""Authenticated, replay-resistant Appointment API intake Lambda."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Callable

from common.authentication import AuthenticationError, authenticate_request
from common.observability import emit
from common.request_validation import RequestValidationError, validate_request_document
from intake.workflow import WorkflowError, WorkflowRepository


_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_CLIENTS: dict[str, Any] = {}


def _client(service: str) -> Any:
    if service not in _CLIENTS:
        import boto3

        _CLIENTS[service] = boto3.client(service)
    return _CLIENTS[service]


def _correlation_id(event: dict[str, Any]) -> str:
    for key, value in (event.get("headers") or {}).items():
        if str(key).lower() == "x-correlation-id":
            supplied = str(value or "")
            if _SAFE_CORRELATION_ID.fullmatch(supplied):
                return supplied
    request_id = str((event.get("requestContext") or {}).get("requestId") or "")
    if _SAFE_CORRELATION_ID.fullmatch(request_id):
        return request_id
    return str(uuid.uuid4())


def _response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(payload, separators=(",", ":"), sort_keys=True),
    }


def _controlled_failure(
    *, status_code: int, request_id: str, message: str
) -> dict[str, Any]:
    return _response(
        status_code,
        {"requestId": request_id, "status": "REJECTED", "message": message},
    )


def handle_request(
    event: dict[str, Any],
    context: Any,
    *,
    secret_client: Any,
    dynamodb_client: Any,
    sqs_client: Any,
    now: Callable[[], int],
) -> dict[str, Any]:
    started = time.monotonic()
    correlation_id = _correlation_id(event)
    invocation_id = str(getattr(context, "aws_request_id", "") or correlation_id)

    try:
        authenticated = authenticate_request(
            event,
            secret_client=secret_client,
            secret_arn=os.environ["HMAC_SECRET_ARN"],
            now=now,
            maximum_body_bytes=int(os.environ.get("MAXIMUM_BODY_BYTES", "16384")),
            maximum_clock_skew_seconds=int(
                os.environ.get("MAXIMUM_CLOCK_SKEW_SECONDS", "300")
            ),
        )
    except KeyError:
        emit(
            "authentication_failure",
            correlation_id=correlation_id,
            request_id=invocation_id,
            state="REJECTED",
            error_category="SECRET_CONFIGURATION_FAILURE",
        )
        return _controlled_failure(
            status_code=503,
            request_id=correlation_id,
            message="Request authentication is temporarily unavailable.",
        )
    except AuthenticationError as error:
        emit(
            "authentication_failure",
            correlation_id=correlation_id,
            request_id=invocation_id,
            state="REJECTED",
            error_category=error.category,
        )
        return _controlled_failure(
            status_code=error.status_code,
            request_id=correlation_id,
            message=error.message,
        )

    try:
        request_document = validate_request_document(
            json.loads(authenticated.body_bytes.decode("utf-8"))
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RequestValidationError,
    ):
        emit(
            "authenticated_request_rejected",
            correlation_id=correlation_id,
            request_id=invocation_id,
            state="REJECTED",
            error_category="INVALID_REQUEST_SCHEMA",
        )
        return _controlled_failure(
            status_code=400,
            request_id=correlation_id,
            message="Request body does not match the appointment contract.",
        )

    try:
        repository = WorkflowRepository(
            dynamodb_client=dynamodb_client,
            sqs_client=sqs_client,
            table_name=os.environ["WORKFLOW_TABLE_NAME"],
            queue_url=os.environ["WORK_QUEUE_URL"],
            nonce_ttl_seconds=int(os.environ.get("NONCE_TTL_SECONDS", "600")),
            idempotency_ttl_seconds=int(
                os.environ.get("IDEMPOTENCY_TTL_SECONDS", "604800")
            ),
            reconciliation_stale_seconds=int(
                os.environ.get("RECONCILIATION_STALE_SECONDS", "300")
            ),
        )
    except KeyError:
        emit(
            "workflow_rejected",
            correlation_id=correlation_id,
            request_id=invocation_id,
            state="REJECTED",
            error_category="WORKFLOW_CONFIGURATION_FAILURE",
        )
        return _controlled_failure(
            status_code=503,
            request_id=correlation_id,
            message="Request processing is temporarily unavailable.",
        )

    now_epoch = int(now())
    request_id = str(uuid.uuid4())
    try:
        reservation = repository.reserve(
            authenticated,
            request_id=request_id,
            request_document=request_document,
            now_epoch=now_epoch,
        )
        if reservation.created:
            status = repository.enqueue(
                authenticated,
                reservation,
                correlation_id=correlation_id,
                now_epoch=now_epoch,
            )
        else:
            status = reservation.status
    except WorkflowError as error:
        emit(
            "workflow_rejected",
            correlation_id=correlation_id,
            request_id=invocation_id,
            state="REJECTED",
            error_category=error.category,
        )
        return _controlled_failure(
            status_code=error.status_code,
            request_id=correlation_id,
            message=error.message,
        )

    emit(
        "authenticated_request_accepted",
        correlation_id=correlation_id,
        request_id=reservation.request_id,
        state=status,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    return _response(
        202,
        {
            "requestId": reservation.request_id,
            "status": status,
            "message": "Authenticated request accepted for asynchronous processing.",
        },
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return handle_request(
        event,
        context,
        secret_client=_client("secretsmanager"),
        dynamodb_client=_client("dynamodb"),
        sqs_client=_client("sqs"),
        now=lambda: int(time.time()),
    )

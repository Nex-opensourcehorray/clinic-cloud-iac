"""Idempotent SQS worker ownership with a fail-safe no-adapter outcome."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Callable

from common.clinical_adapter import (
    AdapterOutcome,
    ClinicalAdapter,
    UnavailableClinicalAdapter,
)
from common.observability import emit, emit_metric
from common.state_machine import TERMINAL_STATES, WorkflowState
from common.workflow_state import WorkflowStateRepository


_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_CLIENTS: dict[str, Any] = {}


def _client(service: str) -> Any:
    if service not in _CLIENTS:
        import boto3

        _CLIENTS[service] = boto3.client(service)
    return _CLIENTS[service]


def _envelope(record: dict[str, Any]) -> tuple[str, str]:
    value = json.loads(record.get("body") or "")
    if not isinstance(value, dict) or set(value) != {"requestId", "correlationId"}:
        raise ValueError("Message envelope must contain only approved references.")
    request_id = value.get("requestId")
    correlation_id = value.get("correlationId")
    if not isinstance(request_id, str) or not _SAFE_REFERENCE.fullmatch(request_id):
        raise ValueError("Request reference is invalid.")
    if not isinstance(correlation_id, str) or not _SAFE_REFERENCE.fullmatch(
        correlation_id
    ):
        raise ValueError("Correlation reference is invalid.")
    return request_id, correlation_id


def handle_records(
    event: dict[str, Any],
    context: Any,
    *,
    repository: WorkflowStateRepository,
    adapter: ClinicalAdapter,
    now: Callable[[], int],
    owner_factory: Callable[[], str],
) -> dict[str, Any]:
    del context
    failures: list[dict[str, str]] = []

    for record in event.get("Records") or []:
        message_id = str(record.get("messageId") or "unknown")
        queue_attempt = str(
            (record.get("attributes") or {}).get("ApproximateReceiveCount")
            or "unknown"
        )

        try:
            request_id, correlation_id = _envelope(record)
            owner_token = owner_factory()
            now_epoch = int(now())
            decision = repository.acquire_processing(
                request_id=request_id,
                owner_token=owner_token,
                now_epoch=now_epoch,
            )

            if not decision.acquired:
                current = decision.state.status if decision.state else "NOT_FOUND"
                terminal_values = {state.value for state in TERMINAL_STATES}
                if decision.state and current in terminal_values:
                    emit_metric(
                        "worker_duplicate_delivery",
                        "WorkerDuplicateDelivery",
                        correlation_id=correlation_id,
                        request_id=request_id,
                        message_id=message_id,
                        queue_attempt=queue_attempt,
                        state=current,
                    )
                else:
                    emit_metric(
                        "processing_ownership_conflict",
                        "WorkerOwnershipConflict",
                        correlation_id=correlation_id,
                        request_id=request_id,
                        message_id=message_id,
                        queue_attempt=queue_attempt,
                        state=current,
                    )
                continue

            if decision.recovered_expired_lease:
                emit_metric(
                    "processing_lease_expired",
                    "ProcessingLeaseExpired",
                    correlation_id=correlation_id,
                    request_id=request_id,
                    message_id=message_id,
                    queue_attempt=queue_attempt,
                    lease_expired=True,
                    state=WorkflowState.PROCESSING.value,
                )

            outcome = adapter.process(request_id)
            if outcome == AdapterOutcome.RETRYABLE_FAILURE:
                repository.mark_failed_retryable(
                    request_id=request_id,
                    owner_token=owner_token,
                    reason="CLINICAL_ADAPTER_RETRYABLE_FAILURE",
                    now_epoch=now_epoch,
                )
                emit(
                    "worker_retryable_failure",
                    correlation_id=correlation_id,
                    request_id=request_id,
                    message_id=message_id,
                    queue_attempt=queue_attempt,
                    outcome=outcome.value,
                    state=WorkflowState.FAILED_RETRYABLE.value,
                )
                failures.append({"itemIdentifier": message_id})
                continue

            reason = {
                AdapterOutcome.SUCCESS: "CLINICAL_SUCCESS_NOT_AUTHORIZED",
                AdapterOutcome.NONRETRYABLE_FAILURE: (
                    "CLINICAL_ADAPTER_NONRETRYABLE_FAILURE"
                ),
                AdapterOutcome.UNKNOWN_RESULT: "CLINICAL_ADAPTER_UNAVAILABLE",
            }.get(outcome, "CLINICAL_ADAPTER_UNKNOWN_OUTCOME")
            repository.mark_manual_review(
                request_id=request_id,
                owner_token=owner_token,
                reason=reason,
                now_epoch=now_epoch,
            )
            emit_metric(
                "manual_review_escalation",
                "ManualReviewEscalation",
                correlation_id=correlation_id,
                request_id=request_id,
                message_id=message_id,
                queue_attempt=queue_attempt,
                outcome=getattr(outcome, "value", "UNKNOWN_RESULT"),
                state=WorkflowState.MANUAL_REVIEW_REQUIRED.value,
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            emit(
                "worker_rejected_envelope",
                message_id=message_id,
                queue_attempt=queue_attempt,
                state="REJECTED",
                error_category="INVALID_MESSAGE_ENVELOPE",
            )
            failures.append({"itemIdentifier": message_id})
        except Exception:
            emit(
                "worker_processing_failure",
                message_id=message_id,
                queue_attempt=queue_attempt,
                state="RETRY_REQUIRED",
                error_category="WORKFLOW_STATE_FAILURE",
            )
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    repository = WorkflowStateRepository(
        dynamodb_client=_client("dynamodb"),
        sqs_client=_client("sqs"),
        table_name=os.environ["WORKFLOW_TABLE_NAME"],
        reconciliation_index_name=os.environ.get(
            "RECONCILIATION_INDEX_NAME", "reconciliation-index"
        ),
        queue_url=os.environ["WORK_QUEUE_URL"],
        processing_lease_seconds=int(
            os.environ.get("PROCESSING_LEASE_SECONDS", "120")
        ),
        reconciliation_backoff_seconds=int(
            os.environ.get("RECONCILIATION_BACKOFF_SECONDS", "300")
        ),
        maximum_reconciliation_attempts=int(
            os.environ.get("MAXIMUM_RECONCILIATION_ATTEMPTS", "3")
        ),
    )
    return handle_records(
        event,
        context,
        repository=repository,
        adapter=UnavailableClinicalAdapter(),
        now=lambda: int(time.time()),
        owner_factory=lambda: str(uuid.uuid4()),
    )

"""Nonproduction intake contract for W3.2.

This foundation validates basic transport expectations and deliberately performs
no persistence, queue submission, HMAC verification, or clinical-system action.
Production HMAC and workflow behavior are deferred to W3.3.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from common.observability import emit


_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _headers(event: dict[str, Any]) -> dict[str, str]:
    return {
        str(key).lower(): str(value)
        for key, value in (event.get("headers") or {}).items()
        if value is not None
    }


def _correlation_id(event: dict[str, Any], headers: dict[str, str]) -> str:
    supplied = headers.get("x-correlation-id", "")
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


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    started = time.monotonic()
    headers = _headers(event)
    correlation_id = _correlation_id(event, headers)
    request_id = str(getattr(context, "aws_request_id", "") or correlation_id)

    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        emit(
            "intake_rejected",
            correlation_id=correlation_id,
            request_id=request_id,
            state="REJECTED",
            error_category="UNSUPPORTED_CONTENT_TYPE",
        )
        return _response(
            415,
            {
                "requestId": correlation_id,
                "status": "REJECTED",
                "message": "Content-Type must be application/json.",
            },
        )

    try:
        body = json.loads(event.get("body") or "")
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
    except (json.JSONDecodeError, TypeError, ValueError):
        emit(
            "intake_rejected",
            correlation_id=correlation_id,
            request_id=request_id,
            state="REJECTED",
            error_category="INVALID_JSON",
        )
        return _response(
            400,
            {
                "requestId": correlation_id,
                "status": "REJECTED",
                "message": "Request body must be a valid JSON object.",
            },
        )

    duration_ms = round((time.monotonic() - started) * 1000)
    emit(
        "intake_foundation_accepted",
        correlation_id=correlation_id,
        request_id=request_id,
        state="FOUNDATION_ONLY",
        duration_ms=duration_ms,
    )

    return _response(
        202,
        {
            "requestId": correlation_id,
            "status": "FOUNDATION_ONLY",
            "message": "Request contract accepted; no appointment was created.",
        },
    )

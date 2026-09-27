"""SQS worker contract for W3.2; performs no clinical-system action."""

from __future__ import annotations

import json
from typing import Any

from common.observability import emit


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    failures: list[dict[str, str]] = []

    for record in event.get("Records") or []:
        message_id = str(record.get("messageId") or "unknown")
        receive_count = str(
            (record.get("attributes") or {}).get("ApproximateReceiveCount") or "unknown"
        )

        try:
            envelope = json.loads(record.get("body") or "")
            if not isinstance(envelope, dict):
                raise ValueError("Message envelope must be an object")

            correlation_id = str(envelope.get("correlationId") or "unknown")
            request_id = str(envelope.get("requestId") or "unknown")
            emit(
                "worker_foundation_received",
                correlation_id=correlation_id,
                request_id=request_id,
                message_id=message_id,
                queue_attempt=receive_count,
                state="NO_CLINICAL_ACTION",
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            emit(
                "worker_rejected_envelope",
                message_id=message_id,
                queue_attempt=receive_count,
                state="REJECTED",
                error_category="INVALID_MESSAGE_ENVELOPE",
            )
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}

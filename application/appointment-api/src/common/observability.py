"""Data-minimized structured logging for the Appointment API."""

from __future__ import annotations

import json
from typing import Any


_ALLOWED_FIELDS = {
    "attempt_count",
    "correlation_id",
    "duration_ms",
    "error_category",
    "event",
    "lease_expired",
    "message_id",
    "outcome",
    "queue_attempt",
    "request_id",
    "source_state",
    "state",
}

_ALLOWED_METRICS = {
    "ManualReviewBacklog",
    "ManualReviewEscalation",
    "ProcessingLeaseExpired",
    "ReconciliationAttempt",
    "ReconciliationFailure",
    "ReconciliationSuccess",
    "StaleQueueState",
    "WorkerDuplicateDelivery",
    "WorkerOwnershipConflict",
}


def emit(event: str, **fields: Any) -> None:
    """Emit only explicitly approved operational metadata as one JSON line."""

    record = {"event": event}
    for key, value in fields.items():
        if key in _ALLOWED_FIELDS and value is not None:
            record[key] = value

    print(json.dumps(record, separators=(",", ":"), sort_keys=True))


def emit_metric(event: str, metric_name: str, value: int = 1, **fields: Any) -> None:
    """Emit an allow-listed CloudWatch EMF metric without sensitive dimensions."""

    if metric_name not in _ALLOWED_METRICS:
        raise ValueError("Metric name is not approved for Appointment API telemetry.")

    record: dict[str, Any] = {"event": event, metric_name: value}
    for key, field_value in fields.items():
        if key in _ALLOWED_FIELDS and field_value is not None:
            record[key] = field_value
    record["_aws"] = {
        "CloudWatchMetrics": [
            {
                "Dimensions": [[]],
                "Metrics": [{"Name": metric_name, "Unit": "Count"}],
                "Namespace": "Clinic/AppointmentApi",
            }
        ]
    }
    print(json.dumps(record, separators=(",", ":"), sort_keys=True))

"""Data-minimized structured logging for the Appointment API foundation."""

from __future__ import annotations

import json
from typing import Any


_ALLOWED_FIELDS = {
    "correlation_id",
    "duration_ms",
    "error_category",
    "event",
    "message_id",
    "queue_attempt",
    "request_id",
    "state",
}


def emit(event: str, **fields: Any) -> None:
    """Emit only explicitly approved operational metadata as one JSON line."""

    record = {"event": event}
    for key, value in fields.items():
        if key in _ALLOWED_FIELDS and value is not None:
            record[key] = value

    print(json.dumps(record, separators=(",", ":"), sort_keys=True))

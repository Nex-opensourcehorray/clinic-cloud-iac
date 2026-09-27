"""Scheduled reconciliation contract for W3.2; performs no workflow mutation."""

from __future__ import annotations

from typing import Any

from common.observability import emit


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, str]:
    request_id = str(getattr(context, "aws_request_id", "") or "unknown")
    emit(
        "reconciler_foundation_invoked",
        request_id=request_id,
        state="NO_WORKFLOW_MUTATION",
    )
    return {"status": "FOUNDATION_ONLY"}

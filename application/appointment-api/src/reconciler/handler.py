"""Bounded reconciliation for stale or uncertain Appointment API handoffs."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable

from common.observability import emit, emit_metric
from common.state_machine import WorkflowState
from common.workflow_state import WorkflowStateRepository


_CLIENTS: dict[str, Any] = {}
_RECOVERABLE_STATES = (
    WorkflowState.QUEUE_PENDING.value,
    WorkflowState.RECONCILE_REQUIRED.value,
    WorkflowState.PROCESSING.value,
    WorkflowState.FAILED_RETRYABLE.value,
)


def _client(service: str) -> Any:
    if service not in _CLIENTS:
        import boto3

        _CLIENTS[service] = boto3.client(service)
    return _CLIENTS[service]


def handle_reconciliation(
    event: dict[str, Any],
    context: Any,
    *,
    repository: WorkflowStateRepository,
    now: Callable[[], int],
    owner_factory: Callable[[], str],
    batch_size: int,
) -> dict[str, int]:
    del event
    invocation_id = str(getattr(context, "aws_request_id", "") or "unknown")
    now_epoch = int(now())
    summary = {"attempted": 0, "requeued": 0, "manualReview": 0, "conflicts": 0}

    for source_state in _RECOVERABLE_STATES:
        request_ids = repository.query_due(
            status=source_state,
            now_epoch=now_epoch,
            limit=batch_size,
        )
        for request_id in request_ids:
            summary["attempted"] += 1
            if source_state in {
                WorkflowState.QUEUE_PENDING.value,
                WorkflowState.PROCESSING.value,
            }:
                emit_metric(
                    "stale_queue_state",
                    "StaleQueueState",
                    request_id=request_id,
                    source_state=source_state,
                    state=source_state,
                )
            if source_state == WorkflowState.PROCESSING.value:
                emit_metric(
                    "processing_lease_expired",
                    "ProcessingLeaseExpired",
                    request_id=request_id,
                    source_state=source_state,
                    lease_expired=True,
                    state=source_state,
                )

            owner_token = owner_factory()
            try:
                decision = repository.acquire_reconciliation(
                    request_id=request_id,
                    expected_status=source_state,
                    owner_token=owner_token,
                    now_epoch=now_epoch,
                )
                if not decision.acquired:
                    if decision.exhausted and repository.escalate_exhausted(
                        request_id=request_id,
                        expected_status=source_state,
                        now_epoch=now_epoch,
                    ):
                        summary["manualReview"] += 1
                        emit_metric(
                            "max_retries_reached",
                            "ManualReviewEscalation",
                            request_id=request_id,
                            source_state=source_state,
                            state=WorkflowState.MANUAL_REVIEW_REQUIRED.value,
                            error_category="RECONCILIATION_ATTEMPTS_EXHAUSTED",
                        )
                    else:
                        summary["conflicts"] += 1
                        emit(
                            "reconciliation_ownership_conflict",
                            request_id=request_id,
                            source_state=source_state,
                            state=decision.state.status if decision.state else "NOT_FOUND",
                        )
                    continue

                attempt_count = (
                    decision.state.reconciliation_attempts if decision.state else 0
                )
                emit_metric(
                    "reconciliation_attempt",
                    "ReconciliationAttempt",
                    request_id=request_id,
                    source_state=source_state,
                    attempt_count=attempt_count,
                    state=WorkflowState.RECONCILE_REQUIRED.value,
                )

                try:
                    message_id = repository.send_reference(
                        request_id=request_id,
                        correlation_id=request_id,
                    )
                    repository.complete_reconciliation(
                        request_id=request_id,
                        owner_token=owner_token,
                        message_id=message_id,
                        now_epoch=now_epoch,
                    )
                    summary["requeued"] += 1
                    emit_metric(
                        "reconciliation_success",
                        "ReconciliationSuccess",
                        request_id=request_id,
                        source_state=source_state,
                        attempt_count=attempt_count,
                        state=WorkflowState.QUEUED.value,
                    )
                except Exception:
                    target = repository.record_reconciliation_failure(
                        request_id=request_id,
                        owner_token=owner_token,
                        attempt_count=attempt_count,
                        now_epoch=now_epoch,
                    )
                    emit_metric(
                        "reconciliation_failure",
                        "ReconciliationFailure",
                        request_id=request_id,
                        source_state=source_state,
                        attempt_count=attempt_count,
                        state=target,
                        error_category="RECONCILIATION_SEND_OR_COMMIT_UNCERTAIN",
                    )
                    if target == WorkflowState.MANUAL_REVIEW_REQUIRED.value:
                        summary["manualReview"] += 1
                        emit_metric(
                            "manual_review_escalation",
                            "ManualReviewEscalation",
                            request_id=request_id,
                            source_state=source_state,
                            attempt_count=attempt_count,
                            state=target,
                        )
            except Exception:
                emit_metric(
                    "reconciliation_failure",
                    "ReconciliationFailure",
                    request_id=request_id,
                    source_state=source_state,
                    state="RECOVERABLE",
                    error_category="RECONCILIATION_STATE_FAILURE",
                )

    try:
        backlog = 1 if repository.manual_review_exists() else 0
        emit_metric(
            "manual_review_backlog",
            "ManualReviewBacklog",
            value=backlog,
            request_id=invocation_id,
            state=(
                WorkflowState.MANUAL_REVIEW_REQUIRED.value if backlog else "CLEAR"
            ),
        )
    except Exception:
        emit(
            "manual_review_backlog_check_failed",
            request_id=invocation_id,
            state="UNKNOWN",
            error_category="RECONCILIATION_STATE_FAILURE",
        )

    return summary


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, int]:
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
    return handle_reconciliation(
        event,
        context,
        repository=repository,
        now=lambda: int(time.time()),
        owner_factory=lambda: str(uuid.uuid4()),
        batch_size=int(os.environ.get("RECONCILIATION_BATCH_SIZE", "25")),
    )

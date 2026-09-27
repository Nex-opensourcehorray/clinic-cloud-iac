"""Explicit durable states and legal Appointment API workflow transitions."""

from __future__ import annotations

from enum import Enum


class WorkflowState(str, Enum):
    QUEUE_PENDING = "QUEUE_PENDING"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    RECONCILE_REQUIRED = "RECONCILE_REQUIRED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    SUCCEEDED = "SUCCEEDED"


LEGAL_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.QUEUE_PENDING: frozenset(
        {
            WorkflowState.QUEUED,
            WorkflowState.PROCESSING,
            WorkflowState.RECONCILE_REQUIRED,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        }
    ),
    WorkflowState.QUEUED: frozenset(
        {
            WorkflowState.PROCESSING,
            WorkflowState.RECONCILE_REQUIRED,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        }
    ),
    WorkflowState.PROCESSING: frozenset(
        {
            WorkflowState.FAILED_RETRYABLE,
            WorkflowState.RECONCILE_REQUIRED,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
            # Reserved for a future approved clinical adapter. W3.5 never uses it.
            WorkflowState.SUCCEEDED,
        }
    ),
    WorkflowState.FAILED_RETRYABLE: frozenset(
        {
            WorkflowState.QUEUED,
            WorkflowState.PROCESSING,
            WorkflowState.RECONCILE_REQUIRED,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        }
    ),
    WorkflowState.RECONCILE_REQUIRED: frozenset(
        {
            WorkflowState.QUEUED,
            WorkflowState.PROCESSING,
            WorkflowState.MANUAL_REVIEW_REQUIRED,
        }
    ),
    WorkflowState.MANUAL_REVIEW_REQUIRED: frozenset(),
    WorkflowState.SUCCEEDED: frozenset(),
}

TERMINAL_STATES = frozenset(
    {WorkflowState.MANUAL_REVIEW_REQUIRED, WorkflowState.SUCCEEDED}
)


class InvalidStateTransition(ValueError):
    """Raised before attempting an illegal or out-of-order state mutation."""


def require_legal_transition(current: str, target: str) -> None:
    try:
        current_state = WorkflowState(current)
        target_state = WorkflowState(target)
    except ValueError as error:
        raise InvalidStateTransition("Unknown workflow state.") from error

    if target_state not in LEGAL_TRANSITIONS[current_state]:
        raise InvalidStateTransition(
            f"Illegal workflow transition: {current_state.value} -> {target_state.value}"
        )

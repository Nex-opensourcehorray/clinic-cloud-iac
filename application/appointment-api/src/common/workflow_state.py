"""Conditional DynamoDB ownership and bounded reconciliation operations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from common.state_machine import WorkflowState, require_legal_transition


CONDITIONAL_FAILURE = "ConditionalCheckFailedException"


def _s(value: str) -> dict[str, str]:
    return {"S": value}


def _n(value: int) -> dict[str, str]:
    return {"N": str(value)}


def _error_code(error: Exception) -> str:
    response = getattr(error, "response", {})
    return str((response.get("Error") or {}).get("Code") or "")


def _text(item: dict[str, Any], name: str) -> str | None:
    value = item.get(name)
    if isinstance(value, dict) and isinstance(value.get("S"), str):
        return value["S"]
    return None


def _number(item: dict[str, Any], name: str) -> int:
    value = item.get(name)
    if isinstance(value, dict) and isinstance(value.get("N"), str):
        try:
            return int(value["N"])
        except ValueError:
            return 0
    return 0


@dataclass(frozen=True)
class RequestState:
    request_id: str
    status: str
    processing_attempts: int = 0
    reconciliation_attempts: int = 0


@dataclass(frozen=True)
class OwnershipDecision:
    acquired: bool
    state: RequestState | None
    recovered_expired_lease: bool = False
    exhausted: bool = False


class WorkflowStateRepository:
    """Uses conditional writes so only one worker or reconciler owns a request."""

    def __init__(
        self,
        *,
        dynamodb_client: Any,
        sqs_client: Any,
        table_name: str,
        reconciliation_index_name: str,
        queue_url: str,
        processing_lease_seconds: int,
        reconciliation_backoff_seconds: int,
        maximum_reconciliation_attempts: int,
    ) -> None:
        self._dynamodb = dynamodb_client
        self._sqs = sqs_client
        self._table_name = table_name
        self._index_name = reconciliation_index_name
        self._queue_url = queue_url
        self._processing_lease_seconds = processing_lease_seconds
        self._reconciliation_backoff_seconds = reconciliation_backoff_seconds
        self._maximum_reconciliation_attempts = maximum_reconciliation_attempts

    @staticmethod
    def _request_pk(request_id: str) -> str:
        return f"REQUEST#{request_id}"

    @staticmethod
    def _state(item: dict[str, Any]) -> RequestState | None:
        request_id = _text(item, "request_id")
        status = _text(item, "status")
        if not request_id or not status:
            return None
        return RequestState(
            request_id=request_id,
            status=status,
            processing_attempts=_number(item, "processing_attempts"),
            reconciliation_attempts=_number(item, "reconciliation_attempts"),
        )

    def get_request(self, request_id: str) -> RequestState | None:
        result = self._dynamodb.get_item(
            TableName=self._table_name,
            Key={"PK": _s(self._request_pk(request_id)), "SK": _s("METADATA")},
            ConsistentRead=True,
        )
        return self._state(result.get("Item") or {})

    def _acquire_processing_update(
        self,
        *,
        request_id: str,
        owner_token: str,
        now_epoch: int,
        expired_only: bool,
    ) -> RequestState:
        lease_expires = now_epoch + self._processing_lease_seconds
        values = {
            ":processing": _s(WorkflowState.PROCESSING.value),
            ":owner": _s(owner_token),
            ":lease": _n(lease_expires),
            ":now": _n(now_epoch),
            ":one": _n(1),
        }
        if expired_only:
            condition = "#status = :processing AND lease_expires_at <= :now"
        else:
            for source in (
                WorkflowState.QUEUE_PENDING,
                WorkflowState.QUEUED,
                WorkflowState.FAILED_RETRYABLE,
                WorkflowState.RECONCILE_REQUIRED,
            ):
                require_legal_transition(
                    source.value, WorkflowState.PROCESSING.value
                )
            condition = (
                "#status IN (:queue_pending, :queued, :retryable, :reconcile_required)"
            )
            values.update(
                {
                    ":queue_pending": _s(WorkflowState.QUEUE_PENDING.value),
                    ":queued": _s(WorkflowState.QUEUED.value),
                    ":retryable": _s(WorkflowState.FAILED_RETRYABLE.value),
                    ":reconcile_required": _s(
                        WorkflowState.RECONCILE_REQUIRED.value
                    ),
                }
            )

        result = self._dynamodb.update_item(
            TableName=self._table_name,
            Key={"PK": _s(self._request_pk(request_id)), "SK": _s("METADATA")},
            UpdateExpression=(
                "SET #status = :processing, processing_owner = :owner, "
                "lease_expires_at = :lease, updated_at = :now, "
                "reconcile_status = :processing, next_attempt_at = :lease "
                "REMOVE reconciliation_owner, reconciliation_lease_expires_at "
                "ADD processing_attempts :one"
            ),
            ConditionExpression=f"attribute_exists(PK) AND ({condition})",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
        state = self._state(result.get("Attributes") or {})
        if state is None:
            raise RuntimeError("DynamoDB did not return the acquired request state.")
        return state

    def acquire_processing(
        self, *, request_id: str, owner_token: str, now_epoch: int
    ) -> OwnershipDecision:
        try:
            state = self._acquire_processing_update(
                request_id=request_id,
                owner_token=owner_token,
                now_epoch=now_epoch,
                expired_only=False,
            )
            return OwnershipDecision(True, state)
        except Exception as error:
            if _error_code(error) != CONDITIONAL_FAILURE:
                raise

        try:
            state = self._acquire_processing_update(
                request_id=request_id,
                owner_token=owner_token,
                now_epoch=now_epoch,
                expired_only=True,
            )
            return OwnershipDecision(True, state, recovered_expired_lease=True)
        except Exception as error:
            if _error_code(error) != CONDITIONAL_FAILURE:
                raise

        return OwnershipDecision(False, self.get_request(request_id))

    def mark_manual_review(
        self,
        *,
        request_id: str,
        owner_token: str,
        reason: str,
        now_epoch: int,
    ) -> None:
        require_legal_transition(
            WorkflowState.PROCESSING.value,
            WorkflowState.MANUAL_REVIEW_REQUIRED.value,
        )
        self._dynamodb.update_item(
            TableName=self._table_name,
            Key={"PK": _s(self._request_pk(request_id)), "SK": _s("METADATA")},
            UpdateExpression=(
                "SET #status = :manual, reconcile_status = :manual, "
                "next_attempt_at = :now, updated_at = :now, "
                "exception_category = :reason "
                "REMOVE processing_owner, lease_expires_at, reconciliation_owner, "
                "reconciliation_lease_expires_at"
            ),
            ConditionExpression=(
                "#status = :processing AND processing_owner = :owner"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":manual": _s(WorkflowState.MANUAL_REVIEW_REQUIRED.value),
                ":processing": _s(WorkflowState.PROCESSING.value),
                ":owner": _s(owner_token),
                ":reason": _s(reason),
                ":now": _n(now_epoch),
            },
        )

    def mark_failed_retryable(
        self,
        *,
        request_id: str,
        owner_token: str,
        reason: str,
        now_epoch: int,
    ) -> None:
        require_legal_transition(
            WorkflowState.PROCESSING.value,
            WorkflowState.FAILED_RETRYABLE.value,
        )
        next_attempt = now_epoch + self._reconciliation_backoff_seconds
        self._dynamodb.update_item(
            TableName=self._table_name,
            Key={"PK": _s(self._request_pk(request_id)), "SK": _s("METADATA")},
            UpdateExpression=(
                "SET #status = :retryable, reconcile_status = :retryable, "
                "next_attempt_at = :next_attempt, updated_at = :now, "
                "exception_category = :reason REMOVE processing_owner, lease_expires_at"
            ),
            ConditionExpression=(
                "#status = :processing AND processing_owner = :owner"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":retryable": _s(WorkflowState.FAILED_RETRYABLE.value),
                ":processing": _s(WorkflowState.PROCESSING.value),
                ":owner": _s(owner_token),
                ":reason": _s(reason),
                ":next_attempt": _n(next_attempt),
                ":now": _n(now_epoch),
            },
        )

    def query_due(self, *, status: str, now_epoch: int, limit: int) -> list[str]:
        result = self._dynamodb.query(
            TableName=self._table_name,
            IndexName=self._index_name,
            KeyConditionExpression=(
                "reconcile_status = :status AND next_attempt_at <= :now"
            ),
            ExpressionAttributeValues={
                ":status": _s(status),
                ":now": _n(now_epoch),
            },
            Limit=limit,
            ScanIndexForward=True,
        )
        request_ids: list[str] = []
        for item in result.get("Items") or []:
            pk = _text(item, "PK") or ""
            if pk.startswith("REQUEST#"):
                request_ids.append(pk.removeprefix("REQUEST#"))
        return request_ids

    def manual_review_exists(self) -> bool:
        result = self._dynamodb.query(
            TableName=self._table_name,
            IndexName=self._index_name,
            KeyConditionExpression="reconcile_status = :status",
            ExpressionAttributeValues={
                ":status": _s(WorkflowState.MANUAL_REVIEW_REQUIRED.value),
            },
            Select="COUNT",
            Limit=1,
        )
        return int(result.get("Count") or 0) > 0

    def acquire_reconciliation(
        self,
        *,
        request_id: str,
        expected_status: str,
        owner_token: str,
        now_epoch: int,
    ) -> OwnershipDecision:
        lease_expires = now_epoch + self._processing_lease_seconds
        if expected_status != WorkflowState.RECONCILE_REQUIRED.value:
            require_legal_transition(
                expected_status, WorkflowState.RECONCILE_REQUIRED.value
            )
        try:
            result = self._dynamodb.update_item(
                TableName=self._table_name,
                Key={
                    "PK": _s(self._request_pk(request_id)),
                    "SK": _s("METADATA"),
                },
                UpdateExpression=(
                    "SET #status = :reconcile, reconcile_status = :reconcile, "
                    "next_attempt_at = :lease, updated_at = :now, "
                    "reconciliation_owner = :owner, "
                    "reconciliation_lease_expires_at = :lease "
                    "REMOVE processing_owner, lease_expires_at "
                    "ADD reconciliation_attempts :one"
                ),
                ConditionExpression=(
                    "#status = :expected AND next_attempt_at <= :now AND "
                    "(attribute_not_exists(reconciliation_lease_expires_at) OR "
                    "reconciliation_lease_expires_at <= :now) AND "
                    "(attribute_not_exists(reconciliation_attempts) OR "
                    "reconciliation_attempts < :maximum_attempts)"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":expected": _s(expected_status),
                    ":reconcile": _s(WorkflowState.RECONCILE_REQUIRED.value),
                    ":owner": _s(owner_token),
                    ":lease": _n(lease_expires),
                    ":now": _n(now_epoch),
                    ":one": _n(1),
                    ":maximum_attempts": _n(
                        self._maximum_reconciliation_attempts
                    ),
                },
                ReturnValues="ALL_NEW",
            )
            state = self._state(result.get("Attributes") or {})
            if state is None:
                raise RuntimeError("DynamoDB did not return reconciliation state.")
            return OwnershipDecision(
                True,
                state,
                recovered_expired_lease=(
                    expected_status == WorkflowState.PROCESSING.value
                ),
            )
        except Exception as error:
            if _error_code(error) != CONDITIONAL_FAILURE:
                raise

        state = self.get_request(request_id)
        exhausted = bool(
            state
            and state.status == expected_status
            and state.reconciliation_attempts
            >= self._maximum_reconciliation_attempts
        )
        return OwnershipDecision(False, state, exhausted=exhausted)

    def escalate_exhausted(
        self, *, request_id: str, expected_status: str, now_epoch: int
    ) -> bool:
        require_legal_transition(
            expected_status, WorkflowState.MANUAL_REVIEW_REQUIRED.value
        )
        try:
            self._dynamodb.update_item(
                TableName=self._table_name,
                Key={
                    "PK": _s(self._request_pk(request_id)),
                    "SK": _s("METADATA"),
                },
                UpdateExpression=(
                    "SET #status = :manual, reconcile_status = :manual, "
                    "next_attempt_at = :now, updated_at = :now, "
                    "exception_category = :reason "
                    "REMOVE processing_owner, lease_expires_at, reconciliation_owner, "
                    "reconciliation_lease_expires_at"
                ),
                ConditionExpression=(
                    "#status = :expected AND next_attempt_at <= :now AND "
                    "reconciliation_attempts >= :maximum_attempts"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":expected": _s(expected_status),
                    ":manual": _s(WorkflowState.MANUAL_REVIEW_REQUIRED.value),
                    ":reason": _s("RECONCILIATION_ATTEMPTS_EXHAUSTED"),
                    ":now": _n(now_epoch),
                    ":maximum_attempts": _n(
                        self._maximum_reconciliation_attempts
                    ),
                },
            )
            return True
        except Exception as error:
            if _error_code(error) == CONDITIONAL_FAILURE:
                return False
            raise

    def send_reference(self, *, request_id: str, correlation_id: str) -> str:
        result = self._sqs.send_message(
            QueueUrl=self._queue_url,
            MessageBody=json.dumps(
                {"correlationId": correlation_id, "requestId": request_id},
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        return str(result.get("MessageId") or "")

    def complete_reconciliation(
        self,
        *,
        request_id: str,
        owner_token: str,
        message_id: str,
        now_epoch: int,
    ) -> None:
        require_legal_transition(
            WorkflowState.RECONCILE_REQUIRED.value, WorkflowState.QUEUED.value
        )
        self._dynamodb.update_item(
            TableName=self._table_name,
            Key={"PK": _s(self._request_pk(request_id)), "SK": _s("METADATA")},
            UpdateExpression=(
                "SET #status = :queued, updated_at = :now, queue_message_id = :message_id "
                "REMOVE reconcile_status, next_attempt_at, reconciliation_owner, "
                "reconciliation_lease_expires_at, exception_category"
            ),
            ConditionExpression=(
                "#status = :reconcile AND reconciliation_owner = :owner"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":queued": _s(WorkflowState.QUEUED.value),
                ":reconcile": _s(WorkflowState.RECONCILE_REQUIRED.value),
                ":owner": _s(owner_token),
                ":message_id": _s(message_id or "not-returned"),
                ":now": _n(now_epoch),
            },
        )

    def record_reconciliation_failure(
        self,
        *,
        request_id: str,
        owner_token: str,
        attempt_count: int,
        now_epoch: int,
    ) -> str:
        if attempt_count >= self._maximum_reconciliation_attempts:
            require_legal_transition(
                WorkflowState.RECONCILE_REQUIRED.value,
                WorkflowState.MANUAL_REVIEW_REQUIRED.value,
            )
            target = WorkflowState.MANUAL_REVIEW_REQUIRED.value
            next_attempt = now_epoch
            reason = "RECONCILIATION_ATTEMPTS_EXHAUSTED"
        else:
            target = WorkflowState.RECONCILE_REQUIRED.value
            next_attempt = now_epoch + self._reconciliation_backoff_seconds
            reason = "RECONCILIATION_SEND_UNCERTAIN"

        self._dynamodb.update_item(
            TableName=self._table_name,
            Key={"PK": _s(self._request_pk(request_id)), "SK": _s("METADATA")},
            UpdateExpression=(
                "SET #status = :target, reconcile_status = :target, "
                "next_attempt_at = :next_attempt, updated_at = :now, "
                "exception_category = :reason "
                "REMOVE reconciliation_owner, reconciliation_lease_expires_at"
            ),
            ConditionExpression=(
                "#status = :reconcile AND reconciliation_owner = :owner"
            ),
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":target": _s(target),
                ":reconcile": _s(WorkflowState.RECONCILE_REQUIRED.value),
                ":owner": _s(owner_token),
                ":next_attempt": _n(next_attempt),
                ":now": _n(now_epoch),
                ":reason": _s(reason),
            },
        )
        return target

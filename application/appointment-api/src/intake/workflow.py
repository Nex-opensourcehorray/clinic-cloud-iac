"""Atomic replay/idempotency reservation and durable queue handoff."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from common.authentication import AuthenticatedRequest
from common.observability import emit
from common.state_machine import WorkflowState, require_legal_transition


class WorkflowError(Exception):
    """A controlled workflow reservation or handoff failure."""

    def __init__(self, category: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.status_code = status_code


class WorkflowTransitionConflict(Exception):
    """A conditional transition failed without a newer authoritative state."""


@dataclass(frozen=True)
class Reservation:
    created: bool
    request_id: str
    status: str


@dataclass(frozen=True)
class TransitionResult:
    applied: bool
    status: str


def _s(value: str) -> dict[str, str]:
    return {"S": value}


def _n(value: int) -> dict[str, str]:
    return {"N": str(value)}


def _error_code(error: Exception) -> str:
    response = getattr(error, "response", {})
    return str((response.get("Error") or {}).get("Code") or "")


def _is_conditional_failure(error: Exception) -> bool:
    code = _error_code(error)
    if code == "ConditionalCheckFailedException":
        return True
    if code != "TransactionCanceledException":
        return False

    response = getattr(error, "response", {})
    reasons = response.get("CancellationReasons") or []
    return any(
        isinstance(reason, dict)
        and reason.get("Code") == "ConditionalCheckFailed"
        for reason in reasons
    )


def _item_value(item: dict[str, Any], name: str) -> str | None:
    value = item.get(name)
    if isinstance(value, dict) and isinstance(value.get("S"), str):
        return value["S"]
    return None


class WorkflowRepository:
    """Coordinates DynamoDB state and the non-transactional SQS handoff."""

    def __init__(
        self,
        *,
        dynamodb_client: Any,
        sqs_client: Any,
        table_name: str,
        queue_url: str,
        nonce_ttl_seconds: int,
        idempotency_ttl_seconds: int,
        reconciliation_stale_seconds: int,
    ) -> None:
        self._dynamodb = dynamodb_client
        self._sqs = sqs_client
        self._table_name = table_name
        self._queue_url = queue_url
        self._nonce_ttl_seconds = nonce_ttl_seconds
        self._idempotency_ttl_seconds = idempotency_ttl_seconds
        self._reconciliation_stale_seconds = reconciliation_stale_seconds

    @staticmethod
    def _nonce_pk(authenticated: AuthenticatedRequest) -> str:
        return f"NONCE#{authenticated.key_id}#{authenticated.nonce}"

    @staticmethod
    def _idempotency_pk(authenticated: AuthenticatedRequest) -> str:
        return f"IDEMPOTENCY#{authenticated.key_id}#{authenticated.idempotency_key}"

    @staticmethod
    def _request_pk(request_id: str) -> str:
        return f"REQUEST#{request_id}"

    def _get(self, pk: str) -> dict[str, Any]:
        response = self._dynamodb.get_item(
            TableName=self._table_name,
            Key={"PK": _s(pk), "SK": _s("METADATA")},
            ConsistentRead=True,
        )
        return response.get("Item") or {}

    def reserve(
        self,
        authenticated: AuthenticatedRequest,
        *,
        request_id: str,
        request_document: dict[str, Any],
        now_epoch: int,
    ) -> Reservation:
        nonce_pk = self._nonce_pk(authenticated)
        idempotency_pk = self._idempotency_pk(authenticated)
        request_pk = self._request_pk(request_id)
        nonce_expires = now_epoch + self._nonce_ttl_seconds
        idempotency_expires = now_epoch + self._idempotency_ttl_seconds

        transaction = [
            {
                "Put": {
                    "TableName": self._table_name,
                    "Item": {
                        "PK": _s(nonce_pk),
                        "SK": _s("METADATA"),
                        "item_type": _s("NONCE"),
                        "created_at": _n(now_epoch),
                        "expires_at": _n(nonce_expires),
                    },
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            },
            {
                "Put": {
                    "TableName": self._table_name,
                    "Item": {
                        "PK": _s(idempotency_pk),
                        "SK": _s("METADATA"),
                        "item_type": _s("IDEMPOTENCY"),
                        "body_digest": _s(authenticated.body_digest),
                        "request_id": _s(request_id),
                        "status": _s("QUEUE_PENDING"),
                        "created_at": _n(now_epoch),
                        "updated_at": _n(now_epoch),
                        "expires_at": _n(idempotency_expires),
                    },
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            },
            {
                "Put": {
                    "TableName": self._table_name,
                    "Item": {
                        "PK": _s(request_pk),
                        "SK": _s("METADATA"),
                        "item_type": _s("REQUEST"),
                        "body_digest": _s(authenticated.body_digest),
                        "idempotency_reference": _s(idempotency_pk),
                        "request_id": _s(request_id),
                        "status": _s("QUEUE_PENDING"),
                        "reconcile_status": _s("QUEUE_PENDING"),
                        "next_attempt_at": _n(
                            now_epoch + self._reconciliation_stale_seconds
                        ),
                        "request_payload_json": _s(
                            json.dumps(
                                request_document,
                                separators=(",", ":"),
                                sort_keys=True,
                            )
                        ),
                        "created_at": _n(now_epoch),
                        "updated_at": _n(now_epoch),
                        "expires_at": _n(idempotency_expires),
                    },
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            },
        ]

        try:
            self._dynamodb.transact_write_items(
                TransactItems=transaction,
                ClientRequestToken=request_id,
            )
            return Reservation(True, request_id, "QUEUE_PENDING")
        except Exception as error:
            if _error_code(error) not in {
                "ConditionalCheckFailedException",
                "TransactionCanceledException",
            }:
                raise WorkflowError(
                    "DYNAMODB_RESERVATION_FAILURE",
                    "Request could not be reserved.",
                    503,
                ) from error

        try:
            if self._get(nonce_pk):
                raise WorkflowError(
                    "NONCE_REPLAY", "Request nonce has already been used.", 409
                )
            existing = self._get(idempotency_pk)
        except WorkflowError:
            raise
        except Exception as error:
            raise WorkflowError(
                "DYNAMODB_RESERVATION_FAILURE",
                "Request could not be reserved.",
                503,
            ) from error

        if not existing:
            raise WorkflowError(
                "DYNAMODB_RESERVATION_FAILURE",
                "Request could not be reserved.",
                503,
            )

        existing_digest = _item_value(existing, "body_digest")
        existing_request_id = _item_value(existing, "request_id")
        existing_status = _item_value(existing, "status") or "QUEUE_PENDING"
        if existing_digest != authenticated.body_digest or not existing_request_id:
            try:
                self._dynamodb.transact_write_items(
                    TransactItems=[
                        {
                            "Put": {
                                "TableName": self._table_name,
                                "Item": {
                                    "PK": _s(nonce_pk),
                                    "SK": _s("METADATA"),
                                    "item_type": _s("NONCE"),
                                    "created_at": _n(now_epoch),
                                    "expires_at": _n(nonce_expires),
                                },
                                "ConditionExpression": "attribute_not_exists(PK)",
                            }
                        },
                        {
                            "ConditionCheck": {
                                "TableName": self._table_name,
                                "Key": {
                                    "PK": _s(idempotency_pk),
                                    "SK": _s("METADATA"),
                                },
                                "ConditionExpression": "body_digest <> :digest",
                                "ExpressionAttributeValues": {
                                    ":digest": _s(authenticated.body_digest),
                                },
                            }
                        },
                    ]
                )
            except Exception as error:
                if _error_code(error) in {
                    "ConditionalCheckFailedException",
                    "TransactionCanceledException",
                }:
                    raise WorkflowError(
                        "NONCE_REPLAY", "Request nonce has already been used.", 409
                    ) from error
                raise WorkflowError(
                    "DYNAMODB_RESERVATION_FAILURE",
                    "Request could not be reserved.",
                    503,
                ) from error
            raise WorkflowError(
                "IDEMPOTENCY_DIGEST_CONFLICT",
                "Idempotency key was previously used for different content.",
                409,
            )

        try:
            self._dynamodb.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": {
                                "PK": _s(nonce_pk),
                                "SK": _s("METADATA"),
                                "item_type": _s("NONCE"),
                                "created_at": _n(now_epoch),
                                "expires_at": _n(nonce_expires),
                            },
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                    {
                        "ConditionCheck": {
                            "TableName": self._table_name,
                            "Key": {"PK": _s(idempotency_pk), "SK": _s("METADATA")},
                            "ConditionExpression": (
                                "body_digest = :digest AND request_id = :request_id"
                            ),
                            "ExpressionAttributeValues": {
                                ":digest": _s(authenticated.body_digest),
                                ":request_id": _s(existing_request_id),
                            },
                        }
                    },
                ]
            )
        except Exception as error:
            if _error_code(error) in {
                "ConditionalCheckFailedException",
                "TransactionCanceledException",
            }:
                raise WorkflowError(
                    "NONCE_REPLAY", "Request nonce has already been used.", 409
                ) from error
            raise WorkflowError(
                "DYNAMODB_RESERVATION_FAILURE",
                "Request could not be reserved.",
                503,
            ) from error

        try:
            request_item = self._get(self._request_pk(existing_request_id))
            existing_status = _item_value(request_item, "status") or existing_status
        except Exception as error:
            raise WorkflowError(
                "DYNAMODB_RESERVATION_FAILURE",
                "Request could not be reserved.",
                503,
            ) from error

        return Reservation(False, existing_request_id, existing_status)

    def _transition_status(
        self,
        *,
        idempotency_pk: str,
        request_id: str,
        expected_status: str,
        target_status: str,
        now_epoch: int,
        queue_message_id: str | None = None,
    ) -> TransitionResult:
        require_legal_transition(expected_status, target_status)

        idempotency_values = {
            ":expected": _s(expected_status),
            ":request_id": _s(request_id),
            ":status": _s(target_status),
            ":updated": _n(now_epoch),
        }
        request_values = {
            ":expected": _s(expected_status),
            ":idempotency_pk": _s(idempotency_pk),
            ":request_id": _s(request_id),
            ":status": _s(target_status),
            ":updated": _n(now_epoch),
        }
        idempotency_expression = "SET #status = :status, updated_at = :updated"
        request_expression = "SET #status = :status, updated_at = :updated"
        if queue_message_id:
            idempotency_values[":message_id"] = _s(queue_message_id)
            request_values[":message_id"] = _s(queue_message_id)
            idempotency_expression += ", queue_message_id = :message_id"
            request_expression += ", queue_message_id = :message_id"

        if target_status == WorkflowState.RECONCILE_REQUIRED.value:
            request_values[":next_attempt"] = _n(
                now_epoch + self._reconciliation_stale_seconds
            )
            request_expression += (
                ", reconcile_status = :status, next_attempt_at = :next_attempt"
            )
        elif target_status == WorkflowState.QUEUED.value:
            request_expression += " REMOVE reconcile_status, next_attempt_at"

        updates = [
            {
                "Update": {
                    "TableName": self._table_name,
                    "Key": {"PK": _s(idempotency_pk), "SK": _s("METADATA")},
                    "UpdateExpression": idempotency_expression,
                    "ConditionExpression": (
                        "#status = :expected AND request_id = :request_id"
                    ),
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": idempotency_values,
                }
            },
            {
                "Update": {
                    "TableName": self._table_name,
                    "Key": {
                        "PK": _s(self._request_pk(request_id)),
                        "SK": _s("METADATA"),
                    },
                    "UpdateExpression": request_expression,
                    "ConditionExpression": (
                        "#status = :expected AND request_id = :request_id AND "
                        "idempotency_reference = :idempotency_pk"
                    ),
                    "ExpressionAttributeNames": {"#status": "status"},
                    "ExpressionAttributeValues": request_values,
                }
            },
        ]
        try:
            self._dynamodb.transact_write_items(TransactItems=updates)
            return TransitionResult(True, target_status)
        except Exception as error:
            if not _is_conditional_failure(error):
                raise

        request_item = self._get(self._request_pk(request_id))
        authoritative_status = _item_value(request_item, "status")
        advanced_states = {
            state.value
            for state in WorkflowState
            if state != WorkflowState.QUEUE_PENDING
        }
        if authoritative_status in advanced_states:
            emit(
                "intake_state_transition_conflict",
                request_id=request_id,
                source_state=expected_status,
                state=authoritative_status,
                error_category="CONCURRENT_STATE_ADVANCE",
            )
            return TransitionResult(False, authoritative_status)

        emit(
            "intake_state_transition_conflict",
            request_id=request_id,
            source_state=expected_status,
            state=authoritative_status or "UNKNOWN",
            error_category="CONDITIONAL_STATE_CONFLICT",
        )
        raise WorkflowTransitionConflict(
            "Conditional workflow transition could not be classified as an advance."
        )

    def enqueue(
        self,
        authenticated: AuthenticatedRequest,
        reservation: Reservation,
        *,
        correlation_id: str,
        now_epoch: int,
    ) -> str:
        """Enqueue only a reference; SQS and DynamoDB are not one transaction."""

        idempotency_pk = self._idempotency_pk(authenticated)
        try:
            result = self._sqs.send_message(
                QueueUrl=self._queue_url,
                MessageBody=json.dumps(
                    {
                        "correlationId": correlation_id,
                        "requestId": reservation.request_id,
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        except Exception as error:
            try:
                transition = self._transition_status(
                    idempotency_pk=idempotency_pk,
                    request_id=reservation.request_id,
                    expected_status=WorkflowState.QUEUE_PENDING.value,
                    target_status=WorkflowState.RECONCILE_REQUIRED.value,
                    now_epoch=now_epoch,
                )
            except WorkflowTransitionConflict as state_error:
                raise WorkflowError(
                    "QUEUE_RECOVERY_STATE_CONFLICT",
                    "Request queue recovery state could not be confirmed.",
                    503,
                ) from state_error
            except Exception as state_error:
                raise WorkflowError(
                    "QUEUE_RECOVERY_STATE_FAILURE",
                    "Request was reserved but queue recovery state could not be recorded.",
                    503,
                ) from state_error
            if not transition.applied:
                return transition.status
            raise WorkflowError(
                "QUEUE_SUBMISSION_FAILURE",
                "Request was reserved but could not be queued.",
                503,
            ) from error

        message_id = str(result.get("MessageId") or "")
        try:
            transition = self._transition_status(
                idempotency_pk=idempotency_pk,
                request_id=reservation.request_id,
                expected_status=WorkflowState.QUEUE_PENDING.value,
                target_status=WorkflowState.QUEUED.value,
                now_epoch=now_epoch,
                queue_message_id=message_id or None,
            )
            return transition.status
        except WorkflowTransitionConflict as error:
            raise WorkflowError(
                "QUEUE_STATE_CONFIRMATION_CONFLICT",
                "Request was queued but its workflow state could not be confirmed.",
                503,
            ) from error
        except Exception as error:
            raise WorkflowError(
                "QUEUE_STATE_CONFIRMATION_FAILURE",
                "Request was queued but confirmation remains pending.",
                503,
            ) from error

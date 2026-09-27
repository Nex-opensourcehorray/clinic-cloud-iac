"""Atomic replay/idempotency reservation and durable queue handoff."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from common.authentication import AuthenticatedRequest


class WorkflowError(Exception):
    """A controlled workflow reservation or handoff failure."""

    def __init__(self, category: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class Reservation:
    created: bool
    request_id: str
    status: str


def _s(value: str) -> dict[str, str]:
    return {"S": value}


def _n(value: int) -> dict[str, str]:
    return {"N": str(value)}


def _error_code(error: Exception) -> str:
    response = getattr(error, "response", {})
    return str((response.get("Error") or {}).get("Code") or "")


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
    ) -> None:
        self._dynamodb = dynamodb_client
        self._sqs = sqs_client
        self._table_name = table_name
        self._queue_url = queue_url
        self._nonce_ttl_seconds = nonce_ttl_seconds
        self._idempotency_ttl_seconds = idempotency_ttl_seconds

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

        return Reservation(False, existing_request_id, existing_status)

    def _set_status(
        self,
        *,
        idempotency_pk: str,
        request_id: str,
        status: str,
        now_epoch: int,
        queue_message_id: str | None = None,
    ) -> None:
        values = {":status": _s(status), ":updated": _n(now_epoch)}
        expression = "SET #status = :status, updated_at = :updated"
        if queue_message_id:
            values[":message_id"] = _s(queue_message_id)
            expression += ", queue_message_id = :message_id"

        updates = []
        for pk in (idempotency_pk, self._request_pk(request_id)):
            updates.append(
                {
                    "Update": {
                        "TableName": self._table_name,
                        "Key": {"PK": _s(pk), "SK": _s("METADATA")},
                        "UpdateExpression": expression,
                        "ConditionExpression": "attribute_exists(PK)",
                        "ExpressionAttributeNames": {"#status": "status"},
                        "ExpressionAttributeValues": values,
                    }
                }
            )
        self._dynamodb.transact_write_items(TransactItems=updates)

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
                self._set_status(
                    idempotency_pk=idempotency_pk,
                    request_id=reservation.request_id,
                    status="RECONCILE_REQUIRED",
                    now_epoch=now_epoch,
                )
            except Exception:
                pass
            raise WorkflowError(
                "QUEUE_SUBMISSION_FAILURE",
                "Request was reserved but could not be queued.",
                503,
            ) from error

        message_id = str(result.get("MessageId") or "")
        try:
            self._set_status(
                idempotency_pk=idempotency_pk,
                request_id=reservation.request_id,
                status="QUEUED",
                now_epoch=now_epoch,
                queue_message_id=message_id or None,
            )
            return "QUEUED"
        except Exception:
            return "QUEUE_PENDING"

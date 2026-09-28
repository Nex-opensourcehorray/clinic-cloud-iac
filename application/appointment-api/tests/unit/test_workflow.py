from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
import sys
import unittest
from dataclasses import replace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from common.authentication import AuthenticatedRequest  # noqa: E402
from intake.workflow import WorkflowError, WorkflowRepository  # noqa: E402


class FakeAwsError(Exception):
    def __init__(
        self, code: str, *, cancellation_reasons: list[dict] | None = None
    ) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}
        if cancellation_reasons is not None:
            self.response["CancellationReasons"] = cancellation_reasons


class FakeDynamo:
    def __init__(
        self,
        *,
        initial_error: str | None = None,
        nonce_item: dict | None = None,
        idempotency_item: dict | None = None,
        request_item: dict | None = None,
        status_error: Exception | None = None,
        request_read_error: Exception | None = None,
    ) -> None:
        self.initial_error = initial_error
        self.nonce_item = nonce_item or {}
        self.idempotency_item = idempotency_item or {}
        self.request_item = request_item or {}
        self.status_error = status_error
        self.request_read_error = request_read_error
        self.transactions: list[list[dict]] = []
        self.gets: list[str] = []

    def transact_write_items(self, *, TransactItems, **kwargs):
        del kwargs
        self.transactions.append(TransactItems)
        for transaction_item in TransactItems:
            update = transaction_item.get("Update")
            if not update:
                continue
            expressions = " ".join(
                str(update.get(name) or "")
                for name in ("UpdateExpression", "ConditionExpression")
            )
            referenced = set(re.findall(r":[A-Za-z0-9_]+", expressions))
            provided = set((update.get("ExpressionAttributeValues") or {}).keys())
            if referenced != provided:
                raise AssertionError(
                    f"Expression placeholders differ: {referenced} != {provided}"
                )
        if len(TransactItems) == 3 and self.initial_error:
            raise FakeAwsError(self.initial_error)
        if len(TransactItems) == 2 and all("Update" in item for item in TransactItems):
            if self.status_error:
                raise self.status_error
        return {}

    def get_item(self, *, Key, **kwargs):
        del kwargs
        pk = Key["PK"]["S"]
        self.gets.append(pk)
        if pk.startswith("NONCE#"):
            return {"Item": self.nonce_item} if self.nonce_item else {}
        if pk.startswith("REQUEST#"):
            if self.request_read_error:
                raise self.request_read_error
            return {"Item": self.request_item} if self.request_item else {}
        return {"Item": self.idempotency_item} if self.idempotency_item else {}


class FakeSqs:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[dict] = []

    def send_message(self, **kwargs):
        self.messages.append(kwargs)
        if self.fail:
            raise FakeAwsError("ServiceUnavailable")
        return {"MessageId": "message-001"}


def authenticated(
    *, nonce: str = "nonce-000000000001", digest: str | None = None
) -> AuthenticatedRequest:
    body = b'{"patientReference":"SYNTHETIC-PATIENT-001"}'
    return AuthenticatedRequest(
        body_bytes=body,
        body_digest=digest or hashlib.sha256(body).hexdigest(),
        idempotency_key="idem-0001",
        key_id="v1",
        nonce=nonce,
        timestamp=2_000_000_000,
    )


class WorkflowTests(unittest.TestCase):
    @staticmethod
    def request_item(status: str, **fields):
        item = {
            "request_id": {"S": "request-001"},
            "status": {"S": status},
        }
        item.update(fields)
        return item

    @staticmethod
    def existing_request_item(
        auth: AuthenticatedRequest,
        status: str,
        request_id: str = "existing-request",
    ):
        return {
            "body_digest": {"S": auth.body_digest},
            "idempotency_reference": {
                "S": f"IDEMPOTENCY#{auth.key_id}#{auth.idempotency_key}"
            },
            "request_id": {"S": request_id},
            "status": {"S": status},
        }

    def conditional_race(self, status: str, **kwargs) -> FakeDynamo:
        return FakeDynamo(
            request_item=self.request_item(status, **kwargs),
            status_error=FakeAwsError("ConditionalCheckFailedException"),
        )

    def repository(self, dynamo: FakeDynamo, sqs: FakeSqs) -> WorkflowRepository:
        return WorkflowRepository(
            dynamodb_client=dynamo,
            sqs_client=sqs,
            table_name="workflow-table",
            queue_url="https://sqs.example/work",
            nonce_ttl_seconds=600,
            idempotency_ttl_seconds=604800,
            reconciliation_stale_seconds=300,
        )

    def reserve(self, repository: WorkflowRepository, auth=None):
        return repository.reserve(
            auth or authenticated(),
            request_id="request-001",
            request_document={"patientReference": "SYNTHETIC-PATIENT-001"},
            now_epoch=2_000_000_000,
        )

    def test_first_use_atomically_reserves_nonce_idempotency_and_request(self) -> None:
        dynamo = FakeDynamo()
        reservation = self.reserve(self.repository(dynamo, FakeSqs()))
        self.assertTrue(reservation.created)
        self.assertEqual(3, len(dynamo.transactions[0]))
        self.assertTrue(all("Put" in item for item in dynamo.transactions[0]))
        request_item = dynamo.transactions[0][2]["Put"]["Item"]
        self.assertEqual("QUEUE_PENDING", request_item["reconcile_status"]["S"])
        self.assertEqual("2000000300", request_item["next_attempt_at"]["N"])
        nonce_put = dynamo.transactions[0][0]["Put"]
        self.assertEqual("attribute_not_exists(PK)", nonce_put["ConditionExpression"])

    def test_nonce_replay_is_rejected(self) -> None:
        dynamo = FakeDynamo(
            initial_error="TransactionCanceledException",
            nonce_item={"PK": {"S": "existing"}},
        )
        sqs = FakeSqs()
        with self.assertRaises(WorkflowError) as raised:
            self.reserve(self.repository(dynamo, sqs))
        self.assertEqual("NONCE_REPLAY", raised.exception.category)
        self.assertNotIn("nonce-000000000001", raised.exception.message)
        self.assertNotIn("v1", raised.exception.message)
        self.assertEqual([], sqs.messages)

    def test_same_nonce_is_rejected_across_changed_retry_inputs(self) -> None:
        base = authenticated()
        variants = (
            replace(base, idempotency_key="different-idempotency"),
            replace(base, body_digest="0" * 64),
        )
        for auth in variants:
            with self.subTest(auth=auth):
                dynamo = FakeDynamo(
                    initial_error="TransactionCanceledException",
                    nonce_item={"PK": {"S": "existing"}},
                    request_item=self.request_item("PROCESSING"),
                )
                sqs = FakeSqs()
                with self.assertRaises(WorkflowError) as raised:
                    self.reserve(self.repository(dynamo, sqs), auth)
                self.assertEqual("NONCE_REPLAY", raised.exception.category)
                self.assertEqual([], sqs.messages)

    def test_replay_after_worker_processing_begins_is_rejected(self) -> None:
        dynamo = FakeDynamo(
            initial_error="TransactionCanceledException",
            nonce_item={"PK": {"S": "existing"}},
            request_item=self.request_item("PROCESSING"),
        )
        with self.assertRaises(WorkflowError) as raised:
            self.reserve(self.repository(dynamo, FakeSqs()))
        self.assertEqual("NONCE_REPLAY", raised.exception.category)
        self.assertEqual(1, len(dynamo.transactions))

    def test_same_idempotency_key_and_digest_returns_existing_request(self) -> None:
        auth = authenticated(nonce="nonce-000000000002")
        dynamo = FakeDynamo(
            initial_error="TransactionCanceledException",
            idempotency_item={
                "body_digest": {"S": auth.body_digest},
                "request_id": {"S": "existing-request"},
                "status": {"S": "QUEUED"},
            },
            request_item=self.existing_request_item(auth, "QUEUED"),
        )
        sqs = FakeSqs()
        reservation = self.reserve(self.repository(dynamo, sqs), auth)
        self.assertFalse(reservation.created)
        self.assertEqual("existing-request", reservation.request_id)
        self.assertEqual("QUEUED", reservation.status)
        self.assertEqual([], sqs.messages)

    def test_idempotent_retry_requires_authoritative_request_record(self) -> None:
        auth = authenticated(nonce="nonce-000000000002")
        dynamo = FakeDynamo(
            initial_error="TransactionCanceledException",
            idempotency_item={
                "body_digest": {"S": auth.body_digest},
                "request_id": {"S": "existing-request"},
                "status": {"S": "QUEUED"},
            },
        )
        with self.assertRaises(WorkflowError) as raised:
            self.reserve(self.repository(dynamo, FakeSqs()), auth)
        self.assertEqual(
            "IDEMPOTENCY_RECORD_INTEGRITY_FAILURE", raised.exception.category
        )

    def test_idempotent_retry_rejects_mismatched_request_linkage(self) -> None:
        auth = authenticated(nonce="nonce-000000000002")
        for field, value in (
            ("request_id", {"S": "different-request"}),
            ("idempotency_reference", {"S": "IDEMPOTENCY#v1#different"}),
            ("body_digest", {"S": "0" * 64}),
            ("status", {"S": "UNKNOWN_STATE"}),
        ):
            with self.subTest(field=field):
                request_item = self.existing_request_item(auth, "QUEUED")
                request_item[field] = value
                dynamo = FakeDynamo(
                    initial_error="TransactionCanceledException",
                    idempotency_item={
                        "body_digest": {"S": auth.body_digest},
                        "request_id": {"S": "existing-request"},
                        "status": {"S": "QUEUED"},
                    },
                    request_item=request_item,
                )
                with self.assertRaises(WorkflowError) as raised:
                    self.reserve(self.repository(dynamo, FakeSqs()), auth)
                self.assertEqual(
                    "IDEMPOTENCY_RECORD_INTEGRITY_FAILURE",
                    raised.exception.category,
                )

    def test_idempotent_retry_uses_authoritative_advanced_state_without_requeue(self) -> None:
        for status in (
            "QUEUED",
            "PROCESSING",
            "MANUAL_REVIEW_REQUIRED",
            "SUCCEEDED",
        ):
            with self.subTest(status=status):
                auth = authenticated(nonce="nonce-000000000002")
                dynamo = FakeDynamo(
                    initial_error="TransactionCanceledException",
                    idempotency_item={
                        "body_digest": {"S": auth.body_digest},
                        "request_id": {"S": "existing-request"},
                        "status": {"S": "QUEUE_PENDING"},
                    },
                    request_item=self.existing_request_item(auth, status),
                )
                sqs = FakeSqs()
                reservation = self.reserve(self.repository(dynamo, sqs), auth)
                self.assertFalse(reservation.created)
                self.assertEqual(status, reservation.status)
                self.assertEqual([], sqs.messages)

    def test_request_without_idempotency_record_fails_closed(self) -> None:
        dynamo = FakeDynamo(
            initial_error="TransactionCanceledException",
            request_item=self.request_item("QUEUED"),
        )
        with self.assertRaises(WorkflowError) as raised:
            self.reserve(self.repository(dynamo, FakeSqs()))
        self.assertEqual("DYNAMODB_RESERVATION_FAILURE", raised.exception.category)

    def test_same_idempotency_key_with_different_digest_conflicts(self) -> None:
        dynamo = FakeDynamo(
            initial_error="TransactionCanceledException",
            idempotency_item={
                "body_digest": {"S": "different-digest"},
                "request_id": {"S": "existing-request"},
            },
        )
        with self.assertRaises(WorkflowError) as raised:
            self.reserve(self.repository(dynamo, FakeSqs()))
        self.assertEqual("IDEMPOTENCY_DIGEST_CONFLICT", raised.exception.category)
        self.assertEqual(2, len(dynamo.transactions))
        self.assertIn("Put", dynamo.transactions[1][0])

    def test_same_idempotency_key_with_changed_appointment_field_conflicts(self) -> None:
        changed_body = b'{"patientReference":"SYNTHETIC-PATIENT-002"}'
        changed_auth = replace(
            authenticated(),
            body_bytes=changed_body,
            body_digest=hashlib.sha256(changed_body).hexdigest(),
        )
        original_digest = authenticated().body_digest
        dynamo = FakeDynamo(
            initial_error="TransactionCanceledException",
            idempotency_item={
                "body_digest": {"S": original_digest},
                "request_id": {"S": "existing-request"},
            },
        )

        with self.assertRaises(WorkflowError) as raised:
            self.reserve(self.repository(dynamo, FakeSqs()), changed_auth)

        self.assertEqual("IDEMPOTENCY_DIGEST_CONFLICT", raised.exception.category)
        self.assertEqual(2, len(dynamo.transactions))

    def test_concurrent_identical_reservation_cannot_create_second_request(self) -> None:
        dynamo = FakeDynamo(
            initial_error="TransactionCanceledException",
            nonce_item={"PK": {"S": "already-won-by-concurrent-request"}},
        )
        with self.assertRaises(WorkflowError) as raised:
            self.reserve(self.repository(dynamo, FakeSqs()))
        self.assertEqual("NONCE_REPLAY", raised.exception.category)
        self.assertEqual(1, len(dynamo.transactions))

    def test_dynamodb_failure_fails_closed_before_sqs(self) -> None:
        dynamo = FakeDynamo(initial_error="InternalServerError")
        sqs = FakeSqs()
        with self.assertRaises(WorkflowError) as raised:
            self.reserve(self.repository(dynamo, sqs))
        self.assertEqual("DYNAMODB_RESERVATION_FAILURE", raised.exception.category)
        self.assertEqual([], sqs.messages)

    def test_sqs_failure_marks_reconciliation_required(self) -> None:
        dynamo = FakeDynamo()
        sqs = FakeSqs(fail=True)
        repository = self.repository(dynamo, sqs)
        reservation = self.reserve(repository)
        with self.assertRaises(WorkflowError) as raised:
            repository.enqueue(
                authenticated(),
                reservation,
                correlation_id="correlation-001",
                now_epoch=2_000_000_000,
            )
        self.assertEqual("QUEUE_SUBMISSION_FAILURE", raised.exception.category)
        update = dynamo.transactions[-1][0]["Update"]
        self.assertEqual(
            "RECONCILE_REQUIRED",
            update["ExpressionAttributeValues"][":status"]["S"],
        )
        idempotency_update = dynamo.transactions[-1][0]["Update"]
        request_update = dynamo.transactions[-1][1]["Update"]
        self.assertNotIn(":next_attempt", idempotency_update["ExpressionAttributeValues"])
        self.assertIn(":next_attempt", request_update["ExpressionAttributeValues"])
        self.assertIn("next_attempt_at", request_update["UpdateExpression"])

    def test_queue_payload_is_data_minimized(self) -> None:
        dynamo = FakeDynamo()
        sqs = FakeSqs()
        repository = self.repository(dynamo, sqs)
        reservation = self.reserve(repository)
        self.assertEqual(
            "QUEUED",
            repository.enqueue(
                authenticated(),
                reservation,
                correlation_id="correlation-001",
                now_epoch=2_000_000_000,
            ),
        )
        payload = json.loads(sqs.messages[0]["MessageBody"])
        self.assertEqual({"correlationId", "requestId"}, set(payload))
        self.assertNotIn("patientReference", sqs.messages[0]["MessageBody"])

    def test_normal_queue_pending_to_queued_transition_is_conditional(self) -> None:
        dynamo = FakeDynamo()
        repository = self.repository(dynamo, FakeSqs())
        status = repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual("QUEUED", status)
        request_update = dynamo.transactions[-1][1]["Update"]
        self.assertIn("#status = :expected", request_update["ConditionExpression"])
        self.assertEqual(
            "QUEUE_PENDING",
            request_update["ExpressionAttributeValues"][":expected"]["S"],
        )

    def test_processing_race_is_not_overwritten_by_queue_confirmation(self) -> None:
        dynamo = self.conditional_race("PROCESSING")
        repository = self.repository(dynamo, FakeSqs())
        status = repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual("PROCESSING", status)
        self.assertEqual(2, len(dynamo.transactions))

    def test_failed_retryable_race_is_not_overwritten_by_queue_confirmation(self) -> None:
        dynamo = self.conditional_race("FAILED_RETRYABLE")
        repository = self.repository(dynamo, FakeSqs())
        status = repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual("FAILED_RETRYABLE", status)
        self.assertEqual(2, len(dynamo.transactions))

    def test_reconcile_required_race_is_not_overwritten_by_queue_confirmation(self) -> None:
        dynamo = self.conditional_race("RECONCILE_REQUIRED")
        repository = self.repository(dynamo, FakeSqs())
        status = repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual("RECONCILE_REQUIRED", status)
        self.assertEqual(2, len(dynamo.transactions))

    def test_manual_review_race_is_not_overwritten_by_queue_confirmation(self) -> None:
        dynamo = self.conditional_race("MANUAL_REVIEW_REQUIRED")
        repository = self.repository(dynamo, FakeSqs())
        status = repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual("MANUAL_REVIEW_REQUIRED", status)
        self.assertEqual(2, len(dynamo.transactions))

    def test_succeeded_race_is_not_overwritten_by_queue_confirmation(self) -> None:
        dynamo = self.conditional_race("SUCCEEDED")
        repository = self.repository(dynamo, FakeSqs())
        status = repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual("SUCCEEDED", status)
        self.assertEqual(2, len(dynamo.transactions))

    def test_duplicate_queued_confirmation_is_safe_and_idempotent(self) -> None:
        dynamo = self.conditional_race("QUEUED")
        repository = self.repository(dynamo, FakeSqs())
        status = repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual("QUEUED", status)
        self.assertEqual(2, len(dynamo.transactions))

    def test_failed_send_processing_race_preserves_authoritative_state(self) -> None:
        dynamo = self.conditional_race("PROCESSING")
        repository = self.repository(dynamo, FakeSqs(fail=True))
        status = repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual("PROCESSING", status)
        self.assertEqual(2, len(dynamo.transactions))

    def test_conditional_classification_read_never_grants_write_ownership(self) -> None:
        dynamo = self.conditional_race("PROCESSING")
        repository = self.repository(dynamo, FakeSqs())
        repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual(["REQUEST#request-001"], dynamo.gets)
        self.assertEqual(2, len(dynamo.transactions))

    def test_request_and_idempotency_updates_are_one_guarded_transaction(self) -> None:
        dynamo = FakeDynamo()
        repository = self.repository(dynamo, FakeSqs())
        repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        updates = dynamo.transactions[-1]
        self.assertEqual(2, len(updates))
        self.assertTrue(all("Update" in item for item in updates))
        self.assertIn("request_id = :request_id", updates[0]["Update"]["ConditionExpression"])
        self.assertIn("#status = :expected", updates[0]["Update"]["ConditionExpression"])
        self.assertIn("idempotency_reference = :idempotency_pk", updates[1]["Update"]["ConditionExpression"])
        self.assertIn("#status = :expected", updates[1]["Update"]["ConditionExpression"])

    def test_transaction_cancellation_with_conditional_reason_is_classified(self) -> None:
        dynamo = FakeDynamo(
            request_item=self.request_item("PROCESSING"),
            status_error=FakeAwsError(
                "TransactionCanceledException",
                cancellation_reasons=[
                    {"Code": "None"},
                    {"Code": "ConditionalCheckFailed"},
                ],
            ),
        )
        repository = self.repository(dynamo, FakeSqs())
        status = repository.enqueue(
            authenticated(),
            self.reserve(repository),
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual("PROCESSING", status)

    def test_conditional_failure_while_still_pending_fails_without_fallback(self) -> None:
        dynamo = self.conditional_race("QUEUE_PENDING")
        repository = self.repository(dynamo, FakeSqs())
        with self.assertRaises(WorkflowError) as raised:
            repository.enqueue(
                authenticated(),
                self.reserve(repository),
                correlation_id="correlation-001",
                now_epoch=2_000_000_000,
            )
        self.assertEqual("QUEUE_STATE_CONFIRMATION_CONFLICT", raised.exception.category)
        self.assertEqual(2, len(dynamo.transactions))

    def test_failed_send_service_failure_leaves_queue_pending_recoverable(self) -> None:
        dynamo = FakeDynamo(
            request_item=self.request_item("QUEUE_PENDING"),
            status_error=FakeAwsError("InternalServerError"),
        )
        repository = self.repository(dynamo, FakeSqs(fail=True))
        with self.assertRaises(WorkflowError) as raised:
            repository.enqueue(
                authenticated(),
                self.reserve(repository),
                correlation_id="correlation-001",
                now_epoch=2_000_000_000,
            )
        self.assertEqual("QUEUE_RECOVERY_STATE_FAILURE", raised.exception.category)
        self.assertEqual("QUEUE_PENDING", dynamo.request_item["status"]["S"])
        self.assertEqual(2, len(dynamo.transactions))

    def test_concurrency_log_excludes_sensitive_item_values(self) -> None:
        marker = "SYNTHETIC-CONTACT-NOT-FOR-LOGS"
        dynamo = self.conditional_race(
            "PROCESSING", contact_value={"S": marker}
        )
        repository = self.repository(dynamo, FakeSqs())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            repository.enqueue(
                authenticated(),
                self.reserve(repository),
                correlation_id="correlation-001",
                now_epoch=2_000_000_000,
            )
        self.assertNotIn(marker, output.getvalue())
        self.assertNotIn("contact_value", output.getvalue())

    def test_uncertain_post_send_state_is_surfaced_without_resend(self) -> None:
        dynamo = FakeDynamo(status_error=FakeAwsError("InternalServerError"))
        sqs = FakeSqs()
        repository = self.repository(dynamo, sqs)
        reservation = self.reserve(repository)
        with self.assertRaises(WorkflowError) as raised:
            repository.enqueue(
                authenticated(),
                reservation,
                correlation_id="correlation-001",
                now_epoch=2_000_000_000,
            )
        self.assertEqual("QUEUE_STATE_CONFIRMATION_FAILURE", raised.exception.category)
        self.assertEqual(1, len(sqs.messages))

    def test_queued_update_removes_reconciliation_index_attributes(self) -> None:
        dynamo = FakeDynamo()
        repository = self.repository(dynamo, FakeSqs())
        reservation = self.reserve(repository)
        repository.enqueue(
            authenticated(),
            reservation,
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        request_update = dynamo.transactions[-1][1]["Update"]
        self.assertIn("REMOVE reconcile_status, next_attempt_at", request_update["UpdateExpression"])
        self.assertNotIn(":next_attempt", request_update["ExpressionAttributeValues"])


if __name__ == "__main__":
    unittest.main()

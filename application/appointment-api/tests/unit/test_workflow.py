from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from common.authentication import AuthenticatedRequest  # noqa: E402
from intake.workflow import WorkflowError, WorkflowRepository  # noqa: E402


class FakeAwsError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeDynamo:
    def __init__(
        self,
        *,
        initial_error: str | None = None,
        nonce_item: dict | None = None,
        idempotency_item: dict | None = None,
        status_error: bool = False,
    ) -> None:
        self.initial_error = initial_error
        self.nonce_item = nonce_item or {}
        self.idempotency_item = idempotency_item or {}
        self.status_error = status_error
        self.transactions: list[list[dict]] = []
        self.gets: list[str] = []

    def transact_write_items(self, *, TransactItems, **kwargs):
        del kwargs
        self.transactions.append(TransactItems)
        if len(TransactItems) == 3 and self.initial_error:
            raise FakeAwsError(self.initial_error)
        if len(TransactItems) == 2 and all("Update" in item for item in TransactItems):
            if self.status_error:
                raise FakeAwsError("InternalServerError")
        return {}

    def get_item(self, *, Key, **kwargs):
        del kwargs
        pk = Key["PK"]["S"]
        self.gets.append(pk)
        if pk.startswith("NONCE#"):
            return {"Item": self.nonce_item} if self.nonce_item else {}
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
    def repository(self, dynamo: FakeDynamo, sqs: FakeSqs) -> WorkflowRepository:
        return WorkflowRepository(
            dynamodb_client=dynamo,
            sqs_client=sqs,
            table_name="workflow-table",
            queue_url="https://sqs.example/work",
            nonce_ttl_seconds=600,
            idempotency_ttl_seconds=604800,
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

    def test_nonce_replay_is_rejected(self) -> None:
        dynamo = FakeDynamo(
            initial_error="TransactionCanceledException",
            nonce_item={"PK": {"S": "existing"}},
        )
        sqs = FakeSqs()
        with self.assertRaises(WorkflowError) as raised:
            self.reserve(self.repository(dynamo, sqs))
        self.assertEqual("NONCE_REPLAY", raised.exception.category)
        self.assertEqual([], sqs.messages)

    def test_same_idempotency_key_and_digest_returns_existing_request(self) -> None:
        auth = authenticated(nonce="nonce-000000000002")
        dynamo = FakeDynamo(
            initial_error="TransactionCanceledException",
            idempotency_item={
                "body_digest": {"S": auth.body_digest},
                "request_id": {"S": "existing-request"},
                "status": {"S": "QUEUED"},
            },
        )
        sqs = FakeSqs()
        reservation = self.reserve(self.repository(dynamo, sqs), auth)
        self.assertFalse(reservation.created)
        self.assertEqual("existing-request", reservation.request_id)
        self.assertEqual("QUEUED", reservation.status)
        self.assertEqual([], sqs.messages)

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

    def test_uncertain_post_send_state_does_not_resend(self) -> None:
        dynamo = FakeDynamo(status_error=True)
        sqs = FakeSqs()
        repository = self.repository(dynamo, sqs)
        reservation = self.reserve(repository)
        status = repository.enqueue(
            authenticated(),
            reservation,
            correlation_id="correlation-001",
            now_epoch=2_000_000_000,
        )
        self.assertEqual("QUEUE_PENDING", status)
        self.assertEqual(1, len(sqs.messages))


if __name__ == "__main__":
    unittest.main()

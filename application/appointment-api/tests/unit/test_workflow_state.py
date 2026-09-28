from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from common.state_machine import InvalidStateTransition  # noqa: E402
from common.workflow_state import WorkflowStateRepository  # noqa: E402


class FakeAwsError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


def state_item(status: str, *, processing: int = 1, reconciliation: int = 0):
    return {
        "request_id": {"S": "request-1"},
        "status": {"S": status},
        "processing_attempts": {"N": str(processing)},
        "reconciliation_attempts": {"N": str(reconciliation)},
    }


class ScriptedDynamo:
    def __init__(self) -> None:
        self.update_outcomes: list[object] = []
        self.current_item = state_item("PROCESSING")
        self.query_results: list[dict] = []
        self.updates: list[dict] = []
        self.queries: list[dict] = []

    def update_item(self, **kwargs):
        expressions = " ".join(
            str(kwargs.get(name) or "")
            for name in ("UpdateExpression", "ConditionExpression")
        )
        referenced = set(re.findall(r":[A-Za-z0-9_]+", expressions))
        provided = set((kwargs.get("ExpressionAttributeValues") or {}).keys())
        if referenced != provided:
            raise AssertionError(
                f"Expression placeholders differ: {referenced} != {provided}"
            )
        self.updates.append(kwargs)
        outcome = self.update_outcomes.pop(0) if self.update_outcomes else {}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def get_item(self, **kwargs):
        del kwargs
        return {"Item": self.current_item}

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return self.query_results.pop(0) if self.query_results else {"Items": []}


class RecordingSqs:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return {"MessageId": "message-1"}


class WorkflowStateRepositoryTests(unittest.TestCase):
    def repository(self, dynamo=None, sqs=None):
        return WorkflowStateRepository(
            dynamodb_client=dynamo or ScriptedDynamo(),
            sqs_client=sqs or RecordingSqs(),
            table_name="workflow-table",
            reconciliation_index_name="reconciliation-index",
            queue_url="https://sqs.example/work",
            processing_lease_seconds=120,
            reconciliation_backoff_seconds=300,
            maximum_reconciliation_attempts=3,
        )

    def test_first_worker_acquisition_is_one_conditional_update(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.update_outcomes = [{"Attributes": state_item("PROCESSING")}]
        decision = self.repository(dynamo).acquire_processing(
            request_id="request-1", owner_token="owner-1", now_epoch=1000
        )
        self.assertTrue(decision.acquired)
        self.assertEqual(1, len(dynamo.updates))
        self.assertIn("#status IN", dynamo.updates[0]["ConditionExpression"])
        self.assertIn("ADD processing_attempts :one", dynamo.updates[0]["UpdateExpression"])

    def test_active_owner_duplicate_cannot_take_ownership(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.update_outcomes = [
            FakeAwsError("ConditionalCheckFailedException"),
            FakeAwsError("ConditionalCheckFailedException"),
        ]
        decision = self.repository(dynamo).acquire_processing(
            request_id="request-1", owner_token="owner-2", now_epoch=1000
        )
        self.assertFalse(decision.acquired)
        self.assertEqual("PROCESSING", decision.state.status)
        self.assertEqual(2, len(dynamo.updates))

    def test_unexpired_processing_lease_cannot_be_stolen(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.current_item = state_item("PROCESSING")
        dynamo.update_outcomes = [
            FakeAwsError("ConditionalCheckFailedException"),
            FakeAwsError("ConditionalCheckFailedException"),
        ]
        decision = self.repository(dynamo).acquire_processing(
            request_id="request-1", owner_token="owner-competitor", now_epoch=1000
        )
        self.assertFalse(decision.acquired)
        self.assertIn("lease_expires_at <= :now", dynamo.updates[1]["ConditionExpression"])

    def test_expired_processing_lease_can_be_recovered_conditionally(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.update_outcomes = [
            FakeAwsError("ConditionalCheckFailedException"),
            {"Attributes": state_item("PROCESSING", processing=2)},
        ]
        decision = self.repository(dynamo).acquire_processing(
            request_id="request-1", owner_token="owner-2", now_epoch=1000
        )
        self.assertTrue(decision.acquired)
        self.assertTrue(decision.recovered_expired_lease)
        self.assertIn("lease_expires_at <= :now", dynamo.updates[1]["ConditionExpression"])

    def test_terminal_state_cannot_be_overwritten_by_stale_worker(self) -> None:
        for status in ("MANUAL_REVIEW_REQUIRED", "SUCCEEDED"):
            with self.subTest(status=status):
                dynamo = ScriptedDynamo()
                dynamo.current_item = state_item(status)
                dynamo.update_outcomes = [
                    FakeAwsError("ConditionalCheckFailedException"),
                    FakeAwsError("ConditionalCheckFailedException"),
                ]
                decision = self.repository(dynamo).acquire_processing(
                    request_id="request-1", owner_token="owner-3", now_epoch=1000
                )
                self.assertFalse(decision.acquired)
                self.assertEqual(status, decision.state.status)

    def test_out_of_order_sources_are_in_atomic_processing_condition(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.update_outcomes = [{"Attributes": state_item("PROCESSING")}]
        self.repository(dynamo).acquire_processing(
            request_id="request-1", owner_token="owner-1", now_epoch=1000
        )
        values = dynamo.updates[0]["ExpressionAttributeValues"]
        self.assertEqual("QUEUE_PENDING", values[":queue_pending"]["S"])
        self.assertEqual("RECONCILE_REQUIRED", values[":reconcile_required"]["S"])

    def test_manual_review_update_contains_only_safe_metadata(self) -> None:
        dynamo = ScriptedDynamo()
        self.repository(dynamo).mark_manual_review(
            request_id="request-1",
            owner_token="owner-1",
            reason="CLINICAL_ADAPTER_UNAVAILABLE",
            now_epoch=1000,
        )
        serialized = json.dumps(dynamo.updates[0], sort_keys=True)
        self.assertIn("processing_owner = :owner", serialized)
        for forbidden in ("request_payload", "contact", "signature", "secret"):
            self.assertNotIn(forbidden, serialized.lower())

    def test_gsi_query_is_bounded_and_never_scans(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.query_results = [
            {"Items": [{"PK": {"S": "REQUEST#request-1"}, "SK": {"S": "METADATA"}}]}
        ]
        result = self.repository(dynamo).query_due(
            status="QUEUE_PENDING", now_epoch=1000, limit=25
        )
        self.assertEqual(["request-1"], result)
        self.assertEqual("reconciliation-index", dynamo.queries[0]["IndexName"])
        self.assertEqual(25, dynamo.queries[0]["Limit"])
        self.assertIn("next_attempt_at <= :now", dynamo.queries[0]["KeyConditionExpression"])
        self.assertFalse(hasattr(dynamo, "scan"))

    def test_backoff_not_elapsed_is_excluded_by_query_key_condition(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.query_results = [{"Items": []}]
        result = self.repository(dynamo).query_due(
            status="RECONCILE_REQUIRED", now_epoch=1000, limit=25
        )
        self.assertEqual([], result)
        values = dynamo.queries[0]["ExpressionAttributeValues"]
        self.assertEqual("1000", values[":now"]["N"])
        self.assertIn("next_attempt_at <= :now", dynamo.queries[0]["KeyConditionExpression"])

    def test_reference_only_reenqueue_payload(self) -> None:
        sqs = RecordingSqs()
        self.repository(sqs=sqs).send_reference(
            request_id="request-1", correlation_id="correlation-1"
        )
        body = json.loads(sqs.messages[0]["MessageBody"])
        self.assertEqual({"requestId", "correlationId"}, set(body))
        self.assertEqual("request-1", body["requestId"])

    def test_reconciliation_acquisition_is_conditional_and_increments_attempt(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.update_outcomes = [
            {"Attributes": state_item("RECONCILE_REQUIRED", reconciliation=1)}
        ]
        decision = self.repository(dynamo).acquire_reconciliation(
            request_id="request-1",
            expected_status="FAILED_RETRYABLE",
            owner_token="reconciler-1",
            now_epoch=1000,
        )
        self.assertTrue(decision.acquired)
        self.assertIn("next_attempt_at <= :now", dynamo.updates[0]["ConditionExpression"])
        self.assertIn("ADD reconciliation_attempts :one", dynamo.updates[0]["UpdateExpression"])
        condition = dynamo.updates[0]["ConditionExpression"]
        self.assertIn("#status = :expected", condition)
        self.assertIn("next_attempt_at <= :now", condition)
        self.assertIn("reconciliation_lease_expires_at <= :now", condition)
        self.assertIn("reconciliation_attempts < :maximum_attempts", condition)

    def test_stale_reconciler_cannot_regress_newer_worker_state(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.current_item = state_item("PROCESSING", reconciliation=1)
        dynamo.update_outcomes = [
            FakeAwsError("ConditionalCheckFailedException")
        ]
        decision = self.repository(dynamo).acquire_reconciliation(
            request_id="request-1",
            expected_status="QUEUE_PENDING",
            owner_token="stale-reconciler",
            now_epoch=1000,
        )
        self.assertFalse(decision.acquired)
        self.assertEqual("PROCESSING", decision.state.status)
        self.assertEqual(1, len(dynamo.updates))

    def test_worker_and_reconciler_completion_require_matching_owner(self) -> None:
        dynamo = ScriptedDynamo()
        repository = self.repository(dynamo)
        repository.mark_manual_review(
            request_id="request-1",
            owner_token="owner-1",
            reason="SAFE_REASON",
            now_epoch=1000,
        )
        repository.mark_failed_retryable(
            request_id="request-1",
            owner_token="owner-1",
            reason="SAFE_REASON",
            now_epoch=1000,
        )
        repository.complete_reconciliation(
            request_id="request-1",
            owner_token="reconciler-1",
            message_id="message-1",
            now_epoch=1000,
        )
        repository.record_reconciliation_failure(
            request_id="request-1",
            owner_token="reconciler-1",
            attempt_count=1,
            now_epoch=1000,
        )
        self.assertIn(
            "processing_owner = :owner", dynamo.updates[0]["ConditionExpression"]
        )
        self.assertIn(
            "processing_owner = :owner", dynamo.updates[1]["ConditionExpression"]
        )
        self.assertIn(
            "reconciliation_owner = :owner",
            dynamo.updates[2]["ConditionExpression"],
        )
        self.assertIn(
            "reconciliation_owner = :owner",
            dynamo.updates[3]["ConditionExpression"],
        )

    def test_wrong_owner_conditional_failures_are_not_treated_as_success(self) -> None:
        operations = (
            (
                "complete_reconciliation",
                {
                    "request_id": "request-1",
                    "owner_token": "wrong-owner",
                    "message_id": "message-1",
                    "now_epoch": 1000,
                },
            ),
            (
                "record_reconciliation_failure",
                {
                    "request_id": "request-1",
                    "owner_token": "wrong-owner",
                    "attempt_count": 1,
                    "now_epoch": 1000,
                },
            ),
        )
        for operation, kwargs in operations:
            with self.subTest(operation=operation):
                dynamo = ScriptedDynamo()
                dynamo.update_outcomes = [
                    FakeAwsError("ConditionalCheckFailedException")
                ]
                with self.assertRaises(FakeAwsError):
                    getattr(self.repository(dynamo), operation)(**kwargs)

    def test_dynamodb_service_error_during_ownership_acquisition_propagates(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.update_outcomes = [FakeAwsError("InternalServerError")]
        with self.assertRaises(FakeAwsError):
            self.repository(dynamo).acquire_processing(
                request_id="request-1", owner_token="owner-1", now_epoch=1000
            )
        self.assertEqual(1, len(dynamo.updates))

    def test_reconciliation_attempts_zero_one_two_remain_bounded(self) -> None:
        for attempt_count in (0, 1, 2):
            with self.subTest(attempt_count=attempt_count):
                dynamo = ScriptedDynamo()
                target = self.repository(dynamo).record_reconciliation_failure(
                    request_id="request-1",
                    owner_token="reconciler-1",
                    attempt_count=attempt_count,
                    now_epoch=1000,
                )
                self.assertEqual("RECONCILE_REQUIRED", target)
                self.assertEqual(
                    "1300",
                    dynamo.updates[0]["ExpressionAttributeValues"][":next_attempt"]["N"],
                )

    def test_query_is_one_bounded_page_per_invocation(self) -> None:
        dynamo = ScriptedDynamo()
        dynamo.query_results = [
            {
                "Items": [
                    {"PK": {"S": "REQUEST#request-1"}, "SK": {"S": "METADATA"}}
                ],
                "LastEvaluatedKey": {"PK": {"S": "REQUEST#request-1"}},
            }
        ]
        result = self.repository(dynamo).query_due(
            status="FAILED_RETRYABLE", now_epoch=1000, limit=25
        )
        self.assertEqual(["request-1"], result)
        self.assertEqual(1, len(dynamo.queries))
        self.assertEqual(25, dynamo.queries[0]["Limit"])

    def test_failed_reconciliation_uses_backoff_before_next_attempt(self) -> None:
        dynamo = ScriptedDynamo()
        target = self.repository(dynamo).record_reconciliation_failure(
            request_id="request-1",
            owner_token="reconciler-1",
            attempt_count=1,
            now_epoch=1000,
        )
        self.assertEqual("RECONCILE_REQUIRED", target)
        self.assertEqual(
            "1300",
            dynamo.updates[0]["ExpressionAttributeValues"][":next_attempt"]["N"],
        )

    def test_maximum_reconciliation_attempt_escalates_to_manual_review(self) -> None:
        dynamo = ScriptedDynamo()
        target = self.repository(dynamo).record_reconciliation_failure(
            request_id="request-1",
            owner_token="reconciler-1",
            attempt_count=3,
            now_epoch=1000,
        )
        self.assertEqual("MANUAL_REVIEW_REQUIRED", target)

    def test_invalid_state_transition_is_rejected_before_dynamodb(self) -> None:
        dynamo = ScriptedDynamo()
        with self.assertRaises(InvalidStateTransition):
            self.repository(dynamo).escalate_exhausted(
                request_id="request-1",
                expected_status="SUCCEEDED",
                now_epoch=1000,
            )
        self.assertEqual([], dynamo.updates)

    def test_manual_review_state_cannot_be_silently_reopened(self) -> None:
        dynamo = ScriptedDynamo()
        with self.assertRaises(InvalidStateTransition):
            self.repository(dynamo).escalate_exhausted(
                request_id="request-1",
                expected_status="MANUAL_REVIEW_REQUIRED",
                now_epoch=1000,
            )
        self.assertEqual([], dynamo.updates)


if __name__ == "__main__":
    unittest.main()

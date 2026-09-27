from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from common.workflow_state import OwnershipDecision, RequestState  # noqa: E402
from reconciler.handler import handle_reconciliation  # noqa: E402


class FakeRepository:
    def __init__(self) -> None:
        self.due: dict[str, list[str]] = {}
        self.decisions: dict[str, OwnershipDecision] = {}
        self.query_calls: list[dict] = []
        self.acquire_calls: list[dict] = []
        self.send_calls: list[dict] = []
        self.complete_calls: list[dict] = []
        self.failure_calls: list[dict] = []
        self.escalate_calls: list[dict] = []
        self.send_error = False
        self.complete_error = False
        self.failure_target = "RECONCILE_REQUIRED"
        self.escalate_result = True
        self.backlog = False

    def query_due(self, **kwargs):
        self.query_calls.append(kwargs)
        return list(self.due.get(kwargs["status"], []))

    def acquire_reconciliation(self, **kwargs):
        self.acquire_calls.append(kwargs)
        return self.decisions.get(
            kwargs["request_id"],
            OwnershipDecision(
                True,
                RequestState(
                    kwargs["request_id"],
                    "RECONCILE_REQUIRED",
                    reconciliation_attempts=1,
                ),
            ),
        )

    def escalate_exhausted(self, **kwargs):
        self.escalate_calls.append(kwargs)
        return self.escalate_result

    def send_reference(self, **kwargs):
        self.send_calls.append(kwargs)
        if self.send_error:
            raise RuntimeError("synthetic send uncertainty")
        return "message-1"

    def complete_reconciliation(self, **kwargs):
        self.complete_calls.append(kwargs)
        if self.complete_error:
            raise RuntimeError("synthetic completion uncertainty")

    def record_reconciliation_failure(self, **kwargs):
        self.failure_calls.append(kwargs)
        return self.failure_target

    def manual_review_exists(self):
        return self.backlog


class ReconcilerTests(unittest.TestCase):
    def invoke(self, repository: FakeRepository, event=None):
        return handle_reconciliation(
            event or {},
            SimpleNamespace(aws_request_id="reconciler-invocation"),
            repository=repository,
            now=lambda: 1000,
            owner_factory=lambda: "reconciler-owner",
            batch_size=25,
        )

    def test_fresh_queue_pending_is_not_reconciled(self) -> None:
        repository = FakeRepository()
        result = self.invoke(repository)
        self.assertEqual(0, result["attempted"])
        self.assertEqual([], repository.send_calls)

    def test_stale_queue_pending_is_reenqueued(self) -> None:
        repository = FakeRepository()
        repository.due["QUEUE_PENDING"] = ["request-1"]
        result = self.invoke(repository)
        self.assertEqual(1, result["requeued"])
        self.assertEqual("request-1", repository.send_calls[0]["request_id"])
        self.assertEqual(1, len(repository.complete_calls))

    def test_reconcile_required_is_retried(self) -> None:
        repository = FakeRepository()
        repository.due["RECONCILE_REQUIRED"] = ["request-1"]
        self.invoke(repository)
        self.assertEqual(
            "RECONCILE_REQUIRED", repository.acquire_calls[0]["expected_status"]
        )

    def test_failed_retryable_participates_in_bounded_reconciliation(self) -> None:
        repository = FakeRepository()
        repository.due["FAILED_RETRYABLE"] = ["request-1"]
        result = self.invoke(repository)
        self.assertEqual(1, result["requeued"])
        self.assertEqual(
            "FAILED_RETRYABLE", repository.acquire_calls[0]["expected_status"]
        )

    def test_failed_reenqueue_remains_recoverable(self) -> None:
        repository = FakeRepository()
        repository.due["QUEUE_PENDING"] = ["request-1"]
        repository.send_error = True
        result = self.invoke(repository)
        self.assertEqual(0, result["requeued"])
        self.assertEqual(1, len(repository.failure_calls))
        self.assertEqual("RECONCILE_REQUIRED", repository.failure_target)

    def test_uncertain_completion_is_recorded_as_reconciliation_failure(self) -> None:
        repository = FakeRepository()
        repository.due["RECONCILE_REQUIRED"] = ["request-1"]
        repository.complete_error = True
        self.invoke(repository)
        self.assertEqual(1, len(repository.send_calls))
        self.assertEqual(1, len(repository.failure_calls))

    def test_max_attempt_failure_escalates_to_manual_review(self) -> None:
        repository = FakeRepository()
        repository.due["RECONCILE_REQUIRED"] = ["request-1"]
        repository.send_error = True
        repository.failure_target = "MANUAL_REVIEW_REQUIRED"
        result = self.invoke(repository)
        self.assertEqual(1, result["manualReview"])

    def test_already_exhausted_request_is_escalated_without_send(self) -> None:
        repository = FakeRepository()
        repository.due["RECONCILE_REQUIRED"] = ["request-1"]
        repository.decisions["request-1"] = OwnershipDecision(
            False,
            RequestState(
                "request-1", "RECONCILE_REQUIRED", reconciliation_attempts=3
            ),
            exhausted=True,
        )
        result = self.invoke(repository)
        self.assertEqual(1, result["manualReview"])
        self.assertEqual(1, len(repository.escalate_calls))
        self.assertEqual([], repository.send_calls)

    def test_duplicate_reconciler_invocation_loses_ownership_safely(self) -> None:
        repository = FakeRepository()
        repository.due["QUEUE_PENDING"] = ["request-1"]
        repository.decisions["request-1"] = OwnershipDecision(
            False, RequestState("request-1", "RECONCILE_REQUIRED")
        )
        result = self.invoke(repository)
        self.assertEqual(1, result["conflicts"])
        self.assertEqual([], repository.send_calls)

    def test_expired_processing_lease_is_recovered(self) -> None:
        repository = FakeRepository()
        repository.due["PROCESSING"] = ["request-1"]
        repository.decisions["request-1"] = OwnershipDecision(
            True,
            RequestState(
                "request-1", "RECONCILE_REQUIRED", reconciliation_attempts=1
            ),
            recovered_expired_lease=True,
        )
        result = self.invoke(repository)
        self.assertEqual(1, result["requeued"])

    def test_one_invocation_never_retries_same_candidate_in_a_loop(self) -> None:
        repository = FakeRepository()
        repository.due["FAILED_RETRYABLE"] = ["request-1"]
        repository.send_error = True
        self.invoke(repository)
        self.assertEqual(1, len(repository.send_calls))
        self.assertEqual(1, len(repository.failure_calls))

    def test_manual_review_backlog_metric_is_emitted(self) -> None:
        repository = FakeRepository()
        repository.backlog = True
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.invoke(repository)
        self.assertIn('"ManualReviewBacklog":1', output.getvalue())

    def test_reconciler_logs_exclude_event_payload(self) -> None:
        repository = FakeRepository()
        marker = "SYNTHETIC-APPOINTMENT-BODY-NOT-FOR-LOGS"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.invoke(repository, {"appointmentBody": marker})
        self.assertNotIn(marker, output.getvalue())
        self.assertNotIn("appointmentBody", output.getvalue())


if __name__ == "__main__":
    unittest.main()

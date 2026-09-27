from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from common.clinical_adapter import AdapterOutcome  # noqa: E402
from common.workflow_state import OwnershipDecision, RequestState  # noqa: E402
from worker.handler import handle_records  # noqa: E402


class FakeRepository:
    def __init__(self, decision: OwnershipDecision | None = None) -> None:
        self.decision = decision or OwnershipDecision(
            True, RequestState("request-1", "PROCESSING", processing_attempts=1)
        )
        self.acquire_calls: list[dict] = []
        self.manual_calls: list[dict] = []
        self.retryable_calls: list[dict] = []

    def acquire_processing(self, **kwargs):
        self.acquire_calls.append(kwargs)
        return self.decision

    def mark_manual_review(self, **kwargs):
        self.manual_calls.append(kwargs)

    def mark_failed_retryable(self, **kwargs):
        self.retryable_calls.append(kwargs)


class FakeAdapter:
    def __init__(self, outcome: AdapterOutcome) -> None:
        self.outcome = outcome
        self.calls: list[str] = []

    def process(self, request_id: str) -> AdapterOutcome:
        self.calls.append(request_id)
        return self.outcome


class RaisingAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def process(self, request_id: str):
        self.calls.append(request_id)
        raise RuntimeError("synthetic adapter failure")


def event(*, extra: dict | None = None):
    body = {"requestId": "request-1", "correlationId": "correlation-1"}
    body.update(extra or {})
    return {
        "Records": [
            {
                "messageId": "message-1",
                "body": json.dumps(body),
                "attributes": {"ApproximateReceiveCount": "1"},
            }
        ]
    }


class WorkerHandlerTests(unittest.TestCase):
    def invoke(self, repository, adapter, worker_event=None):
        return handle_records(
            worker_event or event(),
            None,
            repository=repository,
            adapter=adapter,
            now=lambda: 1000,
            owner_factory=lambda: "owner-1",
        )

    def test_first_delivery_acquires_ownership_before_adapter(self) -> None:
        repository = FakeRepository()
        adapter = FakeAdapter(AdapterOutcome.UNKNOWN_RESULT)
        result = self.invoke(repository, adapter)
        self.assertEqual([], result["batchItemFailures"])
        self.assertEqual(["request-1"], adapter.calls)
        self.assertEqual("owner-1", repository.acquire_calls[0]["owner_token"])

    def test_active_duplicate_is_safe_noop(self) -> None:
        repository = FakeRepository(
            OwnershipDecision(False, RequestState("request-1", "PROCESSING"))
        )
        adapter = FakeAdapter(AdapterOutcome.UNKNOWN_RESULT)
        result = self.invoke(repository, adapter)
        self.assertEqual([], result["batchItemFailures"])
        self.assertEqual([], adapter.calls)
        self.assertEqual([], repository.manual_calls)

    def test_concurrent_ownership_loser_does_not_process(self) -> None:
        repository = FakeRepository(
            OwnershipDecision(False, RequestState("request-1", "QUEUED"))
        )
        adapter = FakeAdapter(AdapterOutcome.UNKNOWN_RESULT)
        self.invoke(repository, adapter)
        self.assertEqual([], adapter.calls)

    def test_terminal_duplicate_is_safe_noop(self) -> None:
        for status in ("MANUAL_REVIEW_REQUIRED", "SUCCEEDED"):
            with self.subTest(status=status):
                repository = FakeRepository(
                    OwnershipDecision(False, RequestState("request-1", status))
                )
                adapter = FakeAdapter(AdapterOutcome.UNKNOWN_RESULT)
                result = self.invoke(repository, adapter)
                self.assertEqual([], result["batchItemFailures"])
                self.assertEqual([], adapter.calls)

    def test_expired_lease_recovery_continues_under_new_owner(self) -> None:
        repository = FakeRepository(
            OwnershipDecision(
                True,
                RequestState("request-1", "PROCESSING", processing_attempts=2),
                recovered_expired_lease=True,
            )
        )
        adapter = FakeAdapter(AdapterOutcome.UNKNOWN_RESULT)
        self.invoke(repository, adapter)
        self.assertEqual(1, len(repository.manual_calls))

    def test_retryable_outcome_is_persisted_before_batch_failure(self) -> None:
        repository = FakeRepository()
        adapter = FakeAdapter(AdapterOutcome.RETRYABLE_FAILURE)
        result = self.invoke(repository, adapter)
        self.assertEqual([{"itemIdentifier": "message-1"}], result["batchItemFailures"])
        self.assertEqual(1, len(repository.retryable_calls))
        self.assertEqual([], repository.manual_calls)

    def test_unavailable_adapter_escalates_to_manual_review(self) -> None:
        repository = FakeRepository()
        self.invoke(repository, FakeAdapter(AdapterOutcome.UNKNOWN_RESULT))
        self.assertEqual(
            "CLINICAL_ADAPTER_UNAVAILABLE", repository.manual_calls[0]["reason"]
        )

    def test_unexpected_success_never_creates_clinical_success(self) -> None:
        repository = FakeRepository()
        result = self.invoke(repository, FakeAdapter(AdapterOutcome.SUCCESS))
        self.assertEqual([], result["batchItemFailures"])
        self.assertEqual(
            "CLINICAL_SUCCESS_NOT_AUTHORIZED",
            repository.manual_calls[0]["reason"],
        )

    def test_nonretryable_failure_escalates_without_success(self) -> None:
        repository = FakeRepository()
        result = self.invoke(
            repository, FakeAdapter(AdapterOutcome.NONRETRYABLE_FAILURE)
        )
        self.assertEqual([], result["batchItemFailures"])
        self.assertEqual(
            "CLINICAL_ADAPTER_NONRETRYABLE_FAILURE",
            repository.manual_calls[0]["reason"],
        )
        self.assertEqual([], repository.retryable_calls)

    def test_adapter_exception_returns_partial_batch_failure(self) -> None:
        repository = FakeRepository()
        adapter = RaisingAdapter()
        result = self.invoke(repository, adapter)
        self.assertEqual(["request-1"], adapter.calls)
        self.assertEqual(
            [{"itemIdentifier": "message-1"}], result["batchItemFailures"]
        )
        self.assertEqual([], repository.manual_calls)
        self.assertEqual([], repository.retryable_calls)

    def test_queue_envelope_rejects_clinical_payload(self) -> None:
        repository = FakeRepository()
        marker = "SYNTHETIC-CLINICAL-DATA"
        result = self.invoke(
            repository,
            FakeAdapter(AdapterOutcome.UNKNOWN_RESULT),
            event(extra={"appointmentBody": marker}),
        )
        self.assertEqual([{"itemIdentifier": "message-1"}], result["batchItemFailures"])
        self.assertEqual([], repository.acquire_calls)

    def test_malformed_missing_and_oversized_envelopes_are_rejected(self) -> None:
        bodies = (
            "",
            "{",
            json.dumps({"correlationId": "correlation-1"}),
            json.dumps({"requestId": "request-1"}),
            json.dumps(
                {
                    "requestId": "R" * 129,
                    "correlationId": "correlation-1",
                }
            ),
            json.dumps(
                {
                    "requestId": "request-1",
                    "correlationId": "correlation-1",
                    "unexpected": "value",
                }
            ),
            json.dumps(["request-1", "correlation-1"]),
        )
        for body in bodies:
            with self.subTest(body=body):
                repository = FakeRepository()
                worker_event = {
                    "Records": [
                        {
                            "messageId": "message-1",
                            "body": body,
                            "attributes": {"ApproximateReceiveCount": "5"},
                        }
                    ]
                }
                result = self.invoke(
                    repository,
                    FakeAdapter(AdapterOutcome.UNKNOWN_RESULT),
                    worker_event,
                )
                self.assertEqual(
                    [{"itemIdentifier": "message-1"}],
                    result["batchItemFailures"],
                )
                self.assertEqual([], repository.acquire_calls)

    def test_bounded_unexpected_envelope_keys_are_rejected(self) -> None:
        for index in range(16):
            with self.subTest(index=index):
                repository = FakeRepository()
                result = self.invoke(
                    repository,
                    FakeAdapter(AdapterOutcome.UNKNOWN_RESULT),
                    event(extra={f"unexpected_{index}": "synthetic"}),
                )
                self.assertEqual(
                    [{"itemIdentifier": "message-1"}],
                    result["batchItemFailures"],
                )
                self.assertEqual([], repository.acquire_calls)

    def test_unknown_request_is_data_minimized_noop(self) -> None:
        repository = FakeRepository(OwnershipDecision(False, None))
        adapter = FakeAdapter(AdapterOutcome.UNKNOWN_RESULT)
        result = self.invoke(repository, adapter)
        self.assertEqual([], result["batchItemFailures"])
        self.assertEqual([], adapter.calls)
        self.assertEqual([], repository.manual_calls)

    def test_delayed_and_out_of_order_duplicates_never_call_adapter(self) -> None:
        for status in (
            "QUEUE_PENDING",
            "QUEUED",
            "PROCESSING",
            "FAILED_RETRYABLE",
            "RECONCILE_REQUIRED",
            "MANUAL_REVIEW_REQUIRED",
            "SUCCEEDED",
        ):
            with self.subTest(status=status):
                repository = FakeRepository(
                    OwnershipDecision(False, RequestState("request-1", status))
                )
                adapter = FakeAdapter(AdapterOutcome.UNKNOWN_RESULT)
                self.invoke(repository, adapter)
                self.assertEqual([], adapter.calls)

    def test_repeated_retryable_delivery_is_one_attempt_per_invocation(self) -> None:
        repository = FakeRepository()
        adapter = FakeAdapter(AdapterOutcome.RETRYABLE_FAILURE)
        first = self.invoke(repository, adapter)
        second = self.invoke(repository, adapter)
        self.assertEqual(2, len(repository.acquire_calls))
        self.assertEqual(2, len(repository.retryable_calls))
        self.assertEqual(2, len(adapter.calls))
        self.assertEqual(1, len(first["batchItemFailures"]))
        self.assertEqual(1, len(second["batchItemFailures"]))

    def test_every_adapter_outcome_is_fail_safe(self) -> None:
        for outcome in AdapterOutcome:
            with self.subTest(outcome=outcome.value):
                repository = FakeRepository()
                result = self.invoke(repository, FakeAdapter(outcome))
                if outcome == AdapterOutcome.RETRYABLE_FAILURE:
                    self.assertEqual(1, len(repository.retryable_calls))
                    self.assertEqual(1, len(result["batchItemFailures"]))
                    self.assertEqual([], repository.manual_calls)
                else:
                    self.assertEqual(1, len(repository.manual_calls))
                    self.assertEqual([], repository.retryable_calls)
                    self.assertEqual([], result["batchItemFailures"])

    def test_worker_logs_exclude_rejected_payload_values(self) -> None:
        repository = FakeRepository()
        marker = "SYNTHETIC-CONTACT-NOT-FOR-LOGS"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.invoke(
                repository,
                FakeAdapter(AdapterOutcome.UNKNOWN_RESULT),
                event(extra={"contact": marker}),
            )
        self.assertNotIn(marker, output.getvalue())
        self.assertNotIn("contact", output.getvalue())


if __name__ == "__main__":
    unittest.main()

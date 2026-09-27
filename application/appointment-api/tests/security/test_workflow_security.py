from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = PROJECT_ROOT / "src"
MODULE_ROOT = REPOSITORY_ROOT / "modules" / "appointment-api"


class WorkflowSecurityStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = (SOURCE_ROOT / "common" / "clinical_adapter.py").read_text(
            encoding="utf-8"
        )
        cls.worker = (SOURCE_ROOT / "worker" / "handler.py").read_text(
            encoding="utf-8"
        )
        cls.repository = (
            SOURCE_ROOT / "common" / "workflow_state.py"
        ).read_text(encoding="utf-8")
        cls.observability = (
            SOURCE_ROOT / "common" / "observability.py"
        ).read_text(encoding="utf-8")
        cls.dynamodb = (MODULE_ROOT / "dynamodb.tf").read_text(encoding="utf-8")
        cls.iam = (MODULE_ROOT / "iam.tf").read_text(encoding="utf-8")
        cls.monitoring = (MODULE_ROOT / "monitoring.tf").read_text(
            encoding="utf-8"
        )
        cls.readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    def test_reconciliation_index_is_keys_only_and_contains_no_payload_field(self) -> None:
        self.assertIn('name            = "reconciliation-index"', self.dynamodb)
        self.assertIn('hash_key        = "reconcile_status"', self.dynamodb)
        self.assertIn('range_key       = "next_attempt_at"', self.dynamodb)
        self.assertIn('projection_type = "KEYS_ONLY"', self.dynamodb)
        index = self.dynamodb.split("global_secondary_index {", 1)[1].split("}", 1)[0]
        for forbidden in ("request_payload", "contact", "clinical", "signature", "secret"):
            self.assertNotIn(forbidden, index.lower())

    def test_reconciliation_uses_query_not_scan(self) -> None:
        self.assertIn("self._dynamodb.query(", self.repository)
        self.assertNotIn("self._dynamodb.scan(", self.repository)
        self.assertIn('IndexName=self._index_name', self.repository)
        self.assertIn('Limit=limit', self.repository)

    def test_new_worker_and_reconciler_iam_is_narrow(self) -> None:
        worker = self.iam.split('data "aws_iam_policy_document" "worker"', 1)[1].split(
            'resource "aws_iam_role_policy" "worker"', 1
        )[0]
        reconciler = self.iam.split(
            'data "aws_iam_policy_document" "reconciler"', 1
        )[1].split('resource "aws_iam_role_policy" "reconciler"', 1)[0]
        self.assertIn('"dynamodb:GetItem"', worker)
        self.assertIn('"dynamodb:UpdateItem"', worker)
        self.assertIn('"dynamodb:Query"', reconciler)
        self.assertIn('"sqs:SendMessage"', reconciler)
        for policy in (worker, reconciler):
            self.assertNotIn('"dynamodb:*"', policy)
            self.assertNotIn('"sqs:*"', policy)
            self.assertNotIn('"iam:PassRole"', policy)
            self.assertNotIn("AdministratorAccess", policy)

    def test_adapter_is_interface_only_and_has_no_external_client(self) -> None:
        self.assertIn("return AdapterOutcome.UNKNOWN_RESULT", self.adapter)
        for forbidden in (
            "boto3",
            "requests",
            "urllib",
            "socket",
            ".client(",
            "create_appointment",
        ):
            self.assertNotIn(forbidden, self.adapter)

    def test_unexpected_adapter_success_is_forced_to_manual_review(self) -> None:
        self.assertIn(
            'AdapterOutcome.SUCCESS: "CLINICAL_SUCCESS_NOT_AUTHORIZED"', self.worker
        )
        self.assertIn("repository.mark_manual_review(", self.worker)
        self.assertNotIn(":succeeded", self.repository.lower())

    def test_each_new_alarm_metric_has_an_approved_emission_path(self) -> None:
        for metric in (
            "StaleQueueState",
            "ReconciliationFailure",
            "ManualReviewBacklog",
            "ProcessingLeaseExpired",
        ):
            with self.subTest(metric=metric):
                self.assertIn(metric, self.monitoring)
                self.assertIn(metric, self.observability)

    def test_dlq_procedure_forbids_automatic_delete_and_redrive(self) -> None:
        self.assertIn("DLQ messages are not automatically deleted or redriven", self.readme)
        self.assertIn("manual redrive requires separate operational approval", self.readme)


if __name__ == "__main__":
    unittest.main()

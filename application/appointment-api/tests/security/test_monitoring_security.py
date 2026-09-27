from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = REPOSITORY_ROOT / "modules" / "appointment-api"
ENVIRONMENT_ROOT = REPOSITORY_ROOT / "environments" / "nonprod"


class MonitoringSecurityStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.alerts = (MODULE_ROOT / "alerts.tf").read_text(encoding="utf-8")
        cls.dashboard = (MODULE_ROOT / "dashboard.tf").read_text(encoding="utf-8")
        cls.iam = (MODULE_ROOT / "iam.tf").read_text(encoding="utf-8")
        cls.logging = (MODULE_ROOT / "logging.tf").read_text(encoding="utf-8")
        cls.monitoring = (MODULE_ROOT / "monitoring.tf").read_text(encoding="utf-8")
        cls.observability = (
            PROJECT_ROOT / "src" / "common" / "observability.py"
        ).read_text(encoding="utf-8")
        cls.environment = (ENVIRONMENT_ROOT / "appointment-api.tf").read_text(
            encoding="utf-8"
        )
        cls.runbook = (PROJECT_ROOT / "OPERATIONS.md").read_text(encoding="utf-8")

    def test_all_fourteen_alarms_use_dedicated_alarm_and_recovery_route(self) -> None:
        self.assertEqual(7, self.monitoring.count('resource "aws_cloudwatch_metric_alarm"'))
        self.assertIn("for_each = local.workflow_operational_alarms", self.monitoring)
        self.assertEqual(2, self.monitoring.count("for_each = local.monitored_lambda_functions"))
        self.assertEqual(7, self.monitoring.count("alarm_actions = local.alert_topic_actions"))
        self.assertEqual(7, self.monitoring.count("ok_actions    = local.alert_topic_actions"))
        self.assertIn("alert_topic_actions = [aws_sns_topic.alerts.arn]", self.monitoring)

    def test_alert_topic_is_dedicated_and_encrypted(self) -> None:
        self.assertIn('name              = "clinic-nonprod-appointment-api-alerts"', self.alerts)
        self.assertIn('kms_master_key_id = "alias/aws/sns"', self.alerts)

    def test_topic_policy_is_not_public_and_limits_cloudwatch_source(self) -> None:
        self.assertNotIn('effect      = "Allow"\n    actions    = ["sns:*"', self.alerts)
        self.assertNotIn('identifiers = ["*"]', self.alerts)
        self.assertIn('identifiers = ["cloudwatch.amazonaws.com"]', self.alerts)
        self.assertIn('variable = "AWS:SourceAccount"', self.alerts)
        self.assertIn('variable = "AWS:SourceArn"', self.alerts)

    def test_no_lambda_role_can_publish_to_sns(self) -> None:
        self.assertNotRegex(self.iam, r'(?i)sns:(publish|\*)')

    def test_no_subscription_destination_is_fabricated(self) -> None:
        terraform = "\n".join(
            path.read_text(encoding="utf-8") for path in MODULE_ROOT.glob("*.tf")
        )
        self.assertNotIn('resource "aws_sns_topic_subscription"', terraform)

    def test_dashboard_contains_only_safe_operational_metrics(self) -> None:
        for required in (
            "5XXError",
            "Errors",
            "Throttles",
            "ApproximateAgeOfOldestMessage",
            "ApproximateNumberOfMessagesVisible",
            "SystemErrors",
            "StaleQueueState",
            "ReconciliationFailure",
            "ManualReviewBacklog",
            "ProcessingLeaseExpired",
        ):
            self.assertIn(required, self.dashboard)
        for forbidden in (
            "request_payload",
            "patient",
            "contact",
            "clinical",
            "hmac",
            "signature",
            "secret",
            "token",
        ):
            self.assertNotIn(forbidden, self.dashboard.lower())

    def test_all_wave_three_log_groups_have_explicit_retention(self) -> None:
        self.assertEqual(5, self.logging.count('resource "aws_cloudwatch_log_group"'))
        self.assertEqual(5, self.logging.count("retention_in_days = var.log_retention_days"))
        self.assertIn("log_retention_days              = 90", self.environment)

    def test_custom_alarm_metrics_match_runtime_emissions(self) -> None:
        for metric in (
            "StaleQueueState",
            "ReconciliationFailure",
            "ManualReviewBacklog",
            "ProcessingLeaseExpired",
        ):
            with self.subTest(metric=metric):
                self.assertIn(metric, self.monitoring)
                self.assertIn(metric, self.observability)
        self.assertIn('"Dimensions": [[]]', self.observability)

    def test_service_metric_dimensions_are_bound_to_correct_resources(self) -> None:
        self.assertIn("FunctionName = each.value", self.monitoring)
        self.assertIn("ApiName = aws_api_gateway_rest_api.this.name", self.monitoring)
        self.assertIn("Stage   = aws_api_gateway_stage.this.stage_name", self.monitoring)
        self.assertIn("QueueName = aws_sqs_queue.work.name", self.monitoring)
        self.assertIn("QueueName = aws_sqs_queue.dead_letter.name", self.monitoring)
        for operation in ("GetItem", "UpdateItem", "TransactWriteItems", "Query"):
            self.assertIn(f'Operation = "{operation}"', self.monitoring)
        self.assertGreaterEqual(
            self.monitoring.count("TableName = aws_dynamodb_table.workflow.name"), 4
        )

    def test_each_alarm_has_complete_semantics(self) -> None:
        blocks = self.monitoring.split('resource "aws_cloudwatch_metric_alarm"')[1:]
        for block in blocks:
            with self.subTest(alarm=block.split("{", 1)[0].strip()):
                for field in (
                    "comparison_operator",
                    "evaluation_periods",
                    "threshold",
                    "treat_missing_data",
                    "alarm_actions",
                    "ok_actions",
                ):
                    self.assertIn(field, block)

    def test_runbook_lists_every_alarm_and_manual_dlq_control(self) -> None:
        suffixes = (
            "intake-errors",
            "worker-errors",
            "reconciler-errors",
            "intake-throttles",
            "worker-throttles",
            "reconciler-throttles",
            "api-5xx",
            "work-queue-age",
            "dlq-messages",
            "dynamodb-system-errors",
            "stale-queue-state",
            "reconciliation-failure",
            "manual-review-backlog",
            "processing-lease-expired",
        )
        for suffix in suffixes:
            self.assertIn(f"`{suffix}`", self.runbook)
        self.assertIn("Never automatically delete or redrive DLQ messages", self.runbook)
        self.assertIn("authoritative DynamoDB", self.runbook)

    def test_runbook_keeps_human_destination_as_an_explicit_gate(self) -> None:
        self.assertIn("No subscription is configured", self.runbook)
        self.assertIn("before operational acceptance", self.runbook)
        self.assertIsNone(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", self.runbook))


if __name__ == "__main__":
    unittest.main()

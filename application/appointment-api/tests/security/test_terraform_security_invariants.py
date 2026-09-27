from __future__ import annotations

import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = REPOSITORY_ROOT / "modules" / "appointment-api"


class TerraformSecurityInvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.files = {
            path.name: path.read_text(encoding="utf-8")
            for path in MODULE_ROOT.glob("*.tf")
        }
        cls.all_tf = "\n".join(cls.files.values())
        cls.api = cls.files["api-gateway.tf"]
        cls.alerts = cls.files["alerts.tf"]
        cls.iam = cls.files["iam.tf"]
        cls.lambda_tf = cls.files["lambda.tf"]
        cls.logging = cls.files["logging.tf"]
        cls.monitoring = cls.files["monitoring.tf"]
        cls.secrets = cls.files["secrets.tf"]
        cls.sqs = cls.files["sqs.tf"]
        cls.waf = cls.files["waf.tf"]

    def test_api_has_one_regional_stage_and_one_processing_route(self) -> None:
        self.assertIn('types = ["REGIONAL"]', self.api)
        self.assertEqual(1, self.api.count('resource "aws_api_gateway_stage"'))
        self.assertEqual(1, self.api.count('resource "aws_api_gateway_method"'))
        self.assertIn('http_method   = "POST"', self.api)
        self.assertIn('path_part   = "appointments"', self.api)
        self.assertNotRegex(
            self.api,
            r'http_method\s*=\s*"(GET|PUT|PATCH|DELETE|OPTIONS|ANY)"',
        )
        self.assertNotIn("Access-Control-Allow-Origin", self.api)

    def test_required_hmac_headers_and_closed_request_validation_remain(self) -> None:
        for header in (
            "Content-Type",
            "Idempotency-Key",
            "X-Clinic-Key-Id",
            "X-Clinic-Nonce",
            "X-Clinic-Signature",
            "X-Clinic-Timestamp",
            "X-Content-SHA256",
        ):
            self.assertIn(f'"method.request.header.{header}"', self.api)
        self.assertIn("validate_request_body       = true", self.api)
        self.assertIn("validate_request_parameters = true", self.api)

    def test_waf_managed_rules_block_and_oversize_controls_remain_hardened(self) -> None:
        for rule in (
            "AWSManagedRulesCommonRuleSet",
            "AWSManagedRulesKnownBadInputsRuleSet",
            "AWSManagedRulesAmazonIpReputationList",
        ):
            self.assertIn(rule, self.waf)
        self.assertNotIn("count {}", self.waf)
        self.assertIn('comparison_operator = "GT"', self.waf)
        self.assertIn("size                = var.maximum_request_body_bytes", self.waf)
        self.assertIn('oversize_handling = "MATCH"', self.waf)
        self.assertIn('resource "aws_wafv2_web_acl_association" "api"', self.waf)

    def test_waf_and_api_logs_exclude_sensitive_request_material(self) -> None:
        for header in (
            "authorization",
            "cookie",
            "x-clinic-signature",
            "x-clinic-key-id",
            "x-clinic-timestamp",
            "x-clinic-nonce",
            "idempotency-key",
            "x-content-sha256",
        ):
            self.assertIn(f'name = "{header}"', self.waf)
        self.assertIn("query_string {}", self.waf)
        access = self.api.split("access_log_settings {", 1)[1].split(
            "  tags = local.common_tags", 1
        )[0]
        for forbidden in (
            "$context.requestBody",
            "$context.responseBody",
            "$context.queryString",
            "$context.identity",
            "X-Clinic-Signature",
            "Idempotency-Key",
        ):
            self.assertNotIn(forbidden, access)

    def test_lambda_has_no_vpc_or_clinical_infrastructure_dependency(self) -> None:
        self.assertNotIn("vpc_config", self.lambda_tf)
        self.assertNotIn("security_group_ids", self.lambda_tf)
        for forbidden in (
            'resource "aws_nat_gateway"',
            'resource "aws_vpc_endpoint"',
            'resource "aws_db_instance"',
            'resource "aws_rds_',
            'resource "aws_fsx_',
            'resource "aws_directory_service_',
            "module.network",
            "module.directory",
            "module.fsx",
        ):
            self.assertNotIn(forbidden, self.all_tf)

    def test_hmac_secret_is_metadata_only(self) -> None:
        self.assertIn('resource "aws_secretsmanager_secret" "hmac"', self.secrets)
        self.assertNotIn("aws_secretsmanager_secret_version", self.all_tf)
        self.assertNotRegex(self.secrets, r'(?m)^\s*(secret_string|secret_binary)\s*=')
        self.assertIn("value managed outside Terraform", self.secrets)

    def test_monitoring_routing_remains_fourteen_of_fourteen(self) -> None:
        self.assertEqual(7, self.monitoring.count('resource "aws_cloudwatch_metric_alarm"'))
        self.assertEqual(2, self.monitoring.count("for_each = local.monitored_lambda_functions"))
        self.assertIn("for_each = local.workflow_operational_alarms", self.monitoring)
        self.assertEqual(7, self.monitoring.count("alarm_actions = local.alert_topic_actions"))
        self.assertEqual(7, self.monitoring.count("ok_actions    = local.alert_topic_actions"))
        self.assertNotIn('resource "aws_sns_topic_subscription"', self.all_tf)

    def test_topic_policy_and_lambda_iam_remain_scoped(self) -> None:
        self.assertIn('identifiers = ["cloudwatch.amazonaws.com"]', self.alerts)
        self.assertIn('variable = "AWS:SourceAccount"', self.alerts)
        self.assertIn('variable = "AWS:SourceArn"', self.alerts)
        self.assertNotIn('identifiers = ["*"]', self.alerts)
        self.assertNotRegex(self.iam, r'(?i)sns:(publish|\*)')

    def test_no_broad_application_iam_grants_are_introduced(self) -> None:
        for forbidden in (
            "AdministratorAccess",
            "PowerUserAccess",
            '"iam:PassRole"',
            '"iam:*"',
            '"dynamodb:*"',
            '"secretsmanager:*"',
        ):
            self.assertNotIn(forbidden, self.iam)
        self.assertNotIn('"sqs:*"', self.iam)
        self.assertEqual(3, self.iam.count('resources = ["*"]'))
        self.assertEqual(3, self.iam.count('"xray:PutTraceSegments"'))
        self.assertEqual(3, self.iam.count('"xray:PutTelemetryRecords"'))

    def test_sqs_wildcard_actions_are_deny_only(self) -> None:
        self.assertEqual(2, self.sqs.count('actions   = ["sqs:*"]'))
        self.assertEqual(2, self.sqs.count('effect = "Deny"'))
        self.assertNotIn('effect = "Allow"\n\n    actions   = ["sqs:*"]', self.sqs)

    def test_all_wave_three_logs_retain_ninety_day_configuration(self) -> None:
        self.assertEqual(5, self.logging.count('resource "aws_cloudwatch_log_group"'))
        self.assertEqual(5, self.logging.count("retention_in_days = var.log_retention_days"))
        environment = (
            REPOSITORY_ROOT / "environments" / "nonprod" / "appointment-api.tf"
        ).read_text(encoding="utf-8")
        self.assertIn("log_retention_days              = 90", environment)


if __name__ == "__main__":
    unittest.main()

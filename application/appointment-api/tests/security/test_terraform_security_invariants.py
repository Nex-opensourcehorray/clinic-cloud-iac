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
        cls.variables = cls.files["variables.tf"]
        cls.waf = cls.files["waf.tf"]
        cls.environment_variables = (
            REPOSITORY_ROOT / "environments" / "nonprod" / "variables.tf"
        ).read_text(encoding="utf-8")
        cls.environment_module = (
            REPOSITORY_ROOT / "environments" / "nonprod" / "appointment-api.tf"
        ).read_text(encoding="utf-8")
        cls.readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        cls.deployment_readiness = (
            PROJECT_ROOT / "DEPLOYMENT-READINESS.md"
        ).read_text(encoding="utf-8")

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

    def test_hmac_secret_is_an_external_operational_dependency(self) -> None:
        self.assertNotRegex(
            self.all_tf,
            r'(?m)^\s*(resource|data)\s+"aws_secretsmanager_secret',
        )
        self.assertNotIn("aws_secretsmanager_secret_version", self.all_tf)
        self.assertNotRegex(self.all_tf, r'(?m)^\s*(secret_string|secret_binary)\s*=')
        self.assertIn("EXTERNALLY MANAGED OPERATIONAL DEPENDENCY", self.secrets)
        self.assertIn("does not create, import, delete, or read", self.secrets)

    def test_external_hmac_secret_arn_is_a_required_validated_input(self) -> None:
        self.assertIn('variable "hmac_secret_arn"', self.variables)
        hmac_variable = self.variables.split('variable "hmac_secret_arn"', 1)[1].split(
            '\n}\n', 1
        )[0]
        self.assertIn("type        = string", hmac_variable)
        self.assertIn("secretsmanager", hmac_variable)
        self.assertNotIn("default", hmac_variable)
        self.assertIn(
            'variable "appointment_api_hmac_secret_arn"',
            self.environment_variables,
        )
        self.assertRegex(
            self.environment_module,
            r"hmac_secret_arn\s*=\s*var\.appointment_api_hmac_secret_arn",
        )

    def test_external_hmac_consumers_use_only_the_supplied_arn(self) -> None:
        self.assertIn("HMAC_SECRET_ARN              = var.hmac_secret_arn", self.lambda_tf)
        self.assertIn("`secretsmanager:GetSecretValue` permission", self.readme)
        self.assertNotIn('"secretsmanager:*"', self.all_tf)
        self.assertNotIn('"kms:Decrypt"', self.all_tf)
        self.assertNotIn("aws_secretsmanager_secret.hmac", self.all_tf)

    def test_monitoring_routing_remains_fourteen_of_fourteen(self) -> None:
        self.assertEqual(7, self.monitoring.count('resource "aws_cloudwatch_metric_alarm"'))
        self.assertEqual(2, self.monitoring.count("for_each = local.monitored_lambda_functions"))
        self.assertIn("for_each = local.workflow_operational_alarms", self.monitoring)
        self.assertEqual(7, self.monitoring.count("alarm_actions = local.alert_topic_actions"))
        self.assertEqual(7, self.monitoring.count("ok_actions    = local.alert_topic_actions"))
        self.assertNotIn('resource "aws_sns_topic_subscription"', self.all_tf)

    def test_topic_policy_remains_scoped(self) -> None:
        self.assertIn('identifiers = ["cloudwatch.amazonaws.com"]', self.alerts)
        self.assertIn('variable = "AWS:SourceAccount"', self.alerts)
        self.assertIn('variable = "AWS:SourceArn"', self.alerts)
        self.assertNotIn('identifiers = ["*"]', self.alerts)

    def test_no_broad_application_iam_grants_are_introduced_in_terraform(self) -> None:
        for forbidden in (
            "AdministratorAccess",
            "PowerUserAccess",
            '"iam:PassRole"',
            '"iam:*"',
            '"dynamodb:*"',
            '"secretsmanager:*"',
        ):
            self.assertNotIn(forbidden, self.all_tf)

    def test_terraform_does_not_own_external_iam_roles_or_policies(self) -> None:
        self.assertNotRegex(self.all_tf, r'resource\s+"aws_iam_role"')
        self.assertNotRegex(self.all_tf, r'resource\s+"aws_iam_role_policy"')
        self.assertNotRegex(self.all_tf, r'data\s+"aws_iam_role"')
        self.assertNotRegex(self.all_tf, r'data\s+"aws_iam_policy"')
        self.assertNotIn("assume_role_policy", self.all_tf)
        self.assertNotIn("permissions_boundary", self.all_tf)
        self.assertNotIn('actions = ["sts:AssumeRole"]', self.all_tf)

    def test_external_role_arn_inputs_are_required_and_validated(self) -> None:
        names = (
            "intake_role_arn",
            "worker_role_arn",
            "reconciler_role_arn",
            "api_gateway_logs_role_arn",
        )
        for name in names:
            with self.subTest(name=name):
                marker = f'variable "{name}"'
                self.assertIn(marker, self.variables)
                block = self.variables.split(marker, 1)[1].split("\n}\n", 1)[0]
                self.assertIn("type        = string", block)
                self.assertIn(":iam::", block)
                self.assertIn(":role/", block)
                self.assertNotIn("default", block)

    def test_environment_exposes_and_passes_all_external_role_arns(self) -> None:
        pairs = {
            "appointment_api_intake_role_arn": "intake_role_arn",
            "appointment_api_worker_role_arn": "worker_role_arn",
            "appointment_api_reconciler_role_arn": "reconciler_role_arn",
            "appointment_api_api_gateway_logs_role_arn": "api_gateway_logs_role_arn",
        }
        for root_name, module_name in pairs.items():
            with self.subTest(root_name=root_name):
                self.assertIn(f'variable "{root_name}"', self.environment_variables)
                self.assertRegex(
                    self.environment_module,
                    rf"{module_name}\s*=\s*var\.{root_name}",
                )

    def test_compute_and_api_logging_consume_only_external_role_inputs(self) -> None:
        for name in ("intake", "worker", "reconciler"):
            self.assertIn(f"role          = var.{name}_role_arn", self.lambda_tf)
        self.assertEqual(3, self.lambda_tf.count("role          = var."))
        self.assertNotIn("aws_iam_role", self.lambda_tf)
        self.assertIn(
            "cloudwatch_role_arn = var.api_gateway_logs_role_arn",
            self.iam,
        )

    def test_documentation_defines_exact_external_iam_contract(self) -> None:
        expected_roles = (
            "clinic-nonprod-appointment-api-intake",
            "clinic-nonprod-appointment-api-worker",
            "clinic-nonprod-appointment-api-reconciler",
            "clinic-nonprod-appointment-api-api-logs",
        )
        for document in (self.readme, self.deployment_readiness):
            with self.subTest(document=document[:40]):
                self.assertIn("Externally managed IAM", document)
                self.assertIn("lambda.amazonaws.com", document)
                self.assertIn("apigateway.amazonaws.com", document)
                self.assertIn("clinic-nonprod-appointment-api-runtime-boundary", document)
                self.assertIn("clinic-nonprod-appointment-api-api-logs-boundary", document)
                for role in expected_roles:
                    self.assertIn(f"arn:aws:iam::<AWS_ACCOUNT_ID>:role/{role}", document)
        self.assertNotRegex(
            "\n".join(
                line
                for line in self.readme.splitlines()
                if "arn:aws:iam::<AWS_ACCOUNT_ID>:role/" in line
            ),
            r"role/[^`|\s]*\*",
        )

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

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = REPOSITORY_ROOT / "modules" / "appointment-api"


class PublicBoundaryStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.api = (MODULE_ROOT / "api-gateway.tf").read_text(encoding="utf-8")
        cls.waf = (MODULE_ROOT / "waf.tf").read_text(encoding="utf-8")
        cls.schema = json.loads(
            (PROJECT_ROOT / "schema" / "appointment-request.schema.json").read_text(
                encoding="utf-8"
            )
        )
        cls.readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    def test_only_post_appointments_integrates_with_intake_lambda(self) -> None:
        self.assertEqual(1, self.api.count('resource "aws_api_gateway_method"'))
        self.assertIn('path_part   = "appointments"', self.api)
        self.assertIn('http_method   = "POST"', self.api)
        self.assertNotRegex(self.api, r'http_method\s*=\s*"(GET|PUT|PATCH|DELETE|OPTIONS|ANY)"')
        self.assertIn('type                    = "AWS_PROXY"', self.api)
        self.assertIn("aws_lambda_function.intake.invoke_arn", self.api)
        self.assertNotIn('type                    = "AWS"\n', self.api)

    def test_waf_is_associated_with_the_only_stage(self) -> None:
        self.assertIn("resource \"aws_wafv2_web_acl_association\" \"api\"", self.waf)
        self.assertIn("resource_arn = aws_api_gateway_stage.this.arn", self.waf)
        self.assertIn('types = ["REGIONAL"]', self.api)

    def test_required_headers_are_enforced_and_redacted(self) -> None:
        header_names = (
            "Idempotency-Key",
            "X-Clinic-Key-Id",
            "X-Clinic-Nonce",
            "X-Clinic-Signature",
            "X-Clinic-Timestamp",
            "X-Content-SHA256",
        )
        for header in header_names:
            with self.subTest(header=header):
                self.assertIn(f"method.request.header.{header}", self.api)
                self.assertIn(f'name = "{header.lower()}"', self.waf)

    def test_waf_rule_priorities_and_actions_are_hardened(self) -> None:
        expected = {
            "BlockOversizeAppointmentRequests": "1",
            "AWSManagedRulesCommonRuleSet": "10",
            "AWSManagedRulesKnownBadInputsRuleSet": "20",
            "AWSManagedRulesAmazonIpReputationList": "30",
            "RateLimitBySourceIp": "40",
        }
        for name, priority in expected.items():
            pattern = rf'name\s*=\s*"{re.escape(name)}"\s+priority\s*=\s*{priority}'
            with self.subTest(rule=name):
                self.assertRegex(self.waf, pattern)
        self.assertNotIn("count {}", self.waf)
        self.assertIn('oversize_handling = "MATCH"', self.waf)
        self.assertIn("evaluation_window_sec = 300", self.waf)

    def test_schema_and_body_limit_are_closed(self) -> None:
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(
            {
                "patientReference",
                "appointmentTypeCode",
                "requestedDate",
                "timePreference",
                "locationCode",
                "contactPreference",
            },
            set(self.schema["properties"]),
        )
        self.assertIn("size                = var.maximum_request_body_bytes", self.waf)

    def test_logs_exclude_bodies_queries_and_authentication_material(self) -> None:
        access_log = self.api.split("access_log_settings {", 1)[1].split(
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
            with self.subTest(value=forbidden):
                self.assertNotIn(forbidden, access_log)
        self.assertIn('name = "authorization"', self.waf)
        self.assertIn('name = "cookie"', self.waf)
        self.assertIn("query_string {}", self.waf)

    def test_server_to_server_api_has_no_cors_and_disables_caching(self) -> None:
        self.assertNotIn("Access-Control-Allow-Origin", self.api)
        self.assertNotIn('http_method   = "OPTIONS"', self.api)
        self.assertIn("Browsers are not intended to call API Gateway directly", self.readme)
        self.assertEqual(2, self.api.count('"gatewayresponse.header.Cache-Control"'))
        self.assertIn("'no-store'", self.api)


if __name__ == "__main__":
    unittest.main()

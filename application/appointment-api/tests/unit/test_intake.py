from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from intake.handler import lambda_handler  # noqa: E402


class IntakeHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = SimpleNamespace(aws_request_id="lambda-request-123")

    def test_rejects_unsupported_content_type(self) -> None:
        response = lambda_handler(
            {"headers": {"Content-Type": "text/plain"}, "body": "ignored"},
            self.context,
        )

        self.assertEqual(415, response["statusCode"])

    def test_rejects_invalid_json(self) -> None:
        response = lambda_handler(
            {"headers": {"Content-Type": "application/json"}, "body": "{"},
            self.context,
        )

        self.assertEqual(400, response["statusCode"])

    def test_returns_controlled_foundation_response(self) -> None:
        response = lambda_handler(
            {
                "headers": {
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Correlation-Id": "correlation-123",
                },
                "body": json.dumps({"patientReference": "SYNTHETIC-001"}),
            },
            self.context,
        )

        payload = json.loads(response["body"])
        self.assertEqual(202, response["statusCode"])
        self.assertEqual("FOUNDATION_ONLY", payload["status"])
        self.assertIn("no appointment was created", payload["message"])


if __name__ == "__main__":
    unittest.main()

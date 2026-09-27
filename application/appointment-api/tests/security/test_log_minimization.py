from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from intake.handler import handle_request  # noqa: E402
from tests.helpers import FakeSecretClient, NOW, signed_event  # noqa: E402


class NeverCalled:
    def __getattr__(self, name):
        raise AssertionError(f"AWS workflow operation occurred before authentication: {name}")


class LogMinimizationTests(unittest.TestCase):
    def test_logs_exclude_body_secret_signature_and_contact_values(self) -> None:
        contact_marker = "SYNTHETIC-CONTACT-NOT-FOR-LOGS"
        secret_marker = "synthetic-secret-not-for-logs-000000001"
        body = json.dumps(
            {
                "patientReference": contact_marker,
                "appointmentTypeCode": "GENERAL_CONSULT",
                "requestedDate": "2030-01-15",
            },
            separators=(",", ":"),
        )
        event = signed_event(body=body, key=secret_marker)
        signature_marker = event["headers"]["X-Clinic-Signature"]
        event["headers"]["X-Clinic-Signature"] = "v1=" + ("A" * 43) + "="
        output = io.StringIO()

        with patch.dict(
            os.environ,
            {"HMAC_SECRET_ARN": "arn:aws:secretsmanager:region:account:secret:test"},
            clear=False,
        ), contextlib.redirect_stdout(output):
            handle_request(
                event,
                SimpleNamespace(aws_request_id="security-test-request"),
                secret_client=FakeSecretClient(
                    {"keys": {"v1": {"enabled": True, "key": secret_marker}}}
                ),
                dynamodb_client=NeverCalled(),
                sqs_client=NeverCalled(),
                now=lambda: NOW,
            )

        logged = output.getvalue()
        self.assertNotIn(contact_marker, logged)
        self.assertNotIn(secret_marker, logged)
        self.assertNotIn(signature_marker, logged)
        self.assertNotIn(event["headers"]["X-Clinic-Signature"], logged)
        self.assertNotIn("patientReference", logged)
        self.assertIn("BAD_HMAC", logged)


if __name__ == "__main__":
    unittest.main()

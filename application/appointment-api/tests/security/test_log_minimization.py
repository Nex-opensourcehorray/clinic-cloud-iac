from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from intake.handler import lambda_handler  # noqa: E402


class LogMinimizationTests(unittest.TestCase):
    def test_intake_does_not_log_request_body_or_signature(self) -> None:
        sensitive_marker = "SYNTHETIC-CONTACT-NOT-FOR-LOGS"
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            lambda_handler(
                {
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Clinic-Signature": "synthetic-signature-marker",
                    },
                    "body": json.dumps(
                        {
                            "patientReference": sensitive_marker,
                            "appointmentTypeCode": "GENERAL_CONSULT",
                            "requestedDate": "2030-01-15",
                        }
                    ),
                },
                SimpleNamespace(aws_request_id="security-test-request"),
            )

        logged = output.getvalue()
        self.assertNotIn(sensitive_marker, logged)
        self.assertNotIn("synthetic-signature-marker", logged)
        self.assertNotIn("patientReference", logged)


if __name__ == "__main__":
    unittest.main()

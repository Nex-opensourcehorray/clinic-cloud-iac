from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from worker.handler import lambda_handler  # noqa: E402


class WorkerHandlerTests(unittest.TestCase):
    def test_accepts_minimum_envelope_without_clinical_action(self) -> None:
        result = lambda_handler(
            {
                "Records": [
                    {
                        "messageId": "message-1",
                        "body": json.dumps(
                            {
                                "requestId": "request-1",
                                "correlationId": "correlation-1",
                            }
                        ),
                        "attributes": {"ApproximateReceiveCount": "1"},
                    }
                ]
            },
            None,
        )

        self.assertEqual([], result["batchItemFailures"])

    def test_reports_invalid_envelope_as_batch_failure(self) -> None:
        result = lambda_handler(
            {
                "Records": [
                    {
                        "messageId": "message-2",
                        "body": "not-json",
                        "attributes": {"ApproximateReceiveCount": "2"},
                    }
                ]
            },
            None,
        )

        self.assertEqual(
            [{"itemIdentifier": "message-2"}], result["batchItemFailures"]
        )


if __name__ == "__main__":
    unittest.main()

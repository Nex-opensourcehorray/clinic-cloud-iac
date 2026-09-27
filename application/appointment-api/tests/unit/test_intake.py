from __future__ import annotations

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


class RecordingDynamo:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.transactions = []

    def transact_write_items(self, *, TransactItems, **kwargs):
        del kwargs
        self.transactions.append(TransactItems)
        if self.fail:
            raise RuntimeError("synthetic DynamoDB failure")
        return {}


class RecordingSqs:
    def __init__(self) -> None:
        self.messages = []

    def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return {"MessageId": "message-001"}


class IntakeHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = SimpleNamespace(aws_request_id="lambda-request-123")
        self.environment = patch.dict(
            os.environ,
            {
                "HMAC_SECRET_ARN": "arn:aws:secretsmanager:region:account:secret:test",
                "WORKFLOW_TABLE_NAME": "workflow-table",
                "WORK_QUEUE_URL": "https://sqs.example/work",
                "NONCE_TTL_SECONDS": "600",
                "IDEMPOTENCY_TTL_SECONDS": "604800",
            },
            clear=False,
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()

    def invoke(self, event, dynamo=None, sqs=None):
        return handle_request(
            event,
            self.context,
            secret_client=FakeSecretClient(),
            dynamodb_client=dynamo or RecordingDynamo(),
            sqs_client=sqs or RecordingSqs(),
            now=lambda: NOW,
        )

    def test_valid_authenticated_request_returns_202(self) -> None:
        dynamo = RecordingDynamo()
        sqs = RecordingSqs()
        response = self.invoke(signed_event(), dynamo, sqs)
        payload = json.loads(response["body"])
        self.assertEqual(202, response["statusCode"])
        self.assertEqual("QUEUED", payload["status"])
        self.assertEqual(1, len(sqs.messages))
        self.assertEqual(2, len(dynamo.transactions))

    def test_no_queue_or_dynamodb_operation_before_authentication(self) -> None:
        event = signed_event()
        event["headers"]["X-Clinic-Signature"] = "v1=" + ("A" * 43) + "="
        dynamo = RecordingDynamo()
        sqs = RecordingSqs()
        response = self.invoke(event, dynamo, sqs)
        self.assertEqual(401, response["statusCode"])
        self.assertEqual([], dynamo.transactions)
        self.assertEqual([], sqs.messages)

    def test_dynamodb_failure_does_not_enqueue(self) -> None:
        sqs = RecordingSqs()
        response = self.invoke(signed_event(), RecordingDynamo(fail=True), sqs)
        self.assertEqual(503, response["statusCode"])
        self.assertEqual([], sqs.messages)

    def test_missing_secret_configuration_fails_closed(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            response = self.invoke(signed_event())
        self.assertEqual(503, response["statusCode"])


if __name__ == "__main__":
    unittest.main()

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
from tests.helpers import FakeSecretClient, NOW, SOURCE_KEY, signed_event  # noqa: E402


class RecordingDynamo:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.transactions: list[list[dict]] = []

    def transact_write_items(self, *, TransactItems, **kwargs):
        del kwargs
        self.transactions.append(TransactItems)
        if self.fail:
            raise RuntimeError("synthetic internal table detail")
        return {}


class RecordingSqs:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return {"MessageId": "message-1"}


class TransactionCanceled(Exception):
    def __init__(self) -> None:
        super().__init__("synthetic transaction cancellation")
        self.response = {"Error": {"Code": "TransactionCanceledException"}}


class ReplayDynamo:
    def __init__(self) -> None:
        self.transactions: list[list[dict]] = []

    def transact_write_items(self, *, TransactItems, **kwargs):
        del kwargs
        self.transactions.append(TransactItems)
        raise TransactionCanceled()

    def get_item(self, *, Key, **kwargs):
        del kwargs
        if Key["PK"]["S"].startswith("NONCE#"):
            return {"Item": {"PK": {"S": "existing-nonce"}}}
        return {}


class NegativeApiPrivacyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = SimpleNamespace(aws_request_id="lambda-invocation-1")
        self.environment = patch.dict(
            os.environ,
            {
                "HMAC_SECRET_ARN": "arn:aws:secretsmanager:region:account:secret:test",
                "WORKFLOW_TABLE_NAME": "workflow-table",
                "WORK_QUEUE_URL": "https://sqs.example/work",
            },
            clear=False,
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()

    def invoke(self, event, *, secret=None, dynamo=None, sqs=None):
        return handle_request(
            event,
            self.context,
            secret_client=secret or FakeSecretClient(),
            dynamodb_client=dynamo or RecordingDynamo(),
            sqs_client=sqs or RecordingSqs(),
            now=lambda: NOW,
        )

    def assert_public_response_is_minimized(self, response, markers=()) -> None:
        serialized = json.dumps(response, sort_keys=True).lower()
        forbidden = (
            "arn:aws:",
            "lambda",
            "workflow-table",
            "sqs.example",
            "clinic-nonprod-appointment-api-alerts",
            "<AWS_ACCOUNT_ID>",
            "traceback",
            "stack trace",
            "conditionalcheckfailed",
            "conditionexpression",
            "x-clinic-signature",
            "x-content-sha256",
            "secretaccesskey",
            "sessiontoken",
        )
        for value in forbidden + tuple(str(marker).lower() for marker in markers):
            self.assertNotIn(value, serialized)

    def test_all_unsupported_methods_and_paths_fail_before_business_calls(self) -> None:
        cases = (
            ("GET", "/appointments"),
            ("PUT", "/appointments"),
            ("PATCH", "/appointments"),
            ("DELETE", "/appointments"),
            ("OPTIONS", "/appointments"),
            ("POST", "/"),
            ("POST", "/unknown"),
        )
        for method, path in cases:
            with self.subTest(method=method, path=path):
                event = signed_event()
                event["httpMethod"] = method
                event["resource"] = path
                dynamo = RecordingDynamo()
                sqs = RecordingSqs()
                response = self.invoke(event, dynamo=dynamo, sqs=sqs)
                self.assertEqual(400, response["statusCode"])
                self.assertEqual([], dynamo.transactions)
                self.assertEqual([], sqs.messages)
                self.assert_public_response_is_minimized(response)

    def test_wrong_or_missing_content_type_and_query_fail_closed(self) -> None:
        events = []
        wrong = signed_event()
        wrong["headers"]["Content-Type"] = "text/plain"
        events.append(wrong)
        missing = signed_event()
        del missing["headers"]["Content-Type"]
        events.append(missing)
        query = signed_event()
        query["rawQueryString"] = "unexpected=true"
        events.append(query)
        for event in events:
            with self.subTest(event=event):
                dynamo = RecordingDynamo()
                sqs = RecordingSqs()
                response = self.invoke(event, dynamo=dynamo, sqs=sqs)
                self.assertGreaterEqual(response["statusCode"], 400)
                self.assertEqual([], dynamo.transactions)
                self.assertEqual([], sqs.messages)

    def test_malformed_empty_and_nonobject_json_are_generic_contract_failures(self) -> None:
        for body in (b"", b"{", b"null", b"[]", b'"string"'):
            with self.subTest(body=body):
                response = self.invoke(signed_event(body=body))
                self.assertEqual(400, response["statusCode"])
                self.assertEqual(
                    "Request body does not match the appointment contract.",
                    json.loads(response["body"])["message"],
                )
                self.assert_public_response_is_minimized(response)

    def test_bounded_malformed_json_inputs_fail_deterministically(self) -> None:
        bodies = (
            b"{]",
            b'{"a":}',
            b'{"a":1,}',
            b'{"a" "b"}',
            b"\x00",
            b"[1,2",
            b'{"unterminated":"value}',
        )
        for body in bodies:
            with self.subTest(body=body):
                response = self.invoke(signed_event(body=body))
                self.assertEqual(400, response["statusCode"])
                self.assert_public_response_is_minimized(response, (body,))

    def test_prohibited_field_classes_are_rejected_without_leakage(self) -> None:
        fields = {
            "clinicalNotes": "SYNTHETIC-CLINICAL-MARKER",
            "freeText": "SYNTHETIC-FREE-TEXT-MARKER",
            "paymentCard": "SYNTHETIC-PAYMENT-MARKER",
            "password": "SYNTHETIC-PASSWORD-MARKER",
            "credential": "SYNTHETIC-CREDENTIAL-MARKER",
        }
        base = {
            "patientReference": "SYNTHETIC-PATIENT-001",
            "appointmentTypeCode": "GENERAL_CONSULT",
            "requestedDate": "2030-01-15",
        }
        for field, marker in fields.items():
            with self.subTest(field=field):
                document = dict(base)
                document[field] = marker
                response = self.invoke(
                    signed_event(
                        body=json.dumps(document, separators=(",", ":"))
                    )
                )
                self.assertEqual(400, response["statusCode"])
                self.assert_public_response_is_minimized(response, (marker, field))

    def test_key_validity_is_not_disclosed_in_public_response(self) -> None:
        unknown = self.invoke(signed_event(key_id="unknown"))
        disabled = self.invoke(
            signed_event(),
            secret=FakeSecretClient(
                {"keys": {"v1": {"enabled": False, "key": SOURCE_KEY}}}
            ),
        )
        bad_hmac_event = signed_event()
        bad_hmac_event["headers"]["X-Clinic-Signature"] = "v1=" + ("A" * 43) + "="
        bad_hmac = self.invoke(bad_hmac_event)
        bodies = {response["body"] for response in (unknown, disabled, bad_hmac)}
        self.assertEqual(1, len(bodies))
        for response in (unknown, disabled, bad_hmac):
            self.assertEqual(401, response["statusCode"])
            self.assert_public_response_is_minimized(response)

    def test_internal_service_failures_do_not_leak_topology_or_exception_text(self) -> None:
        response = self.invoke(signed_event(), dynamo=RecordingDynamo(fail=True))
        self.assertEqual(503, response["statusCode"])
        self.assert_public_response_is_minimized(
            response, ("synthetic internal table detail",)
        )

    def test_public_acceptance_never_claims_appointment_confirmation(self) -> None:
        sqs = RecordingSqs()
        response = self.invoke(signed_event(), sqs=sqs)
        self.assertEqual(202, response["statusCode"])
        body = response["body"].lower()
        for prohibited_claim in (
            "appointment confirmed",
            "appointment scheduled",
            "clinical success",
            '"status":"succeeded"',
        ):
            self.assertNotIn(prohibited_claim, body)
        queue_body = sqs.messages[0]["MessageBody"].lower()
        self.assertNotIn("confirmed", queue_body)
        self.assertNotIn("succeeded", queue_body)

    def test_negative_path_logs_exclude_body_and_authentication_markers(self) -> None:
        marker = "SYNTHETIC-CONTACT-NEVER-LOG"
        document = {
            "patientReference": "SYNTHETIC-PATIENT-001",
            "appointmentTypeCode": "GENERAL_CONSULT",
            "requestedDate": "2030-01-15",
            "contact": marker,
        }
        event = signed_event(body=json.dumps(document, separators=(",", ":")))
        signature = event["headers"]["X-Clinic-Signature"]
        digest = event["headers"]["X-Content-SHA256"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            response = self.invoke(event)
        self.assertEqual(400, response["statusCode"])
        emitted = output.getvalue()
        for forbidden in (marker, signature, digest, "contact"):
            self.assertNotIn(forbidden, emitted)

    def test_replay_telemetry_excludes_nonce_signature_digest_and_body(self) -> None:
        event = signed_event()
        nonce = event["headers"]["X-Clinic-Nonce"]
        signature = event["headers"]["X-Clinic-Signature"]
        digest = event["headers"]["X-Content-SHA256"]
        body = event["body"]
        sqs = RecordingSqs()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            response = self.invoke(event, dynamo=ReplayDynamo(), sqs=sqs)
        self.assertEqual(409, response["statusCode"])
        self.assertEqual([], sqs.messages)
        serialized = output.getvalue() + response["body"]
        self.assertIn("NONCE_REPLAY", output.getvalue())
        for forbidden in (nonce, signature, digest, body, "SYNTHETIC-PATIENT-001"):
            self.assertNotIn(forbidden, serialized)

    def test_response_headers_prevent_caching_on_success_and_failure(self) -> None:
        success = self.invoke(signed_event())
        failure_event = signed_event()
        del failure_event["headers"]["X-Clinic-Signature"]
        failure = self.invoke(failure_event)
        for response in (success, failure):
            self.assertEqual("no-store", response["headers"]["Cache-Control"])
            self.assertEqual("application/json", response["headers"]["Content-Type"])


if __name__ == "__main__":
    unittest.main()

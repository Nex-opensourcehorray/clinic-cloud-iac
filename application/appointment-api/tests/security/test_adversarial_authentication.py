from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import string
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from common.authentication import (  # noqa: E402
    AuthenticationError,
    build_canonical_request,
    authenticate_request,
)
from intake.handler import handle_request  # noqa: E402
from tests.helpers import FakeSecretClient, NOW, SOURCE_KEY, signed_event  # noqa: E402


class NoBusinessSideEffects:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def transact_write_items(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("Authentication failure reached DynamoDB")

    def send_message(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("Authentication failure reached SQS")


class AdversarialAuthenticationTests(unittest.TestCase):
    def authenticate(self, event, **kwargs):
        return authenticate_request(
            event,
            secret_client=kwargs.pop("secret_client", FakeSecretClient()),
            secret_arn="arn:aws:secretsmanager:region:account:secret:test",
            now=lambda: kwargs.pop("current_time", NOW),
            **kwargs,
        )

    def assert_category(self, category: str, event, **kwargs) -> None:
        with self.assertRaises(AuthenticationError) as raised:
            self.authenticate(event, **kwargs)
        self.assertEqual(category, raised.exception.category)

    def test_missing_and_empty_signature_or_key_id_fail(self) -> None:
        for header in ("X-Clinic-Signature", "X-Clinic-Key-Id"):
            with self.subTest(header=header, case="missing"):
                event = signed_event()
                del event["headers"][header]
                self.assert_category("MISSING_REQUIRED_HEADER", event)
            with self.subTest(header=header, case="empty"):
                event = signed_event()
                event["headers"][header] = ""
                self.assert_category("DUPLICATE_SECURITY_HEADER", event)

    def test_malformed_base64_signatures_fail(self) -> None:
        for signature in ("not-versioned", "v1=!!!!", "v1=A", "v1=AA=="):
            with self.subTest(signature=signature):
                event = signed_event()
                event["headers"]["X-Clinic-Signature"] = signature
                self.assert_category("MALFORMED_SIGNATURE", event)

    def test_wrong_hmac_key_unknown_key_and_disabled_key_fail(self) -> None:
        self.assert_category("BAD_HMAC", signed_event(key="x" * 40))
        self.assert_category("UNKNOWN_KEY_ID", signed_event(key_id="unknown"))
        self.assert_category(
            "DISABLED_KEY",
            signed_event(),
            secret_client=FakeSecretClient(
                {"keys": {"v1": {"enabled": False, "key": SOURCE_KEY}}}
            ),
        )

    def test_duplicate_and_mixed_case_duplicate_headers_fail(self) -> None:
        for header in ("X-Clinic-Key-Id", "X-Clinic-Signature"):
            with self.subTest(header=header):
                event = signed_event()
                event["headers"][header.swapcase()] = event["headers"][header]
                self.assert_category("DUPLICATE_SECURITY_HEADER", event)

        event = signed_event()
        event["multiValueHeaders"] = {
            "X-Clinic-Key-Id": ["v1"],
            "x-clinic-key-id": ["v1"],
        }
        self.assert_category("DUPLICATE_SECURITY_HEADER", event)

    def test_timestamp_validation_is_exact_and_ascii_only(self) -> None:
        for value in ("", "not-a-number", "1.5", "-1", "２０００００００００"):
            with self.subTest(value=value):
                event = signed_event()
                event["headers"]["X-Clinic-Timestamp"] = value
                expected = (
                    "DUPLICATE_SECURITY_HEADER" if value == "" else "MALFORMED_TIMESTAMP"
                )
                self.assert_category(expected, event)
        for timestamp in (NOW - 300, NOW + 300):
            self.authenticate(signed_event(timestamp=timestamp))
        self.assert_category("EXPIRED_TIMESTAMP", signed_event(timestamp=NOW - 301))
        self.assert_category("FUTURE_TIMESTAMP", signed_event(timestamp=NOW + 301))

    def test_digest_and_signature_layers_fail_independently(self) -> None:
        malformed = signed_event()
        malformed["headers"]["X-Content-SHA256"] = "xyz"
        self.assert_category("MALFORMED_BODY_DIGEST", malformed)

        mismatch = signed_event()
        mismatch["headers"]["X-Content-SHA256"] = "0" * 64
        self.assert_category("BODY_DIGEST_MISMATCH", mismatch)

        incorrect_mac = signed_event()
        incorrect_mac["headers"]["X-Clinic-Signature"] = (
            "v1=" + base64.b64encode(b"x" * 32).decode("ascii")
        )
        self.assert_category("BAD_HMAC", incorrect_mac)

    def test_signed_request_mutations_fail(self) -> None:
        mutations = {
            "body": lambda event: event.update({"body": event["body"] + " "}),
            "path": lambda event: event.update({"resource": "/appointments/other"}),
            "method": lambda event: event.update({"httpMethod": "PUT"}),
            "query": lambda event: event.update(
                {"queryStringParameters": {"smuggled": "true"}}
            ),
            "content-type": lambda event: event["headers"].update(
                {"Content-Type": "application/json; charset=utf-8"}
            ),
            "idempotency": lambda event: event["headers"].update(
                {"Idempotency-Key": "idem-mutated"}
            ),
            "nonce": lambda event: event["headers"].update(
                {"X-Clinic-Nonce": "nonce-000000000099"}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                event = signed_event()
                mutate(event)
                with self.assertRaises(AuthenticationError):
                    self.authenticate(event)

    def test_base64_manipulation_truncation_and_oversize_fail(self) -> None:
        invalid = signed_event(base64_encoded=True)
        invalid["body"] = "%%%"
        self.assert_category("INVALID_BODY_ENCODING", invalid)

        manipulated = signed_event(base64_encoded=True)
        raw = base64.b64decode(manipulated["body"])
        manipulated["body"] = base64.b64encode(raw + b" ").decode("ascii")
        self.assert_category("BODY_DIGEST_MISMATCH", manipulated)

        truncated = signed_event()
        truncated["body"] = truncated["body"][:-1]
        self.assert_category("BODY_DIGEST_MISMATCH", truncated)

        self.assert_category("BODY_TOO_LARGE", signed_event(body=b"A" * 16385))
        self.assertEqual(
            16384,
            len(self.authenticate(signed_event(body=b"A" * 16384)).body_bytes),
        )

    def test_secret_retrieval_and_document_failures_are_controlled(self) -> None:
        cases = (
            (FakeSecretClient(error=RuntimeError("synthetic")), "SECRET_RETRIEVAL_FAILURE"),
            (FakeSecretClient("not-json"), "INVALID_SECRET_DOCUMENT"),
            (FakeSecretClient({"notKeys": {}}), "INVALID_SECRET_DOCUMENT"),
            (FakeSecretClient({"keys": []}), "INVALID_SECRET_DOCUMENT"),
            (
                FakeSecretClient(
                    {"keys": {"v1": {"enabled": True, "key": "short"}}}
                ),
                "INVALID_SECRET_DOCUMENT",
            ),
        )
        for client, category in cases:
            with self.subTest(category=category):
                self.assert_category(category, signed_event(), secret_client=client)

    def test_canonical_request_is_deterministic_and_exact(self) -> None:
        body = b'{"patientReference":"SYNTHETIC-1"}'
        digest = hashlib.sha256(body).hexdigest()
        first = build_canonical_request(
            body_digest=digest,
            idempotency_key="idem-1",
            nonce="nonce-000000000001",
            timestamp=NOW,
        )
        second = build_canonical_request(
            body_digest=digest,
            idempotency_key="idem-1",
            nonce="nonce-000000000001",
            timestamp=NOW,
        )
        self.assertEqual(first, second)
        self.assertEqual(9, len(first.decode("utf-8").split("\n")))
        self.assertIn("\nPOST\n/appointments\n\napplication/json\n", first.decode())

    def test_exact_body_bytes_are_authenticated_without_json_normalization(self) -> None:
        bodies = (
            b'{"a":1,"b":2}',
            b'{ "a": 1, "b": 2 }',
            b'{"b":2,"a":1}',
            b'{"line":"a\\nb"}',
            b'{"line":"a\\r\\nb"}',
            '{"value":"caf\u00e9 \\u2603"}'.encode("utf-8"),
            b'{"optional":""}',
        )
        digests = set()
        for body in bodies:
            with self.subTest(body=body):
                result = self.authenticate(signed_event(body=body))
                self.assertEqual(body, result.body_bytes)
                digests.add(result.body_digest)
        self.assertEqual(len(bodies), len(digests))

    def test_reformatted_json_invalidates_original_signature(self) -> None:
        original = b'{"a":1,"b":2}'
        for changed in (b'{ "a": 1, "b": 2 }', b'{"b":2,"a":1}'):
            with self.subTest(changed=changed):
                event = signed_event(body=original)
                event["body"] = changed.decode("utf-8")
                self.assert_category("BODY_DIGEST_MISMATCH", event)

    def test_base64_and_plain_gateway_forms_preserve_identical_body_bytes(self) -> None:
        body = '{"value":"unicode-\u2603"}'.encode("utf-8")
        plain = self.authenticate(signed_event(body=body))
        encoded = self.authenticate(signed_event(body=body, base64_encoded=True))
        self.assertEqual(plain.body_bytes, encoded.body_bytes)
        self.assertEqual(plain.body_digest, encoded.body_digest)

    def test_header_casing_does_not_change_authentication(self) -> None:
        event = signed_event()
        event["headers"] = {key.swapcase(): value for key, value in event["headers"].items()}
        self.authenticate(event)

    def test_exact_path_and_query_absence_are_required(self) -> None:
        for path in ("", "/", "/appointments/", "/Appointments"):
            with self.subTest(path=path):
                event = signed_event()
                event["resource"] = path
                self.assert_category("INVALID_REQUEST_TARGET", event)
        for query_field, value in (
            ("queryStringParameters", {"a": "1"}),
            ("multiValueQueryStringParameters", {"a": ["1"]}),
            ("rawQueryString", "a=1"),
        ):
            with self.subTest(query_field=query_field):
                event = signed_event()
                event[query_field] = value
                self.assert_category("UNEXPECTED_QUERY_PARAMETERS", event)

    def test_bounded_header_fuzz_fails_deterministically(self) -> None:
        generator = random.Random(3701)
        alphabet = string.whitespace + "\x00,;:/\\" + "\u2603"
        for _ in range(32):
            value = "".join(generator.choice(alphabet) for _ in range(12))
            event = signed_event()
            event["headers"]["X-Clinic-Nonce"] = value
            with self.assertRaises(AuthenticationError):
                self.authenticate(event)

    def test_authentication_failures_precede_business_side_effects(self) -> None:
        invalid_events = []
        for header in (
            "X-Clinic-Signature",
            "X-Clinic-Key-Id",
            "X-Clinic-Timestamp",
            "X-Content-SHA256",
        ):
            event = signed_event()
            del event["headers"][header]
            invalid_events.append(event)
        invalid_events.extend(
            [
                signed_event(timestamp=NOW - 301),
                signed_event(timestamp=NOW + 301),
                signed_event(body=b"A" * 16385),
            ]
        )
        with patch.dict(
            os.environ,
            {
                "HMAC_SECRET_ARN": "arn:aws:secretsmanager:region:account:secret:test",
                "WORKFLOW_TABLE_NAME": "workflow-table",
                "WORK_QUEUE_URL": "https://sqs.example/work",
            },
            clear=False,
        ):
            for event in invalid_events:
                with self.subTest(headers=event.get("headers")):
                    dynamo = NoBusinessSideEffects()
                    sqs = NoBusinessSideEffects()
                    response = handle_request(
                        event,
                        SimpleNamespace(aws_request_id="lambda-request"),
                        secret_client=FakeSecretClient(),
                        dynamodb_client=dynamo,
                        sqs_client=sqs,
                        now=lambda: NOW,
                    )
                    self.assertGreaterEqual(response["statusCode"], 400)
                    self.assertEqual([], dynamo.calls)
                    self.assertEqual([], sqs.calls)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

from common.authentication import AuthenticationError, authenticate_request  # noqa: E402
from tests.helpers import FakeSecretClient, NOW, SOURCE_KEY, signed_event  # noqa: E402


class AuthenticationTests(unittest.TestCase):
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

    def test_valid_hmac(self) -> None:
        result = self.authenticate(signed_event())
        self.assertEqual("v1", result.key_id)
        self.assertEqual("idem-0001", result.idempotency_key)

    def test_invalid_hmac(self) -> None:
        event = signed_event()
        event["headers"]["X-Clinic-Signature"] = "v1=" + ("A" * 43) + "="
        self.assert_category("BAD_HMAC", event)

    def test_unknown_key_id(self) -> None:
        self.assert_category("UNKNOWN_KEY_ID", signed_event(key_id="unknown"))

    def test_disabled_key(self) -> None:
        client = FakeSecretClient(
            {"keys": {"v1": {"enabled": False, "key": SOURCE_KEY}}}
        )
        self.assert_category("DISABLED_KEY", signed_event(), secret_client=client)

    def test_missing_secret(self) -> None:
        client = FakeSecretClient(error=RuntimeError("synthetic missing secret"))
        self.assert_category(
            "SECRET_RETRIEVAL_FAILURE", signed_event(), secret_client=client
        )

    def test_malformed_secret_json(self) -> None:
        self.assert_category(
            "INVALID_SECRET_DOCUMENT",
            signed_event(),
            secret_client=FakeSecretClient("not-json"),
        )

    def test_malformed_secret_key_entry(self) -> None:
        self.assert_category(
            "INVALID_SECRET_DOCUMENT",
            signed_event(),
            secret_client=FakeSecretClient(
                {"keys": {"v1": {"enabled": "yes", "key": SOURCE_KEY}}}
            ),
        )

    def test_missing_required_header(self) -> None:
        event = signed_event()
        del event["headers"]["X-Clinic-Nonce"]
        self.assert_category("MISSING_REQUIRED_HEADER", event)

    def test_duplicate_security_header(self) -> None:
        event = signed_event()
        event["multiValueHeaders"] = {
            "x-clinic-nonce": ["nonce-000000000001", "nonce-000000000002"]
        }
        self.assert_category("DUPLICATE_SECURITY_HEADER", event)

    def test_timestamp_too_old(self) -> None:
        self.assert_category("EXPIRED_TIMESTAMP", signed_event(timestamp=NOW - 301))

    def test_timestamp_too_far_in_future(self) -> None:
        self.assert_category("FUTURE_TIMESTAMP", signed_event(timestamp=NOW + 301))

    def test_exact_timestamp_boundaries(self) -> None:
        for timestamp in (NOW - 300, NOW + 300):
            with self.subTest(timestamp=timestamp):
                self.authenticate(signed_event(timestamp=timestamp))

    def test_body_digest_mismatch(self) -> None:
        event = signed_event()
        event["headers"]["X-Content-SHA256"] = "0" * 64
        self.assert_category("BODY_DIGEST_MISMATCH", event)

    def test_base64_api_gateway_body(self) -> None:
        result = self.authenticate(signed_event(base64_encoded=True))
        self.assertIn(b"SYNTHETIC-PATIENT-001", result.body_bytes)

    def test_body_size_rejection(self) -> None:
        event = signed_event(body=b"{}")
        self.assert_category("BODY_TOO_LARGE", event, maximum_body_bytes=1)

    def test_wrong_content_type(self) -> None:
        event = signed_event()
        event["headers"]["Content-Type"] = "text/plain"
        self.assert_category("UNSUPPORTED_CONTENT_TYPE", event)

    def test_unexpected_query_parameters(self) -> None:
        event = signed_event()
        event["queryStringParameters"] = {"unexpected": "true"}
        self.assert_category("UNEXPECTED_QUERY_PARAMETERS", event)

    def test_header_lookup_is_case_insensitive(self) -> None:
        event = signed_event()
        event["headers"] = {key.swapcase(): value for key, value in event["headers"].items()}
        self.authenticate(event)

    def test_previous_rotation_key_can_overlap(self) -> None:
        previous = "synthetic-previous-key-material-0000000001"
        client = FakeSecretClient(
            {
                "keys": {
                    "v1": {"enabled": True, "key": SOURCE_KEY},
                    "v0": {"enabled": True, "key": previous},
                }
            }
        )
        result = self.authenticate(
            signed_event(key_id="v0", key=previous), secret_client=client
        )
        self.assertEqual("v0", result.key_id)


if __name__ == "__main__":
    unittest.main()

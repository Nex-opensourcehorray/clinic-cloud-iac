from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any


SOURCE_KEY = "synthetic-unit-test-key-material-000000000001"
NOW = 2_000_000_000


class FakeSecretClient:
    def __init__(self, document: Any = None, error: Exception | None = None) -> None:
        self.document = document
        self.error = error
        self.calls = 0

    def get_secret_value(self, **kwargs: Any) -> dict[str, str]:
        del kwargs
        self.calls += 1
        if self.error:
            raise self.error
        if isinstance(self.document, str):
            return {"SecretString": self.document}
        document = self.document
        if document is None:
            document = {"keys": {"v1": {"enabled": True, "key": SOURCE_KEY}}}
        return {"SecretString": json.dumps(document)}


def signed_event(
    *,
    body: str | bytes | None = None,
    key: str = SOURCE_KEY,
    key_id: str = "v1",
    nonce: str = "nonce-000000000001",
    idempotency_key: str = "idem-0001",
    timestamp: int = NOW,
    base64_encoded: bool = False,
) -> dict[str, Any]:
    from common.authentication import build_canonical_request

    if body is None:
        body = json.dumps(
            {
                "patientReference": "SYNTHETIC-PATIENT-001",
                "appointmentTypeCode": "GENERAL_CONSULT",
                "requestedDate": "2030-01-15",
            },
            separators=(",", ":"),
        )
    body_bytes = body if isinstance(body, bytes) else body.encode("utf-8")
    digest = hashlib.sha256(body_bytes).hexdigest()
    canonical = build_canonical_request(
        body_digest=digest,
        idempotency_key=idempotency_key,
        nonce=nonce,
        timestamp=timestamp,
    )
    signature = base64.b64encode(
        hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).digest()
    ).decode("ascii")
    event_body = (
        base64.b64encode(body_bytes).decode("ascii")
        if base64_encoded
        else body_bytes.decode("utf-8")
    )
    return {
        "httpMethod": "POST",
        "resource": "/appointments",
        "headers": {
            "Content-Type": "application/json",
            "X-Clinic-Key-Id": key_id,
            "X-Clinic-Timestamp": str(timestamp),
            "X-Clinic-Nonce": nonce,
            "Idempotency-Key": idempotency_key,
            "X-Content-SHA256": digest,
            "X-Clinic-Signature": f"v1={signature}",
            "X-Correlation-Id": "correlation-001",
        },
        "body": event_body,
        "isBase64Encoded": base64_encoded,
        "requestContext": {"requestId": "api-request-001"},
    }

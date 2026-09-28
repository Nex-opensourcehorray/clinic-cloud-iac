"""Fail-closed HMAC authentication for Appointment API requests."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any, Callable


EXPECTED_METHOD = "POST"
EXPECTED_PATH = "/appointments"
CANONICAL_VERSION = "CLINIC-HMAC-V1"
REQUIRED_HEADERS = (
    "x-clinic-key-id",
    "x-clinic-timestamp",
    "x-clinic-nonce",
    "idempotency-key",
    "x-content-sha256",
    "x-clinic-signature",
)

_KEY_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_NONCE = re.compile(r"^[A-Za-z0-9._~-]{16,128}$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
_SHA256_HEX = re.compile(r"^[0-9a-fA-F]{64}$")
_SIGNATURE = re.compile(r"^v1=([A-Za-z0-9+/]+={0,2})$")


class AuthenticationError(Exception):
    """A controlled request-authentication failure."""

    def __init__(
        self,
        category: str,
        message: str = "Request authentication failed.",
        status_code: int = 401,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class AuthenticatedRequest:
    body_bytes: bytes
    body_digest: str
    idempotency_key: str
    key_id: str
    nonce: str
    timestamp: int


def _header_values(event: dict[str, Any], name: str) -> tuple[list[str], list[str]]:
    single: list[str] = []
    for key, value in (event.get("headers") or {}).items():
        if str(key).lower() == name and value is not None:
            single.append(str(value).strip())

    multiple: list[str] = []
    matching_multi_keys = 0
    for key, values in (event.get("multiValueHeaders") or {}).items():
        if str(key).lower() != name:
            continue
        matching_multi_keys += 1
        if isinstance(values, list):
            multiple.extend(str(value).strip() for value in values if value is not None)
        elif values is not None:
            multiple.append(str(values).strip())

    if matching_multi_keys > 1:
        multiple.append("__AMBIGUOUS_HEADER_NAME__")
    return single, multiple


def _unique_header(event: dict[str, Any], name: str) -> str:
    single, multiple = _header_values(event, name)
    if len(single) > 1 or len(multiple) > 1:
        raise AuthenticationError("DUPLICATE_SECURITY_HEADER", status_code=400)

    if multiple:
        if single and not hmac.compare_digest(single[0], multiple[0]):
            raise AuthenticationError("DUPLICATE_SECURITY_HEADER", status_code=400)
        value = multiple[0]
    elif single:
        value = single[0]
    else:
        raise AuthenticationError("MISSING_REQUIRED_HEADER", status_code=400)

    if not value or "," in value:
        raise AuthenticationError("DUPLICATE_SECURITY_HEADER", status_code=400)
    return value


def _body_bytes(event: dict[str, Any], maximum_body_bytes: int) -> bytes:
    body = event.get("body")
    if not isinstance(body, str):
        raise AuthenticationError("INVALID_BODY_ENCODING", status_code=400)

    if event.get("isBase64Encoded") is True:
        try:
            decoded = base64.b64decode(body, validate=True)
        except (binascii.Error, ValueError) as error:
            raise AuthenticationError(
                "INVALID_BODY_ENCODING", status_code=400
            ) from error
    else:
        decoded = body.encode("utf-8")

    if len(decoded) > maximum_body_bytes:
        raise AuthenticationError(
            "BODY_TOO_LARGE", "Request body is too large.", status_code=413
        )
    return decoded


def _request_method(event: dict[str, Any]) -> str:
    method = event.get("httpMethod")
    if method is None:
        method = ((event.get("requestContext") or {}).get("http") or {}).get("method")
    return str(method or "").upper()


def _request_path(event: dict[str, Any]) -> str:
    return str(event.get("resource") or event.get("rawPath") or event.get("path") or "")


def _has_query(event: dict[str, Any]) -> bool:
    return bool(
        event.get("queryStringParameters")
        or event.get("multiValueQueryStringParameters")
        or event.get("rawQueryString")
    )


def build_canonical_request(
    *,
    body_digest: str,
    idempotency_key: str,
    nonce: str,
    timestamp: int,
) -> bytes:
    """Build the versioned canonical form; the query line is intentionally empty."""

    components = (
        CANONICAL_VERSION,
        EXPECTED_METHOD,
        EXPECTED_PATH,
        "",
        "application/json",
        body_digest,
        str(timestamp),
        nonce,
        idempotency_key,
    )
    return "\n".join(components).encode("utf-8")


def _resolve_key(secret_client: Any, secret_arn: str, key_id: str) -> bytes:
    try:
        response = secret_client.get_secret_value(SecretId=secret_arn)
    except Exception as error:
        raise AuthenticationError(
            "SECRET_RETRIEVAL_FAILURE",
            "Request authentication is temporarily unavailable.",
            status_code=503,
        ) from error

    secret_string = response.get("SecretString")
    if not isinstance(secret_string, str):
        raise AuthenticationError(
            "INVALID_SECRET_DOCUMENT",
            "Request authentication is temporarily unavailable.",
            status_code=503,
        )

    try:
        document = json.loads(secret_string)
        keys = document["keys"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise AuthenticationError(
            "INVALID_SECRET_DOCUMENT",
            "Request authentication is temporarily unavailable.",
            status_code=503,
        ) from error

    if not isinstance(keys, dict):
        raise AuthenticationError(
            "INVALID_SECRET_DOCUMENT",
            "Request authentication is temporarily unavailable.",
            status_code=503,
        )

    for candidate_id, candidate in keys.items():
        if (
            not isinstance(candidate_id, str)
            or not _KEY_ID.fullmatch(candidate_id)
            or not isinstance(candidate, dict)
            or not isinstance(candidate.get("enabled"), bool)
            or not isinstance(candidate.get("key"), str)
            or len(candidate["key"].encode("utf-8")) < 32
        ):
            raise AuthenticationError(
                "INVALID_SECRET_DOCUMENT",
                "Request authentication is temporarily unavailable.",
                status_code=503,
            )

    key_entry = keys.get(key_id)
    if not isinstance(key_entry, dict):
        raise AuthenticationError("UNKNOWN_KEY_ID")
    if key_entry.get("enabled") is not True:
        raise AuthenticationError("DISABLED_KEY")

    return key_entry["key"].encode("utf-8")


def authenticate_request(
    event: dict[str, Any],
    *,
    secret_client: Any,
    secret_arn: str,
    now: Callable[[], int],
    maximum_body_bytes: int = 16384,
    maximum_clock_skew_seconds: int = 300,
) -> AuthenticatedRequest:
    """Authenticate an API Gateway event before any business-side AWS call."""

    body_bytes = _body_bytes(event, maximum_body_bytes)
    content_type = _unique_header(event, "content-type").lower()
    if content_type != "application/json":
        raise AuthenticationError(
            "UNSUPPORTED_CONTENT_TYPE",
            "Content-Type must be application/json.",
            status_code=415,
        )

    headers = {name: _unique_header(event, name) for name in REQUIRED_HEADERS}

    if _request_method(event) != EXPECTED_METHOD or _request_path(event) != EXPECTED_PATH:
        raise AuthenticationError("INVALID_REQUEST_TARGET", status_code=400)
    if _has_query(event):
        raise AuthenticationError("UNEXPECTED_QUERY_PARAMETERS", status_code=400)

    timestamp_text = headers["x-clinic-timestamp"]
    if not timestamp_text.isascii() or not timestamp_text.isdigit():
        raise AuthenticationError("MALFORMED_TIMESTAMP", status_code=400)
    timestamp = int(timestamp_text)
    current_time = int(now())
    if timestamp < current_time - maximum_clock_skew_seconds:
        raise AuthenticationError("EXPIRED_TIMESTAMP")
    if timestamp > current_time + maximum_clock_skew_seconds:
        raise AuthenticationError("FUTURE_TIMESTAMP")

    key_id = headers["x-clinic-key-id"]
    nonce = headers["x-clinic-nonce"]
    idempotency_key = headers["idempotency-key"]
    claimed_digest = headers["x-content-sha256"].lower()
    signature = headers["x-clinic-signature"]

    if not _KEY_ID.fullmatch(key_id):
        raise AuthenticationError("MALFORMED_KEY_ID", status_code=400)
    if not _NONCE.fullmatch(nonce):
        raise AuthenticationError("MALFORMED_NONCE", status_code=400)
    if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
        raise AuthenticationError("MALFORMED_IDEMPOTENCY_KEY", status_code=400)
    if not _SHA256_HEX.fullmatch(claimed_digest):
        raise AuthenticationError("MALFORMED_BODY_DIGEST", status_code=400)

    calculated_digest = hashlib.sha256(body_bytes).hexdigest()
    if not hmac.compare_digest(calculated_digest, claimed_digest):
        raise AuthenticationError("BODY_DIGEST_MISMATCH")

    match = _SIGNATURE.fullmatch(signature)
    if match is None:
        raise AuthenticationError("MALFORMED_SIGNATURE", status_code=400)
    try:
        supplied_mac = base64.b64decode(match.group(1), validate=True)
    except (binascii.Error, ValueError) as error:
        raise AuthenticationError("MALFORMED_SIGNATURE", status_code=400) from error
    if len(supplied_mac) != hashlib.sha256().digest_size:
        raise AuthenticationError("MALFORMED_SIGNATURE", status_code=400)

    key = _resolve_key(secret_client, secret_arn, key_id)
    canonical = build_canonical_request(
        body_digest=calculated_digest,
        idempotency_key=idempotency_key,
        nonce=nonce,
        timestamp=timestamp,
    )
    expected_mac = hmac.new(key, canonical, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_mac, supplied_mac):
        raise AuthenticationError("BAD_HMAC")

    return AuthenticatedRequest(
        body_bytes=body_bytes,
        body_digest=calculated_digest,
        idempotency_key=idempotency_key,
        key_id=key_id,
        nonce=nonce,
        timestamp=timestamp,
    )

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings


settings = get_settings()


def now_utc() -> datetime:
    return datetime.now(UTC)


def generate_numeric_code(length: int | None = None) -> str:
    code_length = length or settings.auth_code_length
    return "".join(secrets.choice("0123456789") for _ in range(code_length))


def hash_verification_code(provider: str, target: str, code: str) -> str:
    message = f"{provider}:{target}:{code}".encode("utf-8")
    return hmac.new(settings.auth_secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_verification_code(provider: str, target: str, code: str, code_hash: str) -> bool:
    candidate = hash_verification_code(provider, target, code)
    return hmac.compare_digest(candidate, code_hash)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hmac.new(settings.auth_secret_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def create_access_token(*, user_id: str, session_id: str) -> tuple[str, int]:
    expires_in = settings.auth_access_token_ttl_seconds
    issued_at = now_utc()
    expires_at = issued_at + timedelta(seconds=expires_in)
    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": user_id,
        "sid": session_id,
        "typ": "access",
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    signing_input = f"{_base64url_json(header)}.{_base64url_json(payload)}"
    signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_base64url(signature)}", expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise ValueError("invalid token format") from exc

    signing_input = f"{header_segment}.{payload_segment}"
    expected_signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()

    try:
        provided_signature = _base64url_decode(signature_segment)
    except ValueError as exc:
        raise ValueError("invalid token signature") from exc

    if not hmac.compare_digest(provided_signature, expected_signature):
        raise ValueError("invalid token signature")

    header = _base64url_json_decode(header_segment)
    payload = _base64url_json_decode(payload_segment)
    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise ValueError("invalid token header")
    if payload.get("typ") != "access":
        raise ValueError("invalid token type")

    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at <= int(now_utc().timestamp()):
        raise ValueError("expired token")

    return payload


def _base64url_json(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _base64url(raw)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid base64url value") from exc


def _base64url_json_decode(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(_base64url_decode(value))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("invalid json segment") from exc
    if not isinstance(decoded, dict):
        raise ValueError("invalid json object")
    return decoded

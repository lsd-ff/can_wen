from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from app.config import get_settings


settings = get_settings()


def now_utc() -> datetime:
    return datetime.now(UTC)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + _b64(salt) + "$" + _b64(derived)


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, salt_text, expected_text = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(password.encode("utf-8"), salt=_b64_decode(salt_text), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(derived, _b64_decode(expected_text))
    except (ValueError, TypeError):
        return False


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hmac.new(settings.auth_secret_key.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def create_access_token(*, account_id: str, session_id: str, permissions_version: int = 1) -> tuple[str, int]:
    expires_in = settings.access_token_ttl_seconds
    issued_at = now_utc()
    payload = {
        "sub": account_id,
        "sid": session_id,
        "aud": "canw-admin",
        "typ": "access",
        "pv": permissions_version,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(seconds=expires_in)).timestamp()),
    }
    return _jwt_encode(payload), expires_in


def create_mfa_ticket(*, account_id: str, purpose: str) -> str:
    issued_at = now_utc()
    return _jwt_encode(
        {
            "sub": account_id,
            "aud": "canw-admin",
            "typ": "mfa-ticket",
            "purpose": purpose,
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + timedelta(seconds=settings.mfa_ticket_ttl_seconds)).timestamp()),
        }
    )


def decode_token(token: str, *, expected_type: str) -> dict:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
        signing_input = f"{header_segment}.{payload_segment}"
        expected_signature = hmac.new(settings.auth_secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected_signature, _b64_decode(signature_segment)):
            raise ValueError("invalid signature")
        header = _json_b64_decode(header_segment)
        payload = _json_b64_decode(payload_segment)
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise ValueError("invalid header")
        if payload.get("aud") != "canw-admin" or payload.get("typ") != expected_type:
            raise ValueError("invalid token type")
        if not isinstance(payload.get("exp"), int) or payload["exp"] <= int(now_utc().timestamp()):
            raise ValueError("expired token")
        return payload
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("invalid administrator token") from exc


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def build_totp_uri(*, email: str, secret: str) -> str:
    issuer = "CanW 管理后台"
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}&period=30&digits=6"


def verify_totp(secret: str, code: str, *, valid_window: int = 1) -> bool:
    normalized = "".join(character for character in code if character.isdigit())
    if len(normalized) != 6:
        return False
    try:
        current_counter = int(now_utc().timestamp()) // 30
        for counter in range(current_counter - valid_window, current_counter + valid_window + 1):
            if hmac.compare_digest(_totp_code(secret, counter), normalized):
                return True
    except (ValueError, TypeError):
        return False
    return False


def encrypt_secret(value: str) -> str:
    nonce = secrets.token_bytes(16)
    raw = value.encode("utf-8")
    ciphertext = _xor_stream(raw, nonce)
    tag = hmac.new(_encryption_key(), nonce + ciphertext, hashlib.sha256).digest()
    return _b64(nonce + tag + ciphertext)


def decrypt_secret(value: str) -> str:
    raw = _b64_decode(value)
    if len(raw) < 48:
        raise ValueError("invalid encrypted value")
    nonce, tag, ciphertext = raw[:16], raw[16:48], raw[48:]
    expected = hmac.new(_encryption_key(), nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("invalid encrypted value")
    return _xor_stream(ciphertext, nonce).decode("utf-8")


def _jwt_encode(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_segment = _json_b64(header)
    payload_segment = _json_b64(payload)
    signing_input = f"{header_segment}.{payload_segment}"
    signature = hmac.new(settings.auth_secret_key.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(signature)}"


def _totp_code(secret: str, counter: int) -> str:
    padded_secret = secret.upper() + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded_secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{number:06d}"


def _encryption_key() -> bytes:
    return hashlib.sha256(settings.encryption_key.encode("utf-8")).digest()


def _xor_stream(value: bytes, nonce: bytes) -> bytes:
    output = bytearray()
    counter = 0
    while len(output) < len(value):
        block = hashlib.sha256(_encryption_key() + nonce + counter.to_bytes(4, "big")).digest()
        output.extend(block)
        counter += 1
    return bytes(left ^ right for left, right in zip(value, output, strict=False))


def _json_b64(value: dict) -> str:
    return _b64(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _json_b64_decode(value: str) -> dict:
    decoded = json.loads(_b64_decode(value))
    if not isinstance(decoded, dict):
        raise ValueError("invalid JSON object")
    return decoded


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode((value + "=" * (-len(value) % 4)).encode("ascii"))

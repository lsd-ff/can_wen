from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from uuid import UUID
from urllib.parse import urlparse

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import now_utc
from app.models import LLMModelConfig, User
from app.schemas.model_configs import (
    ModelConfigCreateRequest,
    ModelConfigResponse,
    ModelConfigTestResponse,
    ModelConfigUpdateRequest,
)
from app.services.llm_client import (
    LLMConfigurationError,
    LLMProviderError,
    OpenAICompatibleModelConfig,
    request_openai_compatible_reply,
)


def list_current_user_model_configs(db: Session, *, user: User) -> list[ModelConfigResponse]:
    configs = db.scalars(
        select(LLMModelConfig)
        .where(LLMModelConfig.user_id == user.id, LLMModelConfig.deleted_at.is_(None))
        .order_by(desc(LLMModelConfig.is_default), desc(LLMModelConfig.created_at))
    ).all()
    return [_model_config_response(config) for config in configs]


def create_current_user_model_config(
    db: Session,
    *,
    user: User,
    settings: Settings,
    payload: ModelConfigCreateRequest,
) -> ModelConfigResponse:
    _validate_api_request_url(payload.api_request_url)
    should_be_default = payload.is_default or _current_user_config_count(db, user=user) == 0
    if should_be_default:
        _clear_default_model_config(db, user=user)

    config = LLMModelConfig(
        user_id=user.id,
        provider_name=payload.provider_name.strip(),
        model_id=payload.model_id.strip(),
        api_key_ciphertext=_encrypt_secret(payload.api_key.strip(), settings=settings),
        api_request_url=payload.api_request_url.strip().rstrip("/"),
        is_enabled=payload.is_enabled,
        is_default=should_be_default,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return _model_config_response(config)


def update_current_user_model_config(
    db: Session,
    *,
    user: User,
    settings: Settings,
    model_config_id: UUID,
    payload: ModelConfigUpdateRequest,
) -> ModelConfigResponse:
    config = _get_current_user_model_config(db, user=user, model_config_id=model_config_id)

    if payload.provider_name is not None:
        config.provider_name = payload.provider_name.strip()
    if payload.model_id is not None:
        config.model_id = payload.model_id.strip()
    if payload.api_request_url is not None:
        _validate_api_request_url(payload.api_request_url)
        config.api_request_url = payload.api_request_url.strip().rstrip("/")
    if payload.api_key is not None and payload.api_key.strip():
        config.api_key_ciphertext = _encrypt_secret(payload.api_key.strip(), settings=settings)
    if payload.is_enabled is not None:
        config.is_enabled = payload.is_enabled
        if not payload.is_enabled:
            config.is_default = False
    if payload.is_default is True:
        _clear_default_model_config(db, user=user)
        config.is_default = True
        config.is_enabled = True
    elif payload.is_default is False:
        config.is_default = False

    db.add(config)
    db.flush()
    _ensure_current_user_has_default(db, user=user)
    db.commit()
    db.refresh(config)
    return _model_config_response(config)


def delete_current_user_model_config(db: Session, *, user: User, model_config_id: UUID) -> None:
    config = _get_current_user_model_config(db, user=user, model_config_id=model_config_id)
    config.deleted_at = now_utc()
    config.is_enabled = False
    config.is_default = False
    db.add(config)
    db.flush()
    _ensure_current_user_has_default(db, user=user)
    db.commit()


def set_current_user_default_model_config(
    db: Session,
    *,
    user: User,
    model_config_id: UUID,
) -> ModelConfigResponse:
    config = _get_current_user_model_config(db, user=user, model_config_id=model_config_id)
    _clear_default_model_config(db, user=user)
    config.is_enabled = True
    config.is_default = True
    db.add(config)
    db.commit()
    db.refresh(config)
    return _model_config_response(config)


def test_current_user_model_config(
    db: Session,
    *,
    user: User,
    settings: Settings,
    model_config_id: UUID,
) -> ModelConfigTestResponse:
    config = _get_current_user_model_config(db, user=user, model_config_id=model_config_id)
    tested_at = now_utc()

    try:
        request_openai_compatible_reply(
            _openai_compatible_config_from_record(config, settings=settings),
            messages=[{"role": "user", "content": "请只回复 pong"}],
            timeout_seconds=settings.openai_timeout_seconds,
        )
    except (LLMConfigurationError, LLMProviderError) as error:
        config.last_test_status = "failed"
        config.last_test_message = str(error)
    else:
        config.last_test_status = "success"
        config.last_test_message = "Connectivity test succeeded"

    config.last_test_at = tested_at
    db.add(config)
    db.commit()

    return ModelConfigTestResponse(
        id=config.id,
        status=config.last_test_status,
        message=config.last_test_message or "",
        tested_at=tested_at,
    )


def resolve_current_user_llm_config(
    db: Session,
    *,
    user: User,
    settings: Settings,
    model_config_id: UUID | None,
) -> OpenAICompatibleModelConfig:
    config: LLMModelConfig | None = None
    if model_config_id is not None:
        config = _get_current_user_model_config(db, user=user, model_config_id=model_config_id)
        if not config.is_enabled:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Selected model config is disabled")
    else:
        config = db.scalar(
            select(LLMModelConfig)
            .where(
                LLMModelConfig.user_id == user.id,
                LLMModelConfig.deleted_at.is_(None),
                LLMModelConfig.is_enabled.is_(True),
                LLMModelConfig.is_default.is_(True),
            )
            .order_by(desc(LLMModelConfig.created_at))
        )
        if config is None:
            config = db.scalar(
                select(LLMModelConfig)
                .where(
                    LLMModelConfig.user_id == user.id,
                    LLMModelConfig.deleted_at.is_(None),
                    LLMModelConfig.is_enabled.is_(True),
                )
                .order_by(desc(LLMModelConfig.created_at))
            )

    if config is not None:
        return _openai_compatible_config_from_record(config, settings=settings)

    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        raise LLMConfigurationError("Large model API key is not configured")
    return OpenAICompatibleModelConfig(
        provider_name="Environment",
        model_id=settings.openai_model_id,
        api_key=api_key,
        api_request_url=settings.openai_base_url,
    )


def _get_current_user_model_config(db: Session, *, user: User, model_config_id: UUID) -> LLMModelConfig:
    config = db.scalar(
        select(LLMModelConfig).where(
            LLMModelConfig.id == model_config_id,
            LLMModelConfig.user_id == user.id,
            LLMModelConfig.deleted_at.is_(None),
        )
    )
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model config does not exist")
    return config


def _current_user_config_count(db: Session, *, user: User) -> int:
    configs = db.scalars(
        select(LLMModelConfig.id).where(LLMModelConfig.user_id == user.id, LLMModelConfig.deleted_at.is_(None))
    ).all()
    return len(configs)


def _clear_default_model_config(db: Session, *, user: User) -> None:
    configs = db.scalars(
        select(LLMModelConfig).where(
            LLMModelConfig.user_id == user.id,
            LLMModelConfig.deleted_at.is_(None),
            LLMModelConfig.is_default.is_(True),
        )
    ).all()
    for config in configs:
        config.is_default = False
        db.add(config)


def _ensure_current_user_has_default(db: Session, *, user: User) -> None:
    default_config = db.scalar(
        select(LLMModelConfig).where(
            LLMModelConfig.user_id == user.id,
            LLMModelConfig.deleted_at.is_(None),
            LLMModelConfig.is_enabled.is_(True),
            LLMModelConfig.is_default.is_(True),
        )
    )
    if default_config is not None:
        return

    fallback_config = db.scalar(
        select(LLMModelConfig)
        .where(
            LLMModelConfig.user_id == user.id,
            LLMModelConfig.deleted_at.is_(None),
            LLMModelConfig.is_enabled.is_(True),
        )
        .order_by(desc(LLMModelConfig.created_at))
    )
    if fallback_config is not None:
        fallback_config.is_default = True
        db.add(fallback_config)


def _openai_compatible_config_from_record(
    config: LLMModelConfig,
    *,
    settings: Settings,
) -> OpenAICompatibleModelConfig:
    return OpenAICompatibleModelConfig(
        provider_name=config.provider_name,
        model_id=config.model_id,
        api_key=_decrypt_secret(config.api_key_ciphertext, settings=settings),
        api_request_url=config.api_request_url,
        config_id=config.id,
    )


def _model_config_response(config: LLMModelConfig) -> ModelConfigResponse:
    return ModelConfigResponse(
        id=config.id,
        provider_name=config.provider_name,
        model_id=config.model_id,
        api_request_url=config.api_request_url,
        is_enabled=config.is_enabled,
        is_default=config.is_default,
        has_api_key=bool(config.api_key_ciphertext),
        last_test_status=config.last_test_status,
        last_test_message=config.last_test_message,
        last_test_at=config.last_test_at,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _validate_api_request_url(value: str) -> None:
    parsed_url = urlparse(value.strip())
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="API request URL must be http(s)")


def _encrypt_secret(value: str, *, settings: Settings) -> str:
    key = _secret_key(settings)
    nonce = secrets.token_bytes(12)
    plaintext = value.encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, b"canw-model-config/v2")
    return "v2:" + ":".join(_b64(part) for part in (nonce, ciphertext))


def _decrypt_secret(value: str, *, settings: Settings) -> str:
    if value.startswith("v2:"):
        try:
            version, nonce_b64, ciphertext_b64 = value.split(":", 2)
            if version != "v2":
                raise ValueError("unsupported version")
            nonce = _unb64(nonce_b64)
            ciphertext = _unb64(ciphertext_b64)
            plaintext = AESGCM(_secret_key(settings)).decrypt(nonce, ciphertext, b"canw-model-config/v2")
            return plaintext.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise LLMConfigurationError("Stored API key cannot be decoded") from error
        except Exception as error:
            raise LLMConfigurationError("Stored API key failed integrity check") from error
    return _decrypt_legacy_v1_secret(value, settings=settings)


def _decrypt_legacy_v1_secret(value: str, *, settings: Settings) -> str:
    """Read old v1 records during the one-way upgrade to authenticated AES-GCM."""
    try:
        version, nonce_b64, cipher_b64, tag_b64 = value.split(":", 3)
        if version != "v1":
            raise ValueError("unsupported version")
        nonce = _unb64(nonce_b64)
        cipher = _unb64(cipher_b64)
        tag = _unb64(tag_b64)
    except ValueError as error:
        raise LLMConfigurationError("Stored API key cannot be decoded") from error

    key = _secret_key(settings)
    expected_tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected_tag):
        raise LLMConfigurationError("Stored API key failed integrity check")
    plaintext = _xor_bytes(cipher, _key_stream(key, nonce, len(cipher)))
    return plaintext.decode("utf-8")


def _secret_key(settings: Settings) -> bytes:
    return hashlib.sha256(settings.auth_secret_key.encode("utf-8")).digest()


def _key_stream(key: bytes, nonce: bytes, length: int) -> bytes:
    chunks: list[bytes] = []
    counter = 0
    while sum(len(chunk) for chunk in chunks) < length:
        counter_bytes = counter.to_bytes(8, "big")
        chunks.append(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return b"".join(chunks)[:length]


def _xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(left_byte ^ right_byte for left_byte, right_byte in zip(left, right))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)

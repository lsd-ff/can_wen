from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.llm_client import LLMConfigurationError
from app.services.model_config_service import _decrypt_secret, _encrypt_secret


def test_model_config_secret_uses_authenticated_aes_gcm() -> None:
    settings = Settings(auth_secret_key="test-only-model-config-secret")

    ciphertext = _encrypt_secret("sk-secret-value", settings=settings)

    assert ciphertext.startswith("v2:")
    assert "sk-secret-value" not in ciphertext
    assert _decrypt_secret(ciphertext, settings=settings) == "sk-secret-value"


def test_model_config_secret_rejects_tampering() -> None:
    settings = Settings(auth_secret_key="test-only-model-config-secret")
    ciphertext = _encrypt_secret("sk-secret-value", settings=settings)
    version, nonce, encrypted_value = ciphertext.split(":", 2)
    tampered = f"{version}:{nonce}:{'A' if encrypted_value[0] != 'A' else 'B'}{encrypted_value[1:]}"

    with pytest.raises(LLMConfigurationError):
        _decrypt_secret(tampered, settings=settings)

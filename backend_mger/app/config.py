from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CANW_ADMIN_", extra="ignore")

    app_name: str = "CanW 管理员服务"
    api_prefix: str = "/api/admin/v1"
    database_url: str = "postgresql+psycopg://canwen:canwen123@127.0.0.1:5432/can_wen"
    database_echo: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:5175"])
    auth_secret_key: str = "change-me-admin-auth-secret"
    encryption_key: str = "change-me-admin-encryption-key"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_days: int = 7
    mfa_ticket_ttl_seconds: int = 300
    sensitive_access_ttl_seconds: int = 900
    user_api_health_url: str = "http://127.0.0.1:8010/healthz"
    object_storage_health_url: str | None = None
    service_probe_timeout_seconds: float = 3.0
    auto_create_schema: bool = True
    bootstrap_email: str | None = None
    bootstrap_password: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()

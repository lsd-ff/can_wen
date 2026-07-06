from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Can Wen API"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
    debug: bool = False
    database_url: str = "postgresql+psycopg://canwen:canwen123@127.0.0.1:5432/can_wen"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    auth_secret_key: str = "change-me-in-production"
    auth_code_ttl_seconds: int = 300
    auth_code_resend_cooldown_seconds: int = 60
    auth_code_hourly_limit: int = 10
    auth_code_length: int = 6
    auth_access_token_ttl_seconds: int = 1800
    auth_refresh_token_ttl_days: int = 30
    auth_dev_code_enabled: bool = True
    allowed_email_domains: list[str] = [
        "qq.com",
        "vip.qq.com",
        "foxmail.com",
        "163.com",
        "126.com",
        "yeah.net",
        "188.com",
        "vip.163.com",
        "vip.126.com",
    ]
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_use_ssl: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CAN_WEN_",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

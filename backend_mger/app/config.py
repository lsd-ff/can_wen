from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
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

    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str = "redis://127.0.0.1:6379/0"
    celery_result_backend: str = "redis://127.0.0.1:6379/1"
    celery_task_always_eager: bool = False

    knowledge_storage_backend: str = "local"
    knowledge_storage_root: Path = Path("var/knowledge")
    knowledge_upload_max_bytes: int = 200 * 1024 * 1024
    knowledge_chunk_target_tokens: int = 1200
    knowledge_auto_publish_score: float = 0.9
    knowledge_max_reflection_rounds: int = 2

    storage_endpoint_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CANW_ADMIN_STORAGE_ENDPOINT_URL", "CAN_WEN_STORAGE_ENDPOINT_URL"),
    )
    storage_access_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CANW_ADMIN_STORAGE_ACCESS_KEY_ID", "CAN_WEN_STORAGE_ACCESS_KEY_ID"),
    )
    storage_secret_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CANW_ADMIN_STORAGE_SECRET_ACCESS_KEY", "CAN_WEN_STORAGE_SECRET_ACCESS_KEY"),
    )
    storage_bucket: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CANW_ADMIN_STORAGE_BUCKET", "CAN_WEN_STORAGE_BUCKET"),
    )
    storage_region: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CANW_ADMIN_STORAGE_REGION", "CAN_WEN_STORAGE_REGION"),
    )

    mineru_base_url: str = "https://mineru.net/api/v4"
    mineru_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MINERU_TOKEN", "CANW_ADMIN_MINERU_TOKEN"),
    )
    mineru_model_version: str = "vlm"
    mineru_poll_initial_seconds: float = 5.0
    mineru_poll_max_seconds: float = 30.0
    mineru_timeout_seconds: float = 1800.0

    dashscope_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DASHSCOPE_API_KEY", "CANW_ADMIN_DASHSCOPE_API_KEY"),
    )
    dashscope_chat_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_rerank_base_url: str = "https://dashscope.aliyuncs.com/compatible-api/v1"
    qa_model_id: str = "qwen3.7-plus-2026-05-26"
    kg_model_id: str = "qwen3.7-plus-2026-05-26"
    expert_model_id: str = "qwen3.7-max-2026-06-08"
    embedding_model_id: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    rerank_model_id: str = "qwen3-rerank"
    model_request_timeout_seconds: float = 120.0

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "silkworm_qa_v1"
    opensearch_url: str = "http://127.0.0.1:9200"
    opensearch_username: str | None = None
    opensearch_password: str | None = None
    opensearch_index: str = "silkworm_qa_v1"
    # Neo4j is intentionally environment-only. The project uses the configured
    # Aura instance as its sole business graph and must never fall back to a
    # local Bolt endpoint when an environment file is missing.
    neo4j_uri: str = ""
    neo4j_user: str = ""
    neo4j_password: str = ""
    neo4j_database: str = ""

    def require_neo4j_aura(self) -> None:
        if not all((self.neo4j_uri, self.neo4j_user, self.neo4j_password, self.neo4j_database)):
            raise RuntimeError("Neo4j Aura 配置不完整")
        if not self.neo4j_uri.lower().startswith("neo4j+s://"):
            raise RuntimeError("Neo4j 仅允许使用 neo4j+s:// Aura 连接")


@lru_cache
def get_settings() -> Settings:
    return Settings()

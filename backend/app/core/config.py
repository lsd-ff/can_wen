from functools import lru_cache

from pydantic import AliasChoices, Field
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
    api_rate_limit_requests_per_minute: int = 300
    auth_rate_limit_requests_per_minute: int = 60
    security_headers_enabled: bool = True
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
    storage_endpoint_url: str | None = None
    storage_access_key_id: str | None = None
    storage_secret_access_key: str | None = None
    storage_bucket: str | None = None
    storage_region: str | None = None
    storage_public_base_url: str | None = None
    avatar_upload_max_bytes: int = 2 * 1024 * 1024
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CAN_WEN_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("CAN_WEN_OPENAI_BASE_URL", "OPENAI_BASE_URL"),
    )
    openai_model_id: str = Field(
        default="gpt-5-nano",
        validation_alias=AliasChoices("CAN_WEN_OPENAI_MODEL_ID", "MODEL_ID"),
    )
    openai_transcription_model_id: str = Field(
        default="whisper-1",
        validation_alias=AliasChoices("CAN_WEN_OPENAI_TRANSCRIPTION_MODEL_ID", "OPENAI_TRANSCRIPTION_MODEL_ID"),
    )
    openai_timeout_seconds: float = Field(
        default=60.0,
        validation_alias=AliasChoices("CAN_WEN_OPENAI_TIMEOUT_SECONDS", "OPENAI_TIMEOUT_SECONDS"),
    )
    diagnosis_agent_enabled: bool = True
    diagnosis_agent_max_retrieval_rounds: int = Field(default=2, ge=1, le=3)
    diagnosis_agent_dense_top_k: int = Field(default=30, ge=1, le=100)
    diagnosis_agent_bm25_top_k: int = Field(default=30, ge=1, le=100)
    diagnosis_agent_fusion_top_k: int = Field(default=20, ge=2, le=100)
    diagnosis_agent_final_evidence_limit: int = Field(default=8, ge=2, le=30)
    knowledge_model_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CAN_WEN_KNOWLEDGE_MODEL_API_KEY", "DASHSCOPE_API_KEY"),
    )
    knowledge_embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-api/v1"
    knowledge_embedding_model_id: str = "text-embedding-v4"
    knowledge_embedding_dimensions: int = Field(default=1024, ge=1, le=8192)
    knowledge_rerank_base_url: str = "https://dashscope.aliyuncs.com/compatible-api/v1"
    knowledge_rerank_model_id: str = "qwen3-rerank"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "silkworm_qa_v1"
    opensearch_url: str = "http://127.0.0.1:9200"
    opensearch_username: str | None = None
    opensearch_password: str | None = None
    opensearch_index: str = "silkworm_qa_v1"
    neo4j_uri: str = ""
    neo4j_user: str = ""
    neo4j_password: str = ""
    neo4j_database: str = ""
    voice_transcription_max_bytes: int = Field(
        default=20 * 1024 * 1024,
        validation_alias=AliasChoices("CAN_WEN_VOICE_TRANSCRIPTION_MAX_BYTES", "VOICE_TRANSCRIPTION_MAX_BYTES"),
    )
    multimodal_attachment_max_bytes: int = Field(
        default=80 * 1024 * 1024,
        validation_alias=AliasChoices("CAN_WEN_MULTIMODAL_ATTACHMENT_MAX_BYTES", "MULTIMODAL_ATTACHMENT_MAX_BYTES"),
    )
    multimodal_attachment_max_count: int = Field(
        default=6,
        validation_alias=AliasChoices("CAN_WEN_MULTIMODAL_ATTACHMENT_MAX_COUNT", "MULTIMODAL_ATTACHMENT_MAX_COUNT"),
    )
    public_frontend_base_url: str = Field(
        default="http://127.0.0.1:5174",
        validation_alias=AliasChoices("CAN_WEN_PUBLIC_FRONTEND_BASE_URL", "PUBLIC_FRONTEND_BASE_URL"),
    )

    def require_neo4j_aura(self) -> None:
        if not all((self.neo4j_uri, self.neo4j_user, self.neo4j_password, self.neo4j_database)):
            raise RuntimeError("Neo4j Aura 连接配置未完成")
        if not self.neo4j_uri.lower().startswith("neo4j+s://"):
            raise RuntimeError("用户端 KG 检索仅允许连接 Neo4j Aura")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CAN_WEN_",
        case_sensitive=False,
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import SystemModelConfig
from app.security import encrypt_secret


def seed_knowledge_model_configs(db: Session, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    defaults = (
        ("qa-extract", "QA 抽取模型", settings.qa_model_id, settings.dashscope_chat_base_url, "chat"),
        ("kg-extract", "KG 抽取模型", settings.kg_model_id, settings.dashscope_chat_base_url, "chat"),
        ("expert-review", "知识专家评审模型", settings.expert_model_id, settings.dashscope_chat_base_url, "chat"),
        ("embedding-primary", "知识库 Embedding", settings.embedding_model_id, settings.dashscope_chat_base_url, "embedding"),
        ("rerank-primary", "知识库 Rerank", settings.rerank_model_id, settings.dashscope_rerank_base_url, "rerank"),
    )
    for key, label, model_id, base_url, capability in defaults:
        item = db.scalar(select(SystemModelConfig).where(SystemModelConfig.key == key))
        if item is not None:
            continue
        db.add(
            SystemModelConfig(
                key=key,
                label=label,
                model_id=model_id,
                api_base_url=base_url,
                api_key_ciphertext=encrypt_secret(settings.dashscope_api_key) if settings.dashscope_api_key else None,
                capability=capability,
                enabled=True,
            )
        )
    db.commit()

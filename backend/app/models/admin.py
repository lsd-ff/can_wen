from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExpertReview(Base):
    """Administrator-authored assessment published back into a diagnosis or husbandry case."""

    __tablename__ = "expert_reviews"
    __table_args__ = (
        CheckConstraint("risk_level IN ('low', 'medium', 'high', 'critical')", name="expert_reviews_risk_allowed"),
        CheckConstraint("status IN ('draft', 'published', 'superseded')", name="expert_reviews_status_allowed"),
        Index("idx_expert_reviews_case_status", "husbandry_case_id", "status", text("published_at DESC")),
        Index("idx_expert_reviews_conversation_status", "conversation_id", "status", text("published_at DESC")),
        Index(
            "uq_expert_reviews_husbandry_case_version",
            "husbandry_case_id",
            "version",
            unique=True,
            postgresql_where=text("husbandry_case_id IS NOT NULL"),
        ),
        {"schema": "admin"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("diagnoses.id", ondelete="SET NULL"), nullable=True)
    husbandry_case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("husbandry_cases.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reviewer_name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(Text, nullable=False, default="medium", server_default=text("'medium'"))
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft", server_default=text("'draft'"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

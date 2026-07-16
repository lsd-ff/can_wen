from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Farm(Base):
    __tablename__ = "farms"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="farms_status_allowed"),
        Index("idx_farms_owner_status_created", "owner_id", "status", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SilkwormBatch(Base):
    __tablename__ = "silkworm_batches"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'finished', 'archived')", name="silkworm_batches_status_allowed"),
        CheckConstraint("population_count IS NULL OR population_count >= 0", name="silkworm_batches_population_nonnegative"),
        Index("idx_silkworm_batches_farm_status_created", "farm_id", "status", text("created_at DESC")),
        Index("idx_silkworm_batches_project_status", "project_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    batch_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    variety: Mapped[str | None] = mapped_column(Text, nullable=True)
    instar: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_cocooning_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    population_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    environment_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class HusbandryDailyRecord(Base):
    __tablename__ = "husbandry_daily_records"
    __table_args__ = (
        CheckConstraint("temperature_celsius IS NULL OR (temperature_celsius >= -30 AND temperature_celsius <= 80)", name="husbandry_daily_records_temperature_range"),
        CheckConstraint("humidity_percent IS NULL OR (humidity_percent >= 0 AND humidity_percent <= 100)", name="husbandry_daily_records_humidity_range"),
        CheckConstraint("feedings IS NULL OR feedings >= 0", name="husbandry_daily_records_feedings_nonnegative"),
        CheckConstraint("leaf_amount_kg IS NULL OR leaf_amount_kg >= 0", name="husbandry_daily_records_leaf_amount_nonnegative"),
        CheckConstraint("sick_count IS NULL OR sick_count >= 0", name="husbandry_daily_records_sick_nonnegative"),
        CheckConstraint("death_count IS NULL OR death_count >= 0", name="husbandry_daily_records_death_nonnegative"),
        UniqueConstraint("batch_id", "record_date", name="uq_husbandry_daily_records_batch_date"),
        Index("idx_husbandry_daily_records_batch_date", "batch_id", text("record_date DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("silkworm_batches.id", ondelete="CASCADE"), nullable=False)
    record_date: Mapped[date] = mapped_column(Date, nullable=False)
    temperature_celsius: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    humidity_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    feedings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    leaf_amount_kg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    sick_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    death_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    management_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class HusbandryCase(Base):
    __tablename__ = "husbandry_cases"
    __table_args__ = (
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name="husbandry_cases_severity_allowed"),
        CheckConstraint("status IN ('needs_more_info', 'suspected', 'processing', 'closed')", name="husbandry_cases_status_allowed"),
        Index("idx_husbandry_cases_owner_status_created", "owner_id", "status", text("created_at DESC")),
        Index("idx_husbandry_cases_batch_status_occurred", "batch_id", "status", text("occurred_on DESC")),
        Index("idx_husbandry_cases_conversation", "source_conversation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    farm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("farms.id", ondelete="RESTRICT"), nullable=False)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("silkworm_batches.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    symptom_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    suspected_disease: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False, default="medium", server_default=text("'medium'"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="needs_more_info", server_default=text("'needs_more_info'"))
    diagnosis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HusbandryCaseFollowUp(Base):
    __tablename__ = "husbandry_case_follow_ups"
    __table_args__ = (
        CheckConstraint("affected_count IS NULL OR affected_count >= 0", name="husbandry_case_follow_ups_affected_nonnegative"),
        CheckConstraint("death_count IS NULL OR death_count >= 0", name="husbandry_case_follow_ups_death_nonnegative"),
        Index("idx_husbandry_case_follow_ups_case_observed", "case_id", text("observed_on DESC")),
        Index("idx_husbandry_case_follow_ups_next_follow_up", "next_follow_up_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("husbandry_cases.id", ondelete="CASCADE"), nullable=False)
    observed_on: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    death_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class HusbandryRecordAsset(Base):
    __tablename__ = "husbandry_record_assets"
    __table_args__ = (
        CheckConstraint(
            "(daily_record_id IS NOT NULL AND case_id IS NULL) OR (daily_record_id IS NULL AND case_id IS NOT NULL)",
            name="husbandry_record_assets_single_owner",
        ),
        UniqueConstraint("daily_record_id", "file_id", name="uq_husbandry_daily_record_assets_file"),
        UniqueConstraint("case_id", "file_id", name="uq_husbandry_case_assets_file"),
        Index("idx_husbandry_record_assets_daily", "daily_record_id", text("created_at ASC")),
        Index("idx_husbandry_record_assets_case", "case_id", text("created_at ASC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    daily_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("husbandry_daily_records.id", ondelete="CASCADE"), nullable=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("husbandry_cases.id", ondelete="CASCADE"), nullable=True)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

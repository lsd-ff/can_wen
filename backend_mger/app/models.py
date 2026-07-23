from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


ADMIN_SCHEMA = "admin"


class Base(DeclarativeBase):
    pass


class AdminAccount(Base):
    __tablename__ = "admin_accounts"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'active', 'disabled', 'locked')", name="admin_accounts_status_allowed"),
        Index("idx_admin_accounts_status_email", "status", "email"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default=text("'pending'"))
    mfa_enrolled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AdminRole(Base):
    __tablename__ = "roles"
    __table_args__ = ({"schema": ADMIN_SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AdminPermission(Base):
    __tablename__ = "permissions"
    __table_args__ = ({"schema": ADMIN_SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    group_key: Mapped[str] = mapped_column(Text, nullable=False)


class AdminAccountRole(Base):
    __tablename__ = "admin_account_roles"
    __table_args__ = (UniqueConstraint("admin_account_id", "role_id", name="uq_admin_account_roles_pair"), {"schema": ADMIN_SCHEMA})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    admin_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.admin_accounts.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.roles.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AdminRolePermission(Base):
    __tablename__ = "admin_role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_admin_role_permissions_pair"), {"schema": ADMIN_SCHEMA})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.roles.id", ondelete="CASCADE"), nullable=False)
    permission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.permissions.id", ondelete="CASCADE"), nullable=False)


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked', 'expired')", name="admin_sessions_status_allowed"),
        Index("idx_admin_sessions_account_status", "admin_account_id", "status"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    admin_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.admin_accounts.id", ondelete="CASCADE"), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default=text("'active'"))
    device_name: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AdminMfaFactor(Base):
    __tablename__ = "admin_mfa_factors"
    __table_args__ = (UniqueConstraint("admin_account_id", "factor_type", name="uq_admin_mfa_factor_type"), {"schema": ADMIN_SCHEMA})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    admin_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.admin_accounts.id", ondelete="CASCADE"), nullable=False)
    factor_type: Mapped[str] = mapped_column(Text, nullable=False, default="totp", server_default=text("'totp'"))
    secret_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AdminInvite(Base):
    __tablename__ = "admin_invites"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'accepted', 'revoked', 'expired')", name="admin_invites_status_allowed"),
        Index("idx_admin_invites_email_status", "email", "status"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    role_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default=text("'pending'"))
    invited_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'claimed', 'completed', 'cancelled')", name="work_items_status_allowed"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name="work_items_priority_allowed"),
        Index("idx_work_items_queue", "status", "priority", "due_at"),
        Index(
            "uq_work_items_active_resource",
            "resource_type",
            "resource_id",
            unique=True,
            postgresql_where=text("status IN ('open', 'claimed')"),
        ),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    item_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False, default="medium", server_default=text("'medium'"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default=text("'open'"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SensitiveAccessGrant(Base):
    __tablename__ = "sensitive_access_grants"
    __table_args__ = (Index("idx_sensitive_access_grants_lookup", "admin_account_id", "resource_type", "resource_id", "expires_at"), {"schema": ADMIN_SCHEMA})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    admin_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RiskIncident(Base):
    """A deduplicated administrator-facing risk event with its handling state."""

    __tablename__ = "risk_incidents"
    __table_args__ = (
        CheckConstraint("risk_level IN ('low', 'medium', 'high', 'critical')", name="risk_incidents_level_allowed"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name="risk_incidents_priority_allowed"),
        CheckConstraint("status IN ('open', 'acknowledged', 'in_progress', 'resolved', 'dismissed', 'suppressed')", name="risk_incidents_status_allowed"),
        Index("idx_risk_incidents_queue", "status", "priority", "due_at"),
        Index("idx_risk_incidents_seen", "last_detected_at"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    fingerprint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    risk_type: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default=text("'open'"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suppressed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RiskIncidentActivity(Base):
    __tablename__ = "risk_incident_activities"
    __table_args__ = (Index("idx_risk_incident_activities_timeline", "incident_id", "created_at"), {"schema": ADMIN_SCHEMA})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.risk_incidents.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    activity_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class RiskNotificationReceipt(Base):
    __tablename__ = "risk_notification_receipts"
    __table_args__ = (
        UniqueConstraint("incident_id", "admin_account_id", name="uq_risk_notification_receipts_incident_admin"),
        Index("idx_risk_notification_receipts_admin", "admin_account_id", "read_at"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.risk_incidents.id", ondelete="CASCADE"), nullable=False)
    admin_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.admin_accounts.id", ondelete="CASCADE"), nullable=False)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ModerationAction(Base):
    __tablename__ = "moderation_actions"
    __table_args__ = (Index("idx_moderation_actions_target", "target_type", "target_id", "created_at"), {"schema": ADMIN_SCHEMA})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ServiceHealthSnapshot(Base):
    """An immutable result of a dependency probe used for health trends."""

    __tablename__ = "service_health_snapshots"
    __table_args__ = (
        CheckConstraint("status IN ('healthy', 'degraded', 'failed', 'maintenance', 'unknown')", name="service_health_snapshots_status_allowed"),
        Index("idx_service_health_snapshots_service_checked", "service_key", "checked_at"),
        Index("idx_service_health_snapshots_checked", "checked_at"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    service_key: Mapped[str] = mapped_column(Text, nullable=False)
    service_label: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status_code: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ExpertReview(Base):
    __tablename__ = "expert_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'superseded')", name="expert_reviews_status_allowed"),
        CheckConstraint("risk_level IN ('low', 'medium', 'high', 'critical')", name="expert_reviews_risk_allowed"),
        Index("idx_expert_reviews_conversation_status", "conversation_id", "status", text("published_at DESC")),
        Index("idx_expert_reviews_case_status", "husbandry_case_id", "status", text("published_at DESC")),
        Index(
            "uq_expert_reviews_husbandry_case_version",
            "husbandry_case_id",
            "version",
            unique=True,
            postgresql_where=text("husbandry_case_id IS NOT NULL"),
        ),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    husbandry_case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reviewer_name_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft", server_default=text("'draft'"))
    risk_level: Mapped[str] = mapped_column(Text, nullable=False, default="medium", server_default=text("'medium'"))
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("idx_audit_logs_actor_created", "actor_id", "created_at"), Index("idx_audit_logs_resource", "resource_type", "resource_id", "created_at"), {"schema": ADMIN_SCHEMA})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    before_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    after_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    request_id: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class AdminMetricDaily(Base):
    __tablename__ = "metric_daily"
    __table_args__ = (UniqueConstraint("metric_date", "metric_key", name="uq_admin_metric_daily_key"), {"schema": ADMIN_SCHEMA})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    metric_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))


class SystemModelConfig(Base):
    __tablename__ = "system_model_configs"
    __table_args__ = (
        CheckConstraint("capability IN ('chat', 'vision', 'embedding', 'rerank', 'speech')", name="system_model_configs_capability_allowed"),
        UniqueConstraint("key", name="uq_system_model_configs_key"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    api_base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    capability: Mapped[str] = mapped_column(Text, nullable=False, default="chat", server_default=text("'chat'"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    last_test_status: Mapped[str | None] = mapped_column(Text)
    last_test_message: Mapped[str | None] = mapped_column(Text)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'processing', 'ready', 'failed', 'disabled')", name="knowledge_sources_status_allowed"),
        Index("idx_knowledge_sources_sha256", "content_sha256"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False, default="document", server_default=text("'document'"))
    source_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft", server_default=text("'draft'"))
    version: Mapped[str] = mapped_column(Text, nullable=False, default="v1", server_default=text("'v1'"))
    license_note: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    storage_uri: Mapped[str | None] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(Text)
    published_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="background_jobs_status_allowed"),
        Index("idx_background_jobs_status_created", "status", "created_at"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued", server_default=text("'queued'"))
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class KnowledgeSourceVersion(Base):
    __tablename__ = "knowledge_source_versions"
    __table_args__ = (
        CheckConstraint("status IN ('uploaded', 'parsing', 'parsed', 'failed', 'disabled')", name="knowledge_source_versions_status_allowed"),
        UniqueConstraint("source_id", "version", name="uq_knowledge_source_versions_source_version"),
        Index("idx_knowledge_source_versions_source_created", "source_id", text("created_at DESC")),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_sources.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="uploaded", server_default=text("'uploaded'"))
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    original_storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    markdown_storage_uri: Mapped[str | None] = mapped_column(Text)
    parser: Mapped[str] = mapped_column(Text, nullable=False, default="markdown", server_default=text("'markdown'"))
    parser_task_id: Mapped[str | None] = mapped_column(Text)
    parser_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    heading_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class KnowledgeBuildRun(Base):
    __tablename__ = "knowledge_build_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'awaiting_review', 'publishing', 'succeeded', 'failed', 'cancelled')", name="knowledge_build_runs_status_allowed"),
        Index("idx_knowledge_build_runs_status_created", "status", text("created_at DESC")),
        Index("idx_knowledge_build_runs_version_created", "source_version_id", text("created_at DESC")),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_source_versions.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("admin.background_jobs.id", ondelete="SET NULL"))
    targets: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued", server_default=text("'queued'"))
    current_node: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    graph_thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("build_run_id", "stable_key", name="uq_knowledge_chunks_run_key"),
        Index("idx_knowledge_chunks_version_ordinal", "source_version_id", "ordinal"),
        Index("idx_knowledge_chunks_run_ordinal", "build_run_id", "ordinal"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_source_versions.id", ondelete="CASCADE"), nullable=False)
    build_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_build_runs.id", ondelete="CASCADE"), nullable=False)
    stable_key: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    heading_path: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    heading_level: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default=text("1.0"))
    quality_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    split_strategy: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class KnowledgeQAItem(Base):
    __tablename__ = "knowledge_qa_items"
    __table_args__ = (
        CheckConstraint("review_status IN ('pending', 'needs_review', 'approved', 'rejected', 'published')", name="knowledge_qa_items_review_status_allowed"),
        UniqueConstraint("build_run_id", "question_sha256", name="uq_knowledge_qa_items_run_question"),
        Index("idx_knowledge_qa_items_review_created", "review_status", text("created_at DESC")),
        Index("idx_knowledge_qa_items_chunk", "chunk_id"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    build_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_build_runs.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_chunks.id", ondelete="CASCADE"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    knowledge_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default=text("0.0"))
    rule_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default=text("0.0"))
    expert_score: Mapped[float | None] = mapped_column(Float)
    expert_assessment: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    risk_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    review_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default=text("'pending'"))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qdrant_point_id: Mapped[str | None] = mapped_column(Text)
    opensearch_document_id: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class KnowledgeTriple(Base):
    __tablename__ = "knowledge_triples"
    __table_args__ = (
        CheckConstraint("review_status IN ('pending', 'needs_review', 'approved', 'rejected', 'published')", name="knowledge_triples_review_status_allowed"),
        UniqueConstraint("build_run_id", "triple_key", name="uq_knowledge_triples_run_key"),
        Index("idx_knowledge_triples_review_created", "review_status", text("created_at DESC")),
        Index("idx_knowledge_triples_chunk", "chunk_id"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    build_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_build_runs.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_chunks.id", ondelete="CASCADE"), nullable=False)
    triple_key: Mapped[str] = mapped_column(Text, nullable=False)
    subject_name: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    object_name: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[str] = mapped_column(Text, nullable=False)
    object_canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default=text("0.0"))
    rule_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default=text("0.0"))
    expert_score: Mapped[float | None] = mapped_column(Float)
    expert_assessment: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    risk_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    resolution_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    review_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default=text("'pending'"))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    neo4j_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class KnowledgeReviewItem(Base):
    __tablename__ = "knowledge_review_items"
    __table_args__ = (
        CheckConstraint("item_type IN ('chunk', 'qa', 'triple', 'conflict')", name="knowledge_review_items_type_allowed"),
        CheckConstraint("status IN ('open', 'claimed', 'approved', 'rejected')", name="knowledge_review_items_status_allowed"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name="knowledge_review_items_priority_allowed"),
        Index("idx_knowledge_review_items_queue", "status", "priority", text("created_at ASC")),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    build_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_build_runs.id", ondelete="CASCADE"), nullable=False)
    item_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default=text("'open'"))
    priority: Mapped[str] = mapped_column(Text, nullable=False, default="medium", server_default=text("'medium'"))
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    model_assessment: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class KnowledgeBuildEvent(Base):
    __tablename__ = "knowledge_build_events"
    __table_args__ = (
        CheckConstraint("level IN ('debug', 'info', 'warning', 'error')", name="knowledge_build_events_level_allowed"),
        Index("idx_knowledge_build_events_run_created", "build_run_id", "created_at"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    build_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_build_runs.id", ondelete="CASCADE"), nullable=False)
    node: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(Text, nullable=False, default="info", server_default=text("'info'"))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class KnowledgePublication(Base):
    __tablename__ = "knowledge_publications"
    __table_args__ = (
        CheckConstraint("status IN ('staging', 'published', 'failed', 'rolled_back')", name="knowledge_publications_status_allowed"),
        UniqueConstraint("build_run_id", name="uq_knowledge_publications_run"),
        Index("idx_knowledge_publications_status_created", "status", text("created_at DESC")),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    build_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_build_runs.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="staging", server_default=text("'staging'"))
    qdrant_collection: Mapped[str | None] = mapped_column(Text)
    opensearch_index: Mapped[str | None] = mapped_column(Text)
    neo4j_database: Mapped[str | None] = mapped_column(Text)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    error_message: Mapped[str | None] = mapped_column(Text)
    published_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class KnowledgeSyncOutbox(Base):
    __tablename__ = "knowledge_sync_outbox"
    __table_args__ = (
        CheckConstraint("target IN ('qdrant', 'opensearch', 'neo4j')", name="knowledge_sync_outbox_target_allowed"),
        CheckConstraint("operation IN ('upsert', 'delete')", name="knowledge_sync_outbox_operation_allowed"),
        CheckConstraint("status IN ('pending', 'processing', 'succeeded', 'failed')", name="knowledge_sync_outbox_status_allowed"),
        UniqueConstraint("event_key", name="uq_knowledge_sync_outbox_event_key"),
        Index("idx_knowledge_sync_outbox_pending", "status", "target", "created_at"),
        {"schema": ADMIN_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    build_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("admin.knowledge_build_runs.id", ondelete="CASCADE"), nullable=False)
    event_key: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False, default="upsert", server_default=text("'upsert'"))
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SystemSetting(Base):
    __tablename__ = "system_settings"
    __table_args__ = (UniqueConstraint("key", name="uq_system_settings_key"), {"schema": ADMIN_SCHEMA})

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

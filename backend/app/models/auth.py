from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_settings import UserSettings


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('farmer', 'agritech', 'expert', 'admin')",
            name="users_role_allowed",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled', 'deleted')",
            name="users_status_allowed",
        ),
        {"comment": "用户主表：保存系统内的用户主体，不直接区分手机号、邮箱等登录方式。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="用户 ID，系统内部用户唯一标识。",
    )
    display_name: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default=text("''"),
        comment="用户显示名称，注册初期可为空字符串。",
    )
    username: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default=text("''"),
        comment="用户公开用户名，用于个人资料展示。",
    )
    avatar_url: Mapped[str | None] = mapped_column(Text, comment="用户头像地址。")
    role: Mapped[str] = mapped_column(
        Text,
        default="farmer",
        server_default=text("'farmer'"),
        comment="用户角色：farmer 农户、agritech 农技人员、expert 专家、admin 管理员。",
    )
    status: Mapped[str] = mapped_column(
        Text,
        default="active",
        server_default=text("'active'"),
        comment="用户状态：active 正常、disabled 禁用、deleted 已删除。",
    )
    locale: Mapped[str] = mapped_column(
        Text,
        default="zh-CN",
        server_default=text("'zh-CN'"),
        comment="用户界面语言，默认 zh-CN。",
    )
    timezone: Mapped[str] = mapped_column(
        Text,
        default="Asia/Shanghai",
        server_default=text("'Asia/Shanghai'"),
        comment="用户所在时区，默认 Asia/Shanghai。",
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="用户首次注册时间。",
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="用户最近一次活跃时间。",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录创建时间。",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录最后更新时间。",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="软删除时间，未删除时为空。",
    )

    identities: Mapped[list[UserIdentity]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    login_events: Mapped[list[LoginEvent]] = relationship(back_populates="user")
    settings: Mapped[UserSettings | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('phone', 'email')",
            name="user_identities_provider_allowed",
        ),
        CheckConstraint(
            "provider <> 'phone' OR phone_number IS NOT NULL",
            name="user_identities_phone_required",
        ),
        CheckConstraint(
            "provider <> 'email' OR email IS NOT NULL",
            name="user_identities_email_required",
        ),
        Index(
            "uq_user_identities_active_subject",
            "provider",
            "provider_subject",
            unique=True,
            postgresql_where=text("unbound_at IS NULL"),
        ),
        Index(
            "uq_user_identities_primary_per_provider",
            "user_id",
            "provider",
            unique=True,
            postgresql_where=text("is_primary AND unbound_at IS NULL"),
        ),
        {"comment": "用户登录身份表：保存用户绑定的手机号或邮箱。一个用户可同时绑定手机号和邮箱。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="登录身份 ID。",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        comment="所属用户 ID。",
    )
    provider: Mapped[str] = mapped_column(Text, comment="登录身份类型：phone 手机号、email 邮箱。")
    provider_subject: Mapped[str] = mapped_column(
        Text,
        comment="标准化后的登录账号，用于唯一识别。例如手机号建议存 E.164 格式，邮箱建议存小写格式。",
    )
    phone_country_code: Mapped[str | None] = mapped_column(
        Text,
        comment="手机号国家或地区区号，例如 +86。",
    )
    phone_number: Mapped[str | None] = mapped_column(
        Text,
        comment="手机号，不含或含区号取决于业务标准，建议与 provider_subject 保持可追溯。",
    )
    email: Mapped[str | None] = mapped_column(
        CITEXT,
        comment="邮箱地址，citext 类型表示大小写不敏感。",
    )
    is_primary: Mapped[bool] = mapped_column(
        default=False,
        server_default=text("false"),
        comment="是否为该登录类型下的主身份。",
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="该手机号或邮箱完成验证的时间。",
    )
    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="绑定到用户账号的时间。",
    )
    unbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="解绑时间。为空表示当前仍有效。",
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="扩展信息，预留给来源渠道、运营标记等非核心字段。",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录创建时间。",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录最后更新时间。",
    )

    user: Mapped[User] = relationship(back_populates="identities")
    sessions: Mapped[list[AuthSession]] = relationship(back_populates="identity")
    login_events: Mapped[list[LoginEvent]] = relationship(back_populates="identity")


class AuthVerificationCode(Base):
    __tablename__ = "auth_verification_codes"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('phone', 'email')",
            name="auth_verification_codes_provider_allowed",
        ),
        CheckConstraint(
            "purpose IN ('login', 'bind_identity')",
            name="auth_verification_codes_purpose_allowed",
        ),
        CheckConstraint(
            "status IN ('pending', 'used', 'expired', 'blocked')",
            name="auth_verification_codes_status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="auth_verification_codes_attempt_count_nonnegative"),
        CheckConstraint("max_attempts > 0", name="auth_verification_codes_max_attempts_positive"),
        Index(
            "idx_auth_verification_codes_target",
            "provider",
            "target",
            "purpose",
            "status",
            text("created_at DESC"),
        ),
        Index("idx_auth_verification_codes_expires_at", "expires_at"),
        {"comment": "登录验证码表：保存手机号或邮箱验证码的哈希、有效期、尝试次数和使用状态。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="验证码记录 ID。",
    )
    provider: Mapped[str] = mapped_column(Text, comment="验证码发送渠道：phone 手机短信、email 邮箱。")
    target: Mapped[str] = mapped_column(
        Text,
        comment="验证码接收目标，手机号或邮箱，建议与 user_identities.provider_subject 使用同一标准化规则。",
    )
    code_hash: Mapped[str] = mapped_column(Text, comment="验证码哈希值，只存哈希，不存明文验证码。")
    purpose: Mapped[str] = mapped_column(
        Text,
        default="login",
        server_default=text("'login'"),
        comment="验证码用途：login 登录、bind_identity 绑定手机号或邮箱。",
    )
    status: Mapped[str] = mapped_column(
        Text,
        default="pending",
        server_default=text("'pending'"),
        comment="验证码状态：pending 待验证、used 已使用、expired 已过期、blocked 已锁定。",
    )
    attempt_count: Mapped[int] = mapped_column(
        default=0,
        server_default=text("0"),
        comment="已验证尝试次数。",
    )
    max_attempts: Mapped[int] = mapped_column(
        default=5,
        server_default=text("5"),
        comment="最大允许验证次数，超过后可置为 blocked。",
    )
    request_ip: Mapped[str | None] = mapped_column(INET, comment="请求发送验证码时的 IP 地址。")
    request_user_agent: Mapped[str | None] = mapped_column(
        Text,
        comment="请求发送验证码时的 User-Agent。",
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="验证码实际发送时间。",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        comment="验证码过期时间。",
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="验证码验证成功并被使用的时间。",
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="扩展信息，例如短信服务商返回 ID、邮件模板 ID。",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录创建时间。",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录最后更新时间。",
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'revoked', 'expired')",
            name="auth_sessions_status_allowed",
        ),
        Index("uq_auth_sessions_refresh_token_hash", "refresh_token_hash", unique=True),
        Index("idx_auth_sessions_user_id", "user_id", "status", text("created_at DESC")),
        Index("idx_auth_sessions_expires_at", "expires_at"),
        {"comment": "登录会话表：保存登录成功后的 refresh token 哈希、设备信息、过期和退出状态。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="会话 ID。",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        comment="会话所属用户 ID。",
    )
    identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_identities.id", ondelete="SET NULL"),
        comment="本次登录使用的手机号或邮箱身份 ID。",
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        Text,
        comment="刷新令牌哈希值，只存哈希，不存明文 refresh token。",
    )
    status: Mapped[str] = mapped_column(
        Text,
        default="active",
        server_default=text("'active'"),
        comment="会话状态：active 有效、revoked 已主动失效、expired 已过期。",
    )
    device_id: Mapped[str | None] = mapped_column(Text, comment="客户端设备 ID，可由前端生成并持久化。")
    device_name: Mapped[str | None] = mapped_column(Text, comment="设备名称，例如 iPhone、Chrome on Windows。")
    ip_address: Mapped[str | None] = mapped_column(INET, comment="登录或最近刷新会话的 IP 地址。")
    user_agent: Mapped[str | None] = mapped_column(Text, comment="登录或最近刷新会话的 User-Agent。")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), comment="会话过期时间。")
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="会话最近一次使用时间。",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="会话被主动撤销或退出登录的时间。",
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="扩展信息，例如 App 版本、渠道、风控标记。",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录创建时间。",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录最后更新时间。",
    )

    user: Mapped[User] = relationship(back_populates="sessions")
    identity: Mapped[UserIdentity | None] = relationship(back_populates="sessions")
    login_events: Mapped[list[LoginEvent]] = relationship(back_populates="session")


class LoginEvent(Base):
    __tablename__ = "login_events"
    __table_args__ = (
        CheckConstraint(
            "provider IS NULL OR provider IN ('phone', 'email')",
            name="login_events_provider_allowed",
        ),
        CheckConstraint(
            """
            event_type IN (
                'verification_requested',
                'verification_succeeded',
                'verification_failed',
                'login_success',
                'login_failed',
                'logout',
                'session_refreshed',
                'session_revoked',
                'identity_bound'
            )
            """,
            name="login_events_event_type_allowed",
        ),
        Index("idx_login_events_user_created_at", "user_id", text("created_at DESC")),
        Index("idx_login_events_target_created_at", "provider", "target", text("created_at DESC")),
        {"comment": "登录事件表：记录验证码发送、验证成功或失败、登录成功或失败、退出登录、刷新会话等审计事件。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="登录事件 ID。",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        comment="事件关联用户 ID。登录失败或未识别用户时可为空。",
    )
    identity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user_identities.id", ondelete="SET NULL"),
        comment="事件关联的手机号或邮箱身份 ID。未匹配到身份时可为空。",
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("auth_sessions.id", ondelete="SET NULL"),
        comment="事件关联会话 ID。只有登录成功、刷新、退出等会话事件通常会有值。",
    )
    provider: Mapped[str | None] = mapped_column(Text, comment="事件涉及的登录渠道：phone 手机号、email 邮箱。")
    target: Mapped[str | None] = mapped_column(Text, comment="事件涉及的手机号或邮箱。")
    event_type: Mapped[str] = mapped_column(
        Text,
        comment="事件类型，例如 verification_requested、login_success、logout。",
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        comment="失败原因，例如 code_expired、code_invalid、too_many_attempts。",
    )
    ip_address: Mapped[str | None] = mapped_column(INET, comment="触发事件的 IP 地址。")
    user_agent: Mapped[str | None] = mapped_column(Text, comment="触发事件的 User-Agent。")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="扩展信息，用于记录风控结果、服务商返回值等。",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="事件发生时间。",
    )

    user: Mapped[User | None] = relationship(back_populates="login_events")
    identity: Mapped[UserIdentity | None] = relationship(back_populates="login_events")
    session: Mapped[AuthSession | None] = relationship(back_populates="login_events")

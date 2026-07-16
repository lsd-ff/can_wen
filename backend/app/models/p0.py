from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="projects_status_allowed",
        ),
        Index("idx_projects_owner_status_created", "owner_id", "status", text("created_at DESC")),
        Index("idx_projects_owner_status_pinned_updated", "owner_id", "status", text("pinned_at DESC NULLS LAST"), text("updated_at DESC")),
        {"comment": "项目文件夹表：保存用户创建的项目，用于组织项目内问诊对话和文件。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="项目 ID。",
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        comment="项目创建人用户 ID。",
    )
    name: Mapped[str] = mapped_column(Text, comment="项目名称。")
    description: Mapped[str | None] = mapped_column(Text, comment="项目描述。")
    icon_key: Mapped[str] = mapped_column(
        Text,
        default="folder",
        server_default=text("'folder'"),
        comment="项目图标 key，对应前端图标选择。",
    )
    color: Mapped[str] = mapped_column(
        Text,
        default="#11110f",
        server_default=text("'#11110f'"),
        comment="项目颜色值，对应前端颜色选择。",
    )
    status: Mapped[str] = mapped_column(
        Text,
        default="active",
        server_default=text("'active'"),
        comment="项目状态：active 正常、archived 归档、deleted 已删除。",
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
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="Pinned timestamp; null means not pinned.",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="软删除时间，未删除时为空。",
    )

    conversations: Mapped[list[Conversation]] = relationship(back_populates="project")
    files: Mapped[list[UploadedFile]] = relationship(back_populates="project")
    shares: Mapped[list[ProjectShare]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "conversation_type IN ('diagnosis', 'video', 'general')",
            name="conversations_type_allowed",
        ),
        CheckConstraint(
            "status IN ('active', 'archived', 'deleted')",
            name="conversations_status_allowed",
        ),
        Index("idx_conversations_user_status_last_message", "user_id", "status", text("last_message_at DESC")),
        Index("idx_conversations_project_status_updated", "project_id", "status", text("updated_at DESC")),
        Index("idx_conversations_user_status_pinned_last", "user_id", "status", text("pinned_at DESC NULLS LAST"), text("last_message_at DESC")),
        Index("idx_conversations_project_status_pinned_updated", "project_id", "status", text("pinned_at DESC NULLS LAST"), text("updated_at DESC")),
        {"comment": "问诊对话表：保存项目内或项目外的对话主体。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="对话 ID。",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        comment="对话所属用户 ID。",
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        comment="所属项目 ID。为空表示普通对话，不在项目文件夹中。",
    )
    title: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default=text("''"),
        comment="对话标题。",
    )
    summary: Mapped[str | None] = mapped_column(Text, comment="对话摘要。")
    conversation_type: Mapped[str] = mapped_column(
        Text,
        default="diagnosis",
        server_default=text("'diagnosis'"),
        comment="对话类型：diagnosis 问诊、video 视频咨询、general 普通对话。",
    )
    status: Mapped[str] = mapped_column(
        Text,
        default="active",
        server_default=text("'active'"),
        comment="对话状态：active 正常、archived 归档、deleted 已删除。",
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="最近一条消息时间，用于对话列表排序。",
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
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="Pinned timestamp; null means not pinned.",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="软删除时间，未删除时为空。",
    )

    project: Mapped[Project | None] = relationship(back_populates="conversations")
    tags: Mapped[list[ConversationTag]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    messages: Mapped[list[Message]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    diagnoses: Mapped[list[Diagnosis]] = relationship(back_populates="conversation", cascade="all, delete-orphan")
    shares: Mapped[list[ConversationShare]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class ConversationTag(Base):
    __tablename__ = "conversation_tags"
    __table_args__ = (
        UniqueConstraint("conversation_id", "name", name="uq_conversation_tags_conversation_name"),
        Index("idx_conversation_tags_conversation", "conversation_id"),
        {"comment": "对话标签表：保存对话的用户侧标签。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="标签 ID。",
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        comment="所属对话 ID。",
    )
    name: Mapped[str] = mapped_column(Text, comment="标签名称。")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录创建时间。",
    )

    conversation: Mapped[Conversation] = relationship(back_populates="tags")


class ConversationShare(Base):
    __tablename__ = "conversation_shares"
    __table_args__ = (
        CheckConstraint(
            "variant IN ('summary', 'full-record', 'expert-review')",
            name="conversation_shares_variant_allowed",
        ),
        CheckConstraint(
            "status IN ('active', 'revoked', 'deleted')",
            name="conversation_shares_status_allowed",
        ),
        UniqueConstraint("share_token", name="uq_conversation_shares_share_token"),
        Index("idx_conversation_shares_conversation_created", "conversation_id", text("created_at DESC")),
        Index("idx_conversation_shares_token_status", "share_token", "status"),
        {"comment": "会话分享表：保存可公开访问的问诊会话 Markdown 快照。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="分享 ID。",
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        comment="来源对话 ID。",
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        comment="创建分享的用户 ID。",
    )
    share_token: Mapped[str] = mapped_column(Text, comment="公开分享访问令牌。")
    title: Mapped[str] = mapped_column(Text, comment="分享标题。")
    variant: Mapped[str] = mapped_column(
        Text,
        default="summary",
        server_default=text("'summary'"),
        comment="分享类型：summary 摘要、full-record 完整记录、expert-review 专家复核。",
    )
    content_markdown: Mapped[str] = mapped_column(Text, comment="分享时生成的 Markdown 快照。")
    status: Mapped[str] = mapped_column(
        Text,
        default="active",
        server_default=text("'active'"),
        comment="分享状态：active 有效、revoked 已撤销、deleted 已删除。",
    )
    view_count: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default=text("0"),
        comment="公开链接访问次数。",
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="分享扩展信息。",
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
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="分享过期时间，空表示不过期。",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="分享撤销时间。",
    )

    conversation: Mapped[Conversation] = relationship(back_populates="shares")


class ProjectShare(Base):
    __tablename__ = "project_shares"
    __table_args__ = (
        CheckConstraint(
            "variant IN ('summary', 'full-record', 'expert-review')",
            name="project_shares_variant_allowed",
        ),
        CheckConstraint(
            "status IN ('active', 'revoked', 'deleted')",
            name="project_shares_status_allowed",
        ),
        UniqueConstraint("share_token", name="uq_project_shares_share_token"),
        Index("idx_project_shares_project_created", "project_id", text("created_at DESC")),
        Index("idx_project_shares_token_status", "share_token", "status"),
        {"comment": "项目分享表：保存可公开访问的项目 Markdown 快照。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="分享 ID。",
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        comment="来源项目 ID。",
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        comment="创建分享的用户 ID。",
    )
    share_token: Mapped[str] = mapped_column(Text, comment="公开分享访问令牌。")
    title: Mapped[str] = mapped_column(Text, comment="分享标题。")
    variant: Mapped[str] = mapped_column(
        Text,
        default="summary",
        server_default=text("'summary'"),
        comment="分享类型：summary 摘要、full-record 完整记录、expert-review 专家复核。",
    )
    content_markdown: Mapped[str] = mapped_column(Text, comment="分享时生成的 Markdown 快照。")
    status: Mapped[str] = mapped_column(
        Text,
        default="active",
        server_default=text("'active'"),
        comment="分享状态：active 有效、revoked 已撤销、deleted 已删除。",
    )
    view_count: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        server_default=text("0"),
        comment="公开链接访问次数。",
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="分享扩展信息。",
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
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="分享过期时间，空表示不过期。",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="分享撤销时间。",
    )

    project: Mapped[Project] = relationship(back_populates="shares")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "sender_type IN ('user', 'assistant', 'system')",
            name="messages_sender_type_allowed",
        ),
        CheckConstraint(
            "message_type IN ('text', 'image', 'video', 'file', 'diagnosis_result')",
            name="messages_message_type_allowed",
        ),
        CheckConstraint(
            "status IN ('sending', 'sent', 'failed')",
            name="messages_status_allowed",
        ),
        Index("idx_messages_conversation_created", "conversation_id", text("created_at ASC")),
        {"comment": "对话消息表：保存用户、助手和系统消息。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="消息 ID。",
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        comment="所属对话 ID。",
    )
    sender_type: Mapped[str] = mapped_column(Text, comment="发送方类型：user 用户、assistant 助手、system 系统。")
    content: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default=text("''"),
        comment="消息文本内容。纯文件消息可为空字符串。",
    )
    message_type: Mapped[str] = mapped_column(
        Text,
        default="text",
        server_default=text("'text'"),
        comment="消息类型：text 文本、image 图片、video 视频、file 文件、diagnosis_result 诊断结果。",
    )
    status: Mapped[str] = mapped_column(
        Text,
        default="sent",
        server_default=text("'sent'"),
        comment="消息状态：sending 发送中、sent 已发送、failed 失败。",
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="消息扩展信息，例如模型调用、客户端临时 ID、流式输出状态。",
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

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    files: Mapped[list[MessageFile]] = relationship(back_populates="message", cascade="all, delete-orphan")
    triggered_diagnoses: Mapped[list[Diagnosis]] = relationship(
        back_populates="trigger_message",
        foreign_keys="Diagnosis.trigger_message_id",
    )
    multimodal_analyses: Mapped[list[DiagnosisMultimodalAnalysis]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class LLMModelConfig(Base):
    __tablename__ = "llm_model_configs"
    __table_args__ = (
        CheckConstraint(
            "last_test_status IS NULL OR last_test_status IN ('success', 'failed')",
            name="llm_model_configs_last_test_status_allowed",
        ),
        Index("idx_llm_model_configs_user_created", "user_id", text("created_at DESC")),
        Index("idx_llm_model_configs_user_default", "user_id", "is_default"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider_name: Mapped[str] = mapped_column(Text)
    model_id: Mapped[str] = mapped_column(Text)
    api_key_ciphertext: Mapped[str] = mapped_column(Text)
    api_request_url: Mapped[str] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    last_test_status: Mapped[str | None] = mapped_column(Text)
    last_test_message: Mapped[str | None] = mapped_column(Text)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UploadedFile(Base):
    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint(
            "file_type IN ('image', 'video', 'document', 'audio', 'other')",
            name="files_file_type_allowed",
        ),
        CheckConstraint("file_size >= 0", name="files_file_size_nonnegative"),
        Index("idx_files_user_created", "user_id", text("created_at DESC")),
        Index("idx_files_project_created", "project_id", text("created_at DESC")),
        {"comment": "上传文件表：保存图片、视频、文档等文件的存储信息。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="文件 ID。",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        comment="上传用户 ID。",
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        comment="所属项目 ID。为空表示未归入项目。",
    )
    file_name: Mapped[str] = mapped_column(Text, comment="原始文件名。")
    file_type: Mapped[str] = mapped_column(Text, comment="文件类型：image、video、document、audio、other。")
    mime_type: Mapped[str] = mapped_column(Text, comment="文件 MIME 类型。")
    storage_key: Mapped[str] = mapped_column(Text, comment="对象存储 key 或本地存储 key。")
    storage_url: Mapped[str | None] = mapped_column(Text, comment="可访问文件 URL。")
    file_size: Mapped[int] = mapped_column(BigInteger, comment="文件大小，单位字节。")
    checksum: Mapped[str | None] = mapped_column(Text, comment="文件校验值，用于去重或完整性校验。")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="文件扩展信息，例如图片宽高、视频时长、转码状态。",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录创建时间。",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="软删除时间，未删除时为空。",
    )

    project: Mapped[Project | None] = relationship(back_populates="files")
    messages: Mapped[list[MessageFile]] = relationship(back_populates="file", cascade="all, delete-orphan")


class MessageFile(Base):
    __tablename__ = "message_files"
    __table_args__ = (
        UniqueConstraint("message_id", "file_id", name="uq_message_files_message_file"),
        Index("idx_message_files_message", "message_id"),
        Index("idx_message_files_file", "file_id"),
        {"comment": "消息文件关联表：记录一条消息引用了哪些上传文件。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="消息文件关联 ID。",
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        comment="消息 ID。",
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"),
        comment="文件 ID。",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录创建时间。",
    )

    message: Mapped[Message] = relationship(back_populates="files")
    file: Mapped[UploadedFile] = relationship(back_populates="messages")


class DiagnosisMultimodalAnalysis(Base):
    __tablename__ = "diagnosis_multimodal_analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="diagnosis_multimodal_analyses_status_allowed",
        ),
        Index("idx_diagnosis_multimodal_analyses_message_created", "message_id", text("created_at DESC")),
        Index("idx_diagnosis_multimodal_analyses_conversation_created", "conversation_id", text("created_at DESC")),
        {"comment": "多模态解析表：保存多模态模型对消息附件的结构化观察结果。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="多模态解析 ID。",
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        comment="关联问诊对话 ID。",
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        comment="触发解析的用户消息 ID。",
    )
    file_ids: Mapped[list[str]] = mapped_column(
        JSONB,
        server_default=text("'[]'::jsonb"),
        comment="参与本次解析的文件 ID 列表。",
    )
    status: Mapped[str] = mapped_column(
        Text,
        default="pending",
        server_default=text("'pending'"),
        comment="解析状态：pending 待处理、running 处理中、completed 完成、failed 失败。",
    )
    model_id: Mapped[str | None] = mapped_column(Text, comment="执行多模态解析的模型 ID。")
    analysis_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="多模态模型输出的结构化解析结果。",
    )
    analysis_text: Mapped[str | None] = mapped_column(Text, comment="多模态解析结果的文本版摘要。")
    error_message: Mapped[str | None] = mapped_column(Text, comment="解析失败原因。")
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

    conversation: Mapped[Conversation] = relationship()
    message: Mapped[Message] = relationship(back_populates="multimodal_analyses")


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="diagnoses_status_allowed",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="diagnoses_confidence_range",
        ),
        Index("idx_diagnoses_user_status_created", "user_id", "status", text("created_at DESC")),
        Index("idx_diagnoses_conversation_created", "conversation_id", text("created_at DESC")),
        {"comment": "诊断任务表：保存一次疾病诊断任务及其结构化结论。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="诊断 ID。",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        comment="诊断所属用户 ID。",
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        comment="关联对话 ID。",
    )
    trigger_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"),
        comment="触发本次诊断的消息 ID。",
    )
    status: Mapped[str] = mapped_column(
        Text,
        default="pending",
        server_default=text("'pending'"),
        comment="诊断状态：pending 待处理、running 处理中、completed 完成、failed 失败。",
    )
    disease_name: Mapped[str | None] = mapped_column(Text, comment="诊断出的疾病名称。")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), comment="诊断置信度，范围 0 到 1。")
    result_summary: Mapped[str | None] = mapped_column(Text, comment="诊断结果摘要。")
    suggestion: Mapped[str | None] = mapped_column(Text, comment="处置建议。")
    follow_up_question: Mapped[str | None] = mapped_column(Text, comment="需要继续追问的问题。")
    model_name: Mapped[str | None] = mapped_column(Text, comment="生成诊断结果的模型名称。")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="诊断扩展信息，例如 prompt 版本、工具调用摘要、错误原因。",
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
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="诊断完成时间。",
    )

    conversation: Mapped[Conversation] = relationship(back_populates="diagnoses")
    trigger_message: Mapped[Message | None] = relationship(
        back_populates="triggered_diagnoses",
        foreign_keys=[trigger_message_id],
    )
    evidence: Mapped[list[DiagnosisEvidence]] = relationship(back_populates="diagnosis", cascade="all, delete-orphan")


class DiagnosisEvidence(Base):
    __tablename__ = "diagnosis_evidence"
    __table_args__ = (
        CheckConstraint(
            "evidence_type IN ('symptom', 'rag_document', 'graph_path', 'rule', 'image')",
            name="diagnosis_evidence_type_allowed",
        ),
        Index("idx_diagnosis_evidence_diagnosis_created", "diagnosis_id", text("created_at ASC")),
        {"comment": "诊断依据表：保存诊断结论对应的症状、文档、图谱、规则或图片依据。"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="诊断依据 ID。",
    )
    diagnosis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagnoses.id", ondelete="CASCADE"),
        comment="所属诊断 ID。",
    )
    evidence_type: Mapped[str] = mapped_column(
        Text,
        comment="依据类型：symptom 症状、rag_document 文档、graph_path 图谱路径、rule 规则、image 图片。",
    )
    title: Mapped[str] = mapped_column(Text, comment="依据标题。")
    content: Mapped[str] = mapped_column(Text, comment="依据内容。")
    source: Mapped[str | None] = mapped_column(Text, comment="依据来源。")
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), comment="依据分数或相关性得分。")
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        comment="依据扩展信息，例如原始检索结果、图谱路径节点、图片区域。",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        comment="记录创建时间。",
    )

    diagnosis: Mapped[Diagnosis] = relationship(back_populates="evidence")

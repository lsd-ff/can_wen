from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, SmallInteger, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CommunityPost(Base):
    __tablename__ = "community_posts"
    __table_args__ = (
        CheckConstraint(
            "post_type IN ('experience', 'case', 'question', 'reference', 'announcement')",
            name="community_posts_type_allowed",
        ),
        CheckConstraint("visibility IN ('public', 'followers')", name="community_posts_visibility_allowed"),
        CheckConstraint("status IN ('draft', 'published', 'hidden', 'deleted')", name="community_posts_status_allowed"),
        CheckConstraint("question_status IN ('open', 'resolved')", name="community_posts_question_status_allowed"),
        Index("idx_community_posts_feed", "status", "visibility", text("published_at DESC")),
        Index("idx_community_posts_author", "author_id", "status", text("updated_at DESC")),
        Index("idx_community_posts_author_created", "author_id", text("created_at DESC")),
        Index("idx_community_posts_source_conversation", "source_conversation_id"),
        Index("idx_community_posts_source_husbandry_case", "source_husbandry_case_id"),
        Index("idx_community_posts_question_status", "post_type", "question_status", text("published_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    source_husbandry_case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("husbandry_cases.id", ondelete="SET NULL"), nullable=True
    )
    accepted_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("community_comments.id", ondelete="SET NULL", use_alter=True, name="fk_community_posts_accepted_comment"), nullable=True
    )
    cover_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    post_type: Mapped[str] = mapped_column(Text, nullable=False, default="experience", server_default=text("'experience'"))
    visibility: Mapped[str] = mapped_column(Text, nullable=False, default="public", server_default=text("'public'"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft", server_default=text("'draft'"))
    question_status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default=text("'open'"))
    case_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    like_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    bookmark_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    comment_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    view_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Management console mutations use this value for optimistic concurrency.
    moderation_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))


class CommunityPostAsset(Base):
    __tablename__ = "community_post_assets"
    __table_args__ = (
        CheckConstraint("asset_role IN ('attachment', 'cover')", name="community_post_assets_role_allowed"),
        UniqueConstraint("post_id", "file_id", name="uq_community_post_assets_post_file"),
        Index("idx_community_post_assets_post_order", "post_id", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="RESTRICT"), nullable=False)
    asset_role: Mapped[str] = mapped_column(Text, nullable=False, default="attachment", server_default=text("'attachment'"))
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityTag(Base):
    __tablename__ = "community_tags"
    __table_args__ = (
        UniqueConstraint("name", name="uq_community_tags_name"),
        Index("idx_community_tags_usage", text("post_count DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    post_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityPostTag(Base):
    __tablename__ = "community_post_tags"
    __table_args__ = (
        UniqueConstraint("post_id", "tag_id", name="uq_community_post_tags_post_tag"),
        Index("idx_community_post_tags_tag_post", "tag_id", "post_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_tags.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityTopicFollow(Base):
    __tablename__ = "community_topic_follows"
    __table_args__ = (
        UniqueConstraint("user_id", "tag_id", name="uq_community_topic_follows_user_tag"),
        Index("idx_community_topic_follows_user_created", "user_id", text("created_at DESC")),
        Index("idx_community_topic_follows_tag", "tag_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_tags.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityPostLike(Base):
    __tablename__ = "community_post_likes"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_community_post_likes_post_user"),
        Index("idx_community_post_likes_user_created", "user_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityPostBookmark(Base):
    __tablename__ = "community_post_bookmarks"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_community_post_bookmarks_post_user"),
        Index("idx_community_post_bookmarks_user_created", "user_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityBookmarkCollection(Base):
    __tablename__ = "community_bookmark_collections"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_community_bookmark_collections_owner_name"),
        Index("idx_community_bookmark_collections_owner_updated", "owner_id", text("updated_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityBookmarkCollectionItem(Base):
    __tablename__ = "community_bookmark_collection_items"
    __table_args__ = (
        UniqueConstraint("collection_id", "post_id", name="uq_community_bookmark_collection_items_collection_post"),
        Index("idx_community_bookmark_collection_items_collection_created", "collection_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    collection_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_bookmark_collections.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityComment(Base):
    __tablename__ = "community_comments"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'hidden', 'deleted')", name="community_comments_status_allowed"),
        Index("idx_community_comments_post_created", "post_id", text("created_at ASC")),
        Index("idx_community_comments_parent_created", "parent_comment_id", text("created_at ASC")),
        Index("idx_community_comments_author_created", "author_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("community_comments.id", ondelete="CASCADE"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default=text("'active'"))
    like_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommunityCommentLike(Base):
    __tablename__ = "community_comment_likes"
    __table_args__ = (
        UniqueConstraint("comment_id", "user_id", name="uq_community_comment_likes_comment_user"),
        Index("idx_community_comment_likes_user_created", "user_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    comment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_comments.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityCaseUpdate(Base):
    __tablename__ = "community_case_updates"
    __table_args__ = (
        CheckConstraint(
            "outcome_status IN ('observing', 'improved', 'stable', 'worsened', 'resolved')",
            name="community_case_updates_outcome_allowed",
        ),
        Index("idx_community_case_updates_post_date", "post_id", text("occurred_on DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, server_default=text("CURRENT_DATE"))
    outcome_status: Mapped[str] = mapped_column(Text, nullable=False, default="observing", server_default=text("'observing'"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityProfile(Base):
    __tablename__ = "community_profiles"
    __table_args__ = (
        CheckConstraint(
            "identity_type IN ('farmer', 'technician', 'researcher', 'other')",
            name="community_profiles_identity_allowed",
        ),
        CheckConstraint(
            "verification_status IN ('unverified', 'pending', 'verified', 'rejected')",
            name="community_profiles_verification_allowed",
        ),
        CheckConstraint("years_experience IS NULL OR years_experience >= 0", name="community_profiles_years_nonnegative"),
        Index("idx_community_profiles_discovery", "verification_status", "identity_type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    identity_type: Mapped[str] = mapped_column(Text, nullable=False, default="farmer", server_default=text("'farmer'"))
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization: Mapped[str | None] = mapped_column(Text, nullable=True)
    expertise_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(Text, nullable=False, default="unverified", server_default=text("'unverified'"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityUserBlock(Base):
    __tablename__ = "community_user_blocks"
    __table_args__ = (
        CheckConstraint("blocker_id <> blocked_id", name="community_user_blocks_distinct_users"),
        UniqueConstraint("blocker_id", "blocked_id", name="uq_community_user_blocks_pair"),
        Index("idx_community_user_blocks_blocker", "blocker_id", "blocked_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    blocker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    blocked_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityPostPreference(Base):
    __tablename__ = "community_post_preferences"
    __table_args__ = (
        CheckConstraint("preference_type IN ('not_interested', 'hidden')", name="community_post_preferences_type_allowed"),
        UniqueConstraint("user_id", "post_id", name="uq_community_post_preferences_user_post"),
        Index("idx_community_post_preferences_user", "user_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False)
    preference_type: Mapped[str] = mapped_column(Text, nullable=False, default="not_interested", server_default=text("'not_interested'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityFollow(Base):
    __tablename__ = "community_follows"
    __table_args__ = (
        CheckConstraint("follower_id <> followed_id", name="community_follows_distinct_users"),
        UniqueConstraint("follower_id", "followed_id", name="uq_community_follows_pair"),
        Index("idx_community_follows_followed", "followed_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    follower_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    followed_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityInteractionEvent(Base):
    __tablename__ = "community_interaction_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('view', 'like', 'bookmark', 'comment', 'not_interested')",
            name="community_interaction_events_type_allowed",
        ),
        Index("idx_community_interaction_events_user_created", "user_id", text("created_at DESC")),
        Index("idx_community_interaction_events_user_post", "user_id", "post_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityDirectThread(Base):
    __tablename__ = "community_direct_threads"
    __table_args__ = (
        CheckConstraint("participant_one_id <> participant_two_id", name="community_direct_threads_distinct_users"),
        UniqueConstraint("participant_one_id", "participant_two_id", name="uq_community_direct_threads_pair"),
        Index("idx_community_direct_threads_one_recent", "participant_one_id", text("last_message_at DESC")),
        Index("idx_community_direct_threads_two_recent", "participant_two_id", text("last_message_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    participant_one_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    participant_two_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    last_message_preview: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityDirectMessage(Base):
    __tablename__ = "community_direct_messages"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'deleted')", name="community_direct_messages_status_allowed"),
        Index("idx_community_direct_messages_thread_created", "thread_id", text("created_at ASC")),
        Index("idx_community_direct_messages_recipient_unread", "recipient_id", "read_at"),
        Index("idx_community_direct_messages_sender_created", "sender_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("community_direct_threads.id", ondelete="CASCADE"), nullable=False)
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active", server_default=text("'active'"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommunityNotification(Base):
    __tablename__ = "community_notifications"
    __table_args__ = (
        CheckConstraint(
            "notification_type IN ('post_like', 'post_comment', 'comment_reply', 'comment_like', 'follow', 'moderation', 'answer_accepted', 'case_update', 'mention', 'direct_message')",
            name="community_notifications_type_allowed",
        ),
        Index("idx_community_notifications_user_created", "user_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    post_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=True)
    comment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("community_comments.id", ondelete="CASCADE"), nullable=True)
    notification_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class CommunityReport(Base):
    __tablename__ = "community_reports"
    __table_args__ = (
        CheckConstraint("target_type IN ('post', 'comment')", name="community_reports_target_allowed"),
        CheckConstraint("status IN ('pending', 'reviewed', 'dismissed')", name="community_reports_status_allowed"),
        Index("idx_community_reports_status_created", "status", text("created_at DESC")),
        Index("idx_community_reports_reporter_created", "reporter_id", text("created_at DESC")),
        Index(
            "uq_community_reports_pending_post_reporter",
            "reporter_id",
            "post_id",
            unique=True,
            postgresql_where=text("status = 'pending' AND target_type = 'post' AND post_id IS NOT NULL"),
        ),
        Index(
            "uq_community_reports_pending_comment_reporter",
            "reporter_id",
            "comment_id",
            unique=True,
            postgresql_where=text("status = 'pending' AND target_type = 'comment' AND comment_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=True)
    comment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("community_comments.id", ondelete="CASCADE"), nullable=True)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default=text("'pending'"))
    review_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

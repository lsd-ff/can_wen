from __future__ import annotations

from datetime import date, datetime
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


CommunityPostType = Literal["experience", "case", "question", "reference", "announcement"]
CommunityPostVisibility = Literal["public", "followers"]
CommunityPostStatus = Literal["draft", "published", "hidden", "deleted"]
COMMUNITY_TAG_CONTENT_PATTERN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]")


def _normalized_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty")
    return normalized


def _normalized_community_tags(value: list[str]) -> list[str]:
    normalized_tags: list[str] = []
    for tag in value:
        normalized = " ".join(tag.strip().lstrip("#").split())[:32]
        if not normalized:
            continue
        if not COMMUNITY_TAG_CONTENT_PATTERN.search(normalized):
            raise ValueError("tag must include Chinese characters, letters, or numbers")
        if normalized not in normalized_tags:
            normalized_tags.append(normalized)
    return normalized_tags


class CommunityPostCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    content_markdown: str = Field(default="", max_length=60000)
    post_type: CommunityPostType = "experience"
    visibility: CommunityPostVisibility = "public"
    tags: list[str] = Field(default_factory=list, max_length=8)
    file_ids: list[UUID] = Field(default_factory=list, max_length=9)
    cover_file_id: UUID | None = None
    publish: bool = True
    source_conversation_id: UUID | None = None
    source_husbandry_case_id: UUID | None = None
    case_data: dict = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return _normalized_text(value, field_name="title")

    @field_validator("content_markdown")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return _normalized_community_tags(value)


class CommunityPostUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    content_markdown: str | None = Field(default=None, max_length=60000)
    post_type: CommunityPostType | None = None
    visibility: CommunityPostVisibility | None = None
    tags: list[str] | None = Field(default=None, max_length=8)
    file_ids: list[UUID] | None = Field(default=None, max_length=9)
    cover_file_id: UUID | None = None
    publish: bool | None = None
    case_data: dict | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        return _normalized_text(value, field_name="title") if value is not None else None

    @field_validator("content_markdown")
    @classmethod
    def normalize_content(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return _normalized_community_tags(value)


class CommunityBookmarkCollectionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=180)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _normalized_text(value, field_name="name")

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class CommunityBookmarkCollectionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=40)
    description: str | None = Field(default=None, max_length=180)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return _normalized_text(value, field_name="name") if value is not None else None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

class CommunityCommentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=2000)
    parent_comment_id: UUID | None = None

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return _normalized_text(value, field_name="content")


class CommunityCommentUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return _normalized_text(value, field_name="content")


class CommunityReportCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["post", "comment"]
    reason: str = Field(min_length=1, max_length=80)
    detail: str | None = Field(default=None, max_length=1000)
    comment_id: UUID | None = None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return _normalized_text(value, field_name="reason")

    @field_validator("detail")
    @classmethod
    def normalize_detail(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class CommunityConversationDraftCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)
    include_attachment_ids: list[UUID] = Field(default_factory=list, max_length=9)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        return _normalized_text(value, field_name="title") if value is not None else None


class CommunityAuthorResponse(BaseModel):
    id: str
    display_name: str
    username: str
    avatar_url: str | None = None
    role: str
    is_followed: bool = False
    identity_type: str = "farmer"
    region: str | None = None
    organization: str | None = None
    expertise_tags: list[str] = Field(default_factory=list)
    years_experience: int | None = None
    bio: str | None = None
    verification_status: str = "unverified"
    post_count: int = 0
    follower_count: int = 0
    following_count: int = 0
    received_like_count: int = 0


class CommunityProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity_type: Literal["farmer", "technician", "researcher", "other"] = "farmer"
    region: str | None = Field(default=None, max_length=80)
    organization: str | None = Field(default=None, max_length=120)
    expertise_tags: list[str] = Field(default_factory=list, max_length=8)
    years_experience: int | None = Field(default=None, ge=0, le=80)
    bio: str | None = Field(default=None, max_length=500)
    request_verification: bool = False

    @field_validator("region", "organization", "bio")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("expertise_tags")
    @classmethod
    def normalize_expertise_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(" ".join(item.strip().split())[:32] for item in value if item.strip()))


class CommunityCaseUpdateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_on: date = Field(default_factory=date.today)
    outcome_status: Literal["observing", "improved", "stable", "worsened", "resolved"] = "observing"
    content: str = Field(min_length=1, max_length=3000)
    metrics: dict = Field(default_factory=dict)

    @field_validator("content")
    @classmethod
    def normalize_case_update_content(cls, value: str) -> str:
        return _normalized_text(value, field_name="content")


class CommunityCaseUpdateResponse(BaseModel):
    id: str
    post_id: str
    occurred_on: date
    outcome_status: str
    content: str
    metrics: dict = Field(default_factory=dict)
    author: CommunityAuthorResponse
    created_at: datetime


class CommunityHusbandryDraftCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)


class CommunitySaveToHusbandryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    farm_id: UUID
    batch_id: UUID | None = None


class CommunityAssetResponse(BaseModel):
    id: str
    file_id: str
    file_name: str
    file_type: str
    mime_type: str
    storage_url: str | None = None
    file_size: int
    asset_role: str
    sort_order: int


class CommunityUploadedFileResponse(BaseModel):
    file_id: str
    file_name: str
    file_type: str
    mime_type: str
    storage_url: str | None = None
    file_size: int


class CommunityTagResponse(BaseModel):
    id: str
    name: str
    post_count: int
    is_followed: bool = False


class CommunityPostResponse(BaseModel):
    id: str
    title: str
    content_markdown: str
    excerpt: str
    post_type: CommunityPostType
    visibility: CommunityPostVisibility
    status: CommunityPostStatus
    source_conversation_id: str | None = None
    source_husbandry_case_id: str | None = None
    accepted_comment_id: str | None = None
    question_status: Literal["open", "resolved"] = "open"
    case_data: dict = Field(default_factory=dict)
    case_updates: list[CommunityCaseUpdateResponse] = Field(default_factory=list)
    author: CommunityAuthorResponse
    tags: list[CommunityTagResponse] = Field(default_factory=list)
    assets: list[CommunityAssetResponse] = Field(default_factory=list)
    like_count: int
    bookmark_count: int
    comment_count: int
    view_count: int
    is_liked: bool = False
    is_bookmarked: bool = False
    is_author: bool = False
    recommendation_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class CommunityPostListResponse(BaseModel):
    items: list[CommunityPostResponse]
    next_offset: int | None = None


class CommunityBookmarkCollectionResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    item_count: int = 0
    contains_post: bool = False
    created_at: datetime
    updated_at: datetime


class CommunityBookmarkCollectionListResponse(BaseModel):
    items: list[CommunityBookmarkCollectionResponse] = Field(default_factory=list)


class CommunityBookmarkCollectionDetailResponse(BaseModel):
    collection: CommunityBookmarkCollectionResponse
    posts: list[CommunityPostResponse] = Field(default_factory=list)
    next_offset: int | None = None


class CommunitySearchResponse(BaseModel):
    posts: list[CommunityPostResponse] = Field(default_factory=list)
    authors: list[CommunityAuthorResponse] = Field(default_factory=list)
    tags: list[CommunityTagResponse] = Field(default_factory=list)


class CommunityCommentResponse(BaseModel):
    id: str
    post_id: str
    parent_comment_id: str | None = None
    content: str
    status: str
    like_count: int
    is_liked: bool = False
    is_author: bool = False
    is_accepted: bool = False
    author: CommunityAuthorResponse
    created_at: datetime
    updated_at: datetime


class CommunityCommentListResponse(BaseModel):
    items: list[CommunityCommentResponse]
    next_offset: int | None = None


class CommunityNotificationResponse(BaseModel):
    id: str
    notification_type: str
    post_id: str | None = None
    comment_id: str | None = None
    actor: CommunityAuthorResponse | None = None
    payload: dict = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime


class CommunityNotificationListResponse(BaseModel):
    items: list[CommunityNotificationResponse]
    unread_count: int


class CommunityProfileDetailResponse(BaseModel):
    author: CommunityAuthorResponse
    posts: list[CommunityPostResponse] = Field(default_factory=list)
    next_offset: int | None = None


class CommunityRelationshipListResponse(BaseModel):
    author: CommunityAuthorResponse
    relationship_type: Literal["followers", "following"]
    items: list[CommunityAuthorResponse] = Field(default_factory=list)
    next_offset: int | None = None


class CommunityBlockedUserListResponse(BaseModel):
    items: list[CommunityAuthorResponse] = Field(default_factory=list)
    next_offset: int | None = None


class CommunityCreatorOverviewResponse(BaseModel):
    post_count: int = 0
    published_this_week: int = 0
    view_count: int = 0
    received_like_count: int = 0
    bookmark_count: int = 0
    comment_count: int = 0
    follower_count: int = 0
    following_count: int = 0


class CommunityDirectMessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return _normalized_text(value, field_name="content")


class CommunityDirectMessageResponse(BaseModel):
    id: str
    thread_id: str
    sender_id: str
    recipient_id: str
    content: str
    status: str
    is_mine: bool = False
    read_at: datetime | None = None
    created_at: datetime


class CommunityDirectThreadResponse(BaseModel):
    id: str
    counterpart: CommunityAuthorResponse
    last_message_preview: str
    last_message_at: datetime
    unread_count: int = 0


class CommunityDirectThreadListResponse(BaseModel):
    items: list[CommunityDirectThreadResponse] = Field(default_factory=list)


class CommunityDirectMessageListResponse(BaseModel):
    items: list[CommunityDirectMessageResponse] = Field(default_factory=list)
    next_offset: int | None = None

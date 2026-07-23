from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


ProjectShareVariant = Literal["summary", "full-record", "expert-review"]


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    icon_key: str = Field(default="folder", min_length=1, max_length=64)
    color: str = Field(default="#11110f", min_length=1, max_length=32)


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    icon_key: str | None = Field(default=None, min_length=1, max_length=64)
    color: str | None = Field(default=None, min_length=1, max_length=32)


class ProjectPinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pinned: bool


class ProjectShareCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)
    variant: ProjectShareVariant = "summary"
    content_markdown: str = Field(min_length=1, max_length=120000)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("title cannot be empty")
        return normalized

    @field_validator("content_markdown")
    @classmethod
    def normalize_content_markdown(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("content_markdown cannot be empty")
        return normalized


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    icon_key: str
    color: str
    status: str
    created_at: datetime
    updated_at: datetime
    pinned_at: datetime | None = None


class ProjectConversationMoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID | None = None


class ProjectShareResponse(BaseModel):
    id: str
    project_id: str
    share_token: str
    share_url: str
    title: str
    variant: ProjectShareVariant
    created_at: datetime
    expires_at: datetime | None = None


class PublicProjectShareResponse(BaseModel):
    title: str
    variant: ProjectShareVariant
    content_markdown: str
    created_at: datetime
    updated_at: datetime

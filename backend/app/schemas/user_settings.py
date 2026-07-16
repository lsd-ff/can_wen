from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserSettingsResponse(BaseModel):
    preferences: dict[str, Any]
    updated_at: datetime | None = None


class UpdateUserSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferences: dict[str, Any] = Field(default_factory=dict)


class AuthSessionResponse(BaseModel):
    id: str
    device_name: str
    last_used_at: datetime | None = None
    created_at: datetime
    expires_at: datetime
    is_current: bool


class AccountDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str = Field(min_length=1, max_length=32)


class StatusResponse(BaseModel):
    status: str

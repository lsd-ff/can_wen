from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


ModelTestStatus = Literal["success", "failed"]


class ModelConfigCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_name: str = Field(min_length=1, max_length=120)
    model_id: str = Field(min_length=1, max_length=160)
    api_key: str = Field(min_length=1, max_length=4000)
    api_request_url: str = Field(min_length=1, max_length=500)
    is_enabled: bool = True
    is_default: bool = False


class ModelConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_name: str | None = Field(default=None, min_length=1, max_length=120)
    model_id: str | None = Field(default=None, min_length=1, max_length=160)
    api_key: str | None = Field(default=None, max_length=4000)
    api_request_url: str | None = Field(default=None, min_length=1, max_length=500)
    is_enabled: bool | None = None
    is_default: bool | None = None


class ModelConfigResponse(BaseModel):
    id: UUID
    provider_name: str
    model_id: str
    api_request_url: str
    is_enabled: bool
    is_default: bool
    has_api_key: bool
    last_test_status: ModelTestStatus | None = None
    last_test_message: str | None = None
    last_test_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ModelConfigTestResponse(BaseModel):
    id: UUID
    status: ModelTestStatus
    message: str
    tested_at: datetime

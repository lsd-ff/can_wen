from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


AdminUserRole = Literal["farmer", "agritech", "expert", "admin"]
AdminUserStatus = Literal["active", "disabled", "deleted"]
AdminReviewStatus = Literal["draft", "published", "superseded"]
AdminRiskLevel = Literal["low", "medium", "high", "critical"]


class AdminMetricResponse(BaseModel):
    key: str
    label: str
    value: int
    trend: str | None = None
    tone: Literal["blue", "green", "orange", "red", "gray"] = "gray"


class AdminDashboardResponse(BaseModel):
    metrics: list[AdminMetricResponse] = Field(default_factory=list)
    role_distribution: list[AdminMetricResponse] = Field(default_factory=list)
    review_queue: list["AdminReviewQueueItemResponse"] = Field(default_factory=list)
    pending_reports: list["AdminReportResponse"] = Field(default_factory=list)


class AdminUserResponse(BaseModel):
    id: str
    display_name: str
    username: str
    avatar_url: str | None = None
    role: AdminUserRole
    status: AdminUserStatus
    email: str = ""
    phone_number: str = ""
    registered_at: datetime
    last_seen_at: datetime | None = None
    farm_count: int = 0
    batch_count: int = 0
    case_count: int = 0
    post_count: int = 0


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse] = Field(default_factory=list)
    total: int = 0


class AdminUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: AdminUserRole | None = None
    status: AdminUserStatus | None = None


class AdminReportResponse(BaseModel):
    id: str
    target_type: Literal["post", "comment"]
    reason: str
    detail: str | None = None
    status: Literal["pending", "reviewed", "dismissed"]
    reporter_name: str
    reporter_id: str
    target_title: str
    target_excerpt: str | None = None
    post_id: str | None = None
    comment_id: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class AdminReviewQueueItemResponse(BaseModel):
    id: str
    title: str
    symptom_summary: str | None = None
    suspected_disease: str | None = None
    severity: AdminRiskLevel
    case_status: str
    owner_name: str
    owner_id: str
    farm_name: str
    batch_code: str | None = None
    occurred_on: date
    created_at: datetime
    review_count: int = 0
    latest_review_status: AdminReviewStatus | None = None


class AdminExpertReviewResponse(BaseModel):
    id: str
    husbandry_case_id: str | None = None
    conversation_id: str | None = None
    reviewer_id: str | None = None
    reviewer_name: str
    risk_level: AdminRiskLevel
    conclusion: str
    recommendation: str
    evidence: list[dict] = Field(default_factory=list)
    status: AdminReviewStatus
    version: int
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class AdminExpertReviewCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    husbandry_case_id: str | None = None
    conversation_id: str | None = None
    risk_level: AdminRiskLevel = "medium"
    conclusion: str = Field(min_length=1, max_length=6000)
    recommendation: str = Field(min_length=1, max_length=6000)
    evidence: list[dict] = Field(default_factory=list, max_length=20)
    status: Literal["draft", "published"] = "published"

    @field_validator("conclusion", "recommendation")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("内容不能为空")
        return normalized


class AdminExpertReviewUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: AdminRiskLevel | None = None
    conclusion: str | None = Field(default=None, min_length=1, max_length=6000)
    recommendation: str | None = Field(default=None, min_length=1, max_length=6000)
    evidence: list[dict] | None = Field(default=None, max_length=20)
    status: AdminReviewStatus | None = None

    @field_validator("conclusion", "recommendation")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("内容不能为空")
        return normalized

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


CaseSeverity = Literal["low", "medium", "high", "critical"]
CaseStatus = Literal["needs_more_info", "suspected", "processing", "closed"]
BatchStatus = Literal["active", "finished", "archived"]


class FarmCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    location: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("养殖场名称不能为空")
        return normalized


class FarmUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    location: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)
    status: Literal["active", "archived"] | None = None


class FarmResponse(BaseModel):
    id: str
    name: str
    location: str | None
    notes: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class BatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    farm_id: UUID
    project_id: UUID | None = None
    batch_code: str | None = Field(default=None, max_length=80)
    variety: str | None = Field(default=None, max_length=80)
    instar: str | None = Field(default=None, max_length=40)
    start_date: date | None = None
    expected_cocooning_date: date | None = None
    population_count: int | None = Field(default=None, ge=0, le=10_000_000)
    notes: str | None = Field(default=None, max_length=2000)


class BatchResponse(BaseModel):
    id: str
    farm_id: str
    project_id: str | None
    farm_name: str
    batch_code: str | None
    variety: str | None
    instar: str | None
    start_date: date | None
    expected_cocooning_date: date | None
    population_count: int | None
    notes: str | None
    status: BatchStatus
    created_at: datetime
    updated_at: datetime


class BatchUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_code: str | None = Field(default=None, max_length=80)
    variety: str | None = Field(default=None, max_length=80)
    instar: str | None = Field(default=None, max_length=40)
    start_date: date | None = None
    expected_cocooning_date: date | None = None
    population_count: int | None = Field(default=None, ge=0, le=10_000_000)
    notes: str | None = Field(default=None, max_length=2000)
    status: BatchStatus | None = None


class DailyRecordUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_date: date
    temperature_celsius: Decimal | None = Field(default=None, ge=-30, le=80)
    humidity_percent: Decimal | None = Field(default=None, ge=0, le=100)
    feedings: int | None = Field(default=None, ge=0, le=30)
    leaf_amount_kg: Decimal | None = Field(default=None, ge=0, le=100000)
    sick_count: int | None = Field(default=None, ge=0, le=10_000_000)
    death_count: int | None = Field(default=None, ge=0, le=10_000_000)
    observations: str | None = Field(default=None, max_length=3000)
    management_notes: str | None = Field(default=None, max_length=3000)


class HusbandryAssetResponse(BaseModel):
    id: str
    file_id: str
    file_name: str
    file_type: Literal["image", "video"]
    mime_type: str
    storage_url: str | None
    file_size: int
    created_at: datetime


class DailyRecordResponse(BaseModel):
    id: str
    batch_id: str
    record_date: date
    temperature_celsius: float | None
    humidity_percent: float | None
    feedings: int | None
    leaf_amount_kg: float | None
    sick_count: int | None
    death_count: int | None
    observations: str | None
    management_notes: str | None
    created_at: datetime
    updated_at: datetime
    assets: list[HusbandryAssetResponse] = Field(default_factory=list)


class CaseCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    farm_id: UUID
    batch_id: UUID | None = None
    project_id: UUID | None = None
    source_conversation_id: UUID | None = None
    title: str = Field(min_length=1, max_length=120)
    occurred_on: date
    symptom_summary: str | None = Field(default=None, max_length=4000)
    suspected_disease: str | None = Field(default=None, max_length=160)
    severity: CaseSeverity = "medium"
    status: CaseStatus = "needs_more_info"
    diagnosis_summary: str | None = Field(default=None, max_length=6000)
    recommendation: str | None = Field(default=None, max_length=6000)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("病例标题不能为空")
        return normalized


class CaseUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    symptom_summary: str | None = Field(default=None, max_length=4000)
    suspected_disease: str | None = Field(default=None, max_length=160)
    severity: CaseSeverity | None = None
    status: CaseStatus | None = None
    diagnosis_summary: str | None = Field(default=None, max_length=6000)
    recommendation: str | None = Field(default=None, max_length=6000)


class CaseFollowUpCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_on: date
    action_taken: str | None = Field(default=None, max_length=3000)
    note: str | None = Field(default=None, max_length=4000)
    affected_count: int | None = Field(default=None, ge=0, le=10_000_000)
    death_count: int | None = Field(default=None, ge=0, le=10_000_000)
    next_follow_up_on: date | None = None


class CaseFollowUpUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_on: date | None = None
    action_taken: str | None = Field(default=None, max_length=3000)
    note: str | None = Field(default=None, max_length=4000)
    affected_count: int | None = Field(default=None, ge=0, le=10_000_000)
    death_count: int | None = Field(default=None, ge=0, le=10_000_000)
    next_follow_up_on: date | None = None


class CaseFollowUpResponse(BaseModel):
    id: str
    case_id: str
    observed_on: date
    action_taken: str | None
    note: str | None
    affected_count: int | None
    death_count: int | None
    next_follow_up_on: date | None
    created_at: datetime


class HusbandryExpertReviewResponse(BaseModel):
    id: str
    reviewer_name: str
    risk_level: Literal["low", "medium", "high", "critical"]
    conclusion: str
    recommendation: str
    evidence: list[dict] = Field(default_factory=list)
    version: int
    published_at: datetime


class CaseResponse(BaseModel):
    id: str
    farm_id: str
    batch_id: str | None
    project_id: str | None
    source_conversation_id: str | None
    farm_name: str
    batch_code: str | None
    title: str
    occurred_on: date
    symptom_summary: str | None
    suspected_disease: str | None
    severity: CaseSeverity
    status: CaseStatus
    diagnosis_summary: str | None
    recommendation: str | None
    source_snapshot: dict
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    follow_ups: list[CaseFollowUpResponse] = Field(default_factory=list)
    assets: list[HusbandryAssetResponse] = Field(default_factory=list)
    expert_reviews: list[HusbandryExpertReviewResponse] = Field(default_factory=list)


class HusbandryDashboardResponse(BaseModel):
    active_batch_count: int
    open_case_count: int
    due_follow_up_count: int
    today_record_count: int
    recent_cases: list[CaseResponse] = Field(default_factory=list)

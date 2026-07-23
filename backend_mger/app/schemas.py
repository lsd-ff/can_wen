from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdminIdentity(BaseModel):
    id: str
    email: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    mfa_enrolled: bool


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    admin: AdminIdentity


class MfaRequiredResponse(BaseModel):
    mfa_required: bool = True
    mfa_setup_required: bool = False
    mfa_ticket: str


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=256)
    device_name: str | None = Field(default=None, max_length=128)


class MfaVerifyRequest(StrictModel):
    mfa_ticket: str = Field(min_length=20)
    code: str = Field(min_length=6, max_length=16)
    device_name: str | None = Field(default=None, max_length=128)


class MfaTicketRequest(StrictModel):
    mfa_ticket: str = Field(min_length=20)


class MfaSetupResponse(BaseModel):
    mfa_ticket: str
    secret: str
    otpauth_uri: str


class RefreshRequest(StrictModel):
    refresh_token: str = Field(min_length=24)


class LogoutRequest(StrictModel):
    refresh_token: str = Field(min_length=24)


class InviteCreateRequest(StrictModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=80)
    role_keys: list[str] = Field(min_length=1, max_length=6)
    expires_in_hours: int = Field(default=72, ge=1, le=168)


class AdminRoleAssignmentRequest(StrictModel):
    role_keys: list[str] = Field(min_length=1, max_length=12)
    reason: str = Field(min_length=3, max_length=500)


class RoleUpsertRequest(StrictModel):
    key: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=3, max_length=500)
    permission_keys: list[str] = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=3, max_length=500)


class AcceptInviteRequest(StrictModel):
    token: str = Field(min_length=32)
    password: str = Field(min_length=12, max_length=256)


class WorkItemPatchRequest(StrictModel):
    action: Literal["claim", "release", "complete", "cancel"]
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=500)


class WorkItemTransferRequest(StrictModel):
    target_admin_id: str = Field(min_length=36, max_length=36)
    reason: str = Field(min_length=3, max_length=500)


class WorkItemBatchClaimRequest(StrictModel):
    item_ids: list[str] = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=3, max_length=500)


class RiskIncidentActionRequest(StrictModel):
    action: Literal["acknowledge", "start", "claim", "release", "resolve", "dismiss", "suppress", "reopen", "assign", "note"]
    note: str | None = Field(default=None, max_length=1200)
    assignee_id: str | None = Field(default=None, min_length=36, max_length=36)
    suppress_hours: int | None = Field(default=None, ge=1, le=720)


class UserStatusRequest(StrictModel):
    status: Literal["active", "disabled"]
    reason: str = Field(min_length=3, max_length=500)


class UserBatchActionRequest(StrictModel):
    user_ids: list[UUID] = Field(min_length=1, max_length=50)
    action: Literal["disable", "restore", "revoke_sessions"]
    reason: str = Field(min_length=3, max_length=500)


class RevokeSessionsRequest(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


class SensitiveAccessRequest(StrictModel):
    resource_type: Literal["conversation", "file", "husbandry_case"]
    resource_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=3, max_length=500)
    work_item_id: str | None = None


class SensitiveAccessResponse(BaseModel):
    id: str
    expires_at: datetime


class ModerationReportReviewRequest(StrictModel):
    status: Literal["reviewed", "dismissed"]
    action: Literal["none", "hide", "restore", "warn", "disable_author"] = "none"
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class VerificationReviewRequest(StrictModel):
    status: Literal["verified", "rejected"]
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class ContentStatusRequest(StrictModel):
    status: Literal["published", "hidden", "deleted"]
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class ExpertReviewRequest(StrictModel):
    source_message_id: str | None = None
    diagnosis_id: str | None = None
    risk_level: Literal["low", "medium", "high", "critical"]
    conclusion: str = Field(min_length=3, max_length=8000)
    recommendation: str = Field(min_length=3, max_length=8000)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    publish: bool = True
    reason: str = Field(min_length=3, max_length=500)


class DiagnosisReviewQueueRequest(StrictModel):
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    reason: str = Field(min_length=3, max_length=500)


class HusbandryReviewRequest(StrictModel):
    expected_version: int = Field(ge=0)
    risk_level: Literal["low", "medium", "high", "critical"]
    conclusion: str = Field(min_length=3, max_length=8000)
    recommendation: str = Field(min_length=3, max_length=8000)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    publish: bool = True
    reason: str = Field(min_length=3, max_length=500)


class HusbandryReviewQueueRequest(StrictModel):
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    reason: str = Field(min_length=3, max_length=500)


class ModelConfigRequest(StrictModel):
    key: str = Field(min_length=2, max_length=80)
    label: str = Field(min_length=2, max_length=120)
    model_id: str = Field(min_length=2, max_length=200)
    api_base_url: str = Field(min_length=8, max_length=500)
    api_key: str | None = Field(default=None, min_length=8, max_length=1000)
    clear_api_key: bool = False
    capability: Literal["chat", "vision", "embedding", "rerank", "speech"] = "chat"
    enabled: bool = True
    reason: str = Field(min_length=3, max_length=500)


class KnowledgeBuildRequest(StrictModel):
    targets: list[Literal["rag", "kg"]] = Field(default_factory=lambda: ["rag", "kg"], min_length=1, max_length=2)
    reason: str = Field(min_length=3, max_length=500)


class KnowledgePublishRequest(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


class KnowledgeReviewDecisionRequest(StrictModel):
    action: Literal["approve", "reject"]
    version: int = Field(ge=1)
    note: str = Field(min_length=3, max_length=2000)
    corrections: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSourceStatusRequest(StrictModel):
    status: Literal["draft", "disabled"]
    reason: str = Field(min_length=3, max_length=500)


class KnowledgeSourceDeleteRequest(StrictModel):
    confirmation_title: str = Field(min_length=2, max_length=240)
    reason: str = Field(min_length=3, max_length=500)


class JobActionRequest(StrictModel):
    action: Literal["retry", "cancel"]
    reason: str = Field(min_length=3, max_length=500)


class SystemSettingRequest(StrictModel):
    value: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=500)


class ReasonRequest(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


class AssetLifecycleRequest(ReasonRequest):
    action: Literal["quarantine", "restore", "delete"]


class TagRenameRequest(ReasonRequest):
    name: str = Field(min_length=1, max_length=80)


class TagMergeRequest(ReasonRequest):
    target_tag_id: str = Field(min_length=1, max_length=100)

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


DiagnosisMessageRole = Literal["user", "assistant", "system"]
DiagnosisMessageFeedback = Literal["like", "dislike"]
DiagnosisConversationShareVariant = Literal["summary", "full-record", "expert-review"]


class DiagnosisChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class DiagnosisChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    history: list[DiagnosisChatMessage] = Field(default_factory=list, max_length=20)


class DiagnosisChatResponse(BaseModel):
    reply: str
    model: str
    provider: str = "openai-compatible"


class DiagnosisVoiceTranscriptionResponse(BaseModel):
    text: str
    model: str
    provider: str = "openai-compatible"


class DiagnosisConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    model_config_id: UUID | None = None
    project_id: UUID | None = None


class DiagnosisConversationMessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    model_config_id: UUID | None = None


class DiagnosisConversationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("title cannot be empty")
        return normalized


class DiagnosisConversationShareCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)
    variant: DiagnosisConversationShareVariant = "summary"
    content_markdown: str = Field(min_length=1, max_length=80000)

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


class DiagnosisConversationPinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pinned: bool


class DiagnosisMessageUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("content cannot be empty")
        return normalized


class DiagnosisMessageFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: DiagnosisMessageFeedback | None = None
    feedback_reasons: list[str] = Field(default_factory=list, max_length=6)
    feedback_detail: str | None = Field(default=None, max_length=1000)

    @field_validator("feedback_reasons")
    @classmethod
    def normalize_feedback_reasons(cls, value: list[str]) -> list[str]:
        normalized_reasons: list[str] = []
        for reason in value:
            normalized = " ".join(reason.split())
            if normalized and normalized not in normalized_reasons:
                normalized_reasons.append(normalized)
        return normalized_reasons

    @field_validator("feedback_detail")
    @classmethod
    def normalize_feedback_detail(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class DiagnosisMessageRegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_config_id: UUID | None = None


class DiagnosisFileResponse(BaseModel):
    id: str
    file_name: str
    file_type: str
    mime_type: str
    storage_url: str | None = None
    file_size: int
    metadata: dict = Field(default_factory=dict)


class DiagnosisMessageResponse(BaseModel):
    id: str
    role: DiagnosisMessageRole
    content: str
    message_type: str
    status: str
    created_at: datetime
    displayed_at: datetime
    feedback: DiagnosisMessageFeedback | None = None
    feedback_reasons: list[str] = Field(default_factory=list)
    feedback_detail: str | None = None
    attachments: list[DiagnosisFileResponse] = Field(default_factory=list)


class DiagnosisConversationResponse(BaseModel):
    id: str
    project_id: str | None = None
    title: str
    summary: str | None = None
    conversation_type: str
    status: str
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    pinned_at: datetime | None = None


class DiagnosisConversationDetailResponse(DiagnosisConversationResponse):
    messages: list[DiagnosisMessageResponse]
    expert_reviews: list["DiagnosisExpertReviewResponse"] = Field(default_factory=list)


class DiagnosisExpertReviewResponse(BaseModel):
    id: str
    reviewer_name: str
    risk_level: Literal["low", "medium", "high", "critical"]
    conclusion: str
    recommendation: str
    evidence: list[dict] = Field(default_factory=list)
    version: int
    published_at: datetime


class DiagnosisConversationShareResponse(BaseModel):
    id: str
    conversation_id: str
    share_token: str
    share_url: str
    title: str
    variant: DiagnosisConversationShareVariant
    created_at: datetime
    expires_at: datetime | None = None


class PublicDiagnosisConversationShareResponse(BaseModel):
    title: str
    variant: DiagnosisConversationShareVariant
    content_markdown: str
    created_at: datetime
    updated_at: datetime


class DiagnosisConversationTurnResponse(BaseModel):
    conversation: DiagnosisConversationResponse
    user_message: DiagnosisMessageResponse
    assistant_message: DiagnosisMessageResponse
    model: str
    provider: str = "openai-compatible"


class DiagnosisMessageMutationResponse(BaseModel):
    conversation: DiagnosisConversationResponse
    message: DiagnosisMessageResponse

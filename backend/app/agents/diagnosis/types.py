from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated, Any, Literal, Protocol, TypedDict

from pydantic import BaseModel, Field

from app.core.config import Settings
from app.services.llm_client import OpenAICompatibleModelConfig


AgentRoute = Literal["rag", "kg", "hybrid", "clarify", "out_of_domain", "non_knowledge"]
RiskLevel = Literal["low", "medium", "high", "critical"]
RunStatus = Literal["completed", "waiting_for_user", "degraded", "failed"]
EvidenceType = Literal["rag_document", "kg_path", "multimodal_observation", "user_context"]


class QueryPlan(BaseModel):
    standalone_question: str
    domain: Literal["silkworm_disease", "silkworm_husbandry", "out_of_domain", "uncertain"] = "uncertain"
    intent: str = "knowledge_question"
    risk_level: RiskLevel = "low"
    route: AgentRoute = "hybrid"
    entities: list[str] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    dense_queries: list[str] = Field(default_factory=list)
    bm25_queries: list[str] = Field(default_factory=list)
    kg_terms: list[str] = Field(default_factory=list)
    route_reason: str = ""


class EvidenceItem(BaseModel):
    evidence_key: str
    evidence_type: EvidenceType
    retriever: str
    title: str
    content: str
    source_name: str | None = None
    source_uri: str | None = None
    source_version: str | None = None
    source_page: str | None = None
    score: float | None = None
    rank_order: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    evidence_id: str
    title: str
    source_name: str | None = None
    source_uri: str | None = None
    source_version: str | None = None
    source_page: str | None = None
    retrievers: list[str] = Field(default_factory=list)
    score: float | None = None
    excerpt: str = ""


class EvidenceAssessment(BaseModel):
    sufficient: bool = False
    conflict: bool = False
    conflict_summary: str = ""
    missing_information: list[str] = Field(default_factory=list)
    rationale: str = ""


class AgentPublicEvent(BaseModel):
    run_id: str | None = None
    sequence: int | None = None
    agent: str
    stage: str
    status: Literal["started", "progress", "completed", "waiting", "degraded", "failed"]
    title: str
    summary: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class DiagnosisAgentResult(BaseModel):
    answer: str
    status: RunStatus
    route: AgentRoute
    risk_level: RiskLevel
    original_question: str
    rewritten_question: str
    context_pack: dict[str, Any] = Field(default_factory=dict)
    evidence_status: Literal["sufficient", "insufficient", "conflicted", "not_required"]
    evidence: list[EvidenceItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class EventEmitter(Protocol):
    def __call__(
        self,
        *,
        agent: str,
        stage: str,
        status: str,
        title: str,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
        internal_payload: dict[str, Any] | None = None,
    ) -> AgentPublicEvent: ...


class AgentState(TypedDict, total=False):
    run_id: str
    original_question: str
    conversation_summary: str
    history: list[dict[str, str]]
    structured_data: dict[str, Any]
    multimodal_observations: dict[str, Any]
    pending_slots: list[str]
    user_preferences: dict[str, Any]
    settings: Settings
    model_config: OpenAICompatibleModelConfig
    emit: EventEmitter
    knowledge_snapshot: dict[str, Any]
    context_pack: dict[str, Any]
    query_plan: QueryPlan
    rag_evidence: list[EvidenceItem]
    kg_evidence: list[EvidenceItem]
    branch_metrics: Annotated[list[dict[str, Any]], operator.add]
    branch_errors: Annotated[list[str], operator.add]
    answer: str
    result: DiagnosisAgentResult

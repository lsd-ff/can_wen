from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictKnowledgeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DocumentChunk(StrictKnowledgeModel):
    stable_key: str
    ordinal: int = Field(ge=0)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    heading_path: list[str] = Field(default_factory=list)
    heading_level: int | None = Field(default=None, ge=1, le=6)
    content: str = Field(min_length=1)
    content_sha256: str
    token_count: int = Field(ge=1)
    quality_score: float = Field(ge=0, le=1)
    quality_flags: list[str] = Field(default_factory=list)
    split_strategy: str


class QAExtraction(StrictKnowledgeModel):
    question: str = Field(min_length=2, max_length=500)
    answer: str = Field(min_length=2, max_length=8000)
    evidence: str = Field(min_length=1, max_length=8000)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    knowledge_types: list[
        Literal["concept", "symptom", "cause", "step", "parameter", "diagnosis", "prevention", "other"]
    ] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)

    @field_validator("keywords")
    @classmethod
    def unique_keywords(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))[:20]


class QAExtractionBatch(StrictKnowledgeModel):
    items: list[QAExtraction] = Field(default_factory=list, max_length=12)


class TripleExtraction(StrictKnowledgeModel):
    subject_name: str = Field(min_length=1, max_length=300)
    subject_type: str = Field(min_length=1, max_length=80)
    relation: str = Field(min_length=1, max_length=80)
    object_name: str = Field(min_length=1, max_length=500)
    object_type: str = Field(min_length=1, max_length=80)
    evidence: str = Field(min_length=1, max_length=8000)
    confidence: float = Field(default=0.8, ge=0, le=1)


class TripleExtractionBatch(StrictKnowledgeModel):
    items: list[TripleExtraction] = Field(default_factory=list, max_length=80)


class ExpertAssessment(StrictKnowledgeModel):
    approved: bool
    score: float = Field(ge=0, le=1)
    risk_flags: list[str] = Field(default_factory=list)
    reason: str = Field(default="", max_length=2000)
    corrected_payload: dict[str, Any] | None = None


class SemanticSegments(StrictKnowledgeModel):
    segments: list[str] = Field(min_length=2, max_length=30)


class BuildState(TypedDict, total=False):
    build_run_id: str
    source_version_id: str
    targets: list[str]
    markdown: str
    markdown_uri: str
    chunks: list[dict[str, Any]]
    qa_items: list[dict[str, Any]]
    rag_failures: list[dict[str, Any]]
    triples: list[dict[str, Any]]
    kg_failures: list[dict[str, Any]]
    review_count: int
    metrics: dict[str, Any]
    agent_plan: dict[str, Any]
    rag_route: str
    rag_revision_round: int
    rag_risk_summary: dict[str, int]
    kg_route: str
    kg_revision_round: int
    kg_risk_summary: dict[str, int]
    error: str

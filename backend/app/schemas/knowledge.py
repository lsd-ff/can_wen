from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeGraphSourceResponse(BaseModel):
    title: str
    version: str | None = None
    url: str | None = None
    published_at: str | None = None


class KnowledgeGraphNodeResponse(BaseModel):
    id: str
    name: str
    type: str
    type_label: str
    degree: int = 0


class KnowledgeGraphEdgeResponse(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    relation_key: str
    has_evidence: bool = False


class KnowledgeGraphSchemaItemResponse(BaseModel):
    key: str
    label: str
    count: int


class KnowledgeGraphSchemaResponse(BaseModel):
    total_nodes: int = 0
    total_relationships: int = 0
    node_types: list[KnowledgeGraphSchemaItemResponse] = Field(default_factory=list)
    relationship_types: list[KnowledgeGraphSchemaItemResponse] = Field(default_factory=list)


class KnowledgeGraphResultResponse(BaseModel):
    node_count: int = 0
    relationship_count: int = 0
    matching_relationships: int = 0
    limit: int
    truncated: bool = False
    query: str = ""


class KnowledgeGraphSnapshotResponse(BaseModel):
    scope: Literal["curated", "curated_and_published"] = "curated"
    scope_label: str
    source_count: int = 0
    sources: list[KnowledgeGraphSourceResponse] = Field(default_factory=list)


class KnowledgeGraphResponse(BaseModel):
    available: bool
    reason: str | None = None
    nodes: list[KnowledgeGraphNodeResponse] = Field(default_factory=list)
    edges: list[KnowledgeGraphEdgeResponse] = Field(default_factory=list)
    schema_: KnowledgeGraphSchemaResponse = Field(alias="schema")
    result: KnowledgeGraphResultResponse
    snapshot: KnowledgeGraphSnapshotResponse


class KnowledgeGraphNodeDetailResponse(BaseModel):
    id: str
    name: str
    type: str
    type_label: str
    degree: int = 0
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    english_label: str | None = None
    evidence: str | None = None
    source_documents: list[str] = Field(default_factory=list)
    confidence: str | float | int | None = None
    review_status: str | None = None


class KnowledgeGraphRelationshipDetailResponse(BaseModel):
    id: str
    source: str
    source_name: str
    target: str
    target_name: str
    relation: str
    relation_key: str
    evidence: str | None = None
    source_documents: list[str] = Field(default_factory=list)
    confidence: str | float | int | None = None
    review_status: str | None = None
    source_record: KnowledgeGraphSourceResponse | None = None


class KnowledgeGraphDetailResponse(BaseModel):
    kind: Literal["node", "relationship"]
    node: KnowledgeGraphNodeDetailResponse | None = None
    relationship: KnowledgeGraphRelationshipDetailResponse | None = None

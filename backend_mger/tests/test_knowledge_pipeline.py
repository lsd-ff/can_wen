from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from starlette.requests import Request

import app.routes.knowledge as knowledge_routes
from app.config import Settings
from app.knowledge.deletion import KnowledgeSourceDeletionService
from app.knowledge.indexes import Neo4jKnowledgeGraph, OpenSearchQAIndex, QdrantQAIndex
from app.knowledge.markdown import AdaptiveMarkdownChunker, estimate_tokens
from app.knowledge.mineru import MinerUClient
from app.knowledge.extractors import REFINABLE_QA_FLAGS, KnowledgeExtractor
from app.knowledge.model_gateway import ModelGateway, ModelGatewayError
from app.knowledge.quality import validate_qa, validate_triple
from app.knowledge.schema import (
    KG_NEO4J_LABELS,
    KG_NEO4J_RELATION_TYPES,
    KG_RELATIONS,
    KG_SCHEMA_LABELS,
    SilkwormGlossary,
)
from app.knowledge.storage import KnowledgeStorage
from app.knowledge.types import DocumentChunk, QAExtraction, QAExtractionBatch, TripleExtraction
from app.knowledge.workflow import KnowledgeBuildWorkflow, KnowledgeGraphBuildAgent, _quality_route, build_document_plan
from app.models import BackgroundJob, KnowledgeBuildEvent, KnowledgeBuildRun, KnowledgeChunk, KnowledgePublication, KnowledgeQAItem, KnowledgeReviewItem, KnowledgeSource, KnowledgeSourceVersion, KnowledgeTriple
from app.routes.knowledge import _agent_runtime, _build_dict, _extraction_dict, decide_review, update_source_status
from app.routes.system import patch_job
from app.schemas import JobActionRequest, KnowledgeReviewDecisionRequest, KnowledgeSourceStatusRequest


class ExtractionDetailSession:
    def __init__(self, values: dict[type, object]):
        self.values = values

    def get(self, model: type, _resource_id):
        return self.values.get(model)

    @staticmethod
    def scalar(_statement):
        return None


class JobActionSession:
    def __init__(self, values: dict[tuple[type, object], object], scalar_values: list[int] | None = None):
        self.values = values
        self.scalar_values = list(scalar_values or [])
        self.added: list[object] = []
        self.commit_count = 0

    def get(self, model: type, resource_id):
        return self.values.get((model, resource_id))

    def scalar(self, _statement):
        return self.scalar_values.pop(0) if self.scalar_values else 0

    def add(self, item: object) -> None:
        self.added.append(item)

    def commit(self) -> None:
        self.commit_count += 1


def _job_request(job_id) -> Request:
    return Request({"type": "http", "method": "PATCH", "path": f"/jobs/{job_id}", "headers": []})


def _background_job(job_id, job_type: str, job_status: str, payload: dict) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=job_id,
        job_type=job_type,
        status=job_status,
        progress=42,
        payload=payload,
        result={"stale": True},
        error_message="previous failure" if job_status == "failed" else None,
        requested_by_id=None,
        started_at=now,
        completed_at=now if job_status == "failed" else None,
        created_at=now,
        updated_at=now,
    )


def test_cancelling_build_job_unlocks_source_and_preserves_trace() -> None:
    job_id, run_id, version_id, source_id, actor_id = (uuid4() for _ in range(5))
    job = _background_job(job_id, "knowledge_build", "queued", {"build_run_id": str(run_id)})
    run = SimpleNamespace(
        id=run_id,
        source_version_id=version_id,
        status="queued",
        current_node="queued",
        progress=0,
        error_message=None,
        started_at=None,
        completed_at=None,
        updated_at=datetime.now(UTC),
    )
    version = SimpleNamespace(id=version_id, source_id=source_id)
    source = SimpleNamespace(id=source_id, status="processing", published_version_id=None, updated_at=datetime.now(UTC))
    session = JobActionSession(
        {
            (BackgroundJob, job_id): job,
            (KnowledgeBuildRun, run_id): run,
            (KnowledgeSourceVersion, version_id): version,
            (KnowledgeSource, source_id): source,
        },
        scalar_values=[0, 0],
    )

    result = patch_job(
        job_id,
        JobActionRequest(action="cancel", reason="停止隔离验收任务"),
        _job_request(job_id),
        db=session,  # type: ignore[arg-type]
        actor=SimpleNamespace(id=actor_id),
    )

    assert result["status"] == "cancelled"
    assert run.status == "cancelled" and run.current_node == "cancelled"
    assert source.status == "draft"
    assert any(isinstance(item, KnowledgeBuildEvent) and item.node == "cancelled" for item in session.added)


def test_cancelling_publish_job_keeps_build_ready_to_publish() -> None:
    job_id, run_id, publication_id, actor_id = (uuid4() for _ in range(4))
    job = _background_job(
        job_id,
        "knowledge_publish",
        "running",
        {"build_run_id": str(run_id), "publication_id": str(publication_id)},
    )
    run = SimpleNamespace(
        id=run_id,
        status="publishing",
        current_node="opensearch",
        progress=100,
        error_message=None,
        completed_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    publication = SimpleNamespace(
        id=publication_id,
        build_run_id=run_id,
        status="staging",
        error_message=None,
        updated_at=datetime.now(UTC),
    )
    session = JobActionSession(
        {
            (BackgroundJob, job_id): job,
            (KnowledgeBuildRun, run_id): run,
            (KnowledgePublication, publication_id): publication,
        }
    )

    result = patch_job(
        job_id,
        JobActionRequest(action="cancel", reason="停止本次发布验收"),
        _job_request(job_id),
        db=session,  # type: ignore[arg-type]
        actor=SimpleNamespace(id=actor_id),
    )

    assert result["status"] == "cancelled"
    assert publication.status == "rolled_back"
    assert run.status == "succeeded" and run.current_node == "ready_to_publish"
    assert any(isinstance(item, KnowledgeBuildEvent) and item.node == "publish_cancelled" for item in session.added)


def test_retrying_failed_build_resets_stale_state_and_locks_source(monkeypatch) -> None:
    job_id, run_id, version_id, source_id, actor_id = (uuid4() for _ in range(5))
    job = _background_job(job_id, "knowledge_build", "failed", {"build_run_id": str(run_id)})
    run = SimpleNamespace(
        id=run_id,
        source_version_id=version_id,
        status="failed",
        current_node="kg_extract",
        progress=42,
        error_message="model timeout",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    version = SimpleNamespace(id=version_id, source_id=source_id)
    source = SimpleNamespace(id=source_id, status="failed", published_version_id=None, updated_at=datetime.now(UTC))
    session = JobActionSession(
        {
            (BackgroundJob, job_id): job,
            (KnowledgeBuildRun, run_id): run,
            (KnowledgeSourceVersion, version_id): version,
            (KnowledgeSource, source_id): source,
        }
    )
    dispatched: list[object] = []
    monkeypatch.setattr("app.knowledge.tasks.dispatch_background_job", lambda value: dispatched.append(value))

    result = patch_job(
        job_id,
        JobActionRequest(action="retry", reason="依赖恢复后重新执行"),
        _job_request(job_id),
        db=session,  # type: ignore[arg-type]
        actor=SimpleNamespace(id=actor_id),
    )

    assert result["status"] == "queued" and result["result"] == {}
    assert run.status == "queued" and run.current_node == "retry_queued"
    assert run.started_at is None and run.completed_at is None
    assert source.status == "processing"
    assert dispatched == [job_id]


def test_retry_rejects_job_types_without_an_executor() -> None:
    job_id, actor_id = uuid4(), uuid4()
    job = _background_job(job_id, "legacy_export", "failed", {})
    session = JobActionSession({(BackgroundJob, job_id): job})

    with pytest.raises(Exception) as caught:
        patch_job(
            job_id,
            JobActionRequest(action="retry", reason="尝试重试旧任务"),
            _job_request(job_id),
            db=session,  # type: ignore[arg-type]
            actor=SimpleNamespace(id=actor_id),
        )

    assert getattr(caught.value, "status_code", None) == 409
    assert job.status == "failed"


def test_all_extractions_include_auto_approved_qa_without_review_queue_entry() -> None:
    now = datetime.now(UTC)
    run_id, chunk_id, version_id, source_id, qa_id = (uuid4() for _ in range(5))
    qa = KnowledgeQAItem(
        id=qa_id,
        build_run_id=run_id,
        chunk_id=chunk_id,
        question="家蚕核型多角体病有什么典型症状？",
        question_sha256="question-hash",
        answer="病蚕体躯肿胀，体壁乳白且容易破裂。",
        evidence_text="病蚕体躯肿胀，体壁乳白。",
        keywords=["核型多角体病", "症状"],
        knowledge_types=["症状"],
        extraction_confidence=0.96,
        rule_score=0.94,
        expert_score=0.92,
        expert_assessment={"verdict": "pass"},
        risk_flags=[],
        review_status="approved",
        review_note=None,
        reviewed_at=None,
        published_at=None,
        qdrant_point_id=None,
        opensearch_document_id=None,
        created_at=now,
        updated_at=now,
    )
    session = ExtractionDetailSession(
        {
            KnowledgeChunk: SimpleNamespace(
                id=chunk_id,
                source_version_id=version_id,
                ordinal=0,
                heading_path=["病毒病", "核型多角体病"],
                start_line=10,
                end_line=22,
                content="病蚕体躯肿胀，体壁乳白。",
                token_count=18,
                quality_score=1.0,
                quality_flags=[],
                split_strategy="h3_complete",
            ),
            KnowledgeSourceVersion: SimpleNamespace(id=version_id, source_id=source_id, version="v1"),
            KnowledgeSource: SimpleNamespace(id=source_id, title="家蚕病理学"),
            KnowledgeBuildRun: SimpleNamespace(id=run_id, status="succeeded", targets=["rag"], created_at=now),
        }
    )

    result = _extraction_dict(session, qa, include_content=True)  # type: ignore[arg-type]

    assert result["item_type"] == "qa"
    assert result["status"] == "approved"
    assert result["manual_review"] is None
    assert result["candidate"]["answer"] == qa.answer
    assert result["source"]["title"] == "家蚕病理学"


def test_all_extractions_include_full_kg_triple_and_traceability() -> None:
    now = datetime.now(UTC)
    run_id, chunk_id, version_id, source_id, triple_id = (uuid4() for _ in range(5))
    triple = KnowledgeTriple(
        id=triple_id,
        build_run_id=run_id,
        chunk_id=chunk_id,
        triple_key="triple-hash",
        subject_name="核型多角体病",
        subject_type="Disease",
        subject_canonical_name="核型多角体病",
        relation="HAS_SYMPTOM",
        object_name="体躯肿胀",
        object_type="Symptom",
        object_canonical_name="体躯肿胀",
        evidence_text="核型多角体病的病蚕体躯肿胀。",
        extraction_confidence=0.93,
        rule_score=0.91,
        expert_score=0.9,
        expert_assessment={"verdict": "pass"},
        risk_flags=[],
        resolution_metadata={"canonicalized": True},
        review_status="approved",
        review_note=None,
        reviewed_at=None,
        neo4j_synced_at=None,
        published_at=None,
        created_at=now,
        updated_at=now,
    )
    session = ExtractionDetailSession(
        {
            KnowledgeChunk: SimpleNamespace(
                id=chunk_id,
                source_version_id=version_id,
                ordinal=1,
                heading_path=["病毒病", "核型多角体病"],
                start_line=23,
                end_line=30,
                content="核型多角体病的病蚕体躯肿胀。",
                token_count=20,
                quality_score=1.0,
                quality_flags=[],
                split_strategy="h3_complete",
            ),
            KnowledgeSourceVersion: SimpleNamespace(id=version_id, source_id=source_id, version="v1"),
            KnowledgeSource: SimpleNamespace(id=source_id, title="常见蚕病防治"),
            KnowledgeBuildRun: SimpleNamespace(id=run_id, status="succeeded", targets=["kg"], created_at=now),
        }
    )

    result = _extraction_dict(session, triple, include_content=True)  # type: ignore[arg-type]

    assert result["item_type"] == "triple"
    assert result["candidate"]["relation"] == "HAS_SYMPTOM"
    assert result["candidate"]["resolution_metadata"] == {"canonicalized": True}
    assert result["chunk"]["heading_path"] == ["病毒病", "核型多角体病"]


def test_build_payload_includes_its_latest_publication_snapshot() -> None:
    now = datetime.now(UTC)
    run_id, version_id, source_id, publication_id = (uuid4() for _ in range(4))
    version = SimpleNamespace(id=version_id, source_id=source_id, version="v1")
    source = SimpleNamespace(id=source_id, title="家蚕病理学")
    publication = SimpleNamespace(
        id=publication_id,
        build_run_id=run_id,
        version="v1",
        status="published",
        qdrant_collection="silkworm_qa",
        opensearch_index="silkworm_qa",
        neo4j_database="2714bfde",
        counts={"qa": 12, "triples": 8},
        error_message=None,
        published_at=now,
        created_at=now,
        updated_at=now,
    )

    class FakeSession:
        scalar_calls = 0

        @staticmethod
        def get(model, resource_id):
            if model is KnowledgeSourceVersion and resource_id == version_id:
                return version
            if model is KnowledgeSource and resource_id == source_id:
                return source
            return None

        def scalar(self, _statement):
            self.scalar_calls += 1
            return 0 if self.scalar_calls == 1 else publication

    run = SimpleNamespace(
        id=run_id,
        source_version_id=version_id,
        job_id=uuid4(),
        targets=["rag", "kg"],
        status="succeeded",
        current_node="published",
        progress=100,
        metrics={"qa_count": 12, "triple_count": 8},
        error_message=None,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )

    result = _build_dict(FakeSession(), run)  # type: ignore[arg-type]

    assert result["publication"]["status"] == "published"
    assert result["publication"]["counts"] == {"qa": 12, "triples": 8}
    assert result["open_review_count"] == 0


def test_source_status_change_is_blocked_while_a_build_is_active() -> None:
    source_id = uuid4()
    source = SimpleNamespace(id=source_id, title="验收文档", status="processing", updated_at=None)

    class FakeSession:
        @staticmethod
        def get(model, resource_id):
            return source if model is KnowledgeSource and resource_id == source_id else None

        @staticmethod
        def scalar(_statement):
            return 1

    request = Request({"type": "http", "method": "PATCH", "path": f"/sources/{source_id}/status", "headers": []})

    with pytest.raises(Exception) as caught:
        update_source_status(
            source_id,
            KnowledgeSourceStatusRequest(status="disabled", reason="等待构建结束后再停用"),
            request,
            db=FakeSession(),  # type: ignore[arg-type]
            actor=SimpleNamespace(id=uuid4()),
        )

    assert getattr(caught.value, "status_code", None) == 409
    assert source.status == "processing"


def test_rejecting_invalid_review_does_not_run_approval_corrections(monkeypatch) -> None:
    now = datetime.now(UTC)
    run_id, chunk_id, review_id, qa_id, actor_id = (uuid4() for _ in range(5))
    review = KnowledgeReviewItem(
        id=review_id,
        build_run_id=run_id,
        item_type="qa",
        resource_id=qa_id,
        status="open",
        priority="medium",
        reason_codes=["evidence_missing"],
        model_assessment={},
        version=1,
        created_at=now,
        updated_at=now,
    )
    candidate = KnowledgeQAItem(
        id=qa_id,
        build_run_id=run_id,
        chunk_id=chunk_id,
        question="待驳回问题",
        question_sha256="question-hash",
        answer="没有可靠依据的答案",
        evidence_text="不在来源 Chunk 中的证据",
        keywords=[],
        knowledge_types=[],
        extraction_confidence=0.2,
        rule_score=0.1,
        expert_score=0.1,
        expert_assessment={},
        risk_flags=["evidence_missing"],
        review_status="needs_review",
        created_at=now,
        updated_at=now,
    )

    class FakeSession:
        committed = False

        @staticmethod
        def get(model, resource_id):
            return review if model is KnowledgeReviewItem and resource_id == review_id else None

        @staticmethod
        def flush():
            return None

        def commit(self):
            self.committed = True

        @staticmethod
        def rollback():
            return None

    session = FakeSession()
    monkeypatch.setattr(knowledge_routes, "_review_dict", lambda _db, item, include_content: {"status": item.status, "version": item.version})
    monkeypatch.setattr(knowledge_routes, "_candidate", lambda _db, _item: candidate)
    monkeypatch.setattr(knowledge_routes, "_refresh_run_review_state", lambda _db, _run_id: None)
    monkeypatch.setattr(knowledge_routes, "write_audit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        knowledge_routes,
        "_apply_corrections",
        lambda *_args, **_kwargs: pytest.fail("reject must not validate or apply candidate corrections"),
    )
    payload = KnowledgeReviewDecisionRequest(
        action="reject",
        version=1,
        note="证据缺失，予以驳回",
        corrections={"evidence": "仍然无效"},
    )
    request = Request({"type": "http", "method": "PATCH", "path": f"/reviews/{review_id}", "headers": []})

    result = decide_review(
        review_id,
        payload,
        request,
        db=session,  # type: ignore[arg-type]
        actor=SimpleNamespace(id=actor_id),
    )

    assert result == {"status": "rejected", "version": 2}
    assert candidate.review_status == "rejected"
    assert review.decision_note == "证据缺失，予以驳回"
    assert session.committed is True


def test_neo4j_configuration_rejects_local_fallback() -> None:
    local = Settings(
        neo4j_uri="bolt://127.0.0.1:7687",
        neo4j_user="neo4j",
        neo4j_password="password",
        neo4j_database="neo4j",
    )
    with pytest.raises(RuntimeError, match="Aura"):
        local.require_neo4j_aura()

    aura = Settings(
        neo4j_uri="neo4j+s://example.databases.neo4j.io",
        neo4j_user="example",
        neo4j_password="password",
        neo4j_database="example",
    )
    aura.require_neo4j_aura()


def test_neo4j_schema_reuses_existing_name_indexes_without_constraint_conflicts() -> None:
    calls: list[str] = []

    class FakeResult(list):
        @staticmethod
        def consume() -> None:
            return None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, cypher: str, **_parameters):
            calls.append(cypher)
            if cypher.startswith("SHOW INDEXES"):
                return FakeResult([{"labelsOrTypes": [KG_NEO4J_LABELS["Disease"]], "properties": ["name"]}])
            return FakeResult()

    class FakeDriver:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def verify_connectivity() -> None:
            return None

        def session(self, **_kwargs):
            return FakeSession()

    graph = Neo4jKnowledgeGraph(Settings())
    graph._driver = lambda: FakeDriver()  # type: ignore[method-assign]
    graph.ensure_schema()

    schema_writes = [call for call in calls if call.startswith("CREATE")]
    assert len(schema_writes) == len(KG_SCHEMA_LABELS) - 1
    assert all(call.startswith("CREATE INDEX") for call in schema_writes)
    assert all("CONSTRAINT" not in call for call in schema_writes)
    assert all("FOR (n:`疾病`)" not in call for call in schema_writes)


def test_schema_remains_exactly_the_approved_domain_schema() -> None:
    assert len(KG_SCHEMA_LABELS) == 11
    assert len(KG_RELATIONS) == 10
    assert "Evidence" not in KG_SCHEMA_LABELS
    assert "Document" not in KG_SCHEMA_LABELS
    assert "DrugParameter" not in KG_SCHEMA_LABELS
    assert set(subject for subject, _ in KG_RELATIONS.values()) == {"Disease"}
    assert set(KG_NEO4J_LABELS) == set(KG_SCHEMA_LABELS)
    assert set(KG_NEO4J_RELATION_TYPES) == set(KG_RELATIONS)
    assert KG_NEO4J_LABELS["Disease"] == "疾病"
    assert KG_NEO4J_RELATION_TYPES["HAS_SYMPTOM"] == "表现症状"


def test_neo4j_preview_does_not_shadow_driver_query_argument() -> None:
    seen: dict = {}

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, cypher: str, **parameters):
            seen["cypher"] = cypher
            seen["parameters"] = parameters
            return []

    class FakeDriver:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def session(self, **_kwargs):
            return FakeSession()

    graph = Neo4jKnowledgeGraph(Settings())
    graph._driver = lambda: FakeDriver()  # type: ignore[method-assign]

    assert graph.preview(query="核型多角体病", limit=5) == {"nodes": [], "edges": []}
    assert seen["parameters"] == {"search_text": "核型多角体病", "limit": 5}


def test_neo4j_explore_returns_full_schema_and_mapped_graph() -> None:
    class FakeResult(list):
        def single(self, strict: bool = False):
            if strict and len(self) != 1:
                raise ValueError("expected one record")
            return self[0] if self else None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, cypher: str, **_parameters):
            if "WITH s, r, o ORDER BY elementId(r)" in cypher:
                return FakeResult([
                    {
                        "source_id": "disease-1",
                        "source_type": "疾病",
                        "source_name": "核型多角体病",
                        "relation": "表现症状",
                        "relation_id": "relation-1",
                        "target_id": "symptom-1",
                        "target_type": "典型病征",
                        "target_name": "体躯肿胀",
                    }
                ])
            if "RETURN node_types, relationship_types, property_keys" in cypher:
                return FakeResult([
                    {
                        "node_types": [{"label": "疾病", "count": 1}, {"label": "典型病征", "count": 1}],
                        "relationship_types": [{"relation": "表现症状", "count": 1}],
                        "property_keys": ["id", "name"],
                    }
                ])
            raise AssertionError(f"unexpected query: {cypher}")

    class FakeDriver:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def session(self, **_kwargs):
            return FakeSession()

    graph = Neo4jKnowledgeGraph(Settings())
    graph._driver = lambda: FakeDriver()  # type: ignore[method-assign]
    result = graph.explore(limit=5000)

    assert result["result"] == {
        "node_count": 2,
        "relationship_count": 1,
        "matching_relationships": 1,
        "limit": 5000,
        "truncated": False,
        "query": "",
    }
    assert result["nodes"][0]["type"] == "Disease"
    assert result["edges"][0]["relation_key"] == "HAS_SYMPTOM"
    assert result["schema"]["total_nodes"] == 2
    assert result["schema"]["property_keys"] == ["id", "name"]


def test_neo4j_detail_returns_properties_on_demand() -> None:
    class FakeResult(list):
        def single(self, strict: bool = False):
            del strict
            return self[0] if self else None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, cypher: str, **_parameters):
            if "OPTIONAL MATCH (n)-[r]-()" in cypher:
                return FakeResult([{"id": "node-1", "type": "疾病", "name": "核型多角体病", "properties": {"name": "核型多角体病", "别名": ["NPV"]}, "degree": 4}])
            if "WHERE elementId(r) = $element_id" in cypher:
                return FakeResult([{"id": "edge-1", "relation": "表现症状", "properties": {"latest_evidence": "病蚕体躯肿胀"}, "source_id": "node-1", "source_name": "核型多角体病", "target_id": "node-2", "target_name": "体躯肿胀"}])
            raise AssertionError(f"unexpected query: {cypher}")

    class FakeDriver:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def session(self, **_kwargs):
            return FakeSession()

    graph = Neo4jKnowledgeGraph(Settings())
    graph._driver = lambda: FakeDriver()  # type: ignore[method-assign]

    node = graph.detail("node-1", "node")
    relationship = graph.detail("edge-1", "relationship")
    assert node and node["node"]["type"] == "Disease"
    assert node["node"]["properties"]["别名"] == ["NPV"]
    assert relationship and relationship["relationship"]["relation_key"] == "HAS_SYMPTOM"
    assert relationship["relationship"]["evidence"] == "病蚕体躯肿胀"


def test_neo4j_boundary_maps_internal_schema_to_existing_chinese_graph() -> None:
    seen: dict = {}

    class FakeResult:
        @staticmethod
        def consume() -> None:
            return None

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, cypher: str, parameters=None, **_kwargs):
            seen["cypher"] = cypher
            seen["parameters"] = parameters
            return FakeResult()

    class FakeDriver:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def session(self, **_kwargs):
            return FakeSession()

    graph = Neo4jKnowledgeGraph(Settings())
    graph._driver = lambda: FakeDriver()  # type: ignore[method-assign]
    graph.upsert_triple(
        {
            "subject_name": "核型多角体病",
            "subject_type": "Disease",
            "subject_canonical_name": "核型多角体病",
            "relation": "HAS_SYMPTOM",
            "object_name": "体壁乳白",
            "object_type": "Symptom",
            "object_canonical_name": "体壁乳白",
            "evidence": "核型多角体病可见体壁乳白",
            "source_version_id": "version-1",
            "chunk_id": "chunk-1",
            "evidence_sha256": "evidence-1",
            "publication_id": "publication-1",
            "provenance": {},
        }
    )

    assert "MERGE (s:`疾病`" in seen["cypher"]
    assert "MERGE (o:`典型病征`" in seen["cypher"]
    assert "[r:`表现症状`]" in seen["cypher"]
    assert "r.canwen_managed = true" in seen["cypher"]
    assert seen["parameters"]["subject_id"].startswith("AUTO_Disease_")
    assert seen["parameters"]["object_id"].startswith("AUTO_Symptom_")


def test_neo4j_source_cleanup_removes_only_canwen_owned_provenance() -> None:
    calls: list[tuple[str, dict]] = []

    class FakeResult:
        def __init__(self, row: dict):
            self.row = row

        def single(self):
            return self.row

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, cypher: str, **parameters):
            calls.append((cypher, parameters))
            if "AS updated" in cypher:
                return FakeResult({"updated": 2})
            if "MATCH (n)" in cypher:
                return FakeResult({"deleted": 1})
            return FakeResult({"deleted": 3, "candidate_node_ids": ["node-1", "node-2"]})

    class FakeDriver:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def session(self, **_kwargs):
            return FakeSession()

    graph = Neo4jKnowledgeGraph(Settings())
    graph._driver = lambda: FakeDriver()  # type: ignore[method-assign]
    result = graph.delete_source_artifacts(["version-1", "version-1"], ["publication-1"])

    assert result == {"relationships_deleted": 3, "relationships_updated": 2, "nodes_deleted": 1}
    assert "coalesce(r.canwen_managed, false) = true" in calls[0][0]
    assert calls[0][1]["source_version_ids"] == ["version-1"]
    assert calls[1][1]["publication_ids"] == ["publication-1"]
    assert "STARTS WITH 'AUTO_'" in calls[2][0]
    assert calls[2][1]["candidate_node_ids"] == ["node-1", "node-2"]


def test_vector_indexes_delete_idempotently_when_storage_is_absent() -> None:
    class FakeQdrantClient:
        deleted = False

        @staticmethod
        def collection_exists(_name):
            return False

        def delete(self, **_kwargs):
            self.deleted = True

    qdrant_client = FakeQdrantClient()
    qdrant = QdrantQAIndex(Settings())
    qdrant._client = lambda: qdrant_client  # type: ignore[method-assign]
    qdrant.delete(["point-1"])
    assert qdrant_client.deleted is False

    class FakeIndices:
        refreshed = False

        @staticmethod
        def exists(**_kwargs):
            return False

        def refresh(self, **_kwargs):
            self.refreshed = True

    class FakeOpenSearchClient:
        def __init__(self):
            self.indices = FakeIndices()
            self.deleted = False

        def delete(self, **_kwargs):
            self.deleted = True

    open_client = FakeOpenSearchClient()
    opensearch = OpenSearchQAIndex(Settings(), tokenizer=SimpleNamespace(tokenize=lambda value: value))
    opensearch._client = lambda: open_client  # type: ignore[method-assign]
    opensearch.delete_many(["document-1"])
    assert open_client.deleted is False
    assert open_client.indices.refreshed is False


def test_source_deletion_cleans_every_derived_store_before_database_cascade() -> None:
    source_id, version_id, run_id, qa_id, triple_id, publication_id = (uuid4() for _ in range(6))
    source = KnowledgeSource(
        id=source_id,
        title="待删除测试文档",
        source_type="document",
        status="ready",
        version="v1",
        storage_uri="local://source/original.md",
        metadata_={},
    )
    version = SimpleNamespace(
        id=version_id,
        original_storage_uri="local://source/original.md",
        markdown_storage_uri="local://source/parsed.md",
    )
    run = SimpleNamespace(id=run_id, status="succeeded")
    qa = SimpleNamespace(
        id=qa_id,
        qdrant_point_id=str(qa_id),
        opensearch_document_id=str(qa_id),
    )
    triple = SimpleNamespace(id=triple_id, neo4j_synced_at=datetime.now(UTC), review_status="published")
    publication = SimpleNamespace(id=publication_id)
    outbox = [
        SimpleNamespace(target="qdrant", aggregate_type="qa", aggregate_id=qa_id),
        SimpleNamespace(target="opensearch", aggregate_type="qa", aggregate_id=qa_id),
        SimpleNamespace(target="neo4j", aggregate_type="triple", aggregate_id=triple_id),
    ]
    related_jobs = [
        SimpleNamespace(id=uuid4(), job_type="knowledge_build", payload={"build_run_id": str(run_id)}),
        SimpleNamespace(id=uuid4(), job_type="knowledge_publish", payload={"publication_id": str(publication_id)}),
    ]
    unrelated_job = SimpleNamespace(id=uuid4(), job_type="knowledge_build", payload={"build_run_id": str(uuid4())})

    class ScalarRows:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.results = iter([
                [version],
                [run],
                [SimpleNamespace(id=uuid4())],
                [qa],
                [triple],
                [SimpleNamespace(id=uuid4())],
                [publication],
                outbox,
                [*related_jobs, unrelated_job],
            ])
            self.deleted: list[object] = []
            self.flushed = False

        def scalars(self, _statement):
            return ScalarRows(next(self.results))

        def delete(self, item):
            self.deleted.append(item)

        def flush(self):
            self.flushed = True

    class FakeStorage:
        deleted: list[str] = []

        def delete(self, uri: str):
            self.deleted.append(uri)

    class FakeQdrant:
        deleted: list[str] = []

        def delete(self, ids: list[str]):
            self.deleted.extend(ids)

    class FakeOpenSearch:
        deleted: list[str] = []

        def delete_many(self, ids: list[str]):
            self.deleted.extend(ids)

    class FakeNeo4j:
        calls: list[tuple[list[str], list[str]]] = []

        def delete_source_artifacts(self, version_ids: list[str], publication_ids: list[str]):
            self.calls.append((version_ids, publication_ids))
            return {"relationships_deleted": 1, "relationships_updated": 0, "nodes_deleted": 2}

    session = FakeSession()
    storage, qdrant, opensearch, neo4j = FakeStorage(), FakeQdrant(), FakeOpenSearch(), FakeNeo4j()
    result = KnowledgeSourceDeletionService(
        session,  # type: ignore[arg-type]
        Settings(),
        storage=storage,  # type: ignore[arg-type]
        qdrant=qdrant,  # type: ignore[arg-type]
        opensearch=opensearch,  # type: ignore[arg-type]
        neo4j=neo4j,  # type: ignore[arg-type]
    ).delete(source)

    assert qdrant.deleted == [str(qa_id)]
    assert opensearch.deleted == [str(qa_id)]
    assert neo4j.calls == [([str(version_id)], [str(publication_id)])]
    assert storage.deleted == ["local://source/original.md", "local://source/parsed.md"]
    assert related_jobs[0] in session.deleted and related_jobs[1] in session.deleted
    assert unrelated_job not in session.deleted
    assert source in session.deleted and session.flushed is True
    assert result["deleted"]["qa_items"] == 1
    assert result["deleted"]["triples"] == 1
    assert result["deleted"]["neo4j"]["relationships_deleted"] == 1


def test_local_knowledge_storage_can_delete_an_owned_object(tmp_path) -> None:
    storage = KnowledgeStorage(Settings(knowledge_storage_root=tmp_path))
    item = storage.put_bytes("knowledge/smoke.md", "养蚕知识".encode("utf-8"), "text/markdown")

    assert storage.read_text(item.uri) == "养蚕知识"
    storage.delete(item.uri)
    assert not (tmp_path / "knowledge" / "smoke.md").exists()


def test_adaptive_chunker_prefers_h3_and_preserves_short_complete_sections() -> None:
    markdown = """# 手册

## 蚕病问答

### 什么是白僵病

白僵病是由白僵菌感染引起的真菌病。

### 如何预防

保持蚕室清洁并及时消毒。
"""
    chunks = AdaptiveMarkdownChunker(target_tokens=200).split(markdown)

    assert [chunk.heading_path[-1] for chunk in chunks if chunk.heading_level == 3] == ["什么是白僵病", "如何预防"]
    assert all(chunk.split_strategy == "h3_complete" for chunk in chunks if chunk.heading_level == 3)
    assert any("short_but_complete" in chunk.quality_flags for chunk in chunks)
    assert not any("short_fragment" in chunk.quality_flags for chunk in chunks)


def test_adaptive_chunker_falls_back_to_h2_and_defers_semantic_split() -> None:
    long_text = "。".join(["高温高湿条件下需要加强通风并及时清除病蚕"] * 260)
    markdown = f"# 手册\n\n## 高温季节如何防病\n\n{long_text}。\n"
    chunks = AdaptiveMarkdownChunker(target_tokens=200, defer_semantic=True).split(markdown)

    assert len(chunks) == 1
    assert chunks[0].heading_level == 2
    assert chunks[0].split_strategy == "semantic_pending"
    assert chunks[0].token_count > 200


def test_deterministic_semantic_fallback_never_exceeds_target() -> None:
    text = "# 手册\n\n## 防治\n\n" + "。".join(["发现病蚕后立即隔离并进行蚕室消毒"] * 300)
    chunks = AdaptiveMarkdownChunker(target_tokens=220).split(text)

    assert len(chunks) > 1
    assert max(chunk.token_count for chunk in chunks) <= 220
    assert all(chunk.split_strategy == "semantic_fallback" for chunk in chunks)


def test_qa_quality_requires_exact_evidence_and_rejects_new_parameters() -> None:
    chunk = _chunk("蚕室温度保持在25℃，并注意通风。")
    valid = validate_qa(
        QAExtraction(
            question="蚕室温度应保持在多少？",
            answer="蚕室温度应保持在25℃。",
            evidence="蚕室温度保持在25℃",
            keywords=["蚕室", "温度"],
            knowledge_types=["parameter"],
            confidence=0.98,
        ),
        chunk,
    )
    invalid = validate_qa(
        QAExtraction(
            question="它应该怎么处理？",
            answer="将温度提高到30℃并保持2小时。",
            evidence="原文没有这句话",
            keywords=[],
            knowledge_types=["parameter"],
            confidence=0.99,
        ),
        chunk,
    )

    assert not valid.flags
    assert {"question_context_dependent", "evidence_missing", "unsupported_parameter"} <= set(invalid.flags)


def test_ambiguous_disease_name_is_forced_to_review() -> None:
    chunk = _chunk("玫烟色僵病可见尸体硬化。")
    quality, canonical_subject, _, resolution = validate_triple(
        TripleExtraction(
            subject_name="玫烟色僵病",
            subject_type="Disease",
            relation="HAS_SYMPTOM",
            object_name="尸体硬化",
            object_type="Symptom",
            evidence="玫烟色僵病可见尸体硬化",
            confidence=0.95,
        ),
        chunk,
        SilkwormGlossary.default(),
    )

    assert canonical_subject == "玫烟色僵病"
    assert "ambiguous_subject" in quality.flags
    assert resolution["subject_status"] == "expert_review"


def test_mineru_batch_uses_bearer_token_and_vlm_contract() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "data": {"batch_id": "batch-1", "file_urls": ["https://upload.test/1"]}})

    settings = Settings(MINERU_TOKEN="temporary-token")
    client = MinerUClient(settings, transport=httpx.MockTransport(handler))
    batch = asyncio.run(client.create_upload_batch([{"name": "家蚕病理学.pdf", "data_id": "doc-1", "is_ocr": False}]))

    assert batch.batch_id == "batch-1"
    assert seen["authorization"] == "Bearer temporary-token"
    assert seen["payload"]["model_version"] == "vlm"
    assert seen["payload"]["enable_table"] is True


def test_model_gateway_validates_structured_output_and_never_echoes_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer temporary-key"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "items": [
                                        {
                                            "question": "白僵病由什么引起？",
                                            "answer": "由白僵菌感染引起。",
                                            "evidence": "白僵病由白僵菌感染引起",
                                            "keywords": ["白僵病", "白僵菌"],
                                            "knowledge_types": ["cause"],
                                            "confidence": 0.95,
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    settings = Settings(DASHSCOPE_API_KEY="temporary-key")
    gateway = ModelGateway(settings, transport=httpx.MockTransport(handler))
    result = asyncio.run(
        gateway.chat_json(
            model=settings.qa_model_id,
            purpose="qa",
            system_prompt="test",
            user_prompt="test",
            response_model=QAExtractionBatch,
        )
    )
    assert isinstance(result, QAExtractionBatch)
    assert result.items[0].question.startswith("白僵病")

    missing_key_gateway = ModelGateway(Settings(DASHSCOPE_API_KEY=None), transport=httpx.MockTransport(handler))
    try:
        asyncio.run(
            missing_key_gateway.chat_json(
                model=settings.qa_model_id,
                system_prompt="test",
                user_prompt="test",
                response_model=QAExtractionBatch,
                retries=0,
            )
        )
    except ModelGatewayError as exc:
        assert "temporary-key" not in str(exc)
    else:
        raise AssertionError("missing API key must fail")


def test_all_three_langgraphs_compile() -> None:
    workflow = KnowledgeBuildWorkflow()
    assert workflow.compile() is not None
    assert workflow.rag_agent.graph is not None
    assert workflow.kg_agent.graph is not None
    assert {"load_document", "plan_document", "adaptive_chunk", "rag_agent", "kg_agent", "finalize"} <= set(workflow.compile().get_graph().nodes)
    assert {"rag_extract", "rag_evaluate", "rag_revise", "rag_expert_review", "rag_persist"} <= set(workflow.rag_agent.graph.get_graph().nodes)
    assert {"kg_extract", "kg_evaluate", "kg_resolve", "kg_expert_review", "kg_persist"} <= set(workflow.kg_agent.graph.get_graph().nodes)


def test_document_planner_and_quality_router_make_explicit_agent_decisions() -> None:
    plan = build_document_plan(
        "# 手册\n\n## 病害\n\n### 白僵病\n\n|症状|措施|\n|---|---|\n|尸体硬化|隔离消毒|",
        targets=["rag", "kg"],
        default_target_tokens=1200,
        max_reflection_rounds=2,
    )
    assert plan["execution_order"] == ["rag", "kg"]
    assert plan["base_heading_level"] == 3
    assert plan["document_profile"]["table_rows"] == 3
    assert plan["quality_route"] == "rules_then_reflection_then_expert_then_human"

    candidate = {"review_status": "needs_review", "risk_flags": ["evidence_missing"], "revision_count": 0}
    assert _quality_route([candidate], revision_round=0, max_reflection_rounds=2, refinable_flags=REFINABLE_QA_FLAGS)[0] == "revise"
    assert _quality_route([candidate], revision_round=2, max_reflection_rounds=2, refinable_flags=REFINABLE_QA_FLAGS)[0] == "expert"
    assert _quality_route([{**candidate, "review_status": "approved", "risk_flags": []}], revision_round=1, max_reflection_rounds=2, refinable_flags=REFINABLE_QA_FLAGS)[0] == "persist"


def test_agent_runtime_preserves_tool_order_and_exposes_reflection_route() -> None:
    class EmptyReviewQuery:
        @staticmethod
        def all() -> list:
            return []

    class FakeDb:
        @staticmethod
        def scalars(_statement) -> EmptyReviewQuery:
            return EmptyReviewQuery()

    run = SimpleNamespace(
        id=uuid4(),
        config_snapshot={"agent_plan": {"planner": "document_build_planner_v1"}},
        current_node="rag_revise",
    )
    events = [
        SimpleNamespace(
            id=uuid4(),
            node="load_document",
            message="load",
            payload={"event_type": "tool_call", "agent": "orchestrator", "tool": "knowledge_storage"},
            created_at=datetime.now(UTC),
        ),
        SimpleNamespace(
            id=uuid4(),
            node="rag_revise",
            message="revise",
            payload={"event_type": "reflection", "agent": "rag", "tool": "qa_model", "route": "reevaluate", "revision_round": 1},
            created_at=datetime.now(UTC),
        ),
    ]

    runtime = _agent_runtime(FakeDb(), run, events)  # type: ignore[arg-type]

    assert runtime["active_agent"] == "rag"
    assert runtime["tools_invoked"] == ["knowledge_storage", "qa_model"]
    assert runtime["reflection_rounds"] == {"rag": 1, "kg": 0}
    assert runtime["last_route"] == "reevaluate"


def test_rag_reflection_revalidates_corrected_candidate_against_source() -> None:
    class RevisionGateway:
        async def chat_json(self, **_kwargs):
            return QAExtraction(
                question="蚕室温度应保持在多少摄氏度？",
                answer="蚕室温度应保持在25℃。",
                evidence="蚕室温度保持在25℃",
                keywords=["蚕室", "温度"],
                knowledge_types=["parameter"],
                confidence=0.98,
            )

    chunk = _chunk("蚕室温度保持在25℃，并注意通风。")
    extractor = KnowledgeExtractor(gateway=RevisionGateway(), settings=Settings())  # type: ignore[arg-type]
    candidate = {
        "question": "它应该多少度？",
        "answer": "提高到30℃。",
        "evidence": "原文没有这句话",
        "keywords": [],
        "knowledge_types": ["parameter"],
        "confidence": 0.8,
        "question_sha256": "old",
        "rule_score": 0.1,
        "risk_flags": ["question_context_dependent", "evidence_missing", "unsupported_parameter"],
        "review_status": "needs_review",
        "revision_count": 0,
        "revision_history": [],
    }
    revised = asyncio.run(extractor.revise_qa_candidate(candidate, chunk))
    assert revised["review_status"] == "approved"
    assert revised["risk_flags"] == []
    assert revised["revision_count"] == 1
    assert revised["revision_history"][0]["risk_before"]


def test_kg_reflection_revalidates_schema_and_source_evidence() -> None:
    class RevisionGateway:
        async def chat_json(self, **_kwargs):
            return TripleExtraction(
                subject_name="核型多角体病",
                subject_type="Disease",
                relation="HAS_SYMPTOM",
                object_name="体壁乳白",
                object_type="Symptom",
                evidence="核型多角体病可见体壁乳白",
                confidence=0.98,
            )

    class ExactGlossary:
        @staticmethod
        def normalize(term: str):
            return SimpleNamespace(
                surface=term,
                canonical=term,
                status="exact",
                note="",
                requires_review=False,
            )

        @staticmethod
        def known_term(_term: str, _term_type: str) -> bool:
            return True

    chunk = _chunk("核型多角体病可见体壁乳白，病蚕行动迟缓。")
    extractor = KnowledgeExtractor(
        gateway=RevisionGateway(),  # type: ignore[arg-type]
        glossary=ExactGlossary(),  # type: ignore[arg-type]
        settings=Settings(),
    )
    candidate = {
        "subject_name": "该病",
        "subject_type": "Disease",
        "subject_canonical_name": "该病",
        "relation": "UNKNOWN_RELATION",
        "object_name": "异常",
        "object_type": "Symptom",
        "object_canonical_name": "异常",
        "evidence": "原文没有这句话",
        "confidence": 0.7,
        "triple_key": "old",
        "rule_score": 0.1,
        "risk_flags": ["unknown_relation", "evidence_missing", "ambiguous_subject"],
        "resolution_metadata": {},
        "review_status": "needs_review",
        "revision_count": 0,
        "revision_history": [],
    }

    revised = asyncio.run(extractor.revise_triple_candidate(candidate, chunk))

    assert revised["review_status"] == "approved"
    assert revised["risk_flags"] == []
    assert revised["revision_count"] == 1
    assert revised["triple_key"] != "old"
    assert revised["resolution_metadata"]["subject_status"] == "exact"


def test_kg_agent_treats_empty_schema_extraction_as_normal_skip() -> None:
    class EmptyExtractor:
        async def extract_triples(self, chunk: DocumentChunk) -> list[dict]:
            del chunk
            return []

    agent = KnowledgeGraphBuildAgent(EmptyExtractor())  # type: ignore[arg-type]
    candidates, failures = asyncio.run(agent._extract_all([_chunk("桑叶应当保持新鲜。").model_dump()]))

    assert candidates == []
    assert failures == []


def _chunk(content: str) -> DocumentChunk:
    return DocumentChunk(
        stable_key="a" * 64,
        ordinal=0,
        start_line=1,
        end_line=1,
        heading_path=["测试"],
        heading_level=3,
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        token_count=estimate_tokens(content),
        quality_score=1,
        quality_flags=[],
        split_strategy="h3_complete",
    )

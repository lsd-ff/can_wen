from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.agents.diagnosis.answer import EvidenceAnswerAgent
from app.agents.diagnosis.context import ContextRoutingAgent, build_context_pack
from app.agents.diagnosis.gateway import DiagnosisAgentGateway, KnowledgeModelError
from app.agents.diagnosis.knowledge import BM25Retriever, HNSWRetriever, KGRetriever
from app.agents.diagnosis.retrieval import KGRetrievalAgent, RAGRetrievalAgent, reciprocal_rank_fusion
from app.agents.diagnosis.types import Citation, DiagnosisAgentResult, EvidenceItem, QueryPlan
from app.agents.diagnosis.workflow import DiagnosisAgentWorkflow
from app.core.config import Settings
from app.db.session import SessionLocal, check_database_connection
from app.models import AgentEvidence, AgentRun, AgentRunEvent, Conversation, Message, User
from app.services import diagnosis_agent_service as diagnosis_agent_service_module
from app.services.diagnosis_agent_service import execute_diagnosis_agent, get_agent_run_response
from app.services.llm_client import LLMProviderError, OpenAICompatibleModelConfig


def _settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        openai_api_key="test",
        diagnosis_agent_max_retrieval_rounds=2,
        diagnosis_agent_dense_top_k=8,
        diagnosis_agent_bm25_top_k=8,
        diagnosis_agent_fusion_top_k=8,
        diagnosis_agent_final_evidence_limit=6,
        **overrides,
    )


def _model_config() -> OpenAICompatibleModelConfig:
    return OpenAICompatibleModelConfig(
        provider_name="test",
        model_id="test-model",
        api_key="test",
        api_request_url="https://example.test/v1",
    )


class EventLog:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def __call__(self, **event: Any):
        self.items.append(event)
        return event


def _evidence(
    key: str,
    *,
    retriever: str,
    evidence_type: str = "rag_document",
    source: str = "家蚕病害防治资料",
    score: float = 0.8,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_key=key,
        evidence_type=evidence_type,
        retriever=retriever,
        title=f"证据 {key}",
        content="五龄蚕体色发白并变硬时，应结合死亡比例、环境与病原证据进行鉴别。",
        source_name=source,
        source_version="v1",
        score=score,
        metadata={"channels": [retriever], "chunk_id": key, "source_version_id": "version-1"},
    )


def test_context_pack_marks_assistant_history_as_non_evidence_and_disables_long_memory() -> None:
    context = build_context_pack(
        original_question="那应该怎么消毒？",
        history=[
            {"role": "user", "content": "五龄蚕出现发白变硬"},
            {"role": "assistant", "content": "可能是某种疾病"},
        ],
        structured_data={"temperature": 29},
        multimodal_observations={"symptoms": ["发白", "变硬"]},
        pending_slots=["异常比例"],
    )

    assert context["original_question"] == "那应该怎么消毒？"
    assert context["recent_conversation"][1]["authority"] == "conversation_only_not_evidence"
    assert context["context_policy"]["assistant_history_is_evidence"] is False
    assert context["context_policy"]["long_term_memory_enabled"] is False


def test_context_pack_keeps_summary_and_compacts_messages_older_than_recent_window() -> None:
    history = [
        {"role": "user" if index % 2 == 0 else "assistant", "content": f"第 {index} 条上下文"}
        for index in range(14)
    ]
    context = build_context_pack(
        original_question="那现在怎么办？",
        history=history,
        structured_data={},
        multimodal_observations={},
        pending_slots=[],
        conversation_summary="五龄蚕出现发白变硬",
    )

    assert context["conversation_summary"] == "五龄蚕出现发白变硬"
    assert "会话摘要：五龄蚕出现发白变硬" in context["rolling_summary"]
    assert "第 0 条上下文" in context["rolling_summary"]
    assert "助手记录（非证据）" in context["rolling_summary"]
    assert len(context["recent_conversation"]) == 10


def test_context_router_falls_back_to_hybrid_for_symptom_diagnosis() -> None:
    class FailingGateway:
        def chat_json(self, **_: Any) -> dict[str, Any]:
            raise LLMProviderError("offline")

    events = EventLog()
    output = ContextRoutingAgent(FailingGateway())(
        {
            "original_question": "五龄蚕发白变硬并开始死亡，是什么原因？",
            "history": [],
            "structured_data": {},
            "multimodal_observations": {},
            "pending_slots": [],
            "user_preferences": {"rag_enabled": True, "knowledge_graph_enabled": True},
            "emit": events,
        }
    )

    plan = output["query_plan"]
    assert plan.route == "hybrid"
    assert plan.domain == "silkworm_disease"
    assert plan.risk_level == "medium"
    assert {event["stage"] for event in events.items} >= {"understand", "model_fallback", "route"}


def test_context_router_recognizes_named_silkworm_disease_without_word_silkworm() -> None:
    class FailingGateway:
        def chat_json(self, **_: Any) -> dict[str, Any]:
            raise LLMProviderError("offline")

    output = ContextRoutingAgent(FailingGateway())(
        {
            "original_question": "白僵病的病原是什么？",
            "history": [],
            "structured_data": {},
            "multimodal_observations": {},
            "pending_slots": [],
            "user_preferences": {"rag_enabled": True, "knowledge_graph_enabled": True},
            "emit": EventLog(),
        }
    )

    plan = output["query_plan"]
    assert plan.domain == "silkworm_disease"
    assert plan.route == "kg"


def test_context_router_applies_multimodal_observations_to_deterministic_risk_floor() -> None:
    class FailingGateway:
        def chat_json(self, **_: Any) -> dict[str, Any]:
            raise LLMProviderError("offline")

    output = ContextRoutingAgent(FailingGateway())(
        {
            "original_question": "请分析这个视频",
            "history": [],
            "structured_data": {"silkworm_stage": "五龄"},
            "multimodal_observations": {"symptoms": ["家蚕吐液", "快速扩散", "大量死亡"]},
            "pending_slots": [],
            "user_preferences": {"rag_enabled": True, "knowledge_graph_enabled": True},
            "emit": EventLog(),
        }
    )

    plan = output["query_plan"]
    assert plan.domain == "silkworm_disease"
    assert plan.route == "hybrid"
    assert plan.intent == "diagnosis_or_cause"
    assert plan.risk_level == "high"


def test_context_router_rewrites_long_anaphoric_follow_up_with_previous_user_turn() -> None:
    class FailingGateway:
        def chat_json(self, **_: Any) -> dict[str, Any]:
            raise LLMProviderError("offline")

    output = ContextRoutingAgent(FailingGateway())(
        {
            "original_question": "那这种情况具体应该怎样进行消毒处理？",
            "history": [
                {"role": "user", "content": "五龄蚕出现体表发白、僵硬，已经死亡约 5%。"},
                {"role": "assistant", "content": "上一轮助手的判断不能作为检索证据。"},
            ],
            "structured_data": {},
            "multimodal_observations": {},
            "pending_slots": [],
            "user_preferences": {"rag_enabled": True, "knowledge_graph_enabled": True},
            "emit": EventLog(),
        }
    )

    assert "五龄蚕出现体表发白" in output["query_plan"].standalone_question
    assert "用户追问" in output["query_plan"].standalone_question


def test_context_router_cannot_skip_three_way_retrieval_for_in_domain_question() -> None:
    class ClarifyGateway:
        def chat_json(self, **_: Any) -> dict[str, Any]:
            return {
                "standalone_question": "五龄蚕体表发白变硬并死亡约 5%，如何判断和处理？",
                "domain": "silkworm_disease",
                "intent": "diagnosis_or_cause",
                "risk_level": "medium",
                "route": "clarify",
                "entities": ["五龄蚕", "发白", "变硬"],
                "missing_slots": ["温湿度与通风情况"],
                "dense_queries": ["五龄蚕 发白 变硬 死亡"],
                "bm25_queries": ["五龄蚕 发白 变硬"],
                "kg_terms": ["发白", "变硬"],
                "route_reason": "模型希望先追问",
            }

    output = ContextRoutingAgent(ClarifyGateway())(
        {
            "original_question": "五龄蚕体表发白变硬，死亡约5%，应该如何判断和处理？",
            "history": [],
            "structured_data": {},
            "multimodal_observations": {},
            "pending_slots": [],
            "user_preferences": {"rag_enabled": True, "knowledge_graph_enabled": True},
            "emit": EventLog(),
        }
    )

    assert output["query_plan"].route == "hybrid"
    assert output["query_plan"].missing_slots == ["温湿度与通风情况"]


def test_context_router_explains_when_both_knowledge_sources_are_disabled() -> None:
    class FailingGateway:
        def chat_json(self, **_: Any) -> dict[str, Any]:
            raise LLMProviderError("offline")

    output = ContextRoutingAgent(FailingGateway())(
        {
            "original_question": "五龄蚕发白变硬并死亡，如何判断？",
            "history": [],
            "structured_data": {},
            "multimodal_observations": {},
            "pending_slots": [],
            "user_preferences": {"rag_enabled": False, "knowledge_graph_enabled": False},
            "emit": EventLog(),
        }
    )

    plan = output["query_plan"]
    assert plan.route == "clarify"
    assert plan.missing_slots[0] == "请在设置中至少启用 RAG 文档检索或知识图谱 KG"
    assert "均已关闭" in plan.route_reason


def test_evidence_deduplication_preserves_cross_channel_evidence_types() -> None:
    from app.agents.diagnosis.answer import deduplicate_evidence, deterministic_assessment

    rag = _evidence("rag:same", retriever="hnsw", evidence_type="rag_document")
    kg = _evidence("kg:same", retriever="kg", evidence_type="kg_path")
    kg.content = rag.content
    kg.title = rag.title
    merged = deduplicate_evidence([rag, kg])

    assert len(merged) == 1
    assert merged[0].metadata["evidence_types"] == ["kg_path", "rag_document"]
    assessment = deterministic_assessment(
        plan=QueryPlan(standalone_question="家蚕病害关系", route="hybrid"),
        evidence=merged,
        branch_errors=[],
    )
    assert "文档原文证据" not in assessment.missing_information
    assert "图谱关系证据" not in assessment.missing_information
    assert "更多相互独立的文档或图谱证据" in assessment.missing_information


def test_hybrid_evidence_selection_reserves_space_for_rag_and_kg() -> None:
    from app.agents.diagnosis.answer import select_evidence_for_route

    kg_items = [
        _evidence(f"kg:{index}", retriever="kg", evidence_type="kg_path", score=1.0 - index / 100)
        for index in range(5)
    ]
    rag_item = _evidence("rag:lower", retriever="hnsw", evidence_type="rag_document", score=0.2)
    selected = select_evidence_for_route([*kg_items, rag_item], route="hybrid", limit=2)

    assert len(selected) == 2
    assert {item.evidence_type for item in selected} == {"rag_document", "kg_path"}


def test_high_risk_evidence_selection_reserves_an_independent_source() -> None:
    from app.agents.diagnosis.answer import select_evidence_for_route

    same_source = [
        _evidence(f"rag:{index}", retriever="bm25", source="来源甲", score=1.0 - index / 100)
        for index in range(5)
    ]
    independent = _evidence("rag:independent", retriever="hnsw", source="来源乙", score=0.1)
    selected = select_evidence_for_route(
        [*same_source, independent],
        route="rag",
        risk_level="high",
        limit=2,
    )

    assert {item.source_name for item in selected} == {"来源甲", "来源乙"}


def test_rag_agent_refines_sparse_queries_and_fuses_hnsw_with_bm25() -> None:
    class Gateway:
        def __init__(self) -> None:
            self.refinements = 0

        def embed(self, queries: list[str]) -> list[list[float]]:
            return [[float(index + 1)] for index, _ in enumerate(queries)]

        def suggest_query_refinement(self, **kwargs: Any) -> list[str]:
            self.refinements += 1
            return [f"{kwargs['channel']} 改写"]

        def rerank(self, query: str, documents: list[str], *, top_n: int) -> list[dict[str, Any]]:
            assert query
            return [{"index": index, "relevance_score": 1 - index / 10} for index in range(min(top_n, len(documents)))]

    class HNSW:
        def __init__(self) -> None:
            self.calls = 0

        def search(self, **_: Any) -> list[EvidenceItem]:
            self.calls += 1
            return [] if self.calls == 1 else [_evidence("rag:shared", retriever="hnsw", score=0.91)]

    class BM25:
        def __init__(self) -> None:
            self.calls = 0

        def search(self, **_: Any) -> list[EvidenceItem]:
            self.calls += 1
            return [] if self.calls == 1 else [_evidence("rag:shared", retriever="bm25", score=4.2)]

    gateway = Gateway()
    hnsw = HNSW()
    bm25 = BM25()
    events = EventLog()
    agent = RAGRetrievalAgent(_settings(), gateway, hnsw=hnsw, bm25=bm25)
    output = agent(
        {
            "query_plan": QueryPlan(
                standalone_question="五龄蚕发白变硬怎么办",
                route="rag",
                entities=["五龄蚕", "发白", "变硬"],
                dense_queries=["五龄蚕发白变硬"],
                bm25_queries=["五龄蚕 发白 变硬"],
            ),
            "knowledge_snapshot": {"available": True, "publication_ids": ["p1"]},
            "emit": events,
        }
    )

    assert hnsw.calls == 2
    assert bm25.calls == 2
    assert gateway.refinements == 2
    assert output["rag_evidence"][0].metadata["channels"] == ["bm25", "hnsw"]
    assert any(event["stage"] == "refine" for event in events.items)


def test_kg_agent_expands_from_first_round_anchors() -> None:
    class Gateway:
        def suggest_query_refinement(self, **_: Any) -> list[str]:
            return ["白僵病"]

    class KG:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def search(self, **kwargs: Any) -> list[EvidenceItem]:
            self.calls.append(kwargs)
            first = _evidence("kg:1", retriever="kg", evidence_type="kg_path")
            first.metadata.update({"subject": "白僵病", "subject_labels": ["疾病"], "relation": "表现症状", "object": "体表白色菌丝"})
            if len(self.calls) == 1:
                return [first]
            second = _evidence("kg:2", retriever="kg", evidence_type="kg_path")
            second.metadata.update({"subject": "白僵病", "subject_labels": ["疾病"], "relation": "由……引起", "object": "白僵菌"})
            third = _evidence("kg:3", retriever="kg", evidence_type="kg_path")
            third.metadata.update({"subject": "白僵病", "subject_labels": ["疾病"], "relation": "防治措施", "object": "隔离消毒"})
            return [first, second, third]

    kg = KG()
    events = EventLog()
    output = KGRetrievalAgent(_settings(), Gateway(), kg=kg)(
        {
            "query_plan": QueryPlan(
                standalone_question="五龄蚕发白变硬是什么原因",
                route="kg",
                intent="diagnosis_or_cause",
                entities=["发白", "变硬"],
                kg_terms=["发白", "变硬"],
            ),
            "knowledge_snapshot": {"available": True, "publication_ids": ["p1"]},
            "emit": events,
        }
    )

    assert len(kg.calls) == 2
    assert "白僵病" in kg.calls[1]["anchors"]
    assert len(output["kg_evidence"]) == 3
    assert any(event["stage"] == "refine" for event in events.items)


def test_kg_agent_uses_aura_when_rag_documents_are_not_published() -> None:
    class Gateway:
        def suggest_query_refinement(self, **_: Any) -> list[str]:
            return []

    class KG:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def search(self, **kwargs: Any) -> list[EvidenceItem]:
            self.calls.append(kwargs)
            item = _evidence("kg:aura", retriever="kg", evidence_type="kg_path")
            item.metadata.update({"subject": "Disease", "relation": "HAS_SYMPTOM", "object": "Symptom"})
            return [item]

    kg = KG()
    events = EventLog()
    output = KGRetrievalAgent(_settings(), Gateway(), kg=kg)(
        {
            "query_plan": QueryPlan(
                standalone_question="What symptom is linked to this disease?",
                route="kg",
                intent="entity_relation",
                entities=["Disease"],
                kg_terms=["Disease"],
            ),
            "knowledge_snapshot": {
                "available": True,
                "rag_available": False,
                "rag_reason": "No published RAG documents",
                "kg_available": True,
                "kg_mode": "aura_curated",
                "publication_ids": [],
            },
            "emit": events,
        }
    )

    assert len(kg.calls) == 1
    assert len(output["kg_evidence"]) == 1
    assert any(event["title"] == "KG 已接入 Neo4j Aura 图谱" for event in events.items)
    assert not any(event["title"] == "KG 图谱连接不可用" for event in events.items)


def test_evidence_answer_agent_refuses_model_only_answer_when_evidence_is_missing() -> None:
    class Gateway:
        def chat_json(self, **_: Any) -> dict[str, Any]:
            raise AssertionError("no evidence means the model assessor must not be called")

        def generate_grounded_answer(self, **_: Any) -> str:
            raise AssertionError("model-only answer is forbidden")

    events = EventLog()
    output = EvidenceAnswerAgent(Gateway())(
        {
            "original_question": "五龄蚕发白变硬怎么办",
            "query_plan": QueryPlan(
                standalone_question="五龄蚕发白变硬怎么办",
                route="hybrid",
                risk_level="medium",
                missing_slots=["异常数量或比例"],
            ),
            "context_pack": {},
            "rag_evidence": [],
            "kg_evidence": [],
            "branch_metrics": [],
            "branch_errors": [],
            "emit": events,
        }
    )

    result = output["result"]
    assert result.status == "waiting_for_user"
    assert result.evidence_status == "insufficient"
    assert "不直接用大模型常识" in result.answer
    assert "异常数量或比例" in result.answer


def test_evidence_answer_agent_generates_only_grounded_cited_answer() -> None:
    class Gateway:
        def chat_json(self, **_: Any) -> dict[str, Any]:
            return {
                "sufficient": True,
                "conflict": False,
                "conflict_summary": "",
                "missing_information": [],
                "rationale": "文本与关系证据互相支持。",
            }

        def generate_grounded_answer(self, **_: Any) -> str:
            return "## 初步判断\n\n当前表现与白僵病相关特征相符，但不能视为确诊。[E1][E2]"

    rag = _evidence("rag:1", retriever="hnsw")
    kg = _evidence("kg:1", retriever="kg", evidence_type="kg_path", source="家蚕疾病知识图谱")
    events = EventLog()
    output = EvidenceAnswerAgent(Gateway())(
        {
            "original_question": "五龄蚕发白变硬是什么原因",
            "query_plan": QueryPlan(
                standalone_question="五龄蚕发白变硬是什么原因",
                route="hybrid",
                risk_level="medium",
            ),
            "context_pack": {},
            "rag_evidence": [rag],
            "kg_evidence": [kg],
            "branch_metrics": [],
            "branch_errors": [],
            "emit": events,
        }
    )

    result = output["result"]
    assert result.status == "completed"
    assert result.evidence_status == "sufficient"
    assert "[E1]" in result.answer and "[E2]" in result.answer
    assert [citation.evidence_id for citation in result.citations] == ["E1", "E2"]


def test_rrf_merges_same_document_from_both_retrieval_channels() -> None:
    dense = _evidence("rag:same", retriever="hnsw", score=0.9)
    lexical = _evidence("rag:same", retriever="bm25", score=6.0)

    fused = reciprocal_rank_fusion([dense], [lexical])

    assert len(fused) == 1
    assert fused[0].retriever == "bm25+hnsw"
    assert fused[0].metadata["channels"] == ["bm25", "hnsw"]


def test_knowledge_gateway_never_reuses_end_user_chat_key() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key="server-chat-key",
        knowledge_model_api_key=None,
    )
    gateway = DiagnosisAgentGateway(settings, _model_config())

    with pytest.raises(KnowledgeModelError, match="知识检索模型 API Key 未配置"):
        gateway._post("https://example.test/embeddings", {"input": ["test"]})


def test_hnsw_adapter_filters_to_publication_snapshot_and_closes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import qdrant_client

    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs

        def query_points(self, **kwargs: Any):
            captured["query"] = kwargs
            point = type(
                "Point",
                (),
                {
                    "id": "qa-1",
                    "score": 0.91,
                    "payload": {
                        "publication_id": "publication-1",
                        "question": "白僵病有哪些典型症状？",
                        "answer": "病蚕体表可见白色菌丝。",
                        "source_version": "v1",
                    },
                },
            )()
            return type("Response", (), {"points": [point]})()

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(qdrant_client, "QdrantClient", FakeClient)
    evidence = HNSWRetriever(_settings()).search(
        vector=[0.1],
        snapshot={
            "publication_ids": ["publication-1"],
            "qdrant_collections": ["silkworm_qa_v1"],
            "publications": [
                {
                    "publication_id": "publication-1",
                    "source_title": "家蚕病害资料",
                    "source_url": "https://example.test/source",
                }
            ],
        },
        limit=5,
    )

    assert captured["query"]["collection_name"] == "silkworm_qa_v1"
    assert captured["query"]["query_filter"].must[0].match.any == ["publication-1"]
    assert captured["client"]["trust_env"] is False
    assert captured["closed"] is True
    assert evidence[0].retriever == "hnsw"
    assert evidence[0].source_name == "家蚕病害资料"


def test_bm25_adapter_uses_tokenized_query_snapshot_filter_and_closes_client() -> None:
    captured: dict[str, Any] = {}

    class Tokenizer:
        def tokenize(self, value: str) -> str:
            assert value == "白僵病 症状"
            return "白僵病 症状"

    class FakeClient:
        def search(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {
                "hits": {
                    "hits": [
                        {
                            "_id": "qa-1",
                            "_score": 4.2,
                            "_source": {
                                "publication_id": "publication-1",
                                "question": "白僵病有哪些典型症状？",
                                "answer": "病蚕体表可见白色菌丝。",
                            },
                        }
                    ]
                }
            }

        def close(self) -> None:
            captured["closed"] = True

    retriever = BM25Retriever(_settings(), tokenizer=Tokenizer())
    retriever._client = lambda: FakeClient()  # type: ignore[method-assign]
    evidence = retriever.search(
        query="白僵病 症状",
        snapshot={
            "publication_ids": ["publication-1"],
            "opensearch_indexes": ["silkworm_qa_v1"],
            "publications": [{"publication_id": "publication-1", "source_title": "家蚕病害资料"}],
        },
        limit=5,
    )

    assert captured["index"] == "silkworm_qa_v1"
    assert captured["body"]["query"]["bool"]["filter"] == [
        {"terms": {"publication_id": ["publication-1"]}}
    ]
    assert captured["closed"] is True
    assert evidence[0].retriever == "bm25"


def test_kg_adapter_uses_parameterized_template_and_aura_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    import neo4j

    captured: dict[str, Any] = {}

    class FakeRecord:
        def data(self) -> dict[str, Any]:
            return {
                "subject_name": "白僵病",
                "subject_labels": ["疾病"],
                "relation_type": "表现症状",
                "object_name": "体表白色菌丝",
                "object_labels": ["症状"],
                "evidence": "病蚕体表密布白色菌丝。",
                "provenance": '{"source_title":"家蚕病害资料","source_version":"v1"}',
                "publication_id": "publication-1",
            }

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def run(self, cypher: str, **parameters: Any):
            captured["cypher"] = cypher
            captured["parameters"] = parameters
            return [FakeRecord()]

    class FakeDriver:
        def verify_connectivity(self) -> None:
            captured["verified"] = True

        def session(self, **kwargs: Any) -> FakeSession:
            captured["session"] = kwargs
            return FakeSession()

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(neo4j.GraphDatabase, "driver", lambda *args, **kwargs: FakeDriver())
    settings = Settings(
        _env_file=None,
        neo4j_uri="neo4j+s://example.databases.neo4j.io",
        neo4j_user="neo4j",
        neo4j_password="secret",
        neo4j_database="neo4j",
    )
    evidence = KGRetriever(settings).search(
        terms=["白僵病"],
        snapshot={
            "publication_ids": ["publication-1"],
            "neo4j_databases": ["neo4j"],
            "publications": [{"publication_id": "publication-1", "source_title": "家蚕病害资料"}],
        },
        limit=5,
    )

    assert "白僵病" not in captured["cypher"]
    assert captured["parameters"]["terms"] == ["白僵病"]
    assert captured["parameters"]["publication_ids"] == ["publication-1"]
    assert captured["session"] == {"database": "neo4j"}
    assert captured["verified"] is True and captured["closed"] is True
    assert evidence[0].evidence_type == "kg_path"
    assert evidence[0].source_version == "v1"


def test_kg_adapter_reads_curated_aura_graph_without_local_publication(monkeypatch: pytest.MonkeyPatch) -> None:
    import neo4j

    captured: dict[str, Any] = {}

    class FakeRecord:
        def data(self) -> dict[str, Any]:
            return {
                "subject_name": "Disease A",
                "subject_labels": ["Disease"],
                "relation_type": "HAS_SYMPTOM",
                "object_name": "Symptom B",
                "object_labels": ["Symptom"],
                "evidence": "Curated graph evidence.",
                "provenance": "",
                "source_documents": ["Existing Aura graph"],
                "confidence": 0.9,
                "publication_id": "",
            }

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def run(self, cypher: str, **parameters: Any):
            captured["cypher"] = cypher
            captured["parameters"] = parameters
            return [FakeRecord()]

    class FakeDriver:
        def verify_connectivity(self) -> None:
            captured["verified"] = True

        def session(self, **kwargs: Any) -> FakeSession:
            captured["session"] = kwargs
            return FakeSession()

        def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(neo4j.GraphDatabase, "driver", lambda *args, **kwargs: FakeDriver())
    settings = Settings(
        _env_file=None,
        neo4j_uri="neo4j+s://example.databases.neo4j.io",
        neo4j_user="neo4j",
        neo4j_password="secret",
        neo4j_database="configured-aura",
    )
    evidence = KGRetriever(settings).search(
        terms=["Disease"],
        snapshot={
            "kg_available": True,
            "kg_mode": "aura_curated",
            "kg_source_title": "Configured Aura graph",
            "publication_ids": [],
            "neo4j_databases": ["must-not-be-used"],
        },
        limit=5,
    )

    assert "coalesce(relation.publication_id, '') = ''" in captured["cypher"]
    assert "relation.publication_id IN $publication_ids" in captured["cypher"]
    assert captured["parameters"]["publication_ids"] == []
    assert captured["session"] == {"database": "configured-aura"}
    assert captured["verified"] is True and captured["closed"] is True
    assert evidence[0].source_name == "Configured Aura graph"
    assert evidence[0].metadata["graph_source"] == "aura_curated"


def test_langgraph_hybrid_route_joins_kg_and_rag_before_agent4() -> None:
    calls: list[str] = []

    class ContextAgent:
        def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
            calls.append("agent1")
            return {
                "context_pack": {"original_question": state["original_question"]},
                "query_plan": QueryPlan(
                    standalone_question=state["original_question"],
                    route="hybrid",
                    risk_level="low",
                ),
            }

    class KGAgent:
        def __call__(self, _: dict[str, Any]) -> dict[str, Any]:
            calls.append("agent2")
            return {
                "kg_evidence": [_evidence("kg:joined", retriever="kg", evidence_type="kg_path")],
                "branch_metrics": [{"agent": "kg"}],
                "branch_errors": [],
            }

    class RAGAgent:
        def __call__(self, _: dict[str, Any]) -> dict[str, Any]:
            calls.append("agent3")
            return {
                "rag_evidence": [_evidence("rag:joined", retriever="bm25")],
                "branch_metrics": [{"agent": "rag"}],
                "branch_errors": [],
            }

    class AnswerAgent:
        def __call__(self, state: dict[str, Any]) -> dict[str, Any]:
            calls.append("agent4")
            assert len(state["kg_evidence"]) == 1
            assert len(state["rag_evidence"]) == 1
            assert {item["agent"] for item in state["branch_metrics"]} == {"kg", "rag"}
            result = DiagnosisAgentResult(
                answer="joined",
                status="completed",
                route="hybrid",
                risk_level="low",
                original_question=state["original_question"],
                rewritten_question=state["original_question"],
                evidence_status="sufficient",
            )
            return {"answer": "joined", "result": result}

    workflow = DiagnosisAgentWorkflow(
        settings=_settings(),
        model_config=_model_config(),
        gateway=object(),
        context_agent=ContextAgent(),
        kg_agent=KGAgent(),
        rag_agent=RAGAgent(),
        answer_agent=AnswerAgent(),
    )
    result = workflow.invoke(
        run_id="run-1",
        original_question="家蚕症状判断",
        conversation_summary="",
        history=[],
        structured_data={},
        multimodal_observations={},
        pending_slots=[],
        user_preferences={},
        model_config=_model_config(),
        knowledge_snapshot={"available": True},
        emit=EventLog(),
    )

    assert result.answer == "joined"
    assert calls[0] == "agent1"
    assert set(calls[1:3]) == {"agent2", "agent3"}
    assert calls[-1] == "agent4"


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_agent_execution_persists_snapshot_events_evidence_and_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    publication_id = str(uuid4())
    snapshot = {
        "available": True,
        "reason": None,
        "publication_ids": [publication_id],
        "qdrant_collections": ["silkworm_qa_v1"],
        "opensearch_indexes": ["silkworm_qa_v1"],
        "neo4j_databases": ["neo4j"],
        "publications": [{"publication_id": publication_id, "source_title": "测试知识源"}],
        "source_count": 1,
    }
    monkeypatch.setattr(diagnosis_agent_service_module, "load_knowledge_snapshot", lambda db: snapshot)

    class PersistingWorkflow:
        def __init__(self, **_: Any) -> None:
            pass

        def invoke(self, **state: Any) -> DiagnosisAgentResult:
            state["emit"](
                agent="agent1_context_router",
                stage="route",
                status="completed",
                title="路由完成",
                payload={
                    "route": "rag",
                    "prompt": "不得出现在公开事件中",
                    "provider_access_token": "secret-token",
                },
            )
            state["emit"](
                agent="agent3_rag",
                stage="complete",
                status="completed",
                title="RAG 检索完成",
                payload={"hnsw_hits": 1, "bm25_hits": 1},
            )
            evidence = _evidence("rag:persisted", retriever="hnsw+bm25", score=0.93)
            citation = Citation(
                evidence_id="E1",
                title=evidence.title,
                source_name=evidence.source_name,
                source_version=evidence.source_version,
                retrievers=["hnsw", "bm25"],
                score=evidence.score,
                excerpt=evidence.content,
            )
            state["emit"](
                agent="agent4_evidence_answer",
                stage="answer",
                status="completed",
                title="证据融合回答完成",
                payload={"citation_count": 1},
            )
            return DiagnosisAgentResult(
                answer="请根据检索证据继续核查。[E1]",
                status="completed",
                route="rag",
                risk_level="low",
                original_question=state["original_question"],
                rewritten_question="五龄蚕发白变硬的处理依据",
                context_pack={"context_policy": {"long_term_memory_enabled": False}},
                evidence_status="sufficient",
                evidence=[evidence],
                citations=[citation],
                metrics={"retrieval": [{"agent": "rag", "rounds": 1}]},
            )

    user_id = None
    try:
        with SessionLocal() as db:
            user = User(display_name="agent-runtime-test", username=f"agent-{uuid4().hex[:10]}")
            db.add(user)
            db.flush()
            conversation = Conversation(user_id=user.id, title="智能体持久化测试", conversation_type="diagnosis")
            db.add(conversation)
            db.flush()
            message = Message(
                conversation_id=conversation.id,
                sender_type="user",
                content="五龄蚕发白变硬怎么办？",
                message_type="text",
                status="sent",
            )
            db.add(message)
            db.commit()
            db.refresh(user)
            db.refresh(conversation)
            db.refresh(message)
            user_id = user.id

            execution = execute_diagnosis_agent(
                db,
                user=user,
                conversation=conversation,
                user_message=message,
                settings=_settings(),
                model_config=_model_config(),
                original_question=message.content,
                history=[],
                workflow_factory=PersistingWorkflow,
            )

            run = db.get(AgentRun, execution.run_id)
            assert run is not None
            assert run.status == "completed"
            assert run.route == "rag"
            assert run.knowledge_snapshot["publication_ids"] == [publication_id]
            assert run.context_pack["context_policy"]["long_term_memory_enabled"] is False

            events = list(
                db.scalars(
                    select(AgentRunEvent)
                    .where(AgentRunEvent.agent_run_id == execution.run_id)
                    .order_by(AgentRunEvent.sequence)
                )
            )
            assert [event.sequence for event in events] == [1, 2, 3, 4]
            assert [event.agent_key for event in events] == [
                "orchestrator",
                "agent1_context_router",
                "agent3_rag",
                "agent4_evidence_answer",
            ]
            assert "prompt" not in events[1].public_payload
            assert "provider_access_token" not in events[1].public_payload

            stored_evidence = db.scalar(
                select(AgentEvidence).where(AgentEvidence.agent_run_id == execution.run_id)
            )
            assert stored_evidence is not None
            assert stored_evidence.evidence_key == "rag:persisted"
            assert stored_evidence.retriever == "hnsw+bm25"

            replay = get_agent_run_response(db, user=user, run_id=execution.run_id)
            assert replay.evidence_status == "sufficient"
            assert replay.citations[0].evidence_id == "E1"
            assert [event.sequence for event in replay.events] == [1, 2, 3, 4]
    finally:
        if user_id is not None:
            with SessionLocal() as db:
                db.execute(delete(User).where(User.id == user_id))
                db.commit()

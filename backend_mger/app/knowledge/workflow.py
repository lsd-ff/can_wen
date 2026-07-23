from __future__ import annotations

import asyncio
import io
import re
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from langgraph.graph import END, START, StateGraph
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.knowledge.extractors import REFINABLE_KG_FLAGS, REFINABLE_QA_FLAGS, KnowledgeExtractor
from app.knowledge.markdown import AdaptiveMarkdownChunker, estimate_tokens
from app.knowledge.mineru import MinerUClient
from app.knowledge.model_gateway import ModelGateway
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.storage import KnowledgeStorage, safe_filename
from app.knowledge.types import BuildState, DocumentChunk
from app.models import KnowledgeSourceVersion


def _record_agent_event(
    session_factory,
    run_id: UUID,
    node: str,
    message: str,
    payload: dict[str, Any],
    *,
    level: str = "info",
) -> None:
    with session_factory() as db:
        repository = KnowledgeRepository(db)
        repository.event(run_id, node, message, level=level, payload=payload)
        db.commit()


def _quality_route(
    candidates: list[dict[str, Any]],
    *,
    revision_round: int,
    max_reflection_rounds: int,
    refinable_flags: frozenset[str],
) -> tuple[str, dict[str, int]]:
    risks = Counter(
        str(flag)
        for candidate in candidates
        for flag in candidate.get("risk_flags", [])
    )
    has_revisable = any(
        candidate.get("review_status") == "needs_review"
        and int(candidate.get("revision_count", 0)) < max_reflection_rounds
        and bool(set(map(str, candidate.get("risk_flags", []))) & refinable_flags)
        for candidate in candidates
    )
    has_pending_risk = any(candidate.get("review_status") == "needs_review" for candidate in candidates)
    if has_revisable and revision_round < max_reflection_rounds:
        return "revise", dict(risks)
    if has_pending_risk:
        return "expert", dict(risks)
    return "persist", dict(risks)


def _deduplicate_candidates(candidates: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = str(candidate.get(key, ""))
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(candidate)
    return result


def _attach_agent_metadata(candidate: dict[str, Any], agent: str) -> dict[str, Any]:
    assessment = dict(candidate.get("expert_review", {}))
    assessment["agent"] = {
        "name": agent,
        "revision_count": int(candidate.get("revision_count", 0)),
        "revision_history": list(candidate.get("revision_history", [])),
        "expert_trigger_flags": list(candidate.get("risk_flags", [])),
        "final_route": "human_review" if candidate.get("review_status") == "needs_review" else "approved",
    }
    return {**candidate, "expert_review": assessment}


class RagDocumentBuildAgent:
    """RAG sub-agent with quality routing and bounded reflection."""

    def __init__(self, extractor: KnowledgeExtractor, session_factory=SessionLocal) -> None:
        self.extractor = extractor
        self.session_factory = session_factory
        self.max_reflection_rounds = int(
            getattr(getattr(extractor, "settings", None), "knowledge_max_reflection_rounds", 2)
        )
        builder = StateGraph(BuildState)
        builder.add_node("rag_extract", self._extract)
        builder.add_node("rag_evaluate", self._evaluate)
        builder.add_node("rag_revise", self._revise)
        builder.add_node("rag_expert_review", self._expert_review)
        builder.add_node("rag_persist", self._persist)
        builder.add_edge(START, "rag_extract")
        builder.add_edge("rag_extract", "rag_evaluate")
        builder.add_conditional_edges(
            "rag_evaluate",
            self._route_after_evaluation,
            {"revise": "rag_revise", "expert": "rag_expert_review", "persist": "rag_persist"},
        )
        builder.add_edge("rag_revise", "rag_evaluate")
        builder.add_edge("rag_expert_review", "rag_persist")
        builder.add_edge("rag_persist", END)
        self.graph = builder.compile()

    def invoke(self, state: BuildState) -> BuildState:
        if "rag" not in state.get("targets", []):
            return state
        return self.graph.invoke(state)

    def _extract(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        with self.session_factory() as db:
            KnowledgeRepository(db).set_progress(run_id, "rag_extract", 45, "RAG 智能体正在调用 QA 模型抽取问答")
        candidates, failures = asyncio.run(self._extract_all(state.get("chunks", [])))
        _record_agent_event(
            self.session_factory,
            run_id,
            "rag_extract",
            f"RAG 智能体完成首轮抽取：{len(candidates)} 条候选，{len(failures)} 个 Chunk 失败",
            {
                "event_type": "tool_call",
                "agent": "rag",
                "tool": "qa_model",
                "chunk_count": len(state.get("chunks", [])),
                "candidate_count": len(candidates),
                "failure_count": len(failures),
            },
            level="warning" if failures else "info",
        )
        return {"qa_items": candidates, "rag_failures": failures, "rag_revision_round": 0}

    async def _extract_all(self, chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        semaphore = asyncio.Semaphore(2)

        async def one(data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
            chunk = DocumentChunk.model_validate(data)
            async with semaphore:
                try:
                    try:
                        items = await self.extractor.extract_qa(chunk, defer_expert=True)
                    except TypeError as exc:
                        if "defer_expert" not in str(exc):
                            raise
                        items = await self.extractor.extract_qa(chunk)
                    if not items:
                        return [], {"chunk_key": chunk.stable_key, "error": "模型返回空 QA 列表"}
                    return [{**item, "_chunk_key": chunk.stable_key} for item in items], None
                except Exception as exc:
                    return [], {"chunk_key": chunk.stable_key, "error": _safe_error(exc)}

        results = await asyncio.gather(*(one(chunk) for chunk in chunks))
        candidates = [item for items, _ in results for item in items]
        failures = [failure for _, failure in results if failure]
        return candidates, failures

    def _evaluate(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        revision_round = int(state.get("rag_revision_round", 0))
        route, risk_summary = _quality_route(
            state.get("qa_items", []),
            revision_round=revision_round,
            max_reflection_rounds=self.max_reflection_rounds,
            refinable_flags=REFINABLE_QA_FLAGS,
        )
        route_label = {"revise": "进入反思修正", "expert": "转交专家模型", "persist": "通过质量门禁"}[route]
        _record_agent_event(
            self.session_factory,
            run_id,
            "rag_evaluate",
            f"RAG 质量决策：{route_label}",
            {
                "event_type": "quality_decision",
                "agent": "rag",
                "route": route,
                "revision_round": revision_round,
                "max_reflection_rounds": self.max_reflection_rounds,
                "risk_summary": risk_summary,
            },
            level="warning" if route != "persist" else "info",
        )
        return {"rag_route": route, "rag_risk_summary": risk_summary}

    @staticmethod
    def _route_after_evaluation(state: BuildState) -> str:
        return str(state.get("rag_route", "persist"))

    def _revise(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        chunks = {
            chunk.stable_key: chunk
            for chunk in (DocumentChunk.model_validate(data) for data in state.get("chunks", []))
        }

        async def revise_all() -> tuple[list[dict[str, Any]], int, int]:
            semaphore = asyncio.Semaphore(2)

            async def one(candidate: dict[str, Any]) -> tuple[dict[str, Any], bool, bool]:
                flags = set(map(str, candidate.get("risk_flags", [])))
                if (
                    candidate.get("review_status") != "needs_review"
                    or not flags & REFINABLE_QA_FLAGS
                    or int(candidate.get("revision_count", 0)) >= self.max_reflection_rounds
                ):
                    return candidate, False, False
                chunk = chunks.get(str(candidate.get("_chunk_key", "")))
                if chunk is None:
                    return candidate, False, True
                async with semaphore:
                    try:
                        return await self.extractor.revise_qa_candidate(candidate, chunk), True, False
                    except Exception as exc:
                        failed = {
                            **candidate,
                            "revision_count": int(candidate.get("revision_count", 0)) + 1,
                            "revision_history": [
                                *list(candidate.get("revision_history", [])),
                                {
                                    "round": int(candidate.get("revision_count", 0)) + 1,
                                    "risk_before": list(candidate.get("risk_flags", [])),
                                    "risk_after": [*list(candidate.get("risk_flags", [])), "reflection_failed"],
                                    "error": _safe_error(exc),
                                },
                            ],
                            "risk_flags": list(dict.fromkeys([*candidate.get("risk_flags", []), "reflection_failed"])),
                            "review_status": "needs_review",
                        }
                        return failed, True, True

            results = await asyncio.gather(*(one(candidate) for candidate in state.get("qa_items", [])))
            return (
                [item for item, _, _ in results],
                sum(changed for _, changed, _ in results),
                sum(failed for _, _, failed in results),
            )

        candidates, revised_count, failed_count = asyncio.run(revise_all())
        revision_round = int(state.get("rag_revision_round", 0)) + 1
        _record_agent_event(
            self.session_factory,
            run_id,
            "rag_revise",
            f"RAG 智能体完成第 {revision_round} 轮反思修正：{revised_count} 条",
            {
                "event_type": "reflection",
                "agent": "rag",
                "tool": "qa_model",
                "route": "reevaluate",
                "revision_round": revision_round,
                "revised_count": revised_count,
                "failure_count": failed_count,
            },
            level="warning" if failed_count else "info",
        )
        return {"qa_items": candidates, "rag_revision_round": revision_round}

    def _expert_review(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        chunks = {
            chunk.stable_key: chunk
            for chunk in (DocumentChunk.model_validate(data) for data in state.get("chunks", []))
        }

        async def review_all() -> tuple[list[dict[str, Any]], int]:
            semaphore = asyncio.Semaphore(2)

            async def one(candidate: dict[str, Any]) -> tuple[dict[str, Any], bool]:
                if candidate.get("review_status") != "needs_review":
                    return candidate, False
                chunk = chunks.get(str(candidate.get("_chunk_key", "")))
                if chunk is None:
                    return candidate, False
                async with semaphore:
                    return await self.extractor.expert_review_candidate("qa", candidate, chunk), True

            results = await asyncio.gather(*(one(candidate) for candidate in state.get("qa_items", [])))
            return [item for item, _ in results], sum(reviewed for _, reviewed in results)

        candidates, reviewed_count = asyncio.run(review_all())
        handoff_count = sum(candidate.get("review_status") == "needs_review" for candidate in candidates)
        _record_agent_event(
            self.session_factory,
            run_id,
            "rag_expert_review",
            f"专家模型完成 RAG 评审：{reviewed_count} 条，转人工 {handoff_count} 条",
            {
                "event_type": "expert_review",
                "agent": "rag",
                "tool": "expert_model",
                "reviewed_count": reviewed_count,
                "human_handoff_count": handoff_count,
                "route": "human_review" if handoff_count else "persist",
            },
            level="warning" if handoff_count else "info",
        )
        return {"qa_items": candidates}

    def _persist(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        with self.session_factory() as db:
            repository = KnowledgeRepository(db)
            repository.set_progress(run_id, "rag_quality", 65, "RAG 智能体正在保存候选与人工审核路由")
            candidates = _deduplicate_candidates(
                [_attach_agent_metadata(item, "rag") for item in state.get("qa_items", [])],
                "question_sha256",
            )
            count = repository.persist_qa(run_id, candidates, state.get("rag_failures", []))
        _record_agent_event(
            self.session_factory,
            run_id,
            "rag_persist",
            f"RAG 智能体已保存 {count} 条去重 QA",
            {"event_type": "persistence", "agent": "rag", "tool": "postgresql", "candidate_count": count},
        )
        return {"metrics": {**state.get("metrics", {}), "qa_count": count}}


class KnowledgeGraphBuildAgent:
    """KG sub-agent with schema repair, entity resolution and bounded reflection."""

    def __init__(self, extractor: KnowledgeExtractor, session_factory=SessionLocal) -> None:
        self.extractor = extractor
        self.session_factory = session_factory
        self.max_reflection_rounds = int(
            getattr(getattr(extractor, "settings", None), "knowledge_max_reflection_rounds", 2)
        )
        builder = StateGraph(BuildState)
        builder.add_node("kg_extract", self._extract)
        builder.add_node("kg_evaluate", self._evaluate)
        builder.add_node("kg_resolve", self._resolve)
        builder.add_node("kg_expert_review", self._expert_review)
        builder.add_node("kg_persist", self._persist)
        builder.add_edge(START, "kg_extract")
        builder.add_edge("kg_extract", "kg_evaluate")
        builder.add_conditional_edges(
            "kg_evaluate",
            self._route_after_evaluation,
            {"revise": "kg_resolve", "expert": "kg_expert_review", "persist": "kg_persist"},
        )
        builder.add_edge("kg_resolve", "kg_evaluate")
        builder.add_edge("kg_expert_review", "kg_persist")
        builder.add_edge("kg_persist", END)
        self.graph = builder.compile()

    def invoke(self, state: BuildState) -> BuildState:
        if "kg" not in state.get("targets", []):
            return state
        return self.graph.invoke(state)

    def _extract(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        with self.session_factory() as db:
            KnowledgeRepository(db).set_progress(run_id, "kg_extract", 72, "KG 智能体正在按 Schema 抽取三元组")
        candidates, failures = asyncio.run(self._extract_all(state.get("chunks", [])))
        _record_agent_event(
            self.session_factory,
            run_id,
            "kg_extract",
            f"KG 智能体完成首轮抽取：{len(candidates)} 条候选，{len(failures)} 个 Chunk 失败",
            {
                "event_type": "tool_call",
                "agent": "kg",
                "tool": "kg_model",
                "chunk_count": len(state.get("chunks", [])),
                "candidate_count": len(candidates),
                "failure_count": len(failures),
            },
            level="warning" if failures else "info",
        )
        return {"triples": candidates, "kg_failures": failures, "kg_revision_round": 0}

    async def _extract_all(self, chunks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        semaphore = asyncio.Semaphore(2)

        async def one(data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
            chunk = DocumentChunk.model_validate(data)
            async with semaphore:
                try:
                    try:
                        items = await self.extractor.extract_triples(chunk, defer_expert=True)
                    except TypeError as exc:
                        if "defer_expert" not in str(exc):
                            raise
                        items = await self.extractor.extract_triples(chunk)
                    # A general husbandry section may contain no disease-schema
                    # relation. An empty, valid KG extraction is a normal skip.
                    if not items:
                        return [], None
                    return [{**item, "_chunk_key": chunk.stable_key} for item in items], None
                except Exception as exc:
                    return [], {"chunk_key": chunk.stable_key, "error": _safe_error(exc)}

        results = await asyncio.gather(*(one(chunk) for chunk in chunks))
        candidates = [item for items, _ in results for item in items]
        failures = [failure for _, failure in results if failure]
        return candidates, failures

    def _evaluate(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        revision_round = int(state.get("kg_revision_round", 0))
        route, risk_summary = _quality_route(
            state.get("triples", []),
            revision_round=revision_round,
            max_reflection_rounds=self.max_reflection_rounds,
            refinable_flags=REFINABLE_KG_FLAGS,
        )
        route_label = {"revise": "进入消歧修正", "expert": "转交专家模型", "persist": "通过质量门禁"}[route]
        _record_agent_event(
            self.session_factory,
            run_id,
            "kg_evaluate",
            f"KG 质量决策：{route_label}",
            {
                "event_type": "quality_decision",
                "agent": "kg",
                "route": route,
                "revision_round": revision_round,
                "max_reflection_rounds": self.max_reflection_rounds,
                "risk_summary": risk_summary,
            },
            level="warning" if route != "persist" else "info",
        )
        return {"kg_route": route, "kg_risk_summary": risk_summary}

    @staticmethod
    def _route_after_evaluation(state: BuildState) -> str:
        return str(state.get("kg_route", "persist"))

    def _resolve(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        chunks = {
            chunk.stable_key: chunk
            for chunk in (DocumentChunk.model_validate(data) for data in state.get("chunks", []))
        }

        async def resolve_all() -> tuple[list[dict[str, Any]], int, int]:
            semaphore = asyncio.Semaphore(2)

            async def one(candidate: dict[str, Any]) -> tuple[dict[str, Any], bool, bool]:
                flags = set(map(str, candidate.get("risk_flags", [])))
                if (
                    candidate.get("review_status") != "needs_review"
                    or not flags & REFINABLE_KG_FLAGS
                    or int(candidate.get("revision_count", 0)) >= self.max_reflection_rounds
                ):
                    return candidate, False, False
                chunk = chunks.get(str(candidate.get("_chunk_key", "")))
                if chunk is None:
                    return candidate, False, True
                async with semaphore:
                    try:
                        return await self.extractor.revise_triple_candidate(candidate, chunk), True, False
                    except Exception as exc:
                        failed = {
                            **candidate,
                            "revision_count": int(candidate.get("revision_count", 0)) + 1,
                            "revision_history": [
                                *list(candidate.get("revision_history", [])),
                                {
                                    "round": int(candidate.get("revision_count", 0)) + 1,
                                    "risk_before": list(candidate.get("risk_flags", [])),
                                    "risk_after": [*list(candidate.get("risk_flags", [])), "resolution_failed"],
                                    "error": _safe_error(exc),
                                },
                            ],
                            "risk_flags": list(dict.fromkeys([*candidate.get("risk_flags", []), "resolution_failed"])),
                            "review_status": "needs_review",
                        }
                        return failed, True, True

            results = await asyncio.gather(*(one(candidate) for candidate in state.get("triples", [])))
            return (
                [item for item, _, _ in results],
                sum(changed for _, changed, _ in results),
                sum(failed for _, _, failed in results),
            )

        candidates, resolved_count, failed_count = asyncio.run(resolve_all())
        revision_round = int(state.get("kg_revision_round", 0)) + 1
        _record_agent_event(
            self.session_factory,
            run_id,
            "kg_resolve",
            f"KG 智能体完成第 {revision_round} 轮消歧修正：{resolved_count} 条",
            {
                "event_type": "reflection",
                "agent": "kg",
                "tool": "kg_model",
                "route": "reevaluate",
                "revision_round": revision_round,
                "revised_count": resolved_count,
                "failure_count": failed_count,
            },
            level="warning" if failed_count else "info",
        )
        return {"triples": candidates, "kg_revision_round": revision_round}

    def _expert_review(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        chunks = {
            chunk.stable_key: chunk
            for chunk in (DocumentChunk.model_validate(data) for data in state.get("chunks", []))
        }

        async def review_all() -> tuple[list[dict[str, Any]], int]:
            semaphore = asyncio.Semaphore(2)

            async def one(candidate: dict[str, Any]) -> tuple[dict[str, Any], bool]:
                if candidate.get("review_status") != "needs_review":
                    return candidate, False
                chunk = chunks.get(str(candidate.get("_chunk_key", "")))
                if chunk is None:
                    return candidate, False
                async with semaphore:
                    return await self.extractor.expert_review_candidate("triple", candidate, chunk), True

            results = await asyncio.gather(*(one(candidate) for candidate in state.get("triples", [])))
            return [item for item, _ in results], sum(reviewed for _, reviewed in results)

        candidates, reviewed_count = asyncio.run(review_all())
        handoff_count = sum(candidate.get("review_status") == "needs_review" for candidate in candidates)
        _record_agent_event(
            self.session_factory,
            run_id,
            "kg_expert_review",
            f"专家模型完成 KG 评审：{reviewed_count} 条，转人工 {handoff_count} 条",
            {
                "event_type": "expert_review",
                "agent": "kg",
                "tool": "expert_model",
                "reviewed_count": reviewed_count,
                "human_handoff_count": handoff_count,
                "route": "human_review" if handoff_count else "persist",
            },
            level="warning" if handoff_count else "info",
        )
        return {"triples": candidates}

    def _persist(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        with self.session_factory() as db:
            repository = KnowledgeRepository(db)
            repository.set_progress(run_id, "kg_quality", 90, "KG 智能体正在融合实体并保存人工审核路由")
            candidates = _deduplicate_candidates(
                [_attach_agent_metadata(item, "kg") for item in state.get("triples", [])],
                "triple_key",
            )
            count = repository.persist_triples(run_id, candidates, state.get("kg_failures", []))
        _record_agent_event(
            self.session_factory,
            run_id,
            "kg_persist",
            f"KG 智能体已保存 {count} 条去重三元组",
            {"event_type": "persistence", "agent": "kg", "tool": "postgresql", "candidate_count": count},
        )
        return {"metrics": {**state.get("metrics", {}), "triple_count": count}}


class KnowledgeBuildWorkflow:
    def __init__(
        self,
        settings: Settings | None = None,
        storage: KnowledgeStorage | None = None,
        mineru: MinerUClient | None = None,
        extractor: KnowledgeExtractor | None = None,
        session_factory=SessionLocal,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or KnowledgeStorage(self.settings)
        self.mineru = mineru or MinerUClient(self.settings)
        self.extractor = extractor or KnowledgeExtractor(
            gateway=ModelGateway.from_database(self.settings, session_factory),
            settings=self.settings,
        )
        self.session_factory = session_factory
        self.rag_agent = RagDocumentBuildAgent(self.extractor, session_factory)
        self.kg_agent = KnowledgeGraphBuildAgent(self.extractor, session_factory)

    def compile(self, checkpointer=None):
        builder = StateGraph(BuildState)
        builder.add_node("load_document", self._load_document)
        builder.add_node("plan_document", self._plan_document)
        builder.add_node("adaptive_chunk", self._adaptive_chunk)
        builder.add_node("persist_chunks", self._persist_chunks)
        builder.add_node("rag_agent", self._run_rag_agent)
        builder.add_node("kg_agent", self._run_kg_agent)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "load_document")
        builder.add_edge("load_document", "plan_document")
        builder.add_edge("plan_document", "adaptive_chunk")
        builder.add_edge("adaptive_chunk", "persist_chunks")
        builder.add_conditional_edges(
            "persist_chunks",
            self._route_after_chunks,
            {"rag": "rag_agent", "kg": "kg_agent", "finalize": "finalize"},
        )
        builder.add_conditional_edges(
            "rag_agent",
            self._route_after_rag,
            {"kg": "kg_agent", "finalize": "finalize"},
        )
        builder.add_edge("kg_agent", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile(checkpointer=checkpointer)

    def run(self, run_id: UUID) -> BuildState:
        with self.session_factory() as db:
            run = KnowledgeRepository(db).require_run(run_id)
            initial: BuildState = {
                "build_run_id": str(run.id),
                "source_version_id": str(run.source_version_id),
                "targets": list(run.targets),
                "metrics": dict(run.metrics),
            }
            thread_id = run.graph_thread_id
        config = {"configurable": {"thread_id": thread_id}}

        try:
            if self.settings.database_url.startswith("postgresql"):
                from langgraph.checkpoint.postgres import PostgresSaver

                connection_string = self.settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
                with PostgresSaver.from_conn_string(connection_string) as checkpointer:
                    checkpointer.setup()
                    graph = self.compile(checkpointer=checkpointer)
                    snapshot = graph.get_state(config)
                    result = graph.invoke(None if snapshot.values and snapshot.next else initial, config=config)
            else:
                result = self.compile().invoke(initial)
            return result
        except Exception as exc:
            with self.session_factory() as db:
                KnowledgeRepository(db).fail_run(run_id, exc)
            raise

    def _load_document(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        version_id = UUID(state["source_version_id"])
        with self.session_factory() as db:
            repository = KnowledgeRepository(db)
            repository.set_progress(run_id, "load_document", 8, "正在读取并校验文档版本")
            version = db.get(KnowledgeSourceVersion, version_id)
            if version is None:
                raise LookupError("知识源版本不存在")
            markdown_uri = version.markdown_storage_uri

        if not markdown_uri:
            markdown_uri = asyncio.run(self._parse_with_mineru(version_id))
            parser_tool = "mineru"
        else:
            parser_tool = "knowledge_storage"
        markdown = self.storage.read_text(markdown_uri)
        if not markdown.strip():
            raise RuntimeError("Markdown 文档为空")
        _record_agent_event(
            self.session_factory,
            run_id,
            "load_document",
            "总控智能体完成文档加载" if parser_tool == "knowledge_storage" else "总控智能体完成 MinerU 解析",
            {
                "event_type": "tool_call",
                "agent": "orchestrator",
                "tool": parser_tool,
                "decision": "reuse_markdown" if parser_tool == "knowledge_storage" else "parse_with_mineru",
                "markdown_uri": markdown_uri,
            },
        )
        return {"markdown": markdown, "markdown_uri": markdown_uri}

    def _plan_document(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        plan = build_document_plan(
            state["markdown"],
            targets=list(state.get("targets", [])),
            default_target_tokens=self.settings.knowledge_chunk_target_tokens,
            max_reflection_rounds=self.settings.knowledge_max_reflection_rounds,
        )
        with self.session_factory() as db:
            repository = KnowledgeRepository(db)
            repository.set_progress(run_id, "plan_document", 12, "总控智能体正在制定文档构建计划")
            run = repository.require_run(run_id)
            run.config_snapshot = {**dict(run.config_snapshot), "agent_plan": plan}
            repository.event(
                run_id,
                "plan_document",
                f"规划完成：以 H{plan['base_heading_level']} 为知识章，执行 {' → '.join(plan['execution_order'])}",
                payload={
                    "event_type": "agent_plan",
                    "agent": "orchestrator",
                    "route": "execute",
                    "plan": plan,
                },
            )
            db.commit()
        return {
            "agent_plan": plan,
            "metrics": {
                **state.get("metrics", {}),
                "document_token_estimate": int(plan["document_profile"]["estimated_tokens"]),
            },
        }

    def _adaptive_chunk(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        with self.session_factory() as db:
            KnowledgeRepository(db).set_progress(run_id, "adaptive_chunk", 18, "正在按标题层级进行自适应切分")
        plan = dict(state.get("agent_plan", {}))
        target_tokens = int(plan.get("chunk_target_tokens", self.settings.knowledge_chunk_target_tokens))
        chunker = AdaptiveMarkdownChunker(
            target_tokens=target_tokens,
            defer_semantic=True,
        )
        structural = chunker.split(state["markdown"])

        async def refine() -> list[DocumentChunk]:
            output: list[DocumentChunk] = []
            for chunk in structural:
                output.extend(await self.extractor.semantic_split(chunk))
            return output

        refined = asyncio.run(refine())
        normalized = [chunk.model_copy(update={"ordinal": index}) for index, chunk in enumerate(refined)]
        if not normalized:
            raise RuntimeError("文档切分后没有可用 Chunk")
        strategy_counts = dict(Counter(chunk.split_strategy for chunk in normalized))
        _record_agent_event(
            self.session_factory,
            run_id,
            "adaptive_chunk",
            f"切分智能体生成 {len(normalized)} 个可追溯 Chunk",
            {
                "event_type": "tool_call",
                "agent": "orchestrator",
                "tool": "adaptive_markdown_chunker",
                "chunk_target_tokens": target_tokens,
                "chunk_count": len(normalized),
                "split_strategies": strategy_counts,
                "semantic_fallback_count": strategy_counts.get("semantic_fallback", 0),
            },
        )
        return {
            "chunks": [chunk.model_dump(mode="json") for chunk in normalized],
            "metrics": {**state.get("metrics", {}), "chunk_count": len(normalized)},
        }

    def _persist_chunks(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        with self.session_factory() as db:
            repository = KnowledgeRepository(db)
            repository.set_progress(run_id, "persist_chunks", 30, "正在保存可追溯 Chunk")
            repository.persist_chunks(run_id, state.get("chunks", []))
        _record_agent_event(
            self.session_factory,
            run_id,
            "persist_chunks",
            "总控智能体已建立 Chunk 追溯基线",
            {
                "event_type": "persistence",
                "agent": "orchestrator",
                "tool": "postgresql",
                "chunk_count": len(state.get("chunks", [])),
                "route": self._route_after_chunks(state),
            },
        )
        return {}

    @staticmethod
    def _route_after_chunks(state: BuildState) -> str:
        targets = set(state.get("targets", []))
        if "rag" in targets:
            return "rag"
        if "kg" in targets:
            return "kg"
        return "finalize"

    @staticmethod
    def _route_after_rag(state: BuildState) -> str:
        return "kg" if "kg" in set(state.get("targets", [])) else "finalize"

    def _run_rag_agent(self, state: BuildState) -> dict[str, Any]:
        if "rag" not in state.get("targets", []):
            return {}
        result = self.rag_agent.invoke(state)
        return {
            "qa_items": result.get("qa_items", []),
            "rag_failures": result.get("rag_failures", []),
            "rag_revision_round": int(result.get("rag_revision_round", 0)),
            "rag_risk_summary": dict(result.get("rag_risk_summary", {})),
            "metrics": result.get("metrics", state.get("metrics", {})),
        }

    def _run_kg_agent(self, state: BuildState) -> dict[str, Any]:
        if "kg" not in state.get("targets", []):
            return {}
        result = self.kg_agent.invoke(state)
        return {
            "triples": result.get("triples", []),
            "kg_failures": result.get("kg_failures", []),
            "kg_revision_round": int(result.get("kg_revision_round", 0)),
            "kg_risk_summary": dict(result.get("kg_risk_summary", {})),
            "metrics": {**state.get("metrics", {}), **result.get("metrics", {})},
        }

    def _finalize(self, state: BuildState) -> dict[str, Any]:
        run_id = UUID(state["build_run_id"])
        with self.session_factory() as db:
            repository = KnowledgeRepository(db)
            repository.set_progress(run_id, "finalize", 98, "正在汇总构建结果")
            metrics = repository.finish_extraction(run_id)
        _record_agent_event(
            self.session_factory,
            run_id,
            "finalize",
            "总控智能体已完成构建并执行最终路由",
            {
                "event_type": "quality_decision",
                "agent": "orchestrator",
                "route": "human_review" if metrics["review_count"] else "ready_to_publish",
                "metrics": metrics,
                "rag_revision_round": int(state.get("rag_revision_round", 0)),
                "kg_revision_round": int(state.get("kg_revision_round", 0)),
            },
            level="warning" if metrics["review_count"] else "info",
        )
        return {"metrics": {**state.get("metrics", {}), **metrics}, "review_count": metrics["review_count"]}

    async def _parse_with_mineru(self, version_id: UUID) -> str:
        with self.session_factory() as db:
            version = db.get(KnowledgeSourceVersion, version_id)
            if version is None:
                raise LookupError("知识源版本不存在")
            source_id = version.source_id
            version_label = version.version
            original_uri = version.original_storage_uri
            version.status = "parsing"
            db.commit()

        safe_version = re.sub(r"[^A-Za-z0-9_.-]+", "-", version_label).strip("-") or "v1"
        with tempfile.TemporaryDirectory(prefix="canw-mineru-") as temp_dir:
            local_path = Path(temp_dir) / safe_filename(Path(original_uri).name)
            self.storage.materialize(original_uri, local_path)
            batch = await self.mineru.create_upload_batch(
                [{"name": local_path.name, "data_id": str(version_id), "is_ocr": False}]
            )
            with self.session_factory() as db:
                version = db.get(KnowledgeSourceVersion, version_id)
                if version:
                    version.parser = "mineru_v4"
                    version.parser_task_id = batch.batch_id
                    db.commit()
            await self.mineru.upload_signed_file(batch.upload_urls[0], local_path)
            result = await self.mineru.wait_for_batch(batch.batch_id)
            zip_urls = self.mineru.full_zip_urls(result)
            if not zip_urls:
                raise RuntimeError("MinerU 完成任务但未返回 full_zip_url")
            zip_bytes = await _download_bytes(zip_urls[0], max_bytes=self.settings.knowledge_upload_max_bytes * 3)
            markdown = _extract_full_markdown(zip_bytes)

        prefix = f"knowledge/{source_id}/{safe_version}/mineru"
        zip_object = self.storage.put_bytes(f"{prefix}/result.zip", zip_bytes, "application/zip")
        markdown_object = self.storage.put_bytes(f"{prefix}/full.md", markdown.encode("utf-8"), "text/markdown")
        with self.session_factory() as db:
            version = db.get(KnowledgeSourceVersion, version_id)
            if version is None:
                raise LookupError("知识源版本不存在")
            version.markdown_storage_uri = markdown_object.uri
            version.status = "parsed"
            version.parser_metadata = {
                "batch_id": batch.batch_id,
                "result_zip_uri": zip_object.uri,
                "model_version": self.settings.mineru_model_version,
            }
            db.commit()
        return markdown_object.uri


def build_document_plan(
    markdown: str,
    *,
    targets: list[str],
    default_target_tokens: int,
    max_reflection_rounds: int,
) -> dict[str, Any]:
    heading_counts = Counter(
        len(match.group(1))
        for match in re.finditer(r"^(#{1,6})\s+.+$", markdown, flags=re.MULTILINE)
    )
    if heading_counts.get(3):
        base_heading_level = 3
    elif heading_counts.get(2):
        base_heading_level = 2
    elif heading_counts.get(1):
        base_heading_level = 1
    else:
        base_heading_level = 0
    table_rows = sum(1 for line in markdown.splitlines() if line.count("|") >= 2)
    qa_markers = len(re.findall(r"(?:^|\n)\s*(?:Q|A|问|答)\s*[：:]", markdown, flags=re.IGNORECASE))
    knowledge_markers = len(
        re.findall(r"症状|病因|原因|诊断|传播|防治|温度|湿度|浓度|剂量|步骤|方法", markdown)
    )
    execution_order = [agent for agent in ("rag", "kg") if agent in set(targets)]
    reasons = [
        f"检测到 H{base_heading_level} 作为最稳定的知识章层级"
        if base_heading_level
        else "未检测到稳定标题层级，将使用全文与段落兜底切分",
        "保留完整章节，超长内容才进入语义复切",
    ]
    if table_rows:
        reasons.append(f"检测到 {table_rows} 行表格结构，切分时保持表格完整")
    if qa_markers:
        reasons.append(f"检测到 {qa_markers} 个问答标记，RAG 抽取优先保留完整问答对")
    return {
        "planner": "document_build_planner_v1",
        "execution_order": execution_order,
        "base_heading_level": base_heading_level,
        "chunk_target_tokens": default_target_tokens,
        "semantic_split_strategy": "llm_then_deterministic_fallback",
        "max_reflection_rounds": max_reflection_rounds,
        "quality_route": "rules_then_reflection_then_expert_then_human",
        "tools": [
            "adaptive_markdown_chunker",
            *(["qa_model"] if "rag" in execution_order else []),
            *(["kg_model", "silkworm_glossary"] if "kg" in execution_order else []),
            "expert_model",
            "postgresql",
        ],
        "reasons": reasons,
        "document_profile": {
            "estimated_tokens": estimate_tokens(markdown),
            "heading_counts": {f"h{level}": heading_counts.get(level, 0) for level in range(1, 7)},
            "table_rows": table_rows,
            "qa_markers": qa_markers,
            "knowledge_density_markers": knowledge_markers,
        },
    }


async def _download_bytes(url: str, max_bytes: int) -> bytes:
    content = bytearray()
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes(1024 * 1024):
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise RuntimeError("MinerU 结果压缩包超过允许大小")
    return bytes(content)


def _extract_full_markdown(zip_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        candidates = [member for member in archive.infolist() if Path(member.filename).name == "full.md"]
        if not candidates:
            raise RuntimeError("MinerU 结果压缩包中没有 full.md")
        member = min(candidates, key=lambda item: len(Path(item.filename).parts))
        if member.file_size > 50 * 1024 * 1024:
            raise RuntimeError("MinerU full.md 超过安全大小限制")
        return archive.read(member).decode("utf-8-sig")


def _safe_error(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {str(exc)[:400]}"

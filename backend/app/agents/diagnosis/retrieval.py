from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.agents.diagnosis.gateway import DiagnosisAgentGateway
from app.agents.diagnosis.knowledge import BM25Retriever, HNSWRetriever, KGRetriever
from app.agents.diagnosis.types import AgentState, EvidenceItem, QueryPlan
from app.core.config import Settings


class RAGRetrievalAgent:
    """Agent 3: two-channel Agentic Query over HNSW and BM25."""

    def __init__(
        self,
        settings: Settings,
        gateway: DiagnosisAgentGateway,
        *,
        hnsw: HNSWRetriever | None = None,
        bm25: BM25Retriever | None = None,
    ) -> None:
        self.settings = settings
        self.gateway = gateway
        self.hnsw = hnsw or HNSWRetriever(settings)
        self.bm25 = bm25 or BM25Retriever(settings)

    def __call__(self, state: AgentState) -> dict[str, Any]:
        emit = state["emit"]
        plan = state["query_plan"]
        snapshot = state.get("knowledge_snapshot", {})
        emit(
            agent="agent3_rag",
            stage="plan",
            status="started",
            title="RAG 智能体开始检索",
            summary="HNSW 语义检索与 BM25 关键词检索将并行执行并按结果自适应改写。",
            payload={"channels": ["hnsw", "bm25"]},
        )
        if not _channel_available(snapshot, "rag"):
            reason = str(snapshot.get("rag_reason") or snapshot.get("reason") or "当前没有可用的已发布 RAG 文档知识")
            emit(
                agent="agent3_rag",
                stage="knowledge_snapshot",
                status="degraded",
                title="RAG 文档知识尚未构建",
                summary=reason,
                payload={"hits": 0},
            )
            return {
                "rag_evidence": [],
                "branch_metrics": [{"agent": "rag", "rounds": 0, "hits": 0, "knowledge_unavailable": True}],
                "branch_errors": [reason],
            }

        dense_queries = _unique(plan.dense_queries or [plan.standalone_question], limit=3)
        bm25_queries = _unique(plan.bm25_queries or [plan.standalone_question], limit=4)
        attempted_dense: list[str] = []
        attempted_bm25: list[str] = []
        dense_results: list[EvidenceItem] = []
        bm25_results: list[EvidenceItem] = []
        errors: list[str] = []
        rounds = 0

        max_rounds = max(1, min(self.settings.diagnosis_agent_max_retrieval_rounds, 3))
        for round_index in range(1, max_rounds + 1):
            rounds = round_index
            current_dense = [query for query in dense_queries if query not in attempted_dense][:3]
            current_bm25 = [query for query in bm25_queries if query not in attempted_bm25][:4]
            if not current_dense and not current_bm25:
                break
            attempted_dense.extend(current_dense)
            attempted_bm25.extend(current_bm25)
            emit(
                agent="agent3_rag",
                stage="query_round",
                status="progress",
                title=f"RAG 第 {round_index} 轮查询",
                summary="正在并行匹配语义相近内容与精确领域词。",
                payload={
                    "round": round_index,
                    "hnsw_queries": current_dense,
                    "bm25_queries": current_bm25,
                },
            )

            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag-query") as executor:
                dense_future = executor.submit(self._search_hnsw, current_dense, snapshot)
                bm25_future = executor.submit(self._search_bm25, current_bm25, snapshot)
                try:
                    dense_results.extend(dense_future.result())
                except Exception as error:
                    errors.append(f"HNSW:{error.__class__.__name__}")
                    emit(
                        agent="agent3_rag",
                        stage="hnsw",
                        status="degraded",
                        title="HNSW 检索暂不可用",
                        summary="语义通道失败，继续使用 BM25 通道。",
                        payload={"round": round_index},
                        internal_payload={"error_type": error.__class__.__name__},
                    )
                try:
                    bm25_results.extend(bm25_future.result())
                except Exception as error:
                    errors.append(f"BM25:{error.__class__.__name__}")
                    emit(
                        agent="agent3_rag",
                        stage="bm25",
                        status="degraded",
                        title="BM25 检索暂不可用",
                        summary="关键词通道失败，继续使用 HNSW 通道。",
                        payload={"round": round_index},
                        internal_payload={"error_type": error.__class__.__name__},
                    )

            fused_preview = reciprocal_rank_fusion(dense_results, bm25_results)
            observation = _rag_coverage(fused_preview)
            emit(
                agent="agent3_rag",
                stage="observe",
                status="progress",
                title=f"RAG 第 {round_index} 轮结果评估",
                summary=(
                    f"HNSW 累计 {len(_dedup(dense_results))} 条，BM25 累计 {len(_dedup(bm25_results))} 条，"
                    f"融合后 {observation['unique_hits']} 条。"
                ),
                payload={"round": round_index, **observation},
            )
            if observation["adequate"] or round_index >= max_rounds:
                break

            summaries = [item.title for item in fused_preview[:5]]
            dense_refinements = self.gateway.suggest_query_refinement(
                channel="HNSW semantic retrieval",
                question=plan.standalone_question,
                attempted_queries=attempted_dense,
                result_summaries=summaries,
                entities=plan.entities,
            )
            bm25_refinements = self.gateway.suggest_query_refinement(
                channel="BM25 exact keyword retrieval",
                question=plan.standalone_question,
                attempted_queries=attempted_bm25,
                result_summaries=summaries,
                entities=plan.entities,
            )
            dense_queries.extend(
                dense_refinements
                or _fallback_dense_refinements(plan, attempted=attempted_dense)
            )
            bm25_queries.extend(
                bm25_refinements
                or _fallback_bm25_refinements(plan, attempted=attempted_bm25)
            )
            emit(
                agent="agent3_rag",
                stage="refine",
                status="progress",
                title="RAG 已调整下一轮查询",
                summary="根据覆盖度补充同义表达、实体词和处置维度。",
                payload={
                    "round": round_index,
                    "next_hnsw_queries": [query for query in dense_queries if query not in attempted_dense][:3],
                    "next_bm25_queries": [query for query in bm25_queries if query not in attempted_bm25][:4],
                },
            )

        fused = reciprocal_rank_fusion(dense_results, bm25_results)
        rerank_used = False
        if fused:
            try:
                fused = self._rerank(plan.standalone_question, fused)
                rerank_used = True
            except Exception as error:
                errors.append(f"RERANK:{error.__class__.__name__}")
                emit(
                    agent="agent3_rag",
                    stage="rerank",
                    status="degraded",
                    title="精排暂不可用",
                    summary="已保留 RRF 融合顺序继续处理。",
                    payload={"candidate_count": len(fused)},
                    internal_payload={"error_type": error.__class__.__name__},
                )
        fused = fused[: self.settings.diagnosis_agent_fusion_top_k]
        for index, item in enumerate(fused, start=1):
            item.rank_order = index
        emit(
            agent="agent3_rag",
            stage="complete",
            status="completed" if fused else "degraded",
            title="RAG 检索完成" if fused else "RAG 未检索到可用证据",
            summary=f"完成 {rounds} 轮查询，融合后保留 {len(fused)} 条候选证据。",
            payload={
                "rounds": rounds,
                "hnsw_hits": len(_dedup(dense_results)),
                "bm25_hits": len(_dedup(bm25_results)),
                "fused_hits": len(fused),
                "rerank_used": rerank_used,
            },
        )
        return {
            "rag_evidence": fused,
            "branch_metrics": [
                {
                    "agent": "rag",
                    "rounds": rounds,
                    "hnsw_hits": len(_dedup(dense_results)),
                    "bm25_hits": len(_dedup(bm25_results)),
                    "hits": len(fused),
                    "rerank_used": rerank_used,
                }
            ],
            "branch_errors": errors,
        }

    def _search_hnsw(self, queries: list[str], snapshot: dict[str, Any]) -> list[EvidenceItem]:
        vectors = self.gateway.embed(queries)
        results: list[EvidenceItem] = []
        per_query_limit = max(3, self.settings.diagnosis_agent_dense_top_k // max(1, len(queries)))
        for query, vector in zip(queries, vectors, strict=True):
            for item in self.hnsw.search(vector=vector, snapshot=snapshot, limit=per_query_limit):
                item.metadata["query"] = query
                results.append(item)
        return results

    def _search_bm25(self, queries: list[str], snapshot: dict[str, Any]) -> list[EvidenceItem]:
        results: list[EvidenceItem] = []
        per_query_limit = max(3, self.settings.diagnosis_agent_bm25_top_k // max(1, len(queries)))
        for query in queries:
            for item in self.bm25.search(query=query, snapshot=snapshot, limit=per_query_limit):
                item.metadata["query"] = query
                results.append(item)
        return results

    def _rerank(self, question: str, candidates: list[EvidenceItem]) -> list[EvidenceItem]:
        top_candidates = candidates[: self.settings.diagnosis_agent_fusion_top_k]
        rows = self.gateway.rerank(
            question,
            [f"{item.title}\n{item.content}" for item in top_candidates],
            top_n=len(top_candidates),
        )
        reranked: list[EvidenceItem] = []
        used: set[int] = set()
        for row in rows:
            try:
                index = int(row.get("index"))
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= len(top_candidates) or index in used:
                continue
            used.add(index)
            item = top_candidates[index]
            rerank_score = row.get("relevance_score", row.get("score"))
            if isinstance(rerank_score, (int, float)):
                item.metadata["rerank_score"] = float(rerank_score)
                item.score = float(rerank_score)
            reranked.append(item)
        reranked.extend(item for index, item in enumerate(top_candidates) if index not in used)
        return reranked


class KGRetrievalAgent:
    """Agent 2: entity-linked, bounded Agentic Query over fixed Cypher templates."""

    def __init__(
        self,
        settings: Settings,
        gateway: DiagnosisAgentGateway,
        *,
        kg: KGRetriever | None = None,
    ) -> None:
        self.settings = settings
        self.gateway = gateway
        self.kg = kg or KGRetriever(settings)

    def __call__(self, state: AgentState) -> dict[str, Any]:
        emit = state["emit"]
        plan = state["query_plan"]
        snapshot = state.get("knowledge_snapshot", {})
        emit(
            agent="agent2_kg",
            stage="plan",
            status="started",
            title="KG 智能体开始查询",
            summary="先做实体匹配，再按覆盖度扩展相邻关系；查询只使用固定安全模板。",
            payload={"initial_terms": plan.kg_terms[:8]},
        )
        if not _channel_available(snapshot, "kg"):
            reason = str(snapshot.get("kg_reason") or snapshot.get("reason") or "Neo4j Aura 图谱尚未配置")
            emit(
                agent="agent2_kg",
                stage="knowledge_snapshot",
                status="degraded",
                title="KG 图谱连接不可用",
                summary=reason,
                payload={"hits": 0},
            )
            return {
                "kg_evidence": [],
                "branch_metrics": [{"agent": "kg", "rounds": 0, "hits": 0, "knowledge_unavailable": True}],
                "branch_errors": [reason],
            }

        if snapshot.get("kg_mode") == "aura_curated":
            emit(
                agent="agent2_kg",
                stage="knowledge_source",
                status="progress",
                title="KG 已接入 Neo4j Aura 图谱",
                summary="直接查询已接入的家蚕疾病知识图谱，不依赖 RAG 文档发布状态。",
                payload={"mode": "aura_curated", "publication_count": len(snapshot.get("publication_ids", []))},
            )

        terms = _unique([*plan.kg_terms, *plan.entities], limit=10)
        attempted: list[str] = []
        evidence: list[EvidenceItem] = []
        errors: list[str] = []
        anchors: list[str] = []
        rounds = 0
        max_rounds = max(1, min(self.settings.diagnosis_agent_max_retrieval_rounds, 3))
        for round_index in range(1, max_rounds + 1):
            current_terms = [term for term in terms if term not in attempted][:10]
            if not current_terms and not anchors:
                break
            rounds = round_index
            attempted.extend(current_terms)
            emit(
                agent="agent2_kg",
                stage="query_round",
                status="progress",
                title=f"KG 第 {round_index} 轮关系查询",
                summary="正在进行实体消歧与关系路径匹配。" if round_index == 1 else "正在围绕已命中实体扩展相邻路径。",
                payload={"round": round_index, "terms": current_terms, "anchor_count": len(anchors)},
            )
            try:
                rows = self.kg.search(
                    terms=current_terms or attempted,
                    anchors=anchors,
                    snapshot=snapshot,
                    limit=max(8, self.settings.diagnosis_agent_fusion_top_k),
                )
                evidence.extend(rows)
            except Exception as error:
                errors.append(f"KG:{error.__class__.__name__}")
                emit(
                    agent="agent2_kg",
                    stage="query",
                    status="degraded",
                    title="KG 查询暂不可用",
                    summary="图谱通道未返回结果，联合路由仍可继续使用 RAG 证据。",
                    payload={"round": round_index},
                    internal_payload={"error_type": error.__class__.__name__},
                )
                break

            unique = _dedup(evidence)
            observation = _kg_coverage(unique, plan)
            emit(
                agent="agent2_kg",
                stage="observe",
                status="progress",
                title=f"KG 第 {round_index} 轮结果评估",
                summary=f"当前命中 {observation['unique_hits']} 条路径、{observation['relation_count']} 类关系。",
                payload={"round": round_index, **observation},
            )
            if observation["adequate"] or round_index >= max_rounds:
                break

            anchors = _kg_anchors(unique)
            summaries = [item.title for item in unique[:5]]
            refinements = self.gateway.suggest_query_refinement(
                channel="knowledge graph entity and relation retrieval",
                question=plan.standalone_question,
                attempted_queries=attempted,
                result_summaries=summaries,
                entities=plan.entities,
            )
            terms.extend(refinements or _fallback_kg_refinements(plan, unique))
            emit(
                agent="agent2_kg",
                stage="refine",
                status="progress",
                title="KG 已调整下一轮查询",
                summary="根据已命中的疾病或症状实体扩展相关诊断、病因和防治关系。",
                payload={
                    "round": round_index,
                    "anchors": anchors[:6],
                    "next_terms": [term for term in terms if term not in attempted][:8],
                },
            )

        final = _dedup(evidence)[: self.settings.diagnosis_agent_fusion_top_k]
        for index, item in enumerate(final, start=1):
            item.rank_order = index
        emit(
            agent="agent2_kg",
            stage="complete",
            status="completed" if final else "degraded",
            title="KG 查询完成" if final else "KG 未查询到可用路径",
            summary=f"完成 {rounds} 轮查询，保留 {len(final)} 条关系证据。",
            payload={
                "rounds": rounds,
                "path_hits": len(final),
                "relation_count": len({item.metadata.get('relation') for item in final if item.metadata.get('relation')}),
            },
        )
        return {
            "kg_evidence": final,
            "branch_metrics": [{"agent": "kg", "rounds": rounds, "hits": len(final)}],
            "branch_errors": errors,
        }


def reciprocal_rank_fusion(
    dense_results: list[EvidenceItem],
    bm25_results: list[EvidenceItem],
    *,
    constant: int = 60,
) -> list[EvidenceItem]:
    by_key: dict[str, EvidenceItem] = {}
    scores: dict[str, float] = {}
    channel_scores: dict[str, dict[str, float]] = {}
    for channel, items in (("hnsw", _dedup(dense_results)), ("bm25", _dedup(bm25_results))):
        for rank, item in enumerate(items, start=1):
            key = item.evidence_key
            scores[key] = scores.get(key, 0.0) + 1.0 / (constant + rank)
            channel_scores.setdefault(key, {})[channel] = float(item.score or 0.0)
            current = by_key.get(key)
            if current is None or (item.score or 0.0) > (current.score or 0.0):
                by_key[key] = item.model_copy(deep=True)
    ordered = sorted(by_key, key=lambda key: scores[key], reverse=True)
    result: list[EvidenceItem] = []
    for key in ordered:
        item = by_key[key]
        channels = sorted(channel_scores[key])
        item.retriever = "+".join(channels)
        item.score = scores[key]
        item.metadata["channels"] = channels
        item.metadata["channel_scores"] = channel_scores[key]
        item.metadata["rrf_score"] = scores[key]
        result.append(item)
    return result


def _rag_coverage(items: list[EvidenceItem]) -> dict[str, Any]:
    unique = _dedup(items)
    sources = {item.source_name for item in unique if item.source_name}
    channels = {
        channel
        for item in unique
        for channel in item.metadata.get("channels", [item.retriever])
    }
    adequate = len(unique) >= 4 or (len(unique) >= 2 and len(channels) >= 2) or len(sources) >= 2
    return {
        "unique_hits": len(unique),
        "source_count": len(sources),
        "channels_with_hits": sorted(channels),
        "adequate": adequate,
    }


def _kg_coverage(items: list[EvidenceItem], plan: QueryPlan) -> dict[str, Any]:
    relations = {item.metadata.get("relation") for item in items if item.metadata.get("relation")}
    adequate = len(items) >= 3 or (plan.intent == "entity_relation" and len(items) >= 1)
    return {"unique_hits": len(items), "relation_count": len(relations), "adequate": adequate}


def _fallback_dense_refinements(plan: QueryPlan, *, attempted: list[str]) -> list[str]:
    candidates = [
        f"{plan.standalone_question} 诊断依据与鉴别特征",
        f"{' '.join(plan.entities[:4]) or plan.standalone_question} 发生条件 病因",
        f"{' '.join(plan.entities[:4]) or plan.standalone_question} 防治 消毒 处置",
    ]
    return [value for value in _unique(candidates, limit=3) if value not in attempted]


def _fallback_bm25_refinements(plan: QueryPlan, *, attempted: list[str]) -> list[str]:
    exact = " ".join(_query_tokens(plan.standalone_question)[:10])
    candidates = [
        exact,
        " ".join([*plan.entities[:5], "症状", "诊断依据"]),
        " ".join([*plan.entities[:5], "防治措施", "消毒"]),
    ]
    return [value for value in _unique(candidates, limit=3) if value not in attempted]


def _fallback_kg_refinements(plan: QueryPlan, evidence: list[EvidenceItem]) -> list[str]:
    values = [*plan.entities]
    for item in evidence[:5]:
        values.extend([str(item.metadata.get("subject") or ""), str(item.metadata.get("object") or "")])
    values.extend(["诊断依据", "发生条件", "防治措施"])
    return _unique(values, limit=10)


def _kg_anchors(items: list[EvidenceItem]) -> list[str]:
    anchors: list[str] = []
    for item in items[:10]:
        subject = str(item.metadata.get("subject") or "")
        subject_labels = [str(value) for value in item.metadata.get("subject_labels", [])]
        object_name = str(item.metadata.get("object") or "")
        object_labels = [str(value) for value in item.metadata.get("object_labels", [])]
        if "疾病" in subject_labels and subject:
            anchors.append(subject)
        if "疾病" in object_labels and object_name:
            anchors.append(object_name)
    if not anchors:
        anchors.extend(str(item.metadata.get("subject") or "") for item in items[:4])
    return _unique(anchors, limit=6)


def _dedup(items: list[EvidenceItem]) -> list[EvidenceItem]:
    result: list[EvidenceItem] = []
    seen: set[str] = set()
    for item in items:
        if item.evidence_key in seen:
            continue
        seen.add(item.evidence_key)
        result.append(item)
    return result


def _query_tokens(value: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]{2,10}|[A-Za-z0-9.%℃]+", value)


def _channel_available(snapshot: dict[str, Any], channel: str) -> bool:
    key = f"{channel}_available"
    if key in snapshot:
        return bool(snapshot.get(key))
    return bool(snapshot.get("available"))


def _unique(values: list[str], *, limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = " ".join(str(value).split())[:180]
        if normalized and normalized not in result:
            result.append(normalized)
        if len(result) >= limit:
            break
    return result

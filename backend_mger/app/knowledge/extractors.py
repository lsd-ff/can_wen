from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.config import Settings, get_settings
from app.knowledge.markdown import estimate_tokens, fallback_semantic_split
from app.knowledge.model_gateway import ModelGateway, ModelGatewayError
from app.knowledge.quality import validate_qa, validate_triple
from app.knowledge.schema import KG_RELATIONS, KG_SCHEMA_LABELS, SilkwormGlossary
from app.knowledge.types import (
    DocumentChunk,
    ExpertAssessment,
    QAExtraction,
    QAExtractionBatch,
    SemanticSegments,
    TripleExtraction,
    TripleExtractionBatch,
)


QA_SYSTEM_PROMPT = """你是养蚕领域 RAG 数据构建智能体。只根据给定原文生成可独立理解的中文问答。
要求：问题必须包含明确主题；答案以原文事实为边界，可做不改变事实的解释性组织；数字、剂量、温度、浓度和时长不得自行增加；evidence 必须逐字摘自原文；覆盖概念、症状、原因、步骤、参数、诊断和防治等适用知识类型。只返回 JSON。"""

KG_SYSTEM_PROMPT = """你是家蚕疾病知识图谱抽取智能体。严格按照提供的 Schema 从原文抽取显式三元组。
不得创造原文没有支撑的实体或关系；subject 必须是 Disease；evidence 必须逐字摘自原文；不要创建 Document、Evidence、DrugParameter 等节点；剂量、浓度和温度保留在 Measure 名称或证据文本中。只返回 JSON。"""

EXPERT_SYSTEM_PROMPT = """你是养蚕知识库的独立专家评审模型。检查候选数据是否被原文支撑、是否违反 Schema、是否有歧义、泛化、缺失条件或参数幻觉。宁可送人工审核，也不要放行证据不足的数据。只返回 JSON。"""

SEMANTIC_SPLIT_SYSTEM_PROMPT = """你是 Markdown 语义切分器。将超长知识章节切成若干语义完整的连续片段，保留全部原文，不改写、不概括、不遗漏，不拆散表格、步骤或问答对。每段不超过给定 token 目标。segments 中只能放原文的连续子串。只返回 JSON。"""

QA_REFLECTION_SYSTEM_PROMPT = """你是养蚕领域 RAG 数据修正智能体。根据候选问答、质量风险和原始 Chunk 修正问答。问题必须脱离上下文独立成立；答案必须以原文事实为边界；evidence 必须是原文连续摘录；不得新增原文没有的温度、湿度、剂量、浓度或时长。保留有价值的信息，修正而不是扩写。只返回符合给定 Schema 的 JSON。"""

KG_RESOLUTION_SYSTEM_PROMPT = """你是家蚕疾病知识图谱消歧与修正智能体。根据候选三元组、质量风险、固定 Schema、领域词表提示和原始 Chunk 修正候选。只能输出原文明示且证据可逐字定位的关系；不得创造新标签、新关系或原文没有的实体；无法可靠消歧时保留原名称，交由后续专家或人工审核。只返回符合给定 Schema 的 JSON。"""


REFINABLE_QA_FLAGS = frozenset(
    {
        "question_too_generic",
        "question_context_dependent",
        "answer_too_short",
        "evidence_missing",
        "unsupported_parameter",
        "keywords_missing",
    }
)

REFINABLE_KG_FLAGS = frozenset(
    {
        "unknown_subject_type",
        "unknown_object_type",
        "unknown_relation",
        "relation_type_mismatch",
        "evidence_missing",
        "ambiguous_subject",
        "ambiguous_object",
        "unknown_disease",
    }
)


def dynamic_qa_count(chunk: DocumentChunk) -> int:
    if chunk.token_count <= 350:
        base = 1
    elif chunk.token_count <= 700:
        base = 3
    else:
        base = 5
    density_terms = len(re.findall(r"症状|病因|原因|步骤|方法|温度|湿度|浓度|剂量|防治|诊断|传播", chunk.content))
    table_bonus = 1 if "contains_table" in chunk.quality_flags else 0
    return min(8, max(1, base + min(2, density_terms // 5) + table_bonus))


class KnowledgeExtractor:
    def __init__(
        self,
        gateway: ModelGateway | None = None,
        glossary: SilkwormGlossary | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.gateway = gateway or ModelGateway(self.settings)
        self.glossary = glossary or SilkwormGlossary.default()

    async def extract_qa(self, chunk: DocumentChunk, *, defer_expert: bool = False) -> list[dict[str, Any]]:
        count = dynamic_qa_count(chunk)
        prompt = json.dumps(
            {
                "heading_path": chunk.heading_path,
                "target_count": count,
                "output_schema": {
                    "items": [
                        {
                            "question": "string",
                            "answer": "string",
                            "evidence": "原文连续摘录",
                            "keywords": ["string"],
                            "knowledge_types": ["concept|symptom|cause|step|parameter|diagnosis|prevention|other"],
                            "confidence": "0..1",
                        }
                    ]
                },
                "content": chunk.content,
            },
            ensure_ascii=False,
        )
        batch = await self.gateway.chat_json(
            model=self.settings.qa_model_id,
            system_prompt=QA_SYSTEM_PROMPT,
            user_prompt=prompt,
            response_model=QAExtractionBatch,
            purpose="qa",
            enable_thinking=False,
            temperature=0.1,
        )
        assert isinstance(batch, QAExtractionBatch)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in batch.items[:count]:
            question_hash = hashlib.sha256("".join(item.question.split()).encode("utf-8")).hexdigest()
            if question_hash in seen:
                continue
            seen.add(question_hash)
            quality = validate_qa(item, chunk)
            result = {
                **item.model_dump(),
                "question_sha256": question_hash,
                "rule_score": quality.score,
                "risk_flags": list(quality.flags),
                "review_status": "needs_review" if quality.requires_review else "approved",
                "revision_count": 0,
                "revision_history": [],
            }
            if quality.requires_review and not defer_expert:
                result = await self.expert_review_candidate("qa", result, chunk)
            results.append(result)
        return results

    async def extract_triples(self, chunk: DocumentChunk, *, defer_expert: bool = False) -> list[dict[str, Any]]:
        relation_schema = {
            relation: {"subject_type": pair[0], "object_type": pair[1]}
            for relation, pair in KG_RELATIONS.items()
        }
        prompt = json.dumps(
            {
                "heading_path": chunk.heading_path,
                "labels": KG_SCHEMA_LABELS,
                "relations": relation_schema,
                "output_schema": {
                    "items": [
                        {
                            "subject_name": "string",
                            "subject_type": "Disease",
                            "relation": "relation enum",
                            "object_name": "string",
                            "object_type": "label enum",
                            "evidence": "原文连续摘录",
                            "confidence": "0..1",
                        }
                    ]
                },
                "content": chunk.content,
            },
            ensure_ascii=False,
        )
        batch = await self.gateway.chat_json(
            model=self.settings.kg_model_id,
            system_prompt=KG_SYSTEM_PROMPT,
            user_prompt=prompt,
            response_model=TripleExtractionBatch,
            purpose="kg",
            enable_thinking=False,
            temperature=0.1,
        )
        assert isinstance(batch, TripleExtractionBatch)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in batch.items:
            quality, subject_canonical, object_canonical, resolution = validate_triple(item, chunk, self.glossary)
            key_material = "\x1f".join(
                [subject_canonical, item.subject_type, item.relation, object_canonical, item.object_type]
            )
            triple_key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
            if triple_key in seen:
                continue
            seen.add(triple_key)
            result = {
                **item.model_dump(),
                "subject_canonical_name": subject_canonical,
                "object_canonical_name": object_canonical,
                "triple_key": triple_key,
                "rule_score": quality.score,
                "risk_flags": list(quality.flags),
                "resolution_metadata": resolution,
                "review_status": "needs_review" if quality.requires_review else "approved",
                "revision_count": 0,
                "revision_history": [],
            }
            if quality.requires_review and not defer_expert:
                result = await self.expert_review_candidate("triple", result, chunk)
            results.append(result)
        return results

    async def revise_qa_candidate(self, candidate: dict[str, Any], chunk: DocumentChunk) -> dict[str, Any]:
        before_flags = list(candidate.get("risk_flags", []))
        prompt = json.dumps(
            {
                "heading_path": chunk.heading_path,
                "quality_risks": before_flags,
                "candidate": {
                    key: candidate.get(key)
                    for key in ("question", "answer", "evidence", "keywords", "knowledge_types", "confidence")
                },
                "output_schema": {
                    "question": "string",
                    "answer": "string",
                    "evidence": "原文连续摘录",
                    "keywords": ["string"],
                    "knowledge_types": ["concept|symptom|cause|step|parameter|diagnosis|prevention|other"],
                    "confidence": "0..1",
                },
                "source_content": chunk.content,
            },
            ensure_ascii=False,
        )
        revised = await self.gateway.chat_json(
            model=self.settings.qa_model_id,
            system_prompt=QA_REFLECTION_SYSTEM_PROMPT,
            user_prompt=prompt,
            response_model=QAExtraction,
            purpose="qa",
            enable_thinking=False,
            temperature=0.0,
        )
        assert isinstance(revised, QAExtraction)
        quality = validate_qa(revised, chunk)
        question_hash = hashlib.sha256("".join(revised.question.split()).encode("utf-8")).hexdigest()
        history = [
            *list(candidate.get("revision_history", [])),
            {
                "round": int(candidate.get("revision_count", 0)) + 1,
                "risk_before": before_flags,
                "risk_after": list(quality.flags),
                "rule_score": quality.score,
            },
        ]
        return {
            **candidate,
            **revised.model_dump(),
            "question_sha256": question_hash,
            "rule_score": quality.score,
            "risk_flags": list(quality.flags),
            "review_status": "needs_review" if quality.requires_review else "approved",
            "revision_count": int(candidate.get("revision_count", 0)) + 1,
            "revision_history": history,
        }

    async def revise_triple_candidate(self, candidate: dict[str, Any], chunk: DocumentChunk) -> dict[str, Any]:
        before_flags = list(candidate.get("risk_flags", []))
        prompt = json.dumps(
            {
                "heading_path": chunk.heading_path,
                "quality_risks": before_flags,
                "candidate": {
                    key: candidate.get(key)
                    for key in (
                        "subject_name",
                        "subject_type",
                        "relation",
                        "object_name",
                        "object_type",
                        "evidence",
                        "confidence",
                    )
                },
                "labels": KG_SCHEMA_LABELS,
                "relations": {
                    relation: {"subject_type": pair[0], "object_type": pair[1]}
                    for relation, pair in KG_RELATIONS.items()
                },
                "normalization_context": candidate.get("resolution_metadata", {}),
                "output_schema": {
                    "subject_name": "string",
                    "subject_type": "Disease",
                    "relation": "relation enum",
                    "object_name": "string",
                    "object_type": "label enum",
                    "evidence": "原文连续摘录",
                    "confidence": "0..1",
                },
                "source_content": chunk.content,
            },
            ensure_ascii=False,
        )
        revised = await self.gateway.chat_json(
            model=self.settings.kg_model_id,
            system_prompt=KG_RESOLUTION_SYSTEM_PROMPT,
            user_prompt=prompt,
            response_model=TripleExtraction,
            purpose="kg",
            enable_thinking=False,
            temperature=0.0,
        )
        assert isinstance(revised, TripleExtraction)
        quality, subject_canonical, object_canonical, resolution = validate_triple(revised, chunk, self.glossary)
        key_material = "\x1f".join(
            [subject_canonical, revised.subject_type, revised.relation, object_canonical, revised.object_type]
        )
        history = [
            *list(candidate.get("revision_history", [])),
            {
                "round": int(candidate.get("revision_count", 0)) + 1,
                "risk_before": before_flags,
                "risk_after": list(quality.flags),
                "rule_score": quality.score,
            },
        ]
        return {
            **candidate,
            **revised.model_dump(),
            "subject_canonical_name": subject_canonical,
            "object_canonical_name": object_canonical,
            "triple_key": hashlib.sha256(key_material.encode("utf-8")).hexdigest(),
            "rule_score": quality.score,
            "risk_flags": list(quality.flags),
            "resolution_metadata": resolution,
            "review_status": "needs_review" if quality.requires_review else "approved",
            "revision_count": int(candidate.get("revision_count", 0)) + 1,
            "revision_history": history,
        }

    async def semantic_split(self, chunk: DocumentChunk) -> list[DocumentChunk]:
        if chunk.split_strategy != "semantic_pending" or chunk.token_count <= self.settings.knowledge_chunk_target_tokens:
            return [chunk]
        prompt = json.dumps(
            {
                "target_tokens": self.settings.knowledge_chunk_target_tokens,
                "heading_path": chunk.heading_path,
                "output_schema": {"segments": ["原文连续子串"]},
                "content": chunk.content,
            },
            ensure_ascii=False,
        )
        strategy = "semantic_llm"
        try:
            response = await self.gateway.chat_json(
                model=self.settings.qa_model_id,
                system_prompt=SEMANTIC_SPLIT_SYSTEM_PROMPT,
                user_prompt=prompt,
                response_model=SemanticSegments,
                purpose="qa",
                enable_thinking=False,
                temperature=0.0,
            )
            assert isinstance(response, SemanticSegments)
            pieces = response.segments
            if not self._valid_semantic_segments(chunk.content, pieces):
                raise ValueError("语义切分结果未完整覆盖原文或包含改写")
        except (ModelGatewayError, ValueError):
            pieces = fallback_semantic_split(chunk.content, self.settings.knowledge_chunk_target_tokens)
            strategy = "semantic_fallback"

        refined: list[DocumentChunk] = []
        for index, piece in enumerate(pieces):
            cleaned = piece.strip()
            content_sha = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
            stable_key = hashlib.sha256(f"{chunk.stable_key}\x1f{index}\x1f{content_sha}".encode("utf-8")).hexdigest()
            refined.append(
                chunk.model_copy(
                    update={
                        "stable_key": stable_key,
                        "ordinal": chunk.ordinal + index,
                        "content": cleaned,
                        "content_sha256": content_sha,
                        "token_count": estimate_tokens(cleaned),
                        "split_strategy": strategy,
                        "quality_flags": list(dict.fromkeys([*chunk.quality_flags, strategy])),
                    }
                )
            )
        return refined

    async def expert_review_candidate(self, item_type: str, candidate: dict[str, Any], chunk: DocumentChunk) -> dict[str, Any]:
        prompt = json.dumps(
            {
                "item_type": item_type,
                "candidate": candidate,
                "heading_path": chunk.heading_path,
                "source_content": chunk.content,
                "output_schema": {
                    "approved": "boolean",
                    "score": "0..1",
                    "risk_flags": ["string"],
                    "reason": "string",
                    "corrected_payload": "object|null",
                },
            },
            ensure_ascii=False,
        )
        try:
            assessment = await self.gateway.chat_json(
                model=self.settings.expert_model_id,
                system_prompt=EXPERT_SYSTEM_PROMPT,
                user_prompt=prompt,
                response_model=ExpertAssessment,
                purpose="expert",
                enable_thinking=True,
                temperature=0.0,
            )
            assert isinstance(assessment, ExpertAssessment)
        except ModelGatewayError as exc:
            candidate["risk_flags"] = list(dict.fromkeys([*candidate.get("risk_flags", []), "expert_review_failed"]))
            candidate["review_status"] = "needs_review"
            candidate["expert_review"] = {
                "approved": False,
                "score": 0,
                "reason": str(exc)[:500],
                "agent": self._agent_metadata(candidate),
            }
            return candidate

        candidate["expert_score"] = assessment.score
        candidate["expert_review"] = {**assessment.model_dump(), "agent": self._agent_metadata(candidate)}
        candidate["risk_flags"] = list(dict.fromkeys([*candidate.get("risk_flags", []), *assessment.risk_flags]))
        if assessment.corrected_payload:
            candidate["expert_correction"] = assessment.corrected_payload
        candidate["review_status"] = (
            "approved"
            if assessment.approved and assessment.score >= self.settings.knowledge_auto_publish_score and not assessment.risk_flags
            else "needs_review"
        )
        return candidate

    @staticmethod
    def _agent_metadata(candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "revision_count": int(candidate.get("revision_count", 0)),
            "revision_history": list(candidate.get("revision_history", [])),
            "expert_trigger_flags": list(candidate.get("risk_flags", [])),
        }

    @staticmethod
    def _valid_semantic_segments(original: str, segments: list[str]) -> bool:
        if len(segments) < 2:
            return False
        compact_original = re.sub(r"\s+", "", original)
        compact_joined = "".join(re.sub(r"\s+", "", segment) for segment in segments)
        if compact_joined != compact_original:
            return False
        return all(segment.strip() and segment.strip() in original for segment in segments)

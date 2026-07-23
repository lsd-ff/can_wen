from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BackgroundJob,
    KnowledgeBuildEvent,
    KnowledgeBuildRun,
    KnowledgeChunk,
    KnowledgeQAItem,
    KnowledgeReviewItem,
    KnowledgeSource,
    KnowledgeSourceVersion,
    KnowledgeTriple,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class KnowledgeRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def event(
        self,
        run_id: UUID,
        node: str,
        message: str,
        *,
        level: str = "info",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            KnowledgeBuildEvent(
                build_run_id=run_id,
                node=node,
                level=level,
                message=message,
                payload=payload or {},
            )
        )

    def set_progress(self, run_id: UUID, node: str, progress: int, message: str) -> KnowledgeBuildRun:
        run = self.require_run(run_id)
        if run.status == "cancelled":
            raise BuildCancelled("构建任务已取消")
        now = utcnow()
        run.status = "running"
        run.current_node = node
        run.progress = max(run.progress, min(99, progress))
        run.updated_at = now
        run.started_at = run.started_at or now
        if run.job_id:
            job = self.db.get(BackgroundJob, run.job_id)
            if job and job.status != "cancelled":
                job.status = "running"
                job.progress = run.progress
                job.started_at = job.started_at or now
                job.updated_at = now
        self.event(run_id, node, message)
        self.db.commit()
        return run

    def persist_chunks(self, run_id: UUID, chunks: list[dict[str, Any]]) -> dict[str, UUID]:
        run = self.require_run(run_id)
        existing = {
            item.stable_key: item
            for item in self.db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.build_run_id == run_id)).all()
        }
        mapping: dict[str, UUID] = {}
        for data in chunks:
            item = existing.get(str(data["stable_key"]))
            if item is None:
                item = KnowledgeChunk(
                    source_version_id=run.source_version_id,
                    build_run_id=run_id,
                    stable_key=str(data["stable_key"]),
                    ordinal=int(data["ordinal"]),
                    start_line=data.get("start_line"),
                    end_line=data.get("end_line"),
                    heading_path=list(data.get("heading_path", [])),
                    heading_level=data.get("heading_level"),
                    content=str(data["content"]),
                    content_sha256=str(data["content_sha256"]),
                    token_count=int(data["token_count"]),
                    quality_score=float(data["quality_score"]),
                    quality_flags=list(data.get("quality_flags", [])),
                    split_strategy=str(data["split_strategy"]),
                )
                self.db.add(item)
                self.db.flush()
                existing[item.stable_key] = item
            mapping[item.stable_key] = item.id
        version = self.db.get(KnowledgeSourceVersion, run.source_version_id)
        if version:
            version.chunk_count = len(mapping)
            version.heading_count = len({tuple(data.get("heading_path", [])) for data in chunks})
            version.status = "parsed"
            version.updated_at = utcnow()
        self.db.commit()
        return mapping

    def persist_qa(
        self,
        run_id: UUID,
        candidates: list[dict[str, Any]],
        failures: list[dict[str, Any]],
    ) -> int:
        chunks = self._chunks_by_key(run_id)
        existing = {
            item.question_sha256: item
            for item in self.db.scalars(select(KnowledgeQAItem).where(KnowledgeQAItem.build_run_id == run_id)).all()
        }
        for data in candidates:
            chunk = chunks[str(data["_chunk_key"])]
            question_hash = str(data["question_sha256"])
            item = existing.get(question_hash)
            if item is None:
                item = KnowledgeQAItem(
                    build_run_id=run_id,
                    chunk_id=chunk.id,
                    question=str(data["question"]),
                    question_sha256=question_hash,
                    answer=str(data["answer"]),
                    evidence_text=str(data["evidence"]),
                    keywords=list(data.get("keywords", [])),
                    knowledge_types=list(data.get("knowledge_types", [])),
                    extraction_confidence=float(data.get("confidence", 0)),
                    rule_score=float(data.get("rule_score", 0)),
                    expert_score=data.get("expert_score"),
                    expert_assessment=dict(data.get("expert_review", {})),
                    risk_flags=list(data.get("risk_flags", [])),
                    review_status=str(data.get("review_status", "needs_review")),
                )
                self.db.add(item)
                self.db.flush()
                existing[question_hash] = item
            elif item.review_status not in {"approved", "rejected", "published"}:
                item.question = str(data["question"])
                item.answer = str(data["answer"])
                item.evidence_text = str(data["evidence"])
                item.keywords = list(data.get("keywords", []))
                item.knowledge_types = list(data.get("knowledge_types", []))
                item.extraction_confidence = float(data.get("confidence", 0))
                item.rule_score = float(data.get("rule_score", 0))
                item.expert_score = data.get("expert_score")
                item.expert_assessment = dict(data.get("expert_review", {}))
                item.risk_flags = list(data.get("risk_flags", []))
                item.review_status = str(data.get("review_status", "needs_review"))
                item.updated_at = utcnow()
            if item.review_status == "needs_review":
                self._ensure_review_item(
                    run_id,
                    "qa",
                    item.id,
                    item.risk_flags or ["quality_gate"],
                    item.expert_assessment,
                )

        self._queue_chunk_failures(run_id, chunks, failures, "qa")
        self.db.commit()
        return len(existing)

    def persist_triples(
        self,
        run_id: UUID,
        candidates: list[dict[str, Any]],
        failures: list[dict[str, Any]],
    ) -> int:
        chunks = self._chunks_by_key(run_id)
        existing = {
            item.triple_key: item
            for item in self.db.scalars(select(KnowledgeTriple).where(KnowledgeTriple.build_run_id == run_id)).all()
        }
        for data in candidates:
            chunk = chunks[str(data["_chunk_key"])]
            triple_key = str(data["triple_key"])
            item = existing.get(triple_key)
            if item is None:
                item = KnowledgeTriple(
                    build_run_id=run_id,
                    chunk_id=chunk.id,
                    triple_key=triple_key,
                    subject_name=str(data["subject_name"]),
                    subject_type=str(data["subject_type"]),
                    subject_canonical_name=str(data["subject_canonical_name"]),
                    relation=str(data["relation"]),
                    object_name=str(data["object_name"]),
                    object_type=str(data["object_type"]),
                    object_canonical_name=str(data["object_canonical_name"]),
                    evidence_text=str(data["evidence"]),
                    extraction_confidence=float(data.get("confidence", 0)),
                    rule_score=float(data.get("rule_score", 0)),
                    expert_score=data.get("expert_score"),
                    expert_assessment=dict(data.get("expert_review", {})),
                    risk_flags=list(data.get("risk_flags", [])),
                    resolution_metadata=dict(data.get("resolution_metadata", {})),
                    review_status=str(data.get("review_status", "needs_review")),
                )
                self.db.add(item)
                self.db.flush()
                existing[triple_key] = item
            elif item.review_status not in {"approved", "rejected", "published"}:
                item.evidence_text = str(data["evidence"])
                item.extraction_confidence = float(data.get("confidence", 0))
                item.rule_score = float(data.get("rule_score", 0))
                item.expert_score = data.get("expert_score")
                item.expert_assessment = dict(data.get("expert_review", {}))
                item.risk_flags = list(data.get("risk_flags", []))
                item.resolution_metadata = dict(data.get("resolution_metadata", {}))
                item.review_status = str(data.get("review_status", "needs_review"))
                item.updated_at = utcnow()
            if item.review_status == "needs_review":
                priority = "high" if any(flag.startswith("ambiguous") or flag == "relation_type_mismatch" for flag in item.risk_flags) else "medium"
                self._ensure_review_item(
                    run_id,
                    "triple",
                    item.id,
                    item.risk_flags or ["quality_gate"],
                    item.expert_assessment,
                    priority=priority,
                )

        self._queue_chunk_failures(run_id, chunks, failures, "kg")
        self.db.commit()
        return len(existing)

    def finish_extraction(self, run_id: UUID) -> dict[str, int]:
        run = self.require_run(run_id)
        qa_count = int(self.db.scalar(select(func.count()).select_from(KnowledgeQAItem).where(KnowledgeQAItem.build_run_id == run_id)) or 0)
        triple_count = int(self.db.scalar(select(func.count()).select_from(KnowledgeTriple).where(KnowledgeTriple.build_run_id == run_id)) or 0)
        review_count = int(
            self.db.scalar(
                select(func.count()).select_from(KnowledgeReviewItem).where(
                    KnowledgeReviewItem.build_run_id == run_id,
                    KnowledgeReviewItem.status.in_(["open", "claimed"]),
                )
            )
            or 0
        )
        targets = set(run.targets)
        if "rag" in targets and qa_count == 0:
            raise RuntimeError("RAG 构建未生成任何 QA 数据")
        if "kg" in targets and triple_count == 0:
            raise RuntimeError("KG 构建未生成任何三元组")

        now = utcnow()
        run.status = "awaiting_review" if review_count else "succeeded"
        run.current_node = "awaiting_review" if review_count else "ready_to_publish"
        run.progress = 100
        run.completed_at = now
        run.updated_at = now
        run.metrics = {**run.metrics, "qa_count": qa_count, "triple_count": triple_count, "review_count": review_count}
        if run.job_id:
            job = self.db.get(BackgroundJob, run.job_id)
            if job and job.status != "cancelled":
                job.status = "succeeded"
                job.progress = 100
                job.result = {"build_run_id": str(run.id), "build_status": run.status, **run.metrics}
                job.completed_at = now
                job.updated_at = now
        version = self.db.get(KnowledgeSourceVersion, run.source_version_id)
        if version:
            source = self.db.get(KnowledgeSource, version.source_id)
            if source:
                source.status = "processing" if review_count else "ready"
                source.updated_at = now
        self.event(
            run_id,
            run.current_node or "finished",
            f"抽取完成：QA {qa_count} 条，三元组 {triple_count} 条，待人工审核 {review_count} 条",
            payload=run.metrics,
        )
        self.db.commit()
        return {"qa_count": qa_count, "triple_count": triple_count, "review_count": review_count}

    def fail_run(self, run_id: UUID, error: Exception) -> None:
        run = self.db.get(KnowledgeBuildRun, run_id)
        if run is None or run.status == "cancelled":
            return
        now = utcnow()
        message = str(error)[:2000]
        run.status = "failed"
        run.error_message = message
        run.updated_at = now
        run.completed_at = now
        if run.job_id:
            job = self.db.get(BackgroundJob, run.job_id)
            if job:
                job.status = "failed"
                job.error_message = message
                job.updated_at = now
                job.completed_at = now
        version = self.db.get(KnowledgeSourceVersion, run.source_version_id)
        if version:
            source = self.db.get(KnowledgeSource, version.source_id)
            if source:
                source.status = "failed"
                source.updated_at = now
        self.event(run_id, run.current_node or "workflow", message, level="error")
        self.db.commit()

    def require_run(self, run_id: UUID) -> KnowledgeBuildRun:
        run = self.db.get(KnowledgeBuildRun, run_id)
        if run is None:
            raise LookupError("知识构建任务不存在")
        return run

    def _chunks_by_key(self, run_id: UUID) -> dict[str, KnowledgeChunk]:
        return {
            item.stable_key: item
            for item in self.db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.build_run_id == run_id)).all()
        }

    def _ensure_review_item(
        self,
        run_id: UUID,
        item_type: str,
        resource_id: UUID,
        reason_codes: Iterable[str],
        assessment: dict[str, Any] | None = None,
        *,
        priority: str = "medium",
    ) -> None:
        existing = self.db.scalar(
            select(KnowledgeReviewItem).where(
                KnowledgeReviewItem.build_run_id == run_id,
                KnowledgeReviewItem.item_type == item_type,
                KnowledgeReviewItem.resource_id == resource_id,
                KnowledgeReviewItem.status.in_(["open", "claimed"]),
            )
        )
        if existing is None:
            self.db.add(
                KnowledgeReviewItem(
                    build_run_id=run_id,
                    item_type=item_type,
                    resource_id=resource_id,
                    priority=priority,
                    reason_codes=list(dict.fromkeys(reason_codes)),
                    model_assessment=assessment or {},
                )
            )

    def _queue_chunk_failures(
        self,
        run_id: UUID,
        chunks: dict[str, KnowledgeChunk],
        failures: list[dict[str, Any]],
        branch: str,
    ) -> None:
        for failure in failures:
            chunk = chunks.get(str(failure.get("chunk_key", "")))
            if chunk is None:
                continue
            self._ensure_review_item(
                run_id,
                "chunk",
                chunk.id,
                [f"{branch}_extraction_failed"],
                {"error": str(failure.get("error", "unknown"))[:500]},
                priority="high",
            )


class BuildCancelled(RuntimeError):
    pass

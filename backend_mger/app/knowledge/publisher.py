from __future__ import annotations

import asyncio
import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.knowledge.indexes import Neo4jKnowledgeGraph, OpenSearchQAIndex, QdrantQAIndex
from app.knowledge.model_gateway import ModelGateway
from app.knowledge.repository import KnowledgeRepository, utcnow
from app.models import (
    BackgroundJob,
    KnowledgeBuildRun,
    KnowledgeChunk,
    KnowledgePublication,
    KnowledgeQAItem,
    KnowledgeSource,
    KnowledgeSourceVersion,
    KnowledgeSyncOutbox,
    KnowledgeTriple,
)


class KnowledgePublisher:
    def __init__(
        self,
        settings: Settings | None = None,
        gateway: ModelGateway | None = None,
        qdrant: QdrantQAIndex | None = None,
        opensearch: OpenSearchQAIndex | None = None,
        neo4j: Neo4jKnowledgeGraph | None = None,
        session_factory=SessionLocal,
    ) -> None:
        self.settings = settings or get_settings()
        self.gateway = gateway or ModelGateway.from_database(self.settings, session_factory)
        self.qdrant = qdrant or QdrantQAIndex(self.settings)
        self.opensearch = opensearch or OpenSearchQAIndex(self.settings)
        self.neo4j = neo4j or Neo4jKnowledgeGraph(self.settings)
        self.session_factory = session_factory

    def publish(self, publication_id: UUID, job_id: UUID) -> dict[str, int]:
        try:
            self._assert_not_cancelled(job_id)
            counts = self._prepare_outbox(publication_id, job_id)
            self._assert_not_cancelled(job_id)
            self._process_qdrant(publication_id)
            self._assert_not_cancelled(job_id)
            self._process_opensearch(publication_id)
            self._assert_not_cancelled(job_id)
            self._process_neo4j(publication_id)
            self._assert_not_cancelled(job_id)
            self._finish(publication_id, job_id, counts)
            return counts
        except Exception as exc:
            self._fail(publication_id, job_id, exc)
            raise

    def _prepare_outbox(self, publication_id: UUID, job_id: UUID) -> dict[str, int]:
        with self.session_factory() as db:
            publication = db.get(KnowledgePublication, publication_id)
            job = db.get(BackgroundJob, job_id)
            if publication is None or job is None:
                raise LookupError("发布记录或后台任务不存在")
            if publication.status == "published":
                return {key: int(value) for key, value in publication.counts.items()}
            run = db.get(KnowledgeBuildRun, publication.build_run_id)
            if run is None:
                raise LookupError("知识构建任务不存在")
            job.status = "running"
            job.progress = 5
            job.started_at = job.started_at or utcnow()
            job.updated_at = utcnow()
            publication.status = "staging"
            publication.error_message = None
            publication.updated_at = utcnow()
            KnowledgeRepository(db).event(run.id, "publish_prepare", "正在生成跨存储幂等发布事件")

            qa_rows = db.execute(
                select(KnowledgeQAItem, KnowledgeChunk, KnowledgeSourceVersion, KnowledgeSource)
                .join(KnowledgeChunk, KnowledgeChunk.id == KnowledgeQAItem.chunk_id)
                .join(KnowledgeSourceVersion, KnowledgeSourceVersion.id == KnowledgeChunk.source_version_id)
                .join(KnowledgeSource, KnowledgeSource.id == KnowledgeSourceVersion.source_id)
                .where(KnowledgeQAItem.build_run_id == run.id, KnowledgeQAItem.review_status == "approved")
            ).all()
            triple_rows = db.execute(
                select(KnowledgeTriple, KnowledgeChunk, KnowledgeSourceVersion, KnowledgeSource)
                .join(KnowledgeChunk, KnowledgeChunk.id == KnowledgeTriple.chunk_id)
                .join(KnowledgeSourceVersion, KnowledgeSourceVersion.id == KnowledgeChunk.source_version_id)
                .join(KnowledgeSource, KnowledgeSource.id == KnowledgeSourceVersion.source_id)
                .where(KnowledgeTriple.build_run_id == run.id, KnowledgeTriple.review_status == "approved")
            ).all()
            now_iso = utcnow().isoformat()
            for qa, chunk, version, source in qa_rows:
                payload = {
                    "question": qa.question,
                    "answer": qa.answer,
                    "evidence": qa.evidence_text,
                    "keywords": qa.keywords,
                    "knowledge_types": qa.knowledge_types,
                    "source_id": str(source.id),
                    "source_title": source.title,
                    "source_version_id": str(version.id),
                    "source_version": version.version,
                    "chunk_id": str(chunk.id),
                    "heading_path": chunk.heading_path,
                    "publication_id": str(publication.id),
                    "published_at": now_iso,
                }
                self._ensure_event(db, run.id, publication.id, "qdrant", "qa", qa.id, payload)
                self._ensure_event(db, run.id, publication.id, "opensearch", "qa", qa.id, payload)
            for triple, chunk, version, source in triple_rows:
                evidence_sha = hashlib.sha256(triple.evidence_text.encode("utf-8")).hexdigest()
                payload = {
                    "subject_name": triple.subject_name,
                    "subject_type": triple.subject_type,
                    "subject_canonical_name": triple.subject_canonical_name,
                    "relation": triple.relation,
                    "object_name": triple.object_name,
                    "object_type": triple.object_type,
                    "object_canonical_name": triple.object_canonical_name,
                    "evidence": triple.evidence_text,
                    "evidence_sha256": evidence_sha,
                    "source_id": str(source.id),
                    "source_title": source.title,
                    "source_version_id": str(version.id),
                    "source_version": version.version,
                    "chunk_id": str(chunk.id),
                    "publication_id": str(publication.id),
                    "provenance": {
                        "source_id": str(source.id),
                        "source_title": source.title,
                        "source_version_id": str(version.id),
                        "source_version": version.version,
                        "chunk_id": str(chunk.id),
                        "heading_path": chunk.heading_path,
                    },
                }
                self._ensure_event(db, run.id, publication.id, "neo4j", "triple", triple.id, payload)

            counts = {"qa": len(qa_rows), "triples": len(triple_rows)}
            publication.counts = counts
            publication.qdrant_collection = self.settings.qdrant_collection if qa_rows else None
            publication.opensearch_index = self.settings.opensearch_index if qa_rows else None
            publication.neo4j_database = self.settings.neo4j_database if triple_rows else None
            db.commit()
            return counts

    def _process_qdrant(self, publication_id: UUID) -> None:
        events = self._pending_events(publication_id, "qdrant")
        if not events:
            return
        self.qdrant.ensure_collection()
        for offset in range(0, len(events), 10):
            batch = events[offset : offset + 10]
            try:
                vectors = asyncio.run(self.gateway.embed([str(event.payload["question"]) for event in batch]))
                for event, vector in zip(batch, vectors, strict=True):
                    self.qdrant.upsert(str(event.aggregate_id), vector, event.payload)
                    self._mark_event_success(event.id)
            except Exception as exc:
                for event in batch:
                    self._mark_event_failure(event.id, exc)
                raise

    def _process_opensearch(self, publication_id: UUID) -> None:
        events = self._pending_events(publication_id, "opensearch")
        if not events:
            return
        self.opensearch.ensure_index()
        for event in events:
            try:
                self.opensearch.upsert(str(event.aggregate_id), event.payload)
                self._mark_event_success(event.id)
            except Exception as exc:
                self._mark_event_failure(event.id, exc)
                raise
        self.opensearch.refresh()

    def _process_neo4j(self, publication_id: UUID) -> None:
        events = self._pending_events(publication_id, "neo4j")
        if not events:
            return
        self.neo4j.ensure_schema()
        for event in events:
            try:
                self.neo4j.upsert_triple(event.payload)
                self._mark_event_success(event.id)
            except Exception as exc:
                self._mark_event_failure(event.id, exc)
                raise

    def _finish(self, publication_id: UUID, job_id: UUID, counts: dict[str, int]) -> None:
        with self.session_factory() as db:
            publication = db.get(KnowledgePublication, publication_id)
            job = db.get(BackgroundJob, job_id)
            if publication is None or job is None:
                raise LookupError("发布记录或后台任务不存在")
            run = db.get(KnowledgeBuildRun, publication.build_run_id)
            if run is None:
                raise LookupError("知识构建任务不存在")
            now = utcnow()
            for qa in db.scalars(
                select(KnowledgeQAItem).where(
                    KnowledgeQAItem.build_run_id == run.id,
                    KnowledgeQAItem.review_status == "approved",
                )
            ):
                qa.review_status = "published"
                qa.qdrant_point_id = str(qa.id)
                qa.opensearch_document_id = str(qa.id)
                qa.published_at = now
                qa.updated_at = now
            for triple in db.scalars(
                select(KnowledgeTriple).where(
                    KnowledgeTriple.build_run_id == run.id,
                    KnowledgeTriple.review_status == "approved",
                )
            ):
                triple.review_status = "published"
                triple.neo4j_synced_at = now
                triple.published_at = now
                triple.updated_at = now
            publication.status = "published"
            publication.counts = counts
            publication.published_at = now
            publication.updated_at = now
            run.status = "succeeded"
            run.current_node = "published"
            run.progress = 100
            run.updated_at = now
            version = db.get(KnowledgeSourceVersion, run.source_version_id)
            if version:
                source = db.get(KnowledgeSource, version.source_id)
                if source:
                    source.status = "ready"
                    source.published_version_id = version.id
                    source.updated_at = now
            job.status = "succeeded"
            job.progress = 100
            job.result = {"publication_id": str(publication.id), **counts}
            job.completed_at = now
            job.updated_at = now
            KnowledgeRepository(db).event(run.id, "published", f"发布完成：QA {counts['qa']} 条，三元组 {counts['triples']} 条")
            db.commit()

    def _fail(self, publication_id: UUID, job_id: UUID, error: Exception) -> None:
        with self.session_factory() as db:
            publication = db.get(KnowledgePublication, publication_id)
            job = db.get(BackgroundJob, job_id)
            message = f"{error.__class__.__name__}: {str(error)[:1500]}"
            now = utcnow()
            if publication:
                run = db.get(KnowledgeBuildRun, publication.build_run_id)
                cancelled = bool(job and job.status == "cancelled") or bool(run and run.status == "cancelled")
                publication.status = "rolled_back" if cancelled else "failed"
                publication.error_message = message
                publication.updated_at = now
                if run and not cancelled:
                    run.status = "failed"
                    run.current_node = "publish"
                    run.error_message = message
                    run.updated_at = now
                    KnowledgeRepository(db).event(run.id, "publish", message, level="error")
            if job and job.status != "cancelled":
                job.status = "failed"
                job.error_message = message
                job.completed_at = now
                job.updated_at = now
            db.commit()

    @staticmethod
    def _ensure_event(
        db,
        run_id: UUID,
        publication_id: UUID,
        target: str,
        aggregate_type: str,
        aggregate_id: UUID,
        payload: dict[str, Any],
    ) -> None:
        event_key = f"{publication_id}:{target}:{aggregate_type}:{aggregate_id}:upsert"
        existing = db.scalar(select(KnowledgeSyncOutbox).where(KnowledgeSyncOutbox.event_key == event_key))
        if existing is None:
            db.add(
                KnowledgeSyncOutbox(
                    build_run_id=run_id,
                    event_key=event_key,
                    target=target,
                    operation="upsert",
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    payload=payload,
                )
            )

    def _pending_events(self, publication_id: UUID, target: str) -> list[KnowledgeSyncOutbox]:
        prefix = f"{publication_id}:{target}:"
        with self.session_factory() as db:
            events = db.scalars(
                select(KnowledgeSyncOutbox)
                .where(
                    KnowledgeSyncOutbox.event_key.startswith(prefix),
                    KnowledgeSyncOutbox.status.in_(["pending", "failed", "processing"]),
                )
                .order_by(KnowledgeSyncOutbox.created_at)
            ).all()
            for event in events:
                event.status = "processing"
                event.attempts += 1
                event.error_message = None
                event.updated_at = utcnow()
            db.commit()
            for event in events:
                db.expunge(event)
            return events

    def _mark_event_success(self, event_id: UUID) -> None:
        with self.session_factory() as db:
            event = db.get(KnowledgeSyncOutbox, event_id)
            if event:
                event.status = "succeeded"
                event.processed_at = utcnow()
                event.updated_at = utcnow()
                db.commit()

    def _mark_event_failure(self, event_id: UUID, error: Exception) -> None:
        with self.session_factory() as db:
            event = db.get(KnowledgeSyncOutbox, event_id)
            if event:
                event.status = "failed"
                event.error_message = f"{error.__class__.__name__}: {str(error)[:1000]}"
                event.updated_at = utcnow()
                db.commit()

    def _assert_not_cancelled(self, job_id: UUID) -> None:
        with self.session_factory() as db:
            job = db.get(BackgroundJob, job_id)
            if job is None:
                raise LookupError("发布后台任务不存在")
            if job.status == "cancelled":
                raise RuntimeError("发布任务已取消")

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.knowledge.indexes import Neo4jKnowledgeGraph, OpenSearchQAIndex, QdrantQAIndex
from app.knowledge.storage import KnowledgeStorage
from app.models import (
    BackgroundJob,
    KnowledgeBuildRun,
    KnowledgeChunk,
    KnowledgePublication,
    KnowledgeQAItem,
    KnowledgeReviewItem,
    KnowledgeSource,
    KnowledgeSourceVersion,
    KnowledgeSyncOutbox,
    KnowledgeTriple,
)


class KnowledgeSourceDeletionService:
    """Delete a source and every internal/external artifact derived from it."""

    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        *,
        storage: KnowledgeStorage | None = None,
        qdrant: QdrantQAIndex | None = None,
        opensearch: OpenSearchQAIndex | None = None,
        neo4j: Neo4jKnowledgeGraph | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.storage = storage or KnowledgeStorage(self.settings)
        self.qdrant = qdrant
        self.opensearch = opensearch
        self.neo4j = neo4j

    def delete(self, source: KnowledgeSource) -> dict[str, Any]:
        versions = self.db.scalars(
            select(KnowledgeSourceVersion).where(KnowledgeSourceVersion.source_id == source.id)
        ).all()
        version_ids = [version.id for version in versions]
        runs = (
            self.db.scalars(
                select(KnowledgeBuildRun).where(KnowledgeBuildRun.source_version_id.in_(version_ids))
            ).all()
            if version_ids
            else []
        )
        in_flight = [run for run in runs if run.status in {"queued", "running", "publishing"}]
        if in_flight:
            raise ValueError("该文档仍有正在执行的构建或发布任务，请先取消任务后再删除")

        run_ids = [run.id for run in runs]
        chunks = (
            self.db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.build_run_id.in_(run_ids))).all()
            if run_ids
            else []
        )
        qa_rows = (
            self.db.scalars(select(KnowledgeQAItem).where(KnowledgeQAItem.build_run_id.in_(run_ids))).all()
            if run_ids
            else []
        )
        triples = (
            self.db.scalars(select(KnowledgeTriple).where(KnowledgeTriple.build_run_id.in_(run_ids))).all()
            if run_ids
            else []
        )
        reviews = (
            self.db.scalars(select(KnowledgeReviewItem).where(KnowledgeReviewItem.build_run_id.in_(run_ids))).all()
            if run_ids
            else []
        )
        publications = (
            self.db.scalars(select(KnowledgePublication).where(KnowledgePublication.build_run_id.in_(run_ids))).all()
            if run_ids
            else []
        )
        outbox = (
            self.db.scalars(select(KnowledgeSyncOutbox).where(KnowledgeSyncOutbox.build_run_id.in_(run_ids))).all()
            if run_ids
            else []
        )
        related_jobs = self._related_jobs(source, version_ids, run_ids, publications)

        qdrant_ids = {
            str(qa.qdrant_point_id)
            for qa in qa_rows
            if qa.qdrant_point_id
        }
        opensearch_ids = {
            str(qa.opensearch_document_id)
            for qa in qa_rows
            if qa.opensearch_document_id
        }
        for event in outbox:
            if event.aggregate_type != "qa":
                continue
            if event.target == "qdrant":
                qdrant_ids.add(str(event.aggregate_id))
            elif event.target == "opensearch":
                opensearch_ids.add(str(event.aggregate_id))

        publication_ids = [str(publication.id) for publication in publications]
        has_neo4j_artifacts = any(
            triple.neo4j_synced_at is not None or triple.review_status == "published"
            for triple in triples
        ) or any(event.target == "neo4j" for event in outbox)
        neo4j_counts = {"relationships_deleted": 0, "relationships_updated": 0, "nodes_deleted": 0}

        if qdrant_ids:
            (self.qdrant or QdrantQAIndex(self.settings)).delete(sorted(qdrant_ids))
        if opensearch_ids:
            (self.opensearch or OpenSearchQAIndex(self.settings)).delete_many(sorted(opensearch_ids))
        if has_neo4j_artifacts:
            neo4j_counts = (self.neo4j or Neo4jKnowledgeGraph(self.settings)).delete_source_artifacts(
                [str(version_id) for version_id in version_ids],
                publication_ids,
            )

        storage_uris = self._storage_uris(source, versions)
        for uri in storage_uris:
            self.storage.delete(uri)

        for job in related_jobs:
            self.db.delete(job)
        self.db.delete(source)
        self.db.flush()
        return {
            "source_id": str(source.id),
            "title": source.title,
            "deleted": {
                "versions": len(versions),
                "builds": len(runs),
                "chunks": len(chunks),
                "qa_items": len(qa_rows),
                "triples": len(triples),
                "reviews": len(reviews),
                "publications": len(publications),
                "background_jobs": len(related_jobs),
                "stored_files": len(storage_uris),
                "qdrant_points": len(qdrant_ids),
                "opensearch_documents": len(opensearch_ids),
                "neo4j": neo4j_counts,
            },
        }

    def _related_jobs(
        self,
        source: KnowledgeSource,
        version_ids: list,
        run_ids: list,
        publications: list[KnowledgePublication],
    ) -> list[BackgroundJob]:
        version_keys = {str(value) for value in version_ids}
        run_keys = {str(value) for value in run_ids}
        publication_keys = {str(value.id) for value in publications}
        jobs = self.db.scalars(
            select(BackgroundJob).where(BackgroundJob.job_type.in_(["knowledge_build", "knowledge_publish"]))
        ).all()
        related = []
        for job in jobs:
            payload = job.payload if isinstance(job.payload, dict) else {}
            if (
                str(payload.get("knowledge_source_id", "")) == str(source.id)
                or str(payload.get("source_version_id", "")) in version_keys
                or str(payload.get("build_run_id", "")) in run_keys
                or str(payload.get("publication_id", "")) in publication_keys
            ):
                related.append(job)
        return related

    @staticmethod
    def _storage_uris(
        source: KnowledgeSource,
        versions: list[KnowledgeSourceVersion],
    ) -> list[str]:
        values = [source.storage_uri]
        for version in versions:
            values.extend([version.original_storage_uri, version.markdown_storage_uri])
        return list(dict.fromkeys(str(value) for value in values if value))

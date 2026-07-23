"""Run and clean up a real asynchronous RAG/KG build and publication."""

from __future__ import annotations

import json
import tempfile
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from neo4j import GraphDatabase
from redis import Redis
from sqlalchemy import delete, select, text

from app.config import Settings
from app.db import SessionLocal
from app.knowledge.indexes import OpenSearchQAIndex, QdrantQAIndex
from app.knowledge.schema import KG_NEO4J_LABELS, KG_SCHEMA_LABELS
from app.knowledge.service import KnowledgeService
from app.knowledge.storage import KnowledgeStorage
from app.knowledge.tasks import dispatch_background_job
from app.models import (
    BackgroundJob,
    KnowledgeBuildRun,
    KnowledgeChunk,
    KnowledgePublication,
    KnowledgeQAItem,
    KnowledgeReviewItem,
    KnowledgeSource,
    KnowledgeTriple,
)


TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}


def wait_for_job(job_id: UUID, timeout_seconds: int = 900) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with SessionLocal() as db:
            job = db.get(BackgroundJob, job_id)
            if job is None:
                raise LookupError(f"后台任务不存在：{job_id}")
            if job.status in TERMINAL_JOB_STATUSES:
                result = {
                    "status": job.status,
                    "progress": job.progress,
                    "result": dict(job.result),
                    "error": job.error_message,
                }
                if job.status != "succeeded":
                    raise RuntimeError(f"后台任务失败：{result}")
                return result
        time.sleep(2)
    raise TimeoutError(f"后台任务等待超时：{job_id}")


def main() -> None:
    settings = Settings()
    settings.require_neo4j_aura()
    marker = uuid.uuid4().hex[:12]
    title = f"端到端验收文档-{marker}"
    version_label = f"smoke-{marker}"
    disease = f"端到端验收病{marker}"
    pathogen = f"端到端验收病毒{marker}"
    symptom = f"端到端验收症状{marker}"
    measure = f"端到端验收措施{marker}"
    markdown = (
        "# 养蚕知识构建端到端验收\n\n"
        "## 家蚕疾病问答\n\n"
        f"### {disease}\n\n"
        f"{disease}由{pathogen}引起。病蚕会出现{symptom}。"
        f"发现病蚕后应采用{measure}，并及时隔离病蚕。\n"
    )

    source_id: UUID | None = None
    build_run_id: UUID | None = None
    publication_id: UUID | None = None
    job_ids: list[UUID] = []
    qa_ids: list[str] = []
    graph_entities: set[tuple[str, str]] = set()
    storage_uri: str | None = None
    graph_thread_id: str | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="canw-e2e-") as temp_dir:
            source_path = Path(temp_dir) / f"{title}.md"
            source_path.write_text(markdown, encoding="utf-8")
            with SessionLocal() as db:
                service = KnowledgeService(db, settings=settings)
                source, source_version, created = service.import_path(
                    source_path,
                    title=title,
                    version=version_label,
                    license_note="自动化隔离端到端验收，完成后清理",
                    origin="e2e_smoke",
                )
                if not created:
                    raise RuntimeError("端到端验收知识源发生意外重复")
                source_id = source.id
                storage_uri = source_version.original_storage_uri
                run, build_job, build_created = service.queue_build(
                    source.id,
                    targets=["rag", "kg"],
                    requested_by_id=None,
                )
                if not build_created:
                    raise RuntimeError("端到端验收构建任务发生意外重复")
                build_run_id = run.id
                graph_thread_id = run.graph_thread_id
                job_ids.append(build_job.id)

        dispatch_background_job(job_ids[-1])
        build_result = wait_for_job(job_ids[-1])

        with SessionLocal() as db:
            run = db.get(KnowledgeBuildRun, build_run_id)
            if run is None:
                raise LookupError("端到端验收构建记录不存在")
            chunks = db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.build_run_id == run.id)).all()
            qa_items = db.scalars(select(KnowledgeQAItem).where(KnowledgeQAItem.build_run_id == run.id)).all()
            triples = db.scalars(select(KnowledgeTriple).where(KnowledgeTriple.build_run_id == run.id)).all()
            if len(chunks) != 1 or not qa_items or not triples:
                raise RuntimeError(
                    f"端到端抽取结果不完整：chunks={len(chunks)}, qa={len(qa_items)}, triples={len(triples)}"
                )
            chunk_content = chunks[0].content
            if any(item.evidence_text not in chunk_content for item in qa_items):
                raise RuntimeError("存在无法逐字回落到 Chunk 的 QA 证据")
            if any(item.evidence_text not in chunk_content for item in triples):
                raise RuntimeError("存在无法逐字回落到 Chunk 的三元组证据")

            now = datetime.now(UTC)
            for review in db.scalars(
                select(KnowledgeReviewItem).where(
                    KnowledgeReviewItem.build_run_id == run.id,
                    KnowledgeReviewItem.status.in_(["open", "claimed"]),
                )
            ):
                review.status = "approved"
                review.decision_note = "自动化隔离端到端验收通过"
                review.reviewed_at = now
                review.updated_at = now
                review.version += 1
            for item in qa_items:
                if item.review_status not in {"rejected", "published"}:
                    item.review_status = "approved"
                    item.review_note = "自动化隔离端到端验收通过"
                    item.reviewed_at = now
                    item.updated_at = now
            for item in triples:
                if item.review_status not in {"rejected", "published"}:
                    item.review_status = "approved"
                    item.review_note = "自动化隔离端到端验收通过"
                    item.reviewed_at = now
                    item.updated_at = now
                graph_entities.add((item.subject_type, item.subject_canonical_name))
                graph_entities.add((item.object_type, item.object_canonical_name))
            run.status = "succeeded"
            run.current_node = "smoke_review_complete"
            run.updated_at = now
            qa_ids = [str(item.id) for item in qa_items]
            db.commit()

            publication, publish_job, publish_created = KnowledgeService(db, settings=settings).queue_publish(
                run.id,
                requested_by_id=None,
            )
            if not publish_created:
                raise RuntimeError("端到端验收发布任务发生意外重复")
            publication_id = publication.id
            job_ids.append(publish_job.id)

        dispatch_background_job(job_ids[-1])
        publish_result = wait_for_job(job_ids[-1])

        with SessionLocal() as db:
            publication = db.get(KnowledgePublication, publication_id)
            if publication is None or publication.status != "published":
                raise RuntimeError("发布记录未进入 published 状态")
            published_qa = db.scalars(
                select(KnowledgeQAItem).where(KnowledgeQAItem.build_run_id == build_run_id)
            ).all()
            published_triples = db.scalars(
                select(KnowledgeTriple).where(KnowledgeTriple.build_run_id == build_run_id)
            ).all()
            if any(item.review_status != "published" for item in [*published_qa, *published_triples]):
                raise RuntimeError("发布后仍有知识项未进入 published 状态")
            expected_qa = len(published_qa)
            expected_triples = len(published_triples)

        qdrant = QdrantQAIndex(settings)
        qdrant_client = qdrant._client()
        try:
            qdrant_points = qdrant_client.retrieve(
                collection_name=settings.qdrant_collection,
                ids=qa_ids,
                with_payload=True,
            )
        finally:
            qdrant_client.close()
        if len(qdrant_points) != expected_qa:
            raise RuntimeError("Qdrant 发布数量与 PostgreSQL 不一致")

        opensearch = OpenSearchQAIndex(settings)
        opensearch_client = opensearch._client()
        try:
            search_docs = opensearch_client.mget(
                index=settings.opensearch_index,
                body={"ids": qa_ids},
            )["docs"]
        finally:
            opensearch_client.close()
        if sum(bool(item.get("found")) for item in search_docs) != expected_qa:
            raise RuntimeError("OpenSearch 发布数量与 PostgreSQL 不一致")

        with GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        ) as driver:
            record = driver.execute_query(
                "MATCH ()-[r]->() WHERE r.publication_id = $publication_id RETURN count(r) AS count",
                publication_id=str(publication_id),
                database_=settings.neo4j_database,
            ).records[0]
            neo4j_count = int(record["count"])
        if neo4j_count != expected_triples:
            raise RuntimeError("Neo4j 发布数量与 PostgreSQL 不一致")

        print(
            json.dumps(
                {
                    "marker": marker,
                    "build_job": build_result,
                    "publish_job": publish_result,
                    "chunks": 1,
                    "qa": expected_qa,
                    "triples": expected_triples,
                    "qdrant": len(qdrant_points),
                    "opensearch": sum(bool(item.get("found")) for item in search_docs),
                    "neo4j": neo4j_count,
                    "evidence_traceable": True,
                },
                ensure_ascii=False,
            )
        )
    finally:
        _cleanup(
            settings=settings,
            source_id=source_id,
            publication_id=publication_id,
            job_ids=job_ids,
            qa_ids=qa_ids,
            graph_entities=graph_entities,
            storage_uri=storage_uri,
            graph_thread_id=graph_thread_id,
        )


def _cleanup(
    *,
    settings: Settings,
    source_id: UUID | None,
    publication_id: UUID | None,
    job_ids: list[UUID],
    qa_ids: list[str],
    graph_entities: set[tuple[str, str]],
    storage_uri: str | None,
    graph_thread_id: str | None,
) -> None:
    if qa_ids:
        with suppress(Exception):
            QdrantQAIndex(settings).delete(qa_ids)
        with suppress(Exception):
            opensearch = OpenSearchQAIndex(settings)
            for item_id in qa_ids:
                opensearch.delete(item_id)
            opensearch.refresh()

    if publication_id is not None:
        with suppress(Exception):
            with GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            ) as driver:
                driver.execute_query(
                    "MATCH ()-[r]->() WHERE r.publication_id = $publication_id DELETE r",
                    publication_id=str(publication_id),
                    database_=settings.neo4j_database,
                )
                for label, name in graph_entities:
                    if label not in KG_SCHEMA_LABELS:
                        continue
                    physical_label = KG_NEO4J_LABELS[label].replace("`", "``")
                    driver.execute_query(
                        f"MATCH (n:`{physical_label}` {{name: $name}}) "
                        "WHERE coalesce(n.id, '') STARTS WITH 'AUTO_' AND NOT (n)--() DELETE n",
                        name=name,
                        database_=settings.neo4j_database,
                    )
                # Also recover orphaned nodes left by a previously interrupted smoke run.
                driver.execute_query(
                    "MATCH (n) WHERE coalesce(n.id, '') STARTS WITH 'AUTO_' "
                    "AND n.name STARTS WITH '端到端验收' AND NOT (n)--() DELETE n",
                    database_=settings.neo4j_database,
                )

    with SessionLocal() as db:
        if job_ids:
            db.execute(delete(BackgroundJob).where(BackgroundJob.id.in_(job_ids)))
        if source_id is not None:
            db.execute(delete(KnowledgeSource).where(KnowledgeSource.id == source_id))
        if graph_thread_id:
            for table_name in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                db.execute(
                    text(f"DELETE FROM {table_name} WHERE thread_id = :thread_id"),
                    {"thread_id": graph_thread_id},
                )
        db.commit()

    if storage_uri:
        with suppress(Exception):
            KnowledgeStorage(settings).delete(storage_uri)
    if job_ids:
        with suppress(Exception):
            result_backend = Redis.from_url(settings.celery_result_backend)
            result_backend.delete(*(f"celery-task-meta-{job_id}" for job_id in job_ids))
            result_backend.close()


if __name__ == "__main__":
    main()

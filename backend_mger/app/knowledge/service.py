from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.knowledge.repository import utcnow
from app.knowledge.storage import KnowledgeStorage, safe_filename
from app.models import (
    BackgroundJob,
    KnowledgeBuildRun,
    KnowledgePublication,
    KnowledgeQAItem,
    KnowledgeReviewItem,
    KnowledgeSource,
    KnowledgeSourceVersion,
    KnowledgeTriple,
)


SUPPORTED_DOCUMENT_SUFFIXES = {
    ".md",
    ".markdown",
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".jp2",
    ".webp",
    ".gif",
    ".bmp",
}


class KnowledgeService:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        storage: KnowledgeStorage | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.storage = storage or KnowledgeStorage(self.settings)

    def import_path(
        self,
        path: Path,
        *,
        title: str | None = None,
        version: str = "v1",
        license_note: str | None = None,
        created_by_id: UUID | None = None,
        origin: str = "local_seed",
    ) -> tuple[KnowledgeSource, KnowledgeSourceVersion, bool]:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(str(resolved))
        filename = safe_filename(resolved.name)
        self._validate_suffix(filename)
        digest = _sha256_path(resolved)
        source, existing_version = self._find_existing(title or resolved.stem, version, digest)
        if existing_version:
            return source, existing_version, False
        source = source or self._new_source(title or resolved.stem, version, created_by_id)
        self.db.add(source)
        self.db.flush()
        object_key = self._object_key(source.id, version, filename)
        stored = self.storage.put_path(object_key, resolved)
        source_version = self._attach_version(
            source,
            version=version,
            filename=filename,
            content_sha256=stored.sha256,
            storage_uri=stored.uri,
            content_type=stored.content_type,
            size=stored.size,
            license_note=license_note,
            created_by_id=created_by_id,
            origin=origin,
        )
        self.db.commit()
        return source, source_version, True

    def import_stream(
        self,
        stream: BinaryIO,
        *,
        filename: str,
        title: str,
        version: str,
        content_type: str | None,
        license_note: str | None,
        created_by_id: UUID | None,
    ) -> tuple[KnowledgeSource, KnowledgeSourceVersion]:
        filename = safe_filename(filename)
        self._validate_suffix(filename)
        source = self.db.scalar(select(KnowledgeSource).where(KnowledgeSource.title == title.strip()))
        if source is not None:
            duplicate_version = self.db.scalar(
                select(KnowledgeSourceVersion).where(
                    KnowledgeSourceVersion.source_id == source.id,
                    KnowledgeSourceVersion.version == version.strip(),
                )
            )
            if duplicate_version:
                raise ValueError("该知识源版本已存在")
        source = source or self._new_source(title, version, created_by_id)
        self.db.add(source)
        self.db.flush()
        stored = self.storage.put_stream(
            self._object_key(source.id, version, filename),
            stream,
            content_type=content_type,
        )
        source_version = self._attach_version(
            source,
            version=version,
            filename=filename,
            content_sha256=stored.sha256,
            storage_uri=stored.uri,
            content_type=stored.content_type,
            size=stored.size,
            license_note=license_note,
            created_by_id=created_by_id,
            origin="admin_upload",
        )
        self.db.commit()
        return source, source_version

    def queue_build(
        self,
        source_id: UUID,
        *,
        targets: list[str],
        requested_by_id: UUID | None,
    ) -> tuple[KnowledgeBuildRun, BackgroundJob, bool]:
        normalized_targets = sorted(set(targets))
        if not normalized_targets or set(normalized_targets) - {"rag", "kg"}:
            raise ValueError("构建目标只能是 rag、kg 或两者")
        source = self.db.get(KnowledgeSource, source_id)
        if source is None:
            raise LookupError("知识源不存在")
        if source.status == "disabled":
            raise ValueError("已停用的知识源不能构建")
        version = self.db.scalar(
            select(KnowledgeSourceVersion)
            .where(KnowledgeSourceVersion.source_id == source_id, KnowledgeSourceVersion.status != "disabled")
            .order_by(KnowledgeSourceVersion.created_at.desc())
        )
        if version is None:
            raise ValueError("知识源没有可构建版本")
        active_runs = self.db.scalars(
            select(KnowledgeBuildRun).where(
                KnowledgeBuildRun.source_version_id == version.id,
                KnowledgeBuildRun.status.in_(["queued", "running", "awaiting_review", "publishing"]),
            )
        ).all()
        for active in active_runs:
            if sorted(active.targets) == normalized_targets:
                job = self.db.get(BackgroundJob, active.job_id) if active.job_id else None
                if job:
                    return active, job, False

        run_id = uuid.uuid4()
        job_id = uuid.uuid4()
        job = BackgroundJob(
            id=job_id,
            job_type="knowledge_build",
            status="queued",
            payload={
                "knowledge_source_id": str(source.id),
                "source_version_id": str(version.id),
                "build_run_id": str(run_id),
                "targets": normalized_targets,
            },
            requested_by_id=requested_by_id,
        )
        run = KnowledgeBuildRun(
            id=run_id,
            source_version_id=version.id,
            job_id=job_id,
            targets=normalized_targets,
            graph_thread_id=f"knowledge-build-{run_id}",
            config_snapshot=self._config_snapshot(),
            requested_by_id=requested_by_id,
        )
        source.status = "processing"
        source.updated_at = utcnow()
        self.db.add_all([job, run])
        self.db.commit()
        return run, job, True

    def queue_publish(
        self,
        run_id: UUID,
        *,
        requested_by_id: UUID | None,
    ) -> tuple[KnowledgePublication, BackgroundJob, bool]:
        run = self.db.get(KnowledgeBuildRun, run_id)
        if run is None:
            raise LookupError("知识构建任务不存在")
        if run.status != "succeeded":
            raise ValueError("知识构建尚未完成或仍有数据待审核")
        open_reviews = int(
            self.db.scalar(
                select(func.count()).select_from(KnowledgeReviewItem).where(
                    KnowledgeReviewItem.build_run_id == run_id,
                    KnowledgeReviewItem.status.in_(["open", "claimed"]),
                )
            )
            or 0
        )
        if open_reviews:
            raise ValueError(f"仍有 {open_reviews} 条数据待人工审核")
        publication = self.db.scalar(select(KnowledgePublication).where(KnowledgePublication.build_run_id == run_id))
        if publication and publication.status == "published":
            existing_job = self.db.scalar(
                select(BackgroundJob)
                .where(
                    BackgroundJob.job_type == "knowledge_publish",
                    BackgroundJob.payload["publication_id"].as_string() == str(publication.id),
                )
                .order_by(BackgroundJob.created_at.desc())
            )
            if existing_job:
                return publication, existing_job, False
        qa_count = int(
            self.db.scalar(
                select(func.count()).select_from(KnowledgeQAItem).where(
                    KnowledgeQAItem.build_run_id == run_id,
                    KnowledgeQAItem.review_status == "approved",
                )
            )
            or 0
        )
        triple_count = int(
            self.db.scalar(
                select(func.count()).select_from(KnowledgeTriple).where(
                    KnowledgeTriple.build_run_id == run_id,
                    KnowledgeTriple.review_status == "approved",
                )
            )
            or 0
        )
        if "rag" in run.targets and qa_count == 0:
            raise ValueError("没有通过审核的 QA 可发布")
        if "kg" in run.targets and triple_count == 0:
            raise ValueError("没有通过审核的三元组可发布")

        version = self.db.get(KnowledgeSourceVersion, run.source_version_id)
        if version is None:
            raise LookupError("知识源版本不存在")
        publication = publication or KnowledgePublication(
            build_run_id=run.id,
            version=version.version,
            published_by_id=requested_by_id,
        )
        publication.status = "staging"
        publication.error_message = None
        publication.updated_at = utcnow()
        self.db.add(publication)
        self.db.flush()
        job = BackgroundJob(
            job_type="knowledge_publish",
            status="queued",
            payload={"build_run_id": str(run.id), "publication_id": str(publication.id)},
            requested_by_id=requested_by_id,
        )
        run.status = "publishing"
        run.current_node = "publish_queued"
        run.updated_at = utcnow()
        self.db.add(job)
        self.db.commit()
        return publication, job, True

    def _new_source(self, title: str, version: str, created_by_id: UUID | None) -> KnowledgeSource:
        return KnowledgeSource(
            id=uuid.uuid4(),
            title=title.strip(),
            source_type="document",
            status="draft",
            version=version.strip(),
            created_by_id=created_by_id,
        )

    def _attach_version(
        self,
        source: KnowledgeSource,
        *,
        version: str,
        filename: str,
        content_sha256: str,
        storage_uri: str,
        content_type: str,
        size: int,
        license_note: str | None,
        created_by_id: UUID | None,
        origin: str,
    ) -> KnowledgeSourceVersion:
        markdown = Path(filename).suffix.lower() in {".md", ".markdown"}
        source.version = version.strip()
        source.license_note = license_note
        source.original_filename = filename
        source.mime_type = content_type
        source.storage_uri = storage_uri
        source.content_sha256 = content_sha256
        source.metadata_ = {**source.metadata_, "size": size, "ingestion_origin": origin}
        source.updated_at = utcnow()
        item = KnowledgeSourceVersion(
            source_id=source.id,
            version=version.strip(),
            status="parsed" if markdown else "uploaded",
            content_sha256=content_sha256,
            original_storage_uri=storage_uri,
            markdown_storage_uri=storage_uri if markdown else None,
            parser="markdown" if markdown else "mineru_v4",
            parser_metadata={"original_filename": filename, "content_type": content_type, "size": size, "origin": origin},
            created_by_id=created_by_id,
        )
        self.db.add(item)
        self.db.flush()
        return item

    def _find_existing(
        self,
        title: str,
        version: str,
        digest: str,
    ) -> tuple[KnowledgeSource | None, KnowledgeSourceVersion | None]:
        source = self.db.scalar(select(KnowledgeSource).where(KnowledgeSource.title == title.strip()))
        if source is None:
            return None, None
        item = self.db.scalar(
            select(KnowledgeSourceVersion).where(
                KnowledgeSourceVersion.source_id == source.id,
                KnowledgeSourceVersion.version == version.strip(),
            )
        )
        if item and item.content_sha256 != digest:
            raise ValueError("同名知识源版本已存在，但文件内容不同；请使用新版本号")
        return source, item

    def _config_snapshot(self) -> dict[str, object]:
        return {
            "qa_model_id": self.settings.qa_model_id,
            "kg_model_id": self.settings.kg_model_id,
            "expert_model_id": self.settings.expert_model_id,
            "embedding_model_id": self.settings.embedding_model_id,
            "embedding_dimensions": self.settings.embedding_dimensions,
            "rerank_model_id": self.settings.rerank_model_id,
            "mineru_model_version": self.settings.mineru_model_version,
            "chunk_target_tokens": self.settings.knowledge_chunk_target_tokens,
            "quality_auto_publish_score": self.settings.knowledge_auto_publish_score,
            "max_reflection_rounds": self.settings.knowledge_max_reflection_rounds,
            "schema_version": "家蚕疾病Schema-v1",
            "glossary_version": "1.0.0",
        }

    @staticmethod
    def _object_key(source_id: UUID, version: str, filename: str) -> str:
        safe_version = re.sub(r"[^A-Za-z0-9_.-]+", "-", version).strip("-") or "v1"
        return f"knowledge/{source_id}/{safe_version}/original/{safe_filename(filename)}"

    @staticmethod
    def _validate_suffix(filename: str) -> None:
        if Path(filename).suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
            raise ValueError("暂不支持该文档格式")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()

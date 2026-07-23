from __future__ import annotations

import hashlib
import logging
from collections import Counter, defaultdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import case, func, literal, or_, select, union_all
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_permission
from app.knowledge.deletion import KnowledgeSourceDeletionService
from app.knowledge.indexes import Neo4jKnowledgeGraph
from app.knowledge.quality import evidence_is_supported
from app.knowledge.repository import utcnow
from app.knowledge.schema import validate_triple_types
from app.knowledge.service import KnowledgeService
from app.knowledge.tasks import dispatch_background_job
from app.models import (
    BackgroundJob,
    KnowledgeBuildEvent,
    KnowledgeBuildRun,
    KnowledgeChunk,
    KnowledgePublication,
    KnowledgeQAItem,
    KnowledgeReviewItem,
    KnowledgeSource,
    KnowledgeSourceVersion,
    KnowledgeTriple,
)
from app.schemas import (
    KnowledgeBuildRequest,
    KnowledgePublishRequest,
    KnowledgeReviewDecisionRequest,
    KnowledgeSourceDeleteRequest,
    KnowledgeSourceStatusRequest,
)
from app.services import AdminActor, write_audit


router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    return {
        "sources": int(db.scalar(select(func.count()).select_from(KnowledgeSource)) or 0),
        "ready_sources": int(db.scalar(select(func.count()).select_from(KnowledgeSource).where(KnowledgeSource.status == "ready")) or 0),
        "active_builds": int(
            db.scalar(
                select(func.count()).select_from(KnowledgeBuildRun).where(
                    KnowledgeBuildRun.status.in_(["queued", "running", "publishing"])
                )
            )
            or 0
        ),
        "open_reviews": int(
            db.scalar(
                select(func.count()).select_from(KnowledgeReviewItem).where(
                    KnowledgeReviewItem.status.in_(["open", "claimed"])
                )
            )
            or 0
        ),
        "qa_items": int(db.scalar(select(func.count()).select_from(KnowledgeQAItem)) or 0),
        "triples": int(db.scalar(select(func.count()).select_from(KnowledgeTriple)) or 0),
        "publications": int(
            db.scalar(
                select(func.count()).select_from(KnowledgePublication).where(KnowledgePublication.status == "published")
            )
            or 0
        ),
    }


@router.get("/sources")
def list_sources(
    query: str = Query(default="", max_length=120),
    source_status: str | None = Query(default=None, alias="status", pattern="^(draft|processing|ready|failed|disabled)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    conditions = []
    if query.strip():
        conditions.append(or_(KnowledgeSource.title.ilike(f"%{query.strip()}%"), KnowledgeSource.original_filename.ilike(f"%{query.strip()}%")))
    if source_status:
        conditions.append(KnowledgeSource.status == source_status)
    statement = select(KnowledgeSource)
    count_statement = select(func.count()).select_from(KnowledgeSource)
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)
    total = int(db.scalar(count_statement) or 0)
    items = db.scalars(
        statement.order_by(KnowledgeSource.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_source_dict(db, item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/sources/upload", status_code=status.HTTP_201_CREATED)
def upload_source(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=2, max_length=240),
    version: str = Form(default="v1", min_length=1, max_length=60),
    license_note: str | None = Form(default=None, max_length=1000),
    reason: str = Form(..., min_length=3, max_length=500),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.manage")),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择文档")
    try:
        source, source_version = KnowledgeService(db).import_stream(
            file.file,
            filename=file.filename,
            title=title.strip(),
            version=version.strip(),
            content_type=file.content_type,
            license_note=license_note,
            created_by_id=actor.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    write_audit(
        db,
        actor_id=actor.id,
        action="knowledge.source_uploaded",
        resource_type="knowledge_source",
        resource_id=str(source.id),
        request=request,
        reason=reason,
        after_data={"title": source.title, "version_id": str(source_version.id), "filename": source.original_filename},
    )
    db.commit()
    return {"source": _source_dict(db, source), "version": _version_dict(source_version)}


@router.get("/sources/{source_id}")
def source_detail(
    source_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    source = db.get(KnowledgeSource, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识源不存在")
    versions = db.scalars(
        select(KnowledgeSourceVersion)
        .where(KnowledgeSourceVersion.source_id == source.id)
        .order_by(KnowledgeSourceVersion.created_at.desc())
    ).all()
    version_ids = [version.id for version in versions]
    builds = (
        db.scalars(
            select(KnowledgeBuildRun)
            .where(KnowledgeBuildRun.source_version_id.in_(version_ids))
            .order_by(KnowledgeBuildRun.created_at.desc())
        ).all()
        if version_ids
        else []
    )
    return {
        "source": _source_dict(db, source),
        "versions": [_version_dict(item) for item in versions],
        "builds": [_build_dict(db, item) for item in builds],
    }


@router.patch("/sources/{source_id}/status")
def update_source_status(
    source_id: UUID,
    payload: KnowledgeSourceStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.manage")),
) -> dict:
    source = db.get(KnowledgeSource, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识源不存在")
    active_builds = int(
        db.scalar(
            select(func.count())
            .select_from(KnowledgeBuildRun)
            .join(KnowledgeSourceVersion, KnowledgeSourceVersion.id == KnowledgeBuildRun.source_version_id)
            .where(
                KnowledgeSourceVersion.source_id == source.id,
                KnowledgeBuildRun.status.in_(["queued", "running", "publishing"]),
            )
        )
        or 0
    )
    if active_builds:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该文档仍有运行中的构建或发布任务，请先等待完成或到后台任务中取消")
    before = source.status
    source.status = payload.status
    source.updated_at = utcnow()
    write_audit(db, actor_id=actor.id, action="knowledge.source_status_changed", resource_type="knowledge_source", resource_id=str(source.id), request=request, reason=payload.reason, before_data={"status": before}, after_data={"status": source.status})
    db.commit()
    return _source_dict(db, source)


@router.delete("/sources/{source_id}")
def delete_source(
    source_id: UUID,
    payload: KnowledgeSourceDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.manage")),
) -> dict:
    source = db.get(KnowledgeSource, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识源不存在")
    if payload.confirmation_title.strip() != source.title:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="确认名称与文档名称不一致")
    before = {
        "id": str(source.id),
        "title": source.title,
        "status": source.status,
        "version": source.version,
    }
    try:
        result = KnowledgeSourceDeletionService(db).delete(source)
        write_audit(
            db,
            actor_id=actor.id,
            action="knowledge.source_deleted",
            resource_type="knowledge_source",
            resource_id=str(source_id),
            request=request,
            reason=payload.reason,
            before_data=before,
            after_data=result,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Knowledge source cascade deletion failed", extra={"knowledge_source_id": str(source_id)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="文档关联的外部知识库清理失败，数据库记录尚未删除，请稍后重试",
        ) from exc
    return result


@router.post("/sources/{source_id}/build", status_code=status.HTTP_202_ACCEPTED)
def build_source(
    source_id: UUID,
    payload: KnowledgeBuildRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.manage")),
) -> dict:
    try:
        run, job, created = KnowledgeService(db).queue_build(
            source_id,
            targets=list(payload.targets),
            requested_by_id=actor.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    write_audit(db, actor_id=actor.id, action="knowledge.build_queued", resource_type="knowledge_build", resource_id=str(run.id), request=request, reason=payload.reason, after_data={"job_id": str(job.id), "targets": run.targets, "created": created})
    db.commit()
    if created:
        _dispatch_or_fail(db, job)
    return {"build": _build_dict(db, run), "job": _job_dict(job), "created": created}


@router.get("/builds")
def list_builds(
    build_status: str | None = Query(default=None, alias="status", pattern="^(queued|running|awaiting_review|publishing|succeeded|failed|cancelled)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    statement = select(KnowledgeBuildRun)
    count_statement = select(func.count()).select_from(KnowledgeBuildRun)
    if build_status:
        statement = statement.where(KnowledgeBuildRun.status == build_status)
        count_statement = count_statement.where(KnowledgeBuildRun.status == build_status)
    total = int(db.scalar(count_statement) or 0)
    rows = db.scalars(statement.order_by(KnowledgeBuildRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_build_dict(db, item) for item in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/builds/{run_id}")
def build_detail(
    run_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    run = db.get(KnowledgeBuildRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识构建任务不存在")
    events = db.scalars(
        select(KnowledgeBuildEvent).where(KnowledgeBuildEvent.build_run_id == run.id).order_by(KnowledgeBuildEvent.created_at)
    ).all()
    chunk_decisions, chunk_decision_total = _chunk_agent_decisions(db, run.id)
    return {
        "build": _build_dict(db, run),
        "agent_runtime": _agent_runtime(db, run, events),
        "chunk_decisions": chunk_decisions,
        "chunk_decision_total": chunk_decision_total,
        "events": [
            {"id": str(event.id), "node": event.node, "level": event.level, "message": event.message, "payload": event.payload, "created_at": event.created_at}
            for event in events
        ],
    }


@router.get("/extractions")
def list_extractions(
    item_type: str = Query(default="all", pattern="^(all|qa|triple)$"),
    extraction_status: str = Query(
        default="all",
        alias="status",
        pattern="^(all|pending|needs_review|approved|rejected|published)$",
    ),
    query: str = Query(default="", max_length=160),
    build_run_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    """Return every QA/triple candidate, not only records routed to human review."""
    del actor
    needle = query.strip()
    qa_base_conditions = []
    triple_base_conditions = []
    if build_run_id:
        qa_base_conditions.append(KnowledgeQAItem.build_run_id == build_run_id)
        triple_base_conditions.append(KnowledgeTriple.build_run_id == build_run_id)
    if needle:
        like = f"%{needle}%"
        qa_base_conditions.append(
            or_(
                KnowledgeQAItem.question.ilike(like),
                KnowledgeQAItem.answer.ilike(like),
                KnowledgeQAItem.evidence_text.ilike(like),
            )
        )
        triple_base_conditions.append(
            or_(
                KnowledgeTriple.subject_name.ilike(like),
                KnowledgeTriple.subject_canonical_name.ilike(like),
                KnowledgeTriple.relation.ilike(like),
                KnowledgeTriple.object_name.ilike(like),
                KnowledgeTriple.object_canonical_name.ilike(like),
                KnowledgeTriple.evidence_text.ilike(like),
            )
        )

    qa_conditions = list(qa_base_conditions)
    triple_conditions = list(triple_base_conditions)
    if extraction_status != "all":
        qa_conditions.append(KnowledgeQAItem.review_status == extraction_status)
        triple_conditions.append(KnowledgeTriple.review_status == extraction_status)

    qa_rows = select(
        literal("qa").label("item_type"),
        KnowledgeQAItem.id.label("resource_id"),
        KnowledgeQAItem.created_at.label("created_at"),
    ).where(*qa_conditions)
    triple_rows = select(
        literal("triple").label("item_type"),
        KnowledgeTriple.id.label("resource_id"),
        KnowledgeTriple.created_at.label("created_at"),
    ).where(*triple_conditions)
    if item_type == "qa":
        extraction_rows = qa_rows.subquery("extraction_rows")
    elif item_type == "triple":
        extraction_rows = triple_rows.subquery("extraction_rows")
    else:
        extraction_rows = union_all(qa_rows, triple_rows).subquery("extraction_rows")

    total = int(db.scalar(select(func.count()).select_from(extraction_rows)) or 0)
    rows = db.execute(
        select(extraction_rows.c.item_type, extraction_rows.c.resource_id)
        .order_by(extraction_rows.c.created_at.desc(), extraction_rows.c.resource_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    result_items = []
    for row_type, resource_id in rows:
        model = KnowledgeQAItem if row_type == "qa" else KnowledgeTriple
        candidate = db.get(model, resource_id)
        if candidate is not None:
            result_items.append(_extraction_dict(db, candidate, include_content=False))

    status_counts: Counter[str] = Counter()
    for status_name, count in db.execute(
        select(KnowledgeQAItem.review_status, func.count())
        .where(*qa_base_conditions)
        .group_by(KnowledgeQAItem.review_status)
    ).all():
        status_counts[str(status_name)] += int(count)
    for status_name, count in db.execute(
        select(KnowledgeTriple.review_status, func.count())
        .where(*triple_base_conditions)
        .group_by(KnowledgeTriple.review_status)
    ).all():
        status_counts[str(status_name)] += int(count)
    qa_total = int(
        db.scalar(select(func.count()).select_from(KnowledgeQAItem).where(*qa_base_conditions)) or 0
    )
    triple_total = int(
        db.scalar(select(func.count()).select_from(KnowledgeTriple).where(*triple_base_conditions)) or 0
    )
    return {
        "items": result_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "counts": {
            "all": qa_total + triple_total,
            "qa": qa_total,
            "triple": triple_total,
            "by_status": dict(status_counts),
        },
    }


@router.get("/extractions/{item_type}/{item_id}")
def extraction_detail(
    item_type: str,
    item_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    model = {"qa": KnowledgeQAItem, "triple": KnowledgeTriple}.get(item_type)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="抽取类型不存在")
    candidate = db.get(model, item_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="抽取结果不存在")
    return _extraction_dict(db, candidate, include_content=True)


@router.get("/reviews")
def list_reviews(
    item_type: str | None = Query(default=None, pattern="^(chunk|qa|triple|conflict)$"),
    review_status: str = Query(default="active", alias="status", pattern="^(open|claimed|approved|rejected|active|all)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    conditions = []
    if item_type:
        conditions.append(KnowledgeReviewItem.item_type == item_type)
    if review_status == "active":
        conditions.append(KnowledgeReviewItem.status.in_(["open", "claimed"]))
    elif review_status != "all":
        conditions.append(KnowledgeReviewItem.status == review_status)
    statement = select(KnowledgeReviewItem)
    count_statement = select(func.count()).select_from(KnowledgeReviewItem)
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)
    total = int(db.scalar(count_statement) or 0)
    rows = db.scalars(
        statement.order_by(
            case(
                (KnowledgeReviewItem.priority == "critical", 4),
                (KnowledgeReviewItem.priority == "high", 3),
                (KnowledgeReviewItem.priority == "medium", 2),
                (KnowledgeReviewItem.priority == "low", 1),
                else_=0,
            ).desc(),
            KnowledgeReviewItem.created_at.asc(),
        ).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [_review_dict(db, item, include_content=False) for item in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/reviews/{review_id}")
def review_detail(
    review_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    item = db.get(KnowledgeReviewItem, review_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核项不存在")
    return _review_dict(db, item, include_content=True)


@router.patch("/reviews/{review_id}")
def decide_review(
    review_id: UUID,
    payload: KnowledgeReviewDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.manage")),
) -> dict:
    review = db.get(KnowledgeReviewItem, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="审核项不存在")
    if review.status not in {"open", "claimed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该审核项已经处理")
    if review.version != payload.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="审核项已被其他人更新，请刷新后重试")
    before = _review_dict(db, review, include_content=False)
    applied_corrections: dict[str, Any] = {}
    if payload.action == "approve":
        applied_corrections = payload.corrections
        try:
            _apply_corrections(db, review, applied_corrections)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    now = utcnow()
    decision = "approved" if payload.action == "approve" else "rejected"
    review.status = decision
    review.reviewed_by_id = actor.id
    review.decision_note = payload.note
    review.reviewed_at = now
    review.updated_at = now
    review.version += 1
    candidate = _candidate(db, review)
    if isinstance(candidate, (KnowledgeQAItem, KnowledgeTriple)):
        candidate.review_status = decision
        candidate.review_note = payload.note
        candidate.reviewed_by_id = actor.id
        candidate.reviewed_at = now
        candidate.updated_at = now
    db.flush()
    _refresh_run_review_state(db, review.build_run_id)
    write_audit(db, actor_id=actor.id, action=f"knowledge.review_{payload.action}", resource_type="knowledge_review", resource_id=str(review.id), request=request, reason=payload.note, before_data=before, after_data={"status": decision, "corrections": applied_corrections, "version": review.version})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="修订结果与已有知识项重复") from exc
    return _review_dict(db, review, include_content=True)


@router.post("/builds/{run_id}/publish", status_code=status.HTTP_202_ACCEPTED)
def publish_build(
    run_id: UUID,
    payload: KnowledgePublishRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.manage")),
) -> dict:
    try:
        publication, job, created = KnowledgeService(db).queue_publish(run_id, requested_by_id=actor.id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    write_audit(db, actor_id=actor.id, action="knowledge.publish_queued", resource_type="knowledge_publication", resource_id=str(publication.id), request=request, reason=payload.reason, after_data={"job_id": str(job.id), "created": created})
    db.commit()
    if created:
        _dispatch_or_fail(db, job)
    return {"publication": _publication_dict(publication), "job": _job_dict(job), "created": created}


@router.get("/publications")
def list_publications(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    rows = db.scalars(select(KnowledgePublication).order_by(KnowledgePublication.created_at.desc()).limit(100)).all()
    return {"items": [_publication_dict(item) for item in rows]}


@router.get("/graph/preview")
def graph_preview(
    query: str = Query(default="", max_length=120),
    limit: int = Query(default=120, ge=1, le=300),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    try:
        return Neo4jKnowledgeGraph().preview(query=query, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Neo4j Aura 暂不可用：{exc.__class__.__name__}") from exc


@router.get("/graph/explore")
def graph_explore(
    query: str = Query(default="", max_length=120),
    limit: int = Query(default=3000, ge=1, le=5000),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    try:
        return Neo4jKnowledgeGraph().explore(query=query, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Neo4j Aura 暂不可用：{exc.__class__.__name__}") from exc


@router.get("/graph/detail")
def graph_detail(
    element_id: str = Query(min_length=1, max_length=200),
    kind: str = Query(pattern="^(node|relationship)$"),
    actor: AdminActor = Depends(require_permission("knowledge.read")),
) -> dict:
    del actor
    try:
        result = Neo4jKnowledgeGraph().detail(element_id=element_id, kind=kind)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Neo4j Aura 暂不可用：{exc.__class__.__name__}") from exc
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图谱元素不存在")
    return result


def _dispatch_or_fail(db: Session, job: BackgroundJob) -> None:
    try:
        dispatch_background_job(job.id)
    except Exception as exc:
        failed_at = utcnow()
        job.status = "failed"
        job.error_message = f"任务队列不可用：{exc.__class__.__name__}"
        job.completed_at = failed_at
        job.updated_at = failed_at
        if job.job_type == "knowledge_build":
            run = db.scalar(select(KnowledgeBuildRun).where(KnowledgeBuildRun.job_id == job.id))
            if run is not None:
                run.status = "failed"
                run.current_node = "queue_dispatch_failed"
                run.error_message = job.error_message
                run.completed_at = failed_at
                run.updated_at = failed_at
        elif job.job_type == "knowledge_publish" and job.payload.get("publication_id"):
            publication = db.get(KnowledgePublication, UUID(str(job.payload["publication_id"])))
            if publication is not None:
                publication.status = "failed"
                publication.error_message = job.error_message
                publication.updated_at = failed_at
                run = db.get(KnowledgeBuildRun, publication.build_run_id)
                if run is not None:
                    run.status = "failed"
                    run.current_node = "publish_queue_dispatch_failed"
                    run.error_message = job.error_message
                    run.completed_at = failed_at
                    run.updated_at = failed_at
        db.commit()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="任务队列暂不可用，任务已保留，可稍后重试") from exc


def _source_dict(db: Session, source: KnowledgeSource) -> dict[str, Any]:
    version_count = int(db.scalar(select(func.count()).select_from(KnowledgeSourceVersion).where(KnowledgeSourceVersion.source_id == source.id)) or 0)
    return {
        "id": str(source.id),
        "title": source.title,
        "source_type": source.source_type,
        "status": source.status,
        "version": source.version,
        "license_note": source.license_note,
        "original_filename": source.original_filename,
        "mime_type": source.mime_type,
        "content_sha256": source.content_sha256,
        "published_version_id": str(source.published_version_id) if source.published_version_id else None,
        "metadata": source.metadata_,
        "version_count": version_count,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


def _version_dict(item: KnowledgeSourceVersion) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "source_id": str(item.source_id),
        "version": item.version,
        "status": item.status,
        "content_sha256": item.content_sha256,
        "parser": item.parser,
        "parser_task_id": item.parser_task_id,
        "parser_metadata": item.parser_metadata,
        "heading_count": item.heading_count,
        "chunk_count": item.chunk_count,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _agent_runtime(
    db: Session,
    run: KnowledgeBuildRun,
    events: list[KnowledgeBuildEvent],
) -> dict[str, Any]:
    structured = [event for event in events if isinstance(event.payload, dict) and event.payload.get("event_type")]
    plan = dict(run.config_snapshot.get("agent_plan", {})) if isinstance(run.config_snapshot, dict) else {}
    if not plan:
        for event in structured:
            if event.payload.get("event_type") == "agent_plan" and isinstance(event.payload.get("plan"), dict):
                plan = dict(event.payload["plan"])
                break
    tools = list(
        dict.fromkeys(
            str(event.payload["tool"])
            for event in structured
            if event.payload.get("tool")
        )
    )
    reflection_rounds = {"rag": 0, "kg": 0}
    route_counts: Counter[str] = Counter()
    last_route = ""
    for event in structured:
        payload = event.payload
        agent = str(payload.get("agent", ""))
        if agent in reflection_rounds:
            reflection_rounds[agent] = max(reflection_rounds[agent], int(payload.get("revision_round", 0) or 0))
        route = str(payload.get("route", ""))
        if route:
            route_counts[route] += 1
            last_route = route
    review_rows = db.scalars(
        select(KnowledgeReviewItem).where(
            KnowledgeReviewItem.build_run_id == run.id,
            KnowledgeReviewItem.status.in_(["open", "claimed"]),
        )
    ).all()
    handoff_reasons = Counter(str(reason) for review in review_rows for reason in review.reason_codes)
    current_node = run.current_node or "queued"
    if current_node.startswith("rag_"):
        active_agent = "rag"
    elif current_node.startswith("kg_"):
        active_agent = "kg"
    elif current_node.startswith("publish") or current_node == "published":
        active_agent = "publisher"
    else:
        active_agent = "orchestrator"
    decision_trail = [
        {
            "event_id": str(event.id),
            "node": event.node,
            "message": event.message,
            "event_type": event.payload.get("event_type"),
            "agent": event.payload.get("agent"),
            "tool": event.payload.get("tool"),
            "route": event.payload.get("route"),
            "revision_round": event.payload.get("revision_round"),
            "risk_summary": event.payload.get("risk_summary", {}),
            "created_at": event.created_at,
        }
        for event in structured[-20:]
    ]
    return {
        "active_agent": active_agent,
        "current_node": current_node,
        "last_route": last_route,
        "plan": plan,
        "tools_invoked": tools,
        "reflection_rounds": reflection_rounds,
        "route_counts": dict(route_counts),
        "human_handoff_count": len(review_rows),
        "human_handoff_reasons": dict(handoff_reasons),
        "structured_event_count": len(structured),
        "decision_trail": decision_trail,
    }


def _chunk_agent_decisions(db: Session, run_id: UUID, limit: int = 200) -> tuple[list[dict[str, Any]], int]:
    chunks = db.scalars(
        select(KnowledgeChunk)
        .where(KnowledgeChunk.build_run_id == run_id)
        .order_by(KnowledgeChunk.ordinal)
    ).all()
    qa_rows = db.scalars(select(KnowledgeQAItem).where(KnowledgeQAItem.build_run_id == run_id)).all()
    triple_rows = db.scalars(select(KnowledgeTriple).where(KnowledgeTriple.build_run_id == run_id)).all()
    review_rows = db.scalars(select(KnowledgeReviewItem).where(KnowledgeReviewItem.build_run_id == run_id)).all()
    qa_by_chunk: defaultdict[UUID, list[KnowledgeQAItem]] = defaultdict(list)
    triple_by_chunk: defaultdict[UUID, list[KnowledgeTriple]] = defaultdict(list)
    qa_chunk_by_id: dict[UUID, UUID] = {}
    triple_chunk_by_id: dict[UUID, UUID] = {}
    for item in qa_rows:
        qa_by_chunk[item.chunk_id].append(item)
        qa_chunk_by_id[item.id] = item.chunk_id
    for item in triple_rows:
        triple_by_chunk[item.chunk_id].append(item)
        triple_chunk_by_id[item.id] = item.chunk_id
    handoff_by_chunk: defaultdict[UUID, list[str]] = defaultdict(list)
    for review in review_rows:
        chunk_id = review.resource_id if review.item_type == "chunk" else None
        if review.item_type == "qa":
            chunk_id = qa_chunk_by_id.get(review.resource_id)
        elif review.item_type == "triple":
            chunk_id = triple_chunk_by_id.get(review.resource_id)
        if chunk_id:
            handoff_by_chunk[chunk_id].extend(str(reason) for reason in review.reason_codes)

    def summarize(items: list[KnowledgeQAItem] | list[KnowledgeTriple]) -> dict[str, Any]:
        statuses = Counter(item.review_status for item in items)
        risks = Counter(str(flag) for item in items for flag in item.risk_flags)
        revision_count = 0
        expert_count = 0
        for item in items:
            assessment = item.expert_assessment if isinstance(item.expert_assessment, dict) else {}
            agent_metadata = assessment.get("agent", {}) if isinstance(assessment.get("agent", {}), dict) else {}
            revision_count = max(revision_count, int(agent_metadata.get("revision_count", 0) or 0))
            if "approved" in assessment or assessment.get("reason"):
                expert_count += 1
        return {
            "candidate_count": len(items),
            "status_counts": dict(statuses),
            "risk_flags": dict(risks),
            "revision_count": revision_count,
            "expert_review_count": expert_count,
        }

    decisions: list[dict[str, Any]] = []
    for chunk in chunks[:limit]:
        qa = summarize(qa_by_chunk.get(chunk.id, []))
        kg = summarize(triple_by_chunk.get(chunk.id, []))
        handoff_reasons = list(dict.fromkeys(handoff_by_chunk.get(chunk.id, [])))
        if handoff_reasons:
            final_route = "human_review"
        elif qa["candidate_count"] or kg["candidate_count"]:
            final_route = "approved"
        else:
            final_route = "skipped"
        decisions.append(
            {
                "chunk_id": str(chunk.id),
                "ordinal": chunk.ordinal,
                "heading_path": chunk.heading_path,
                "token_count": chunk.token_count,
                "quality_score": chunk.quality_score,
                "quality_flags": chunk.quality_flags,
                "split_strategy": chunk.split_strategy,
                "rag": qa,
                "kg": kg,
                "final_route": final_route,
                "human_handoff_reasons": handoff_reasons,
            }
        )
    return decisions, len(chunks)


def _build_dict(db: Session, run: KnowledgeBuildRun) -> dict[str, Any]:
    version = db.get(KnowledgeSourceVersion, run.source_version_id)
    source = db.get(KnowledgeSource, version.source_id) if version else None
    review_count = int(
        db.scalar(
            select(func.count()).select_from(KnowledgeReviewItem).where(
                KnowledgeReviewItem.build_run_id == run.id,
                KnowledgeReviewItem.status.in_(["open", "claimed"]),
            )
        )
        or 0
    )
    publication = db.scalar(
        select(KnowledgePublication)
        .where(KnowledgePublication.build_run_id == run.id)
        .order_by(KnowledgePublication.created_at.desc())
        .limit(1)
    )
    return {
        "id": str(run.id),
        "source_version_id": str(run.source_version_id),
        "source_id": str(source.id) if source else None,
        "source_title": source.title if source else None,
        "version": version.version if version else None,
        "job_id": str(run.job_id) if run.job_id else None,
        "targets": run.targets,
        "status": run.status,
        "current_node": run.current_node,
        "progress": run.progress,
        "metrics": run.metrics,
        "open_review_count": review_count,
        "publication": _publication_dict(publication) if publication else None,
        "error_message": run.error_message,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def _extraction_dict(
    db: Session,
    candidate: KnowledgeQAItem | KnowledgeTriple,
    *,
    include_content: bool,
) -> dict[str, Any]:
    item_type = "qa" if isinstance(candidate, KnowledgeQAItem) else "triple"
    chunk = db.get(KnowledgeChunk, candidate.chunk_id)
    version = db.get(KnowledgeSourceVersion, chunk.source_version_id) if chunk else None
    source = db.get(KnowledgeSource, version.source_id) if version else None
    run = db.get(KnowledgeBuildRun, candidate.build_run_id)
    review = db.scalar(
        select(KnowledgeReviewItem)
        .where(
            KnowledgeReviewItem.item_type == item_type,
            KnowledgeReviewItem.resource_id == candidate.id,
        )
        .order_by(KnowledgeReviewItem.created_at.desc())
        .limit(1)
    )

    evidence = candidate.evidence_text if include_content else _preview(candidate.evidence_text, 280)
    common_payload: dict[str, Any] = {
        "id": str(candidate.id),
        "evidence": evidence,
        "extraction_confidence": candidate.extraction_confidence,
        "rule_score": candidate.rule_score,
        "expert_score": candidate.expert_score,
        "expert_assessment": candidate.expert_assessment if include_content else {},
        "risk_flags": candidate.risk_flags,
        "review_status": candidate.review_status,
        "review_note": candidate.review_note,
        "reviewed_at": candidate.reviewed_at,
        "published_at": candidate.published_at,
    }
    if isinstance(candidate, KnowledgeQAItem):
        title = candidate.question
        summary = candidate.answer
        candidate_payload = {
            **common_payload,
            "question": candidate.question,
            "answer": candidate.answer if include_content else _preview(candidate.answer, 320),
            "keywords": candidate.keywords,
            "knowledge_types": candidate.knowledge_types,
            "qdrant_point_id": candidate.qdrant_point_id,
            "opensearch_document_id": candidate.opensearch_document_id,
        }
    else:
        title = (
            f"{candidate.subject_canonical_name} —{candidate.relation}→ "
            f"{candidate.object_canonical_name}"
        )
        summary = candidate.evidence_text
        candidate_payload = {
            **common_payload,
            "subject_name": candidate.subject_name,
            "subject_type": candidate.subject_type,
            "subject_canonical_name": candidate.subject_canonical_name,
            "relation": candidate.relation,
            "object_name": candidate.object_name,
            "object_type": candidate.object_type,
            "object_canonical_name": candidate.object_canonical_name,
            "resolution_metadata": candidate.resolution_metadata if include_content else {},
            "neo4j_synced_at": candidate.neo4j_synced_at,
        }
    return {
        "id": str(candidate.id),
        "item_type": item_type,
        "build_run_id": str(candidate.build_run_id),
        "status": candidate.review_status,
        "display_title": title,
        "display_summary": summary if include_content else _preview(summary, 220),
        "candidate": candidate_payload,
        "source": {
            "id": str(source.id),
            "title": source.title,
            "version": version.version,
            "source_version_id": str(version.id),
        }
        if source and version
        else None,
        "build": {
            "id": str(run.id),
            "status": run.status,
            "targets": run.targets,
            "created_at": run.created_at,
        }
        if run
        else None,
        "chunk": {
            "id": str(chunk.id),
            "ordinal": chunk.ordinal,
            "heading_path": chunk.heading_path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "content": chunk.content if include_content else _preview(chunk.content, 260),
            "token_count": chunk.token_count,
            "quality_score": chunk.quality_score,
            "quality_flags": chunk.quality_flags,
            "split_strategy": chunk.split_strategy,
        }
        if chunk
        else None,
        "manual_review": {
            "id": str(review.id),
            "status": review.status,
            "priority": review.priority,
            "reason_codes": review.reason_codes,
            "model_assessment": review.model_assessment if include_content else {},
            "decision_note": review.decision_note,
            "created_at": review.created_at,
            "reviewed_at": review.reviewed_at,
        }
        if review
        else None,
        "created_at": candidate.created_at,
        "updated_at": candidate.updated_at,
    }


def _preview(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else f"{compact[:limit].rstrip()}…"


def _review_dict(db: Session, item: KnowledgeReviewItem, *, include_content: bool) -> dict[str, Any]:
    candidate = _candidate(db, item)
    chunk = None
    candidate_payload: dict[str, Any] = {}
    if isinstance(candidate, KnowledgeQAItem):
        chunk = db.get(KnowledgeChunk, candidate.chunk_id)
        candidate_payload = {
            "id": str(candidate.id),
            "question": candidate.question,
            "answer": candidate.answer,
            "evidence": candidate.evidence_text,
            "keywords": candidate.keywords,
            "knowledge_types": candidate.knowledge_types,
            "rule_score": candidate.rule_score,
            "expert_score": candidate.expert_score,
            "risk_flags": candidate.risk_flags,
            "review_status": candidate.review_status,
        }
    elif isinstance(candidate, KnowledgeTriple):
        chunk = db.get(KnowledgeChunk, candidate.chunk_id)
        candidate_payload = {
            "id": str(candidate.id),
            "subject_name": candidate.subject_name,
            "subject_type": candidate.subject_type,
            "subject_canonical_name": candidate.subject_canonical_name,
            "relation": candidate.relation,
            "object_name": candidate.object_name,
            "object_type": candidate.object_type,
            "object_canonical_name": candidate.object_canonical_name,
            "evidence": candidate.evidence_text,
            "rule_score": candidate.rule_score,
            "expert_score": candidate.expert_score,
            "risk_flags": candidate.risk_flags,
            "resolution_metadata": candidate.resolution_metadata,
            "review_status": candidate.review_status,
        }
    elif isinstance(candidate, KnowledgeChunk):
        chunk = candidate
        candidate_payload = {"id": str(candidate.id), "quality_score": candidate.quality_score, "quality_flags": candidate.quality_flags}
    version = db.get(KnowledgeSourceVersion, chunk.source_version_id) if chunk else None
    source = db.get(KnowledgeSource, version.source_id) if version else None
    return {
        "id": str(item.id),
        "build_run_id": str(item.build_run_id),
        "item_type": item.item_type,
        "resource_id": str(item.resource_id),
        "status": item.status,
        "priority": item.priority,
        "reason_codes": item.reason_codes,
        "model_assessment": item.model_assessment,
        "decision_note": item.decision_note,
        "version": item.version,
        "candidate": candidate_payload,
        "source": {"id": str(source.id), "title": source.title, "version": version.version} if source and version else None,
        "chunk": {
            "id": str(chunk.id),
            "heading_path": chunk.heading_path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "content": chunk.content if include_content else chunk.content[:240],
            "token_count": chunk.token_count,
        }
        if chunk
        else None,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "reviewed_at": item.reviewed_at,
    }


def _candidate(db: Session, item: KnowledgeReviewItem):
    model = {"qa": KnowledgeQAItem, "triple": KnowledgeTriple, "chunk": KnowledgeChunk}.get(item.item_type)
    return db.get(model, item.resource_id) if model else None


def _apply_corrections(db: Session, review: KnowledgeReviewItem, corrections: dict[str, Any]) -> None:
    if not corrections:
        return
    candidate = _candidate(db, review)
    if isinstance(candidate, KnowledgeQAItem):
        allowed = {"question", "answer", "evidence", "keywords", "knowledge_types"}
        if set(corrections) - allowed:
            raise ValueError("QA 修订包含不支持的字段")
        chunk = db.get(KnowledgeChunk, candidate.chunk_id)
        question = str(corrections.get("question", candidate.question)).strip()
        answer = str(corrections.get("answer", candidate.answer)).strip()
        evidence = str(corrections.get("evidence", candidate.evidence_text)).strip()
        if len(question) < 2 or len(answer) < 2 or not chunk or not evidence_is_supported(evidence, chunk.content):
            raise ValueError("QA 修订内容为空或证据不在来源 Chunk 中")
        candidate.question = question
        candidate.question_sha256 = hashlib.sha256("".join(question.split()).encode("utf-8")).hexdigest()
        candidate.answer = answer
        candidate.evidence_text = evidence
        if "keywords" in corrections:
            candidate.keywords = list(dict.fromkeys(str(value).strip() for value in corrections["keywords"] if str(value).strip()))[:20]
        if "knowledge_types" in corrections:
            candidate.knowledge_types = list(corrections["knowledge_types"])
    elif isinstance(candidate, KnowledgeTriple):
        allowed = {"subject_name", "subject_type", "subject_canonical_name", "relation", "object_name", "object_type", "object_canonical_name", "evidence"}
        if set(corrections) - allowed:
            raise ValueError("三元组修订包含不支持的字段")
        chunk = db.get(KnowledgeChunk, candidate.chunk_id)
        values = {
            "subject_name": str(corrections.get("subject_name", candidate.subject_name)).strip(),
            "subject_type": str(corrections.get("subject_type", candidate.subject_type)).strip(),
            "subject_canonical_name": str(corrections.get("subject_canonical_name", candidate.subject_canonical_name)).strip(),
            "relation": str(corrections.get("relation", candidate.relation)).strip(),
            "object_name": str(corrections.get("object_name", candidate.object_name)).strip(),
            "object_type": str(corrections.get("object_type", candidate.object_type)).strip(),
            "object_canonical_name": str(corrections.get("object_canonical_name", candidate.object_canonical_name)).strip(),
            "evidence": str(corrections.get("evidence", candidate.evidence_text)).strip(),
        }
        if validate_triple_types(values["subject_type"], values["relation"], values["object_type"]):
            raise ValueError("三元组类型或关系不符合 Schema")
        if not all(values.values()) or not chunk or not evidence_is_supported(values["evidence"], chunk.content):
            raise ValueError("三元组修订内容为空或证据不在来源 Chunk 中")
        candidate.subject_name = values["subject_name"]
        candidate.subject_type = values["subject_type"]
        candidate.subject_canonical_name = values["subject_canonical_name"]
        candidate.relation = values["relation"]
        candidate.object_name = values["object_name"]
        candidate.object_type = values["object_type"]
        candidate.object_canonical_name = values["object_canonical_name"]
        candidate.evidence_text = values["evidence"]
        candidate.triple_key = hashlib.sha256("\x1f".join([values["subject_canonical_name"], values["subject_type"], values["relation"], values["object_canonical_name"], values["object_type"]]).encode("utf-8")).hexdigest()
    elif corrections:
        raise ValueError("Chunk 审核项不能直接修改抽取数据")


def _refresh_run_review_state(db: Session, run_id: UUID) -> None:
    remaining = int(
        db.scalar(
            select(func.count()).select_from(KnowledgeReviewItem).where(
                KnowledgeReviewItem.build_run_id == run_id,
                KnowledgeReviewItem.status.in_(["open", "claimed"]),
            )
        )
        or 0
    )
    if remaining:
        return
    run = db.get(KnowledgeBuildRun, run_id)
    if run and run.status == "awaiting_review":
        run.status = "succeeded"
        run.current_node = "ready_to_publish"
        run.updated_at = utcnow()
        version = db.get(KnowledgeSourceVersion, run.source_version_id)
        if version:
            source = db.get(KnowledgeSource, version.source_id)
            if source:
                source.status = "ready"
                source.updated_at = utcnow()


def _publication_dict(item: KnowledgePublication) -> dict[str, Any]:
    return {"id": str(item.id), "build_run_id": str(item.build_run_id), "version": item.version, "status": item.status, "qdrant_collection": item.qdrant_collection, "opensearch_index": item.opensearch_index, "neo4j_database": item.neo4j_database, "counts": item.counts, "error_message": item.error_message, "published_at": item.published_at, "created_at": item.created_at, "updated_at": item.updated_at}


def _job_dict(item: BackgroundJob) -> dict[str, Any]:
    return {"id": str(item.id), "job_type": item.job_type, "status": item.status, "progress": item.progress, "result": item.result, "error_message": item.error_message, "created_at": item.created_at, "updated_at": item.updated_at, "started_at": item.started_at, "completed_at": item.completed_at}

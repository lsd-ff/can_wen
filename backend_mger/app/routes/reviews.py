from __future__ import annotations

import json
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.dependencies import get_actor, require_permission
from app.models import ExpertReview, SensitiveAccessGrant, WorkItem
from app.schemas import DiagnosisReviewQueueRequest, ExpertReviewRequest, HusbandryReviewQueueRequest, HusbandryReviewRequest, SensitiveAccessRequest, SensitiveAccessResponse
from app.security import now_utc
from app.services import AdminActor, complete_work_items_for_resource, require, work_item_sla_hours, write_audit


settings = get_settings()
router = APIRouter(tags=["reviews"])


@router.post("/sensitive-access-grants", response_model=SensitiveAccessResponse)
def create_sensitive_access_grant(
    payload: SensitiveAccessRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(get_actor),
) -> dict:
    permission = "husbandry.sensitive.read" if payload.resource_type == "husbandry_case" else "diagnosis.sensitive.read"
    require(actor, permission)
    expires_at = now_utc() + timedelta(seconds=settings.sensitive_access_ttl_seconds)
    grant = SensitiveAccessGrant(admin_account_id=actor.id, resource_type=payload.resource_type, resource_id=payload.resource_id, reason=payload.reason, work_item_id=UUID(payload.work_item_id) if payload.work_item_id else None, expires_at=expires_at)
    db.add(grant)
    db.flush()
    write_audit(db, actor_id=actor.id, action="sensitive_access.granted", resource_type=payload.resource_type, resource_id=payload.resource_id, request=request, reason=payload.reason, after_data={"expires_at": expires_at.isoformat(), "work_item_id": payload.work_item_id})
    db.commit()
    return {"id": str(grant.id), "expires_at": expires_at}


@router.get("/diagnosis/reviews")
def diagnosis_reviews(
    review_status: str = Query(default="all", alias="status", pattern="^(all|unreviewed|draft|published)$"),
    risk_level: str | None = Query(default=None, pattern="^(low|medium|high|critical)$"),
    created_since: str | None = Query(default=None, pattern="^(today|7d)$"),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("diagnosis.read")),
) -> dict:
    conditions = ["c.deleted_at IS NULL"]
    values: dict[str, object] = {"limit": page_size, "offset": (page - 1) * page_size}
    if review_status == "unreviewed":
        conditions.append("latest_review.id IS NULL")
    elif review_status in {"draft", "published"}:
        conditions.append("latest_review.status = :review_status")
        values["review_status"] = review_status
    if risk_level:
        conditions.append("COALESCE(latest_review.risk_level, case_risk.risk_level, 'medium') = :risk_level")
        values["risk_level"] = risk_level
    if created_since == "today":
        conditions.append("c.created_at >= date_trunc('day', now())")
    elif created_since == "7d":
        conditions.append("c.created_at >= now() - interval '7 days'")
    if q and q.strip():
        conditions.append("(c.title ILIKE :query OR COALESCE(c.summary, '') ILIKE :query OR COALESCE(u.display_name, '') ILIKE :query OR COALESCE(u.username, '') ILIKE :query)")
        values["query"] = f"%{q.strip()}%"
    where = " AND ".join(conditions)
    joins = """
          JOIN users u ON u.id = c.user_id
          LEFT JOIN LATERAL (
             SELECT er.id, er.status, er.risk_level FROM admin.expert_reviews er
              WHERE er.conversation_id = c.id ORDER BY er.version DESC LIMIT 1
          ) latest_review ON TRUE
          LEFT JOIN LATERAL (
             SELECT CASE
                        WHEN bool_or(hc.severity = 'critical') THEN 'critical'
                        WHEN bool_or(hc.severity = 'high') THEN 'high'
                        WHEN bool_or(hc.severity = 'medium') THEN 'medium'
                        WHEN bool_or(hc.severity = 'low') THEN 'low'
                    END AS risk_level,
                    max(hc.severity) AS severity
               FROM husbandry_cases hc WHERE hc.source_conversation_id = c.id
          ) case_risk ON TRUE
          LEFT JOIN LATERAL (
             SELECT count(DISTINCT m.id) AS message_count,
                    count(DISTINCT mf.file_id) AS attachment_count,
                    bool_or(m.sender_type = 'assistant' AND m.status = 'error') AS has_ai_error
               FROM messages m LEFT JOIN message_files mf ON mf.message_id = m.id
              WHERE m.conversation_id = c.id AND m.deleted_at IS NULL
          ) message_stats ON TRUE
          LEFT JOIN LATERAL (
             SELECT id::text AS id, status, priority, assignee_id::text AS assignee_id
               FROM admin.work_items wi
              WHERE wi.resource_type = 'diagnosis_conversation' AND wi.resource_id = c.id::text
                AND wi.status IN ('open', 'claimed')
              ORDER BY wi.created_at DESC LIMIT 1
          ) review_task ON TRUE
          LEFT JOIN admin.admin_accounts task_assignee ON task_assignee.id::text = review_task.assignee_id
    """
    total = int(db.execute(text(f"""
        SELECT count(*)
          FROM conversations c
          {joins}
         WHERE {where}
    """), values).scalar() or 0)
    rows = db.execute(text(f"""
        SELECT c.id::text AS conversation_id, c.title, c.summary, c.status AS conversation_status,
               c.created_at, c.last_message_at, u.id::text AS user_id,
               COALESCE(u.display_name, u.username, '未命名用户') AS user_name,
               COALESCE(message_stats.message_count, 0) AS message_count,
               COALESCE(message_stats.attachment_count, 0) AS attachment_count,
               latest_review.id::text AS review_id, latest_review.status AS review_status,
               COALESCE(latest_review.risk_level, case_risk.risk_level, 'medium') AS risk_level,
               case_risk.severity AS linked_case_severity,
               COALESCE(message_stats.has_ai_error, false) AS has_ai_error,
               EXISTS (SELECT 1 FROM diagnosis_multimodal_analyses dma WHERE dma.conversation_id = c.id AND dma.status = 'failed') AS has_failed_multimodal,
               review_task.id AS work_item_id, review_task.status AS work_item_status,
               review_task.priority AS work_item_priority, task_assignee.display_name AS work_item_assignee
          FROM conversations c
          {joins}
         WHERE {where}
         ORDER BY CASE COALESCE(latest_review.risk_level, case_risk.risk_level, 'medium') WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                  CASE WHEN review_task.status = 'claimed' THEN 0 WHEN review_task.status = 'open' THEN 1 ELSE 2 END,
                  c.last_message_at DESC NULLS LAST, c.created_at DESC
         LIMIT :limit OFFSET :offset
    """), values).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/diagnosis/overview")
def diagnosis_overview(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("diagnosis.read")),
) -> dict:
    summary = db.execute(text("""
        SELECT
            count(*) FILTER (WHERE c.created_at >= date_trunc('day', now())) AS new_today,
            count(*) FILTER (WHERE latest_review.id IS NULL OR latest_review.status = 'draft') AS awaiting_review,
            count(*) FILTER (WHERE review_task.status IN ('open', 'claimed')) AS queued_reviews,
            count(*) FILTER (WHERE COALESCE(latest_review.risk_level, case_risk.risk_level, 'medium') IN ('high', 'critical')
                             AND latest_review.status IS DISTINCT FROM 'published') AS high_risk_open,
            count(*) FILTER (WHERE latest_review.status = 'published' AND latest_review.published_at >= date_trunc('day', now())) AS published_today
          FROM conversations c
          LEFT JOIN LATERAL (
             SELECT er.id, er.status, er.risk_level, er.published_at FROM admin.expert_reviews er
              WHERE er.conversation_id = c.id ORDER BY er.version DESC LIMIT 1
          ) latest_review ON TRUE
          LEFT JOIN LATERAL (
             SELECT CASE
                        WHEN bool_or(hc.severity = 'critical') THEN 'critical'
                        WHEN bool_or(hc.severity = 'high') THEN 'high'
                        WHEN bool_or(hc.severity = 'medium') THEN 'medium'
                        WHEN bool_or(hc.severity = 'low') THEN 'low'
                    END AS risk_level
               FROM husbandry_cases hc WHERE hc.source_conversation_id = c.id
          ) case_risk ON TRUE
          LEFT JOIN LATERAL (
             SELECT status FROM admin.work_items wi
              WHERE wi.resource_type = 'diagnosis_conversation' AND wi.resource_id = c.id::text
                AND wi.status IN ('open', 'claimed') ORDER BY wi.created_at DESC LIMIT 1
          ) review_task ON TRUE
         WHERE c.deleted_at IS NULL
    """)).mappings().one()
    quality = db.execute(text("""
        SELECT
            count(*) FILTER (WHERE sender_type = 'assistant') AS assistant_messages_7d,
            count(*) FILTER (WHERE sender_type = 'assistant' AND status = 'error') AS failed_assistant_messages_7d,
            count(*) FILTER (WHERE sender_type = 'assistant' AND metadata ? 'feedback') AS feedback_messages_7d
          FROM messages WHERE created_at >= now() - interval '7 days'
    """)).mappings().one()
    multimodal = db.execute(text("""
        SELECT count(*) FILTER (WHERE status = 'failed') AS failed_24h,
               count(*) FILTER (WHERE status = 'running') AS running,
               count(*) FILTER (WHERE status = 'pending') AS pending
          FROM diagnosis_multimodal_analyses WHERE updated_at >= now() - interval '24 hours'
    """)).mappings().one()
    pending = db.execute(text("""
        SELECT c.id::text AS conversation_id, c.title, c.last_message_at,
               COALESCE(u.display_name, u.username, '未命名用户') AS user_name,
               COALESCE(latest_review.risk_level, case_risk.risk_level, 'medium') AS risk_level,
               review_task.status AS work_item_status,
               EXISTS (SELECT 1 FROM diagnosis_multimodal_analyses dma WHERE dma.conversation_id = c.id AND dma.status = 'failed') AS has_failed_multimodal
          FROM conversations c
          JOIN users u ON u.id = c.user_id
          LEFT JOIN LATERAL (
             SELECT er.id, er.status, er.risk_level FROM admin.expert_reviews er
              WHERE er.conversation_id = c.id ORDER BY er.version DESC LIMIT 1
          ) latest_review ON TRUE
          LEFT JOIN LATERAL (
             SELECT CASE
                        WHEN bool_or(hc.severity = 'critical') THEN 'critical'
                        WHEN bool_or(hc.severity = 'high') THEN 'high'
                        WHEN bool_or(hc.severity = 'medium') THEN 'medium'
                        WHEN bool_or(hc.severity = 'low') THEN 'low'
                    END AS risk_level
               FROM husbandry_cases hc WHERE hc.source_conversation_id = c.id
          ) case_risk ON TRUE
          LEFT JOIN LATERAL (
             SELECT status FROM admin.work_items wi
              WHERE wi.resource_type = 'diagnosis_conversation' AND wi.resource_id = c.id::text
                AND wi.status IN ('open', 'claimed') ORDER BY wi.created_at DESC LIMIT 1
          ) review_task ON TRUE
         WHERE c.deleted_at IS NULL
           AND (latest_review.id IS NULL OR latest_review.status = 'draft'
                OR review_task.status IN ('open', 'claimed')
                OR EXISTS (SELECT 1 FROM diagnosis_multimodal_analyses dma WHERE dma.conversation_id = c.id AND dma.status = 'failed'))
         ORDER BY CASE COALESCE(latest_review.risk_level, case_risk.risk_level, 'medium') WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                  c.last_message_at DESC NULLS LAST
         LIMIT 6
    """)).mappings().all()
    assistant_total = int(quality["assistant_messages_7d"] or 0)
    failed_total = int(quality["failed_assistant_messages_7d"] or 0)
    return {
        "summary": {key: int(value or 0) for key, value in summary.items()},
        "quality": {
            "assistant_messages_7d": assistant_total,
            "failed_assistant_messages_7d": failed_total,
            "failure_rate": round(failed_total * 100 / assistant_total, 1) if assistant_total else 0,
            "feedback_messages_7d": int(quality["feedback_messages_7d"] or 0),
        },
        "multimodal": {key: int(value or 0) for key, value in multimodal.items()},
        "attention": [dict(row) for row in pending],
    }


@router.post("/diagnosis/reviews/{conversation_id}/queue")
def queue_diagnosis_review(
    conversation_id: UUID,
    payload: DiagnosisReviewQueueRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("diagnosis.review")),
) -> dict:
    conversation = db.execute(text("""
        SELECT id::text AS id, title FROM conversations
         WHERE id = CAST(:conversation_id AS uuid) AND deleted_at IS NULL
    """), {"conversation_id": str(conversation_id)}).mappings().first()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问诊不存在或已删除")
    active_task = db.scalar(select(WorkItem).where(
        WorkItem.resource_type == "diagnosis_conversation",
        WorkItem.resource_id == str(conversation_id),
        WorkItem.status.in_(("open", "claimed")),
    ).order_by(WorkItem.created_at.desc()))
    priority = payload.risk_level
    priority_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    if active_task is not None:
        before = {"priority": active_task.priority, "status": active_task.status, "version": active_task.version}
        if priority_rank[priority] > priority_rank.get(active_task.priority, 2):
            active_task.priority = priority
        active_task.version += 1
        active_task.updated_at = now_utc()
        write_audit(db, actor_id=actor.id, action="diagnosis.review_queue_updated", resource_type="work_item", resource_id=str(active_task.id), request=request, reason=payload.reason, before_data=before, after_data={"priority": active_task.priority, "status": active_task.status, "conversation_id": str(conversation_id), "version": active_task.version})
        db.commit()
        return {"id": str(active_task.id), "status": active_task.status, "priority": active_task.priority, "created": False}
    high_risk_sla, standard_sla = work_item_sla_hours(db)
    task = WorkItem(
        item_type="diagnosis_review",
        resource_type="diagnosis_conversation",
        resource_id=str(conversation_id),
        title=f"专家复核问诊：{conversation['title']}",
        priority=priority,
        due_at=now_utc() + timedelta(hours=high_risk_sla if priority in {"high", "critical"} else standard_sla),
        metadata_={"source": "diagnosis_console", "risk_level": priority},
    )
    db.add(task)
    try:
        db.flush()
    except IntegrityError:
        # The partial unique index is the final guard when two reviewers add
        # the same conversation to the queue at the same instant.
        db.rollback()
        active_task = db.scalar(select(WorkItem).where(
            WorkItem.resource_type == "diagnosis_conversation",
            WorkItem.resource_id == str(conversation_id),
            WorkItem.status.in_(("open", "claimed")),
        ).order_by(WorkItem.created_at.desc()))
        if active_task is not None:
            return {"id": str(active_task.id), "status": active_task.status, "priority": active_task.priority, "created": False}
        raise
    write_audit(db, actor_id=actor.id, action="diagnosis.review_queued", resource_type="work_item", resource_id=str(task.id), request=request, reason=payload.reason, after_data={"conversation_id": str(conversation_id), "priority": priority, "due_at": task.due_at.isoformat() if task.due_at else None})
    db.commit()
    return {"id": str(task.id), "status": task.status, "priority": task.priority, "created": True}


@router.get("/diagnosis/reviews/{conversation_id}")
def diagnosis_review_detail(
    conversation_id: UUID,
    request: Request,
    include_sensitive: bool = Query(default=False),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("diagnosis.read")),
) -> dict:
    conversation = db.execute(text("""
        SELECT c.id::text AS id, c.title, c.summary, c.status, c.created_at, c.last_message_at,
               u.id::text AS user_id, COALESCE(u.display_name, u.username, '未命名用户') AS user_name
          FROM conversations c JOIN users u ON u.id = c.user_id
         WHERE c.id = CAST(:conversation_id AS uuid)
    """), {"conversation_id": str(conversation_id)}).mappings().first()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问诊不存在")
    sensitive = include_sensitive and _has_sensitive_grant(db, actor.id, "conversation", str(conversation_id))
    if include_sensitive and not sensitive:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请先申请临时查看原文授权")
    if sensitive:
        messages = db.execute(text("""
            SELECT m.id::text AS id, m.sender_type, m.content, m.message_type, m.status, m.metadata, m.created_at,
                   COALESCE(json_agg(json_build_object('id', f.id::text, 'name', f.file_name, 'type', f.file_type, 'size', f.file_size, 'storage_url', f.storage_url)) FILTER (WHERE f.id IS NOT NULL), '[]') AS files
              FROM messages m
              LEFT JOIN message_files mf ON mf.message_id = m.id
              LEFT JOIN files f ON f.id = mf.file_id
             WHERE m.conversation_id = CAST(:conversation_id AS uuid) AND m.deleted_at IS NULL
             GROUP BY m.id ORDER BY m.created_at
        """), {"conversation_id": str(conversation_id)}).mappings().all()
        db.execute(text("UPDATE admin.sensitive_access_grants SET last_used_at = now() WHERE admin_account_id = CAST(:account_id AS uuid) AND resource_type = 'conversation' AND resource_id = :resource_id AND expires_at > now()"), {"account_id": str(actor.id), "resource_id": str(conversation_id)})
        write_audit(db, actor_id=actor.id, action="sensitive_access.used", resource_type="conversation", resource_id=str(conversation_id), request=request)
        db.commit()
    else:
        messages = db.execute(text("""
            SELECT m.id::text AS id, m.sender_type, m.message_type, m.status, m.created_at,
                   CASE WHEN m.sender_type = 'assistant' THEN LEFT(m.content, 220) ELSE '已脱敏用户内容' END AS content,
                   '[]'::json AS files
              FROM messages m
             WHERE m.conversation_id = CAST(:conversation_id AS uuid) AND m.deleted_at IS NULL
             ORDER BY m.created_at
        """), {"conversation_id": str(conversation_id)}).mappings().all()
    analyses = db.execute(text("""
        SELECT id::text AS id, status, model_id, analysis_text, error_message, created_at, updated_at
          FROM diagnosis_multimodal_analyses WHERE conversation_id = CAST(:conversation_id AS uuid)
         ORDER BY created_at DESC
    """), {"conversation_id": str(conversation_id)}).mappings().all()
    review_task = db.execute(text("""
        SELECT wi.id::text AS id, wi.status, wi.priority, wi.due_at,
               COALESCE(aa.display_name, aa.email) AS assignee_name
          FROM admin.work_items wi
          LEFT JOIN admin.admin_accounts aa ON aa.id = wi.assignee_id
         WHERE wi.resource_type = 'diagnosis_conversation' AND wi.resource_id = :conversation_id
           AND wi.status IN ('open', 'claimed')
         ORDER BY wi.created_at DESC LIMIT 1
    """), {"conversation_id": str(conversation_id)}).mappings().first()
    reviews = db.execute(text("""
        SELECT id::text AS id, reviewer_name_snapshot, status, risk_level, conclusion, recommendation, evidence, version, published_at, created_at
          FROM admin.expert_reviews WHERE conversation_id = CAST(:conversation_id AS uuid)
         ORDER BY version DESC
    """), {"conversation_id": str(conversation_id)}).mappings().all()
    return {"conversation": dict(conversation), "messages": [dict(row) for row in messages], "multimodal_analyses": [dict(row) for row in analyses], "expert_reviews": [dict(row) for row in reviews], "review_task": dict(review_task) if review_task else None, "sensitive": sensitive}


@router.post("/diagnosis/reviews/{conversation_id}")
def publish_diagnosis_review(
    conversation_id: UUID,
    payload: ExpertReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("diagnosis.review")),
) -> dict:
    context = db.execute(text("SELECT user_id::text AS user_id FROM conversations WHERE id = CAST(:conversation_id AS uuid)"), {"conversation_id": str(conversation_id)}).mappings().first()
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问诊不存在")
    version = int(db.execute(text("SELECT COALESCE(max(version), 0) + 1 FROM admin.expert_reviews WHERE conversation_id = CAST(:conversation_id AS uuid)"), {"conversation_id": str(conversation_id)}).scalar() or 1)
    if payload.publish:
        db.execute(text("UPDATE admin.expert_reviews SET status = 'superseded', updated_at = now() WHERE conversation_id = CAST(:conversation_id AS uuid) AND status = 'published'"), {"conversation_id": str(conversation_id)})
    review = ExpertReview(
        conversation_id=conversation_id,
        source_message_id=UUID(payload.source_message_id) if payload.source_message_id else None,
        diagnosis_id=UUID(payload.diagnosis_id) if payload.diagnosis_id else None,
        user_id=UUID(context["user_id"]), reviewer_id=actor.id, reviewer_name_snapshot=actor.display_name,
        status="published" if payload.publish else "draft", risk_level=payload.risk_level, conclusion=payload.conclusion.strip(), recommendation=payload.recommendation.strip(), evidence=payload.evidence, version=version, published_at=now_utc() if payload.publish else None,
    )
    db.add(review)
    db.flush()
    completed_work_items = 0
    if payload.publish:
        completed_work_items = complete_work_items_for_resource(db, actor_id=actor.id, resource_type="diagnosis_conversation", resource_id=str(conversation_id))
    write_audit(db, actor_id=actor.id, action="diagnosis.expert_review_published" if payload.publish else "diagnosis.expert_review_drafted", resource_type="expert_review", resource_id=str(review.id), request=request, reason=payload.reason, after_data={"conversation_id": str(conversation_id), "risk_level": payload.risk_level, "version": version, "completed_work_items": completed_work_items})
    db.commit()
    return _review_dict(review)


@router.get("/diagnosis/quality")
def diagnosis_quality(db: Session = Depends(get_db), actor: AdminActor = Depends(require_permission("diagnosis.read"))) -> dict:
    rows = db.execute(text("""
        SELECT date_trunc('day', m.created_at) AS day,
               count(*) FILTER (WHERE m.sender_type = 'assistant') AS assistant_messages,
               count(*) FILTER (WHERE m.sender_type = 'assistant' AND m.status = 'error') AS failed_messages,
               count(*) FILTER (WHERE m.metadata ? 'feedback') AS feedback_count
          FROM messages m WHERE m.created_at >= now() - interval '14 days'
         GROUP BY day ORDER BY day
    """)).mappings().all()
    feedback_rows = db.execute(text("""
        SELECT COALESCE(m.metadata->>'feedback', 'none') AS feedback, count(*) AS count
          FROM messages m WHERE m.sender_type = 'assistant' AND m.metadata ? 'feedback'
         GROUP BY COALESCE(m.metadata->>'feedback', 'none') ORDER BY count DESC
    """)).mappings().all()
    totals = db.execute(text("""
        SELECT count(*) FILTER (WHERE sender_type = 'assistant') AS assistant_messages,
               count(*) FILTER (WHERE sender_type = 'assistant' AND status = 'error') AS failed_messages,
               count(*) FILTER (WHERE sender_type = 'assistant' AND metadata ? 'feedback') AS feedback_messages
          FROM messages WHERE created_at >= now() - interval '14 days'
    """)).mappings().one()
    assistant_messages = int(totals["assistant_messages"] or 0)
    return {"daily": [dict(row) for row in rows], "feedback": [dict(row) for row in feedback_rows], "summary": {"assistant_messages": assistant_messages, "failed_messages": int(totals["failed_messages"] or 0), "feedback_messages": int(totals["feedback_messages"] or 0), "failure_rate": round(int(totals["failed_messages"] or 0) * 100 / assistant_messages, 1) if assistant_messages else 0}}


@router.get("/multimodal-jobs")
def multimodal_jobs(
    job_status: str | None = Query(default=None, alias="status", pattern="^(pending|running|completed|failed)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("diagnosis.read")),
) -> dict:
    condition = "TRUE" if not job_status else "dma.status = :status"
    values = {"status": job_status, "limit": page_size, "offset": (page - 1) * page_size}
    total = int(db.execute(text(f"SELECT count(*) FROM diagnosis_multimodal_analyses dma WHERE {condition}"), values).scalar() or 0)
    rows = db.execute(text(f"""
        SELECT dma.id::text AS id, dma.conversation_id::text AS conversation_id, dma.message_id::text AS message_id,
               dma.file_ids, dma.status, dma.model_id, dma.analysis_text, dma.error_message, dma.created_at, dma.updated_at,
               c.title AS conversation_title, COALESCE(u.display_name, u.username, '未命名用户') AS user_name,
               jsonb_array_length(COALESCE(dma.file_ids, '[]'::jsonb)) AS file_count
          FROM diagnosis_multimodal_analyses dma
          LEFT JOIN conversations c ON c.id = dma.conversation_id
          LEFT JOIN users u ON u.id = c.user_id
         WHERE {condition}
         ORDER BY dma.created_at DESC LIMIT :limit OFFSET :offset
    """), values).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/husbandry/overview")
def husbandry_overview(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("husbandry.read")),
) -> dict:
    _sync_husbandry_review_tasks(db)
    joins = """
      LEFT JOIN LATERAL (
         SELECT id, status, risk_level, published_at FROM admin.expert_reviews er
          WHERE er.husbandry_case_id = hc.id ORDER BY er.version DESC LIMIT 1
      ) latest_review ON TRUE
      LEFT JOIN LATERAL (
         SELECT id, observed_on, next_follow_up_on FROM husbandry_case_follow_ups hcf
          WHERE hcf.case_id = hc.id ORDER BY hcf.observed_on DESC, hcf.created_at DESC LIMIT 1
      ) latest_follow_up ON TRUE
      LEFT JOIN LATERAL (
         SELECT status, priority, assignee_id::text AS assignee_id, due_at FROM admin.work_items wi
          WHERE wi.resource_type = 'husbandry_case' AND wi.resource_id = hc.id::text
            AND wi.status IN ('open', 'claimed')
          ORDER BY wi.created_at DESC LIMIT 1
      ) review_task ON TRUE
    """
    summary = db.execute(text(f"""
        SELECT
            count(*) FILTER (WHERE hc.status <> 'closed') AS active_cases,
            count(*) FILTER (WHERE hc.status <> 'closed' AND (latest_review.id IS NULL OR latest_review.status = 'draft')) AS awaiting_review,
            count(*) FILTER (WHERE hc.status <> 'closed' AND hc.severity IN ('high', 'critical')) AS high_risk_open,
            count(*) FILTER (WHERE hc.status = 'processing' AND (latest_follow_up.id IS NULL OR latest_follow_up.next_follow_up_on IS NULL)) AS follow_up_unscheduled,
            count(*) FILTER (WHERE hc.status <> 'closed' AND latest_follow_up.next_follow_up_on <= current_date) AS follow_up_due,
            count(*) FILTER (WHERE hc.status = 'closed' AND hc.closed_at >= date_trunc('day', now()) - interval '6 days') AS closed_7d,
            count(*) FILTER (WHERE review_task.status IN ('open', 'claimed')) AS queued_reviews
          FROM husbandry_cases hc
          {joins}
    """)).mappings().one()
    attention = db.execute(text(f"""
        SELECT hc.id::text AS case_id, hc.title, hc.status, hc.severity, hc.occurred_on, hc.updated_at,
               f.name AS farm_name, sb.batch_code,
               latest_review.status AS review_status,
               latest_follow_up.next_follow_up_on,
               review_task.status AS work_item_status, review_task.priority AS work_item_priority,
               COALESCE(assignee.display_name, assignee.email) AS work_item_assignee
          FROM husbandry_cases hc
          JOIN farms f ON f.id = hc.farm_id
          LEFT JOIN silkworm_batches sb ON sb.id = hc.batch_id
          {joins}
          LEFT JOIN admin.admin_accounts assignee ON assignee.id::text = review_task.assignee_id
         WHERE hc.status <> 'closed'
           AND (
              hc.severity IN ('high', 'critical')
              OR latest_follow_up.next_follow_up_on <= current_date
              OR (hc.status = 'processing' AND (latest_follow_up.id IS NULL OR latest_follow_up.next_follow_up_on IS NULL))
           )
         ORDER BY CASE hc.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                  CASE WHEN latest_follow_up.next_follow_up_on <= current_date THEN 0 ELSE 1 END,
                  hc.updated_at DESC
         LIMIT 8
    """)).mappings().all()
    return {
        "summary": {key: int(value or 0) for key, value in summary.items()},
        "attention": [dict(item) for item in attention],
    }


@router.get("/husbandry/cases")
def husbandry_cases(
    case_status: str = Query(default="open", alias="status", pattern="^(open|all|needs_more_info|suspected|processing|closed)$"),
    severity: str | None = Query(default=None, pattern="^(low|medium|high|critical)$"),
    follow_up: str | None = Query(default=None, pattern="^(due|unscheduled)$"),
    high_risk: bool = Query(default=False),
    created_since: str | None = Query(default=None, pattern="^(today|7d)$"),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("husbandry.read")),
) -> dict:
    _sync_husbandry_review_tasks(db)
    clauses = ["TRUE"]
    values: dict[str, object] = {"limit": page_size, "offset": (page - 1) * page_size}
    if case_status == "open":
        clauses.append("hc.status <> 'closed'")
    elif case_status != "all":
        clauses.append("hc.status = :status")
        values["status"] = case_status
    if high_risk:
        clauses.append("hc.severity IN ('high', 'critical')")
    elif severity:
        clauses.append("hc.severity = :severity")
        values["severity"] = severity
    if follow_up == "due":
        clauses.append("latest_follow_up.next_follow_up_on <= current_date")
    elif follow_up == "unscheduled":
        clauses.append("hc.status = 'processing' AND (latest_follow_up.id IS NULL OR latest_follow_up.next_follow_up_on IS NULL)")
    if created_since == "today":
        clauses.append("hc.created_at >= date_trunc('day', now())")
    elif created_since == "7d":
        clauses.append("hc.created_at >= now() - interval '7 days'")
    if q and q.strip():
        clauses.append("(hc.title ILIKE :query OR COALESCE(hc.suspected_disease, '') ILIKE :query OR COALESCE(hc.symptom_summary, '') ILIKE :query OR COALESCE(f.name, '') ILIKE :query OR COALESCE(u.display_name, '') ILIKE :query OR COALESCE(u.username, '') ILIKE :query)")
        values["query"] = f"%{q.strip()}%"
    where = " AND ".join(clauses)
    joins = """
      JOIN users u ON u.id = hc.owner_id
      JOIN farms f ON f.id = hc.farm_id
      LEFT JOIN silkworm_batches sb ON sb.id = hc.batch_id
      LEFT JOIN LATERAL (
         SELECT id, status, risk_level, published_at FROM admin.expert_reviews er
          WHERE er.husbandry_case_id = hc.id ORDER BY er.version DESC LIMIT 1
      ) latest_review ON TRUE
      LEFT JOIN LATERAL (
         SELECT id, observed_on, next_follow_up_on FROM husbandry_case_follow_ups hcf
          WHERE hcf.case_id = hc.id ORDER BY hcf.observed_on DESC, hcf.created_at DESC LIMIT 1
      ) latest_follow_up ON TRUE
      LEFT JOIN LATERAL (
         SELECT id::text AS id, status, priority, assignee_id::text AS assignee_id, due_at FROM admin.work_items wi
          WHERE wi.resource_type = 'husbandry_case' AND wi.resource_id = hc.id::text
            AND wi.status IN ('open', 'claimed')
          ORDER BY wi.created_at DESC LIMIT 1
      ) review_task ON TRUE
      LEFT JOIN admin.admin_accounts task_assignee ON task_assignee.id::text = review_task.assignee_id
    """
    total = int(db.execute(text(f"SELECT count(*) FROM husbandry_cases hc {joins} WHERE {where}"), values).scalar() or 0)
    rows = db.execute(text(f"""
        SELECT hc.id::text AS id, hc.title, hc.occurred_on, hc.suspected_disease, hc.severity, hc.status,
               hc.source_conversation_id::text AS source_conversation_id, f.name AS farm_name, sb.batch_code, sb.instar,
               COALESCE(u.display_name, u.username, '未命名用户') AS user_name,
               latest_review.status AS review_status, latest_review.risk_level AS review_risk_level,
               latest_follow_up.observed_on AS last_follow_up_on, latest_follow_up.next_follow_up_on,
               COALESCE(latest_follow_up.next_follow_up_on <= current_date, false) AS follow_up_due,
               review_task.id AS work_item_id, review_task.status AS work_item_status,
               review_task.priority AS work_item_priority, review_task.due_at AS work_item_due_at,
               COALESCE(task_assignee.display_name, task_assignee.email) AS work_item_assignee,
               hc.created_at, hc.updated_at
          FROM husbandry_cases hc {joins}
         WHERE {where}
         ORDER BY CASE hc.severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END,
                  CASE WHEN latest_follow_up.next_follow_up_on <= current_date THEN 0 ELSE 1 END,
                  CASE WHEN review_task.status = 'claimed' THEN 0 WHEN review_task.status = 'open' THEN 1 ELSE 2 END,
                  hc.updated_at DESC
         LIMIT :limit OFFSET :offset
    """), values).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/husbandry/cases/{case_id}/queue")
def queue_husbandry_review(
    case_id: UUID,
    payload: HusbandryReviewQueueRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("husbandry.review")),
) -> dict:
    case = db.execute(text("""
        SELECT id::text AS id, title, status, severity FROM husbandry_cases
         WHERE id = CAST(:case_id AS uuid)
    """), {"case_id": str(case_id)}).mappings().first()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="病例不存在")
    if case["status"] == "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="病例已结案，不能再纳入复核")
    active_task = db.scalar(select(WorkItem).where(
        WorkItem.resource_type == "husbandry_case",
        WorkItem.resource_id == str(case_id),
        WorkItem.status.in_(("open", "claimed")),
    ).order_by(WorkItem.created_at.desc()))
    priority = payload.risk_level
    priority_rank = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    if active_task is not None:
        before = {"priority": active_task.priority, "status": active_task.status, "version": active_task.version}
        if priority_rank[priority] > priority_rank.get(active_task.priority, 2):
            active_task.priority = priority
        active_task.version += 1
        active_task.updated_at = now_utc()
        write_audit(db, actor_id=actor.id, action="husbandry.review_queue_updated", resource_type="work_item", resource_id=str(active_task.id), request=request, reason=payload.reason, before_data=before, after_data={"priority": active_task.priority, "status": active_task.status, "case_id": str(case_id), "version": active_task.version})
        db.commit()
        return {"id": str(active_task.id), "status": active_task.status, "priority": active_task.priority, "created": False}
    high_risk_sla, standard_sla = work_item_sla_hours(db)
    task = WorkItem(
        item_type="husbandry_review",
        resource_type="husbandry_case",
        resource_id=str(case_id),
        title=f"专家复核病例：{case['title']}",
        priority=priority,
        due_at=now_utc() + timedelta(hours=high_risk_sla if priority in {"high", "critical"} else standard_sla),
        metadata_={"source": "husbandry_console", "risk_level": priority},
    )
    db.add(task)
    try:
        db.flush()
    except IntegrityError:
        # A simultaneous queue operation must resolve to the active task
        # instead of producing a duplicate review request.
        db.rollback()
        active_task = db.scalar(select(WorkItem).where(
            WorkItem.resource_type == "husbandry_case",
            WorkItem.resource_id == str(case_id),
            WorkItem.status.in_(("open", "claimed")),
        ).order_by(WorkItem.created_at.desc()))
        if active_task is not None:
            return {"id": str(active_task.id), "status": active_task.status, "priority": active_task.priority, "created": False}
        raise
    write_audit(db, actor_id=actor.id, action="husbandry.review_queued", resource_type="work_item", resource_id=str(task.id), request=request, reason=payload.reason, after_data={"case_id": str(case_id), "priority": priority, "due_at": task.due_at.isoformat() if task.due_at else None})
    db.commit()
    return {"id": str(task.id), "status": task.status, "priority": task.priority, "created": True}


@router.get("/husbandry/cases/{case_id}")
def husbandry_case_detail(
    case_id: UUID,
    request: Request,
    include_sensitive: bool = Query(default=False),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("husbandry.read")),
) -> dict:
    _sync_husbandry_review_tasks(db)
    row = db.execute(text("""
        SELECT hc.id::text AS id, hc.title, hc.occurred_on, hc.suspected_disease, hc.severity, hc.status, hc.closed_at,
               hc.symptom_summary, hc.diagnosis_summary, hc.recommendation, hc.source_conversation_id::text AS source_conversation_id,
               f.name AS farm_name, sb.batch_code, sb.variety, sb.instar, COALESCE(u.display_name, u.username, '未命名用户') AS user_name
          FROM husbandry_cases hc JOIN users u ON u.id = hc.owner_id JOIN farms f ON f.id = hc.farm_id
          LEFT JOIN silkworm_batches sb ON sb.id = hc.batch_id WHERE hc.id = CAST(:case_id AS uuid)
    """), {"case_id": str(case_id)}).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="病例不存在")
    sensitive = include_sensitive and _has_sensitive_grant(db, actor.id, "husbandry_case", str(case_id))
    if include_sensitive and not sensitive:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请先申请临时查看原文授权")
    if sensitive:
        db.execute(text("UPDATE admin.sensitive_access_grants SET last_used_at = now() WHERE admin_account_id = CAST(:account_id AS uuid) AND resource_type = 'husbandry_case' AND resource_id = :resource_id AND expires_at > now()"), {"account_id": str(actor.id), "resource_id": str(case_id)})
        write_audit(db, actor_id=actor.id, action="sensitive_access.used", resource_type="husbandry_case", resource_id=str(case_id), request=request)
        db.commit()
    result = dict(row)
    if not sensitive:
        for field in ("symptom_summary", "diagnosis_summary", "recommendation"):
            result[field] = "已脱敏病例内容"
    follow_ups = db.execute(text("""
        SELECT id::text AS id, observed_on, action_taken, note, affected_count, death_count, next_follow_up_on, created_at
          FROM husbandry_case_follow_ups WHERE case_id = CAST(:case_id AS uuid) ORDER BY observed_on DESC, created_at DESC
    """), {"case_id": str(case_id)}).mappings().all()
    reviews = db.execute(text("""
        SELECT id::text AS id, reviewer_name_snapshot, status, risk_level, conclusion, recommendation, evidence, version, published_at, created_at
          FROM admin.expert_reviews WHERE husbandry_case_id = CAST(:case_id AS uuid) ORDER BY version DESC
    """), {"case_id": str(case_id)}).mappings().all()
    assets = db.execute(text("""
        SELECT hra.id::text AS id, f.file_name, f.file_type, f.file_size,
               CASE WHEN :sensitive THEN f.storage_url ELSE NULL END AS storage_url,
               hra.created_at
          FROM husbandry_record_assets hra JOIN files f ON f.id = hra.file_id
         WHERE hra.case_id = CAST(:case_id AS uuid) AND f.deleted_at IS NULL
         ORDER BY hra.created_at ASC
    """), {"case_id": str(case_id), "sensitive": sensitive}).mappings().all()
    review_task = db.execute(text("""
        SELECT wi.id::text AS id, wi.status, wi.priority, wi.due_at,
               COALESCE(aa.display_name, aa.email) AS assignee_name
          FROM admin.work_items wi
          LEFT JOIN admin.admin_accounts aa ON aa.id = wi.assignee_id
         WHERE wi.resource_type = 'husbandry_case' AND wi.resource_id = :case_id
           AND wi.status IN ('open', 'claimed')
         ORDER BY wi.created_at DESC LIMIT 1
    """), {"case_id": str(case_id)}).mappings().first()
    return {"case": result, "follow_ups": [dict(item) for item in follow_ups], "assets": [dict(item) for item in assets], "expert_reviews": [dict(item) for item in reviews], "review_task": dict(review_task) if review_task else None, "sensitive": sensitive}


@router.post("/husbandry/cases/{case_id}/review")
def publish_husbandry_review(
    case_id: UUID,
    payload: HusbandryReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("husbandry.review")),
) -> dict:
    # The row lock plus expected_version makes one review revision a single
    # ordered decision. A stale browser may not silently supersede a newer
    # expert opinion.
    context = db.execute(text("SELECT owner_id::text AS user_id, status, severity FROM husbandry_cases WHERE id = CAST(:case_id AS uuid) FOR UPDATE"), {"case_id": str(case_id)}).mappings().first()
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="病例不存在")
    if context["status"] == "closed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="病例已结案，不能再发布复核意见")
    latest = db.execute(text("""
        SELECT id::text AS id, status, version
          FROM admin.expert_reviews
         WHERE husbandry_case_id = CAST(:case_id AS uuid)
         ORDER BY version DESC
         LIMIT 1
         FOR UPDATE
    """), {"case_id": str(case_id)}).mappings().first()
    latest_version = int(latest["version"]) if latest else 0
    if payload.expected_version != latest_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="病例复核已被其他管理员更新，请刷新后确认最新版本再提交")
    version = latest_version if latest and latest["status"] == "draft" else latest_version + 1
    if payload.publish:
        db.execute(text("UPDATE admin.expert_reviews SET status = 'superseded', updated_at = now() WHERE husbandry_case_id = CAST(:case_id AS uuid) AND status = 'published'"), {"case_id": str(case_id)})
    review = db.get(ExpertReview, UUID(latest["id"])) if latest and latest["status"] == "draft" else None
    if review is None:
        review = ExpertReview(
            husbandry_case_id=case_id,
            user_id=UUID(context["user_id"]),
            reviewer_id=actor.id,
            reviewer_name_snapshot=actor.display_name,
            version=version,
        )
    review.reviewer_id = actor.id
    review.reviewer_name_snapshot = actor.display_name
    review.status = "published" if payload.publish else "draft"
    review.risk_level = payload.risk_level
    review.conclusion = payload.conclusion.strip()
    review.recommendation = payload.recommendation.strip()
    review.evidence = payload.evidence
    review.published_at = now_utc() if payload.publish else None
    review.updated_at = now_utc()
    db.add(review)
    db.flush()
    completed_work_items = 0
    transitioned_to_processing = False
    if payload.publish:
        if context["status"] != "closed":
            db.execute(text("""
                UPDATE husbandry_cases
                   SET status = 'processing', severity = :risk_level,
                       diagnosis_summary = :conclusion, recommendation = :recommendation,
                       updated_at = now(), closed_at = NULL
                 WHERE id = CAST(:case_id AS uuid)
            """), {"case_id": str(case_id), "risk_level": payload.risk_level, "conclusion": payload.conclusion.strip(), "recommendation": payload.recommendation.strip()})
            transitioned_to_processing = True
        completed_work_items = complete_work_items_for_resource(db, actor_id=actor.id, resource_type="husbandry_case", resource_id=str(case_id))
        _create_husbandry_review_notification(
            db,
            user_id=context["user_id"],
            case_id=case_id,
            review_id=review.id,
            version=version,
            conclusion=review.conclusion,
        )
    write_audit(db, actor_id=actor.id, action="husbandry.expert_review_published" if payload.publish else "husbandry.expert_review_drafted", resource_type="expert_review", resource_id=str(review.id), request=request, reason=payload.reason, after_data={"case_id": str(case_id), "risk_level": payload.risk_level, "version": version, "evidence_count": len(payload.evidence), "transitioned_to_processing": transitioned_to_processing, "completed_work_items": completed_work_items})
    db.commit()
    return _review_dict(review)


def _has_sensitive_grant(db: Session, account_id: UUID, resource_type: str, resource_id: str) -> bool:
    return db.scalar(select(SensitiveAccessGrant.id).where(SensitiveAccessGrant.admin_account_id == account_id, SensitiveAccessGrant.resource_type == resource_type, SensitiveAccessGrant.resource_id == resource_id, SensitiveAccessGrant.expires_at > now_utc())) is not None


def _create_husbandry_review_notification(
    db: Session,
    *,
    user_id: str,
    case_id: UUID,
    review_id: UUID,
    version: int,
    conclusion: str,
) -> None:
    """Deliver the published expert result through the existing user notification inbox."""
    summary = " ".join(conclusion.split())[:100]
    db.execute(text("""
        INSERT INTO community_notifications (user_id, notification_type, payload)
        VALUES (CAST(:user_id AS uuid), 'moderation', CAST(:payload AS jsonb))
    """), {
        "user_id": user_id,
        "payload": json.dumps({
            "message": f"专家已发布养殖病例复核意见：{summary}。请完成处置后补充一次随访，再结案。",
            "case_id": str(case_id),
            "review_id": str(review_id),
            "review_version": version,
            "kind": "husbandry_expert_review",
        }, ensure_ascii=False),
    })


def _sync_husbandry_review_tasks(db: Session) -> None:
    """Create the high-risk review tasks even when the workbench was not opened first."""
    candidates = db.execute(text("""
        SELECT hc.id::text AS id, hc.title, hc.severity
          FROM husbandry_cases hc
         WHERE hc.status <> 'closed'
           AND hc.severity IN ('high', 'critical')
           AND NOT EXISTS (
               SELECT 1 FROM admin.expert_reviews er
                WHERE er.husbandry_case_id = hc.id AND er.status = 'published'
           )
    """)).mappings().all()
    if not candidates:
        return
    high_risk_sla, _ = work_item_sla_hours(db)
    now = now_utc()
    created = False
    for candidate in candidates:
        exists = db.scalar(select(WorkItem.id).where(
            WorkItem.resource_type == "husbandry_case",
            WorkItem.resource_id == candidate["id"],
            WorkItem.status.in_(("open", "claimed")),
        ))
        if exists is not None:
            continue
        db.add(WorkItem(
            item_type="high_risk_case",
            resource_type="husbandry_case",
            resource_id=candidate["id"],
            title=f"复核高风险养殖病例：{candidate['title']}",
            priority="critical" if candidate["severity"] == "critical" else "high",
            due_at=now + timedelta(hours=high_risk_sla),
            metadata_={"source": "husbandry_case_risk", "risk_level": candidate["severity"]},
        ))
        created = True
    if created:
        db.commit()




def _review_dict(review: ExpertReview) -> dict:
    return {"id": str(review.id), "conversation_id": str(review.conversation_id) if review.conversation_id else None, "husbandry_case_id": str(review.husbandry_case_id) if review.husbandry_case_id else None, "status": review.status, "risk_level": review.risk_level, "conclusion": review.conclusion, "recommendation": review.recommendation, "evidence": review.evidence, "version": review.version, "published_at": review.published_at, "created_at": review.created_at}

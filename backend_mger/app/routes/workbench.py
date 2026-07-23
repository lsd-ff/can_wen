from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import get_actor, require_permission
from app.models import AdminAccount, AuditLog, WorkItem
from app.schemas import WorkItemBatchClaimRequest, WorkItemPatchRequest, WorkItemTransferRequest
from app.security import now_utc
from app.services import AdminActor, get_roles_and_permissions, work_item_sla_hours, write_audit


router = APIRouter(tags=["workbench"])


@router.get("/me")
def me(actor: AdminActor = Depends(get_actor)) -> dict:
    return {"id": str(actor.id), "email": actor.email, "display_name": actor.display_name, "roles": actor.roles, "permissions": sorted(actor.permissions), "mfa_enrolled": actor.mfa_enrolled}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), actor: AdminActor = Depends(require_permission("dashboard.read"))) -> dict:
    _sync_work_items(db)
    can_users = "users.read" in actor.permissions
    can_community = "community.read" in actor.permissions
    can_diagnosis = "diagnosis.read" in actor.permissions
    can_husbandry = "husbandry.read" in actor.permissions
    can_work_items = "work_items.read" in actor.permissions
    metrics = {
        "new_users_today": _scalar(db, "SELECT count(*) FROM users WHERE created_at >= date_trunc('day', now())") if can_users else 0,
        "active_users_7d": _scalar(db, "SELECT count(*) FROM users WHERE last_seen_at >= now() - interval '7 days'") if can_users else 0,
        "conversations_today": _scalar(db, "SELECT count(*) FROM conversations WHERE created_at >= date_trunc('day', now())") if can_diagnosis else 0,
        "community_posts_today": _scalar(db, "SELECT count(*) FROM community_posts WHERE published_at >= date_trunc('day', now()) AND status = 'published'") if can_community else 0,
        "pending_reports": _scalar(db, "SELECT count(*) FROM community_reports WHERE status = 'pending'") if can_community else 0,
        "pending_verifications": _scalar(db, "SELECT count(*) FROM community_profiles WHERE verification_status = 'pending'") if can_community else 0,
        "high_risk_cases": _scalar(db, "SELECT count(*) FROM husbandry_cases WHERE status != 'closed' AND severity IN ('high', 'critical')") if can_husbandry else 0,
        "failed_multimodal_jobs": _scalar(db, "SELECT count(*) FROM diagnosis_multimodal_analyses WHERE status = 'failed' AND updated_at >= now() - interval '24 hours'") if can_diagnosis else 0,
        "open_work_items": _scalar(db, "SELECT count(*) FROM admin.work_items WHERE status IN ('open', 'claimed')") if can_work_items else 0,
    }
    task_summary = dict(db.execute(text("""
        SELECT
            count(*) FILTER (WHERE status = 'claimed' AND assignee_id = CAST(:actor_id AS uuid)) AS my_claimed,
            count(*) FILTER (WHERE status IN ('open', 'claimed') AND due_at < now()) AS overdue,
            count(*) FILTER (WHERE status IN ('open', 'claimed') AND due_at >= now() AND due_at < now() + interval '4 hours') AS due_soon,
            count(*) FILTER (WHERE status = 'open') AS unclaimed
          FROM admin.work_items
    """), {"actor_id": str(actor.id)}).mappings().one()) if can_work_items else {"my_claimed": 0, "overdue": 0, "due_soon": 0, "unclaimed": 0}
    task_summary = {key: int(value or 0) for key, value in task_summary.items()}
    trend_rows = db.execute(text("""
        SELECT day::date AS day,
               (SELECT count(*) FROM users u WHERE u.created_at >= day AND u.created_at < day + interval '1 day') AS users,
               (SELECT count(*) FROM conversations c WHERE c.created_at >= day AND c.created_at < day + interval '1 day') AS conversations,
               (SELECT count(*) FROM husbandry_cases hc WHERE hc.created_at >= day AND hc.created_at < day + interval '1 day') AS cases,
               (SELECT count(*) FROM community_posts cp WHERE cp.published_at >= day AND cp.published_at < day + interval '1 day' AND cp.status = 'published') AS posts
          FROM generate_series(current_date - interval '6 days', current_date, interval '1 day') AS day
         ORDER BY day
    """)).mappings().all()
    trend = [{
        **dict(row),
        "users": int(row["users"] or 0) if can_users else 0,
        "conversations": int(row["conversations"] or 0) if can_diagnosis else 0,
        "cases": int(row["cases"] or 0) if can_husbandry else 0,
        "posts": int(row["posts"] or 0) if can_community else 0,
    } for row in trend_rows]
    period_comparison = dict(db.execute(text("""
        SELECT
            count(*) FILTER (WHERE created_at >= current_date - interval '6 days') AS users_current,
            count(*) FILTER (WHERE created_at >= current_date - interval '13 days' AND created_at < current_date - interval '6 days') AS users_previous
          FROM users
    """)).mappings().one()) if can_users else {"users_current": 0, "users_previous": 0}
    alerts: list[dict] = []
    if can_work_items and task_summary["overdue"]:
        alerts.append({"level": "critical", "title": "待办已超时", "detail": f"{task_summary['overdue']} 项待办已超过 SLA", "target": "/queue?status=active"})
    if can_work_items and task_summary["due_soon"]:
        alerts.append({"level": "high", "title": "待办即将到期", "detail": f"{task_summary['due_soon']} 项将在 4 小时内到期", "target": "/queue?status=active"})
    if can_husbandry and metrics["high_risk_cases"]:
        alerts.append({"level": "high", "title": "高风险养殖病例", "detail": f"{metrics['high_risk_cases']} 例需要专家复核", "target": "/husbandry?high_risk=true"})
    if can_diagnosis and metrics["failed_multimodal_jobs"]:
        alerts.append({"level": "medium", "title": "多模态分析失败", "detail": f"{metrics['failed_multimodal_jobs']} 项任务在近 24 小时失败", "target": "/diagnosis?tab=jobs&job_status=failed"})
    lifecycle = []
    if can_users:
        lifecycle.append({"key": "registration", "label": "注册", "value": metrics["new_users_today"], "issue_count": 0})
    if can_diagnosis:
        lifecycle.append({"key": "diagnosis", "label": "问诊", "value": metrics["conversations_today"], "issue_count": metrics["failed_multimodal_jobs"]})
    if can_husbandry:
        lifecycle.extend([
            {"key": "case", "label": "病例", "value": _scalar(db, "SELECT count(*) FROM husbandry_cases WHERE created_at >= date_trunc('day', now())"), "issue_count": metrics["high_risk_cases"]},
            {"key": "follow_up", "label": "随访", "value": _scalar(db, "SELECT count(*) FROM husbandry_case_follow_ups WHERE created_at >= date_trunc('day', now())"), "issue_count": _scalar(db, "SELECT count(*) FROM husbandry_case_follow_ups WHERE next_follow_up_on < current_date")},
        ])
    if can_community:
        lifecycle.append({"key": "community", "label": "社区", "value": metrics["community_posts_today"], "issue_count": metrics["pending_reports"]})
    recent_items = [_work_item_dict(item) for item in db.scalars(select(WorkItem).where(WorkItem.status.in_(("open", "claimed"))).order_by(WorkItem.created_at.desc()).limit(8)).all()] if can_work_items else []
    return {
        "metrics": metrics,
        "task_summary": task_summary,
        "alerts": alerts,
        "trend": [dict(row) for row in trend],
        "period_comparison": {key: int(value or 0) for key, value in period_comparison.items()},
        "lifecycle": lifecycle,
        "work_items": recent_items,
        "generated_at": now_utc(),
    }


@router.get("/work-items")
def work_items(
    status_filter: str = Query(default="open", alias="status", pattern="^(open|claimed|completed|cancelled|active|all)$"),
    priority: str | None = Query(default=None, pattern="^(low|medium|high|critical)$"),
    assignee: str | None = Query(default=None, pattern="^(me|unassigned)$"),
    resource_type: str | None = Query(default=None, pattern="^(community_report|community_profile|husbandry_case|diagnosis_conversation)$"),
    sla: str | None = Query(default=None, pattern="^(overdue|due_soon|on_track)$"),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("work_items.read")),
) -> dict:
    _sync_work_items(db)
    query = select(WorkItem)
    count_query = select(WorkItem)
    filters = []
    if status_filter == "active":
        filters.append(WorkItem.status.in_(("open", "claimed")))
    elif status_filter != "all":
        filters.append(WorkItem.status == status_filter)
    if priority:
        filters.append(WorkItem.priority == priority)
    if resource_type:
        filters.append(WorkItem.resource_type == resource_type)
    if assignee == "me":
        filters.append(WorkItem.assignee_id == actor.id)
    elif assignee == "unassigned":
        filters.append(WorkItem.assignee_id.is_(None))
    now = now_utc()
    if sla == "overdue":
        filters.append(WorkItem.due_at < now)
    elif sla == "due_soon":
        filters.extend((WorkItem.due_at >= now, WorkItem.due_at < now + timedelta(hours=4)))
    elif sla == "on_track":
        filters.append(or_(WorkItem.due_at.is_(None), WorkItem.due_at >= now + timedelta(hours=4)))
    if q and q.strip():
        normalized = f"%{q.strip()}%"
        filters.append(or_(WorkItem.title.ilike(normalized), WorkItem.resource_id.ilike(normalized)))
    for predicate in filters:
        query = query.where(predicate)
        count_query = count_query.where(predicate)
    total = len(db.scalars(count_query).all())
    items = db.scalars(query.order_by(WorkItem.due_at.asc().nulls_last(), WorkItem.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": _work_item_dicts_with_assignees(db, items), "total": total, "page": page, "page_size": page_size}


@router.get("/work-items/assignees")
def work_item_assignees(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("work_items.manage")),
) -> dict:
    items: list[dict] = []
    for account in db.scalars(select(AdminAccount).where(AdminAccount.status == "active").order_by(AdminAccount.display_name.asc())).all():
        roles, permissions = get_roles_and_permissions(db, account.id)
        supported = [resource_type for resource_type in ("community_report", "community_profile", "husbandry_case", "diagnosis_conversation") if _can_handle_resource(permissions, resource_type)]
        if supported:
            items.append({"id": str(account.id), "display_name": account.display_name, "email": account.email, "roles": roles, "resource_types": supported})
    return {"items": items, "total": len(items)}


@router.get("/work-items/{item_id}")
def work_item_detail(
    item_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("work_items.read")),
) -> dict:
    _sync_work_items(db)
    item = db.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待办不存在")
    _require_item_reader(actor, item)
    timeline = db.execute(text("""
        SELECT al.id::text AS id, al.action, al.reason, al.resource_type, al.resource_id,
               al.before_data, al.after_data, al.created_at,
               COALESCE(aa.display_name, aa.email, '系统') AS actor_name
          FROM admin.audit_logs al
          LEFT JOIN admin.admin_accounts aa ON aa.id = al.actor_id
         WHERE (al.resource_type = 'work_item' AND al.resource_id = :work_item_id)
            OR (al.resource_type = :resource_type AND al.resource_id = :resource_id)
         ORDER BY al.created_at ASC
         LIMIT 100
    """), {"work_item_id": str(item.id), "resource_type": item.resource_type, "resource_id": item.resource_id}).mappings().all()
    assignee_name = db.scalar(select(AdminAccount.display_name).where(AdminAccount.id == item.assignee_id)) if item.assignee_id else None
    return {"item": _work_item_dict(item, assignee_name=assignee_name), "timeline": [dict(row) for row in timeline]}


@router.post("/work-items/batch-claim")
def batch_claim_work_items(
    payload: WorkItemBatchClaimRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("work_items.manage")),
) -> dict:
    try:
        item_ids = list(dict.fromkeys(UUID(value) for value in payload.item_ids))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="待办标识无效") from error
    items = db.scalars(select(WorkItem).where(WorkItem.id.in_(item_ids))).all()
    if len(items) != len(item_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部分待办不存在或已被移除")
    for item in items:
        _require_item_handler(actor, item)
        if item.status != "open":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="批量领取仅支持未领取待办，请刷新后重试")
    for item in items:
        before = {"status": item.status, "assignee_id": None, "version": item.version}
        item.status, item.assignee_id = "claimed", actor.id
        item.version += 1
        item.updated_at = now_utc()
        write_audit(db, actor_id=actor.id, action="work_item.batch_claim", resource_type="work_item", resource_id=str(item.id), request=request, reason=payload.reason, before_data=before, after_data={"status": item.status, "assignee_id": str(actor.id), "version": item.version})
    db.commit()
    return {"claimed": len(items), "items": [_work_item_dict(item) for item in items]}


@router.post("/work-items/{item_id}/transfer")
def transfer_work_item(
    item_id: UUID,
    payload: WorkItemTransferRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("work_items.manage")),
) -> dict:
    item = db.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待办不存在")
    _require_item_handler(actor, item)
    _require_item_owner_or_admin(actor, item)
    if item.status != "claimed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅处理中待办可以转派")
    try:
        target_id = UUID(payload.target_admin_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="目标管理员标识无效") from error
    if target_id == actor.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="不能转派给自己")
    target = db.get(AdminAccount, target_id)
    if target is None or target.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标管理员不可用")
    _, target_permissions = get_roles_and_permissions(db, target.id)
    if not _can_handle_resource(target_permissions, item.resource_type):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="目标管理员没有处理该业务待办的权限")
    before = {"status": item.status, "assignee_id": str(item.assignee_id), "version": item.version}
    item.assignee_id, item.version, item.updated_at = target.id, item.version + 1, now_utc()
    write_audit(db, actor_id=actor.id, action="work_item.transferred", resource_type="work_item", resource_id=str(item.id), request=request, reason=payload.reason, before_data=before, after_data={"status": item.status, "assignee_id": str(target.id), "assignee_name": target.display_name, "version": item.version})
    db.commit()
    return _work_item_dict(item)


@router.patch("/work-items/{item_id}")
def patch_work_item(
    item_id: UUID,
    payload: WorkItemPatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("work_items.manage")),
) -> dict:
    item = db.get(WorkItem, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待办不存在")
    if item.version != payload.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="待办已被其他管理员更新，请刷新后重试")
    _require_item_handler(actor, item)
    before = {"status": item.status, "assignee_id": str(item.assignee_id) if item.assignee_id else None, "version": item.version}
    if payload.action == "claim":
        if item.status != "open":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="待办已被领取或处理")
        item.status, item.assignee_id = "claimed", actor.id
    elif payload.action == "release":
        _require_item_owner_or_admin(actor, item)
        if item.status != "claimed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅已领取的待办可以释放")
        item.status, item.assignee_id = "open", None
    elif payload.action == "complete":
        _require_item_owner_or_admin(actor, item)
        if item.status != "claimed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先领取待办后再完成")
        if not _resource_is_resolved(db, item):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先在对应业务页面完成审核，待办会自动闭环")
        item.status, item.completed_at = "completed", now_utc()
    else:
        if "admins.manage" not in actor.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只有系统管理员可以取消待办")
        if item.status not in {"open", "claimed"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="待办当前无法取消")
        item.status, item.completed_at = "cancelled", now_utc()
    item.version += 1
    item.updated_at = now_utc()
    write_audit(db, actor_id=actor.id, action=f"work_item.{payload.action}", resource_type="work_item", resource_id=str(item.id), request=request, reason=payload.reason, before_data=before, after_data={"status": item.status, "assignee_id": str(item.assignee_id) if item.assignee_id else None, "version": item.version})
    db.commit()
    return _work_item_dict(item)


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(get_actor),
) -> dict:
    normalized = f"%{q.strip()}%"
    items: list[dict] = []
    if "users.read" in actor.permissions:
        for row in db.execute(text("""
            SELECT id::text AS id, COALESCE(NULLIF(display_name, ''), username, '未命名用户') AS title,
                   status, 'user' AS type
              FROM users
             WHERE display_name ILIKE :query OR username ILIKE :query OR id::text ILIKE :query
             ORDER BY last_seen_at DESC NULLS LAST LIMIT 6
        """), {"query": normalized}).mappings():
            items.append(dict(row))
    if "diagnosis.read" in actor.permissions:
        for row in db.execute(text("""
            SELECT id::text AS id, title, status, 'conversation' AS type
              FROM conversations
             WHERE title ILIKE :query OR id::text ILIKE :query
             ORDER BY last_message_at DESC NULLS LAST LIMIT 6
        """), {"query": normalized}).mappings():
            items.append(dict(row))
    if "community.read" in actor.permissions:
        for row in db.execute(text("""
            SELECT id::text AS id, title, status, 'community_post' AS type
              FROM community_posts
             WHERE title ILIKE :query OR id::text ILIKE :query
             ORDER BY created_at DESC LIMIT 6
        """), {"query": normalized}).mappings():
            items.append(dict(row))
    return {"items": items[:15]}


def _sync_work_items(db: Session) -> None:
    stale_items = db.execute(text("""
        UPDATE admin.work_items wi
           SET status = 'completed',
               completed_at = COALESCE(wi.completed_at, now()),
               updated_at = now(),
               version = wi.version + 1
         WHERE wi.status IN ('open', 'claimed')
           AND (
               (wi.resource_type = 'community_report' AND NOT EXISTS (
                   SELECT 1 FROM community_reports cr
                    WHERE cr.id::text = wi.resource_id AND cr.status = 'pending'
               ))
               OR (wi.resource_type = 'community_profile' AND NOT EXISTS (
                   SELECT 1 FROM community_profiles cp
                    WHERE cp.user_id::text = wi.resource_id AND cp.verification_status = 'pending'
               ))
               OR (wi.resource_type = 'husbandry_case' AND wi.item_type = 'high_risk_case' AND NOT EXISTS (
                   SELECT 1 FROM husbandry_cases hc
                    WHERE hc.id::text = wi.resource_id
                      AND hc.status <> 'closed'
                      AND hc.severity IN ('high', 'critical')
               ))
               OR (wi.resource_type = 'husbandry_case' AND wi.item_type = 'husbandry_review' AND NOT EXISTS (
                   SELECT 1 FROM husbandry_cases hc
                    WHERE hc.id::text = wi.resource_id AND hc.status <> 'closed'
               ))
               OR (wi.resource_type = 'husbandry_case' AND EXISTS (
                   SELECT 1 FROM admin.expert_reviews er
                    WHERE er.husbandry_case_id::text = wi.resource_id AND er.status = 'published'
               ))
               OR (wi.resource_type = 'diagnosis_conversation' AND EXISTS (
                   SELECT 1 FROM admin.expert_reviews er
                    WHERE er.conversation_id::text = wi.resource_id AND er.status = 'published'
               ))
           )
    """)).rowcount
    candidates = db.execute(text("""
        SELECT 'community_report' AS item_type, 'community_report' AS resource_type, id::text AS resource_id,
               '处理社区举报' || ' · ' || reason AS title,
               CASE WHEN reason ILIKE '%隐私%' OR reason ILIKE '%医疗%' THEN 'high' ELSE 'medium' END AS priority,
               created_at
          FROM community_reports WHERE status = 'pending'
        UNION ALL
        SELECT 'verification', 'community_profile', user_id::text,
               '审核专业认证申请', 'medium', updated_at
          FROM community_profiles WHERE verification_status = 'pending'
        UNION ALL
        SELECT 'high_risk_case', 'husbandry_case', id::text,
               '复核高风险养殖病例：' || title,
               CASE WHEN severity = 'critical' THEN 'critical' ELSE 'high' END, created_at
          FROM husbandry_cases hc
         WHERE hc.status != 'closed'
           AND hc.severity IN ('high', 'critical')
           AND NOT EXISTS (
               SELECT 1 FROM admin.expert_reviews er
                WHERE er.husbandry_case_id = hc.id AND er.status = 'published'
           )
    """)).mappings().all()
    now = now_utc()
    high_risk_sla_hours, standard_sla_hours = work_item_sla_hours(db)
    changed = bool(stale_items)
    for row in candidates:
        existing = db.scalar(select(WorkItem).where(WorkItem.resource_type == row["resource_type"], WorkItem.resource_id == row["resource_id"], WorkItem.status.in_(("open", "claimed"))))
        if existing is None:
            sla_hours = high_risk_sla_hours if row["priority"] in {"high", "critical"} else standard_sla_hours
            db.add(WorkItem(item_type=row["item_type"], resource_type=row["resource_type"], resource_id=row["resource_id"], title=row["title"], priority=row["priority"], due_at=now + timedelta(hours=sla_hours)))
            changed = True
    for item in db.scalars(select(WorkItem).where(WorkItem.status.in_(("open", "claimed")), WorkItem.due_at.is_not(None))).all():
        metadata = dict(item.metadata_ or {})
        if item.due_at <= now + timedelta(hours=1) and "sla_reminded_at" not in metadata:
            metadata["sla_reminded_at"] = now.isoformat()
            item.metadata_ = metadata
            item.updated_at = now
            db.add(AuditLog(action="work_item.sla_reminder", resource_type="work_item", resource_id=str(item.id), after_data={"due_at": item.due_at.isoformat(), "priority": item.priority}))
            changed = True
        if item.due_at < now and "sla_escalated_at" not in metadata:
            before = {"priority": item.priority, "due_at": item.due_at.isoformat()}
            metadata = dict(item.metadata_ or {})
            metadata["sla_escalated_at"] = now.isoformat()
            item.metadata_ = metadata
            item.priority = "critical"
            item.version += 1
            item.updated_at = now
            db.add(AuditLog(action="work_item.sla_escalated", resource_type="work_item", resource_id=str(item.id), before_data=before, after_data={"priority": item.priority, "due_at": item.due_at.isoformat()}))
            changed = True
    if changed:
        db.commit()


def _require_item_handler(actor: AdminActor, item: WorkItem) -> None:
    if not _can_handle_resource(actor.permissions, item.resource_type):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有处理该业务待办的权限")


def _require_item_reader(actor: AdminActor, item: WorkItem) -> None:
    required_permission = {
        "community_report": "community.read",
        "community_profile": "community.read",
        "husbandry_case": "husbandry.read",
        "diagnosis_conversation": "diagnosis.read",
    }.get(item.resource_type)
    if required_permission and required_permission not in actor.permissions and "admins.manage" not in actor.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有查看该业务待办的权限")


def _can_handle_resource(permissions: set[str] | frozenset[str], resource_type: str) -> bool:
    required_permission = {
        "community_report": "community.moderate",
        "community_profile": "community.verify",
        "husbandry_case": "husbandry.review",
        "diagnosis_conversation": "diagnosis.review",
    }.get(resource_type)
    return required_permission is None or required_permission in permissions or "admins.manage" in permissions


def _require_item_owner_or_admin(actor: AdminActor, item: WorkItem) -> None:
    if item.assignee_id != actor.id and "admins.manage" not in actor.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能处理自己领取的待办")


def _resource_is_resolved(db: Session, item: WorkItem) -> bool:
    if item.resource_type == "community_report":
        value = db.execute(text("SELECT status FROM community_reports WHERE id::text = :resource_id"), {"resource_id": item.resource_id}).scalar()
        return value is None or value != "pending"
    if item.resource_type == "community_profile":
        value = db.execute(text("SELECT verification_status FROM community_profiles WHERE user_id::text = :resource_id"), {"resource_id": item.resource_id}).scalar()
        return value is None or value != "pending"
    if item.resource_type == "husbandry_case":
        return db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM admin.expert_reviews
                 WHERE husbandry_case_id::text = :resource_id AND status = 'published'
            )
        """), {"resource_id": item.resource_id}).scalar() is True
    if item.resource_type == "diagnosis_conversation":
        return db.execute(text("""
            SELECT EXISTS (
                SELECT 1 FROM admin.expert_reviews
                 WHERE conversation_id::text = :resource_id AND status = 'published'
            )
        """), {"resource_id": item.resource_id}).scalar() is True
    return True


def _scalar(db: Session, statement: str) -> int:
    try:
        return int(db.execute(text(statement)).scalar() or 0)
    except Exception:
        db.rollback()
        return 0


def _work_item_dicts_with_assignees(db: Session, items: list[WorkItem]) -> list[dict]:
    assignee_ids = {item.assignee_id for item in items if item.assignee_id}
    assignee_names = dict(db.execute(select(AdminAccount.id, AdminAccount.display_name).where(AdminAccount.id.in_(assignee_ids))).all()) if assignee_ids else {}
    return [_work_item_dict(item, assignee_name=assignee_names.get(item.assignee_id)) for item in items]


def _work_item_dict(item: WorkItem, assignee_name: str | None = None) -> dict:
    remaining_seconds = int((item.due_at - now_utc()).total_seconds()) if item.due_at else None
    if remaining_seconds is None:
        sla_status = "on_track"
    elif remaining_seconds < 0:
        sla_status = "overdue"
    elif remaining_seconds <= 4 * 60 * 60:
        sla_status = "due_soon"
    else:
        sla_status = "on_track"
    return {"id": str(item.id), "item_type": item.item_type, "resource_type": item.resource_type, "resource_id": item.resource_id, "title": item.title, "priority": item.priority, "status": item.status, "assignee_id": str(item.assignee_id) if item.assignee_id else None, "assignee_name": assignee_name, "due_at": item.due_at, "sla_status": sla_status, "remaining_seconds": remaining_seconds, "sla_reminded_at": item.metadata_.get("sla_reminded_at") if item.metadata_ else None, "sla_escalated_at": item.metadata_.get("sla_escalated_at") if item.metadata_ else None, "metadata": item.metadata_, "version": item.version, "created_at": item.created_at, "updated_at": item.updated_at}

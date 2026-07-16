from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_permission
from app.schemas import ContentStatusRequest, ModerationReportReviewRequest, TagMergeRequest, TagRenameRequest, VerificationReviewRequest
from app.services import AdminActor, complete_work_items_for_resource, write_audit


router = APIRouter(prefix="/community", tags=["community"])


def _create_community_notification(
    db: Session,
    *,
    user_id: str | None,
    post_id: str | None = None,
    comment_id: str | None = None,
    payload: dict[str, object],
) -> None:
    """Persist a user-facing moderation result without mixing admin identities into users."""
    if not user_id:
        return
    db.execute(text("""
        INSERT INTO community_notifications (user_id, post_id, comment_id, notification_type, payload)
        VALUES (CAST(:user_id AS uuid), CAST(:post_id AS uuid), CAST(:comment_id AS uuid), 'moderation', CAST(:payload AS jsonb))
    """), {
        "user_id": user_id,
        "post_id": post_id,
        "comment_id": comment_id,
        "payload": json.dumps(payload, ensure_ascii=False),
    })


def _report_target_label(target_type: str) -> str:
    return "帖子" if target_type == "post" else "评论"


@router.get("/reports")
def reports(
    report_status: str = Query(default="pending", alias="status", pattern="^(pending|reviewed|dismissed|all)$"),
    report_id: UUID | None = Query(default=None, alias="id"),
    author_id: UUID | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.read")),
) -> dict:
    conditions = [] if report_status == "all" else ["cr.status = :report_status"]
    if report_id:
        conditions.append("cr.id = CAST(:report_id AS uuid)")
    if author_id:
        conditions.append("COALESCE(p.author_id, c.author_id) = CAST(:author_id AS uuid)")
    if q and q.strip():
        conditions.append("""(
            cr.reason ILIKE :query OR cr.detail ILIKE :query OR
            p.title ILIKE :query OR p.content_markdown ILIKE :query OR
            c.content ILIKE :query OR r.display_name ILIKE :query OR r.username ILIKE :query
        )""")
    condition = " AND ".join(conditions) if conditions else "TRUE"
    values = {
        "report_status": report_status,
        "report_id": str(report_id) if report_id else None,
        "author_id": str(author_id) if author_id else None,
        "query": f"%{q.strip()}%" if q and q.strip() else None,
        "limit": page_size,
        "offset": (page - 1) * page_size,
    }
    source = """
        community_reports cr
        JOIN users r ON r.id = cr.reporter_id
        LEFT JOIN community_posts p ON p.id = cr.post_id
        LEFT JOIN community_comments c ON c.id = cr.comment_id
    """
    total = int(db.execute(text(f"SELECT count(*) FROM {source} WHERE {condition}"), values).scalar() or 0)
    rows = db.execute(text(f"""
        SELECT cr.id::text AS id, cr.target_type, cr.post_id::text AS post_id, cr.comment_id::text AS comment_id,
               cr.reason, cr.detail, cr.status, cr.review_action, cr.resolution_reason,
               cr.version, cr.created_at, cr.reviewed_at,
               COALESCE(r.display_name, r.username, '未知用户') AS reporter_name, r.id::text AS reporter_id,
               COALESCE(p.title, LEFT(c.content, 120), '已删除内容') AS target_summary,
               COALESCE(p.status, c.status, 'deleted') AS target_status,
               COALESCE(p.author_id, c.author_id)::text AS author_id,
               COALESCE(a.display_name, a.username, '未知作者') AS author_name
          FROM {source}
          LEFT JOIN users a ON a.id = COALESCE(p.author_id, c.author_id)
         WHERE {condition}
         ORDER BY cr.created_at DESC LIMIT :limit OFFSET :offset
    """), values).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/reports/{report_id}")
def report_detail(
    report_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.read")),
) -> dict:
    report = db.execute(text("""
        SELECT cr.id::text AS id, cr.target_type, cr.post_id::text AS post_id, cr.comment_id::text AS comment_id,
               cr.reason, cr.detail, cr.status, cr.review_action, cr.resolution_reason, cr.version,
               cr.created_at, cr.reviewed_at, cr.reviewed_by_admin_id::text AS reviewed_by_admin_id,
               COALESCE(r.display_name, r.username, '未知用户') AS reporter_name, r.id::text AS reporter_id,
               COALESCE(p.title, cp.title, '已删除内容') AS target_title,
               COALESCE(p.content_markdown, c.content, '') AS target_content,
               COALESCE(p.status, c.status, 'deleted') AS target_status,
               COALESCE(p.author_id, c.author_id)::text AS author_id,
               COALESCE(a.display_name, a.username, '未知作者') AS author_name,
               a.status AS author_status,
               reviewer.display_name AS reviewer_name,
               cp.id::text AS context_post_id, cp.title AS context_post_title
          FROM community_reports cr
          JOIN users r ON r.id = cr.reporter_id
          LEFT JOIN community_posts p ON p.id = cr.post_id
          LEFT JOIN community_comments c ON c.id = cr.comment_id
          LEFT JOIN community_posts cp ON cp.id = c.post_id
          LEFT JOIN users a ON a.id = COALESCE(p.author_id, c.author_id)
          LEFT JOIN admin.admin_accounts reviewer ON reviewer.id = cr.reviewed_by_admin_id
         WHERE cr.id = CAST(:report_id AS uuid)
    """), {"report_id": str(report_id)}).mappings().first()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="举报不存在")
    target_id = report["post_id"] if report["target_type"] == "post" else report["comment_id"]
    target_resource_type = "community_post" if report["target_type"] == "post" else "community_comment"
    prior_reports = db.execute(text("""
        SELECT id::text AS id, reason, detail, status, review_action, created_at, reviewed_at
          FROM community_reports
         WHERE (target_type = 'post' AND post_id = CAST(:post_id AS uuid))
            OR (target_type = 'comment' AND comment_id = CAST(:comment_id AS uuid))
         ORDER BY created_at DESC LIMIT 12
    """), {"post_id": report["post_id"], "comment_id": report["comment_id"]}).mappings().all()
    history = db.execute(text("""
        SELECT ma.id::text AS id, ma.action_type, ma.reason, ma.metadata, ma.created_at,
               account.display_name AS actor_name
          FROM admin.moderation_actions ma
          LEFT JOIN admin.admin_accounts account ON account.id = ma.actor_id
         WHERE (ma.target_type = 'community_report' AND ma.target_id = :report_id)
            OR (ma.target_type = :target_type AND ma.target_id = :target_id)
         ORDER BY ma.created_at DESC LIMIT 16
    """), {"report_id": str(report_id), "target_type": target_resource_type, "target_id": target_id}).mappings().all()
    author_summary = db.execute(text("""
        SELECT count(*) FILTER (WHERE cr.status = 'pending') AS pending_reports,
               count(*) FILTER (WHERE cr.status = 'reviewed') AS reviewed_reports,
               count(*) AS total_reports
          FROM community_reports cr
          LEFT JOIN community_posts p ON p.id = cr.post_id
          LEFT JOIN community_comments c ON c.id = cr.comment_id
         WHERE COALESCE(p.author_id, c.author_id)::text = :author_id
    """), {"author_id": report["author_id"] or ""}).mappings().first()
    warning_count = int(db.execute(text("""
        SELECT count(*)
          FROM admin.moderation_actions
         WHERE action_type = 'report_reviewed_warn'
           AND metadata ->> 'author_id' = :author_id
    """), {"author_id": report["author_id"] or ""}).scalar() or 0)
    assets: list[dict] = []
    if report["target_type"] == "post" and report["post_id"]:
        assets = [dict(row) for row in db.execute(text("""
            SELECT f.id::text AS id, f.file_name, f.file_type, f.mime_type, f.file_size
              FROM community_post_assets asset
              JOIN files f ON f.id = asset.file_id
             WHERE asset.post_id = CAST(:post_id AS uuid)
             ORDER BY asset.sort_order, asset.created_at
        """), {"post_id": report["post_id"]}).mappings().all()]
    return {
        "report": dict(report),
        "prior_reports": [dict(row) for row in prior_reports],
        "history": [dict(row) for row in history],
        "author_summary": {**dict(author_summary or {}), "warning_count": warning_count},
        "assets": assets,
    }


@router.patch("/reports/{report_id}")
def review_report(
    report_id: UUID,
    payload: ModerationReportReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.moderate")),
) -> dict:
    report = db.execute(text("""
        SELECT cr.id::text AS id, cr.target_type, cr.post_id::text AS post_id, cr.comment_id::text AS comment_id,
               cr.status, cr.version, cr.reporter_id::text AS reporter_id,
               COALESCE(p.author_id, c.author_id)::text AS author_id
          FROM community_reports cr
          LEFT JOIN community_posts p ON p.id = cr.post_id
          LEFT JOIN community_comments c ON c.id = cr.comment_id
         WHERE cr.id = CAST(:report_id AS uuid)
         FOR UPDATE OF cr
    """), {"report_id": str(report_id)}).mappings().first()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="举报不存在")
    if report["status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="举报已处理")
    if int(report["version"]) != payload.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="举报已被其他管理员更新，请刷新后再处理")
    if payload.status == "dismissed" and payload.action != "none":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="驳回举报不能同时执行内容处置")
    target_id = report["post_id"] if report["target_type"] == "post" else report["comment_id"]
    target_type = "community_post" if report["target_type"] == "post" else "community_comment"
    target_status: str | None = None
    if payload.action in {"hide", "restore"}:
        table = "community_posts" if report["target_type"] == "post" else "community_comments"
        target_status = db.execute(text(f"SELECT status FROM {table} WHERE id = CAST(:target_id AS uuid) FOR UPDATE"), {"target_id": target_id}).scalar()
        if target_status is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="被举报内容已不存在，无法变更状态")
    if payload.action == "hide":
        if target_status not in {"published", "active"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该内容当前不能隐藏")
        table = "community_posts" if report["target_type"] == "post" else "community_comments"
        version_column = ", moderation_version = moderation_version + 1" if report["target_type"] == "post" else ""
        db.execute(text(f"UPDATE {table} SET status = 'hidden', updated_at = now(){version_column} WHERE id = CAST(:target_id AS uuid)"), {"target_id": target_id})
    elif payload.action == "restore":
        if target_status != "hidden":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅已隐藏内容可以恢复")
        table = "community_posts" if report["target_type"] == "post" else "community_comments"
        restored_status = "published" if report["target_type"] == "post" else "active"
        version_column = ", moderation_version = moderation_version + 1" if report["target_type"] == "post" else ""
        db.execute(text(f"UPDATE {table} SET status = :restored_status, updated_at = now(){version_column} WHERE id = CAST(:target_id AS uuid)"), {"target_id": target_id, "restored_status": restored_status})
    elif payload.action == "disable_author" and report["author_id"]:
        db.execute(text("UPDATE users SET status = 'disabled', updated_at = now() WHERE id = CAST(:author_id AS uuid)"), {"author_id": report["author_id"]})
        db.execute(text("UPDATE auth_sessions SET status = 'revoked', revoked_at = now() WHERE user_id = CAST(:author_id AS uuid) AND status = 'active'"), {"author_id": report["author_id"]})
    updated = db.execute(text("""
        UPDATE community_reports
           SET status = :status, review_action = :action, resolution_reason = :reason,
               reviewed_by_admin_id = CAST(:actor_id AS uuid), reviewed_at = now(), version = version + 1
         WHERE id = CAST(:report_id AS uuid) AND status = 'pending' AND version = :version
    """), {"status": payload.status, "action": payload.action, "reason": payload.reason, "actor_id": str(actor.id), "report_id": str(report_id), "version": payload.version})
    if updated.rowcount != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="举报已被其他管理员更新，请刷新后再处理")
    db.execute(text("""
        INSERT INTO admin.moderation_actions (actor_id, target_type, target_id, action_type, reason, metadata)
        VALUES (CAST(:actor_id AS uuid), :target_type, :target_id, :action_type, :reason, CAST(:metadata AS jsonb))
    """), {
        "actor_id": str(actor.id), "target_type": target_type, "target_id": target_id,
        "action_type": f"report_{payload.status}_{payload.action}", "reason": payload.reason,
        "metadata": json.dumps({"report_id": str(report_id), "author_id": report["author_id"], "target_type": report["target_type"]}),
    })
    _create_community_notification(
        db,
        user_id=report["reporter_id"],
        post_id=report["post_id"],
        comment_id=report["comment_id"],
        payload={
            "event": "report_result", "report_id": str(report_id), "status": payload.status,
            "action": payload.action,
            "message": f"你提交的{_report_target_label(report['target_type'])}举报已处理：{'已采取处置' if payload.status == 'reviewed' else '未发现需要处置的问题'}。",
        },
    )
    if report["author_id"] and report["author_id"] != report["reporter_id"]:
        action_label = {"hide": "内容已隐藏", "restore": "内容已恢复", "warn": "已收到社区警告", "disable_author": "账号已被禁用", "none": "举报已处理"}[payload.action]
        _create_community_notification(
            db,
            user_id=report["author_id"],
            post_id=report["post_id"],
            comment_id=report["comment_id"],
            payload={
                "event": "content_moderation", "report_id": str(report_id), "action": payload.action,
                "message": f"管理员已处理你的{_report_target_label(report['target_type'])}：{action_label}。原因：{payload.reason}",
            },
        )
    write_audit(db, actor_id=actor.id, action="community.report_reviewed", resource_type="community_report", resource_id=str(report_id), request=request, reason=payload.reason, before_data={"status": report["status"], "version": report["version"]}, after_data={"status": payload.status, "action": payload.action, "version": payload.version + 1})
    complete_work_items_for_resource(db, actor_id=actor.id, resource_type="community_report", resource_id=str(report_id))
    db.commit()
    return {"id": str(report_id), "status": payload.status, "action": payload.action}


@router.get("/verifications")
def verifications(
    verification_status: str = Query(default="pending", alias="status", pattern="^(unverified|pending|verified|rejected|all)$"),
    user_id: UUID | None = Query(default=None, alias="user_id"),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.read")),
) -> dict:
    conditions = [] if verification_status == "all" else ["cp.verification_status = :verification_status"]
    if user_id:
        conditions.append("cp.user_id = CAST(:user_id AS uuid)")
    if q and q.strip():
        conditions.append("""(
            u.display_name ILIKE :query OR u.username ILIKE :query OR cp.organization ILIKE :query OR
            cp.region ILIKE :query OR cp.identity_type ILIKE :query OR cp.bio ILIKE :query
        )""")
    condition = " AND ".join(conditions) if conditions else "TRUE"
    values = {"verification_status": verification_status, "user_id": str(user_id) if user_id else None, "query": f"%{q.strip()}%" if q and q.strip() else None, "limit": page_size, "offset": (page - 1) * page_size}
    total = int(db.execute(text(f"SELECT count(*) FROM community_profiles cp JOIN users u ON u.id = cp.user_id WHERE {condition}"), values).scalar() or 0)
    rows = db.execute(text(f"""
        SELECT cp.user_id::text AS user_id, cp.identity_type, cp.region, cp.organization, cp.expertise_tags,
               cp.years_experience, cp.bio, cp.verification_status, cp.verification_version, cp.verified_at, cp.updated_at,
               COALESCE(u.display_name, u.username, '未命名用户') AS display_name, u.status AS user_status
          FROM community_profiles cp JOIN users u ON u.id = cp.user_id
         WHERE {condition}
         ORDER BY cp.updated_at DESC LIMIT :limit OFFSET :offset
    """), values).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/verifications/{user_id}")
def verification_detail(
    user_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.read")),
) -> dict:
    profile = db.execute(text("""
        SELECT cp.user_id::text AS user_id, cp.identity_type, cp.region, cp.organization, cp.expertise_tags,
               cp.years_experience, cp.bio, cp.verification_status, cp.verification_version,
               cp.verified_at, cp.created_at, cp.updated_at,
               COALESCE(u.display_name, u.username, '未命名用户') AS display_name, u.status AS user_status,
               u.created_at AS user_created_at
          FROM community_profiles cp
          JOIN users u ON u.id = cp.user_id
         WHERE cp.user_id = CAST(:user_id AS uuid)
    """), {"user_id": str(user_id)}).mappings().first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="社区资料不存在")
    recent_posts = db.execute(text("""
        SELECT id::text AS id, title, excerpt, post_type, status, created_at
          FROM community_posts
         WHERE author_id = CAST(:user_id AS uuid)
         ORDER BY created_at DESC LIMIT 8
    """), {"user_id": str(user_id)}).mappings().all()
    history = db.execute(text("""
        SELECT ma.id::text AS id, ma.action_type, ma.reason, ma.metadata, ma.created_at,
               account.display_name AS actor_name
          FROM admin.moderation_actions ma
          LEFT JOIN admin.admin_accounts account ON account.id = ma.actor_id
         WHERE ma.target_type = 'community_profile' AND ma.target_id = :user_id
         ORDER BY ma.created_at DESC LIMIT 12
    """), {"user_id": str(user_id)}).mappings().all()
    summary = db.execute(text("""
        SELECT count(*) AS post_count,
               count(*) FILTER (WHERE status = 'hidden') AS hidden_post_count,
               count(*) FILTER (WHERE status = 'deleted') AS deleted_post_count
          FROM community_posts WHERE author_id = CAST(:user_id AS uuid)
    """), {"user_id": str(user_id)}).mappings().first()
    return {"profile": dict(profile), "recent_posts": [dict(row) for row in recent_posts], "history": [dict(row) for row in history], "summary": dict(summary or {})}


@router.patch("/verifications/{user_id}")
def review_verification(
    user_id: UUID,
    payload: VerificationReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.verify")),
) -> dict:
    profile = db.execute(text("""
        SELECT verification_status, verification_version
          FROM community_profiles
         WHERE user_id = CAST(:user_id AS uuid)
         FOR UPDATE
    """), {"user_id": str(user_id)}).mappings().first()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="社区资料不存在")
    if profile["verification_status"] != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该认证申请已处理，不能重复审核")
    if int(profile["verification_version"]) != payload.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="认证申请已被其他管理员更新，请刷新后再处理")
    updated = db.execute(text("""
        UPDATE community_profiles SET verification_status = :status,
               verified_at = CASE WHEN :status = 'verified' THEN now() ELSE NULL END,
               updated_at = now(), verification_version = verification_version + 1
         WHERE user_id = CAST(:user_id AS uuid) AND verification_status = 'pending' AND verification_version = :version
    """), {"status": payload.status, "user_id": str(user_id), "version": payload.version})
    if updated.rowcount != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="认证申请已被其他管理员更新，请刷新后再处理")
    db.execute(text("""
        INSERT INTO admin.moderation_actions (actor_id, target_type, target_id, action_type, reason)
        VALUES (CAST(:actor_id AS uuid), 'community_profile', :target_id, :action_type, :reason)
    """), {"actor_id": str(actor.id), "target_id": str(user_id), "action_type": f"verification_{payload.status}", "reason": payload.reason})
    _create_community_notification(
        db,
        user_id=str(user_id),
        payload={
            "event": "verification_result", "status": payload.status,
            "message": f"你的专业认证申请已{'通过' if payload.status == 'verified' else '驳回'}。原因：{payload.reason}",
        },
    )
    write_audit(db, actor_id=actor.id, action="community.verification_reviewed", resource_type="community_profile", resource_id=str(user_id), request=request, reason=payload.reason, before_data={"status": profile["verification_status"], "version": profile["verification_version"]}, after_data={"status": payload.status, "version": payload.version + 1})
    complete_work_items_for_resource(db, actor_id=actor.id, resource_type="community_profile", resource_id=str(user_id))
    db.commit()
    return {"user_id": str(user_id), "status": payload.status}


@router.get("/content/posts")
def posts(
    content_status: str | None = Query(default=None, alias="status", pattern="^(draft|published|hidden|deleted)$"),
    post_type: str | None = Query(default=None, pattern="^(experience|case|question|reference|announcement)$"),
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.read")),
) -> dict:
    conditions = ["TRUE"]
    values: dict[str, object] = {"limit": page_size, "offset": (page - 1) * page_size}
    if content_status:
        conditions.append("p.status = :status")
        values["status"] = content_status
    if post_type:
        conditions.append("p.post_type = :post_type")
        values["post_type"] = post_type
    if q:
        conditions.append("(p.title ILIKE :query OR p.content_markdown ILIKE :query OR p.id::text ILIKE :query)")
        values["query"] = f"%{q.strip()}%"
    where = " AND ".join(conditions)
    total = int(db.execute(text(f"SELECT count(*) FROM community_posts p WHERE {where}"), values).scalar() or 0)
    rows = db.execute(text(f"""
        SELECT p.id::text AS id, p.title, p.excerpt, p.post_type, p.visibility, p.status,
               p.moderation_version, p.like_count, p.bookmark_count, p.comment_count, p.view_count, p.created_at, p.published_at,
               u.id::text AS author_id, COALESCE(u.display_name, u.username, '未命名用户') AS author_name,
               array_remove(array_agg(DISTINCT t.name), NULL) AS tags
          FROM community_posts p JOIN users u ON u.id = p.author_id
          LEFT JOIN community_post_tags pt ON pt.post_id = p.id
          LEFT JOIN community_tags t ON t.id = pt.tag_id
         WHERE {where}
         GROUP BY p.id, u.id
         ORDER BY p.created_at DESC LIMIT :limit OFFSET :offset
    """), values).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/content/posts/{post_id}")
def post_detail(
    post_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.read")),
) -> dict:
    post = db.execute(text("""
        SELECT p.id::text AS id, p.title, p.content_markdown, p.excerpt, p.post_type, p.visibility, p.status,
               p.moderation_version, p.like_count, p.bookmark_count, p.comment_count, p.view_count,
               p.created_at, p.updated_at, p.published_at, p.deleted_at,
               u.id::text AS author_id, COALESCE(u.display_name, u.username, '未命名用户') AS author_name,
               u.status AS author_status
          FROM community_posts p JOIN users u ON u.id = p.author_id
         WHERE p.id = CAST(:post_id AS uuid)
    """), {"post_id": str(post_id)}).mappings().first()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")
    tags_rows = db.execute(text("""
        SELECT t.id::text AS id, t.name
          FROM community_post_tags pt JOIN community_tags t ON t.id = pt.tag_id
         WHERE pt.post_id = CAST(:post_id AS uuid)
         ORDER BY t.name
    """), {"post_id": str(post_id)}).mappings().all()
    reports_summary = db.execute(text("""
        SELECT count(*) AS total, count(*) FILTER (WHERE status = 'pending') AS pending,
               count(*) FILTER (WHERE status = 'reviewed') AS reviewed,
               count(*) FILTER (WHERE status = 'dismissed') AS dismissed
          FROM community_reports
         WHERE target_type = 'post' AND post_id = CAST(:post_id AS uuid)
    """), {"post_id": str(post_id)}).mappings().first()
    history = db.execute(text("""
        SELECT ma.id::text AS id, ma.action_type, ma.reason, ma.metadata, ma.created_at,
               account.display_name AS actor_name
          FROM admin.moderation_actions ma
          LEFT JOIN admin.admin_accounts account ON account.id = ma.actor_id
         WHERE ma.target_type = 'community_post' AND ma.target_id = :post_id
         ORDER BY ma.created_at DESC LIMIT 16
    """), {"post_id": str(post_id)}).mappings().all()
    return {"post": dict(post), "tags": [dict(row) for row in tags_rows], "reports_summary": dict(reports_summary or {}), "history": [dict(row) for row in history]}


@router.patch("/content/posts/{post_id}/status")
def update_post_status(
    post_id: UUID,
    payload: ContentStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.moderate")),
) -> dict:
    row = db.execute(text("""
        SELECT status, moderation_version, author_id::text AS author_id
          FROM community_posts
         WHERE id = CAST(:post_id AS uuid)
         FOR UPDATE
    """), {"post_id": str(post_id)}).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")
    if int(row["moderation_version"]) != payload.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="帖子已被其他管理员更新，请刷新后再处理")
    allowed_transitions = {
        "published": {"hidden", "deleted"},
        "hidden": {"published", "deleted"},
        "draft": set(),
        "deleted": set(),
    }
    if payload.status not in allowed_transitions.get(row["status"], set()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前帖子状态不允许执行该操作")
    updated = db.execute(text("""
        UPDATE community_posts
           SET status = :status, updated_at = now(),
               published_at = CASE WHEN :status = 'published' THEN COALESCE(published_at, now()) ELSE published_at END,
               deleted_at = CASE WHEN :status = 'deleted' THEN now() ELSE deleted_at END,
               moderation_version = moderation_version + 1
         WHERE id = CAST(:post_id AS uuid) AND moderation_version = :version
    """), {"status": payload.status, "post_id": str(post_id), "version": payload.version})
    if updated.rowcount != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="帖子已被其他管理员更新，请刷新后再处理")
    db.execute(text("""
        INSERT INTO admin.moderation_actions (actor_id, target_type, target_id, action_type, reason)
        VALUES (CAST(:actor_id AS uuid), 'community_post', :target_id, :action_type, :reason)
    """), {"actor_id": str(actor.id), "target_id": str(post_id), "action_type": f"post_{payload.status}", "reason": payload.reason})
    post_action = {"hidden": "帖子已隐藏", "published": "帖子已恢复发布", "deleted": "帖子已删除"}[payload.status]
    _create_community_notification(
        db,
        user_id=row["author_id"],
        post_id=str(post_id),
        payload={"event": "post_status", "status": payload.status, "message": f"管理员已处理你的帖子：{post_action}。原因：{payload.reason}"},
    )
    write_audit(db, actor_id=actor.id, action="community.post_status_changed", resource_type="community_post", resource_id=str(post_id), request=request, reason=payload.reason, before_data={"status": row["status"], "version": row["moderation_version"]}, after_data={"status": payload.status, "version": payload.version + 1})
    db.commit()
    return {"id": str(post_id), "status": payload.status}


@router.get("/tags")
def tags(
    q: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.read")),
) -> dict:
    values = {"query": f"%{q.strip()}%" if q and q.strip() else None, "limit": page_size, "offset": (page - 1) * page_size}
    where = "name ILIKE :query" if q and q.strip() else "TRUE"
    total = int(db.execute(text(f"SELECT count(*) FROM community_tags WHERE {where}"), values).scalar() or 0)
    rows = db.execute(text(f"""
        SELECT id::text AS id, name, post_count, created_at
          FROM community_tags WHERE {where}
         ORDER BY post_count DESC, name LIMIT :limit OFFSET :offset
    """), values).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.patch("/tags/{tag_id}")
def rename_tag(
    tag_id: UUID,
    payload: TagRenameRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.moderate")),
) -> dict:
    tag = db.execute(text("SELECT id::text AS id, name FROM community_tags WHERE id = CAST(:tag_id AS uuid)"), {"tag_id": str(tag_id)}).mappings().first()
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
    name = " ".join(payload.name.split())
    if not name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="标签名称不能为空")
    duplicate = db.execute(text("SELECT id FROM community_tags WHERE name = :name AND id <> CAST(:tag_id AS uuid)"), {"name": name, "tag_id": str(tag_id)}).first()
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="标签名称已存在，请使用合并功能")
    db.execute(text("UPDATE community_tags SET name = :name WHERE id = CAST(:tag_id AS uuid)"), {"name": name, "tag_id": str(tag_id)})
    write_audit(db, actor_id=actor.id, action="community.tag_renamed", resource_type="community_tag", resource_id=str(tag_id), request=request, reason=payload.reason, before_data={"name": tag["name"]}, after_data={"name": name})
    db.commit()
    return {"id": str(tag_id), "name": name}


@router.post("/tags/{tag_id}/merge")
def merge_tag(
    tag_id: UUID,
    payload: TagMergeRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("community.moderate")),
) -> dict:
    try:
        target_id = UUID(payload.target_tag_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="目标标签标识无效") from exc
    if target_id == tag_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不能合并到自身")
    source = db.execute(text("SELECT id::text AS id, name FROM community_tags WHERE id = CAST(:tag_id AS uuid)"), {"tag_id": str(tag_id)}).mappings().first()
    target = db.execute(text("SELECT id::text AS id, name FROM community_tags WHERE id = CAST(:tag_id AS uuid)"), {"tag_id": str(target_id)}).mappings().first()
    if source is None or target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源标签或目标标签不存在")
    db.execute(text("""
        INSERT INTO community_post_tags (post_id, tag_id)
        SELECT post_id, CAST(:target_id AS uuid) FROM community_post_tags WHERE tag_id = CAST(:source_id AS uuid)
        ON CONFLICT (post_id, tag_id) DO NOTHING
    """), {"source_id": str(tag_id), "target_id": str(target_id)})
    db.execute(text("DELETE FROM community_post_tags WHERE tag_id = CAST(:source_id AS uuid)"), {"source_id": str(tag_id)})
    db.execute(text("UPDATE community_tags SET post_count = (SELECT count(*) FROM community_post_tags WHERE tag_id = CAST(:target_id AS uuid)) WHERE id = CAST(:target_id AS uuid)"), {"target_id": str(target_id)})
    db.execute(text("DELETE FROM community_tags WHERE id = CAST(:source_id AS uuid)"), {"source_id": str(tag_id)})
    write_audit(db, actor_id=actor.id, action="community.tag_merged", resource_type="community_tag", resource_id=str(tag_id), request=request, reason=payload.reason, before_data={"name": source["name"]}, after_data={"target_id": str(target_id), "target_name": target["name"]})
    db.commit()
    return {"source_id": str(tag_id), "target_id": str(target_id), "target_name": target["name"]}

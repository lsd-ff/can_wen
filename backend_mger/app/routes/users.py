from __future__ import annotations

import csv
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.dependencies import require_permission
from app.schemas import RevokeSessionsRequest, UserBatchActionRequest, UserStatusRequest
from app.services import AdminActor, write_audit


router = APIRouter(prefix="/users", tags=["users"])


def _build_user_filters(
    *,
    q: str | None,
    status_filter: str | None,
    role: str | None,
    verification_status: str | None,
    created_since: str | None,
    attention: str | None,
) -> tuple[list[str], dict[str, object]]:
    filters = ["u.deleted_at IS NOT NULL" if status_filter == "deleted" else "u.deleted_at IS NULL"]
    values: dict[str, object] = {}

    if q and q.strip():
        filters.append(
            """(
                u.display_name ILIKE :query OR u.username ILIKE :query OR u.id::text ILIKE :query
                OR EXISTS (
                    SELECT 1
                      FROM user_identities search_identity
                     WHERE search_identity.user_id = u.id
                       AND search_identity.unbound_at IS NULL
                       AND (search_identity.email ILIKE :query OR search_identity.phone_number ILIKE :query)
                )
            )"""
        )
        values["query"] = f"%{q.strip()}%"
    if status_filter and status_filter != "deleted":
        filters.append("u.status = :status")
        values["status"] = status_filter
    if role:
        filters.append("u.role = :role")
        values["role"] = role
    if verification_status:
        filters.append("COALESCE(cp.verification_status, 'unverified') = :verification_status")
        values["verification_status"] = verification_status
    if created_since == "today":
        filters.append("u.created_at >= date_trunc('day', now())")
    elif created_since == "7d":
        filters.append("u.created_at >= now() - interval '7 days'")

    if attention == "reports":
        filters.append(
            """
            EXISTS (
                SELECT 1
                  FROM community_reports cr
                  LEFT JOIN community_posts reported_post ON reported_post.id = cr.post_id
                  LEFT JOIN community_comments reported_comment ON reported_comment.id = cr.comment_id
                 WHERE cr.status = 'pending'
                   AND (reported_post.author_id = u.id OR reported_comment.author_id = u.id)
            )
            """
        )
    elif attention == "security":
        filters.append(f"(SELECT count(*) FROM login_events login_failure WHERE login_failure.created_at >= now() - interval '7 days' AND login_failure.event_type IN ('login_failed', 'verification_failed') AND (login_failure.user_id = u.id OR EXISTS (SELECT 1 FROM user_identities login_identity WHERE login_identity.user_id = u.id AND login_identity.unbound_at IS NULL AND (login_identity.email = login_failure.target OR login_identity.phone_number = login_failure.target)))) >= 3")
    elif attention == "verification":
        filters.append("COALESCE(cp.verification_status, 'unverified') = 'pending'")

    return filters, values


def _user_sort(sort_by: str) -> str:
    if sort_by == "attention":
        # PostgreSQL permits an output alias in ORDER BY, but not as the operand
        # of a nested CASE expression. Repeat the source conditions here so the
        # default attention-first user directory query remains executable.
        return (
            "CASE "
            "WHEN reports.pending_report_count > 0 THEN 0 "
            "WHEN security.login_failure_count_7d >= 3 THEN 1 "
            "WHEN COALESCE(cp.verification_status, 'unverified') = 'pending' THEN 2 "
            "ELSE 3 END, u.last_seen_at DESC NULLS LAST, u.created_at DESC"
        )
    return {
        "registered": "u.registered_at DESC NULLS LAST, u.created_at DESC",
        "last_seen": "u.last_seen_at DESC NULLS LAST, u.created_at DESC",
    }.get(sort_by, "u.last_seen_at DESC NULLS LAST, u.created_at DESC")


def _select_user_rows(where: str, order_by: str, pagination: str = "") -> str:
    return f"""
        SELECT u.id::text AS id, u.display_name, u.username, u.role, u.status, u.deleted_at, u.registered_at, u.last_seen_at,
               identity.email, identity.phone_number,
               COALESCE(cp.verification_status, 'unverified') AS verification_status,
               activity.conversation_count, activity.post_count, activity.open_case_count,
               sessions.active_session_count, reports.pending_report_count,
               security.login_failure_count_7d, security.last_login_failure_at,
               CASE
                   WHEN reports.pending_report_count > 0 THEN 'reports'
                   WHEN security.login_failure_count_7d >= 3 THEN 'security'
                   WHEN COALESCE(cp.verification_status, 'unverified') = 'pending' THEN 'verification'
                   ELSE 'none'
               END AS attention_level
          FROM users u
          LEFT JOIN community_profiles cp ON cp.user_id = u.id
          LEFT JOIN LATERAL (
              SELECT MAX(i.email) FILTER (WHERE i.provider = 'email') AS email,
                     MAX(i.phone_number) FILTER (WHERE i.provider = 'phone') AS phone_number
                FROM user_identities i
               WHERE i.user_id = u.id AND i.unbound_at IS NULL
          ) identity ON TRUE
          LEFT JOIN LATERAL (
              SELECT
                  (SELECT count(*) FROM conversations c WHERE c.user_id = u.id AND c.deleted_at IS NULL) AS conversation_count,
                  (SELECT count(*) FROM community_posts p WHERE p.author_id = u.id AND p.deleted_at IS NULL) AS post_count,
                  (SELECT count(*) FROM husbandry_cases hc WHERE hc.owner_id = u.id AND hc.status != 'closed') AS open_case_count
          ) activity ON TRUE
          LEFT JOIN LATERAL (
              SELECT count(*) AS active_session_count
                FROM auth_sessions session_row
               WHERE session_row.user_id = u.id AND session_row.status = 'active'
          ) sessions ON TRUE
          LEFT JOIN LATERAL (
              SELECT count(*) AS pending_report_count
                FROM community_reports cr
                LEFT JOIN community_posts reported_post ON reported_post.id = cr.post_id
                LEFT JOIN community_comments reported_comment ON reported_comment.id = cr.comment_id
               WHERE cr.status = 'pending'
                 AND (reported_post.author_id = u.id OR reported_comment.author_id = u.id)
          ) reports ON TRUE
          LEFT JOIN LATERAL (
              SELECT count(*) AS login_failure_count_7d,
                     max(login_failure.created_at) AS last_login_failure_at
                FROM login_events login_failure
               WHERE login_failure.created_at >= now() - interval '7 days'
                 AND login_failure.event_type IN ('login_failed', 'verification_failed')
                 AND (
                      login_failure.user_id = u.id
                      OR EXISTS (
                          SELECT 1
                            FROM user_identities login_identity
                           WHERE login_identity.user_id = u.id
                             AND login_identity.unbound_at IS NULL
                             AND (
                                  login_identity.email = login_failure.target
                                  OR login_identity.phone_number = login_failure.target
                             )
                      )
                 )
          ) security ON TRUE
         WHERE {where}
         ORDER BY {order_by}
         {pagination}
    """


@router.get("")
def list_users(
    q: str | None = Query(default=None, max_length=100),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(active|disabled|deleted)$"),
    role: str | None = Query(default=None, pattern="^(farmer|agritech|expert|admin)$"),
    verification_status: str | None = Query(default=None, pattern="^(unverified|pending|verified|rejected)$"),
    created_since: str | None = Query(default=None, pattern="^(today|7d)$"),
    attention: str | None = Query(default=None, pattern="^(reports|security|verification)$"),
    sort_by: str = Query(default="attention", alias="sort", pattern="^(attention|last_seen|registered)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("users.read")),
) -> dict:
    filters, values = _build_user_filters(
        q=q,
        status_filter=status_filter,
        role=role,
        verification_status=verification_status,
        created_since=created_since,
        attention=attention,
    )
    where = " AND ".join(filters)
    total = int(
        db.execute(
            text(
                f"""
                SELECT count(DISTINCT u.id)
                  FROM users u
                  LEFT JOIN user_identities i ON i.user_id = u.id AND i.unbound_at IS NULL
                  LEFT JOIN community_profiles cp ON cp.user_id = u.id
                 WHERE {where}
                """
            ),
            values,
        ).scalar()
        or 0
    )
    rows = db.execute(
        text(_select_user_rows(where, _user_sort(sort_by), "LIMIT :limit OFFSET :offset")),
        {**values, "limit": page_size, "offset": (page - 1) * page_size},
    ).mappings().all()
    return {"items": [_user_row(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/export")
def export_users(
    request: Request,
    q: str | None = Query(default=None, max_length=100),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(active|disabled|deleted)$"),
    role: str | None = Query(default=None, pattern="^(farmer|agritech|expert|admin)$"),
    verification_status: str | None = Query(default=None, pattern="^(unverified|pending|verified|rejected)$"),
    created_since: str | None = Query(default=None, pattern="^(today|7d)$"),
    attention: str | None = Query(default=None, pattern="^(reports|security|verification)$"),
    sort_by: str = Query(default="attention", alias="sort", pattern="^(attention|last_seen|registered)$"),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("users.read")),
) -> StreamingResponse:
    filters, values = _build_user_filters(
        q=q,
        status_filter=status_filter,
        role=role,
        verification_status=verification_status,
        created_since=created_since,
        attention=attention,
    )
    where = " AND ".join(filters)
    rows = db.execute(
        text(_select_user_rows(where, _user_sort(sort_by), "LIMIT 10000")),
        values,
    ).mappings().all()
    writer_buffer = StringIO()
    writer = csv.writer(writer_buffer)
    writer.writerow(["用户 ID", "显示名称", "用户名", "角色", "账号状态", "认证状态", "邮箱（脱敏）", "手机号（脱敏）", "注册时间", "最近活跃", "对话数", "帖子数", "未关闭病例"])
    for row in rows:
        item = _user_row(row)
        writer.writerow(
            [
                item["id"],
                item["display_name"],
                item["username"],
                item["role"],
                item["status"],
                item["verification_status"],
                item["email"],
                item["phone_number"],
                item["registered_at"],
                item["last_seen_at"],
                item["conversation_count"],
                item["post_count"],
                item["open_case_count"],
            ]
        )

    write_audit(
        db,
        actor_id=actor.id,
        action="users.exported",
        resource_type="user_export",
        resource_id="filtered_users",
        request=request,
        reason="导出脱敏用户清单",
        after_data={"row_count": len(rows), "filters": {"q": q, "status": status_filter, "role": role, "verification_status": verification_status, "created_since": created_since, "attention": attention, "sort": sort_by}},
    )
    db.commit()
    return StreamingResponse(
        iter(["\ufeff" + writer_buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=canw-users.csv"},
    )


@router.get("/overview")
def users_overview(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("users.read")),
) -> dict:
    summary = db.execute(
        text(
            """
            SELECT
                count(*) FILTER (WHERE u.deleted_at IS NULL) AS total_users,
                count(*) FILTER (WHERE u.deleted_at IS NULL AND u.status = 'active') AS active_users,
                count(*) FILTER (WHERE u.deleted_at IS NULL AND u.status = 'disabled') AS disabled_users,
                count(*) FILTER (WHERE u.deleted_at IS NOT NULL) AS deleted_users,
                count(*) FILTER (WHERE u.deleted_at IS NULL AND u.created_at >= date_trunc('day', now())) AS new_today,
                count(*) FILTER (WHERE u.deleted_at IS NULL AND u.created_at >= now() - interval '7 days') AS new_7d,
                count(*) FILTER (WHERE u.deleted_at IS NULL AND cp.verification_status = 'pending') AS pending_verifications,
                (SELECT count(*) FROM auth_sessions WHERE status = 'active') AS active_sessions,
                (
                    SELECT count(DISTINCT session_row.user_id)
                      FROM auth_sessions session_row
                     WHERE session_row.status = 'active'
                ) AS users_with_active_sessions,
                (
                    SELECT count(DISTINCT reported_user_id)
                      FROM (
                          SELECT reported_post.author_id AS reported_user_id
                            FROM community_reports cr
                            JOIN community_posts reported_post ON reported_post.id = cr.post_id
                           WHERE cr.status = 'pending'
                          UNION ALL
                          SELECT reported_comment.author_id AS reported_user_id
                            FROM community_reports cr
                            JOIN community_comments reported_comment ON reported_comment.id = cr.comment_id
                           WHERE cr.status = 'pending'
                      ) pending_reports
                     WHERE reported_user_id IS NOT NULL
                ) AS users_with_pending_reports,
                (
                    SELECT count(*)
                      FROM (
                          SELECT identity_row.user_id
                            FROM login_events login_failure
                            JOIN user_identities identity_row
                              ON identity_row.unbound_at IS NULL
                             AND (
                                  identity_row.email = login_failure.target
                                  OR identity_row.phone_number = login_failure.target
                             )
                           WHERE login_failure.created_at >= now() - interval '7 days'
                             AND login_failure.event_type IN ('login_failed', 'verification_failed')
                           GROUP BY identity_row.user_id
                          HAVING count(*) >= 3
                      ) security_accounts
                ) AS users_with_security_events
              FROM users u
              LEFT JOIN community_profiles cp ON cp.user_id = u.id
            """
        )
    ).mappings().one()
    return {"summary": dict(summary)}


@router.post("/batch-action")
def batch_action(
    payload: UserBatchActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("users.manage")),
) -> dict:
    user_ids = list(dict.fromkeys(str(user_id) for user_id in payload.user_ids))
    rows = db.execute(
        text(
            """
            SELECT id::text AS id, status, deleted_at
              FROM users
             WHERE id = ANY(CAST(:user_ids AS uuid[]))
            """
        ),
        {"user_ids": user_ids},
    ).mappings().all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可处置的用户")

    eligible_ids = [str(row["id"]) for row in rows if row["deleted_at"] is None]
    skipped_deleted = len(user_ids) - len(eligible_ids)
    changed_ids: list[str] = []
    revoked_user_ids: set[str] = set()
    revoked_session_count = 0

    if payload.action == "disable" and eligible_ids:
        changed_ids = [
            str(row["id"])
            for row in db.execute(
                text(
                    """
                    UPDATE users
                       SET status = 'disabled', updated_at = now()
                     WHERE id = ANY(CAST(:user_ids AS uuid[]))
                       AND deleted_at IS NULL
                       AND status != 'disabled'
                 RETURNING id::text AS id
                    """
                ),
                {"user_ids": eligible_ids},
            ).mappings().all()
        ]
    elif payload.action == "restore" and eligible_ids:
        changed_ids = [
            str(row["id"])
            for row in db.execute(
                text(
                    """
                    UPDATE users
                       SET status = 'active', updated_at = now()
                     WHERE id = ANY(CAST(:user_ids AS uuid[]))
                       AND deleted_at IS NULL
                       AND status = 'disabled'
                 RETURNING id::text AS id
                    """
                ),
                {"user_ids": eligible_ids},
            ).mappings().all()
        ]

    if payload.action in {"disable", "revoke_sessions"} and eligible_ids:
        revoked_rows = db.execute(
                text(
                    """
                    UPDATE auth_sessions
                       SET status = 'revoked', revoked_at = now(), last_used_at = now()
                     WHERE user_id = ANY(CAST(:user_ids AS uuid[]))
                       AND status = 'active'
                 RETURNING user_id::text AS user_id
                    """
                ),
                {"user_ids": eligible_ids},
            ).mappings().all()
        revoked_session_count = len(revoked_rows)
        revoked_user_ids = {str(row["user_id"]) for row in revoked_rows}

    action_type = {
        "disable": "user_disabled",
        "restore": "user_active",
        "revoke_sessions": "user_sessions_revoked",
    }[payload.action]
    history_ids = set(changed_ids) | revoked_user_ids
    for user_id in history_ids:
        db.execute(
            text(
                """
                INSERT INTO admin.moderation_actions (actor_id, target_type, target_id, action_type, reason)
                VALUES (CAST(:actor_id AS uuid), 'user', :target_id, :action_type, :reason)
                """
            ),
            {
                "actor_id": str(actor.id),
                "target_id": user_id,
                "action_type": action_type,
                "reason": payload.reason,
            },
        )

    write_audit(
        db,
        actor_id=actor.id,
        action="users.batch_action",
        resource_type="user_batch",
        resource_id=payload.action,
        request=request,
        reason=payload.reason,
        after_data={
            "action": payload.action,
            "requested_count": len(user_ids),
            "changed_user_count": len(changed_ids),
            "revoked_session_count": revoked_session_count,
            "skipped_deleted_count": skipped_deleted,
        },
    )
    db.commit()
    return {
        "action": payload.action,
        "requested_user_count": len(user_ids),
        "changed_user_count": len(changed_ids),
        "revoked_session_count": revoked_session_count,
        "skipped_deleted_count": skipped_deleted,
    }


@router.get("/{user_id}")
def user_detail(
    user_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("users.read")),
) -> dict:
    values = {"user_id": str(user_id)}
    row = db.execute(
        text(
            """
            SELECT u.id::text AS id, u.display_name, u.username, u.avatar_url, u.role, u.status, u.deleted_at, u.locale, u.timezone,
                   u.registered_at, u.last_seen_at, u.created_at, u.updated_at,
                   MAX(i.email) FILTER (WHERE i.provider = 'email') AS email,
                   MAX(i.phone_number) FILTER (WHERE i.provider = 'phone') AS phone_number,
                   COALESCE(cp.identity_type, 'farmer') AS identity_type, COALESCE(cp.verification_status, 'unverified') AS verification_status,
                   cp.region, cp.organization, cp.expertise_tags, cp.years_experience, cp.bio
              FROM users u
              LEFT JOIN user_identities i ON i.user_id = u.id AND i.unbound_at IS NULL
              LEFT JOIN community_profiles cp ON cp.user_id = u.id
             WHERE u.id = CAST(:user_id AS uuid)
             GROUP BY u.id, cp.user_id
            """
        ),
        values,
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    summary = db.execute(
        text(
            """
            SELECT
              (SELECT count(*) FROM projects WHERE owner_id = CAST(:user_id AS uuid) AND deleted_at IS NULL) AS project_count,
              (SELECT count(*) FROM conversations WHERE user_id = CAST(:user_id AS uuid) AND deleted_at IS NULL) AS conversation_count,
              (SELECT count(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id WHERE c.user_id = CAST(:user_id AS uuid) AND m.deleted_at IS NULL) AS message_count,
              (SELECT count(*) FROM farms WHERE owner_id = CAST(:user_id AS uuid) AND status = 'active') AS farm_count,
              (SELECT count(*) FROM husbandry_cases WHERE owner_id = CAST(:user_id AS uuid) AND status != 'closed') AS open_case_count,
              (SELECT count(*) FROM community_posts WHERE author_id = CAST(:user_id AS uuid) AND deleted_at IS NULL) AS post_count,
              (
                  SELECT count(*)
                    FROM community_reports cr
                    LEFT JOIN community_posts reported_post ON reported_post.id = cr.post_id
                    LEFT JOIN community_comments reported_comment ON reported_comment.id = cr.comment_id
                   WHERE cr.status = 'pending'
                     AND (reported_post.author_id = CAST(:user_id AS uuid) OR reported_comment.author_id = CAST(:user_id AS uuid))
              ) AS pending_report_count,
              (SELECT count(*) FROM auth_sessions WHERE user_id = CAST(:user_id AS uuid) AND status = 'active') AS active_session_count,
              (
                  SELECT count(*)
                    FROM login_events login_failure
                   WHERE login_failure.created_at >= now() - interval '7 days'
                     AND login_failure.event_type IN ('login_failed', 'verification_failed')
                     AND (
                          login_failure.user_id = CAST(:user_id AS uuid)
                          OR EXISTS (
                              SELECT 1
                                FROM user_identities login_identity
                               WHERE login_identity.user_id = CAST(:user_id AS uuid)
                                 AND login_identity.unbound_at IS NULL
                                 AND (
                                      login_identity.email = login_failure.target
                                      OR login_identity.phone_number = login_failure.target
                                 )
                          )
                     )
              ) AS login_failure_count_7d
            """
        ),
        values,
    ).mappings().one()
    sessions = db.execute(
        text(
            """
            SELECT id::text AS id, device_name, device_id, ip_address::text AS ip_address, user_agent,
                   status, created_at, last_used_at, expires_at, revoked_at
              FROM auth_sessions
             WHERE user_id = CAST(:user_id AS uuid)
             ORDER BY CASE WHEN status = 'active' THEN 0 ELSE 1 END, last_used_at DESC NULLS LAST, created_at DESC
             LIMIT 20
            """
        ),
        values,
    ).mappings().all()
    login_events = db.execute(
        text(
            """
            SELECT event_type, failure_reason, ip_address::text AS ip_address, created_at
              FROM login_events WHERE user_id = CAST(:user_id AS uuid)
             ORDER BY created_at DESC LIMIT 20
            """
        ),
        values,
    ).mappings().all()
    moderation = db.execute(
        text(
            """
            SELECT action_type, reason, created_at
              FROM admin.moderation_actions
             WHERE target_type = 'user' AND target_id = :user_id
             ORDER BY created_at DESC LIMIT 20
            """
        ),
        values,
    ).mappings().all()
    activity = db.execute(
        text(
            """
            SELECT * FROM (
              SELECT 'conversation'::text AS type, id::text AS id, title, status, updated_at AS occurred_at
                FROM conversations
               WHERE user_id = CAST(:user_id AS uuid) AND deleted_at IS NULL
              UNION ALL
              SELECT 'case'::text AS type, id::text AS id, title, status, updated_at AS occurred_at
                FROM husbandry_cases
               WHERE owner_id = CAST(:user_id AS uuid)
              UNION ALL
              SELECT 'post'::text AS type, id::text AS id, title, status, updated_at AS occurred_at
                FROM community_posts
               WHERE author_id = CAST(:user_id AS uuid) AND deleted_at IS NULL
            ) AS user_activity
            ORDER BY occurred_at DESC
            LIMIT 18
            """
        ),
        values,
    ).mappings().all()

    attention_level = (
        "reports" if int(summary["pending_report_count"] or 0) > 0
        else "security" if int(summary["login_failure_count_7d"] or 0) >= 3
        else "verification" if row["verification_status"] == "pending"
        else "none"
    )
    response = _user_row({**dict(row), "attention_level": attention_level})
    response.update(
        {
            "avatar_url": row["avatar_url"],
            "locale": row["locale"],
            "timezone": row["timezone"],
            "deleted_at": row["deleted_at"],
            "identity_type": row["identity_type"],
            "profile": {
                "region": row["region"],
                "organization": row["organization"],
                "expertise_tags": row["expertise_tags"] or [],
                "years_experience": row["years_experience"],
                "bio": row["bio"],
            },
            "summary": dict(summary),
            "sessions": [dict(item) for item in sessions],
            "login_events": [dict(event) for event in login_events],
            "moderation_history": [dict(item) for item in moderation],
            "activity": [dict(item) for item in activity],
        }
    )
    return response


@router.patch("/{user_id}/status")
def update_status(
    user_id: UUID,
    payload: UserStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("users.manage")),
) -> dict:
    row = db.execute(text("SELECT status, deleted_at FROM users WHERE id = CAST(:user_id AS uuid)"), {"user_id": str(user_id)}).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if row["deleted_at"] is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已删除账号仅供审计查看，不能恢复或变更状态")
    if row["status"] == payload.status:
        return {"id": str(user_id), "status": payload.status, "revoked_sessions": 0, "changed": False}
    db.execute(text("UPDATE users SET status = :status, updated_at = now() WHERE id = CAST(:user_id AS uuid)"), {"user_id": str(user_id), "status": payload.status})
    revoked = 0
    if payload.status == "disabled":
        revoked = int(
            db.execute(
                text(
                    """
                    WITH changed AS (
                        UPDATE auth_sessions SET status = 'revoked', revoked_at = now(), last_used_at = now()
                         WHERE user_id = CAST(:user_id AS uuid) AND status = 'active'
                     RETURNING id
                    ) SELECT count(*) FROM changed
                    """
                ),
                {"user_id": str(user_id)},
            ).scalar()
            or 0
        )
    db.execute(
        text(
            """
            INSERT INTO admin.moderation_actions (actor_id, target_type, target_id, action_type, reason)
            VALUES (CAST(:actor_id AS uuid), 'user', :target_id, :action_type, :reason)
            """
        ),
        {"actor_id": str(actor.id), "target_id": str(user_id), "action_type": f"user_{payload.status}", "reason": payload.reason},
    )
    write_audit(
        db,
        actor_id=actor.id,
        action="users.status_changed",
        resource_type="user",
        resource_id=str(user_id),
        request=request,
        reason=payload.reason,
        before_data={"status": row["status"]},
        after_data={"status": payload.status, "revoked_sessions": revoked},
    )
    db.commit()
    return {"id": str(user_id), "status": payload.status, "revoked_sessions": revoked, "changed": True}


@router.post("/{user_id}/sessions/revoke")
def revoke_sessions(
    user_id: UUID,
    payload: RevokeSessionsRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("users.manage")),
) -> dict:
    _require_existing_user(db, user_id)
    revoked = int(
        db.execute(
            text(
                """
                WITH changed AS (
                    UPDATE auth_sessions SET status = 'revoked', revoked_at = now(), last_used_at = now()
                     WHERE user_id = CAST(:user_id AS uuid) AND status = 'active'
                 RETURNING id
                ) SELECT count(*) FROM changed
                """
            ),
            {"user_id": str(user_id)},
        ).scalar()
        or 0
    )
    write_audit(
        db,
        actor_id=actor.id,
        action="users.sessions_revoked",
        resource_type="user",
        resource_id=str(user_id),
        request=request,
        reason=payload.reason,
        after_data={"revoked_sessions": revoked},
    )
    db.commit()
    return {"id": str(user_id), "revoked_sessions": revoked}


@router.post("/{user_id}/sessions/{session_id}/revoke")
def revoke_session(
    user_id: UUID,
    session_id: UUID,
    payload: RevokeSessionsRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("users.manage")),
) -> dict:
    _require_existing_user(db, user_id)
    existing = db.execute(
        text(
            """
            SELECT id::text AS id, status, device_name, ip_address::text AS ip_address
              FROM auth_sessions
             WHERE id = CAST(:session_id AS uuid) AND user_id = CAST(:user_id AS uuid)
            """
        ),
        {"session_id": str(session_id), "user_id": str(user_id)},
    ).mappings().first()
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="登录会话不存在")

    revoked = existing["status"] == "active"
    if revoked:
        db.execute(
            text(
                """
                UPDATE auth_sessions
                   SET status = 'revoked', revoked_at = now(), last_used_at = now()
                 WHERE id = CAST(:session_id AS uuid)
                """
            ),
            {"session_id": str(session_id)},
        )
    write_audit(
        db,
        actor_id=actor.id,
        action="users.session_revoked",
        resource_type="user_session",
        resource_id=str(session_id),
        request=request,
        reason=payload.reason,
        before_data={"status": existing["status"], "device_name": existing["device_name"], "ip_address": existing["ip_address"]},
        after_data={"status": "revoked", "changed": revoked},
    )
    db.commit()
    return {"id": str(session_id), "status": "revoked", "changed": revoked}


def _user_row(row: object) -> dict:
    value = dict(row)
    return {
        "id": value["id"],
        "display_name": value.get("display_name") or value.get("username") or "未命名用户",
        "username": value.get("username") or "",
        "role": value.get("role"),
        "status": "deleted" if value.get("deleted_at") else value.get("status"),
        "email": _mask_email(value.get("email")),
        "phone_number": _mask_phone(value.get("phone_number")),
        "verification_status": value.get("verification_status", "unverified"),
        "registered_at": value.get("registered_at") or value.get("created_at"),
        "last_seen_at": value.get("last_seen_at"),
        "conversation_count": int(value.get("conversation_count") or 0),
        "post_count": int(value.get("post_count") or 0),
        "open_case_count": int(value.get("open_case_count") or 0),
        "active_session_count": int(value.get("active_session_count") or 0),
        "pending_report_count": int(value.get("pending_report_count") or 0),
        "login_failure_count_7d": int(value.get("login_failure_count_7d") or 0),
        "last_login_failure_at": value.get("last_login_failure_at"),
        "attention_level": value.get("attention_level") or "none",
    }


def _require_existing_user(db: Session, user_id: UUID) -> None:
    exists = db.execute(text("SELECT 1 FROM users WHERE id = CAST(:user_id AS uuid)"), {"user_id": str(user_id)}).scalar()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")


def _mask_email(value: object) -> str:
    email = str(value or "")
    if not email or "@" not in email:
        return ""
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def _mask_phone(value: object) -> str:
    phone = str(value or "")
    return f"***{phone[-4:]}" if len(phone) >= 4 else ""

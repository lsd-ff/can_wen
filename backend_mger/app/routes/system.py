from __future__ import annotations

from datetime import date, datetime, timedelta
from time import perf_counter
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.dependencies import require_permission
from app.models import AdminAccount, AdminAccountRole, AdminPermission, AdminRole, AdminRolePermission, BackgroundJob, KnowledgeBuildEvent, KnowledgeBuildRun, KnowledgePublication, KnowledgeSource, KnowledgeSourceVersion, RiskIncident, RiskIncidentActivity, RiskNotificationReceipt, SensitiveAccessGrant, ServiceHealthSnapshot, SystemModelConfig, SystemSetting
from app.schemas import AdminRoleAssignmentRequest, AssetLifecycleRequest, InviteCreateRequest, JobActionRequest, ModelConfigRequest, ReasonRequest, RiskIncidentActionRequest, RoleUpsertRequest, SystemSettingRequest, UserStatusRequest
from app.security import decrypt_secret, encrypt_secret, now_utc
from app.services import AdminActor, DEFAULT_REVIEW_THRESHOLDS, PERMISSIONS, create_invite, recalculate_active_work_item_slas, work_item_sla_hours, write_audit


router = APIRouter(tags=["system"])
settings = get_settings()


HIGH_RISK_AUDIT_ACTIONS = (
    "admins.status_changed",
    "admins.roles_changed",
    "roles.created",
    "roles.updated",
    "roles.deleted",
    "sensitive_access.granted",
    "sensitive_access.used",
    "settings.updated",
    "risk_rules.updated",
    "models.created",
    "models.updated",
    "assets.quarantine",
    "assets.delete",
    "risk_events.dismiss",
    "risk_events.suppress",
    "health.settings_updated",
)


def _role_permissions(db: Session, role_id: UUID) -> list[str]:
    return sorted(db.scalars(
        select(AdminPermission.key)
        .join(AdminRolePermission, AdminRolePermission.permission_id == AdminPermission.id)
        .where(AdminRolePermission.role_id == role_id)
    ).all())


def _role_impact(db: Session, role_id: UUID) -> dict:
    assigned_admins = [
        dict(row)
        for row in db.execute(text("""
            SELECT aa.id::text AS id, aa.display_name, aa.email, aa.status, aa.mfa_enrolled
              FROM admin.admin_account_roles aar
              JOIN admin.admin_accounts aa ON aa.id = aar.admin_account_id
             WHERE aar.role_id = CAST(:role_id AS uuid)
             ORDER BY aa.status = 'active' DESC, aa.display_name ASC
        """), {"role_id": str(role_id)}).mappings().all()
    ]
    active_session_count = int(db.execute(text("""
        SELECT count(*)
          FROM admin.admin_sessions s
          JOIN admin.admin_account_roles aar ON aar.admin_account_id = s.admin_account_id
         WHERE aar.role_id = CAST(:role_id AS uuid)
           AND s.status = 'active'
    """), {"role_id": str(role_id)}).scalar() or 0)
    return {
        "assigned_admins": assigned_admins,
        "assigned_admin_count": len(assigned_admins),
        "active_session_count": active_session_count,
    }


def _role_payload(db: Session, role: AdminRole) -> dict:
    return {
        "id": str(role.id),
        "key": role.key,
        "label": role.label,
        "description": role.description,
        "is_system": role.is_system,
        "permissions": _role_permissions(db, role.id),
        **_role_impact(db, role.id),
    }




DEFAULT_RISK_RULES = {
    "login_failure_count": 3,
    "login_failure_window_hours": 24,
    "unusual_ip_count": 3,
    "unusual_ip_window_hours": 24,
    "report_surge_count": 3,
    "report_surge_window_hours": 24,
    "posting_spike_count": 5,
    "posting_spike_window_hours": 1,
    "critical_case_sla_hours": 4,
    "notification_window_minutes": 30,
    "suppression_default_hours": 24,
    "sla_hours": {"critical": 4, "high": 24, "medium": 72, "low": 168},
}


# This query only emits administrator-facing anomalies. Each source carries a stable
# resource identity so the incident store can deduplicate repeated detections.
RISK_EVENT_SOURCES_SQL = """
    WITH risk_events AS (
        SELECT
            'repeated_login_failure'::text AS type,
            'high'::text AS risk_level,
            COALESCE(target, '未知账号') AS subject,
            format('同一来源在 %s 小时内登录或验证失败 %s 次', :login_failure_window_hours, count(*)) AS detail,
            ip_address::text AS ip_address,
            max(created_at) AS created_at,
            'login_identity'::text AS resource_type,
            concat_ws('|', COALESCE(target, 'unknown'), COALESCE(ip_address::text, 'unknown')) AS resource_id,
            count(*)::integer AS detected_count,
            jsonb_build_array(
                jsonb_build_object('label', '失败次数', 'value', count(*)),
                jsonb_build_object('label', '观测窗口', 'value', concat(:login_failure_window_hours, ' 小时')),
                jsonb_build_object('label', '来源 IP', 'value', COALESCE(ip_address::text, '未记录'))
            ) AS evidence
          FROM login_events
         WHERE event_type IN ('login_failed', 'verification_failed')
           AND created_at >= now() - (:login_failure_window_hours * interval '1 hour')
         GROUP BY target, ip_address
        HAVING count(*) >= :login_failure_count

        UNION ALL

        SELECT
            'unusual_login_ip'::text AS type,
            'medium'::text AS risk_level,
            COALESCE(NULLIF(u.display_name, ''), NULLIF(u.username, ''), le.target, le.user_id::text, '未知用户') AS subject,
            format('%s 小时内从 %s 个不同 IP 登录', :unusual_ip_window_hours, count(DISTINCT le.ip_address)) AS detail,
            NULL::text AS ip_address,
            max(le.created_at) AS created_at,
            'user'::text AS resource_type,
            COALESCE(le.user_id::text, le.target, 'unknown') AS resource_id,
            count(DISTINCT le.ip_address)::integer AS detected_count,
            jsonb_build_array(
                jsonb_build_object('label', '不同 IP', 'value', count(DISTINCT le.ip_address)),
                jsonb_build_object('label', '观测窗口', 'value', concat(:unusual_ip_window_hours, ' 小时'))
            ) AS evidence
          FROM login_events le
          LEFT JOIN users u ON u.id = le.user_id
         WHERE le.event_type = 'login_success'
           AND le.ip_address IS NOT NULL
           AND le.created_at >= now() - (:unusual_ip_window_hours * interval '1 hour')
         GROUP BY le.user_id, u.display_name, u.username, le.target
        HAVING count(DISTINCT le.ip_address) >= :unusual_ip_count

        UNION ALL

        SELECT
            'admin_permission_change'::text AS type,
            'high'::text AS risk_level,
            COALESCE(NULLIF(aa.display_name, ''), aa.email, al.resource_type || ' · ' || al.resource_id) AS subject,
            concat('管理员高权限操作：', al.action, COALESCE('；' || al.reason, '')) AS detail,
            al.ip_address,
            al.created_at,
            'audit_log'::text AS resource_type,
            al.id::text AS resource_id,
            1 AS detected_count,
            jsonb_build_array(
                jsonb_build_object('label', '审计动作', 'value', al.action),
                jsonb_build_object('label', '关联对象', 'value', concat(al.resource_type, ' · ', al.resource_id)),
                jsonb_build_object('label', '处理理由', 'value', COALESCE(al.reason, '未填写'))
            ) AS evidence
          FROM admin.audit_logs al
          LEFT JOIN admin.admin_accounts aa ON aa.id = al.actor_id
         WHERE al.action IN ('admins.status_changed', 'admins.roles_changed', 'roles.created', 'roles.updated', 'roles.deleted', 'settings.updated')
           AND al.created_at >= now() - interval '7 days'

        UNION ALL

        SELECT
            'sensitive_admin_action'::text AS type,
            'medium'::text AS risk_level,
            COALESCE(NULLIF(aa.display_name, ''), aa.email, al.resource_type || ' · ' || al.resource_id) AS subject,
            concat('敏感管理操作：', al.action, COALESCE('；' || al.reason, '')) AS detail,
            al.ip_address,
            al.created_at,
            'audit_log'::text AS resource_type,
            al.id::text AS resource_id,
            1 AS detected_count,
            jsonb_build_array(
                jsonb_build_object('label', '审计动作', 'value', al.action),
                jsonb_build_object('label', '关联对象', 'value', concat(al.resource_type, ' · ', al.resource_id)),
                jsonb_build_object('label', '处理理由', 'value', COALESCE(al.reason, '未填写'))
            ) AS evidence
          FROM admin.audit_logs al
          LEFT JOIN admin.admin_accounts aa ON aa.id = al.actor_id
         WHERE al.action IN ('sensitive_access.granted', 'sensitive_access.used', 'users.sessions_revoked', 'users.status_changed')
           AND al.created_at >= now() - interval '7 days'

        UNION ALL

        SELECT
            'multimodal_failure'::text AS type,
            'high'::text AS risk_level,
            COALESCE(NULLIF(c.title, ''), '多模态问诊') AS subject,
            COALESCE(dma.error_message, '多模态解析失败，请检查模型能力与请求参数') AS detail,
            NULL::text AS ip_address,
            dma.created_at,
            'conversation'::text AS resource_type,
            dma.conversation_id::text AS resource_id,
            1 AS detected_count,
            jsonb_build_array(
                jsonb_build_object('label', '分析任务', 'value', dma.id::text),
                jsonb_build_object('label', '任务状态', 'value', dma.status),
                jsonb_build_object('label', '失败信息', 'value', COALESCE(dma.error_message, '未记录'))
            ) AS evidence
          FROM diagnosis_multimodal_analyses dma
          LEFT JOIN conversations c ON c.id = dma.conversation_id
         WHERE dma.status = 'failed'
           AND dma.created_at >= now() - interval '7 days'

        UNION ALL

        SELECT
            'background_job_failure'::text AS type,
            'high'::text AS risk_level,
            bj.job_type AS subject,
            COALESCE(bj.error_message, '后台任务失败，请查看任务日志') AS detail,
            NULL::text AS ip_address,
            bj.updated_at AS created_at,
            'background_job'::text AS resource_type,
            bj.id::text AS resource_id,
            1 AS detected_count,
            jsonb_build_array(
                jsonb_build_object('label', '任务类型', 'value', bj.job_type),
                jsonb_build_object('label', '任务状态', 'value', bj.status),
                jsonb_build_object('label', '任务进度', 'value', bj.progress)
            ) AS evidence
          FROM admin.background_jobs bj
         WHERE bj.status = 'failed'
           AND bj.updated_at >= now() - interval '7 days'

        UNION ALL

        SELECT
            'report_surge'::text AS type,
            'high'::text AS risk_level,
            COALESCE(NULLIF(cp.title, ''), cr.post_id::text) AS subject,
            format('%s 小时内收到 %s 条待审核举报，请关注是否存在恶意内容或集中举报', :report_surge_window_hours, count(*)) AS detail,
            NULL::text AS ip_address,
            max(cr.created_at) AS created_at,
            'community_post'::text AS resource_type,
            cr.post_id::text AS resource_id,
            count(*)::integer AS detected_count,
            jsonb_build_array(
                jsonb_build_object('label', '待审核举报', 'value', count(*)),
                jsonb_build_object('label', '观测窗口', 'value', concat(:report_surge_window_hours, ' 小时')),
                jsonb_build_object('label', '帖子 ID', 'value', cr.post_id::text)
            ) AS evidence
          FROM community_reports cr
          LEFT JOIN community_posts cp ON cp.id = cr.post_id
         WHERE cr.status = 'pending'
           AND cr.created_at >= now() - (:report_surge_window_hours * interval '1 hour')
         GROUP BY cr.post_id, cp.title
        HAVING count(*) >= :report_surge_count

        UNION ALL

        SELECT
            'posting_spike'::text AS type,
            'medium'::text AS risk_level,
            COALESCE(NULLIF(u.display_name, ''), NULLIF(u.username, ''), cp.author_id::text) AS subject,
            format('%s 小时内发布 %s 条公开内容，请核查是否为异常发布', :posting_spike_window_hours, count(*)) AS detail,
            NULL::text AS ip_address,
            max(cp.created_at) AS created_at,
            'user'::text AS resource_type,
            cp.author_id::text AS resource_id,
            count(*)::integer AS detected_count,
            jsonb_build_array(
                jsonb_build_object('label', '公开内容数', 'value', count(*)),
                jsonb_build_object('label', '观测窗口', 'value', concat(:posting_spike_window_hours, ' 小时'))
            ) AS evidence
          FROM community_posts cp
          LEFT JOIN users u ON u.id = cp.author_id
         WHERE cp.status = 'published'
           AND cp.created_at >= now() - (:posting_spike_window_hours * interval '1 hour')
         GROUP BY cp.author_id, u.display_name, u.username
        HAVING count(*) >= :posting_spike_count

        UNION ALL

        SELECT
            'critical_case_overdue'::text AS type,
            'critical'::text AS risk_level,
            concat(COALESCE(NULLIF(hc.title, ''), '未命名病例'), ' · ', COALESCE(f.name, '未关联养殖场')) AS subject,
            format('紧急病例已超过 %s 小时，仍未发布专家复核意见', :critical_case_sla_hours) AS detail,
            NULL::text AS ip_address,
            hc.updated_at AS created_at,
            'husbandry_case'::text AS resource_type,
            hc.id::text AS resource_id,
            1 AS detected_count,
            jsonb_build_array(
                jsonb_build_object('label', '严重等级', 'value', hc.severity),
                jsonb_build_object('label', '未复核时长', 'value', concat(:critical_case_sla_hours, ' 小时以上')),
                jsonb_build_object('label', '养殖场', 'value', COALESCE(f.name, '未关联'))
            ) AS evidence
          FROM husbandry_cases hc
          LEFT JOIN farms f ON f.id = hc.farm_id
         WHERE hc.severity = 'critical'
           AND hc.status <> 'closed'
           AND hc.updated_at <= now() - (:critical_case_sla_hours * interval '1 hour')
           AND NOT EXISTS (
                SELECT 1
                  FROM admin.expert_reviews er
                 WHERE er.husbandry_case_id = hc.id
                   AND er.status = 'published'
           )
    )
    SELECT risk_events.*, md5(concat_ws('|', type, resource_type, resource_id)) AS fingerprint
      FROM risk_events
     ORDER BY created_at DESC
     LIMIT 100
"""


RISK_STATUS_LABELS = {
    "open": "待响应",
    "acknowledged": "已确认",
    "in_progress": "处理中",
    "resolved": "已解决",
    "dismissed": "已忽略",
    "suppressed": "已抑制",
}
RISK_PRIORITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _risk_rules(db: Session) -> dict:
    item = db.scalar(select(SystemSetting).where(SystemSetting.key == "risk_rules"))
    saved = item.value if item is not None and isinstance(item.value, dict) else {}
    rules = {**DEFAULT_RISK_RULES, **{key: value for key, value in saved.items() if key != "sla_hours"}}
    saved_sla = saved.get("sla_hours") if isinstance(saved.get("sla_hours"), dict) else {}
    rules["sla_hours"] = {**DEFAULT_RISK_RULES["sla_hours"], **saved_sla}
    return rules


def _risk_event_params(rules: dict) -> dict:
    return {
        "login_failure_count": int(rules["login_failure_count"]),
        "login_failure_window_hours": int(rules["login_failure_window_hours"]),
        "unusual_ip_count": int(rules["unusual_ip_count"]),
        "unusual_ip_window_hours": int(rules["unusual_ip_window_hours"]),
        "report_surge_count": int(rules["report_surge_count"]),
        "report_surge_window_hours": int(rules["report_surge_window_hours"]),
        "posting_spike_count": int(rules["posting_spike_count"]),
        "posting_spike_window_hours": int(rules["posting_spike_window_hours"]),
        "critical_case_sla_hours": int(rules["critical_case_sla_hours"]),
    }


def _risk_due_at(created_at, priority: str, rules: dict):
    hours = int((rules.get("sla_hours") or DEFAULT_RISK_RULES["sla_hours"]).get(priority, DEFAULT_RISK_RULES["sla_hours"][priority]))
    return created_at + timedelta(hours=hours)


def _risk_destination(resource_type: str, resource_id: str) -> dict:
    destinations = {
        "user": {"hash": f"/users?id={resource_id}", "label": "查看用户档案"},
        "conversation": {"hash": f"/diagnosis?tab=reviews&conversation_id={resource_id}", "label": "查看关联问诊"},
        "husbandry_case": {"hash": f"/husbandry?case_id={resource_id}", "label": "查看关联病例"},
        "background_job": {"hash": "/models?tab=jobs&job_status=failed", "label": "查看失败任务"},
        "audit_log": {"hash": f"/system?tab=audit&resource_id={resource_id}", "label": "查看审计记录"},
        "community_post": {"hash": "/community?tab=posts", "label": "查看社区内容"},
        "login_identity": {"hash": "/users", "label": "查看关联账户"},
        "service": {"hash": "/operations?tab=health", "label": "查看服务健康"},
    }
    return destinations.get(resource_type, {"hash": "/operations", "label": "返回风险事件"})


def _risk_activity(db: Session, incident: RiskIncident, activity_type: str, content: str, *, actor_id: UUID | None = None, metadata: dict | None = None) -> None:
    db.add(RiskIncidentActivity(incident_id=incident.id, actor_id=actor_id, activity_type=activity_type, content=content, metadata_=metadata or {}))


def _escalate_overdue_incidents(db: Session, incidents: list[RiskIncident]) -> None:
    now = now_utc()
    for incident in incidents:
        if incident.status not in {"open", "acknowledged", "in_progress"} or incident.due_at is None or incident.due_at > now:
            continue
        current_rank = RISK_PRIORITY_ORDER.get(incident.priority, 0)
        if current_rank >= RISK_PRIORITY_ORDER["critical"]:
            continue
        next_priority = next(level for level, rank in RISK_PRIORITY_ORDER.items() if rank == current_rank + 1)
        before = incident.priority
        incident.priority, incident.updated_at, incident.version = next_priority, now, incident.version + 1
        _risk_activity(db, incident, "sla_escalated", f"已超过 SLA，优先级由 {before} 升级为 {next_priority}", metadata={"before": before, "after": next_priority})


def _sync_risk_incidents(db: Session, rules: dict) -> list[RiskIncident]:
    rows = [dict(row) for row in db.execute(text(RISK_EVENT_SOURCES_SQL), _risk_event_params(rules)).mappings().all()]
    fingerprints = [str(row["fingerprint"]) for row in rows]
    existing = {
        incident.fingerprint: incident
        for incident in db.scalars(select(RiskIncident).where(RiskIncident.fingerprint.in_(fingerprints))).all()
    } if fingerprints else {}
    now = now_utc()
    for row in rows:
        fingerprint = str(row["fingerprint"])
        detected_at = row["created_at"]
        incident = existing.get(fingerprint)
        metadata = {"ip_address": row.get("ip_address"), "evidence": row.get("evidence") or [], "detected_count": int(row.get("detected_count") or 1)}
        if incident is None:
            incident = RiskIncident(
                fingerprint=fingerprint,
                risk_type=str(row["type"]),
                risk_level=str(row["risk_level"]),
                priority=str(row["risk_level"]),
                subject=str(row["subject"]),
                detail=str(row["detail"]),
                resource_type=str(row["resource_type"]),
                resource_id=str(row["resource_id"]),
                first_seen_at=detected_at,
                last_detected_at=detected_at,
                last_seen_at=now,
                due_at=_risk_due_at(detected_at, str(row["risk_level"]), rules),
                metadata_=metadata,
            )
            db.add(incident)
            db.flush()
            _risk_activity(db, incident, "detected", "系统检测到新的风险信号", metadata={"type": row["type"], "evidence": metadata["evidence"]})
            existing[fingerprint] = incident
            continue

        has_new_signal = detected_at > incident.last_detected_at
        previous_status = incident.status
        incident.risk_level = str(row["risk_level"])
        incident.subject = str(row["subject"])
        incident.detail = str(row["detail"])
        incident.resource_type = str(row["resource_type"])
        incident.resource_id = str(row["resource_id"])
        incident.last_seen_at = now
        incident.metadata_ = metadata
        incident.updated_at = now
        if has_new_signal:
            incident.last_detected_at = detected_at
            if incident.status in {"resolved", "dismissed"} or (incident.status == "suppressed" and (incident.suppressed_until is None or incident.suppressed_until <= now)):
                incident.status = "open"
                incident.resolved_at = None
                incident.suppressed_until = None
                incident.priority = str(row["risk_level"])
                incident.due_at = _risk_due_at(detected_at, incident.priority, rules)
                _risk_activity(db, incident, "reopened", "检测到新的同类风险信号，事件已重新打开", metadata={"previous_status": previous_status})
            else:
                _risk_activity(db, incident, "signal_updated", "风险信号已更新", metadata={"evidence": metadata["evidence"]})
        incident.version += 1

    all_incidents = list(existing.values())
    _escalate_overdue_incidents(db, all_incidents)
    db.flush()
    return all_incidents


def _risk_sla_state(incident: RiskIncident) -> str:
    if incident.status in {"resolved", "dismissed", "suppressed"}:
        return "closed"
    if incident.due_at is None:
        return "on_track"
    remaining = incident.due_at - now_utc()
    if remaining.total_seconds() < 0:
        return "overdue"
    if remaining.total_seconds() <= 4 * 3600:
        return "due_soon"
    return "on_track"


def _risk_incident_dict(incident: RiskIncident, *, assignee_name: str | None = None) -> dict:
    return {
        "id": str(incident.id),
        "fingerprint": incident.fingerprint,
        "type": incident.risk_type,
        "risk_level": incident.risk_level,
        "priority": incident.priority,
        "subject": incident.subject,
        "detail": incident.detail,
        "resource_type": incident.resource_type,
        "resource_id": incident.resource_id,
        "status": incident.status,
        "status_label": RISK_STATUS_LABELS[incident.status],
        "assignee_id": str(incident.assignee_id) if incident.assignee_id else None,
        "assignee_name": assignee_name,
        "due_at": incident.due_at,
        "first_seen_at": incident.first_seen_at,
        "last_detected_at": incident.last_detected_at,
        "last_seen_at": incident.last_seen_at,
        "resolved_at": incident.resolved_at,
        "suppressed_until": incident.suppressed_until,
        "sla_state": _risk_sla_state(incident),
        "evidence": incident.metadata_.get("evidence", []),
        "ip_address": incident.metadata_.get("ip_address"),
        "detected_count": incident.metadata_.get("detected_count", 1),
        "destination": _risk_destination(incident.resource_type, incident.resource_id),
        "version": incident.version,
    }


def _risk_assignee_names(db: Session, incidents: list[RiskIncident]) -> dict[UUID, str]:
    assignee_ids = {incident.assignee_id for incident in incidents if incident.assignee_id}
    if not assignee_ids:
        return {}
    return {
        account.id: account.display_name
        for account in db.scalars(select(AdminAccount).where(AdminAccount.id.in_(assignee_ids))).all()
    }


def _risk_summary(incidents: list[RiskIncident]) -> dict:
    active = [item for item in incidents if item.status in {"open", "acknowledged", "in_progress"}]
    return {
        "active": len(active),
        "critical": sum(item.priority == "critical" for item in active),
        "overdue": sum(_risk_sla_state(item) == "overdue" for item in active),
        "unassigned": sum(item.assignee_id is None for item in active),
        "suppressed": sum(item.status == "suppressed" for item in incidents),
    }


@router.get("/admins")
def admins(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("admins.read")),
) -> dict:
    rows = db.execute(text("""
        SELECT aa.id::text AS id, aa.email, aa.display_name, aa.status, aa.mfa_enrolled, aa.last_seen_at, aa.created_at,
               COALESCE(array_agg(ar.key) FILTER (WHERE ar.key IS NOT NULL), '{}') AS roles
          FROM admin.admin_accounts aa
          LEFT JOIN admin.admin_account_roles aar ON aar.admin_account_id = aa.id
          LEFT JOIN admin.roles ar ON ar.id = aar.role_id
         GROUP BY aa.id ORDER BY aa.created_at DESC
    """)).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/admins/invitations")
def invite_admin(
    payload: InviteCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("admins.manage")),
) -> dict:
    invite, token = create_invite(db, actor=actor, email=payload.email, display_name=payload.display_name, role_keys=payload.role_keys, expires_in_hours=payload.expires_in_hours, request=request)
    return {"id": str(invite.id), "email": invite.email, "role_keys": invite.role_keys, "expires_at": invite.expires_at, "invitation_token": token}


@router.patch("/admins/{account_id}/status")
def update_admin_status(
    account_id: UUID,
    payload: UserStatusRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("admins.manage")),
) -> dict:
    account = db.get(AdminAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="管理员不存在")
    if account.id == actor.id and payload.status == "disabled":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能禁用当前登录的管理员")
    before = account.status
    account.status = payload.status
    if payload.status == "disabled":
        db.execute(text("UPDATE admin.admin_sessions SET status = 'revoked', revoked_at = now() WHERE admin_account_id = CAST(:account_id AS uuid) AND status = 'active'"), {"account_id": str(account_id)})
    write_audit(db, actor_id=actor.id, action="admins.status_changed", resource_type="admin_account", resource_id=str(account_id), request=request, reason=payload.reason, before_data={"status": before}, after_data={"status": payload.status})
    db.commit()
    return {"id": str(account.id), "status": account.status}


@router.patch("/admins/{account_id}/roles")
def assign_admin_roles(
    account_id: UUID,
    payload: AdminRoleAssignmentRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("admins.manage")),
) -> dict:
    account = db.get(AdminAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="管理员不存在")
    role_keys = list(dict.fromkeys(key.strip() for key in payload.role_keys if key.strip()))
    roles = db.scalars(select(AdminRole).where(AdminRole.key.in_(role_keys))).all()
    if len(roles) != len(role_keys):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="包含不存在的角色")
    current_roles = db.scalars(
        select(AdminRole.key)
        .join(AdminAccountRole, AdminAccountRole.role_id == AdminRole.id)
        .where(AdminAccountRole.admin_account_id == account.id)
    ).all()
    if account.id == actor.id and set(current_roles) != set(role_keys):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能在当前会话中修改自己的角色，请由另一位超级管理员操作")
    if "super_admin" in current_roles and "super_admin" not in role_keys:
        other_super_admins = int(db.execute(text("""
            SELECT count(*) FROM admin.admin_account_roles aar
            JOIN admin.admin_accounts aa ON aa.id = aar.admin_account_id
            JOIN admin.roles ar ON ar.id = aar.role_id
            WHERE ar.key = 'super_admin' AND aa.status = 'active' AND aa.id <> CAST(:account_id AS uuid)
        """), {"account_id": str(account.id)}).scalar() or 0)
        if other_super_admins == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="至少保留一名启用的超级管理员")
    db.execute(delete(AdminAccountRole).where(AdminAccountRole.admin_account_id == account.id))
    db.add_all(AdminAccountRole(admin_account_id=account.id, role_id=role.id) for role in roles)
    db.execute(text("UPDATE admin.admin_sessions SET status = 'revoked', revoked_at = now() WHERE admin_account_id = CAST(:account_id AS uuid) AND status = 'active'"), {"account_id": str(account.id)})
    write_audit(db, actor_id=actor.id, action="admins.roles_changed", resource_type="admin_account", resource_id=str(account.id), request=request, reason=payload.reason, before_data={"roles": sorted(current_roles)}, after_data={"roles": sorted(role_keys), "sessions_revoked": True})
    db.commit()
    return {"id": str(account.id), "roles": sorted(role_keys)}


@router.get("/roles")
def roles(db: Session = Depends(get_db), actor: AdminActor = Depends(require_permission("roles.read"))) -> dict:
    roles = db.scalars(select(AdminRole).order_by(AdminRole.is_system.desc(), AdminRole.key)).all()
    return {
        "items": [_role_payload(db, role) for role in roles],
        "available_permissions": [{"key": key, "label": label, "group": group} for key, label, group in PERMISSIONS],
    }


@router.get("/roles/{role_id}/impact")
def role_impact(
    role_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("roles.read")),
) -> dict:
    role = db.get(AdminRole, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    return {"role": _role_payload(db, role), **_role_impact(db, role.id)}


@router.post("/roles")
def create_role(
    payload: RoleUpsertRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("roles.manage")),
) -> dict:
    if db.scalar(select(AdminRole).where(AdminRole.key == payload.key)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="角色标识已存在")
    permission_keys = list(dict.fromkeys(payload.permission_keys))
    permissions = db.scalars(select(AdminPermission).where(AdminPermission.key.in_(permission_keys))).all()
    if len(permissions) != len(permission_keys):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="包含不存在的权限")
    role = AdminRole(key=payload.key, label=payload.label.strip(), description=payload.description.strip(), is_system=False)
    db.add(role)
    db.flush()
    db.add_all(AdminRolePermission(role_id=role.id, permission_id=permission.id) for permission in permissions)
    write_audit(db, actor_id=actor.id, action="roles.created", resource_type="admin_role", resource_id=str(role.id), request=request, reason=payload.reason, after_data={"key": role.key, "permissions": sorted(permission_keys)})
    db.commit()
    return _role_payload(db, role)


@router.put("/roles/{role_id}")
def update_role(
    role_id: UUID,
    payload: RoleUpsertRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("roles.manage")),
) -> dict:
    role = db.get(AdminRole, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="系统预置角色不可编辑，请创建自定义角色")
    duplicate = db.scalar(select(AdminRole).where(AdminRole.key == payload.key, AdminRole.id != role.id))
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="角色标识已存在")
    permission_keys = list(dict.fromkeys(payload.permission_keys))
    permissions = db.scalars(select(AdminPermission).where(AdminPermission.key.in_(permission_keys))).all()
    if len(permissions) != len(permission_keys):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="包含不存在的权限")
    if db.scalar(select(AdminAccountRole.id).where(AdminAccountRole.admin_account_id == actor.id, AdminAccountRole.role_id == role.id)) is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能修改当前会话使用的角色，请由另一位管理员操作")
    before = {
        "key": role.key,
        "label": role.label,
        "description": role.description,
        "permissions": _role_permissions(db, role.id),
    }
    impact = _role_impact(db, role.id)
    role.key, role.label, role.description = payload.key, payload.label.strip(), payload.description.strip()
    db.execute(delete(AdminRolePermission).where(AdminRolePermission.role_id == role.id))
    db.add_all(AdminRolePermission(role_id=role.id, permission_id=permission.id) for permission in permissions)
    db.execute(text("""
        UPDATE admin.admin_sessions SET status = 'revoked', revoked_at = now()
         WHERE admin_account_id IN (SELECT admin_account_id FROM admin.admin_account_roles WHERE role_id = CAST(:role_id AS uuid))
           AND status = 'active'
    """), {"role_id": str(role.id)})
    write_audit(db, actor_id=actor.id, action="roles.updated", resource_type="admin_role", resource_id=str(role.id), request=request, reason=payload.reason, before_data=before, after_data={"key": role.key, "label": role.label, "description": role.description, "permissions": sorted(permission_keys), "affected_admin_count": impact["assigned_admin_count"], "sessions_revoked": True})
    db.commit()
    return _role_payload(db, role)


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: UUID,
    payload: ReasonRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("roles.manage")),
) -> Response:
    role = db.get(AdminRole, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="系统预置角色不可删除")
    impact = _role_impact(db, role.id)
    if impact["assigned_admin_count"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"该角色仍分配给 {impact['assigned_admin_count']} 位管理员，请先移除角色后再删除")
    before = _role_payload(db, role)
    db.delete(role)
    write_audit(db, actor_id=actor.id, action="roles.deleted", resource_type="admin_role", resource_id=str(role.id), request=request, reason=payload.reason, before_data=before, after_data={"deleted": True})
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit-logs")
def audit_logs(
    action: str | None = Query(default=None, max_length=120),
    resource_type: str | None = Query(default=None, max_length=120),
    resource_id: str | None = Query(default=None, max_length=160),
    actor_query: str | None = Query(default=None, alias="actor", max_length=120),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    high_risk_only: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("audit.read")),
) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="结束日期不能早于开始日期")
    clauses = ["TRUE"]
    values: dict[str, object] = {"limit": page_size, "offset": (page - 1) * page_size}
    if action:
        clauses.append("al.action = :action")
        values["action"] = action
    if resource_type:
        clauses.append("al.resource_type = :resource_type")
        values["resource_type"] = resource_type
    if resource_id:
        clauses.append("al.resource_id = :resource_id")
        values["resource_id"] = resource_id
    if actor_query:
        clauses.append("(COALESCE(aa.display_name, '') ILIKE :actor OR COALESCE(aa.email, '') ILIKE :actor)")
        values["actor"] = f"%{actor_query.strip()}%"
    if date_from:
        clauses.append("al.created_at >= CAST(:date_from AS date)")
        values["date_from"] = date_from.isoformat()
    if date_to:
        clauses.append("al.created_at < CAST(:date_to AS date) + INTERVAL '1 day'")
        values["date_to"] = date_to.isoformat()
    if high_risk_only:
        placeholders = []
        for index, audit_action in enumerate(HIGH_RISK_AUDIT_ACTIONS):
            key = f"risk_action_{index}"
            placeholders.append(f":{key}")
            values[key] = audit_action
        clauses.append(f"al.action IN ({', '.join(placeholders)})")
    where = " AND ".join(clauses)
    total = int(db.execute(text(f"""
        SELECT count(*)
          FROM admin.audit_logs al
          LEFT JOIN admin.admin_accounts aa ON aa.id = al.actor_id
         WHERE {where}
    """), values).scalar() or 0)
    rows = db.execute(text(f"""
        SELECT al.id::text AS id, al.action, al.resource_type, al.resource_id, al.reason, al.before_data, al.after_data,
               al.request_id, al.ip_address, al.user_agent, al.created_at, aa.display_name AS actor_name, aa.email AS actor_email
          FROM admin.audit_logs al LEFT JOIN admin.admin_accounts aa ON aa.id = al.actor_id
         WHERE {where} ORDER BY al.created_at DESC LIMIT :limit OFFSET :offset
    """), values).mappings().all()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size}


DEFAULT_HEALTH_SETTINGS = {
    "probes": {
        "user_api_url": settings.user_api_health_url,
        "object_storage_url": settings.object_storage_health_url or "",
        "timeout_seconds": settings.service_probe_timeout_seconds,
    },
    "maintenance": {"enabled": False, "services": [], "ends_at": None, "message": ""},
}
HEALTH_SERVICE_ORDER = (
    "admin_api",
    "database",
    "user_api",
    "object_storage",
    "redis",
    "qdrant",
    "opensearch",
    "neo4j",
)


def _health_settings(db: Session) -> dict:
    item = db.scalar(select(SystemSetting).where(SystemSetting.key == "health_settings"))
    saved = item.value if item is not None and isinstance(item.value, dict) else {}
    saved_probes = saved.get("probes") if isinstance(saved.get("probes"), dict) else {}
    saved_maintenance = saved.get("maintenance") if isinstance(saved.get("maintenance"), dict) else {}
    return {
        "probes": {**DEFAULT_HEALTH_SETTINGS["probes"], **saved_probes},
        "maintenance": {**DEFAULT_HEALTH_SETTINGS["maintenance"], **saved_maintenance},
        "updated_at": item.updated_at if item else None,
    }


def _health_maintenance_applies(config: dict, service_key: str) -> bool:
    maintenance = config.get("maintenance") or {}
    if not maintenance.get("enabled"):
        return False
    ends_at = maintenance.get("ends_at")
    if ends_at:
        try:
            until = datetime.fromisoformat(str(ends_at).replace("Z", "+00:00"))
        except ValueError:
            return False
        if until.tzinfo is None or until <= now_utc():
            return False
    services = maintenance.get("services") or []
    return not services or service_key in services


def _health_http_probe(url: str, timeout_seconds: float, label: str, *, range_request: bool = False) -> dict:
    started = perf_counter()
    try:
        headers = {"range": "bytes=0-0"} if range_request else None
        target_host = (urlparse(url).hostname or "").lower()
        # Local services must bypass a development HTTP(S) proxy; remote probes may still use it.
        trust_env = target_host not in {"localhost", "127.0.0.1", "::1"}
        with httpx.stream("GET", url, timeout=timeout_seconds, follow_redirects=True, headers=headers, trust_env=trust_env) as response:
            latency_ms = round((perf_counter() - started) * 1000)
            code = response.status_code
        if 200 <= code < 400:
            return {"status": "healthy", "latency_ms": latency_ms, "status_code": code, "detail": f"{label} 响应正常"}
        severity = "failed" if code >= 500 else "degraded"
        return {"status": severity, "latency_ms": latency_ms, "status_code": code, "detail": f"{label} 返回 HTTP {code}"}
    except httpx.HTTPError as exc:
        return {"status": "failed", "latency_ms": round((perf_counter() - started) * 1000), "status_code": None, "detail": f"{label} 不可达：{str(exc)[:160]}"}


def _health_redis_probe(timeout_seconds: float) -> dict:
    started = perf_counter()
    try:
        from redis import Redis

        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )
        try:
            healthy = bool(client.ping())
        finally:
            client.close()
        return {
            "status": "healthy" if healthy else "failed",
            "latency_ms": round((perf_counter() - started) * 1000),
            "status_code": None,
            "detail": "Redis PING 正常" if healthy else "Redis PING 未返回成功",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "latency_ms": round((perf_counter() - started) * 1000),
            "status_code": None,
            "detail": f"Redis 不可达：{exc.__class__.__name__}",
        }


def _health_neo4j_probe(timeout_seconds: float) -> dict:
    started = perf_counter()
    try:
        from neo4j import GraphDatabase

        settings.require_neo4j_aura()
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=timeout_seconds,
        )
        try:
            record = driver.execute_query(
                "RETURN 1 AS ok",
                database_=settings.neo4j_database,
                result_transformer_=lambda result: result.single(strict=True),
            )
            if record["ok"] != 1:
                raise RuntimeError("Neo4j Aura 数据库探测未返回预期结果")
        finally:
            driver.close()
        return {
            "status": "healthy",
            "latency_ms": round((perf_counter() - started) * 1000),
            "status_code": None,
            "detail": "Neo4j Aura 数据库连接正常",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "latency_ms": round((perf_counter() - started) * 1000),
            "status_code": None,
            "detail": f"Neo4j 不可达：{exc.__class__.__name__}",
        }


def _run_service_health_checks(db: Session, config: dict) -> list[dict]:
    probes = config["probes"]
    timeout_seconds = min(15.0, max(0.5, float(probes.get("timeout_seconds") or settings.service_probe_timeout_seconds)))
    results: list[dict] = [{"key": "admin_api", "label": "管理 API", "status": "healthy", "latency_ms": 0, "status_code": 200, "detail": "本次健康检查已由管理 API 正常处理"}]

    started = perf_counter()
    try:
        db.execute(text("SELECT 1"))
        database_result = {"status": "healthy", "latency_ms": round((perf_counter() - started) * 1000), "status_code": None, "detail": "数据库连接与基础查询正常"}
    except Exception as exc:  # The dashboard must show a genuine database fault.
        database_result = {"status": "failed", "latency_ms": round((perf_counter() - started) * 1000), "status_code": None, "detail": f"数据库基础查询失败：{str(exc)[:160]}"}
    results.append({"key": "database", "label": "PostgreSQL", **database_result})

    user_api_url = str(probes.get("user_api_url") or "").strip()
    results.append({"key": "user_api", "label": "用户 API", **(_health_http_probe(user_api_url, timeout_seconds, "用户 API") if user_api_url else {"status": "unknown", "latency_ms": None, "status_code": None, "detail": "尚未配置用户 API 健康检查地址"})})

    storage_url = str(probes.get("object_storage_url") or "").strip()
    source = "已配置的存储探测地址"
    if not storage_url:
        storage_url = str(db.execute(text("""
            SELECT storage_url FROM files
             WHERE deleted_at IS NULL
               AND NULLIF(storage_url, '') IS NOT NULL
               AND COALESCE(metadata ->> 'asset_status', '') NOT IN ('quarantined', 'deleted')
             ORDER BY created_at DESC LIMIT 1
        """)).scalar() or "")
        source = "最近可用文件样本"
    if storage_url:
        storage_result = _health_http_probe(storage_url, timeout_seconds, "对象存储", range_request=True)
        storage_result["detail"] = f"{storage_result['detail']}（{source}）"
    else:
        storage_result = {"status": "unknown", "latency_ms": None, "status_code": None, "detail": "没有可用文件样本；可配置专用存储探测地址"}
    results.append({"key": "object_storage", "label": "对象存储", **storage_result})

    results.append({"key": "redis", "label": "Redis / Celery", **_health_redis_probe(timeout_seconds)})
    results.append({
        "key": "qdrant",
        "label": "Qdrant 向量库",
        **_health_http_probe(f"{settings.qdrant_url.rstrip('/')}/healthz", timeout_seconds, "Qdrant"),
    })
    results.append({
        "key": "opensearch",
        "label": "OpenSearch BM25",
        **_health_http_probe(f"{settings.opensearch_url.rstrip('/')}/_cluster/health", timeout_seconds, "OpenSearch"),
    })
    results.append({"key": "neo4j", "label": "Neo4j Aura 图数据库", **_health_neo4j_probe(timeout_seconds)})

    maintenance = config.get("maintenance") or {}
    for item in results:
        item["observed_status"] = item["status"]
        if _health_maintenance_applies(config, item["key"]):
            item["status"] = "maintenance"
            item["detail"] = f"{str(maintenance.get('message') or '计划维护中')}；探测结果：{item['observed_status']}"
            item["maintenance_ends_at"] = maintenance.get("ends_at")
    return results


def _record_health_snapshots(db: Session, services: list[dict]) -> None:
    checked_at = now_utc()
    for item in services:
        db.add(ServiceHealthSnapshot(
            service_key=item["key"], service_label=item["label"], status=item["status"], latency_ms=item.get("latency_ms"),
            status_code=item.get("status_code"), detail=item["detail"],
            metadata_={"observed_status": item.get("observed_status"), "maintenance_ends_at": item.get("maintenance_ends_at")}, checked_at=checked_at,
        ))


def _sync_service_health_risks(db: Session, services: list[dict], rules: dict) -> None:
    now = now_utc()
    for service in services:
        fingerprint = f"service_health:{service['key']}"
        incident = db.scalar(select(RiskIncident).where(RiskIncident.fingerprint == fingerprint))
        observed_status = str(service.get("observed_status") or service["status"])
        under_maintenance = service["status"] == "maintenance"
        is_failure = observed_status == "failed" and not under_maintenance
        if incident is None and not is_failure:
            continue
        priority = "critical" if service["key"] in {"admin_api", "database"} else "high"
        if incident is None:
            incident = RiskIncident(
                fingerprint=fingerprint, risk_type="service_health_failure", risk_level=priority, priority=priority,
                subject=f"{service['label']} 不可用", detail=service["detail"], resource_type="service", resource_id=service["key"],
                first_seen_at=now, last_detected_at=now, last_seen_at=now, due_at=_risk_due_at(now, priority, rules),
                metadata_={"service": service["key"], "detail": service["detail"]},
            )
            db.add(incident)
            db.flush()
            _risk_activity(db, incident, "detected", "服务健康检查发现不可用依赖", metadata={"service": service["key"], "detail": service["detail"]})
            continue
        incident.last_seen_at, incident.detail = now, service["detail"]
        incident.metadata_, incident.updated_at = {"service": service["key"], "detail": service["detail"], "observed_status": observed_status}, now
        if under_maintenance and incident.status in {"open", "acknowledged", "in_progress"}:
            incident.status, incident.suppressed_until = "suppressed", None
            _risk_activity(db, incident, "maintenance_suppressed", "服务处于维护窗口，风险事件已自动抑制")
        elif is_failure:
            if incident.status in {"resolved", "dismissed"} or (incident.status == "suppressed" and incident.suppressed_until is None):
                incident.status, incident.resolved_at, incident.priority = "open", None, priority
                incident.due_at, incident.last_detected_at = _risk_due_at(now, priority, rules), now
                _risk_activity(db, incident, "reopened", "服务仍不可用，风险事件已重新打开", metadata={"service": service["key"]})
            else:
                incident.last_detected_at = now
        elif incident.status in {"open", "acknowledged", "in_progress"}:
            incident.status, incident.resolved_at = "resolved", now
            _risk_activity(db, incident, "auto_resolved", "健康检查恢复正常，事件已自动解决", metadata={"service": service["key"]})
        incident.version += 1


def _health_history(db: Session) -> list[dict]:
    rows = db.execute(text("""
        WITH days AS (
            SELECT generate_series(current_date - interval '13 days', current_date, interval '1 day')::date AS day
        ), latest_per_day AS (
            SELECT DISTINCT ON (service_key, checked_at::date) service_key, checked_at::date AS day, status
              FROM admin.service_health_snapshots
             WHERE checked_at >= current_date - interval '13 days'
             ORDER BY service_key, checked_at::date, checked_at DESC
        )
        SELECT d.day, count(l.service_key) FILTER (WHERE l.status = 'healthy') AS healthy,
               count(l.service_key) FILTER (WHERE l.status = 'degraded') AS degraded,
               count(l.service_key) FILTER (WHERE l.status = 'failed') AS failed,
               count(l.service_key) FILTER (WHERE l.status = 'maintenance') AS maintenance,
               count(l.service_key) FILTER (WHERE l.status = 'unknown') AS unknown
          FROM days d LEFT JOIN latest_per_day l ON l.day = d.day
         GROUP BY d.day ORDER BY d.day
    """)).mappings().all()
    return [{key: (value.isoformat() if key == "day" else int(value or 0)) for key, value in dict(row).items()} for row in rows]


def _health_metrics(db: Session) -> dict:
    row = db.execute(text("""
        SELECT count(*) FILTER (WHERE status IN ('queued', 'running')) AS active_jobs,
               count(*) FILTER (WHERE status = 'failed' AND updated_at >= now() - interval '24 hours') AS failed_jobs_24h,
               count(*) FILTER (WHERE status = 'failed' AND updated_at >= now() - interval '7 days') AS failed_jobs_7d,
               (SELECT count(*) FROM admin.system_model_configs WHERE enabled AND last_test_status = 'failed') AS failed_models
          FROM admin.background_jobs
    """)).mappings().one()
    return {key: int(value or 0) for key, value in dict(row).items()}


def _health_payload(db: Session, *, force: bool = False) -> dict:
    config = _health_settings(db)
    services = _run_service_health_checks(db, config)
    _record_health_snapshots(db, services)
    _sync_service_health_risks(db, services, _risk_rules(db))
    db.commit()
    summary = {status_name: sum(item["status"] == status_name for item in services) for status_name in ("healthy", "degraded", "failed", "maintenance", "unknown")}
    return {"services": services, "summary": {**summary, "total": len(services)}, "metrics": _health_metrics(db), "history": _health_history(db), "maintenance": config["maintenance"], "generated_at": now_utc(), "refreshed": force}


@router.get("/health")
def health(db: Session = Depends(get_db), actor: AdminActor = Depends(require_permission("security.read"))) -> dict:
    return _health_payload(db)


@router.post("/health/refresh")
def refresh_health(db: Session = Depends(get_db), actor: AdminActor = Depends(require_permission("security.read"))) -> dict:
    return _health_payload(db, force=True)


@router.get("/health/settings")
def health_settings(db: Session = Depends(get_db), actor: AdminActor = Depends(require_permission("security.read"))) -> dict:
    config = _health_settings(db)
    return {"probes": config["probes"], "maintenance": config["maintenance"], "updated_at": config["updated_at"]}


@router.put("/health/settings")
def put_health_settings(
    payload: SystemSettingRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("security.manage")),
) -> dict:
    _validate_health_settings(payload.value)
    item = db.scalar(select(SystemSetting).where(SystemSetting.key == "health_settings"))
    before = item.value if item else {}
    if item is None:
        item = SystemSetting(key="health_settings", value=payload.value, updated_by_id=actor.id, updated_at=now_utc())
        db.add(item)
    else:
        item.value, item.updated_by_id, item.updated_at = payload.value, actor.id, now_utc()
    write_audit(db, actor_id=actor.id, action="health.settings_updated", resource_type="system_setting", resource_id="health_settings", request=request, reason=payload.reason, before_data=before, after_data={"value": payload.value})
    db.commit()
    config = _health_settings(db)
    return {"probes": config["probes"], "maintenance": config["maintenance"], "updated_at": item.updated_at}


def _validate_health_settings(value: dict) -> None:
    allowed = {"probes", "maintenance"}
    unexpected = set(value) - allowed
    if unexpected:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"不支持的服务健康设置：{', '.join(sorted(unexpected))}")
    probes = value.get("probes", {})
    if not isinstance(probes, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="probes 必须为对象")
    for key in ("user_api_url", "object_storage_url"):
        if key in probes and probes[key] and not str(probes[key]).startswith(("http://", "https://")):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{key} 必须是 http 或 https 地址")
    if "timeout_seconds" in probes:
        try:
            timeout = float(probes["timeout_seconds"])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="timeout_seconds 必须为数字") from exc
        if not 0.5 <= timeout <= 15:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="timeout_seconds 必须在 0.5 到 15 秒之间")
    maintenance = value.get("maintenance", {})
    if not isinstance(maintenance, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="maintenance 必须为对象")
    services = maintenance.get("services", [])
    if not isinstance(services, list) or any(service not in HEALTH_SERVICE_ORDER for service in services):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="maintenance.services 包含不支持的服务")
    if maintenance.get("ends_at"):
        try:
            ends_at = datetime.fromisoformat(str(maintenance["ends_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="maintenance.ends_at 必须是 ISO 时间") from exc
        if ends_at.tzinfo is None or ends_at <= now_utc():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="maintenance.ends_at 必须晚于当前时间")
    if len(str(maintenance.get("message") or "")) > 240:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="maintenance.message 不能超过 240 个字符")


@router.get("/analytics/overview")
def analytics_overview(
    days: int = Query(default=14, ge=7, le=90),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("analytics.read")),
) -> dict:
    """Return privacy-preserving, aggregate-only operating metrics.

    The metrics deliberately use product events that already exist in the user
    product.  No user identity, conversation content, or farm detail leaves
    this endpoint.
    """
    params = {"days": days}
    summary = db.execute(text("""
        WITH bounds AS (
            SELECT current_date - CAST(:days AS int) + 1 AS start_day, current_date AS end_day
        ),
        activity AS (
            SELECT c.user_id, c.created_at::date AS day
              FROM conversations c
             WHERE c.deleted_at IS NULL AND c.status <> 'deleted'
            UNION ALL
            SELECT cp.author_id, COALESCE(cp.published_at, cp.created_at)::date AS day
              FROM community_posts cp
             WHERE cp.status = 'published' AND cp.deleted_at IS NULL
            UNION ALL
            SELECT hc.owner_id, hc.created_at::date AS day
              FROM husbandry_cases hc
            UNION ALL
            SELECT f.owner_id, hdr.record_date AS day
              FROM husbandry_daily_records hdr
              JOIN silkworm_batches sb ON sb.id = hdr.batch_id
              JOIN farms f ON f.id = sb.farm_id
        ),
        cohort AS (
            SELECT u.id, u.created_at::date AS registered_day
              FROM users u, bounds b
             WHERE u.created_at::date BETWEEN b.start_day AND b.end_day
        ),
        eligible_retention AS (
            SELECT c.*
              FROM cohort c, bounds b
             WHERE c.registered_day <= b.end_day - 7
        )
        SELECT
            (SELECT start_day FROM bounds) AS start_day,
            (SELECT end_day FROM bounds) AS end_day,
            (SELECT count(*) FROM cohort) AS new_users,
            (SELECT count(DISTINCT a.user_id) FROM activity a, bounds b WHERE a.day BETWEEN b.start_day AND b.end_day) AS active_users,
            (SELECT count(*) FROM eligible_retention) AS retention_eligible,
            (SELECT count(DISTINCT r.id)
               FROM eligible_retention r
               JOIN activity a ON a.user_id = r.id
               JOIN bounds b ON TRUE
              WHERE a.day BETWEEN r.registered_day + 7 AND b.end_day) AS retention_retained,
            (SELECT count(*) FROM cohort c
              WHERE EXISTS (
                  SELECT 1 FROM conversations cv, bounds b
                   WHERE cv.user_id = c.id AND cv.deleted_at IS NULL AND cv.status <> 'deleted'
                     AND cv.created_at::date BETWEEN b.start_day AND b.end_day
              )) AS converted_to_consultation,
            (SELECT count(*) FROM cohort c
              WHERE EXISTS (
                  SELECT 1 FROM conversations cv, bounds b
                   WHERE cv.user_id = c.id AND cv.deleted_at IS NULL AND cv.status <> 'deleted'
                     AND cv.created_at::date BETWEEN b.start_day AND b.end_day
              ) AND EXISTS (
                  SELECT 1 FROM husbandry_cases hc, bounds b
                   WHERE hc.owner_id = c.id AND hc.created_at::date BETWEEN b.start_day AND b.end_day
              )) AS converted_to_case,
            (SELECT count(*) FROM cohort c
              WHERE EXISTS (
                  SELECT 1 FROM conversations cv, bounds b
                   WHERE cv.user_id = c.id AND cv.deleted_at IS NULL AND cv.status <> 'deleted'
                     AND cv.created_at::date BETWEEN b.start_day AND b.end_day
              ) AND EXISTS (
                  SELECT 1
                    FROM husbandry_case_follow_ups hcf
                    JOIN husbandry_cases hc ON hc.id = hcf.case_id
                    JOIN bounds b ON TRUE
                   WHERE hc.owner_id = c.id AND hcf.created_at::date BETWEEN b.start_day AND b.end_day
              )) AS converted_to_follow_up
    """), params).mappings().one()

    series = db.execute(text("""
        WITH bounds AS (
            SELECT current_date - CAST(:days AS int) + 1 AS start_day, current_date AS end_day
        ),
        calendar AS (
            SELECT generate_series((SELECT start_day FROM bounds), (SELECT end_day FROM bounds), interval '1 day')::date AS day
        ),
        activity AS (
            SELECT c.user_id, c.created_at::date AS day FROM conversations c WHERE c.deleted_at IS NULL AND c.status <> 'deleted'
            UNION ALL SELECT cp.author_id, COALESCE(cp.published_at, cp.created_at)::date FROM community_posts cp WHERE cp.status = 'published' AND cp.deleted_at IS NULL
            UNION ALL SELECT hc.owner_id, hc.created_at::date FROM husbandry_cases hc
            UNION ALL SELECT f.owner_id, hdr.record_date FROM husbandry_daily_records hdr JOIN silkworm_batches sb ON sb.id = hdr.batch_id JOIN farms f ON f.id = sb.farm_id
        )
        SELECT cal.day,
               COALESCE((SELECT count(*) FROM users u WHERE u.created_at::date = cal.day), 0) AS users,
               COALESCE((SELECT count(DISTINCT a.user_id) FROM activity a WHERE a.day = cal.day), 0) AS active_users,
               COALESCE((SELECT count(*) FROM conversations c WHERE c.deleted_at IS NULL AND c.status <> 'deleted' AND c.created_at::date = cal.day), 0) AS conversations,
               COALESCE((SELECT count(*) FROM husbandry_cases hc WHERE hc.created_at::date = cal.day), 0) AS cases,
               COALESCE((SELECT count(*) FROM husbandry_case_follow_ups hcf WHERE hcf.created_at::date = cal.day), 0) AS follow_ups,
               COALESCE((SELECT count(*) FROM community_posts cp WHERE cp.status = 'published' AND cp.deleted_at IS NULL AND COALESCE(cp.published_at, cp.created_at)::date = cal.day), 0) AS posts
          FROM calendar cal
         ORDER BY cal.day
    """), params).mappings().all()

    efficiency = db.execute(text("""
        WITH bounds AS (
            SELECT current_date - CAST(:days AS int) + 1 AS start_day, current_date AS end_day
        ),
        first_user_messages AS (
            SELECT m.conversation_id, min(m.created_at) AS created_at
              FROM messages m, bounds b
             WHERE m.sender_type = 'user' AND m.status = 'sent' AND m.deleted_at IS NULL
               AND m.created_at::date BETWEEN b.start_day AND b.end_day
             GROUP BY m.conversation_id
        ),
        reply_samples AS (
            SELECT fum.created_at AS user_created_at, reply.created_at AS assistant_created_at
              FROM first_user_messages fum
              JOIN LATERAL (
                  SELECT m.created_at
                    FROM messages m
                   WHERE m.conversation_id = fum.conversation_id
                     AND m.sender_type = 'assistant' AND m.status = 'sent' AND m.deleted_at IS NULL
                     AND m.created_at >= fum.created_at
                   ORDER BY m.created_at ASC
                   LIMIT 1
              ) reply ON TRUE
        ),
        latest_follow_up AS (
            SELECT DISTINCT ON (hcf.case_id) hcf.case_id, hcf.next_follow_up_on
              FROM husbandry_case_follow_ups hcf
             ORDER BY hcf.case_id, hcf.observed_on DESC, hcf.created_at DESC
        )
        SELECT
            (SELECT round(avg(extract(epoch FROM (assistant_created_at - user_created_at)) / 60.0)::numeric, 1) FROM reply_samples) AS first_reply_minutes,
            (SELECT round(avg(extract(epoch FROM (hc.closed_at - hc.created_at)) / 3600.0)::numeric, 1)
               FROM husbandry_cases hc, bounds b
              WHERE hc.closed_at IS NOT NULL AND hc.closed_at::date BETWEEN b.start_day AND b.end_day) AS case_close_hours,
            (SELECT count(*) FROM latest_follow_up lfu JOIN husbandry_cases hc ON hc.id = lfu.case_id WHERE hc.status <> 'closed' AND lfu.next_follow_up_on IS NOT NULL) AS scheduled_follow_ups,
            (SELECT count(*) FROM latest_follow_up lfu JOIN husbandry_cases hc ON hc.id = lfu.case_id WHERE hc.status <> 'closed' AND lfu.next_follow_up_on < current_date) AS overdue_follow_ups,
            (SELECT round(avg(extract(epoch FROM (cr.reviewed_at - cr.created_at)) / 3600.0)::numeric, 1)
               FROM community_reports cr, bounds b
              WHERE cr.reviewed_at IS NOT NULL AND cr.reviewed_at::date BETWEEN b.start_day AND b.end_day) AS moderation_review_hours,
            (SELECT count(*) FROM community_reports WHERE status = 'pending') AS pending_reports
    """), params).mappings().one()

    retention_eligible = int(summary["retention_eligible"] or 0)
    retention_retained = int(summary["retention_retained"] or 0)
    scheduled_follow_ups = int(efficiency["scheduled_follow_ups"] or 0)
    overdue_follow_ups = int(efficiency["overdue_follow_ups"] or 0)
    return {
        "period": {"days": days, "from": summary["start_day"], "to": summary["end_day"]},
        "summary": {
            "new_users": int(summary["new_users"] or 0),
            "active_users": int(summary["active_users"] or 0),
        },
        "retention": {
            "eligible_users": retention_eligible,
            "retained_users": retention_retained,
            "rate": round(retention_retained / retention_eligible * 100, 1) if retention_eligible else None,
        },
        "funnel": [
            {"key": "registered", "label": "完成注册", "value": int(summary["new_users"] or 0)},
            {"key": "consultation", "label": "发起问诊", "value": int(summary["converted_to_consultation"] or 0)},
            {"key": "case", "label": "形成病例", "value": int(summary["converted_to_case"] or 0)},
            {"key": "follow_up", "label": "完成随访", "value": int(summary["converted_to_follow_up"] or 0)},
        ],
        "efficiency": {
            "first_reply_minutes": float(efficiency["first_reply_minutes"]) if efficiency["first_reply_minutes"] is not None else None,
            "case_close_hours": float(efficiency["case_close_hours"]) if efficiency["case_close_hours"] is not None else None,
            "scheduled_follow_ups": scheduled_follow_ups,
            "overdue_follow_ups": overdue_follow_ups,
            "overdue_follow_up_rate": round(overdue_follow_ups / scheduled_follow_ups * 100, 1) if scheduled_follow_ups else None,
            "moderation_review_hours": float(efficiency["moderation_review_hours"]) if efficiency["moderation_review_hours"] is not None else None,
            "pending_reports": int(efficiency["pending_reports"] or 0),
        },
        "series": [dict(row) for row in series],
        "generated_at": now_utc(),
    }


@router.get("/analytics/days/{day}")
def analytics_day_detail(
    day: date,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("analytics.read")),
) -> dict:
    """Return an aggregate-only breakdown for one selected day in the chart."""
    params = {"day": day}
    summary = db.execute(text("""
        WITH activity AS (
            SELECT c.user_id FROM conversations c WHERE c.deleted_at IS NULL AND c.status <> 'deleted' AND c.created_at::date = :day
            UNION SELECT cp.author_id FROM community_posts cp WHERE cp.status = 'published' AND cp.deleted_at IS NULL AND COALESCE(cp.published_at, cp.created_at)::date = :day
            UNION SELECT hc.owner_id FROM husbandry_cases hc WHERE hc.created_at::date = :day
            UNION SELECT f.owner_id FROM husbandry_daily_records hdr JOIN silkworm_batches sb ON sb.id = hdr.batch_id JOIN farms f ON f.id = sb.farm_id WHERE hdr.record_date = :day
        )
        SELECT
            (SELECT count(*) FROM users WHERE created_at::date = :day) AS new_users,
            (SELECT count(*) FROM activity) AS active_users,
            (SELECT count(*) FROM conversations WHERE deleted_at IS NULL AND status <> 'deleted' AND created_at::date = :day) AS conversations,
            (SELECT count(*) FROM husbandry_cases WHERE created_at::date = :day) AS cases,
            (SELECT count(*) FROM husbandry_case_follow_ups WHERE created_at::date = :day) AS follow_ups,
            (SELECT count(*) FROM community_posts WHERE status = 'published' AND deleted_at IS NULL AND COALESCE(published_at, created_at)::date = :day) AS posts
    """), params).mappings().one()
    conversation_types = db.execute(text("""
        SELECT COALESCE(NULLIF(conversation_type, ''), '未分类') AS label, count(*) AS value
          FROM conversations
         WHERE deleted_at IS NULL AND status <> 'deleted' AND created_at::date = :day
         GROUP BY conversation_type
         ORDER BY value DESC, label ASC
    """), params).mappings().all()
    case_severities = db.execute(text("""
        SELECT severity AS label, count(*) AS value
          FROM husbandry_cases
         WHERE created_at::date = :day
         GROUP BY severity
         ORDER BY value DESC, label ASC
    """), params).mappings().all()
    post_types = db.execute(text("""
        SELECT post_type AS label, count(*) AS value
          FROM community_posts
         WHERE status = 'published' AND deleted_at IS NULL AND COALESCE(published_at, created_at)::date = :day
         GROUP BY post_type
         ORDER BY value DESC, label ASC
    """), params).mappings().all()
    attention = db.execute(text("""
        SELECT
            (SELECT count(*) FROM husbandry_cases WHERE created_at::date = :day AND severity IN ('high', 'critical')) AS high_risk_cases,
            (SELECT count(*) FROM community_reports WHERE created_at::date = :day) AS reports_created,
            (SELECT count(*) FROM admin.background_jobs WHERE updated_at::date = :day AND status = 'failed') AS failed_jobs
    """), params).mappings().one()
    return {
        "day": day,
        "summary": {key: int(value or 0) for key, value in dict(summary).items()},
        "breakdown": {
            "conversations": [dict(row) for row in conversation_types],
            "cases": [dict(row) for row in case_severities],
            "posts": [dict(row) for row in post_types],
        },
        "attention": {key: int(value or 0) for key, value in dict(attention).items()},
    }


def _asset_status_expression(alias: str = "f") -> str:
    """Lifecycle is stored in file metadata so the user upload schema stays compatible."""
    return f"""
        CASE
            WHEN {alias}.deleted_at IS NOT NULL THEN 'deleted'
            WHEN COALESCE({alias}.metadata ->> 'asset_status', '') = 'quarantined' THEN 'quarantined'
            WHEN COALESCE({alias}.metadata ->> 'asset_status', '') = 'upload_failed'
              OR NULLIF({alias}.storage_url, '') IS NULL THEN 'upload_failed'
            ELSE 'normal'
        END
    """


def _asset_lookup(db: Session, file_id: UUID) -> dict:
    asset_status = _asset_status_expression("f")
    row = db.execute(text(f"""
        SELECT f.id::text AS id, f.file_name, f.file_type, f.mime_type, f.file_size, f.storage_url,
               f.metadata, {asset_status} AS asset_status
          FROM files f
         WHERE f.id = :file_id
    """), {"file_id": file_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件资产不存在")
    return dict(row)


@router.get("/assets")
def assets(
    q: str | None = Query(default=None, min_length=1, max_length=120),
    owner: str | None = Query(default=None, min_length=1, max_length=120),
    file_type: str = Query(default="all", pattern="^(all|image|video|document|audio|other)$"),
    asset_status: str = Query(default="all", alias="status", pattern="^(all|normal|quarantined|deleted|upload_failed)$"),
    created_from: date | None = None,
    created_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("assets.read")),
) -> dict:
    if created_from and created_to and created_from > created_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="开始日期不能晚于结束日期")
    asset_status_sql = _asset_status_expression("f")
    conditions = ["TRUE"]
    values: dict[str, object] = {"limit": page_size, "offset": (page - 1) * page_size}
    if file_type != "all":
        conditions.append("f.file_type = :file_type")
        values["file_type"] = file_type
    if asset_status != "all":
        conditions.append(f"({asset_status_sql}) = :asset_status")
        values["asset_status"] = asset_status
    if q:
        conditions.append("(f.file_name ILIKE :q OR COALESCE(u.display_name, '') ILIKE :q OR COALESCE(u.username, '') ILIKE :q)")
        values["q"] = f"%{q.strip()}%"
    if owner:
        conditions.append("(COALESCE(u.display_name, '') ILIKE :owner OR COALESCE(u.username, '') ILIKE :owner)")
        values["owner"] = f"%{owner.strip()}%"
    if created_from:
        conditions.append("f.created_at::date >= :created_from")
        values["created_from"] = created_from
    if created_to:
        conditions.append("f.created_at::date <= :created_to")
        values["created_to"] = created_to
    where = " AND ".join(conditions)
    total = int(db.execute(text(f"""
        SELECT count(*) FROM files f JOIN users u ON u.id = f.user_id WHERE {where}
    """), values).scalar() or 0)
    rows = db.execute(text(f"""
        SELECT f.id::text AS id, f.file_name, f.file_type, f.mime_type, f.file_size, f.created_at,
               f.project_id::text AS project_id, u.id::text AS owner_id,
               COALESCE(NULLIF(u.display_name, ''), NULLIF(u.username, ''), '未命名用户') AS owner_name,
               {asset_status_sql} AS asset_status,
               refs.reference_count,
               COALESCE(duplicates.duplicate_count, 0) AS duplicate_count,
               (f.file_size >= 52428800) AS is_large,
               (f.created_at < now() - interval '90 days' AND refs.reference_count = 0) AS is_stale
          FROM files f
          JOIN users u ON u.id = f.user_id
          LEFT JOIN LATERAL (
              SELECT count(*)::int AS reference_count FROM (
                  SELECT mf.file_id FROM message_files mf WHERE mf.file_id = f.id
                  UNION ALL SELECT cpa.file_id FROM community_post_assets cpa WHERE cpa.file_id = f.id
                  UNION ALL SELECT hra.file_id FROM husbandry_record_assets hra WHERE hra.file_id = f.id
              ) asset_references
          ) refs ON TRUE
          LEFT JOIN LATERAL (
              SELECT count(*)::int - 1 AS duplicate_count
                FROM files duplicate_file
               WHERE duplicate_file.id <> f.id AND duplicate_file.deleted_at IS NULL
                 AND f.checksum IS NOT NULL AND duplicate_file.checksum = f.checksum
          ) duplicates ON TRUE
         WHERE {where}
         ORDER BY f.created_at DESC LIMIT :limit OFFSET :offset
    """), values).mappings().all()
    summary = db.execute(text(f"""
        WITH asset_refs AS (
            SELECT mf.file_id FROM message_files mf
            UNION ALL SELECT cpa.file_id FROM community_post_assets cpa
            UNION ALL SELECT hra.file_id FROM husbandry_record_assets hra
        ), classified AS (
            SELECT f.id, f.file_size, f.created_at, {asset_status_sql} AS asset_status,
                   (SELECT count(*) FROM asset_refs ar WHERE ar.file_id = f.id) AS reference_count
              FROM files f
        )
        SELECT count(*) AS total_files, COALESCE(sum(file_size), 0) AS total_bytes,
               count(*) FILTER (WHERE asset_status = 'normal') AS normal_files,
               count(*) FILTER (WHERE asset_status = 'quarantined') AS quarantined_files,
               count(*) FILTER (WHERE asset_status = 'deleted') AS deleted_files,
               count(*) FILTER (WHERE asset_status = 'upload_failed') AS failed_files,
               count(*) FILTER (WHERE reference_count = 0 AND asset_status <> 'deleted') AS orphaned_files,
               count(*) FILTER (WHERE file_size >= 52428800 AND asset_status <> 'deleted') AS large_files,
               count(*) FILTER (WHERE created_at < now() - interval '90 days' AND reference_count = 0 AND asset_status <> 'deleted') AS stale_files,
               COALESCE(sum(file_size) FILTER (WHERE asset_status = 'deleted'), 0) AS reclaimable_bytes
          FROM classified
    """)).mappings().one()
    duplicate_files = int(db.execute(text("""
        SELECT COALESCE(sum(file_count - 1), 0)
          FROM (
              SELECT count(*)::int AS file_count
                FROM files
               WHERE deleted_at IS NULL AND checksum IS NOT NULL
               GROUP BY checksum HAVING count(*) > 1
          ) duplicate_groups
    """)).scalar() or 0)
    types = db.execute(text(f"""
        SELECT f.file_type AS type, count(*) AS count, COALESCE(sum(f.file_size), 0) AS bytes
          FROM files f
         WHERE ({asset_status_sql}) <> 'deleted'
         GROUP BY f.file_type ORDER BY count DESC, f.file_type ASC
    """)).mappings().all()
    return {
        "items": [dict(row) for row in rows], "total": total, "page": page, "page_size": page_size,
        "summary": {**{key: int(value or 0) for key, value in dict(summary).items()}, "duplicate_files": duplicate_files},
        "types": [dict(row) for row in types],
    }


@router.post("/assets/{file_id}/preview")
def grant_asset_preview(
    file_id: UUID,
    payload: ReasonRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("assets.manage")),
) -> dict:
    item = _asset_lookup(db, file_id)
    if item["asset_status"] != "normal" or not item["storage_url"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅正常存储的文件可以申请预览")
    expires_at = now_utc() + timedelta(seconds=settings.sensitive_access_ttl_seconds)
    grant = SensitiveAccessGrant(admin_account_id=actor.id, resource_type="file", resource_id=str(file_id), reason=payload.reason, expires_at=expires_at)
    db.add(grant)
    db.flush()
    write_audit(db, actor_id=actor.id, action="assets.preview_granted", resource_type="file", resource_id=str(file_id), request=request, reason=payload.reason, after_data={"expires_at": expires_at.isoformat()})
    db.commit()
    return {"file_id": str(file_id), "file_name": item["file_name"], "mime_type": item["mime_type"], "content_path": f"/assets/{file_id}/content", "expires_at": expires_at}


@router.get("/assets/{file_id}/content")
def preview_asset_content(
    file_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("assets.manage")),
) -> Response:
    active_grant = db.scalar(select(SensitiveAccessGrant.id).where(
        SensitiveAccessGrant.admin_account_id == actor.id,
        SensitiveAccessGrant.resource_type == "file",
        SensitiveAccessGrant.resource_id == str(file_id),
        SensitiveAccessGrant.expires_at > now_utc(),
    ))
    if active_grant is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请先申请文件预览授权")
    item = _asset_lookup(db, file_id)
    if item["asset_status"] != "normal" or not item["storage_url"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该文件当前不可预览")
    try:
        upstream = httpx.get(str(item["storage_url"]), follow_redirects=True, timeout=30.0)
        upstream.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="文件内容暂时不可读取") from exc
    return Response(content=upstream.content, media_type=str(item["mime_type"] or upstream.headers.get("content-type") or "application/octet-stream"), headers={"Cache-Control": "private, no-store", "Content-Disposition": "inline"})


@router.patch("/assets/{file_id}/lifecycle")
def update_asset_lifecycle(
    file_id: UUID,
    payload: AssetLifecycleRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("assets.manage")),
) -> dict:
    item = _asset_lookup(db, file_id)
    current_status = str(item["asset_status"])
    if payload.action == "quarantine" and current_status != "normal":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有正常文件可以隔离")
    if payload.action == "delete" and current_status == "deleted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="文件已处于已删除状态")
    if payload.action == "restore" and current_status not in {"quarantined", "deleted"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前文件无需恢复")
    values = {"file_id": file_id}
    if payload.action == "quarantine":
        db.execute(text("""
            UPDATE files
               SET metadata = jsonb_set(
                       jsonb_set(COALESCE(metadata, '{}'::jsonb), '{asset_status}', to_jsonb('quarantined'::text), true),
                       '{admin_original_storage_url}', to_jsonb(COALESCE(NULLIF(storage_url, ''), NULLIF(metadata ->> 'admin_original_storage_url', ''), '')::text), true
                   ), storage_url = NULL
             WHERE id = :file_id
        """), values)
        next_status = "quarantined"
    elif payload.action == "delete":
        db.execute(text("""
            UPDATE files
               SET deleted_at = now(), metadata = jsonb_set(
                       jsonb_set(COALESCE(metadata, '{}'::jsonb), '{asset_status}', to_jsonb('deleted'::text), true),
                       '{admin_original_storage_url}', to_jsonb(COALESCE(NULLIF(storage_url, ''), NULLIF(metadata ->> 'admin_original_storage_url', ''), '')::text), true
                   ), storage_url = NULL
             WHERE id = :file_id
        """), values)
        next_status = "deleted"
    else:
        original_url = str((item.get("metadata") or {}).get("admin_original_storage_url") or "")
        if not original_url:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="未保留原始存储地址，不能恢复该文件")
        db.execute(text("""
            UPDATE files
               SET deleted_at = NULL,
                   storage_url = NULLIF(metadata ->> 'admin_original_storage_url', ''),
                   metadata = COALESCE(metadata, '{}'::jsonb) - 'asset_status' - 'admin_original_storage_url'
             WHERE id = :file_id
        """), values)
        next_status = "normal"
    write_audit(db, actor_id=actor.id, action=f"assets.{payload.action}", resource_type="file", resource_id=str(file_id), request=request, reason=payload.reason, before_data={"status": current_status, "file_name": item["file_name"]}, after_data={"status": next_status})
    db.commit()
    return {"id": str(file_id), "status": next_status}


@router.get("/risk-events")
def risk_events(
    scope: str = Query(default="active", pattern="^(active|all|archive)$"),
    priority: str | None = Query(default=None, pattern="^(low|medium|high|critical)$"),
    assignee: str | None = Query(default=None, pattern="^(mine|unassigned)$"),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("security.read")),
) -> dict:
    rules = _risk_rules(db)
    _sync_risk_incidents(db, rules)
    all_incidents = list(db.scalars(select(RiskIncident).order_by(RiskIncident.last_detected_at.desc()).limit(500)).all())
    _escalate_overdue_incidents(db, all_incidents)
    db.commit()

    status_sets = {
        "active": {"open", "acknowledged", "in_progress"},
        "archive": {"resolved", "dismissed", "suppressed"},
        "all": set(RISK_STATUS_LABELS),
    }
    incidents = [item for item in all_incidents if item.status in status_sets[scope]]
    if priority:
        incidents = [item for item in incidents if item.priority == priority]
    if assignee == "mine":
        incidents = [item for item in incidents if item.assignee_id == actor.id]
    elif assignee == "unassigned":
        incidents = [item for item in incidents if item.assignee_id is None]

    assignee_names = _risk_assignee_names(db, incidents)
    all_assignee_names = _risk_assignee_names(db, all_incidents)
    read_incident_ids = set(db.scalars(select(RiskNotificationReceipt.incident_id).where(RiskNotificationReceipt.admin_account_id == actor.id)).all())
    unread = [
        item for item in all_incidents
        if item.status in {"open", "acknowledged", "in_progress"}
        and item.priority in {"high", "critical"}
        and item.id not in read_incident_ids
    ]
    start_day = now_utc().date() - timedelta(days=13)
    trend_rows = db.execute(text("""
        SELECT first_seen_at::date AS day,
               count(*) AS total,
               count(*) FILTER (WHERE priority = 'critical') AS critical,
               count(*) FILTER (WHERE priority = 'high') AS high,
               count(*) FILTER (WHERE status IN ('resolved', 'dismissed')) AS closed
          FROM admin.risk_incidents
         WHERE first_seen_at::date >= :start_day
         GROUP BY first_seen_at::date
         ORDER BY first_seen_at::date
    """), {"start_day": start_day}).mappings().all()
    trend_by_day = {row["day"]: dict(row) for row in trend_rows}
    trends = []
    for offset in range(14):
        day = start_day + timedelta(days=offset)
        row = trend_by_day.get(day, {})
        trends.append({"day": day, "total": int(row.get("total") or 0), "critical": int(row.get("critical") or 0), "high": int(row.get("high") or 0), "closed": int(row.get("closed") or 0)})
    type_rows = db.execute(text("""
        SELECT risk_type AS type, count(*) AS total,
               count(*) FILTER (WHERE status IN ('open', 'acknowledged', 'in_progress')) AS active
          FROM admin.risk_incidents
         WHERE first_seen_at >= now() - interval '30 days'
         GROUP BY risk_type
         ORDER BY total DESC, risk_type
         LIMIT 6
    """)).mappings().all()
    assignees = []
    if "security.manage" in actor.permissions:
        assignees = [
            {"id": str(account.id), "display_name": account.display_name, "email": account.email}
            for account in db.scalars(select(AdminAccount).where(AdminAccount.status == "active").order_by(AdminAccount.display_name)).all()
        ]
    return {
        "items": [_risk_incident_dict(item, assignee_name=assignee_names.get(item.assignee_id)) for item in incidents],
        "summary": _risk_summary(all_incidents),
        "trends": trends,
        "top_types": [dict(row) for row in type_rows],
        "notifications": {
            "unread_count": len(unread),
            "items": [_risk_incident_dict(item, assignee_name=all_assignee_names.get(item.assignee_id)) for item in unread[:5]],
        },
        "assignees": assignees,
        "rules": rules,
    }


@router.get("/risk-events/{incident_id}")
def risk_event_detail(
    incident_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("security.read")),
) -> dict:
    incident = db.get(RiskIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="风险事件不存在")
    assignee = db.get(AdminAccount, incident.assignee_id) if incident.assignee_id else None
    timeline = db.execute(text("""
        SELECT ria.id::text AS id, ria.activity_type, ria.content, ria.metadata, ria.created_at,
               aa.display_name AS actor_name, aa.email AS actor_email
          FROM admin.risk_incident_activities ria
          LEFT JOIN admin.admin_accounts aa ON aa.id = ria.actor_id
         WHERE ria.incident_id = CAST(:incident_id AS uuid)
         ORDER BY ria.created_at DESC
    """), {"incident_id": str(incident_id)}).mappings().all()
    return {
        "incident": _risk_incident_dict(incident, assignee_name=assignee.display_name if assignee else None),
        "timeline": [dict(row) for row in timeline],
        "evidence": incident.metadata_.get("evidence", []),
    }


@router.patch("/risk-events/{incident_id}")
def update_risk_event(
    incident_id: UUID,
    payload: RiskIncidentActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("security.manage")),
) -> dict:
    incident = db.get(RiskIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="风险事件不存在")
    note = (payload.note or "").strip()
    if payload.action in {"resolve", "dismiss", "suppress"} and len(note) < 3:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="完成、忽略或抑制风险时请填写至少 3 个字的处置说明")
    if payload.action == "note" and len(note) < 1:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请填写处置备注")
    now = now_utc()
    before = _risk_incident_dict(incident)
    action_label = {
        "acknowledge": "确认风险",
        "start": "开始处置",
        "claim": "领取风险",
        "release": "释放负责人",
        "resolve": "标记已解决",
        "dismiss": "忽略风险",
        "suppress": "抑制同类提醒",
        "reopen": "重新打开风险",
        "assign": "指派负责人",
        "note": "补充处置备注",
    }[payload.action]
    if payload.action == "acknowledge":
        incident.status = "acknowledged"
    elif payload.action == "start":
        incident.status = "in_progress"
    elif payload.action == "claim":
        incident.status, incident.assignee_id = "in_progress", actor.id
    elif payload.action == "release":
        incident.assignee_id = None
    elif payload.action in {"resolve", "dismiss"}:
        incident.status, incident.resolved_at = ("resolved" if payload.action == "resolve" else "dismissed"), now
    elif payload.action == "suppress":
        hours = payload.suppress_hours or int(_risk_rules(db)["suppression_default_hours"])
        incident.status, incident.suppressed_until = "suppressed", now + timedelta(hours=hours)
    elif payload.action == "reopen":
        incident.status, incident.resolved_at, incident.suppressed_until = "open", None, None
        incident.due_at = _risk_due_at(now, incident.priority, _risk_rules(db))
    elif payload.action == "assign":
        if not payload.assignee_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择负责人")
        assignee = db.get(AdminAccount, UUID(payload.assignee_id))
        if assignee is None or assignee.status != "active":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="负责人不存在或不可用")
        incident.assignee_id = assignee.id
    incident.updated_at, incident.version = now, incident.version + 1
    content = action_label + (f"：{note}" if note else "")
    _risk_activity(db, incident, payload.action, content, actor_id=actor.id, metadata={"assignee_id": payload.assignee_id, "suppress_hours": payload.suppress_hours})
    write_audit(db, actor_id=actor.id, action=f"risk_events.{payload.action}", resource_type="risk_incident", resource_id=str(incident.id), request=request, reason=note or None, before_data=before, after_data=_risk_incident_dict(incident))
    db.commit()
    assignee_name = db.get(AdminAccount, incident.assignee_id).display_name if incident.assignee_id else None
    return {"incident": _risk_incident_dict(incident, assignee_name=assignee_name)}


@router.post("/risk-events/{incident_id}/notifications/read")
def mark_risk_notification_read(
    incident_id: UUID,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("security.read")),
) -> dict:
    incident = db.get(RiskIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="风险事件不存在")
    receipt = db.scalar(select(RiskNotificationReceipt).where(RiskNotificationReceipt.incident_id == incident.id, RiskNotificationReceipt.admin_account_id == actor.id))
    if receipt is None:
        db.add(RiskNotificationReceipt(incident_id=incident.id, admin_account_id=actor.id))
        db.commit()
    return {"id": str(incident.id), "read": True}


@router.get("/risk-settings")
def risk_settings(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("security.read")),
) -> dict:
    item = db.scalar(select(SystemSetting).where(SystemSetting.key == "risk_rules"))
    return {"rules": _risk_rules(db), "updated_at": item.updated_at if item else None}


@router.put("/risk-settings")
def put_risk_settings(
    payload: SystemSettingRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("security.manage")),
) -> dict:
    _validate_risk_rules(payload.value)
    item = db.scalar(select(SystemSetting).where(SystemSetting.key == "risk_rules"))
    before = item.value if item else {}
    if item is None:
        item = SystemSetting(key="risk_rules", value=payload.value, updated_by_id=actor.id, updated_at=now_utc())
        db.add(item)
    else:
        item.value, item.updated_by_id, item.updated_at = payload.value, actor.id, now_utc()
    write_audit(db, actor_id=actor.id, action="risk_rules.updated", resource_type="system_setting", resource_id="risk_rules", request=request, reason=payload.reason, before_data=before, after_data={"value": payload.value})
    db.commit()
    return {"rules": _risk_rules(db), "updated_at": item.updated_at}


@router.get("/models")
def models(db: Session = Depends(get_db), actor: AdminActor = Depends(require_permission("models.read"))) -> dict:
    items = db.scalars(select(SystemModelConfig).order_by(SystemModelConfig.created_at.desc())).all()
    return {
        "items": [_model_dict(item) for item in items],
        "summary": {
            "total": len(items),
            "enabled": sum(item.enabled for item in items),
            "passed": sum(item.last_test_status == "passed" for item in items),
            "failed": sum(item.last_test_status == "failed" for item in items),
            "untested": sum(item.last_test_status is None for item in items),
        },
    }


@router.post("/models")
def create_model(
    payload: ModelConfigRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("models.manage")),
) -> dict:
    if db.scalar(select(SystemModelConfig).where(SystemModelConfig.key == payload.key.strip())) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="模型标识已存在")
    item = SystemModelConfig(key=payload.key.strip(), label=payload.label.strip(), model_id=payload.model_id.strip(), api_base_url=payload.api_base_url.strip().rstrip("/"), api_key_ciphertext=encrypt_secret(payload.api_key) if payload.api_key else None, capability=payload.capability, enabled=payload.enabled)
    db.add(item)
    db.flush()
    write_audit(db, actor_id=actor.id, action="models.created", resource_type="system_model", resource_id=str(item.id), request=request, reason=payload.reason, after_data={"key": item.key, "model_id": item.model_id, "enabled": item.enabled})
    db.commit()
    return _model_dict(item)


@router.patch("/models/{model_config_id}")
def update_model(
    model_config_id: UUID,
    payload: ModelConfigRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("models.manage")),
) -> dict:
    item = db.get(SystemModelConfig, model_config_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="系统模型不存在")
    normalized_key = payload.key.strip()
    duplicate = db.scalar(
        select(SystemModelConfig).where(
            SystemModelConfig.key == normalized_key,
            SystemModelConfig.id != item.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="模型标识已存在")
    before = _model_dict(item)
    normalized_base_url = payload.api_base_url.strip().rstrip("/")
    connection_changed = any((
        item.model_id != payload.model_id.strip(),
        item.api_base_url.rstrip("/") != normalized_base_url,
        item.capability != payload.capability,
        bool(payload.api_key),
        payload.clear_api_key and bool(item.api_key_ciphertext),
    ))
    item.key, item.label, item.model_id, item.api_base_url, item.capability, item.enabled, item.updated_at = normalized_key, payload.label.strip(), payload.model_id.strip(), normalized_base_url, payload.capability, payload.enabled, now_utc()
    if payload.clear_api_key:
        item.api_key_ciphertext = None
    elif payload.api_key:
        item.api_key_ciphertext = encrypt_secret(payload.api_key)
    if connection_changed:
        item.last_test_status = None
        item.last_test_message = None
        item.last_test_at = None
    write_audit(db, actor_id=actor.id, action="models.updated", resource_type="system_model", resource_id=str(item.id), request=request, reason=payload.reason, before_data=before, after_data={"key": item.key, "model_id": item.model_id, "enabled": item.enabled})
    db.commit()
    return _model_dict(item)


@router.post("/models/{model_config_id}/test")
def test_model(
    model_config_id: UUID,
    payload: ReasonRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("models.manage")),
) -> dict:
    import httpx

    item = db.get(SystemModelConfig, model_config_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="系统模型不存在")
    base_url = item.api_base_url.rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="模型地址必须使用 HTTP 或 HTTPS")
    model_api_key = decrypt_secret(item.api_key_ciphertext) if item.api_key_ciphertext else settings.dashscope_api_key
    headers = {"authorization": f"Bearer {model_api_key}"} if model_api_key else {}
    before = _model_dict(item)
    try:
        if item.capability in {"chat", "vision"}:
            response = httpx.post(
                f"{base_url}/chat/completions",
                headers={**headers, "content-type": "application/json"},
                json={"model": item.model_id, "messages": [{"role": "user", "content": "只回复 OK"}], "max_tokens": 8, "enable_thinking": False},
                timeout=20.0,
            )
        elif item.capability == "embedding":
            response = httpx.post(
                f"{base_url}/embeddings",
                headers={**headers, "content-type": "application/json"},
                json={"model": item.model_id, "input": ["养蚕知识库连通性测试"], "dimensions": 1024, "encoding_format": "float"},
                timeout=20.0,
            )
        elif item.capability == "rerank":
            response = httpx.post(
                f"{base_url}/reranks",
                headers={**headers, "content-type": "application/json"},
                json={"model": item.model_id, "query": "蚕病防治", "documents": ["保持蚕室清洁并做好消毒"], "top_n": 1},
                timeout=20.0,
            )
        else:
            test_url = f"{base_url}/models" if not base_url.endswith("/models") else base_url
            response = httpx.get(test_url, headers=headers, timeout=8.0, follow_redirects=True)
        if 200 <= response.status_code < 400:
            item.last_test_status, item.last_test_message = "passed", f"HTTP {response.status_code}"
        else:
            item.last_test_status, item.last_test_message = "failed", f"HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        item.last_test_status, item.last_test_message = "failed", str(exc)[:500]
    item.last_test_at = item.updated_at = now_utc()
    write_audit(db, actor_id=actor.id, action="models.tested", resource_type="system_model", resource_id=str(item.id), request=request, reason=payload.reason, before_data=before, after_data={"last_test_status": item.last_test_status, "last_test_message": item.last_test_message})
    db.commit()
    return _model_dict(item)


@router.get("/jobs")
def jobs(
    job_status: str | None = Query(default=None, alias="status", pattern="^(queued|running|succeeded|failed|cancelled)$"),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("models.read")),
) -> dict:
    query = select(BackgroundJob)
    if job_status:
        query = query.where(BackgroundJob.status == job_status)
    count_query = select(func.count()).select_from(BackgroundJob)
    if job_status:
        count_query = count_query.where(BackgroundJob.status == job_status)
    total = int(db.scalar(count_query) or 0)
    items = db.scalars(query.order_by(BackgroundJob.created_at.desc()).limit(200)).all()
    status_counts = {
        str(row_status): int(count)
        for row_status, count in db.execute(
            select(BackgroundJob.status, func.count()).group_by(BackgroundJob.status)
        ).all()
    }
    return {
        "items": [_job_dict(item) for item in items],
        "total": total,
        "summary": {
            "all": sum(status_counts.values()),
            "queued": status_counts.get("queued", 0),
            "running": status_counts.get("running", 0),
            "succeeded": status_counts.get("succeeded", 0),
            "failed": status_counts.get("failed", 0),
            "cancelled": status_counts.get("cancelled", 0),
        },
    }


def _job_payload_uuid(item: BackgroundJob, key: str) -> UUID:
    value = item.payload.get(key)
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"任务缺少有效的 {key}，无法继续操作",
        ) from exc


def _source_for_build_run(db: Session, run: KnowledgeBuildRun) -> KnowledgeSource:
    version = db.get(KnowledgeSourceVersion, run.source_version_id)
    source = db.get(KnowledgeSource, version.source_id) if version else None
    if source is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务关联的知识源不存在")
    return source


def _refresh_source_after_build_cancel(db: Session, run: KnowledgeBuildRun, now: datetime) -> None:
    source = _source_for_build_run(db, run)
    active_count = int(
        db.scalar(
            select(func.count())
            .select_from(KnowledgeBuildRun)
            .join(KnowledgeSourceVersion, KnowledgeSourceVersion.id == KnowledgeBuildRun.source_version_id)
            .where(
                KnowledgeSourceVersion.source_id == source.id,
                KnowledgeBuildRun.id != run.id,
                KnowledgeBuildRun.status.in_(("queued", "running", "awaiting_review", "publishing")),
            )
        )
        or 0
    )
    if active_count:
        source.status = "processing"
    else:
        succeeded_count = int(
            db.scalar(
                select(func.count())
                .select_from(KnowledgeBuildRun)
                .join(KnowledgeSourceVersion, KnowledgeSourceVersion.id == KnowledgeBuildRun.source_version_id)
                .where(
                    KnowledgeSourceVersion.source_id == source.id,
                    KnowledgeBuildRun.id != run.id,
                    KnowledgeBuildRun.status == "succeeded",
                )
            )
            or 0
        )
        source.status = "ready" if source.published_version_id or succeeded_count else "draft"
    source.updated_at = now


def _patch_knowledge_job(
    item: BackgroundJob,
    payload: JobActionRequest,
    request: Request,
    db: Session,
    actor: AdminActor,
) -> dict:
    before = item.status
    now = now_utc()
    run: KnowledgeBuildRun | None = None
    publication: KnowledgePublication | None = None
    source: KnowledgeSource | None = None

    if item.job_type == "knowledge_build":
        run = db.get(KnowledgeBuildRun, _job_payload_uuid(item, "build_run_id"))
        if run is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务关联的知识构建记录不存在")
        source = _source_for_build_run(db, run)
    else:
        publication = db.get(KnowledgePublication, _job_payload_uuid(item, "publication_id"))
        if publication is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务关联的发布记录不存在")
        run = db.get(KnowledgeBuildRun, publication.build_run_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="发布记录关联的知识构建不存在")

    if payload.action == "retry":
        if item.status != "failed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅失败任务可以重试")
        if source is not None and source.status == "disabled":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="知识源已停用，恢复后才能重试构建")
        item.status = "queued"
        item.progress = 0
        item.result = {}
        item.error_message = None
        item.started_at = None
        item.completed_at = None
        if item.job_type == "knowledge_build":
            run.status = "queued"
            run.progress = 0
            run.current_node = "retry_queued"
            run.error_message = None
            run.started_at = None
            run.completed_at = None
            run.updated_at = now
            source.status = "processing"
            source.updated_at = now
        else:
            publication.status = "staging"
            publication.error_message = None
            publication.updated_at = now
            run.status = "publishing"
            run.current_node = "publish_retry_queued"
            run.error_message = None
            run.updated_at = now
    else:
        if item.status not in {"queued", "running"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务当前不能取消")
        item.status = "cancelled"
        item.completed_at = now
        if item.job_type == "knowledge_build":
            run.status = "cancelled"
            run.current_node = "cancelled"
            run.completed_at = now
            run.updated_at = now
            db.add(
                KnowledgeBuildEvent(
                    build_run_id=run.id,
                    node="cancelled",
                    level="warning",
                    message="构建任务已由管理员取消",
                    payload={"reason": payload.reason},
                )
            )
            _refresh_source_after_build_cancel(db, run, now)
        else:
            publication.status = "rolled_back"
            publication.error_message = None
            publication.updated_at = now
            run.status = "succeeded"
            run.current_node = "ready_to_publish"
            run.progress = 100
            run.error_message = None
            run.updated_at = now
            db.add(
                KnowledgeBuildEvent(
                    build_run_id=run.id,
                    node="publish_cancelled",
                    level="warning",
                    message="发布任务已由管理员取消，构建成果仍可重新发布",
                    payload={"reason": payload.reason, "publication_id": str(publication.id)},
                )
            )

    item.updated_at = now
    write_audit(
        db,
        actor_id=actor.id,
        action=f"jobs.{payload.action}",
        resource_type="background_job",
        resource_id=str(item.id),
        request=request,
        reason=payload.reason,
        before_data={"status": before},
        after_data={"status": item.status},
    )
    db.commit()

    if payload.action == "retry":
        try:
            from app.knowledge.tasks import dispatch_background_job

            dispatch_background_job(item.id)
        except Exception as exc:
            failed_at = now_utc()
            item.status = "failed"
            item.error_message = f"任务队列不可用：{exc.__class__.__name__}"
            item.completed_at = failed_at
            item.updated_at = failed_at
            if item.job_type == "knowledge_build":
                run.status = "failed"
                run.current_node = "retry_queue_dispatch_failed"
                run.error_message = item.error_message
                run.completed_at = failed_at
                run.updated_at = failed_at
                source.status = "failed"
                source.updated_at = failed_at
            else:
                publication.status = "failed"
                publication.error_message = item.error_message
                publication.updated_at = failed_at
                run.status = "failed"
                run.current_node = "publish_retry_queue_dispatch_failed"
                run.error_message = item.error_message
                run.completed_at = failed_at
                run.updated_at = failed_at
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="任务队列暂时不可用，任务仍可重试",
            ) from exc
    return _job_dict(item)


@router.patch("/jobs/{job_id}")
def patch_job(
    job_id: UUID,
    payload: JobActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("models.manage")),
) -> dict:
    item = db.get(BackgroundJob, job_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
    if item.job_type in {"knowledge_build", "knowledge_publish"}:
        return _patch_knowledge_job(item, payload, request, db, actor)
    if payload.action == "retry":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该任务类型没有可用的重试执行器")
    before = item.status
    if payload.action == "retry":
        if item.status != "failed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="仅失败任务可重试")
        item.status, item.progress, item.error_message, item.started_at, item.completed_at = "queued", 0, None, None, None
        if item.job_type == "knowledge_build" and item.payload.get("build_run_id"):
            from app.models import KnowledgeBuildRun

            run = db.get(KnowledgeBuildRun, UUID(str(item.payload["build_run_id"])))
            if run:
                run.status, run.progress, run.error_message, run.completed_at = "queued", 0, None, None
                run.current_node, run.updated_at = "retry_queued", now_utc()
        elif item.job_type == "knowledge_publish" and item.payload.get("publication_id"):
            from app.models import KnowledgeBuildRun, KnowledgePublication

            publication = db.get(KnowledgePublication, UUID(str(item.payload["publication_id"])))
            if publication:
                publication.status, publication.error_message, publication.updated_at = "staging", None, now_utc()
                run = db.get(KnowledgeBuildRun, publication.build_run_id)
                if run:
                    run.status, run.current_node, run.error_message, run.updated_at = "publishing", "publish_retry_queued", None, now_utc()
    else:
        if item.status not in {"queued", "running"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务当前不能取消")
        item.status, item.completed_at = "cancelled", now_utc()
        if item.payload.get("build_run_id"):
            from app.models import KnowledgeBuildRun

            run = db.get(KnowledgeBuildRun, UUID(str(item.payload["build_run_id"])))
            if run:
                run.status, run.current_node, run.completed_at, run.updated_at = "cancelled", "cancelled", now_utc(), now_utc()
    item.updated_at = now_utc()
    write_audit(db, actor_id=actor.id, action=f"jobs.{payload.action}", resource_type="background_job", resource_id=str(item.id), request=request, reason=payload.reason, before_data={"status": before}, after_data={"status": item.status})
    db.commit()
    if payload.action == "retry" and item.job_type in {"knowledge_build", "knowledge_publish"}:
        try:
            from app.knowledge.tasks import dispatch_background_job

            dispatch_background_job(item.id)
        except Exception as exc:
            failed_at = now_utc()
            item.status, item.error_message, item.completed_at, item.updated_at = "failed", f"任务队列不可用：{exc.__class__.__name__}", failed_at, failed_at
            if item.job_type == "knowledge_build" and item.payload.get("build_run_id"):
                from app.models import KnowledgeBuildRun

                run = db.get(KnowledgeBuildRun, UUID(str(item.payload["build_run_id"])))
                if run:
                    run.status, run.current_node = "failed", "retry_queue_dispatch_failed"
                    run.error_message, run.completed_at, run.updated_at = item.error_message, failed_at, failed_at
            elif item.job_type == "knowledge_publish" and item.payload.get("publication_id"):
                from app.models import KnowledgeBuildRun, KnowledgePublication

                publication = db.get(KnowledgePublication, UUID(str(item.payload["publication_id"])))
                if publication:
                    publication.status, publication.error_message, publication.updated_at = "failed", item.error_message, failed_at
                    run = db.get(KnowledgeBuildRun, publication.build_run_id)
                    if run:
                        run.status, run.current_node = "failed", "publish_retry_queue_dispatch_failed"
                        run.error_message, run.completed_at, run.updated_at = item.error_message, failed_at, failed_at
            db.commit()
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="任务队列暂不可用，任务仍可重试") from exc
    return _job_dict(item)


@router.get("/settings")
def system_settings(db: Session = Depends(get_db), actor: AdminActor = Depends(require_permission("settings.read"))) -> dict:
    items = db.scalars(select(SystemSetting).order_by(SystemSetting.key)).all()
    return {"items": [{"key": item.key, "value": item.value, "updated_at": item.updated_at} for item in items]}


@router.get("/settings/review-thresholds/impact")
def review_thresholds_impact(
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("settings.read")),
) -> dict:
    """Return the real work-item population that an SLA change will recalculate."""
    high_risk_hours, standard_hours = work_item_sla_hours(db)
    counts = db.execute(text("""
        SELECT
            count(*) AS total,
            count(*) FILTER (WHERE priority IN ('high', 'critical')) AS high_risk,
            count(*) FILTER (WHERE priority NOT IN ('high', 'critical') OR priority IS NULL) AS standard,
            count(*) FILTER (WHERE due_at IS NOT NULL AND due_at < now()) AS overdue,
            min(due_at) AS earliest_due_at
          FROM admin.work_items
         WHERE status IN ('open', 'claimed')
    """)).mappings().one()
    return {
        "effective_thresholds": {
            "high_risk_case_sla_hours": high_risk_hours,
            "standard_work_item_sla_hours": standard_hours,
        },
        "defaults": DEFAULT_REVIEW_THRESHOLDS,
        "active_work_items": dict(counts),
    }


@router.get("/settings/{key}/history")
def setting_history(
    key: str,
    page_size: int = Query(default=12, ge=1, le=30),
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("settings.read")),
) -> dict:
    """Expose immutable audit snapshots so operators can review or restore a setting."""
    rows = db.execute(text("""
        SELECT al.id::text AS id, al.before_data, al.after_data, al.reason, al.created_at,
               aa.display_name AS actor_name, aa.email AS actor_email
          FROM admin.audit_logs al
          LEFT JOIN admin.admin_accounts aa ON aa.id = al.actor_id
         WHERE al.action = 'settings.updated'
           AND al.resource_type = 'system_setting'
           AND al.resource_id = :key
         ORDER BY al.created_at DESC
         LIMIT :limit
    """), {"key": key, "limit": page_size}).mappings().all()
    return {"items": [dict(row) for row in rows], "total": len(rows)}


@router.put("/settings/{key}")
def put_setting(
    key: str,
    payload: SystemSettingRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: AdminActor = Depends(require_permission("settings.manage")),
) -> dict:
    if key != "review_thresholds":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="此设置不在通用设置中心维护；风险规则和服务健康配置请使用各自的专用入口。",
        )
    _validate_review_thresholds(payload.value)
    item = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    before = item.value if item else {}
    if item is None:
        item = SystemSetting(key=key, value=payload.value, updated_by_id=actor.id, updated_at=now_utc())
        db.add(item)
    else:
        item.value, item.updated_by_id, item.updated_at = payload.value, actor.id, now_utc()
    active_slas_recalculated = recalculate_active_work_item_slas(db) if key == "review_thresholds" else 0
    write_audit(db, actor_id=actor.id, action="settings.updated", resource_type="system_setting", resource_id=key, request=request, reason=payload.reason, before_data=before, after_data={"value": payload.value, "active_slas_recalculated": active_slas_recalculated})
    db.commit()
    return {"key": item.key, "value": item.value, "updated_at": item.updated_at, "active_slas_recalculated": active_slas_recalculated}


def _validate_review_thresholds(value: dict) -> None:
    allowed = {"high_risk_case_sla_hours", "standard_work_item_sla_hours"}
    unexpected = set(value) - allowed
    missing = allowed - set(value)
    if unexpected:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"不支持的 SLA 配置项：{', '.join(sorted(unexpected))}")
    if missing:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"请同时提供完整 SLA 配置：{', '.join(sorted(missing))}")
    for key in sorted(allowed):
        try:
            hours = int(value[key])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{key} 必须是小时数") from exc
        if not 1 <= hours <= 720:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{key} 必须在 1 到 720 小时之间")


def _validate_risk_rules(value: dict) -> None:
    allowed = set(DEFAULT_RISK_RULES)
    unexpected = set(value) - allowed
    if unexpected:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"不支持的风险规则：{', '.join(sorted(unexpected))}")
    hour_keys = {
        "login_failure_window_hours",
        "unusual_ip_window_hours",
        "report_surge_window_hours",
        "posting_spike_window_hours",
        "critical_case_sla_hours",
        "suppression_default_hours",
    }
    count_keys = {"login_failure_count", "unusual_ip_count", "report_surge_count", "posting_spike_count"}
    for key in hour_keys | count_keys | {"notification_window_minutes"}:
        if key not in value:
            continue
        try:
            number_value = int(value[key])
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{key} 必须是整数") from exc
        upper = 720 if key in hour_keys else (1440 if key == "notification_window_minutes" else 100)
        if not 1 <= number_value <= upper:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{key} 超出允许范围")
    if "sla_hours" in value:
        sla_hours = value["sla_hours"]
        if not isinstance(sla_hours, dict) or set(sla_hours) - {"low", "medium", "high", "critical"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="sla_hours 只能配置 low、medium、high、critical")
        for level, hours in sla_hours.items():
            try:
                number_hours = int(hours)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"sla_hours.{level} 必须是整数") from exc
            if not 1 <= number_hours <= 720:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"sla_hours.{level} 必须在 1 到 720 小时之间")


def _model_dict(item: SystemModelConfig) -> dict:
    credential_source = "model" if item.api_key_ciphertext else "system" if settings.dashscope_api_key else "missing"
    return {"id": str(item.id), "key": item.key, "label": item.label, "model_id": item.model_id, "api_base_url": item.api_base_url, "capability": item.capability, "enabled": item.enabled, "has_api_key": bool(item.api_key_ciphertext), "credential_source": credential_source, "last_test_status": item.last_test_status, "last_test_message": item.last_test_message, "last_test_at": item.last_test_at, "created_at": item.created_at, "updated_at": item.updated_at}


def _job_dict(item: BackgroundJob) -> dict:
    return {"id": str(item.id), "job_type": item.job_type, "status": item.status, "progress": item.progress, "payload": item.payload, "result": item.result, "error_message": item.error_message, "created_at": item.created_at, "updated_at": item.updated_at, "started_at": item.started_at, "completed_at": item.completed_at}

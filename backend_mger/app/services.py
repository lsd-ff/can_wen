from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ADMIN_SCHEMA,
    AdminAccount,
    AdminAccountRole,
    AdminInvite,
    AdminMfaFactor,
    AdminPermission,
    AdminRole,
    AdminRolePermission,
    AdminSession,
    AuditLog,
    SystemSetting,
    WorkItem,
)
from app.security import (
    build_totp_uri,
    create_access_token,
    create_mfa_ticket,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    generate_refresh_token,
    generate_totp_secret,
    hash_password,
    hash_token,
    now_utc,
    verify_password,
    verify_totp,
)


settings = get_settings()
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEFAULT_REVIEW_THRESHOLDS = {"high_risk_case_sla_hours": 4, "standard_work_item_sla_hours": 24}

PERMISSIONS: tuple[tuple[str, str, str], ...] = (
    ("dashboard.read", "查看运营总览", "workbench"),
    ("work_items.read", "查看待办", "workbench"),
    ("work_items.manage", "处理待办", "workbench"),
    ("users.read", "查看用户", "users"),
    ("users.manage", "处置用户", "users"),
    ("community.read", "查看社区管理数据", "community"),
    ("community.moderate", "审核社区内容", "community"),
    ("community.verify", "审核专业认证", "community"),
    ("diagnosis.read", "查看问诊摘要", "diagnosis"),
    ("diagnosis.review", "发布专家复核", "diagnosis"),
    ("diagnosis.sensitive.read", "查看问诊原文", "diagnosis"),
    ("husbandry.read", "查看养殖摘要", "husbandry"),
    ("husbandry.review", "发布病例复核", "husbandry"),
    ("husbandry.sensitive.read", "查看养殖原文", "husbandry"),
    ("knowledge.read", "查看知识中心", "knowledge"),
    ("knowledge.manage", "管理知识中心", "knowledge"),
    ("models.read", "查看模型监控", "models"),
    ("models.manage", "管理系统模型", "models"),
    ("assets.read", "查看文件资产", "security"),
    ("assets.manage", "处置文件资产", "security"),
    ("analytics.read", "查看运营分析", "analytics"),
    ("security.read", "查看风险事件", "security"),
    ("security.manage", "处置风险事件", "security"),
    ("admins.read", "查看管理员", "system"),
    ("admins.manage", "管理管理员", "system"),
    ("roles.read", "查看角色权限", "system"),
    ("roles.manage", "管理角色权限", "system"),
    ("audit.read", "查看审计日志", "system"),
    ("settings.read", "查看系统设置", "system"),
    ("settings.manage", "管理系统设置", "system"),
)

ROLE_DEFINITIONS: dict[str, tuple[str, str, set[str]]] = {
    "super_admin": ("超级管理员", "管理全部平台与管理员安全策略", {"*"}),
    "operations": (
        "运营管理员",
        "处理用户、公告、数据分析和日常运营任务",
        {"dashboard.read", "work_items.read", "work_items.manage", "users.read", "users.manage", "analytics.read"},
    ),
    "community_moderator": (
        "社区审核员",
        "处理举报、内容和专业认证",
        {"dashboard.read", "work_items.read", "work_items.manage", "community.read", "community.moderate", "community.verify"},
    ),
    "expert_reviewer": (
        "专家审核员",
        "复核问诊与养殖病例",
        {
            "dashboard.read", "work_items.read", "work_items.manage", "diagnosis.read", "diagnosis.review",
            "diagnosis.sensitive.read", "husbandry.read", "husbandry.review", "husbandry.sensitive.read",
        },
    ),
    "platform_operator": (
        "平台运维员",
        "管理模型、任务、文件和技术风险",
        {"dashboard.read", "models.read", "models.manage", "assets.read", "assets.manage", "security.read", "security.manage", "analytics.read", "knowledge.read", "knowledge.manage"},
    ),
}


@dataclass(frozen=True)
class AdminActor:
    id: UUID
    email: str
    display_name: str
    roles: tuple[str, ...]
    permissions: frozenset[str]
    session_id: UUID
    mfa_enrolled: bool


def ensure_admin_schema(db: Session) -> None:
    db.execute(text(f"CREATE SCHEMA IF NOT EXISTS {ADMIN_SCHEMA}"))
    db.commit()


def seed_rbac(db: Session) -> None:
    permissions = {permission.key: permission for permission in db.scalars(select(AdminPermission)).all()}
    for key, label, group_key in PERMISSIONS:
        if key not in permissions:
            permission = AdminPermission(key=key, label=label, group_key=group_key)
            db.add(permission)
            permissions[key] = permission
    db.flush()

    roles = {role.key: role for role in db.scalars(select(AdminRole)).all()}
    for key, (label, description, permission_keys) in ROLE_DEFINITIONS.items():
        role = roles.get(key)
        if role is None:
            role = AdminRole(key=key, label=label, description=description, is_system=True)
            db.add(role)
            db.flush()
            roles[key] = role
        existing = {entry.permission_id for entry in db.scalars(select(AdminRolePermission).where(AdminRolePermission.role_id == role.id)).all()}
        desired_keys = set(permissions) if "*" in permission_keys else permission_keys
        for permission_key in desired_keys:
            permission = permissions[permission_key]
            if permission.id not in existing:
                db.add(AdminRolePermission(role_id=role.id, permission_id=permission.id))
    db.commit()


def bootstrap_super_admin(db: Session) -> None:
    email = _normalize_email(settings.bootstrap_email or "") if settings.bootstrap_email else None
    password = settings.bootstrap_password
    if not email or not password:
        return
    account = db.scalar(select(AdminAccount).where(AdminAccount.email == email))
    if account is None:
        account = AdminAccount(email=email, display_name="系统管理员", password_hash=hash_password(password), status="active", activated_at=now_utc())
        db.add(account)
        db.flush()
    role = db.scalar(select(AdminRole).where(AdminRole.key == "super_admin"))
    if role is not None:
        linked = db.scalar(select(AdminAccountRole).where(AdminAccountRole.admin_account_id == account.id, AdminAccountRole.role_id == role.id))
        if linked is None:
            db.add(AdminAccountRole(admin_account_id=account.id, role_id=role.id))
    db.commit()


def start_login(db: Session, *, email: str, password: str, request: Request, device_name: str | None) -> dict:
    account = db.scalar(select(AdminAccount).where(AdminAccount.email == _normalize_email(email)))
    if account is None or account.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确")
    current_time = now_utc()
    if account.locked_until and account.locked_until > current_time:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="账号暂时锁定，请稍后再试")
    if not verify_password(password, account.password_hash):
        account.failed_attempts += 1
        if account.failed_attempts >= 5:
            account.status = "locked"
            account.locked_until = current_time + timedelta(minutes=15)
        db.commit()
        write_audit(db, actor_id=account.id, action="auth.login_failed", resource_type="admin_account", resource_id=str(account.id), request=request)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码不正确")
    account.failed_attempts = 0
    account.locked_until = None
    db.commit()
    ticket = create_mfa_ticket(account_id=str(account.id), purpose="login")
    return {"mfa_required": True, "mfa_setup_required": not account.mfa_enrolled, "mfa_ticket": ticket, "device_name": device_name}


def setup_mfa(db: Session, *, mfa_ticket: str) -> dict:
    account = _account_from_mfa_ticket(db, mfa_ticket, purpose="login")
    factor = db.scalar(select(AdminMfaFactor).where(AdminMfaFactor.admin_account_id == account.id, AdminMfaFactor.factor_type == "totp"))
    if factor is None:
        secret = generate_totp_secret()
        factor = AdminMfaFactor(admin_account_id=account.id, factor_type="totp", secret_ciphertext=encrypt_secret(secret))
        db.add(factor)
        db.commit()
    else:
        secret = decrypt_secret(factor.secret_ciphertext)
    return {"mfa_ticket": mfa_ticket, "secret": secret, "otpauth_uri": build_totp_uri(email=account.email, secret=secret)}


def verify_mfa_and_issue_tokens(db: Session, *, mfa_ticket: str, code: str, request: Request, device_name: str | None) -> dict:
    account = _account_from_mfa_ticket(db, mfa_ticket, purpose="login")
    factor = db.scalar(select(AdminMfaFactor).where(AdminMfaFactor.admin_account_id == account.id, AdminMfaFactor.factor_type == "totp"))
    if factor is None or not verify_totp(decrypt_secret(factor.secret_ciphertext), code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="双重验证代码不正确")
    if not account.mfa_enrolled:
        account.mfa_enrolled = True
        factor.verified_at = now_utc()
    return issue_tokens(db, account=account, request=request, device_name=device_name)


def accept_invite(db: Session, *, token: str, password: str) -> dict:
    invite = db.scalar(select(AdminInvite).where(AdminInvite.token_hash == hash_token(token), AdminInvite.status == "pending"))
    if invite is None or invite.expires_at <= now_utc():
        if invite is not None:
            invite.status = "expired"
            db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请无效或已过期")
    account = db.scalar(select(AdminAccount).where(AdminAccount.email == invite.email))
    if account is None:
        account = AdminAccount(email=invite.email, display_name=invite.display_name, password_hash=hash_password(password), status="active", activated_at=now_utc(), invited_by_id=invite.invited_by_id)
        db.add(account)
        db.flush()
    elif account.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="此邀请已经被使用")
    else:
        account.password_hash = hash_password(password)
        account.status = "active"
        account.activated_at = now_utc()
    roles = {role.key: role for role in db.scalars(select(AdminRole).where(AdminRole.key.in_(invite.role_keys))).all()}
    for role_key in invite.role_keys:
        role = roles.get(role_key)
        if role is not None:
            existing = db.scalar(select(AdminAccountRole).where(AdminAccountRole.admin_account_id == account.id, AdminAccountRole.role_id == role.id))
            if existing is None:
                db.add(AdminAccountRole(admin_account_id=account.id, role_id=role.id))
    invite.status = "accepted"
    invite.accepted_at = now_utc()
    db.commit()
    return {"mfa_required": True, "mfa_setup_required": True, "mfa_ticket": create_mfa_ticket(account_id=str(account.id), purpose="login")}


def refresh_tokens(db: Session, *, refresh_token: str, request: Request) -> dict:
    session = db.scalar(select(AdminSession).where(AdminSession.refresh_token_hash == hash_token(refresh_token), AdminSession.status == "active"))
    if session is None or session.expires_at <= now_utc():
        if session is not None:
            session.status = "expired"
            db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员登录已失效")
    account = db.get(AdminAccount, session.admin_account_id)
    if account is None or account.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理员账号不可用")
    session.last_used_at = now_utc()
    return _token_response(db, account=account, session=session, refresh_token=refresh_token, request=request)


def logout(db: Session, *, refresh_token: str, request: Request) -> None:
    session = db.scalar(select(AdminSession).where(AdminSession.refresh_token_hash == hash_token(refresh_token), AdminSession.status == "active"))
    if session is not None:
        session.status = "revoked"
        session.revoked_at = now_utc()
        write_audit(db, actor_id=session.admin_account_id, action="auth.logout", resource_type="admin_session", resource_id=str(session.id), request=request)
        db.commit()


def issue_tokens(db: Session, *, account: AdminAccount, request: Request, device_name: str | None) -> dict:
    current_time = now_utc()
    refresh_token = generate_refresh_token()
    session = AdminSession(
        admin_account_id=account.id,
        refresh_token_hash=hash_token(refresh_token),
        device_name=device_name,
        ip_address=_request_ip(request),
        user_agent=request.headers.get("user-agent"),
        expires_at=current_time + timedelta(days=settings.refresh_token_ttl_days),
        last_used_at=current_time,
    )
    db.add(session)
    account.last_seen_at = current_time
    account.failed_attempts = 0
    account.locked_until = None
    db.flush()
    write_audit(db, actor_id=account.id, action="auth.login", resource_type="admin_session", resource_id=str(session.id), request=request)
    db.commit()
    return _token_response(db, account=account, session=session, refresh_token=refresh_token, request=request)


def current_actor(db: Session, *, token: str) -> AdminActor:
    try:
        payload = decode_token(token, expected_type="access")
        account_id = UUID(str(payload["sub"]))
        session_id = UUID(str(payload["sid"]))
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员登录无效") from exc
    session = db.scalar(select(AdminSession).where(AdminSession.id == session_id, AdminSession.admin_account_id == account_id, AdminSession.status == "active"))
    account = db.get(AdminAccount, account_id)
    if session is None or session.expires_at <= now_utc() or account is None or account.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="管理员登录已失效")
    roles, permissions = get_roles_and_permissions(db, account.id)
    return AdminActor(id=account.id, email=account.email, display_name=account.display_name, roles=tuple(roles), permissions=frozenset(permissions), session_id=session.id, mfa_enrolled=account.mfa_enrolled)


def get_roles_and_permissions(db: Session, account_id: UUID) -> tuple[list[str], set[str]]:
    role_rows = db.execute(
        select(AdminRole.key, AdminRole.id)
        .join(AdminAccountRole, AdminAccountRole.role_id == AdminRole.id)
        .where(AdminAccountRole.admin_account_id == account_id)
    ).all()
    roles = [row.key for row in role_rows]
    if "super_admin" in roles:
        return roles, {key for key, _, _ in PERMISSIONS}
    role_ids = [row.id for row in role_rows]
    if not role_ids:
        return roles, set()
    permissions = set(
        db.scalars(
            select(AdminPermission.key)
            .join(AdminRolePermission, AdminRolePermission.permission_id == AdminPermission.id)
            .where(AdminRolePermission.role_id.in_(role_ids))
        ).all()
    )
    return roles, permissions


def require(actor: AdminActor, permission: str) -> None:
    if permission not in actor.permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有执行此操作的权限")


def write_audit(
    db: Session,
    *,
    actor_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str,
    request: Request | None = None,
    reason: str | None = None,
    before_data: dict | None = None,
    after_data: dict | None = None,
) -> AuditLog:
    record = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        reason=reason,
        before_data=jsonable_encoder(before_data or {}),
        after_data=jsonable_encoder(after_data or {}),
        request_id=request.headers.get("x-request-id") if request is not None else None,
        ip_address=_request_ip(request) if request is not None else None,
        user_agent=request.headers.get("user-agent") if request is not None else None,
    )
    db.add(record)
    return record


def complete_work_items_for_resource(
    db: Session,
    *,
    actor_id: UUID,
    resource_type: str,
    resource_id: str,
) -> int:
    """Close active queue items after their underlying business action is completed."""
    items = db.scalars(
        select(WorkItem)
        .where(
            WorkItem.resource_type == resource_type,
            WorkItem.resource_id == resource_id,
            WorkItem.status.in_(("open", "claimed")),
        )
        .order_by(WorkItem.created_at.desc())
    ).all()
    completed_at = now_utc()
    for item in items:
        item.status = "completed"
        item.completed_at = completed_at
        item.updated_at = completed_at
        item.version += 1
    return len(items)


def work_item_sla_hours(db: Session) -> tuple[int, int]:
    setting = db.scalar(select(SystemSetting).where(SystemSetting.key == "review_thresholds"))
    values = setting.value if setting is not None and isinstance(setting.value, dict) else {}
    high_risk = _bounded_positive_int(values.get("high_risk_case_sla_hours"), DEFAULT_REVIEW_THRESHOLDS["high_risk_case_sla_hours"])
    standard = _bounded_positive_int(values.get("standard_work_item_sla_hours"), DEFAULT_REVIEW_THRESHOLDS["standard_work_item_sla_hours"])
    return high_risk, standard


def recalculate_active_work_item_slas(db: Session) -> int:
    high_risk_hours, standard_hours = work_item_sla_hours(db)
    items = db.scalars(select(WorkItem).where(WorkItem.status.in_(("open", "claimed")))).all()
    updated_at = now_utc()
    for item in items:
        hours = high_risk_hours if item.priority in {"high", "critical"} else standard_hours
        item.due_at = item.created_at + timedelta(hours=hours)
        item.updated_at = updated_at
        item.version += 1
    return len(items)


def _bounded_positive_int(value: object, fallback: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return fallback
    return result if 1 <= result <= 720 else fallback


def create_invite(db: Session, *, actor: AdminActor, email: str, display_name: str, role_keys: list[str], expires_in_hours: int, request: Request) -> tuple[AdminInvite, str]:
    require(actor, "admins.manage")
    normalized_email = _normalize_email(email)
    role_keys = list(dict.fromkeys(role_keys))
    found_keys = set(db.scalars(select(AdminRole.key).where(AdminRole.key.in_(role_keys))).all())
    if found_keys != set(role_keys):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="包含不存在的角色")
    token = secrets.token_urlsafe(32)
    invite = AdminInvite(email=normalized_email, display_name=display_name.strip(), token_hash=hash_token(token), role_keys=role_keys, invited_by_id=actor.id, expires_at=now_utc() + timedelta(hours=expires_in_hours))
    db.add(invite)
    db.flush()
    write_audit(db, actor_id=actor.id, action="admins.invite", resource_type="admin_invite", resource_id=str(invite.id), request=request, reason="邀请管理员", after_data={"email": normalized_email, "roles": role_keys})
    db.commit()
    return invite, token


def _token_response(db: Session, *, account: AdminAccount, session: AdminSession, refresh_token: str, request: Request) -> dict:
    roles, permissions = get_roles_and_permissions(db, account.id)
    access_token, expires_in = create_access_token(account_id=str(account.id), session_id=str(session.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "admin": {"id": str(account.id), "email": account.email, "display_name": account.display_name, "roles": roles, "permissions": sorted(permissions), "mfa_enrolled": account.mfa_enrolled},
    }


def _account_from_mfa_ticket(db: Session, ticket: str, *, purpose: str) -> AdminAccount:
    try:
        payload = decode_token(ticket, expected_type="mfa-ticket")
        if payload.get("purpose") != purpose:
            raise ValueError("wrong purpose")
        account_id = UUID(str(payload["sub"]))
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="双重验证会话无效") from exc
    account = db.get(AdminAccount, account_id)
    if account is None or account.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="管理员账号不可用")
    return account


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="邮箱格式不正确")
    return normalized


def _request_ip(request: Request | None) -> str | None:
    return request.client.host if request is not None and request.client is not None else None

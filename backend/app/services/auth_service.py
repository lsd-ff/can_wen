from __future__ import annotations

import re
from datetime import timedelta
from uuid import UUID
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_numeric_code,
    generate_refresh_token,
    hash_token,
    hash_verification_code,
    now_utc,
    verify_verification_code,
)
from app.models import AuthSession, AuthVerificationCode, LoginEvent, User, UserIdentity
from app.schemas.auth import (
    AuthUserResponse,
    EmailLoginResponse,
    EmailVerificationCodeResponse,
    PhoneVerificationCodeResponse,
    RefreshTokenResponse,
    LogoutResponse,
)
from app.services.email_delivery import send_login_code_email, smtp_is_configured
from app.services.sms_delivery import send_login_code_sms, sms_is_configured
from app.services.storage_service import upload_public_file


settings = get_settings()
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
AVATAR_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def request_email_verification_code(
    db: Session,
    *,
    email: str,
    request_ip: str | None,
    request_user_agent: str | None,
) -> EmailVerificationCodeResponse:
    normalized_email = normalize_supported_email(email)
    _ensure_code_request_allowed(db, provider="email", target=normalized_email)
    code = generate_numeric_code()
    sent_at = now_utc()
    expires_at = sent_at + timedelta(seconds=settings.auth_code_ttl_seconds)
    sent = send_login_code_email(normalized_email, code)

    verification = AuthVerificationCode(
        provider="email",
        target=normalized_email,
        code_hash=hash_verification_code("email", normalized_email, code),
        purpose="login",
        status="pending",
        request_ip=request_ip,
        request_user_agent=request_user_agent,
        sent_at=sent_at,
        expires_at=expires_at,
        metadata_={"delivery": "smtp" if sent else "dev"},
    )
    db.add(verification)
    db.add(
        LoginEvent(
            provider="email",
            target=normalized_email,
            event_type="verification_requested",
            ip_address=request_ip,
            user_agent=request_user_agent,
            metadata_={"delivery": "smtp" if sent else "dev"},
        )
    )
    db.commit()

    return EmailVerificationCodeResponse(
        status="sent" if sent else "dev_sent",
        email=normalized_email,
        expires_in=settings.auth_code_ttl_seconds,
        dev_code=code if settings.auth_dev_code_enabled and not smtp_is_configured() else None,
    )


def request_phone_verification_code(
    db: Session,
    *,
    phone_number: str,
    request_ip: str | None,
    request_user_agent: str | None,
) -> PhoneVerificationCodeResponse:
    normalized_phone = normalize_supported_phone(phone_number)
    _ensure_code_request_allowed(db, provider="phone", target=normalized_phone)
    code = generate_numeric_code()
    sent_at = now_utc()
    expires_at = sent_at + timedelta(seconds=settings.auth_code_ttl_seconds)
    sent = send_login_code_sms(normalized_phone, code)

    verification = AuthVerificationCode(
        provider="phone",
        target=normalized_phone,
        code_hash=hash_verification_code("phone", normalized_phone, code),
        purpose="login",
        status="pending",
        request_ip=request_ip,
        request_user_agent=request_user_agent,
        sent_at=sent_at,
        expires_at=expires_at,
        metadata_={"delivery": "sms" if sent else "dev"},
    )
    db.add(verification)
    db.add(
        LoginEvent(
            provider="phone",
            target=normalized_phone,
            event_type="verification_requested",
            ip_address=request_ip,
            user_agent=request_user_agent,
            metadata_={"delivery": "sms" if sent else "dev"},
        )
    )
    db.commit()

    return PhoneVerificationCodeResponse(
        status="sent" if sent else "dev_sent",
        phone_number=normalized_phone,
        expires_in=settings.auth_code_ttl_seconds,
        dev_code=code if settings.auth_dev_code_enabled and not sms_is_configured() else None,
    )


def login_with_email_code(
    db: Session,
    *,
    email: str,
    code: str,
    request_ip: str | None,
    request_user_agent: str | None,
    device_id: str | None,
    device_name: str | None,
) -> EmailLoginResponse:
    normalized_email = normalize_supported_email(email)
    return _login_with_verification_code(
        db,
        provider="email",
        target=normalized_email,
        code=code,
        request_ip=request_ip,
        request_user_agent=request_user_agent,
        device_id=device_id,
        device_name=device_name,
    )


def login_with_phone_code(
    db: Session,
    *,
    phone_number: str,
    code: str,
    request_ip: str | None,
    request_user_agent: str | None,
    device_id: str | None,
    device_name: str | None,
) -> EmailLoginResponse:
    normalized_phone = normalize_supported_phone(phone_number)
    return _login_with_verification_code(
        db,
        provider="phone",
        target=normalized_phone,
        code=code,
        request_ip=request_ip,
        request_user_agent=request_user_agent,
        device_id=device_id,
        device_name=device_name,
    )


def logout_with_refresh_token(
    db: Session,
    *,
    refresh_token: str,
    request_ip: str | None,
    request_user_agent: str | None,
) -> LogoutResponse:
    refresh_token_hash = hash_token(refresh_token.strip())
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.refresh_token_hash == refresh_token_hash,
            AuthSession.status == "active",
        )
    )

    if session is None:
        return LogoutResponse(status="ok")

    current_time = now_utc()
    provider = session.identity.provider if session.identity is not None else None
    session.status = "revoked"
    session.revoked_at = current_time
    session.last_used_at = current_time
    db.add(
        LoginEvent(
            user_id=session.user_id,
            identity_id=session.identity_id,
            session_id=session.id,
            provider=provider,
            event_type="logout",
            ip_address=request_ip,
            user_agent=request_user_agent,
        )
    )
    db.add(
        LoginEvent(
            user_id=session.user_id,
            identity_id=session.identity_id,
            session_id=session.id,
            provider=provider,
            event_type="session_revoked",
            ip_address=request_ip,
            user_agent=request_user_agent,
        )
    )
    db.commit()

    return LogoutResponse(status="ok")


def refresh_access_token(
    db: Session,
    *,
    refresh_token: str,
    request_ip: str | None,
    request_user_agent: str | None,
) -> RefreshTokenResponse:
    refresh_token_hash = hash_token(refresh_token.strip())
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.refresh_token_hash == refresh_token_hash,
            AuthSession.status == "active",
        )
    )

    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效")

    current_time = now_utc()
    if session.expires_at <= current_time:
        session.status = "expired"
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已过期")

    user = session.user
    _ensure_active_user(user)
    session.last_used_at = current_time
    access_token, expires_in = create_access_token(user_id=str(user.id), session_id=str(session.id))
    provider = session.identity.provider if session.identity is not None else None
    db.add(
        LoginEvent(
            user_id=session.user_id,
            identity_id=session.identity_id,
            session_id=session.id,
            provider=provider,
            target=session.identity.provider_subject if session.identity is not None else None,
            event_type="session_refreshed",
            ip_address=request_ip,
            user_agent=request_user_agent,
        )
    )
    db.commit()

    return RefreshTokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=_auth_user_response(db, user),
    )


def get_current_user_profile(db: Session, *, access_token: str) -> AuthUserResponse:
    session = _get_active_session_from_access_token(db, access_token)
    user = session.user
    _ensure_active_user(user)

    return _auth_user_response(db, user)


def get_current_user(db: Session, *, access_token: str) -> User:
    session = _get_active_session_from_access_token(db, access_token)
    user = session.user
    _ensure_active_user(user)

    return user


def get_current_auth_session(db: Session, *, access_token: str) -> AuthSession:
    session = _get_active_session_from_access_token(db, access_token)
    _ensure_active_user(session.user)
    return session


def update_current_user_profile(
    db: Session,
    *,
    access_token: str,
    display_name: str,
    username: str,
) -> AuthUserResponse:
    normalized_display_name = display_name.strip()
    if not normalized_display_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="显示名称不能为空")

    normalized_username = username.strip()
    if not normalized_username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名不能为空")
    if not USERNAME_PATTERN.fullmatch(normalized_username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名只能包含字母、数字、下划线、点和短横线")

    session = _get_active_session_from_access_token(db, access_token)
    user = session.user
    _ensure_active_user(user)

    current_time = now_utc()
    user.display_name = normalized_display_name
    user.username = normalized_username
    user.updated_at = current_time
    session.last_used_at = current_time
    db.commit()
    db.refresh(user)

    return _auth_user_response(db, user)


def upload_current_user_avatar(
    db: Session,
    *,
    access_token: str,
    content: bytes,
    content_type: str | None,
) -> AuthUserResponse:
    normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    extension = AVATAR_CONTENT_TYPES.get(normalized_content_type)
    if extension is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="头像只支持 JPG、PNG 或 WebP 图片")

    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="头像图片不能为空")

    if len(content) > settings.avatar_upload_max_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="头像图片不能超过 2MB")

    if not _has_supported_image_signature(content, normalized_content_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="头像图片格式不正确")

    session = _get_active_session_from_access_token(db, access_token)
    user = session.user
    _ensure_active_user(user)

    object_key = f"avatars/{user.id}/{uuid4().hex}.{extension}"
    avatar_url = upload_public_file(
        object_key=object_key,
        content=content,
        content_type=normalized_content_type,
    )

    current_time = now_utc()
    user.avatar_url = avatar_url
    user.updated_at = current_time
    session.last_used_at = current_time
    db.commit()
    db.refresh(user)

    return _auth_user_response(db, user)


def _has_supported_image_signature(content: bytes, content_type: str) -> bool:
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False


def normalize_supported_email(email: str) -> str:
    normalized = email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱格式不正确")

    domain = normalized.rsplit("@", 1)[1]
    if domain not in settings.allowed_email_domains:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="暂只支持 QQ 邮箱和网易邮箱")

    return normalized


def normalize_supported_phone(phone_number: str) -> str:
    normalized = re.sub(r"[\s-]", "", phone_number.strip())
    if normalized.startswith("0086"):
        normalized = normalized[4:]
    elif normalized.startswith("+86"):
        normalized = normalized[3:]

    if not PHONE_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="手机号格式不正确")

    return f"+86{normalized}"


def _get_latest_pending_code(db: Session, *, provider: str, target: str) -> AuthVerificationCode | None:
    return db.scalar(
        select(AuthVerificationCode)
        .where(
            AuthVerificationCode.provider == provider,
            AuthVerificationCode.target == target,
            AuthVerificationCode.purpose == "login",
            AuthVerificationCode.status == "pending",
        )
        .order_by(desc(AuthVerificationCode.created_at))
    )


def _record_login_failure(
    db: Session,
    *,
    provider: str,
    target: str,
    reason: str,
    request_ip: str | None,
    request_user_agent: str | None,
) -> None:
    db.add(
        LoginEvent(
            provider=provider,
            target=target,
            event_type="login_failed",
            failure_reason=reason,
            ip_address=request_ip,
            user_agent=request_user_agent,
        )
    )


def _display_name_from_email(email: str) -> str:
    return email.split("@", 1)[0][:32]


def _display_name_from_phone(phone_number: str) -> str:
    return f"用户{phone_number[-4:]}"


def _ensure_code_request_allowed(db: Session, *, provider: str, target: str) -> None:
    current_time = now_utc()
    latest = db.scalar(
        select(AuthVerificationCode)
        .where(
            AuthVerificationCode.provider == provider,
            AuthVerificationCode.target == target,
            AuthVerificationCode.purpose == "login",
        )
        .order_by(desc(AuthVerificationCode.created_at))
    )
    if latest is not None and latest.created_at >= current_time - timedelta(
        seconds=settings.auth_code_resend_cooldown_seconds
    ):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="验证码发送太频繁，请稍后再试")

    hourly_count = db.scalar(
        select(func.count())
        .select_from(AuthVerificationCode)
        .where(
            AuthVerificationCode.provider == provider,
            AuthVerificationCode.target == target,
            AuthVerificationCode.purpose == "login",
            AuthVerificationCode.created_at >= current_time - timedelta(hours=1),
        )
    )
    if (hourly_count or 0) >= settings.auth_code_hourly_limit:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="验证码请求次数过多，请稍后再试")


def _login_with_verification_code(
    db: Session,
    *,
    provider: str,
    target: str,
    code: str,
    request_ip: str | None,
    request_user_agent: str | None,
    device_id: str | None,
    device_name: str | None,
) -> EmailLoginResponse:
    normalized_code = code.strip()
    verification = _get_latest_pending_code(db, provider=provider, target=target)
    current_time = now_utc()

    if verification is None:
        _record_login_failure(
            db,
            provider=provider,
            target=target,
            reason="verification_code_not_found",
            request_ip=request_ip,
            request_user_agent=request_user_agent,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码不存在或已失效")

    if verification.expires_at <= current_time:
        verification.status = "expired"
        _record_login_failure(
            db,
            provider=provider,
            target=target,
            reason="code_expired",
            request_ip=request_ip,
            request_user_agent=request_user_agent,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码已过期")

    if verification.attempt_count >= verification.max_attempts:
        verification.status = "blocked"
        _record_login_failure(
            db,
            provider=provider,
            target=target,
            reason="too_many_attempts",
            request_ip=request_ip,
            request_user_agent=request_user_agent,
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码尝试次数过多")

    if not verify_verification_code(provider, target, normalized_code, verification.code_hash):
        verification.attempt_count += 1
        if verification.attempt_count >= verification.max_attempts:
            verification.status = "blocked"
        db.add(
            LoginEvent(
                provider=provider,
                target=target,
                event_type="verification_failed",
                failure_reason="code_invalid",
                ip_address=request_ip,
                user_agent=request_user_agent,
            )
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误")

    verification.status = "used"
    verification.used_at = current_time
    db.add(
        LoginEvent(
            provider=provider,
            target=target,
            event_type="verification_succeeded",
            ip_address=request_ip,
            user_agent=request_user_agent,
        )
    )

    identity = db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == provider,
            UserIdentity.provider_subject == target,
            UserIdentity.unbound_at.is_(None),
        )
    )
    is_new_identity = identity is None

    if identity is None:
        default_name = _display_name_from_email(target) if provider == "email" else _display_name_from_phone(target)
        user = User(display_name=default_name, username=default_name, last_seen_at=current_time)
        db.add(user)
        db.flush()
        identity = UserIdentity(
            user_id=user.id,
            provider=provider,
            provider_subject=target,
            phone_country_code="+86" if provider == "phone" else None,
            phone_number=target if provider == "phone" else None,
            email=target if provider == "email" else None,
            is_primary=True,
            verified_at=current_time,
        )
        db.add(identity)
        db.flush()
        db.add(
            LoginEvent(
                user_id=user.id,
                identity_id=identity.id,
                provider=provider,
                target=target,
                event_type="identity_bound",
                ip_address=request_ip,
                user_agent=request_user_agent,
            )
        )
    else:
        user = identity.user
        if user.status != "active":
            _record_login_failure(
                db,
                provider=provider,
                target=target,
                reason="user_disabled",
                request_ip=request_ip,
                request_user_agent=request_user_agent,
            )
            db.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号不可用")
        user.last_seen_at = current_time
        if not user.username:
            user.username = _display_name_from_email(target) if provider == "email" else _display_name_from_phone(target)
        if identity.verified_at is None:
            identity.verified_at = current_time

    refresh_token = generate_refresh_token()
    session = AuthSession(
        user_id=user.id,
        identity_id=identity.id,
        refresh_token_hash=hash_token(refresh_token),
        status="active",
        device_id=device_id,
        device_name=device_name,
        ip_address=request_ip,
        user_agent=request_user_agent,
        expires_at=current_time + timedelta(days=settings.auth_refresh_token_ttl_days),
        last_used_at=current_time,
        metadata_={"provider": provider, "new_identity": is_new_identity},
    )
    db.add(session)
    db.flush()

    access_token, expires_in = create_access_token(user_id=str(user.id), session_id=str(session.id))
    db.add(
        LoginEvent(
            user_id=user.id,
            identity_id=identity.id,
            session_id=session.id,
            provider=provider,
            target=target,
            event_type="login_success",
            ip_address=request_ip,
            user_agent=request_user_agent,
            metadata_={"new_identity": is_new_identity},
        )
    )
    db.commit()

    return EmailLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        user=_auth_user_response(db, user),
    )


def _get_active_session_from_access_token(db: Session, access_token: str) -> AuthSession:
    try:
        payload = decode_access_token(access_token.strip())
        user_id = UUID(str(payload["sub"]))
        session_id = UUID(str(payload["sid"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态无效") from exc

    session = db.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.status == "active",
        )
    )

    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效")

    if session.expires_at <= now_utc():
        session.status = "expired"
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录状态已过期")

    return session


def _ensure_active_user(user: User) -> None:
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号不可用")


def _primary_email_for_user(db: Session, user_id: UUID) -> str:
    identity = db.scalar(
        select(UserIdentity)
        .where(
            UserIdentity.user_id == user_id,
            UserIdentity.provider == "email",
            UserIdentity.unbound_at.is_(None),
        )
        .order_by(UserIdentity.is_primary.desc(), desc(UserIdentity.bound_at))
    )

    if identity is None:
        return ""
    return identity.email or identity.provider_subject


def _primary_phone_for_user(db: Session, user_id: UUID) -> str:
    identity = db.scalar(
        select(UserIdentity)
        .where(
            UserIdentity.user_id == user_id,
            UserIdentity.provider == "phone",
            UserIdentity.unbound_at.is_(None),
        )
        .order_by(UserIdentity.is_primary.desc(), desc(UserIdentity.bound_at))
    )

    if identity is None:
        return ""
    return identity.phone_number or identity.provider_subject


def _auth_user_response(db: Session, user: User) -> AuthUserResponse:
    return AuthUserResponse(
        id=str(user.id),
        display_name=user.display_name,
        username=user.username,
        role=user.role,
        email=_primary_email_for_user(db, user.id),
        phone_number=_primary_phone_for_user(db, user.id),
        avatar_url=user.avatar_url,
    )

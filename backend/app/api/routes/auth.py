from ipaddress import ip_address

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db_session
from app.schemas.auth import (
    AuthUserResponse,
    EmailLoginRequest,
    EmailLoginResponse,
    EmailVerificationCodeRequest,
    EmailVerificationCodeResponse,
    LogoutRequest,
    LogoutResponse,
    PhoneLoginRequest,
    PhoneVerificationCodeRequest,
    PhoneVerificationCodeResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    UpdateUserProfileRequest,
)
from app.services.auth_service import (
    get_current_user_profile,
    login_with_email_code,
    login_with_phone_code,
    logout_with_refresh_token,
    refresh_access_token,
    request_email_verification_code,
    request_phone_verification_code,
    upload_current_user_avatar,
    update_current_user_profile,
)


router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/email/verification-codes", response_model=EmailVerificationCodeResponse)
def request_email_code(
    payload: EmailVerificationCodeRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> EmailVerificationCodeResponse:
    return request_email_verification_code(
        db,
        email=payload.email,
        request_ip=_request_ip(request),
        request_user_agent=request.headers.get("user-agent"),
    )


@router.post("/email/login", response_model=EmailLoginResponse)
def email_login(
    payload: EmailLoginRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> EmailLoginResponse:
    return login_with_email_code(
        db,
        email=payload.email,
        code=payload.code,
        request_ip=_request_ip(request),
        request_user_agent=request.headers.get("user-agent"),
        device_id=payload.device_id,
        device_name=payload.device_name,
    )


@router.post("/phone/verification-codes", response_model=PhoneVerificationCodeResponse)
def request_phone_code(
    payload: PhoneVerificationCodeRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> PhoneVerificationCodeResponse:
    return request_phone_verification_code(
        db,
        phone_number=payload.phone_number,
        request_ip=_request_ip(request),
        request_user_agent=request.headers.get("user-agent"),
    )


@router.post("/phone/login", response_model=EmailLoginResponse)
def phone_login(
    payload: PhoneLoginRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> EmailLoginResponse:
    return login_with_phone_code(
        db,
        phone_number=payload.phone_number,
        code=payload.code,
        request_ip=_request_ip(request),
        request_user_agent=request.headers.get("user-agent"),
        device_id=payload.device_id,
        device_name=payload.device_name,
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh_token(
    payload: RefreshTokenRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> RefreshTokenResponse:
    return refresh_access_token(
        db,
        refresh_token=payload.refresh_token,
        request_ip=_request_ip(request),
        request_user_agent=request.headers.get("user-agent"),
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    payload: LogoutRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> LogoutResponse:
    return logout_with_refresh_token(
        db,
        refresh_token=payload.refresh_token,
        request_ip=_request_ip(request),
        request_user_agent=request.headers.get("user-agent"),
    )


@router.get("/me", response_model=AuthUserResponse)
def current_user_profile(
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthUserResponse:
    return get_current_user_profile(db, access_token=_bearer_token(request))


@router.patch("/me", response_model=AuthUserResponse)
def update_user_profile(
    payload: UpdateUserProfileRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AuthUserResponse:
    return update_current_user_profile(
        db,
        access_token=_bearer_token(request),
        display_name=payload.display_name,
        username=payload.username,
    )


@router.post("/me/avatar", response_model=AuthUserResponse)
async def upload_user_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    db: Session = Depends(get_db_session),
) -> AuthUserResponse:
    access_token = _bearer_token(request)
    content = await avatar.read(settings.avatar_upload_max_bytes + 1)
    if len(content) > settings.avatar_upload_max_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="头像图片不能超过 2MB")

    return upload_current_user_avatar(
        db,
        access_token=access_token,
        content=content,
        content_type=avatar.content_type,
    )


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return token.strip()


def _request_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    try:
        return str(ip_address(request.client.host))
    except ValueError:
        return None

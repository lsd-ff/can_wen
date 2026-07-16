from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    AcceptInviteRequest,
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    MfaRequiredResponse,
    MfaSetupResponse,
    MfaTicketRequest,
    MfaVerifyRequest,
    RefreshRequest,
)
from app.services import accept_invite, logout, refresh_tokens, setup_mfa, start_login, verify_mfa_and_issue_tokens


router = APIRouter(prefix="/auth", tags=["admin-auth"])


@router.post("/login", response_model=AuthResponse | MfaRequiredResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    return start_login(db, email=payload.email, password=payload.password, request=request, device_name=payload.device_name)


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(payload: MfaTicketRequest, db: Session = Depends(get_db)) -> dict:
    return setup_mfa(db, mfa_ticket=payload.mfa_ticket)


@router.post("/mfa/verify", response_model=AuthResponse)
def mfa_verify(payload: MfaVerifyRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    return verify_mfa_and_issue_tokens(db, mfa_ticket=payload.mfa_ticket, code=payload.code, request=request, device_name=payload.device_name)


@router.post("/invitations/accept", response_model=MfaRequiredResponse)
def invitations_accept(payload: AcceptInviteRequest, db: Session = Depends(get_db)) -> dict:
    return accept_invite(db, token=payload.token, password=payload.password)


@router.post("/refresh", response_model=AuthResponse)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    return refresh_tokens(db, refresh_token=payload.refresh_token, request=request)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_current(payload: LogoutRequest, request: Request, db: Session = Depends(get_db)) -> None:
    logout(db, refresh_token=payload.refresh_token, request=request)

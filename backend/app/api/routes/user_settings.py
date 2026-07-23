from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.routes.auth import _bearer_token
from app.db.session import get_db_session
from app.schemas.user_settings import (
    AccountDeleteRequest,
    AuthSessionResponse,
    StatusResponse,
    UpdateUserSettingsRequest,
    UserSettingsResponse,
)
from app.services.user_settings_service import (
    delete_current_user_account,
    export_current_user_data,
    get_current_user_settings,
    list_current_user_sessions,
    revoke_current_user_session,
    revoke_other_current_user_sessions,
    update_current_user_settings,
)


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/me", response_model=UserSettingsResponse)
def get_settings(request: Request, db: Session = Depends(get_db_session)) -> UserSettingsResponse:
    return get_current_user_settings(db, access_token=_bearer_token(request))


@router.patch("/me", response_model=UserSettingsResponse)
def update_settings(
    payload: UpdateUserSettingsRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> UserSettingsResponse:
    return update_current_user_settings(
        db,
        access_token=_bearer_token(request),
        preferences=payload.preferences,
    )


@router.get("/me/sessions", response_model=list[AuthSessionResponse])
def list_sessions(request: Request, db: Session = Depends(get_db_session)) -> list[AuthSessionResponse]:
    return list_current_user_sessions(db, access_token=_bearer_token(request))


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: str, request: Request, db: Session = Depends(get_db_session)) -> Response:
    revoke_current_user_session(db, access_token=_bearer_token(request), session_id=session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/sessions/revoke-others", response_model=StatusResponse)
def revoke_other_sessions(request: Request, db: Session = Depends(get_db_session)) -> StatusResponse:
    revoke_other_current_user_sessions(db, access_token=_bearer_token(request))
    return StatusResponse(status="ok")


@router.get("/me/export")
def export_data(request: Request, db: Session = Depends(get_db_session)) -> dict:
    return export_current_user_data(db, access_token=_bearer_token(request))


@router.delete("/me", response_model=StatusResponse)
def delete_account(
    payload: AccountDeleteRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> StatusResponse:
    delete_current_user_account(
        db,
        access_token=_bearer_token(request),
        confirmation=payload.confirmation,
    )
    return StatusResponse(status="deleted")

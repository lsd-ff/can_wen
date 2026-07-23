from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.diagnosis import DiagnosisConversationResponse
from app.schemas.projects import (
    ProjectCreateRequest,
    ProjectPinRequest,
    ProjectResponse,
    ProjectShareCreateRequest,
    ProjectShareResponse,
    ProjectUpdateRequest,
    PublicProjectShareResponse,
)
from app.services.auth_service import get_current_user
from app.services.project_service import (
    archive_current_user_project,
    create_current_user_project_share,
    create_current_user_project,
    delete_current_user_project,
    get_public_project_share,
    get_current_user_project,
    list_current_user_archived_projects,
    list_current_user_project_conversations,
    list_current_user_projects,
    restore_current_user_project,
    set_current_user_project_pinned,
    update_current_user_project,
)


router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    request: Request,
    db: Session = Depends(get_db_session),
) -> list[ProjectResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_current_user_projects(db, user=user)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> ProjectResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_current_user_project(
        db,
        user=user,
        name=payload.name,
        description=payload.description,
        icon_key=payload.icon_key,
        color=payload.color,
    )


@router.get("/archived", response_model=list[ProjectResponse])
def list_archived_projects(
    request: Request,
    db: Session = Depends(get_db_session),
) -> list[ProjectResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_current_user_archived_projects(db, user=user)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> ProjectResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return get_current_user_project(db, user=user, project_id=project_id)


@router.get("/{project_id}/conversations", response_model=list[DiagnosisConversationResponse])
def list_project_conversations(
    project_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> list[DiagnosisConversationResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_current_user_project_conversations(db, user=user, project_id=project_id)


@router.post("/{project_id}/shares", response_model=ProjectShareResponse)
def create_project_share(
    project_id: UUID,
    payload: ProjectShareCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ProjectShareResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_current_user_project_share(
        db,
        user=user,
        settings=settings,
        project_id=project_id,
        title=payload.title,
        variant=payload.variant,
        content_markdown=payload.content_markdown,
    )


@router.get("/shares/{share_token}", response_model=PublicProjectShareResponse)
def get_public_project_share_route(
    share_token: str,
    db: Session = Depends(get_db_session),
) -> PublicProjectShareResponse:
    return get_public_project_share(db, share_token=share_token)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: UUID,
    payload: ProjectUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> ProjectResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_current_user_project(
        db,
        user=user,
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        icon_key=payload.icon_key,
        color=payload.color,
    )


@router.patch("/{project_id}/pin", response_model=ProjectResponse)
def set_project_pin(
    project_id: UUID,
    payload: ProjectPinRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> ProjectResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return set_current_user_project_pinned(db, user=user, project_id=project_id, pinned=payload.pinned)


@router.patch("/{project_id}/archive", response_model=ProjectResponse)
def archive_project(
    project_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> ProjectResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return archive_current_user_project(db, user=user, project_id=project_id)


@router.patch("/{project_id}/restore", response_model=ProjectResponse)
def restore_project(
    project_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> ProjectResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return restore_current_user_project(db, user=user, project_id=project_id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> None:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_current_user_project(db, user=user, project_id=project_id)


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return token.strip()

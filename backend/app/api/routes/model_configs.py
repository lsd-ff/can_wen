from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.model_configs import (
    ModelConfigCreateRequest,
    ModelConfigResponse,
    ModelConfigTestResponse,
    ModelConfigUpdateRequest,
)
from app.services.auth_service import get_current_user
from app.services.model_config_service import (
    create_current_user_model_config,
    delete_current_user_model_config,
    list_current_user_model_configs,
    set_current_user_default_model_config,
    test_current_user_model_config,
    update_current_user_model_config,
)


router = APIRouter(prefix="/model-configs", tags=["model-configs"])


@router.get("", response_model=list[ModelConfigResponse])
def list_model_configs(
    request: Request,
    db: Session = Depends(get_db_session),
) -> list[ModelConfigResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_current_user_model_configs(db, user=user)


@router.post("", response_model=ModelConfigResponse, status_code=status.HTTP_201_CREATED)
def create_model_config(
    payload: ModelConfigCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ModelConfigResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_current_user_model_config(db, user=user, settings=settings, payload=payload)


@router.patch("/{model_config_id}", response_model=ModelConfigResponse)
def update_model_config(
    model_config_id: UUID,
    payload: ModelConfigUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ModelConfigResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_current_user_model_config(
        db,
        user=user,
        settings=settings,
        model_config_id=model_config_id,
        payload=payload,
    )


@router.delete("/{model_config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_config(
    model_config_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_current_user_model_config(db, user=user, model_config_id=model_config_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{model_config_id}/set-default", response_model=ModelConfigResponse)
def set_default_model_config(
    model_config_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> ModelConfigResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return set_current_user_default_model_config(db, user=user, model_config_id=model_config_id)


@router.post("/{model_config_id}/test", response_model=ModelConfigTestResponse)
def test_model_config(
    model_config_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> ModelConfigTestResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return test_current_user_model_config(db, user=user, settings=settings, model_config_id=model_config_id)


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in")
    return token.strip()

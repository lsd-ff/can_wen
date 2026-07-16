from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.schemas.admin import (
    AdminDashboardResponse,
    AdminExpertReviewCreateRequest,
    AdminExpertReviewResponse,
    AdminExpertReviewUpdateRequest,
    AdminReviewQueueItemResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdateRequest,
)
from app.services.admin_service import (
    create_admin_expert_review,
    get_admin_dashboard,
    list_admin_expert_reviews,
    list_admin_review_queue,
    list_admin_users,
    update_admin_expert_review,
    update_admin_user,
)
from app.services.auth_service import get_current_user


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=AdminDashboardResponse)
def get_dashboard(request: Request, db: Session = Depends(get_db_session)) -> AdminDashboardResponse:
    return get_admin_dashboard(db, user=get_current_user(db, access_token=_bearer_token(request)))


@router.get("/users", response_model=AdminUserListResponse)
def get_users(
    request: Request,
    query: str | None = Query(default=None, max_length=100),
    role: str | None = Query(default=None, pattern="^(farmer|agritech|expert|admin)$"),
    user_status: str | None = Query(default=None, alias="status", pattern="^(active|disabled|deleted)$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
) -> AdminUserListResponse:
    return list_admin_users(
        db,
        user=get_current_user(db, access_token=_bearer_token(request)),
        query=query,
        role=role,
        user_status=user_status,
        limit=limit,
        offset=offset,
    )


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def patch_user(
    user_id: UUID,
    payload: AdminUserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AdminUserResponse:
    return update_admin_user(
        db,
        user=get_current_user(db, access_token=_bearer_token(request)),
        target_user_id=user_id,
        payload=payload,
    )


@router.get("/review-queue", response_model=list[AdminReviewQueueItemResponse])
def get_review_queue(
    request: Request,
    case_status: str = Query(default="open", alias="status", pattern="^(open|closed|all)$"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> list[AdminReviewQueueItemResponse]:
    return list_admin_review_queue(
        db,
        user=get_current_user(db, access_token=_bearer_token(request)),
        case_status=case_status,
        limit=limit,
    )


@router.get("/reviews", response_model=list[AdminExpertReviewResponse])
def get_expert_reviews(
    request: Request,
    husbandry_case_id: UUID | None = None,
    conversation_id: UUID | None = None,
    db: Session = Depends(get_db_session),
) -> list[AdminExpertReviewResponse]:
    return list_admin_expert_reviews(
        db,
        user=get_current_user(db, access_token=_bearer_token(request)),
        husbandry_case_id=husbandry_case_id,
        conversation_id=conversation_id,
    )


@router.post("/reviews", response_model=AdminExpertReviewResponse, status_code=201)
def post_expert_review(
    payload: AdminExpertReviewCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AdminExpertReviewResponse:
    return create_admin_expert_review(
        db,
        user=get_current_user(db, access_token=_bearer_token(request)),
        payload=payload,
    )


@router.patch("/reviews/{review_id}", response_model=AdminExpertReviewResponse)
def patch_expert_review(
    review_id: UUID,
    payload: AdminExpertReviewUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> AdminExpertReviewResponse:
    return update_admin_expert_review(
        db,
        user=get_current_user(db, access_token=_bearer_token(request)),
        review_id=review_id,
        payload=payload,
    )


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="请先登录")
    return token.strip()

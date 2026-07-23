from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.security import now_utc
from app.models import (
    AuthSession,
    CommunityComment,
    CommunityPost,
    CommunityReport,
    ExpertReview,
    Farm,
    HusbandryCase,
    SilkwormBatch,
    User,
    UserIdentity,
)
from app.schemas.admin import (
    AdminDashboardResponse,
    AdminExpertReviewCreateRequest,
    AdminExpertReviewResponse,
    AdminExpertReviewUpdateRequest,
    AdminMetricResponse,
    AdminReportResponse,
    AdminReviewQueueItemResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdateRequest,
)
from app.models.p0 import Conversation


def get_admin_dashboard(db: Session, *, user: User) -> AdminDashboardResponse:
    _ensure_admin(user)
    now = now_utc()
    week_ago = now - timedelta(days=7)
    metrics = [
        AdminMetricResponse(
            key="active_users",
            label="活跃用户",
            value=_count(db, select(User).where(User.status == "active")),
            trend=f"近 7 天新增 {_count(db, select(User).where(User.registered_at >= week_ago))}",
            tone="blue",
        ),
        AdminMetricResponse(
            key="open_cases",
            label="待跟进病例",
            value=_count(db, select(HusbandryCase).where(HusbandryCase.status != "closed")),
            trend=f"高风险 {_count(db, select(HusbandryCase).where(HusbandryCase.status != 'closed', HusbandryCase.severity.in_(['high', 'critical'])))}",
            tone="orange",
        ),
        AdminMetricResponse(
            key="pending_reports",
            label="待审核举报",
            value=_count(db, select(CommunityReport).where(CommunityReport.status == "pending")),
            trend="优先处理影响社区安全的内容",
            tone="red",
        ),
        AdminMetricResponse(
            key="published_posts",
            label="已发布内容",
            value=_count(db, select(CommunityPost).where(CommunityPost.status == "published")),
            trend=f"隐藏内容 {_count(db, select(CommunityPost).where(CommunityPost.status == 'hidden'))}",
            tone="green",
        ),
    ]
    role_distribution = [
        AdminMetricResponse(key=role, label=_role_label(role), value=_count(db, select(User).where(User.role == role, User.status == "active")))
        for role in ("farmer", "agritech", "expert", "admin")
    ]
    return AdminDashboardResponse(
        metrics=metrics,
        role_distribution=role_distribution,
        review_queue=_list_review_queue_items(db, limit=6),
        pending_reports=_list_report_items(db, report_status="pending", limit=6),
    )


def list_admin_users(
    db: Session,
    *,
    user: User,
    query: str | None,
    role: str | None,
    user_status: str | None,
    limit: int,
    offset: int,
) -> AdminUserListResponse:
    _ensure_admin(user)
    statement = select(User).order_by(User.registered_at.desc())
    if query and query.strip():
        keyword = f"%{query.strip()}%"
        statement = statement.where(or_(User.display_name.ilike(keyword), User.username.ilike(keyword)))
    if role:
        statement = statement.where(User.role == role)
    if user_status:
        statement = statement.where(User.status == user_status)
    total = _count(db, statement)
    users = db.scalars(statement.offset(offset).limit(limit)).all()
    return AdminUserListResponse(items=[_user_response(db, item) for item in users], total=total)


def update_admin_user(
    db: Session,
    *,
    user: User,
    target_user_id: UUID,
    payload: AdminUserUpdateRequest,
) -> AdminUserResponse:
    _ensure_admin(user)
    target = db.get(User, target_user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if target.id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能在管理台修改自己的角色或状态")
    if payload.role is None and payload.status is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择要更新的用户属性")

    changing_from_admin = target.role == "admin" and payload.role is not None and payload.role != "admin"
    disabling_admin = target.role == "admin" and payload.status is not None and payload.status != "active"
    if changing_from_admin or disabling_admin:
        other_active_admins = _count(
            db,
            select(User).where(User.role == "admin", User.status == "active", User.id != target.id),
        )
        if other_active_admins == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="系统至少需要保留一名启用的管理员")

    current_time = now_utc()
    if payload.role is not None:
        target.role = payload.role
    if payload.status is not None:
        target.status = payload.status
        target.deleted_at = current_time if payload.status == "deleted" else None
        if payload.status != "active":
            db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == target.id, AuthSession.status == "active")
                .values(status="revoked", revoked_at=current_time)
            )
    target.updated_at = current_time
    db.add(target)
    db.commit()
    db.refresh(target)
    return _user_response(db, target)


def list_admin_review_queue(
    db: Session,
    *,
    user: User,
    case_status: str,
    limit: int,
) -> list[AdminReviewQueueItemResponse]:
    _ensure_admin(user)
    return _list_review_queue_items(db, case_status=case_status, limit=limit)


def list_admin_expert_reviews(
    db: Session,
    *,
    user: User,
    husbandry_case_id: UUID | None,
    conversation_id: UUID | None,
) -> list[AdminExpertReviewResponse]:
    _ensure_admin(user)
    if (husbandry_case_id is None) == (conversation_id is None):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择一个病例或问诊记录")
    statement = select(ExpertReview)
    if husbandry_case_id is not None:
        statement = statement.where(ExpertReview.husbandry_case_id == husbandry_case_id)
    else:
        statement = statement.where(ExpertReview.conversation_id == conversation_id)
    reviews = db.scalars(statement.order_by(ExpertReview.version.desc())).all()
    return [_expert_review_response(item) for item in reviews]


def create_admin_expert_review(
    db: Session,
    *,
    user: User,
    payload: AdminExpertReviewCreateRequest,
) -> AdminExpertReviewResponse:
    _ensure_admin(user)
    case_id, conversation_id = _review_subject_ids(payload.husbandry_case_id, payload.conversation_id)
    if case_id is not None and db.get(HusbandryCase, case_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="病例不存在")
    if conversation_id is not None and db.get(Conversation, conversation_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问诊记录不存在")
    subject_filter = ExpertReview.husbandry_case_id == case_id if case_id else ExpertReview.conversation_id == conversation_id
    latest_version = db.scalar(select(func.max(ExpertReview.version)).where(subject_filter)) or 0
    current_time = now_utc()
    review = ExpertReview(
        husbandry_case_id=case_id,
        conversation_id=conversation_id,
        reviewer_id=user.id,
        reviewer_name_snapshot=_display_name(user),
        risk_level=payload.risk_level,
        conclusion=payload.conclusion,
        recommendation=payload.recommendation,
        evidence=payload.evidence,
        status=payload.status,
        version=int(latest_version) + 1,
        published_at=current_time if payload.status == "published" else None,
        updated_at=current_time,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return _expert_review_response(review)


def update_admin_expert_review(
    db: Session,
    *,
    user: User,
    review_id: UUID,
    payload: AdminExpertReviewUpdateRequest,
) -> AdminExpertReviewResponse:
    _ensure_admin(user)
    review = db.get(ExpertReview, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="复核记录不存在")
    changes = payload.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择要更新的复核内容")
    for field, value in changes.items():
        setattr(review, field, value)
    review.updated_at = now_utc()
    if review.status == "published":
        review.published_at = review.published_at or review.updated_at
    elif "status" in changes:
        review.published_at = None
    db.add(review)
    db.commit()
    db.refresh(review)
    return _expert_review_response(review)


def _ensure_admin(user: User) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅管理员可访问管理端")


def _count(db: Session, statement) -> int:
    return int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)


def _user_response(db: Session, user: User) -> AdminUserResponse:
    identities = db.scalars(
        select(UserIdentity).where(UserIdentity.user_id == user.id, UserIdentity.unbound_at.is_(None))
    ).all()
    email = next((identity.email for identity in identities if identity.provider == "email" and identity.email), "")
    phone_number = next((identity.phone_number for identity in identities if identity.provider == "phone" and identity.phone_number), "")
    batch_count = int(
        db.scalar(
            select(func.count()).select_from(SilkwormBatch).join(Farm, Farm.id == SilkwormBatch.farm_id).where(Farm.owner_id == user.id)
        )
        or 0
    )
    return AdminUserResponse(
        id=str(user.id),
        display_name=_display_name(user),
        username=user.username,
        avatar_url=user.avatar_url,
        role=user.role,
        status=user.status,
        email=str(email),
        phone_number=str(phone_number),
        registered_at=user.registered_at,
        last_seen_at=user.last_seen_at,
        farm_count=int(db.scalar(select(func.count()).select_from(Farm).where(Farm.owner_id == user.id)) or 0),
        batch_count=batch_count,
        case_count=int(db.scalar(select(func.count()).select_from(HusbandryCase).where(HusbandryCase.owner_id == user.id)) or 0),
        post_count=int(db.scalar(select(func.count()).select_from(CommunityPost).where(CommunityPost.author_id == user.id)) or 0),
    )


def _list_report_items(db: Session, *, report_status: str, limit: int) -> list[AdminReportResponse]:
    reports = db.scalars(
        select(CommunityReport)
        .where(CommunityReport.status == report_status)
        .order_by(CommunityReport.created_at.desc())
        .limit(limit)
    ).all()
    return [_report_response(db, report) for report in reports]


def _report_response(db: Session, report: CommunityReport) -> AdminReportResponse:
    reporter = db.get(User, report.reporter_id)
    post = db.get(CommunityPost, report.post_id) if report.post_id else None
    comment = db.get(CommunityComment, report.comment_id) if report.comment_id else None
    if report.target_type == "comment":
        target_title = f"{post.title if post else '已删除内容'}下的评论"
        target_excerpt = comment.content if comment else None
    else:
        target_title = post.title if post else "已删除内容"
        target_excerpt = post.excerpt if post else None
    return AdminReportResponse(
        id=str(report.id),
        target_type=report.target_type,
        reason=report.reason,
        detail=report.detail,
        status=report.status,
        reporter_name=_display_name(reporter) if reporter else "已删除用户",
        reporter_id=str(report.reporter_id),
        target_title=target_title,
        target_excerpt=target_excerpt,
        post_id=str(report.post_id) if report.post_id else None,
        comment_id=str(report.comment_id) if report.comment_id else None,
        created_at=report.created_at,
        reviewed_at=report.reviewed_at,
    )


def _list_review_queue_items(db: Session, *, case_status: str = "open", limit: int) -> list[AdminReviewQueueItemResponse]:
    statement = (
        select(HusbandryCase, Farm, SilkwormBatch, User)
        .join(Farm, Farm.id == HusbandryCase.farm_id)
        .join(User, User.id == HusbandryCase.owner_id)
        .outerjoin(SilkwormBatch, SilkwormBatch.id == HusbandryCase.batch_id)
        .order_by(HusbandryCase.severity.desc(), HusbandryCase.updated_at.desc())
        .limit(limit)
    )
    if case_status == "open":
        statement = statement.where(HusbandryCase.status != "closed")
    elif case_status == "closed":
        statement = statement.where(HusbandryCase.status == "closed")
    rows = db.execute(statement).all()
    response: list[AdminReviewQueueItemResponse] = []
    for case, farm, batch, owner in rows:
        reviews = db.scalars(
            select(ExpertReview).where(ExpertReview.husbandry_case_id == case.id).order_by(ExpertReview.version.desc()).limit(1)
        ).all()
        review_count = int(db.scalar(select(func.count()).select_from(ExpertReview).where(ExpertReview.husbandry_case_id == case.id)) or 0)
        response.append(
            AdminReviewQueueItemResponse(
                id=str(case.id),
                title=case.title,
                symptom_summary=case.symptom_summary,
                suspected_disease=case.suspected_disease,
                severity=case.severity,
                case_status=case.status,
                owner_name=_display_name(owner),
                owner_id=str(owner.id),
                farm_name=farm.name,
                batch_code=batch.batch_code if batch else None,
                occurred_on=case.occurred_on,
                created_at=case.created_at,
                review_count=review_count,
                latest_review_status=reviews[0].status if reviews else None,
            )
        )
    return response


def _expert_review_response(review: ExpertReview) -> AdminExpertReviewResponse:
    return AdminExpertReviewResponse(
        id=str(review.id),
        husbandry_case_id=str(review.husbandry_case_id) if review.husbandry_case_id else None,
        conversation_id=str(review.conversation_id) if review.conversation_id else None,
        reviewer_id=str(review.reviewer_id) if review.reviewer_id else None,
        reviewer_name=review.reviewer_name_snapshot,
        risk_level=review.risk_level,
        conclusion=review.conclusion,
        recommendation=review.recommendation,
        evidence=review.evidence or [],
        status=review.status,
        version=review.version,
        created_at=review.created_at,
        updated_at=review.updated_at,
        published_at=review.published_at,
    )


def _review_subject_ids(husbandry_case_id: str | None, conversation_id: str | None) -> tuple[UUID | None, UUID | None]:
    if bool(husbandry_case_id) == bool(conversation_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="一次复核只能关联一个病例或问诊记录")
    try:
        return (UUID(husbandry_case_id), None) if husbandry_case_id else (None, UUID(conversation_id or ""))
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="复核目标格式无效") from error


def _display_name(user: User | None) -> str:
    if user is None:
        return "已删除用户"
    return user.display_name.strip() or user.username.strip() or "未命名用户"


def _role_label(role: str) -> str:
    return {"farmer": "养殖户", "agritech": "农技人员", "expert": "专家", "admin": "管理员"}.get(role, role)

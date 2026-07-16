from __future__ import annotations

import secrets
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, nullslast, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import now_utc
from app.models import Conversation, Project, ProjectShare, UploadedFile, User
from app.schemas.diagnosis import DiagnosisConversationResponse
from app.schemas.projects import ProjectResponse, ProjectShareResponse, PublicProjectShareResponse


def list_current_user_projects(db: Session, *, user: User) -> list[ProjectResponse]:
    projects = db.scalars(
        select(Project)
        .where(
            Project.owner_id == user.id,
            Project.status == "active",
        )
        .order_by(nullslast(desc(Project.pinned_at)), desc(Project.updated_at), desc(Project.created_at))
    ).all()

    return [_project_response(project) for project in projects]


def list_current_user_archived_projects(db: Session, *, user: User) -> list[ProjectResponse]:
    projects = db.scalars(
        select(Project)
        .where(
            Project.owner_id == user.id,
            Project.status == "archived",
        )
        .order_by(desc(Project.updated_at), desc(Project.created_at))
    ).all()

    return [_project_response(project) for project in projects]


def get_current_user_project(db: Session, *, user: User, project_id: UUID) -> ProjectResponse:
    return _project_response(_get_current_user_project(db, user=user, project_id=project_id))


def list_current_user_project_conversations(
    db: Session,
    *,
    user: User,
    project_id: UUID,
) -> list[DiagnosisConversationResponse]:
    project = _get_current_user_project(db, user=user, project_id=project_id)
    conversations = db.scalars(
        select(Conversation)
        .where(
            Conversation.user_id == user.id,
            Conversation.project_id == project.id,
            Conversation.status == "active",
        )
        .order_by(
            nullslast(desc(Conversation.pinned_at)),
            desc(Conversation.last_message_at),
            desc(Conversation.updated_at),
            desc(Conversation.created_at),
        )
    ).all()

    return [_conversation_response(conversation) for conversation in conversations]


def create_current_user_project(
    db: Session,
    *,
    user: User,
    name: str,
    description: str | None,
    icon_key: str,
    color: str,
) -> ProjectResponse:
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="项目名称不能为空")

    normalized_description = description.strip() if description else None
    project = Project(
        owner_id=user.id,
        name=normalized_name,
        description=normalized_description or None,
        icon_key=icon_key.strip() or "folder",
        color=color.strip() or "#11110f",
        status="active",
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return _project_response(project)


def update_current_user_project(
    db: Session,
    *,
    user: User,
    project_id: UUID,
    name: str | None = None,
    description: str | None = None,
    icon_key: str | None = None,
    color: str | None = None,
) -> ProjectResponse:
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.id,
            Project.status != "deleted",
        )
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="项目名称不能为空")
        project.name = normalized_name

    if description is not None:
        normalized_description = description.strip()
        project.description = normalized_description or None

    if icon_key is not None:
        project.icon_key = icon_key.strip() or "folder"

    if color is not None:
        project.color = color.strip() or "#11110f"

    db.commit()
    db.refresh(project)

    return _project_response(project)


def set_current_user_project_pinned(
    db: Session,
    *,
    user: User,
    project_id: UUID,
    pinned: bool,
) -> ProjectResponse:
    project = _get_current_user_project(db, user=user, project_id=project_id)
    current_time = now_utc()
    project.pinned_at = current_time if pinned else None
    project.updated_at = current_time
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_response(project)


def archive_current_user_project(db: Session, *, user: User, project_id: UUID) -> ProjectResponse:
    project = _get_current_user_project(db, user=user, project_id=project_id)
    current_time = now_utc()
    project.status = "archived"
    project.pinned_at = None
    project.updated_at = current_time

    conversations = db.scalars(
        select(Conversation).where(
            Conversation.user_id == user.id,
            Conversation.project_id == project.id,
            Conversation.status != "deleted",
        )
    ).all()
    for conversation in conversations:
        conversation.status = "archived"
        conversation.pinned_at = None
        conversation.updated_at = current_time
        db.add(conversation)

    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_response(project)


def restore_current_user_project(db: Session, *, user: User, project_id: UUID) -> ProjectResponse:
    project = _get_current_user_project(db, user=user, project_id=project_id)
    current_time = now_utc()
    project.status = "active"
    project.updated_at = current_time

    conversations = db.scalars(
        select(Conversation).where(
            Conversation.user_id == user.id,
            Conversation.project_id == project.id,
            Conversation.status == "archived",
        )
    ).all()
    for conversation in conversations:
        conversation.status = "active"
        conversation.updated_at = current_time
        db.add(conversation)

    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_response(project)


def create_current_user_project_share(
    db: Session,
    *,
    user: User,
    settings: Settings,
    project_id: UUID,
    title: str,
    variant: str,
    content_markdown: str,
) -> ProjectShareResponse:
    project = _get_current_user_project(db, user=user, project_id=project_id)
    normalized_title = " ".join(title.split()).strip() or project.name or "CanW 项目分享"
    normalized_content = content_markdown.strip()
    if not normalized_content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分享内容不能为空")

    share = ProjectShare(
        project_id=project.id,
        owner_id=user.id,
        share_token=_new_project_share_token(db),
        title=normalized_title[:100],
        variant=variant,
        content_markdown=normalized_content,
        status="active",
        metadata_={"source": "project_share"},
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return _project_share_response(share, settings=settings)


def get_public_project_share(
    db: Session,
    *,
    share_token: str,
) -> PublicProjectShareResponse:
    normalized_token = share_token.strip()
    if not normalized_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")

    share = db.scalar(
        select(ProjectShare).where(
            ProjectShare.share_token == normalized_token,
            ProjectShare.status == "active",
        )
    )
    if share is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在或已失效")
    if share.expires_at is not None and share.expires_at <= now_utc():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享已过期")

    share.view_count = (share.view_count or 0) + 1
    db.add(share)
    db.commit()
    db.refresh(share)
    return PublicProjectShareResponse(
        title=share.title,
        variant=share.variant,
        content_markdown=share.content_markdown,
        created_at=share.created_at,
        updated_at=share.updated_at,
    )


def delete_current_user_project(db: Session, *, user: User, project_id: UUID) -> None:
    project = _get_current_user_project(db, user=user, project_id=project_id)
    current_time = now_utc()
    project.status = "deleted"
    project.deleted_at = current_time
    project.updated_at = current_time

    conversations = db.scalars(
        select(Conversation).where(
            Conversation.user_id == user.id,
            Conversation.project_id == project.id,
            Conversation.status != "deleted",
        )
    ).all()
    for conversation in conversations:
        conversation.project_id = None
        conversation.updated_at = current_time
        db.add(conversation)

    files = db.scalars(
        select(UploadedFile).where(
            UploadedFile.user_id == user.id,
            UploadedFile.project_id == project.id,
            UploadedFile.deleted_at.is_(None),
        )
    ).all()
    for file in files:
        file.project_id = None
        db.add(file)

    db.add(project)
    db.commit()


def _get_current_user_project(db: Session, *, user: User, project_id: UUID) -> Project:
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == user.id,
            Project.status != "deleted",
        )
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


def _project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        description=project.description,
        icon_key=project.icon_key,
        color=project.color,
        status=project.status,
        created_at=project.created_at,
        updated_at=project.updated_at,
        pinned_at=project.pinned_at,
    )


def _conversation_response(conversation: Conversation) -> DiagnosisConversationResponse:
    return DiagnosisConversationResponse(
        id=str(conversation.id),
        project_id=str(conversation.project_id) if conversation.project_id else None,
        title=conversation.title,
        summary=conversation.summary,
        conversation_type=conversation.conversation_type,
        status=conversation.status,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        pinned_at=conversation.pinned_at,
    )


def _new_project_share_token(db: Session) -> str:
    for _ in range(8):
        token = secrets.token_urlsafe(24)
        exists = db.scalar(select(ProjectShare.id).where(ProjectShare.share_token == token))
        if not exists:
            return token
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="分享链接生成失败")


def _project_share_response(share: ProjectShare, *, settings: Settings) -> ProjectShareResponse:
    return ProjectShareResponse(
        id=str(share.id),
        project_id=str(share.project_id),
        share_token=share.share_token,
        share_url=f"{settings.public_frontend_base_url.rstrip('/')}/project-share/{share.share_token}",
        title=share.title,
        variant=share.variant,
        created_at=share.created_at,
        expires_at=share.expires_at,
    )

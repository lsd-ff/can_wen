from __future__ import annotations

import base64
import html
import io
import json
import mimetypes
import re
import hashlib
import secrets
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
from urllib.error import HTTPError
from xml.etree import ElementTree

from fastapi import HTTPException, status
from sqlalchemy import desc, nullslast, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import now_utc
from app.models import (
    Conversation,
    ConversationShare,
    DiagnosisMultimodalAnalysis,
    Message,
    MessageFile,
    Project,
    UploadedFile,
    User,
    UserSettings,
)
from app.schemas.diagnosis import (
    DiagnosisContextMessage,
    DiagnosisConversationDetailResponse,
    DiagnosisExpertReviewResponse,
    DiagnosisConversationResponse,
    DiagnosisConversationShareResponse,
    DiagnosisFileResponse,
    DiagnosisMessageFeedback,
    DiagnosisMessageMutationResponse,
    DiagnosisConversationTurnResponse,
    DiagnosisMessageResponse,
    PublicDiagnosisConversationShareResponse,
)
from app.services.diagnosis_agent_service import (
    agent_run_from_message_metadata,
    execute_diagnosis_agent,
    link_agent_run_to_assistant_message,
)
from app.services.llm_client import (
    LLMConfigurationError,
    LLMProviderError,
    OpenAICompatibleModelConfig,
    request_openai_compatible_reply,
    request_openai_compatible_transcription,
)
from app.services.model_config_service import resolve_current_user_llm_config
from app.services.storage_service import delete_object_file, upload_object_file


MULTIMODAL_ANALYSIS_PROMPT = """你是 CanW 家蚕疾病多模态材料解析器。
你只负责观察、转写、提取关键词和整理检索线索，不要给最终诊断结论，不要给处置方案。
请尽量输出严格 JSON，字段包括：
observations, symptoms, environment_clues, possible_entities, retrieval_queries, missing_info, risk_notes。
如果材料不足，请在 missing_info 中说明还需要补充什么。
"""

DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".rtf",
    ".log",
}
DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/json",
    "application/rtf",
    "application/xml",
    "text/csv",
    "text/html",
    "text/markdown",
    "text/plain",
    "text/rtf",
    "text/xml",
}
MAX_EXTRACTED_TEXT_CHARS = 12000
MAX_INLINE_IMAGE_BYTES = 6 * 1024 * 1024


@dataclass(frozen=True)
class DiagnosisAttachmentUpload:
    file_name: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class DiagnosisVoiceTranscription:
    text: str
    model: str
    provider: str


def upload_current_user_diagnosis_attachments(
    db: Session,
    *,
    user: User,
    attachments: list[DiagnosisAttachmentUpload],
) -> list[DiagnosisFileResponse]:
    _cleanup_expired_diagnosis_drafts(db, user=user)
    uploaded_files: list[UploadedFile] = []
    for index, attachment in enumerate(attachments, start=1):
        if not attachment.content:
            continue

        file_id = uuid.uuid4()
        safe_file_name = _safe_file_name(attachment.file_name or f"attachment-{index}")
        normalized_content_type = _content_type_for_attachment(attachment.file_name, attachment.content_type)
        file_type = _file_type_from_attachment(attachment.file_name, normalized_content_type)
        _ensure_supported_attachment(
            file_name=attachment.file_name or safe_file_name,
            content_type=normalized_content_type,
            file_type=file_type,
        )
        analysis_context = _extract_attachment_analysis_context(
            file_name=attachment.file_name or safe_file_name,
            content_type=normalized_content_type,
            file_type=file_type,
            content=attachment.content,
        )
        object_key = f"diagnosis/{user.id}/drafts/{file_id}/original/{safe_file_name}"
        storage_url = upload_object_file(
            object_key=object_key,
            content=attachment.content,
            content_type=normalized_content_type,
            failure_detail="问诊附件上传失败，请稍后再试",
        )
        uploaded_file = UploadedFile(
            id=file_id,
            user_id=user.id,
            file_name=attachment.file_name or safe_file_name,
            file_type=file_type,
            mime_type=normalized_content_type,
            storage_key=object_key,
            storage_url=storage_url,
            file_size=len(attachment.content),
            checksum=hashlib.sha256(attachment.content).hexdigest(),
            metadata_={
                "source": "diagnosis_draft",
                "upload_state": "ready",
                "analysis_context": analysis_context,
            },
        )
        db.add(uploaded_file)
        uploaded_files.append(uploaded_file)

    db.commit()
    return [_file_response(file) for file in uploaded_files]


def _cleanup_expired_diagnosis_drafts(db: Session, *, user: User) -> None:
    preferences = _preferences_for_user(db, user)
    retention_hours = preferences.get("draft_attachment_retention_hours", 24)
    if retention_hours not in {24, 72, 168}:
        retention_hours = 24
    cutoff = now_utc() - timedelta(hours=retention_hours)
    candidates = db.scalars(
        select(UploadedFile).where(
            UploadedFile.user_id == user.id,
            UploadedFile.deleted_at.is_(None),
            UploadedFile.created_at < cutoff,
        )
    ).all()
    expired_drafts = [
        file for file in candidates
        if (file.metadata_ or {}).get("source") == "diagnosis_draft"
    ]
    if not expired_drafts:
        return

    for draft in expired_drafts:
        try:
            delete_object_file(object_key=draft.storage_key)
        except HTTPException:
            continue
        draft.deleted_at = now_utc()
        db.add(draft)
    db.commit()


def delete_current_user_diagnosis_draft_attachment(
    db: Session,
    *,
    user: User,
    file_id: UUID,
) -> None:
    uploaded_file = db.scalar(
        select(UploadedFile).where(
            UploadedFile.id == file_id,
            UploadedFile.user_id == user.id,
            UploadedFile.deleted_at.is_(None),
        )
    )
    if uploaded_file is None or (uploaded_file.metadata_ or {}).get("source") != "diagnosis_draft":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待发送附件不存在或已被使用")

    delete_object_file(
        object_key=uploaded_file.storage_key,
        failure_detail="问诊附件删除失败，请稍后再试",
    )
    uploaded_file.deleted_at = now_utc()
    db.add(uploaded_file)
    db.commit()


def list_current_user_diagnosis_conversations(db: Session, *, user: User) -> list[DiagnosisConversationResponse]:
    conversations = db.scalars(
        select(Conversation)
        .where(
            Conversation.user_id == user.id,
            Conversation.conversation_type == "diagnosis",
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


def search_current_user_diagnosis_conversations(
    db: Session,
    *,
    user: User,
    query: str,
    limit: int = 20,
) -> list[DiagnosisConversationResponse]:
    normalized_query = " ".join(query.split())
    if not normalized_query:
        return []

    pattern = f"%{normalized_query}%"
    message_matches = (
        select(Message.id)
        .where(
            Message.conversation_id == Conversation.id,
            Message.deleted_at.is_(None),
            Message.content.ilike(pattern),
        )
        .exists()
    )
    conversations = db.scalars(
        select(Conversation)
        .where(
            Conversation.user_id == user.id,
            Conversation.conversation_type == "diagnosis",
            Conversation.status.in_(("active", "archived")),
            or_(
                Conversation.title.ilike(pattern),
                Conversation.summary.ilike(pattern),
                message_matches,
            ),
        )
        .order_by(nullslast(desc(Conversation.pinned_at)), desc(Conversation.last_message_at), desc(Conversation.updated_at))
        .limit(limit)
    ).all()
    return [_conversation_response(conversation) for conversation in conversations]


def list_current_user_archived_diagnosis_conversations(db: Session, *, user: User) -> list[DiagnosisConversationResponse]:
    conversations = db.scalars(
        select(Conversation)
        .where(
            Conversation.user_id == user.id,
            Conversation.conversation_type == "diagnosis",
            Conversation.status == "archived",
        )
        .order_by(desc(Conversation.updated_at), desc(Conversation.created_at))
    ).all()

    return [_conversation_response(conversation) for conversation in conversations]


def get_current_user_diagnosis_conversation(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
) -> DiagnosisConversationDetailResponse:
    conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)
    messages = db.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.deleted_at.is_(None),
        )
        .order_by(Message.created_at.asc())
    ).all()

    return DiagnosisConversationDetailResponse(
        **_conversation_response(conversation).model_dump(),
        messages=[_message_response(message) for message in messages],
        expert_reviews=_published_expert_reviews(db, conversation_id=conversation.id),
    )


def update_current_user_diagnosis_conversation(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
    title: str,
) -> DiagnosisConversationResponse:
    normalized_title = " ".join(title.split())
    if not normalized_title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Conversation title cannot be empty")
    if len(normalized_title) > 80:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Conversation title is too long")

    conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)
    conversation.title = normalized_title
    conversation.updated_at = now_utc()
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _conversation_response(conversation)


def set_current_user_diagnosis_conversation_pinned(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
    pinned: bool,
) -> DiagnosisConversationResponse:
    conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)
    current_time = now_utc()
    conversation.pinned_at = current_time if pinned else None
    conversation.updated_at = current_time
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _conversation_response(conversation)


def archive_current_user_diagnosis_conversation(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
) -> DiagnosisConversationResponse:
    conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)
    current_time = now_utc()
    conversation.status = "archived"
    conversation.pinned_at = None
    conversation.updated_at = current_time
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _conversation_response(conversation)


def restore_current_user_diagnosis_conversation(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
) -> DiagnosisConversationResponse:
    conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)
    current_time = now_utc()
    conversation.status = "active"
    conversation.updated_at = current_time
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _conversation_response(conversation)


def create_current_user_diagnosis_conversation_share(
    db: Session,
    *,
    user: User,
    settings: Settings,
    conversation_id: UUID,
    title: str,
    variant: str,
    content_markdown: str,
) -> DiagnosisConversationShareResponse:
    conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)
    normalized_title = " ".join(title.split()).strip() or conversation.title or "CanW 问诊分享"
    normalized_content = content_markdown.strip()
    if not normalized_content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分享内容不能为空")

    share = ConversationShare(
        conversation_id=conversation.id,
        owner_id=user.id,
        share_token=_new_share_token(db),
        title=normalized_title[:100],
        variant=variant,
        content_markdown=normalized_content,
        status="active",
        metadata_={"source": "diagnosis_conversation_share"},
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return _conversation_share_response(share, settings=settings)


def get_public_diagnosis_conversation_share(
    db: Session,
    *,
    share_token: str,
) -> PublicDiagnosisConversationShareResponse:
    normalized_token = share_token.strip()
    if not normalized_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分享不存在")

    share = db.scalar(
        select(ConversationShare).where(
            ConversationShare.share_token == normalized_token,
            ConversationShare.status == "active",
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
    return PublicDiagnosisConversationShareResponse(
        title=share.title,
        variant=share.variant,
        content_markdown=share.content_markdown,
        created_at=share.created_at,
        updated_at=share.updated_at,
    )


def delete_current_user_diagnosis_conversation(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
) -> None:
    conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)
    current_time = now_utc()
    conversation.status = "deleted"
    conversation.deleted_at = current_time
    conversation.updated_at = current_time
    db.add(conversation)
    db.commit()


def update_current_user_diagnosis_message(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
    message_id: UUID,
    content: str,
) -> DiagnosisMessageMutationResponse:
    normalized_content = content.strip()
    if not normalized_content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="消息内容不能为空")

    conversation, message = _get_current_user_message(
        db,
        user=user,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    if message.sender_type != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能编辑用户消息")
    if message.message_type != "text":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能编辑文本消息")

    current_time = now_utc()
    message.content = normalized_content
    message.updated_at = current_time
    conversation.updated_at = current_time
    db.add_all([conversation, message])
    db.commit()
    db.refresh(conversation)
    db.refresh(message)
    return _message_mutation_response(conversation, message)


def delete_current_user_diagnosis_message(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
    message_id: UUID,
) -> DiagnosisConversationDetailResponse:
    conversation, message = _get_current_user_message(
        db,
        user=user,
        conversation_id=conversation_id,
        message_id=message_id,
    )

    current_time = now_utc()
    messages_to_delete = [message]
    if message.sender_type == "assistant":
        source_user_message = _previous_user_message_for_assistant(
            db,
            conversation_id=conversation.id,
            assistant_message=message,
        )
        if source_user_message is not None:
            messages_to_delete.append(source_user_message)

    for target_message in messages_to_delete:
        target_message.deleted_at = current_time
        target_message.updated_at = current_time
        db.add(target_message)

    conversation.updated_at = current_time
    _refresh_conversation_last_message(db, conversation=conversation)
    db.add(conversation)
    db.commit()
    return get_current_user_diagnosis_conversation(db, user=user, conversation_id=conversation_id)


def set_current_user_diagnosis_message_feedback(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
    message_id: UUID,
    feedback: DiagnosisMessageFeedback | None,
    feedback_reasons: list[str] | None = None,
    feedback_detail: str | None = None,
) -> DiagnosisMessageMutationResponse:
    conversation, message = _get_current_user_message(
        db,
        user=user,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    if message.sender_type != "assistant":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能评价助手回复")

    metadata = dict(message.metadata_ or {})
    if feedback is None:
        metadata.pop("feedback", None)
        metadata.pop("feedback_reasons", None)
        metadata.pop("feedback_detail", None)
    else:
        metadata["feedback"] = feedback
        if feedback == "dislike":
            metadata["feedback_reasons"] = feedback_reasons or []
            if feedback_detail:
                metadata["feedback_detail"] = feedback_detail
            else:
                metadata.pop("feedback_detail", None)
        else:
            metadata.pop("feedback_reasons", None)
            metadata.pop("feedback_detail", None)
    message.metadata_ = metadata
    message.updated_at = now_utc()
    db.add(message)
    db.commit()
    db.refresh(conversation)
    db.refresh(message)
    return _message_mutation_response(conversation, message)


def regenerate_current_user_diagnosis_message(
    db: Session,
    *,
    user: User,
    settings: Settings,
    conversation_id: UUID,
    message_id: UUID,
    model_config_id: UUID | None = None,
    event_callback=None,
) -> DiagnosisMessageMutationResponse:
    if not settings.diagnosis_agent_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="证据型问诊智能体当前未启用")
    conversation, assistant_message = _get_current_user_message(
        db,
        user=user,
        conversation_id=conversation_id,
        message_id=message_id,
    )
    if assistant_message.sender_type != "assistant":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能重新生成助手回复")
    if assistant_message.message_type != "text":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="只能重新生成文本回复")

    source_user_message = _previous_user_message_for_assistant(
        db,
        conversation_id=conversation.id,
        assistant_message=assistant_message,
    )
    if source_user_message is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未找到可用于重试的用户消息")

    user_preferences = _preferences_for_user(db, user)
    model_config = resolve_current_user_llm_config(
        db,
        user=user,
        settings=settings,
        model_config_id=model_config_id,
    )
    history = _history_for_model_before(
        db,
        conversation_id=conversation.id,
        before_message=source_user_message,
    )

    source_metadata = source_user_message.metadata_ or {}
    structured_data = source_metadata.get("structured_data")
    if not isinstance(structured_data, dict):
        structured_data = {}
    multimodal_analysis = db.scalar(
        select(DiagnosisMultimodalAnalysis)
        .where(DiagnosisMultimodalAnalysis.message_id == source_user_message.id)
        .order_by(desc(DiagnosisMultimodalAnalysis.created_at))
    )
    multimodal_observations: dict[str, Any] = {}
    if multimodal_analysis is not None and multimodal_analysis.status == "completed":
        multimodal_observations = dict(multimodal_analysis.analysis_json or {})
        if multimodal_analysis.analysis_text:
            multimodal_observations["analysis_text"] = multimodal_analysis.analysis_text

    execution = execute_diagnosis_agent(
        db,
        user=user,
        conversation=conversation,
        user_message=source_user_message,
        settings=settings,
        model_config=model_config,
        original_question=source_user_message.content,
        history=history,
        structured_data=structured_data,
        multimodal_observations=multimodal_observations,
        user_preferences=user_preferences,
        event_callback=event_callback,
    )
    reply = execution.result.answer
    agent_run_response = execution.response()

    current_time = now_utc()
    metadata = dict(assistant_message.metadata_ or {})
    metadata.update(
        {
            "provider": model_config.provider_name,
            "model": model_config.model_id,
            "model_config_id": str(model_config.config_id) if model_config.config_id else None,
            "pipeline": "agentic_kg_rag",
            "agent_run": agent_run_response.model_dump(mode="json"),
            "regenerated_at": current_time.isoformat(),
            "long_term_memory_enabled": False,
        }
    )
    metadata.pop("feedback", None)
    metadata.pop("feedback_reasons", None)
    metadata.pop("feedback_detail", None)
    assistant_message.content = reply
    assistant_message.status = "sent"
    assistant_message.metadata_ = metadata
    assistant_message.updated_at = current_time
    conversation.updated_at = current_time
    conversation.last_message_at = current_time
    db.add_all([conversation, assistant_message])
    db.flush()
    link_agent_run_to_assistant_message(db, execution=execution, assistant_message=assistant_message)
    db.commit()
    db.refresh(conversation)
    db.refresh(assistant_message)
    return _message_mutation_response(conversation, assistant_message)


def create_current_user_diagnosis_turn(
    db: Session,
    *,
    user: User,
    settings: Settings,
    message: str,
    conversation_id: UUID | None = None,
    model_config_id: UUID | None = None,
    project_id: UUID | None = None,
    event_callback=None,
) -> DiagnosisConversationTurnResponse:
    normalized_message = message.strip()
    user_preferences = _preferences_for_user(db, user)
    auto_generate_title = bool(user_preferences.get("auto_generate_title", True))
    if not normalized_message:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="问诊内容不能为空")
    if not settings.diagnosis_agent_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="证据型问诊智能体当前未启用")

    model_config = resolve_current_user_llm_config(
        db,
        user=user,
        settings=settings,
        model_config_id=model_config_id,
    )

    if conversation_id is None:
        project = _get_current_user_project(db, user=user, project_id=project_id) if project_id is not None else None
        title_source = normalized_message
        conversation = Conversation(
            user_id=user.id,
            project_id=project.id if project is not None else None,
            title=_title_from_message(title_source) if auto_generate_title else "新问诊",
            summary=_summary_from_message(title_source) if auto_generate_title else None,
            conversation_type="diagnosis",
            status="active",
        )
        db.add(conversation)
        db.flush()
    else:
        conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)

    history = _history_for_model(db, conversation_id=conversation.id)
    current_time = now_utc()
    user_message = Message(
        conversation_id=conversation.id,
        sender_type="user",
        content=normalized_message,
        message_type="text",
        status="sent",
    )
    conversation.last_message_at = current_time
    if auto_generate_title and _is_placeholder_diagnosis_title(conversation.title):
        conversation.title = _title_from_message(normalized_message)
    if auto_generate_title and not (conversation.summary or "").strip():
        conversation.summary = _summary_from_message(normalized_message)
    db.add(user_message)
    db.commit()
    db.refresh(conversation)
    db.refresh(user_message)

    execution = execute_diagnosis_agent(
        db,
        user=user,
        conversation=conversation,
        user_message=user_message,
        settings=settings,
        model_config=model_config,
        original_question=normalized_message,
        history=history,
        structured_data={},
        multimodal_observations={},
        user_preferences=user_preferences,
        event_callback=event_callback,
    )
    reply = execution.result.answer
    agent_run_response = execution.response()

    assistant_message = Message(
        conversation_id=conversation.id,
        sender_type="assistant",
        content=reply,
        message_type="text",
        status="sent",
        metadata_={
            "provider": model_config.provider_name,
            "model": model_config.model_id,
            "model_config_id": str(model_config.config_id) if model_config.config_id else None,
            "pipeline": "agentic_kg_rag",
            "agent_run": agent_run_response.model_dump(mode="json"),
            "knowledge_graph_enabled": bool(user_preferences.get("knowledge_graph_enabled", True)),
            "rag_enabled": bool(user_preferences.get("rag_enabled", True)),
            "long_term_memory_enabled": False,
        },
    )
    conversation.last_message_at = now_utc()
    db.add(assistant_message)
    db.flush()
    link_agent_run_to_assistant_message(db, execution=execution, assistant_message=assistant_message)
    db.commit()
    db.refresh(conversation)
    db.refresh(assistant_message)

    return DiagnosisConversationTurnResponse(
        conversation=_conversation_response(conversation),
        user_message=_message_response(user_message),
        assistant_message=_message_response(assistant_message),
        model=model_config.model_id,
        provider=model_config.provider_name,
        agent_run=agent_run_response,
    )


def create_current_user_multimodal_diagnosis_turn(
    db: Session,
    *,
    user: User,
    settings: Settings,
    message: str,
    attachments: list[DiagnosisAttachmentUpload],
    attachment_ids: list[UUID] | None = None,
    structured_data: dict[str, Any] | None = None,
    conversation_id: UUID | None = None,
    model_config_id: UUID | None = None,
    project_id: UUID | None = None,
    event_callback=None,
) -> DiagnosisConversationTurnResponse:
    normalized_message = message.strip()
    structured_payload = structured_data or {}
    user_preferences = _preferences_for_user(db, user)
    auto_generate_title = bool(user_preferences.get("auto_generate_title", True))
    preuploaded_files = _get_current_user_diagnosis_draft_attachments(
        db,
        user=user,
        file_ids=attachment_ids or [],
    )
    if not normalized_message and not attachments and not preuploaded_files and not structured_payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="问诊内容不能为空")
    if not settings.diagnosis_agent_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="证据型问诊智能体当前未启用")

    title_source = normalized_message or _title_from_attachments(
        attachments,
        structured_payload,
        preuploaded_files=preuploaded_files,
    )

    model_config = resolve_current_user_llm_config(
        db,
        user=user,
        settings=settings,
        model_config_id=model_config_id,
    )

    if conversation_id is None:
        project = _get_current_user_project(db, user=user, project_id=project_id) if project_id is not None else None
        conversation = Conversation(
            user_id=user.id,
            project_id=project.id if project is not None else None,
            title=_title_from_message(title_source) if auto_generate_title else "新问诊",
            summary=_summary_from_message(title_source) if auto_generate_title else None,
            conversation_type="diagnosis",
            status="active",
        )
        db.add(conversation)
        db.flush()
    else:
        conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)

    history = _history_for_model(db, conversation_id=conversation.id)
    current_time = now_utc()
    user_message = Message(
        conversation_id=conversation.id,
        sender_type="user",
        content=normalized_message,
        message_type="text",
        status="sent",
        metadata_={
            "structured_data": structured_payload,
            "pipeline": "multimodal_pending",
        },
    )
    conversation.last_message_at = current_time
    if auto_generate_title and _is_placeholder_diagnosis_title(conversation.title):
        conversation.title = _title_from_message(title_source)
    if auto_generate_title and not (conversation.summary or "").strip():
        conversation.summary = _summary_from_message(title_source)
    db.add(user_message)
    db.flush()

    try:
        newly_uploaded_files = _save_message_attachments(
            db,
            user=user,
            conversation=conversation,
            message=user_message,
            attachments=attachments,
        )
        uploaded_files = _attach_preuploaded_files_to_message(
            db,
            conversation=conversation,
            message=user_message,
            files=preuploaded_files,
        )
        uploaded_files.extend(newly_uploaded_files)
        analysis = DiagnosisMultimodalAnalysis(
            conversation_id=conversation.id,
            message_id=user_message.id,
            file_ids=[str(file.id) for file in uploaded_files],
            status="running",
            model_id=model_config.model_id,
            analysis_json={},
        )
        db.add(analysis)
        db.flush()

        user_metadata = dict(user_message.metadata_ or {})
        user_metadata.update(
            {
                "pipeline": "multimodal_analyzing",
                "attachment_file_ids": [str(file.id) for file in uploaded_files],
                "multimodal_analysis_id": str(analysis.id),
            }
        )
        user_message.metadata_ = user_metadata
        db.add_all([conversation, user_message, analysis])
        db.commit()
        db.refresh(conversation)
        db.refresh(user_message)
        db.refresh(analysis)

        analysis_json, analysis_text = analyze_multimodal_materials(
            settings,
            model_config=model_config,
            message=normalized_message,
            files=uploaded_files,
            structured_data=structured_payload,
        )
        analysis.status = "completed"
        analysis.analysis_json = analysis_json
        analysis.analysis_text = analysis_text
        analysis.updated_at = now_utc()

        user_metadata = dict(user_message.metadata_ or {})
        user_metadata.update(
            {
                "pipeline": "multimodal_agent_ready",
                "attachment_file_ids": [str(file.id) for file in uploaded_files],
                "multimodal_analysis_id": str(analysis.id),
            }
        )
        user_message.metadata_ = user_metadata
        db.add_all([user_message, analysis])
        db.commit()
        db.refresh(conversation)
        db.refresh(user_message)
        db.refresh(analysis)

        multimodal_observations = dict(analysis_json)
        multimodal_observations["analysis_text"] = analysis_text
        execution = execute_diagnosis_agent(
            db,
            user=user,
            conversation=conversation,
            user_message=user_message,
            settings=settings,
            model_config=model_config,
            original_question=normalized_message,
            history=history,
            structured_data=structured_payload,
            multimodal_observations=multimodal_observations,
            user_preferences=user_preferences,
            event_callback=event_callback,
        )
        reply = execution.result.answer
        agent_run_response = execution.response()

    except (LLMProviderError, LLMConfigurationError) as error:
        if "analysis" in locals() and analysis.status != "completed":
            analysis.status = "failed"
            analysis.error_message = str(error)
            analysis.updated_at = now_utc()
            db.add(analysis)
            db.commit()
        _save_failed_assistant_message(db, conversation=conversation, model_config=model_config)
        raise error
    except HTTPException:
        db.rollback()
        raise

    assistant_message = Message(
        conversation_id=conversation.id,
        sender_type="assistant",
        content=reply,
        message_type="text",
        status="sent",
        metadata_={
            "provider": model_config.provider_name,
            "model": model_config.model_id,
            "model_config_id": str(model_config.config_id) if model_config.config_id else None,
            "pipeline": "agentic_kg_rag_multimodal",
            "agent_run": agent_run_response.model_dump(mode="json"),
            "multimodal_analysis_id": str(analysis.id),
            "knowledge_graph_enabled": bool(user_preferences.get("knowledge_graph_enabled", True)),
            "rag_enabled": bool(user_preferences.get("rag_enabled", True)),
            "long_term_memory_enabled": False,
        },
    )
    conversation.last_message_at = now_utc()
    db.add(assistant_message)
    db.flush()
    link_agent_run_to_assistant_message(db, execution=execution, assistant_message=assistant_message)
    db.commit()
    db.refresh(conversation)
    db.refresh(user_message)
    db.refresh(assistant_message)

    return DiagnosisConversationTurnResponse(
        conversation=_conversation_response(conversation),
        user_message=_message_response(user_message),
        assistant_message=_message_response(assistant_message),
        model=model_config.model_id,
        provider=model_config.provider_name,
        agent_run=agent_run_response,
    )


def transcribe_current_user_diagnosis_audio(
    db: Session,
    *,
    user: User,
    settings: Settings,
    file_name: str,
    content_type: str,
    content: bytes,
) -> DiagnosisVoiceTranscription:
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="语音内容不能为空")
    if len(content) > settings.voice_transcription_max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="语音文件过大")

    normalized_content_type = (content_type or "application/octet-stream").lower()
    if not (
        normalized_content_type.startswith("audio/")
        or normalized_content_type in {"application/octet-stream", "video/webm"}
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请上传语音文件")

    base_model_config = resolve_current_user_llm_config(db, user=user, settings=settings, model_config_id=None)
    transcription_model_config = OpenAICompatibleModelConfig(
        provider_name=base_model_config.provider_name,
        model_id=settings.openai_transcription_model_id,
        api_key=base_model_config.api_key,
        api_request_url=base_model_config.api_request_url,
        config_id=base_model_config.config_id,
    )
    text = request_openai_compatible_transcription(
        transcription_model_config,
        audio_content=content,
        file_name=file_name or "voice.webm",
        content_type=normalized_content_type,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    normalized_text = " ".join(text.split())
    if not normalized_text:
        raise LLMProviderError("语音转写结果为空")

    return DiagnosisVoiceTranscription(
        text=normalized_text,
        model=transcription_model_config.model_id,
        provider=transcription_model_config.provider_name,
    )


def move_current_user_diagnosis_conversation_project(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
    project_id: UUID | None,
) -> DiagnosisConversationResponse:
    conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)
    project = _get_current_user_project(db, user=user, project_id=project_id) if project_id is not None else None

    current_time = now_utc()
    conversation.project_id = project.id if project is not None else None
    conversation.updated_at = current_time
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return _conversation_response(conversation)


def analyze_multimodal_materials(
    settings: Settings,
    *,
    model_config: OpenAICompatibleModelConfig,
    message: str,
    files: list[UploadedFile],
    structured_data: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    messages = _build_multimodal_analysis_messages(
        message=message,
        files=files,
        structured_data=structured_data,
        include_inline_images=True,
    )
    try:
        reply = request_openai_compatible_reply(
            model_config,
            messages=messages,
            timeout_seconds=settings.openai_timeout_seconds,
            max_tokens=1600,
        )
    except LLMProviderError:
        if not _messages_include_inline_images(messages):
            raise
        reply = request_openai_compatible_reply(
            model_config,
            messages=_build_multimodal_analysis_messages(
                message=message,
                files=files,
                structured_data=structured_data,
                include_inline_images=False,
            ),
            timeout_seconds=settings.openai_timeout_seconds,
            max_tokens=1600,
        )
    analysis_json = _parse_analysis_json(reply)
    analysis_json["file_contexts"] = _file_analysis_contexts(files)
    analysis_text = _analysis_text_from_json(analysis_json, fallback=reply)
    return analysis_json, analysis_text


def _build_multimodal_analysis_messages(
    *,
    message: str,
    files: list[UploadedFile],
    structured_data: dict[str, Any],
    include_inline_images: bool,
) -> list[dict[str, Any]]:
    file_lines = []
    for index, file in enumerate(files, start=1):
        context = _file_analysis_context(file)
        extraction = context.get("extracted_text")
        extraction_preview = ""
        if isinstance(extraction, str) and extraction.strip():
            extraction_preview = f"\n   已解析文本：{_truncate_text(extraction, 1800)}"
        status_text = context.get("extraction_status") or "saved"
        note_text = context.get("extraction_note") or ""
        file_lines.append(
            (
                f"{index}. {file.file_name}，类型：{file.file_type}，MIME：{file.mime_type}，"
                f"大小：{file.file_size} bytes，解析状态：{status_text}，URL：{file.storage_url or file.storage_key}"
                f"{f'，说明：{note_text}' if note_text else ''}"
                f"{extraction_preview}"
            )
        )
    prompt = "\n\n".join(
        [
            f"用户文本：\n{message.strip() or '无，用户仅上传材料。'}",
            f"结构化养殖数据：\n{json.dumps(structured_data, ensure_ascii=False) if structured_data else '无'}",
            f"附件列表：\n{chr(10).join(file_lines) if file_lines else '无'}",
            "请只输出 JSON，不要输出最终问诊回复。",
        ]
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for file in files:
        image_url = _image_model_url(file) if include_inline_images else None
        if image_url:
            content.append({"type": "image_url", "image_url": {"url": image_url}})

    return [
        {"role": "system", "content": MULTIMODAL_ANALYSIS_PROMPT},
        {"role": "user", "content": content if len(content) > 1 else prompt},
    ]


def _save_message_attachments(
    db: Session,
    *,
    user: User,
    conversation: Conversation,
    message: Message,
    attachments: list[DiagnosisAttachmentUpload],
) -> list[UploadedFile]:
    uploaded_files: list[UploadedFile] = []
    for index, attachment in enumerate(attachments, start=1):
        if not attachment.content:
            continue

        file_id = uuid.uuid4()
        safe_file_name = _safe_file_name(attachment.file_name or f"attachment-{index}")
        normalized_content_type = _content_type_for_attachment(attachment.file_name, attachment.content_type)
        file_type = _file_type_from_attachment(attachment.file_name, normalized_content_type)
        _ensure_supported_attachment(
            file_name=attachment.file_name or safe_file_name,
            content_type=normalized_content_type,
            file_type=file_type,
        )
        analysis_context = _extract_attachment_analysis_context(
            file_name=attachment.file_name or safe_file_name,
            content_type=normalized_content_type,
            file_type=file_type,
            content=attachment.content,
        )
        object_key = f"diagnosis/{conversation.id}/{message.id}/original/{file_id}-{safe_file_name}"
        storage_url = upload_object_file(
            object_key=object_key,
            content=attachment.content,
            content_type=normalized_content_type,
            failure_detail="问诊附件上传失败，请稍后再试",
        )
        uploaded_file = UploadedFile(
            id=file_id,
            user_id=user.id,
            project_id=conversation.project_id,
            file_name=attachment.file_name or safe_file_name,
            file_type=file_type,
            mime_type=normalized_content_type,
            storage_key=object_key,
            storage_url=storage_url,
            file_size=len(attachment.content),
            checksum=hashlib.sha256(attachment.content).hexdigest(),
            metadata_={
                "source": "diagnosis_message",
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "analysis_context": analysis_context,
            },
        )
        setattr(uploaded_file, "_analysis_content", attachment.content)
        db.add(uploaded_file)
        db.flush()
        db.add(MessageFile(message_id=message.id, file_id=uploaded_file.id))
        uploaded_files.append(uploaded_file)

    return uploaded_files


def _get_current_user_diagnosis_draft_attachments(
    db: Session,
    *,
    user: User,
    file_ids: list[UUID],
) -> list[UploadedFile]:
    unique_file_ids = list(dict.fromkeys(file_ids))
    if not unique_file_ids:
        return []

    files = list(
        db.scalars(
            select(UploadedFile).where(
                UploadedFile.id.in_(unique_file_ids),
                UploadedFile.user_id == user.id,
                UploadedFile.deleted_at.is_(None),
            )
        )
    )
    files_by_id = {file.id: file for file in files}
    if len(files_by_id) != len(unique_file_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部分待发送附件不存在")

    ordered_files = [files_by_id[file_id] for file_id in unique_file_ids]
    if any((file.metadata_ or {}).get("source") != "diagnosis_draft" for file in ordered_files):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="部分附件已被绑定到其他消息")
    return ordered_files


def _attach_preuploaded_files_to_message(
    db: Session,
    *,
    conversation: Conversation,
    message: Message,
    files: list[UploadedFile],
) -> list[UploadedFile]:
    for uploaded_file in files:
        metadata = dict(uploaded_file.metadata_ or {})
        metadata.update(
            {
                "source": "diagnosis_message",
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "upload_state": "attached",
            }
        )
        uploaded_file.project_id = conversation.project_id
        uploaded_file.metadata_ = metadata
        db.add(uploaded_file)
        db.add(MessageFile(message_id=message.id, file_id=uploaded_file.id))
    db.flush()
    return files


def _content_type_for_attachment(file_name: str, content_type: str) -> str:
    normalized = (content_type or "").strip().lower()
    if normalized and normalized != "application/octet-stream":
        return normalized
    guessed_type, _ = mimetypes.guess_type(file_name or "")
    return (guessed_type or "application/octet-stream").lower()


def _file_type_from_attachment(file_name: str, content_type: str) -> str:
    normalized = (content_type or "").lower()
    if normalized.startswith("image/"):
        return "image"
    if normalized.startswith("video/"):
        return "video"
    if normalized.startswith("audio/"):
        return "audio"
    extension = _file_extension(file_name)
    if normalized in DOCUMENT_MIME_TYPES or normalized.startswith("text/") or extension in DOCUMENT_EXTENSIONS:
        return "document"
    return "other"


def _ensure_supported_attachment(*, file_name: str, content_type: str, file_type: str) -> None:
    if file_type in {"image", "video"}:
        return
    if file_type == "document":
        extension = _file_extension(file_name)
        if (
            content_type in DOCUMENT_MIME_TYPES
            or content_type.startswith("text/")
            or extension in DOCUMENT_EXTENSIONS
        ):
            return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"暂不支持该材料格式：{file_name}",
    )


def _file_extension(file_name: str) -> str:
    match = re.search(r"(\.[A-Za-z0-9]+)$", file_name or "")
    return match.group(1).lower() if match else ""


def _extract_attachment_analysis_context(
    *,
    file_name: str,
    content_type: str,
    file_type: str,
    content: bytes,
) -> dict[str, Any]:
    base_context: dict[str, Any] = {
        "file_name": file_name,
        "file_type": file_type,
        "mime_type": content_type,
        "file_size": len(content),
    }

    if file_type == "image":
        base_context.update(
            {
                "extraction_status": "vision_ready",
                "extraction_note": "图片已保存到 OSS；解析阶段会优先交给多模态模型观察病蚕近景、蚕室环境和可见症状。",
            }
        )
        return base_context

    if file_type == "video":
        base_context.update(
            {
                "extraction_status": "direct_url_ready",
                "extraction_note": "视频已保存到 OSS；当前版本会优先把视频 URL 直接交给支持视频输入的多模态模型，不再额外抽帧。",
            }
        )
        return base_context

    if file_type == "document":
        extracted_text, extraction_note = _extract_document_text(
            file_name=file_name,
            content_type=content_type,
            content=content,
        )
        base_context.update(
            {
                # Documents keep their original object URL for providers that support
                # direct file input; extracted text is an additional fallback rather
                # than a replacement for that capability.
                "extraction_status": "direct_url_ready",
                "extraction_note": f"原始文档 URL 可供模型直接读取；{extraction_note}",
            }
        )
        if extracted_text:
            base_context["extracted_text"] = extracted_text
        return base_context

    base_context.update(
        {
            "extraction_status": "stored_only",
            "extraction_note": "材料已保存，但当前版本未识别出可解析的多模态类型。",
        }
    )
    return base_context


def _extract_document_text(*, file_name: str, content_type: str, content: bytes) -> tuple[str, str]:
    extension = _file_extension(file_name)

    if extension in {".html", ".htm"} or content_type == "text/html":
        text = _html_to_text(_decode_text_content(content))
        return _truncate_text(text, MAX_EXTRACTED_TEXT_CHARS), "已解析 HTML 文本内容。"

    if extension == ".rtf" or content_type in {"application/rtf", "text/rtf"}:
        text = _rtf_to_text(_decode_text_content(content))
        return _truncate_text(text, MAX_EXTRACTED_TEXT_CHARS), "已解析 RTF 文本内容。"

    if extension in {".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".log"} or content_type.startswith("text/"):
        text = _decode_text_content(content)
        return _truncate_text(text, MAX_EXTRACTED_TEXT_CHARS), "已解析文本内容。"

    if extension == ".docx" or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        text = _extract_docx_text(content)
        return _truncate_text(text, MAX_EXTRACTED_TEXT_CHARS), (
            "已解析 DOCX 文本内容。" if text else "DOCX 未解析到可用正文。"
        )

    if extension == ".pptx" or content_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        text = _extract_pptx_text(content)
        return _truncate_text(text, MAX_EXTRACTED_TEXT_CHARS), (
            "已解析 PPTX 幻灯片文本内容。" if text else "PPTX 未解析到可用正文。"
        )

    if extension == ".xlsx" or content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        text = _extract_xlsx_text(content)
        return _truncate_text(text, MAX_EXTRACTED_TEXT_CHARS), (
            "已解析 XLSX 表格文本内容。" if text else "XLSX 未解析到可用表格文本。"
        )

    if extension == ".pdf" or content_type == "application/pdf":
        text = _extract_pdf_text(content)
        return _truncate_text(text, MAX_EXTRACTED_TEXT_CHARS), (
            "已解析 PDF 文本内容。" if text else "PDF 已保存，当前环境未提取到可用文本。"
        )

    if extension in {".doc", ".ppt", ".xls"}:
        return "", "旧版 Office 二进制文档已保存；建议转换为 DOCX/PPTX/XLSX 后可获得更稳定解析。"

    return "", "文档已保存，当前版本暂未提供该格式的文本解析器。"


def _decode_text_content(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _html_to_text(text: str) -> str:
    without_scripts = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", text, flags=re.IGNORECASE)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return _normalize_extracted_text(html.unescape(without_tags))


def _rtf_to_text(text: str) -> str:
    stripped = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    stripped = re.sub(r"\\[a-zA-Z]+-?\d* ?", " ", stripped)
    stripped = stripped.replace("{", " ").replace("}", " ").replace("\\", " ")
    return _normalize_extracted_text(stripped)


def _extract_docx_text(content: bytes) -> str:
    return _extract_zip_xml_text(content, ["word/document.xml"], ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")


def _extract_pptx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            slide_names = sorted(name for name in archive.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", name))
            parts = [
                _extract_xml_text_from_bytes(
                    archive.read(slide_name),
                    ".//{http://schemas.openxmlformats.org/drawingml/2006/main}t",
                )
                for slide_name in slide_names[:80]
            ]
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        return ""
    return _normalize_extracted_text("\n".join(part for part in parts if part.strip()))


def _extract_xlsx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            shared_strings = _extract_xlsx_shared_strings(archive)
            sheet_names = sorted(name for name in archive.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", name))
            rows: list[str] = []
            for sheet_name in sheet_names[:20]:
                sheet_root = ElementTree.fromstring(archive.read(sheet_name))
                namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
                for row in sheet_root.findall(f".//{namespace}row")[:300]:
                    cells: list[str] = []
                    for cell in row.findall(f"{namespace}c")[:40]:
                        value = cell.find(f"{namespace}v")
                        if value is None or not value.text:
                            continue
                        if cell.attrib.get("t") == "s":
                            try:
                                cells.append(shared_strings[int(value.text)])
                            except (ValueError, IndexError):
                                continue
                        else:
                            cells.append(value.text)
                    if cells:
                        rows.append(" | ".join(cells))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        return ""
    return _normalize_extracted_text("\n".join(rows))


def _extract_xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    strings: list[str] = []
    for item in root.findall(f"{namespace}si"):
        parts = [node.text or "" for node in item.findall(f".//{namespace}t")]
        strings.append("".join(parts))
    return strings


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except ImportError:
        return ""

    try:
        reader = PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages[:20]]
    except Exception:
        return ""
    return _normalize_extracted_text("\n".join(pages))


def _extract_zip_xml_text(content: bytes, names: list[str], text_xpath: str) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            parts = [
                _extract_xml_text_from_bytes(archive.read(name), text_xpath)
                for name in names
                if name in archive.namelist()
            ]
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        return ""
    return _normalize_extracted_text("\n".join(part for part in parts if part.strip()))


def _extract_xml_text_from_bytes(content: bytes, text_xpath: str) -> str:
    root = ElementTree.fromstring(content)
    parts = [node.text or "" for node in root.findall(text_xpath)]
    return _normalize_extracted_text("\n".join(parts))


def _normalize_extracted_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _file_analysis_context(file: UploadedFile) -> dict[str, Any]:
    metadata = file.metadata_ or {}
    context = metadata.get("analysis_context")
    return context if isinstance(context, dict) else {}


def _file_analysis_contexts(files: list[UploadedFile]) -> list[dict[str, Any]]:
    return [_file_analysis_context(file) for file in files]


def _image_model_url(file: UploadedFile) -> str | None:
    if file.file_type != "image":
        return None
    content = getattr(file, "_analysis_content", None)
    if isinstance(content, bytes) and 0 < len(content) <= MAX_INLINE_IMAGE_BYTES:
        encoded = base64.b64encode(content).decode("ascii")
        return f"data:{file.mime_type};base64,{encoded}"
    return file.storage_url


def _messages_include_inline_images(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        if any(isinstance(part, dict) and part.get("type") == "image_url" for part in content):
            return True
    return False


def _truncate_text(text: str, max_chars: int) -> str:
    normalized = text.strip()
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[:max_chars].rstrip()}\n...[已截断 {len(normalized) - max_chars} 字]"


def _safe_file_name(file_name: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|\s]+", "-", file_name.strip())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized[:120] or "attachment"


def _parse_analysis_json(reply: str) -> dict[str, Any]:
    normalized = reply.strip()
    if normalized.startswith("```"):
        normalized = re.sub(r"^```(?:json)?\s*", "", normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s*```$", "", normalized)

    try:
        parsed = json.loads(normalized)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    object_match = re.search(r"\{.*\}", normalized, flags=re.DOTALL)
    if object_match:
        try:
            parsed = json.loads(object_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return {
        "observations": [normalized],
        "symptoms": [],
        "environment_clues": [],
        "possible_entities": [],
        "retrieval_queries": [],
        "missing_info": [],
        "risk_notes": ["多模态解析模型未返回严格 JSON，已保存原始解析文本。"],
        "raw_text": reply,
    }


def _analysis_text_from_json(analysis_json: dict[str, Any], *, fallback: str) -> str:
    lines: list[str] = []
    labels = {
        "observations": "观察结果",
        "symptoms": "症状关键词",
        "environment_clues": "环境线索",
        "possible_entities": "可能相关实体",
        "retrieval_queries": "后续检索词",
        "missing_info": "仍需补充",
        "risk_notes": "风险提示",
    }
    for key, label in labels.items():
        value = analysis_json.get(key)
        if isinstance(value, list) and value:
            lines.append(f"{label}：{'; '.join(str(item) for item in value if str(item).strip())}")
        elif isinstance(value, str) and value.strip():
            lines.append(f"{label}：{value.strip()}")

    file_contexts = analysis_json.get("file_contexts")
    if isinstance(file_contexts, list):
        for index, context in enumerate(file_contexts, start=1):
            if not isinstance(context, dict):
                continue
            extracted_text = context.get("extracted_text")
            extraction_note = context.get("extraction_note")
            file_name = context.get("file_name") or f"附件 {index}"
            if isinstance(extracted_text, str) and extracted_text.strip():
                lines.append(f"{file_name} 解析文本：{_truncate_text(extracted_text, 1200)}")
            elif isinstance(extraction_note, str) and extraction_note.strip():
                lines.append(f"{file_name} 解析说明：{extraction_note.strip()}")

    return "\n".join(lines).strip() or fallback.strip()


def _get_current_user_conversation(db: Session, *, user: User, conversation_id: UUID) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.conversation_type == "diagnosis",
            Conversation.status != "deleted",
        )
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="问诊对话不存在")
    return conversation


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


def _get_current_user_message(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
    message_id: UUID,
) -> tuple[Conversation, Message]:
    conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)
    message = db.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation.id,
            Message.deleted_at.is_(None),
        )
    )
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="消息不存在")
    return conversation, message


def _history_for_model(db: Session, *, conversation_id: UUID) -> list[DiagnosisContextMessage]:
    messages = db.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.deleted_at.is_(None),
            Message.status == "sent",
            Message.message_type == "text",
            Message.sender_type.in_(["user", "assistant"]),
        )
        .order_by(Message.created_at.asc())
    ).all()

    history: list[DiagnosisContextMessage] = []
    for message in messages[-40:]:
        content = message.content.strip()
        if not content or message.sender_type not in {"user", "assistant"}:
            continue
        history.append(DiagnosisContextMessage(role=message.sender_type, content=content))
    return history


def _history_for_model_before(
    db: Session,
    *,
    conversation_id: UUID,
    before_message: Message,
) -> list[DiagnosisContextMessage]:
    messages = db.scalars(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.deleted_at.is_(None),
            Message.status == "sent",
            Message.message_type == "text",
            Message.sender_type.in_(["user", "assistant"]),
            Message.created_at < before_message.created_at,
        )
        .order_by(Message.created_at.asc())
    ).all()

    history: list[DiagnosisContextMessage] = []
    for message in messages[-40:]:
        content = message.content.strip()
        if not content or message.sender_type not in {"user", "assistant"}:
            continue
        history.append(DiagnosisContextMessage(role=message.sender_type, content=content))
    return history


def _previous_user_message_for_assistant(
    db: Session,
    *,
    conversation_id: UUID,
    assistant_message: Message,
) -> Message | None:
    return db.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.deleted_at.is_(None),
            Message.status == "sent",
            Message.message_type == "text",
            Message.sender_type == "user",
            Message.created_at < assistant_message.created_at,
        )
        .order_by(desc(Message.created_at))
    )


def _refresh_conversation_last_message(db: Session, *, conversation: Conversation) -> None:
    last_message = db.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation.id,
            Message.deleted_at.is_(None),
            Message.status == "sent",
        )
        .order_by(desc(Message.created_at))
    )
    conversation.last_message_at = last_message.created_at if last_message else None


def _save_failed_assistant_message(
    db: Session,
    *,
    conversation: Conversation,
    model_config: OpenAICompatibleModelConfig,
) -> None:
    assistant_message = Message(
        conversation_id=conversation.id,
        sender_type="assistant",
        content="模型调用失败，请稍后重试。",
        message_type="text",
        status="failed",
        metadata_={
            "provider": model_config.provider_name,
            "model": model_config.model_id,
            "model_config_id": str(model_config.config_id) if model_config.config_id else None,
            "pipeline": "llm_only",
        },
    )
    conversation.last_message_at = now_utc()
    db.add(assistant_message)
    db.commit()


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


def _published_expert_reviews(db: Session, *, conversation_id: UUID) -> list[DiagnosisExpertReviewResponse]:
    """Read administrator-owned reviews without making the user API depend on admin deployment order."""
    try:
        rows = db.execute(
            text(
                """
                SELECT id::text AS id, reviewer_name_snapshot, risk_level, conclusion,
                       recommendation, evidence, version, published_at
                  FROM admin.expert_reviews
                 WHERE conversation_id = CAST(:conversation_id AS uuid)
                   AND status = 'published'
                 ORDER BY version DESC
                """
            ),
            {"conversation_id": str(conversation_id)},
        ).mappings().all()
    except SQLAlchemyError:
        db.rollback()
        return []

    return [
        DiagnosisExpertReviewResponse(
            id=row["id"],
            reviewer_name=row["reviewer_name_snapshot"],
            risk_level=row["risk_level"],
            conclusion=row["conclusion"],
            recommendation=row["recommendation"],
            evidence=row["evidence"] or [],
            version=int(row["version"]),
            published_at=row["published_at"],
        )
        for row in rows
        if row["published_at"] is not None and row["risk_level"] in {"low", "medium", "high", "critical"}
    ]


def _message_mutation_response(conversation: Conversation, message: Message) -> DiagnosisMessageMutationResponse:
    return DiagnosisMessageMutationResponse(
        conversation=_conversation_response(conversation),
        message=_message_response(message),
    )


def _message_response(message: Message) -> DiagnosisMessageResponse:
    metadata = message.metadata_ or {}
    feedback = metadata.get("feedback")
    feedback_reasons = metadata.get("feedback_reasons")
    feedback_detail = metadata.get("feedback_detail")
    return DiagnosisMessageResponse(
        id=str(message.id),
        role=message.sender_type,
        content=message.content,
        message_type=message.message_type,
        status=message.status,
        created_at=message.created_at,
        displayed_at=_message_displayed_at(message, metadata),
        feedback=feedback if feedback in {"like", "dislike"} else None,
        feedback_reasons=feedback_reasons if isinstance(feedback_reasons, list) else [],
        feedback_detail=feedback_detail if isinstance(feedback_detail, str) else None,
        attachments=[_file_response(message_file.file) for message_file in message.files if message_file.file.deleted_at is None],
        agent_run=agent_run_from_message_metadata(metadata),
    )


def _file_response(file: UploadedFile) -> DiagnosisFileResponse:
    return DiagnosisFileResponse(
        id=str(file.id),
        file_name=file.file_name,
        file_type=file.file_type,
        mime_type=file.mime_type,
        storage_url=file.storage_url,
        file_size=file.file_size,
        metadata=file.metadata_ or {},
    )


def _message_displayed_at(message: Message, metadata: dict[str, Any]) -> datetime:
    regenerated_at = metadata.get("regenerated_at")
    if isinstance(regenerated_at, str):
        try:
            return datetime.fromisoformat(regenerated_at)
        except ValueError:
            pass
    return message.created_at


def _new_share_token(db: Session) -> str:
    for _ in range(8):
        token = secrets.token_urlsafe(24)
        exists = db.scalar(select(ConversationShare.id).where(ConversationShare.share_token == token))
        if not exists:
            return token
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="分享链接生成失败")


def _conversation_share_response(share: ConversationShare, *, settings: Settings) -> DiagnosisConversationShareResponse:
    return DiagnosisConversationShareResponse(
        id=str(share.id),
        conversation_id=str(share.conversation_id),
        share_token=share.share_token,
        share_url=f"{settings.public_frontend_base_url.rstrip('/')}/share/{share.share_token}",
        title=share.title,
        variant=share.variant,
        created_at=share.created_at,
        expires_at=share.expires_at,
    )


def _summary_from_message(message: str) -> str:
    normalized = " ".join(message.replace("\u3000", " ").split())
    normalized = re.sub(r"^[#>*`\-\s]+", "", normalized).strip()
    if not normalized:
        return "养蚕问诊"
    if len(normalized) <= 72:
        return normalized
    return f"{normalized[:72]}…"


def _is_placeholder_diagnosis_title(title: str | None) -> bool:
    return not (title or "").strip() or (title or "").strip().lower() in {"new diagnosis", "新问诊", "未命名问诊"}


def _title_from_message(message: str) -> str:
    normalized = _summary_from_message(message).rstrip("。！!？?，,；;：:")
    if not normalized:
        return "养蚕问诊"

    title_candidate = normalized
    intro_prefixes = (
        "请问",
        "你好，",
        "你好",
        "麻烦",
        "帮我",
        "给我",
        "我想了解",
        "我想问",
        "能不能",
        "可以",
    )
    for prefix in intro_prefixes:
        if title_candidate.startswith(prefix):
            title_candidate = title_candidate[len(prefix) :].lstrip("，,：: ")

    introduction_match = re.match(r"^(?:介绍(?:一下|下)?|讲讲|科普(?:一下)?|说明(?:一下)?|说说)(.+)$", title_candidate)
    definition_match = re.match(r"^(?:什么是|关于)(.+)$", title_candidate)
    if introduction_match or definition_match:
        subject = (introduction_match or definition_match).group(1).strip().rstrip("。！!？?，,；;：:")
        subject = re.sub(r"(?:是什么|是怎么回事|有哪些症状|如何防治|怎么办)$", "", subject).strip()
        if subject:
            return _truncate_diagnosis_title(f"{subject}：基础介绍")

    title_candidate = re.sub(r"(?:怎么办|怎么处理|如何处理|如何防治|该怎么做)$", "", title_candidate).strip()
    if title_candidate != normalized and title_candidate:
        return _truncate_diagnosis_title(f"{title_candidate}：处置咨询")
    return _truncate_diagnosis_title(title_candidate or normalized)


def _truncate_diagnosis_title(value: str, max_length: int = 28) -> str:
    return value if len(value) <= max_length else f"{value[:max_length]}…"


def _preferences_for_user(db: Session, user: User) -> dict[str, Any]:
    record = db.get(UserSettings, user.id)
    return dict(record.preferences or {}) if record is not None else {}


def _title_from_attachments(
    attachments: list[DiagnosisAttachmentUpload],
    structured_data: dict[str, Any],
    *,
    preuploaded_files: list[UploadedFile] | None = None,
) -> str:
    if attachments:
        first_file = attachments[0].file_name.strip() or "多模态问诊"
        return _title_from_message(f"上传材料：{first_file}")
    if preuploaded_files:
        first_file = preuploaded_files[0].file_name.strip() or "多模态问诊"
        return _title_from_message(f"上传材料：{first_file}")
    if structured_data:
        return "养殖数据问诊"
    return "新问诊"


def _extract_reply(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text = "".join(_content_part_text(part) for part in content).strip()
            if text:
                return text

    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    raise LLMProviderError("大模型服务没有返回可用回复")


def _content_part_text(part: Any) -> str:
    if isinstance(part, str):
        return part
    if not isinstance(part, dict):
        return ""
    text = part.get("text")
    return text if isinstance(text, str) else ""


def _format_http_error(error: HTTPError) -> str:
    try:
        raw_body = error.read().decode("utf-8")
        body = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raw_body = ""
        body = None

    detail = ""
    if isinstance(body, dict):
        provider_error = body.get("error")
        if isinstance(provider_error, dict):
            message = provider_error.get("message")
            detail = message if isinstance(message, str) else ""
        elif isinstance(body.get("detail"), str):
            detail = body["detail"]

    if not detail:
        detail = raw_body.strip() if raw_body else error.reason
    return f"大模型服务返回 {error.code}：{detail}"

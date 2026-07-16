import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.diagnosis import (
    DiagnosisChatRequest,
    DiagnosisChatResponse,
    DiagnosisConversationCreateRequest,
    DiagnosisConversationDetailResponse,
    DiagnosisConversationMessageCreateRequest,
    DiagnosisConversationPinRequest,
    DiagnosisConversationResponse,
    DiagnosisConversationShareCreateRequest,
    DiagnosisConversationShareResponse,
    DiagnosisConversationTurnResponse,
    DiagnosisConversationUpdateRequest,
    DiagnosisFileResponse,
    DiagnosisMessageFeedbackRequest,
    DiagnosisMessageMutationResponse,
    DiagnosisMessageRegenerateRequest,
    DiagnosisMessageUpdateRequest,
    DiagnosisVoiceTranscriptionResponse,
    PublicDiagnosisConversationShareResponse,
)
from app.schemas.projects import ProjectConversationMoveRequest
from app.services.auth_service import get_current_user
from app.services.diagnosis_service import (
    DiagnosisAttachmentUpload,
    LLMConfigurationError,
    LLMProviderError,
    archive_current_user_diagnosis_conversation,
    create_current_user_diagnosis_turn,
    create_current_user_diagnosis_conversation_share,
    create_current_user_multimodal_diagnosis_turn,
    delete_current_user_diagnosis_draft_attachment,
    delete_current_user_diagnosis_conversation,
    delete_current_user_diagnosis_message,
    generate_diagnosis_reply,
    get_public_diagnosis_conversation_share,
    get_current_user_diagnosis_conversation,
    list_current_user_archived_diagnosis_conversations,
    list_current_user_diagnosis_conversations,
    move_current_user_diagnosis_conversation_project,
    regenerate_current_user_diagnosis_message,
    restore_current_user_diagnosis_conversation,
    search_current_user_diagnosis_conversations,
    set_current_user_diagnosis_conversation_pinned,
    set_current_user_diagnosis_message_feedback,
    transcribe_current_user_diagnosis_audio,
    upload_current_user_diagnosis_attachments,
    update_current_user_diagnosis_conversation,
    update_current_user_diagnosis_message,
)


router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


@router.post("/uploads", response_model=list[DiagnosisFileResponse], status_code=status.HTTP_201_CREATED)
async def upload_diagnosis_attachments(
    request: Request,
    attachments: list[UploadFile] = File(...),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> list[DiagnosisFileResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    if not attachments:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择至少一个问诊材料")
    if len(attachments) > settings.multimodal_attachment_max_count:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"一次最多上传 {settings.multimodal_attachment_max_count} 个问诊材料",
        )

    prepared_attachments: list[DiagnosisAttachmentUpload] = []
    for attachment in attachments:
        content = await attachment.read(settings.multimodal_attachment_max_bytes + 1)
        if len(content) > settings.multimodal_attachment_max_bytes:
            max_mb = max(1, settings.multimodal_attachment_max_bytes // 1024 // 1024)
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"单个问诊材料不能超过 {max_mb}MB")
        prepared_attachments.append(
            DiagnosisAttachmentUpload(
                file_name=attachment.filename or "attachment",
                content_type=attachment.content_type or "application/octet-stream",
                content=content,
            )
        )

    return upload_current_user_diagnosis_attachments(db, user=user, attachments=prepared_attachments)


@router.delete("/uploads/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_diagnosis_attachment(
    file_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_current_user_diagnosis_draft_attachment(db, user=user, file_id=file_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations", response_model=list[DiagnosisConversationResponse])
def list_diagnosis_conversations(
    request: Request,
    db: Session = Depends(get_db_session),
) -> list[DiagnosisConversationResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_current_user_diagnosis_conversations(db, user=user)


@router.get("/conversations/archived", response_model=list[DiagnosisConversationResponse])
def list_archived_diagnosis_conversations(
    request: Request,
    db: Session = Depends(get_db_session),
) -> list[DiagnosisConversationResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_current_user_archived_diagnosis_conversations(db, user=user)


@router.get("/search", response_model=list[DiagnosisConversationResponse])
def search_diagnosis_conversations(
    request: Request,
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db_session),
) -> list[DiagnosisConversationResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return search_current_user_diagnosis_conversations(db, user=user, query=q, limit=limit)


@router.get("/conversations/{conversation_id}", response_model=DiagnosisConversationDetailResponse)
def get_diagnosis_conversation(
    conversation_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> DiagnosisConversationDetailResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return get_current_user_diagnosis_conversation(db, user=user, conversation_id=conversation_id)


@router.patch("/conversations/{conversation_id}", response_model=DiagnosisConversationResponse)
def update_diagnosis_conversation(
    conversation_id: UUID,
    payload: DiagnosisConversationUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> DiagnosisConversationResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_current_user_diagnosis_conversation(db, user=user, conversation_id=conversation_id, title=payload.title)


@router.patch("/conversations/{conversation_id}/project", response_model=DiagnosisConversationResponse)
def move_diagnosis_conversation_project(
    conversation_id: UUID,
    payload: ProjectConversationMoveRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> DiagnosisConversationResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return move_current_user_diagnosis_conversation_project(
        db,
        user=user,
        conversation_id=conversation_id,
        project_id=payload.project_id,
    )


@router.patch("/conversations/{conversation_id}/pin", response_model=DiagnosisConversationResponse)
def set_diagnosis_conversation_pin(
    conversation_id: UUID,
    payload: DiagnosisConversationPinRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> DiagnosisConversationResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return set_current_user_diagnosis_conversation_pinned(
        db,
        user=user,
        conversation_id=conversation_id,
        pinned=payload.pinned,
    )


@router.patch("/conversations/{conversation_id}/archive", response_model=DiagnosisConversationResponse)
def archive_diagnosis_conversation(
    conversation_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> DiagnosisConversationResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return archive_current_user_diagnosis_conversation(db, user=user, conversation_id=conversation_id)


@router.patch("/conversations/{conversation_id}/restore", response_model=DiagnosisConversationResponse)
def restore_diagnosis_conversation(
    conversation_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> DiagnosisConversationResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return restore_current_user_diagnosis_conversation(db, user=user, conversation_id=conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_diagnosis_conversation(
    conversation_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> None:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_current_user_diagnosis_conversation(db, user=user, conversation_id=conversation_id)


@router.post("/conversations/{conversation_id}/shares", response_model=DiagnosisConversationShareResponse)
def create_diagnosis_conversation_share(
    conversation_id: UUID,
    payload: DiagnosisConversationShareCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DiagnosisConversationShareResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_current_user_diagnosis_conversation_share(
        db,
        user=user,
        settings=settings,
        conversation_id=conversation_id,
        title=payload.title,
        variant=payload.variant,
        content_markdown=payload.content_markdown,
    )


@router.get("/shares/{share_token}", response_model=PublicDiagnosisConversationShareResponse)
def get_public_diagnosis_conversation_share_route(
    share_token: str,
    db: Session = Depends(get_db_session),
) -> PublicDiagnosisConversationShareResponse:
    return get_public_diagnosis_conversation_share(db, share_token=share_token)


@router.post("/conversations", response_model=DiagnosisConversationTurnResponse)
def create_diagnosis_conversation(
    payload: DiagnosisConversationCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DiagnosisConversationTurnResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return _create_diagnosis_turn(
        db=db,
        user=user,
        settings=settings,
        message=payload.message,
        project_id=payload.project_id,
        model_config_id=payload.model_config_id,
    )


@router.post("/conversations/{conversation_id}/messages", response_model=DiagnosisConversationTurnResponse)
def create_diagnosis_conversation_message(
    conversation_id: UUID,
    payload: DiagnosisConversationMessageCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DiagnosisConversationTurnResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return _create_diagnosis_turn(
        db=db,
        user=user,
        settings=settings,
        message=payload.message,
        conversation_id=conversation_id,
        model_config_id=payload.model_config_id,
    )


@router.post("/transcribe", response_model=DiagnosisVoiceTranscriptionResponse)
async def transcribe_diagnosis_voice(
    request: Request,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DiagnosisVoiceTranscriptionResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    content = await audio.read(settings.voice_transcription_max_bytes + 1)
    try:
        transcription = await asyncio.to_thread(
            transcribe_current_user_diagnosis_audio,
            db,
            user=user,
            settings=settings,
            file_name=audio.filename or "voice.webm",
            content_type=audio.content_type or "application/octet-stream",
            content=content,
        )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="语音转写模型配置未完成，请检查 OPENAI_API_KEY 或 CAN_WEN_OPENAI_API_KEY",
        ) from error
    except LLMProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    return DiagnosisVoiceTranscriptionResponse(
        text=transcription.text,
        model=transcription.model,
        provider=transcription.provider,
    )


@router.post("/conversations/multimodal", response_model=DiagnosisConversationTurnResponse)
async def create_multimodal_diagnosis_conversation(
    request: Request,
    message: str = Form(default=""),
    model_config_id: UUID | None = Form(default=None),
    project_id: UUID | None = Form(default=None),
    structured_data: str | None = Form(default=None),
    attachment_ids: list[UUID] | None = Form(default=None),
    attachments: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DiagnosisConversationTurnResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return await _create_multimodal_diagnosis_turn(
        db=db,
        user=user,
        settings=settings,
        message=message,
        attachments=attachments or [],
        attachment_ids=attachment_ids or [],
        structured_data=structured_data,
        project_id=project_id,
        model_config_id=model_config_id,
    )


@router.post("/conversations/{conversation_id}/messages/multimodal", response_model=DiagnosisConversationTurnResponse)
async def create_multimodal_diagnosis_conversation_message(
    conversation_id: UUID,
    request: Request,
    message: str = Form(default=""),
    model_config_id: UUID | None = Form(default=None),
    structured_data: str | None = Form(default=None),
    attachment_ids: list[UUID] | None = Form(default=None),
    attachments: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DiagnosisConversationTurnResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return await _create_multimodal_diagnosis_turn(
        db=db,
        user=user,
        settings=settings,
        message=message,
        conversation_id=conversation_id,
        attachments=attachments or [],
        attachment_ids=attachment_ids or [],
        structured_data=structured_data,
        model_config_id=model_config_id,
    )


@router.patch("/conversations/{conversation_id}/messages/{message_id}", response_model=DiagnosisMessageMutationResponse)
def update_diagnosis_conversation_message(
    conversation_id: UUID,
    message_id: UUID,
    payload: DiagnosisMessageUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> DiagnosisMessageMutationResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_current_user_diagnosis_message(
        db,
        user=user,
        conversation_id=conversation_id,
        message_id=message_id,
        content=payload.content,
    )


@router.delete("/conversations/{conversation_id}/messages/{message_id}", response_model=DiagnosisConversationDetailResponse)
def delete_diagnosis_conversation_message(
    conversation_id: UUID,
    message_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> DiagnosisConversationDetailResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return delete_current_user_diagnosis_message(db, user=user, conversation_id=conversation_id, message_id=message_id)


@router.patch("/conversations/{conversation_id}/messages/{message_id}/feedback", response_model=DiagnosisMessageMutationResponse)
def set_diagnosis_conversation_message_feedback(
    conversation_id: UUID,
    message_id: UUID,
    payload: DiagnosisMessageFeedbackRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> DiagnosisMessageMutationResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return set_current_user_diagnosis_message_feedback(
        db,
        user=user,
        conversation_id=conversation_id,
        message_id=message_id,
        feedback=payload.feedback,
        feedback_reasons=payload.feedback_reasons,
        feedback_detail=payload.feedback_detail,
    )


@router.post("/conversations/{conversation_id}/messages/{message_id}/regenerate", response_model=DiagnosisMessageMutationResponse)
def regenerate_diagnosis_conversation_message(
    conversation_id: UUID,
    message_id: UUID,
    payload: DiagnosisMessageRegenerateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> DiagnosisMessageMutationResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    try:
        return regenerate_current_user_diagnosis_message(
            db,
            user=user,
            settings=settings,
            conversation_id=conversation_id,
            message_id=message_id,
            model_config_id=payload.model_config_id,
        )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="大模型配置未完成，请检查后端环境变量 OPENAI_API_KEY 或 CAN_WEN_OPENAI_API_KEY",
        ) from error
    except LLMProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


@router.post("/chat", response_model=DiagnosisChatResponse)
async def create_diagnosis_chat(
    payload: DiagnosisChatRequest,
    settings: Settings = Depends(get_settings),
) -> DiagnosisChatResponse:
    try:
        reply = await asyncio.to_thread(
            generate_diagnosis_reply,
            settings,
            message=payload.message,
            history=payload.history,
        )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="大模型配置未完成，请检查后端环境变量 OPENAI_API_KEY 或 CAN_WEN_OPENAI_API_KEY",
        ) from error
    except LLMProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    return DiagnosisChatResponse(reply=reply, model=settings.openai_model_id)


def _create_diagnosis_turn(
    *,
    db: Session,
    user,
    settings: Settings,
    message: str,
    conversation_id: UUID | None = None,
    model_config_id: UUID | None = None,
    project_id: UUID | None = None,
) -> DiagnosisConversationTurnResponse:
    try:
        return create_current_user_diagnosis_turn(
            db,
            user=user,
            settings=settings,
            message=message,
            conversation_id=conversation_id,
            model_config_id=model_config_id,
            project_id=project_id,
        )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="大模型配置未完成，请检查后端环境变量 OPENAI_API_KEY 或 CAN_WEN_OPENAI_API_KEY",
        ) from error
    except LLMProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


async def _create_multimodal_diagnosis_turn(
    *,
    db: Session,
    user,
    settings: Settings,
    message: str,
    attachments: list[UploadFile],
    attachment_ids: list[UUID],
    structured_data: str | None,
    conversation_id: UUID | None = None,
    model_config_id: UUID | None = None,
    project_id: UUID | None = None,
) -> DiagnosisConversationTurnResponse:
    try:
        if len(attachments) + len(attachment_ids) > settings.multimodal_attachment_max_count:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"一次最多上传 {settings.multimodal_attachment_max_count} 个问诊材料",
            )

        attachment_uploads: list[DiagnosisAttachmentUpload] = []
        for attachment in attachments:
            content = await attachment.read(settings.multimodal_attachment_max_bytes + 1)
            if len(content) > settings.multimodal_attachment_max_bytes:
                max_mb = max(1, settings.multimodal_attachment_max_bytes // 1024 // 1024)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"单个问诊材料不能超过 {max_mb}MB",
                )
            attachment_uploads.append(
                DiagnosisAttachmentUpload(
                    file_name=attachment.filename or "attachment",
                    content_type=attachment.content_type or "application/octet-stream",
                    content=content,
                )
            )
        return create_current_user_multimodal_diagnosis_turn(
            db,
            user=user,
            settings=settings,
            message=message,
            attachments=attachment_uploads,
            attachment_ids=attachment_ids,
            structured_data=_parse_structured_data(structured_data),
            conversation_id=conversation_id,
            model_config_id=model_config_id,
            project_id=project_id,
        )
    except LLMConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="大模型配置未完成，请检查后端环境变量 OPENAI_API_KEY 或 CAN_WEN_OPENAI_API_KEY",
        ) from error
    except LLMProviderError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error


def _parse_structured_data(raw_value: str | None) -> dict:
    if not raw_value or not raw_value.strip():
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="养殖数据必须是合法 JSON") from error
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="养殖数据必须是 JSON 对象")
    return parsed


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return token.strip()

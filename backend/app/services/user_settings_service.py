from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import desc, or_, select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from app.core.security import now_utc
from app.models import (
    AuthSession,
    CommunityCaseUpdate,
    CommunityBookmarkCollection,
    CommunityBookmarkCollectionItem,
    CommunityComment,
    CommunityDirectMessage,
    CommunityDirectThread,
    CommunityFollow,
    CommunityInteractionEvent,
    CommunityNotification,
    CommunityPost,
    CommunityPostAsset,
    CommunityPostBookmark,
    CommunityPostLike,
    CommunityPostPreference,
    CommunityProfile,
    CommunityReport,
    CommunityTopicFollow,
    CommunityUserBlock,
    Conversation,
    ConversationShare,
    DiagnosisMultimodalAnalysis,
    Farm,
    HusbandryCase,
    HusbandryCaseFollowUp,
    HusbandryDailyRecord,
    HusbandryRecordAsset,
    LLMModelConfig,
    LoginEvent,
    Message,
    Project,
    ProjectShare,
    SilkwormBatch,
    UploadedFile,
    User,
    UserIdentity,
    UserSettings,
)
from app.schemas.user_settings import AuthSessionResponse, UserSettingsResponse
from app.services.auth_service import get_current_auth_session
from app.services.storage_service import delete_object_file, is_storage_configured


DEFAULT_USER_PREFERENCES: dict[str, Any] = {
    "knowledge_graph_enabled": True,
    "rag_enabled": True,
    "long_term_memory_enabled": True,
    "memory_agent_write_enabled": True,
    "in_app_notifications": True,
    "upload_notifications": True,
    "model_notifications": True,
    "husbandry_health_notifications": True,
    "husbandry_temperature_min": 20,
    "husbandry_temperature_max": 30,
    "husbandry_humidity_max": 85,
    "auto_generate_title": True,
    "send_shortcut": "enter",
    "show_model_status": True,
    "image_compression": "balanced",
    "auto_retry_upload": True,
    "draft_attachment_retention_hours": 24,
    "reduced_motion": False,
    "high_contrast": False,
    "locale": "zh-CN",
    "theme": "light",
    "font_size": "standard",
}

_BOOLEAN_KEYS = {
    "knowledge_graph_enabled",
    "rag_enabled",
    "long_term_memory_enabled",
    "memory_agent_write_enabled",
    "in_app_notifications",
    "upload_notifications",
    "model_notifications",
    "husbandry_health_notifications",
    "auto_generate_title",
    "show_model_status",
    "auto_retry_upload",
    "reduced_motion",
    "high_contrast",
}
_ENUM_VALUES = {
    "send_shortcut": {"enter", "ctrl_enter"},
    "image_compression": {"balanced", "high_quality"},
    "locale": {"zh-CN", "en-US"},
    "theme": {"light", "dark"},
    "font_size": {"small", "standard", "large", "extra"},
}


def get_current_user_settings(db: Session, *, access_token: str) -> UserSettingsResponse:
    session = get_current_auth_session(db, access_token=access_token)
    record = _ensure_settings_record(db, session.user)
    return UserSettingsResponse(preferences=_merged_preferences(record.preferences), updated_at=record.updated_at)


def update_current_user_settings(
    db: Session,
    *,
    access_token: str,
    preferences: dict[str, Any],
) -> UserSettingsResponse:
    session = get_current_auth_session(db, access_token=access_token)
    validated = _validate_preference_updates(preferences)
    record = _ensure_settings_record(db, session.user)
    next_preferences = {**_merged_preferences(record.preferences), **validated}
    if next_preferences["husbandry_temperature_min"] >= next_preferences["husbandry_temperature_max"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="温度下限必须小于上限")
    record.preferences = next_preferences
    record.updated_at = now_utc()
    session.last_used_at = now_utc()

    if "locale" in validated:
        session.user.locale = validated["locale"]
        session.user.updated_at = now_utc()

    db.commit()
    db.refresh(record)
    return UserSettingsResponse(preferences=_merged_preferences(record.preferences), updated_at=record.updated_at)


def list_current_user_sessions(db: Session, *, access_token: str) -> list[AuthSessionResponse]:
    current_session = get_current_auth_session(db, access_token=access_token)
    sessions = db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == current_session.user_id, AuthSession.status == "active")
        .order_by(desc(AuthSession.last_used_at), desc(AuthSession.created_at))
    ).all()
    return [_session_response(item, current_session.id) for item in sessions]


def revoke_current_user_session(
    db: Session,
    *,
    access_token: str,
    session_id: str,
) -> None:
    current_session = get_current_auth_session(db, access_token=access_token)
    if str(current_session.id) == session_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请使用退出登录结束当前设备会话")

    session = db.scalar(
        select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == current_session.user_id,
            AuthSession.status == "active",
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备会话不存在或已退出")

    _revoke_session(db, session)
    db.commit()


def revoke_other_current_user_sessions(db: Session, *, access_token: str) -> int:
    current_session = get_current_auth_session(db, access_token=access_token)
    sessions = db.scalars(
        select(AuthSession).where(
            AuthSession.user_id == current_session.user_id,
            AuthSession.status == "active",
            AuthSession.id != current_session.id,
        )
    ).all()
    for session in sessions:
        _revoke_session(db, session)
    db.commit()
    return len(sessions)


def export_current_user_data(db: Session, *, access_token: str) -> dict[str, Any]:
    current_session = get_current_auth_session(db, access_token=access_token)
    user = current_session.user
    settings = _ensure_settings_record(db, user)
    projects = list(db.scalars(select(Project).where(Project.owner_id == user.id).order_by(desc(Project.updated_at))))
    conversations = list(db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(desc(Conversation.updated_at))))
    farms = list(db.scalars(select(Farm).where(Farm.owner_id == user.id).order_by(desc(Farm.updated_at))))
    cases = list(db.scalars(select(HusbandryCase).where(HusbandryCase.owner_id == user.id).order_by(desc(HusbandryCase.updated_at))))
    posts = list(db.scalars(select(CommunityPost).where(CommunityPost.author_id == user.id).order_by(desc(CommunityPost.updated_at))))

    project_ids = [project.id for project in projects]
    conversation_ids = [conversation.id for conversation in conversations]
    farm_ids = [farm.id for farm in farms]
    case_ids = [case.id for case in cases]
    post_ids = [post.id for post in posts]
    batches = list(db.scalars(select(SilkwormBatch).where(SilkwormBatch.farm_id.in_(farm_ids)))) if farm_ids else []
    batch_ids = [batch.id for batch in batches]

    return {
        "exported_at": now_utc().isoformat(),
        "profile": {
            "id": str(user.id),
            "display_name": user.display_name,
            "username": user.username,
            "role": user.role,
            "locale": user.locale,
            "timezone": user.timezone,
            "created_at": _iso(user.created_at),
        },
        "settings": _merged_preferences(settings.preferences),
        "identities": _export_rows(db.scalars(select(UserIdentity).where(UserIdentity.user_id == user.id))),
        "account_activity": _export_rows(
            db.scalars(select(LoginEvent).where(LoginEvent.user_id == user.id).order_by(LoginEvent.created_at)),
            exclude={"ip_address", "user_agent"},
        ),
        "projects": _export_rows(projects),
        "project_shares": _export_rows(db.scalars(select(ProjectShare).where(ProjectShare.owner_id == user.id))),
        "conversations": _export_rows(conversations),
        "conversation_shares": _export_rows(db.scalars(select(ConversationShare).where(ConversationShare.owner_id == user.id))),
        "messages": _export_rows(
            db.scalars(select(Message).where(Message.conversation_id.in_(conversation_ids)).order_by(Message.created_at))
            if conversation_ids
            else [],
        ),
        "multimodal_analyses": _export_rows(
            db.scalars(select(DiagnosisMultimodalAnalysis).where(DiagnosisMultimodalAnalysis.conversation_id.in_(conversation_ids)))
            if conversation_ids
            else [],
        ),
        "attachments": _export_rows(
            db.scalars(select(UploadedFile).where(UploadedFile.user_id == user.id).order_by(UploadedFile.created_at)),
            exclude={"storage_key", "storage_url", "checksum"},
        ),
        "model_configs": _export_rows(
            db.scalars(select(LLMModelConfig).where(LLMModelConfig.user_id == user.id)),
            exclude={"api_key_ciphertext"},
        ),
        "husbandry": {
            "farms": _export_rows(farms),
            "batches": _export_rows(batches),
            "daily_records": _export_rows(
                db.scalars(select(HusbandryDailyRecord).where(HusbandryDailyRecord.batch_id.in_(batch_ids)).order_by(HusbandryDailyRecord.record_date))
                if batch_ids
                else [],
            ),
            "cases": _export_rows(cases),
            "follow_ups": _export_rows(
                db.scalars(select(HusbandryCaseFollowUp).where(HusbandryCaseFollowUp.case_id.in_(case_ids)).order_by(HusbandryCaseFollowUp.observed_on))
                if case_ids
                else [],
            ),
            "record_assets": _export_rows(
                db.scalars(select(HusbandryRecordAsset).where(HusbandryRecordAsset.owner_id == user.id).order_by(HusbandryRecordAsset.created_at))
            ),
        },
        "community": {
            "profile": _export_model(db.get(CommunityProfile, user.id)) if db.get(CommunityProfile, user.id) else None,
            "posts": _export_rows(posts),
            "post_assets": _export_rows(
                db.scalars(select(CommunityPostAsset).where(CommunityPostAsset.post_id.in_(post_ids))) if post_ids else [],
            ),
            "comments": _export_rows(db.scalars(select(CommunityComment).where(CommunityComment.author_id == user.id))),
            "case_updates": _export_rows(db.scalars(select(CommunityCaseUpdate).where(CommunityCaseUpdate.author_id == user.id))),
            "likes": _export_rows(db.scalars(select(CommunityPostLike).where(CommunityPostLike.user_id == user.id))),
            "bookmarks": _export_rows(db.scalars(select(CommunityPostBookmark).where(CommunityPostBookmark.user_id == user.id))),
            "bookmark_collections": _export_rows(
                db.scalars(select(CommunityBookmarkCollection).where(CommunityBookmarkCollection.owner_id == user.id))
            ),
            "bookmark_collection_items": _export_rows(
                db.scalars(
                    select(CommunityBookmarkCollectionItem)
                    .join(CommunityBookmarkCollection, CommunityBookmarkCollection.id == CommunityBookmarkCollectionItem.collection_id)
                    .where(CommunityBookmarkCollection.owner_id == user.id)
                )
            ),
            "preferences": _export_rows(db.scalars(select(CommunityPostPreference).where(CommunityPostPreference.user_id == user.id))),
            "follows": _export_rows(
                db.scalars(select(CommunityFollow).where(or_(CommunityFollow.follower_id == user.id, CommunityFollow.followed_id == user.id)))
            ),
            "blocks": _export_rows(
                db.scalars(select(CommunityUserBlock).where(or_(CommunityUserBlock.blocker_id == user.id, CommunityUserBlock.blocked_id == user.id)))
            ),
            "topic_follows": _export_rows(db.scalars(select(CommunityTopicFollow).where(CommunityTopicFollow.user_id == user.id))),
            "interaction_events": _export_rows(db.scalars(select(CommunityInteractionEvent).where(CommunityInteractionEvent.user_id == user.id))),
            "direct_threads": _export_rows(
                db.scalars(
                    select(CommunityDirectThread).where(
                        or_(
                            CommunityDirectThread.participant_one_id == user.id,
                            CommunityDirectThread.participant_two_id == user.id,
                        )
                    )
                )
            ),
            "direct_messages": _export_rows(
                db.scalars(
                    select(CommunityDirectMessage).where(
                        or_(CommunityDirectMessage.sender_id == user.id, CommunityDirectMessage.recipient_id == user.id)
                    )
                )
            ),
            "notifications": _export_rows(db.scalars(select(CommunityNotification).where(CommunityNotification.user_id == user.id))),
            "reports": _export_rows(db.scalars(select(CommunityReport).where(CommunityReport.reporter_id == user.id))),
        },
    }


def delete_current_user_account(
    db: Session,
    *,
    access_token: str,
    confirmation: str,
) -> None:
    if confirmation.strip().upper() != "DELETE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入 DELETE 确认删除账户")

    current_session = get_current_auth_session(db, access_token=access_token)
    user = current_session.user
    object_keys = list(
        dict.fromkeys(
            db.scalars(select(UploadedFile.storage_key).where(UploadedFile.user_id == user.id, UploadedFile.deleted_at.is_(None)))
        )
    )
    if object_keys and not is_storage_configured():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="附件存储尚未配置，无法安全完成账户删除")
    for object_key in object_keys:
        delete_object_file(object_key=object_key, failure_detail="账户附件删除失败，请稍后重试")
    events = db.scalars(select(LoginEvent).where(LoginEvent.user_id == user.id)).all()
    for event in events:
        db.delete(event)
    db.delete(user)
    db.commit()


def _ensure_settings_record(db: Session, user: User) -> UserSettings:
    record = db.get(UserSettings, user.id)
    if record is not None:
        return record

    record = UserSettings(user_id=user.id, preferences=DEFAULT_USER_PREFERENCES.copy())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _merged_preferences(preferences: dict[str, Any] | None) -> dict[str, Any]:
    return {**DEFAULT_USER_PREFERENCES, **(preferences or {})}


def _validate_preference_updates(preferences: dict[str, Any]) -> dict[str, Any]:
    unknown_keys = set(preferences) - set(DEFAULT_USER_PREFERENCES)
    if unknown_keys:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"不支持的设置项：{', '.join(sorted(unknown_keys))}",
        )

    validated: dict[str, Any] = {}
    for key, value in preferences.items():
        if key in _BOOLEAN_KEYS:
            if not isinstance(value, bool):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{key} 必须为布尔值")
            validated[key] = value
            continue
        if key in _ENUM_VALUES:
            if value not in _ENUM_VALUES[key]:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{key} 的值无效")
            validated[key] = value
            continue
        if key == "draft_attachment_retention_hours":
            if not isinstance(value, int) or isinstance(value, bool) or value not in {24, 72, 168}:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="草稿附件保留时间无效")
            validated[key] = value
            continue
        if key in {"husbandry_temperature_min", "husbandry_temperature_max"}:
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 45:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{key} 的值无效")
            validated[key] = value
            continue
        if key == "husbandry_humidity_max":
            if not isinstance(value, int) or isinstance(value, bool) or not 40 <= value <= 100:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="养殖湿度阈值无效")
            validated[key] = value
    minimum = validated.get("husbandry_temperature_min")
    maximum = validated.get("husbandry_temperature_max")
    if minimum is not None and maximum is not None and minimum >= maximum:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="温度下限必须小于上限")
    return validated


def _session_response(session: AuthSession, current_session_id: Any) -> AuthSessionResponse:
    return AuthSessionResponse(
        id=str(session.id),
        device_name=session.device_name or _device_name_from_user_agent(session.user_agent),
        last_used_at=session.last_used_at,
        created_at=session.created_at,
        expires_at=session.expires_at,
        is_current=session.id == current_session_id,
    )


def _device_name_from_user_agent(user_agent: str | None) -> str:
    if not user_agent:
        return "未知设备"
    if "Windows" in user_agent:
        return "Windows 浏览器"
    if "Macintosh" in user_agent:
        return "Mac 浏览器"
    if "iPhone" in user_agent:
        return "iPhone"
    if "Android" in user_agent:
        return "Android 设备"
    return "浏览器设备"


def _revoke_session(db: Session, session: AuthSession) -> None:
    current_time = now_utc()
    session.status = "revoked"
    session.revoked_at = current_time
    session.updated_at = current_time
    db.add(LoginEvent(user_id=session.user_id, session_id=session.id, event_type="session_revoked"))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _export_rows(rows: Any, *, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    return [_export_model(row, exclude=exclude) for row in rows]


def _export_model(model: Any, *, exclude: set[str] | None = None) -> dict[str, Any]:
    if model is None:
        return {}
    excluded = exclude or set()
    result: dict[str, Any] = {}
    for attribute in inspect(model).mapper.column_attrs:
        key = attribute.key
        if key in excluded:
            continue
        export_key = "metadata" if key == "metadata_" else key
        result[export_key] = _export_value(getattr(model, key))
    return result


def _export_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _export_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_export_value(item) for item in value]
    return value

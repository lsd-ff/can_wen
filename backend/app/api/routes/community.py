from __future__ import annotations

import asyncio
import json
from queue import Empty

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.community import (
    CommunityCommentCreateRequest,
    CommunityCommentListResponse,
    CommunityCommentResponse,
    CommunityCommentUpdateRequest,
    CommunityCaseUpdateCreateRequest,
    CommunityCaseUpdateResponse,
    CommunityCreatorOverviewResponse,
    CommunityDirectMessageCreateRequest,
    CommunityDirectMessageListResponse,
    CommunityDirectMessageResponse,
    CommunityDirectThreadListResponse,
    CommunityConversationDraftCreateRequest,
    CommunityHusbandryDraftCreateRequest,
    CommunityNotificationListResponse,
    CommunityPostCreateRequest,
    CommunityPostListResponse,
    CommunityPostResponse,
    CommunityPostUpdateRequest,
    CommunityProfileDetailResponse,
    CommunityProfileUpdateRequest,
    CommunityRelationshipListResponse,
    CommunityAuthorResponse,
    CommunityBookmarkCollectionCreateRequest,
    CommunityBookmarkCollectionDetailResponse,
    CommunityBookmarkCollectionListResponse,
    CommunityBookmarkCollectionResponse,
    CommunityBookmarkCollectionUpdateRequest,
    CommunityBlockedUserListResponse,
    CommunityReportCreateRequest,
    CommunitySaveToHusbandryRequest,
    CommunitySearchResponse,
    CommunityTagResponse,
    CommunityUploadedFileResponse,
)
from app.services.auth_service import get_current_user
from app.services.community_service import (
    create_community_comment,
    create_community_bookmark_collection,
    clear_community_view_history,
    add_community_case_update,
    accept_community_answer,
    create_community_post,
    create_community_post_draft_from_conversation,
    create_community_post_draft_from_husbandry_case,
    create_community_report,
    delete_community_comment,
    delete_community_bookmark_collection,
    delete_community_post,
    get_community_post,
    get_community_profile,
    get_community_profile_detail,
    get_community_creator_overview,
    get_community_bookmark_collection_detail,
    get_community_relationships,
    list_community_comments,
    list_community_bookmark_collections,
    list_community_blocked_users,
    list_community_notifications,
    list_community_direct_messages,
    list_community_direct_threads,
    list_community_posts,
    list_community_tags,
    mark_community_notifications_read,
    hide_community_post,
    reset_community_recommendations,
    save_community_post_to_husbandry,
    save_community_attachments,
    search_community,
    toggle_community_comment_like,
    toggle_community_bookmark_collection_post,
    toggle_community_follow,
    toggle_community_user_block,
    toggle_community_topic_follow,
    toggle_community_post_bookmark,
    toggle_community_post_like,
    update_community_comment,
    update_community_bookmark_collection,
    update_community_post,
    update_community_profile,
    send_community_direct_message,
)
from app.services.community_events import community_event_broker


router = APIRouter(prefix="/community", tags=["community"])


@router.post("/uploads", response_model=list[CommunityUploadedFileResponse], status_code=status.HTTP_201_CREATED)
async def upload_community_files(
    request: Request,
    attachments: list[UploadFile] = File(...),
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> list[CommunityUploadedFileResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    if not attachments:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择至少一个素材")
    if len(attachments) > settings.multimodal_attachment_max_count:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="一次最多上传 6 个素材")
    prepared_attachments: list[tuple[str, str, bytes]] = []
    for attachment in attachments:
        content = await attachment.read()
        if len(content) > settings.multimodal_attachment_max_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="单个素材不能超过 80MB")
        prepared_attachments.append((attachment.filename or "attachment", attachment.content_type or "", content))
    return save_community_attachments(db, user=user, attachments=prepared_attachments)


@router.get("/feed", response_model=CommunityPostListResponse)
def get_feed(
    request: Request,
    tab: str = Query(default="recommended", pattern="^(recommended|following|topics|latest|bookmarked|liked|history|mine|drafts)$"),
    q: str | None = Query(default=None, max_length=100),
    tag: str | None = Query(default=None, max_length=32),
    post_type: str | None = Query(default=None, pattern="^(experience|case|question|reference|announcement)$"),
    question_status: str | None = Query(default=None, pattern="^(open|resolved)$"),
    region: str | None = Query(default=None, max_length=80),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=40),
    db: Session = Depends(get_db_session),
) -> CommunityPostListResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_community_posts(
        db,
        user=user,
        tab=tab,
        query=q,
        tag=tag,
        post_type=post_type,
        question_status=question_status,
        region=region,
        offset=offset,
        limit=limit,
    )


@router.get("/search", response_model=CommunitySearchResponse)
def search_community_content(
    request: Request,
    q: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db_session),
) -> CommunitySearchResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return search_community(db, user=user, query=q)


@router.get("/tags", response_model=list[CommunityTagResponse])
def get_tags(
    request: Request,
    limit: int = Query(default=20, ge=1, le=60),
    db: Session = Depends(get_db_session),
) -> list[CommunityTagResponse]:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_community_tags(db, user=user, limit=limit)


@router.post("/tags/{tag_id}/follow", response_model=CommunityTagResponse)
def follow_topic(tag_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> CommunityTagResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return toggle_community_topic_follow(db, user=user, tag_id=tag_id)


@router.get("/notifications", response_model=CommunityNotificationListResponse)
def get_notifications(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=60),
    db: Session = Depends(get_db_session),
) -> CommunityNotificationListResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_community_notifications(db, user=user, offset=offset, limit=limit)


@router.get("/events")
async def stream_community_events(request: Request, db: Session = Depends(get_db_session)) -> StreamingResponse:
    """Push lightweight refresh signals while durable data stays in the API."""

    user = get_current_user(db, access_token=_bearer_token(request))
    subscription = community_event_broker.subscribe(user.id)

    async def event_stream():
        try:
            yield "event: ready\ndata: {}\n\n"
            while not await request.is_disconnected():
                try:
                    event = await asyncio.to_thread(subscription.get, True, 20)
                except Empty:
                    yield ": keepalive\n\n"
                    continue
                yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            community_event_broker.unsubscribe(user.id, subscription)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/notifications/read", status_code=status.HTTP_204_NO_CONTENT)
def read_notifications(request: Request, db: Session = Depends(get_db_session)) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    mark_community_notifications_read(db, user=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_view_history(request: Request, db: Session = Depends(get_db_session)) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    clear_community_view_history(db, user=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/recommendations", status_code=status.HTTP_204_NO_CONTENT)
def reset_recommendations(request: Request, db: Session = Depends(get_db_session)) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    reset_community_recommendations(db, user=user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/collections", response_model=CommunityBookmarkCollectionListResponse)
def get_bookmark_collections(
    request: Request,
    post_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db_session),
) -> CommunityBookmarkCollectionListResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_community_bookmark_collections(db, user=user, post_id=post_id)


@router.post("/collections", response_model=CommunityBookmarkCollectionResponse, status_code=status.HTTP_201_CREATED)
def create_bookmark_collection(
    payload: CommunityBookmarkCollectionCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityBookmarkCollectionResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_community_bookmark_collection(db, user=user, payload=payload)


@router.get("/collections/{collection_id}", response_model=CommunityBookmarkCollectionDetailResponse)
def get_bookmark_collection(
    collection_id: UUID,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=60),
    db: Session = Depends(get_db_session),
) -> CommunityBookmarkCollectionDetailResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return get_community_bookmark_collection_detail(db, user=user, collection_id=collection_id, offset=offset, limit=limit)


@router.patch("/collections/{collection_id}", response_model=CommunityBookmarkCollectionResponse)
def patch_bookmark_collection(
    collection_id: UUID,
    payload: CommunityBookmarkCollectionUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityBookmarkCollectionResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_community_bookmark_collection(db, user=user, collection_id=collection_id, payload=payload)


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_bookmark_collection(collection_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_community_bookmark_collection(db, user=user, collection_id=collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/collections/{collection_id}/posts/{post_id}", response_model=CommunityBookmarkCollectionResponse)
def toggle_bookmark_collection_post(
    collection_id: UUID,
    post_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityBookmarkCollectionResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return toggle_community_bookmark_collection_post(db, user=user, collection_id=collection_id, post_id=post_id)


@router.post("/users/{user_id}/follow", response_model=dict)
def follow_user(user_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> dict:
    user = get_current_user(db, access_token=_bearer_token(request))
    author = toggle_community_follow(db, user=user, target_user_id=user_id)
    return author.model_dump()


@router.get("/users/{user_id}/profile", response_model=CommunityAuthorResponse)
def get_user_profile(user_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> CommunityAuthorResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return get_community_profile(db, user=user, target_user_id=user_id)


@router.get("/users/{user_id}/posts", response_model=CommunityProfileDetailResponse)
def get_user_posts(
    user_id: UUID,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=12, ge=1, le=40),
    db: Session = Depends(get_db_session),
) -> CommunityProfileDetailResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return get_community_profile_detail(db, user=user, target_user_id=user_id, offset=offset, limit=limit)


@router.get("/users/{user_id}/relationships", response_model=CommunityRelationshipListResponse)
def get_user_relationships(
    user_id: UUID,
    request: Request,
    relationship_type: str = Query(default="followers", pattern="^(followers|following)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=60),
    db: Session = Depends(get_db_session),
) -> CommunityRelationshipListResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return get_community_relationships(
        db,
        user=user,
        target_user_id=user_id,
        relationship_type=relationship_type,
        offset=offset,
        limit=limit,
    )


@router.get("/creator/overview", response_model=CommunityCreatorOverviewResponse)
def get_creator_overview(request: Request, db: Session = Depends(get_db_session)) -> CommunityCreatorOverviewResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return get_community_creator_overview(db, user=user)


@router.put("/profile", response_model=CommunityAuthorResponse)
def put_profile(
    payload: CommunityProfileUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityAuthorResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_community_profile(db, user=user, payload=payload)


@router.get("/blocked-users", response_model=CommunityBlockedUserListResponse)
def get_blocked_users(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=60),
    db: Session = Depends(get_db_session),
) -> CommunityBlockedUserListResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_community_blocked_users(db, user=user, offset=offset, limit=limit)


@router.post("/users/{user_id}/block", response_model=dict)
def block_user(user_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> dict:
    user = get_current_user(db, access_token=_bearer_token(request))
    return toggle_community_user_block(db, user=user, target_user_id=user_id)


@router.get("/direct/threads", response_model=CommunityDirectThreadListResponse)
def get_direct_threads(request: Request, db: Session = Depends(get_db_session)) -> CommunityDirectThreadListResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_community_direct_threads(db, user=user)


@router.get("/direct/threads/{thread_id}/messages", response_model=CommunityDirectMessageListResponse)
def get_direct_messages(
    thread_id: UUID,
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=80, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> CommunityDirectMessageListResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_community_direct_messages(db, user=user, thread_id=thread_id, offset=offset, limit=limit)


@router.post("/users/{user_id}/direct-messages", response_model=CommunityDirectMessageResponse, status_code=status.HTTP_201_CREATED)
def create_direct_message(
    user_id: UUID,
    payload: CommunityDirectMessageCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityDirectMessageResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return send_community_direct_message(db, user=user, target_user_id=user_id, content=payload.content)


@router.post("/posts/from-conversation/{conversation_id}/draft", response_model=CommunityPostResponse, status_code=status.HTTP_201_CREATED)
def create_post_draft_from_conversation(
    conversation_id: UUID,
    payload: CommunityConversationDraftCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityPostResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_community_post_draft_from_conversation(
        db,
        user=user,
        conversation_id=conversation_id,
        title=payload.title,
        include_attachment_ids=payload.include_attachment_ids,
    )


@router.post("/posts/from-husbandry-case/{case_id}/draft", response_model=CommunityPostResponse, status_code=status.HTTP_201_CREATED)
def create_post_draft_from_case(
    case_id: UUID,
    payload: CommunityHusbandryDraftCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityPostResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_community_post_draft_from_husbandry_case(db, user=user, case_id=case_id, title=payload.title)


@router.post("/posts", response_model=CommunityPostResponse, status_code=status.HTTP_201_CREATED)
def create_post(
    payload: CommunityPostCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityPostResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_community_post(db, user=user, payload=payload)


@router.get("/posts/{post_id}", response_model=CommunityPostResponse)
def get_post(post_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> CommunityPostResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return get_community_post(db, user=user, post_id=post_id)


@router.patch("/posts/{post_id}", response_model=CommunityPostResponse)
def patch_post(
    post_id: UUID,
    payload: CommunityPostUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityPostResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_community_post(db, user=user, post_id=post_id, payload=payload)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_post(post_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_community_post(db, user=user, post_id=post_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/posts/{post_id}/like", response_model=CommunityPostResponse)
def toggle_post_like(post_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> CommunityPostResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return toggle_community_post_like(db, user=user, post_id=post_id)


@router.post("/posts/{post_id}/bookmark", response_model=CommunityPostResponse)
def toggle_post_bookmark(post_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> CommunityPostResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return toggle_community_post_bookmark(db, user=user, post_id=post_id)


@router.post("/posts/{post_id}/not-interested", response_model=dict)
def mark_post_not_interested(post_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> dict:
    user = get_current_user(db, access_token=_bearer_token(request))
    return hide_community_post(db, user=user, post_id=post_id)


@router.post("/posts/{post_id}/answers/{comment_id}/accept", response_model=CommunityPostResponse)
def accept_answer(
    post_id: UUID,
    comment_id: UUID,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityPostResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return accept_community_answer(db, user=user, post_id=post_id, comment_id=comment_id)


@router.post("/posts/{post_id}/case-updates", response_model=CommunityCaseUpdateResponse, status_code=status.HTTP_201_CREATED)
def add_case_update(
    post_id: UUID,
    payload: CommunityCaseUpdateCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityCaseUpdateResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return add_community_case_update(
        db,
        user=user,
        post_id=post_id,
        occurred_on=payload.occurred_on,
        outcome_status=payload.outcome_status,
        content=payload.content,
        metrics=payload.metrics,
    )


@router.post("/posts/{post_id}/save-to-husbandry", response_model=dict, status_code=status.HTTP_201_CREATED)
def save_to_husbandry(
    post_id: UUID,
    payload: CommunitySaveToHusbandryRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> dict:
    user = get_current_user(db, access_token=_bearer_token(request))
    return save_community_post_to_husbandry(
        db,
        user=user,
        post_id=post_id,
        farm_id=payload.farm_id,
        batch_id=payload.batch_id,
    )


@router.get("/posts/{post_id}/comments", response_model=CommunityCommentListResponse)
def get_comments(
    post_id: UUID,
    request: Request,
    sort: str = Query(default="top", pattern="^(top|latest)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=60, ge=1, le=100),
    db: Session = Depends(get_db_session),
) -> CommunityCommentListResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return list_community_comments(db, user=user, post_id=post_id, sort=sort, offset=offset, limit=limit)


@router.post("/posts/{post_id}/comments", response_model=CommunityCommentResponse, status_code=status.HTTP_201_CREATED)
def add_comment(
    post_id: UUID,
    payload: CommunityCommentCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityCommentResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return create_community_comment(
        db,
        user=user,
        post_id=post_id,
        content=payload.content,
        parent_comment_id=payload.parent_comment_id,
    )


@router.post("/posts/{post_id}/reports", status_code=status.HTTP_204_NO_CONTENT)
def report_post(
    post_id: UUID,
    payload: CommunityReportCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    create_community_report(
        db,
        user=user,
        post_id=post_id,
        target_type=payload.target_type,
        reason=payload.reason,
        detail=payload.detail,
        comment_id=payload.comment_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/comments/{comment_id}", response_model=CommunityCommentResponse)
def patch_comment(
    comment_id: UUID,
    payload: CommunityCommentUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
) -> CommunityCommentResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return update_community_comment(db, user=user, comment_id=comment_id, content=payload.content)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_comment(comment_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> Response:
    user = get_current_user(db, access_token=_bearer_token(request))
    delete_community_comment(db, user=user, comment_id=comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/comments/{comment_id}/like", response_model=CommunityCommentResponse)
def toggle_comment_like(comment_id: UUID, request: Request, db: Session = Depends(get_db_session)) -> CommunityCommentResponse:
    user = get_current_user(db, access_token=_bearer_token(request))
    return toggle_community_comment_like(db, user=user, comment_id=comment_id)


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    return token.strip()

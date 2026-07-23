from __future__ import annotations

import hashlib
import mimetypes
import re
import uuid
from collections.abc import Iterable
from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import case, delete, desc, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import now_utc
from app.models import (
    CommunityComment,
    CommunityCommentLike,
    CommunityDirectMessage,
    CommunityDirectThread,
    CommunityFollow,
    CommunityCaseUpdate,
    CommunityBookmarkCollection,
    CommunityBookmarkCollectionItem,
    CommunityInteractionEvent,
    CommunityNotification,
    CommunityPost,
    CommunityPostAsset,
    CommunityPostBookmark,
    CommunityPostLike,
    CommunityPostPreference,
    CommunityPostTag,
    CommunityReport,
    CommunityProfile,
    CommunityTag,
    CommunityTopicFollow,
    CommunityUserBlock,
    Conversation,
    Farm,
    HusbandryCase,
    Message,
    MessageFile,
    SilkwormBatch,
    UploadedFile,
    User,
)
from app.schemas.community import (
    CommunityAssetResponse,
    CommunityAuthorResponse,
    CommunityBookmarkCollectionCreateRequest,
    CommunityBookmarkCollectionDetailResponse,
    CommunityBookmarkCollectionListResponse,
    CommunityBookmarkCollectionResponse,
    CommunityBookmarkCollectionUpdateRequest,
    CommunityBlockedUserListResponse,
    CommunityCaseUpdateResponse,
    CommunityCreatorOverviewResponse,
    CommunityCommentListResponse,
    CommunityCommentResponse,
    CommunityDirectMessageListResponse,
    CommunityDirectMessageResponse,
    CommunityDirectThreadListResponse,
    CommunityDirectThreadResponse,
    CommunityNotificationListResponse,
    CommunityNotificationResponse,
    CommunityPostCreateRequest,
    CommunityPostListResponse,
    CommunityPostResponse,
    CommunityPostUpdateRequest,
    CommunityProfileDetailResponse,
    CommunityProfileUpdateRequest,
    CommunityRelationshipListResponse,
    CommunitySearchResponse,
    CommunityTagResponse,
    CommunityUploadedFileResponse,
)
from app.services.community_events import community_event_broker
from app.services.storage_service import upload_object_file


COMMUNITY_DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".txt", ".md", ".markdown",
    ".json", ".xml", ".html", ".htm", ".rtf", ".log",
}
COMMUNITY_DOCUMENT_MIME_TYPES = {
    "application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint", "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv", "text/plain", "text/markdown", "application/json", "application/xml", "text/xml", "text/html", "application/rtf",
}
COMMUNITY_SENSITIVE_CONTACT_PATTERNS = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?i)(?:微信|微s*信|vx|v信|wechat)\s*[:：]?\s*[a-z][a-z0-9_-]{4,24}"),
)


def list_community_posts(
    db: Session,
    *,
    user: User,
    tab: str = "recommended",
    query: str | None = None,
    tag: str | None = None,
    post_type: str | None = None,
    question_status: str | None = None,
    region: str | None = None,
    offset: int = 0,
    limit: int = 20,
) -> CommunityPostListResponse:
    normalized_query = " ".join((query or "").split())
    normalized_tag = " ".join((tag or "").strip().lstrip("#").split())
    normalized_region = " ".join((region or "").split())
    statement = select(CommunityPost)
    recommendation_tag_ids: set[UUID] = set()

    if tab == "mine":
        statement = statement.where(CommunityPost.author_id == user.id, CommunityPost.status == "published")
    elif tab == "drafts":
        statement = statement.where(CommunityPost.author_id == user.id, CommunityPost.status == "draft")
    elif tab == "bookmarked":
        statement = statement.join(CommunityPostBookmark).where(
            CommunityPostBookmark.user_id == user.id,
            CommunityPost.status == "published",
        )
    elif tab == "liked":
        statement = statement.join(CommunityPostLike).where(
            CommunityPostLike.user_id == user.id,
            CommunityPost.status == "published",
        )
    elif tab == "history":
        statement = (
            statement.join(CommunityInteractionEvent)
            .where(
                CommunityInteractionEvent.user_id == user.id,
                CommunityInteractionEvent.event_type == "view",
                CommunityPost.status == "published",
            )
            .group_by(CommunityPost.id)
        )
    else:
        statement = statement.where(CommunityPost.status == "published")
        following_author_ids = select(CommunityFollow.followed_id).where(CommunityFollow.follower_id == user.id)
        statement = statement.where(
            or_(
                CommunityPost.visibility == "public",
                CommunityPost.author_id == user.id,
                CommunityPost.author_id.in_(following_author_ids),
            )
        )
        if tab == "following":
            statement = statement.join(CommunityFollow, CommunityFollow.followed_id == CommunityPost.author_id).where(
                CommunityFollow.follower_id == user.id
            )
        elif tab == "topics":
            followed_topic_posts = (
                select(CommunityPostTag.post_id)
                .join(CommunityTopicFollow, CommunityTopicFollow.tag_id == CommunityPostTag.tag_id)
                .where(CommunityTopicFollow.user_id == user.id)
            )
            statement = statement.where(CommunityPost.id.in_(followed_topic_posts))

        blocked_authors = select(CommunityUserBlock.blocked_id).where(CommunityUserBlock.blocker_id == user.id)
        blocked_viewers = select(CommunityUserBlock.blocker_id).where(CommunityUserBlock.blocked_id == user.id)
        hidden_posts = select(CommunityPostPreference.post_id).where(CommunityPostPreference.user_id == user.id)
        statement = statement.where(
            CommunityPost.author_id.not_in(blocked_authors),
            CommunityPost.author_id.not_in(blocked_viewers),
            CommunityPost.id.not_in(hidden_posts),
        )

    if post_type:
        statement = statement.where(CommunityPost.post_type == post_type)
    if question_status:
        statement = statement.where(CommunityPost.post_type == "question", CommunityPost.question_status == question_status)
    if normalized_region:
        statement = statement.join(CommunityProfile, CommunityProfile.user_id == CommunityPost.author_id).where(
            CommunityProfile.region.ilike(f"%{normalized_region}%")
        )

    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(or_(CommunityPost.title.ilike(pattern), CommunityPost.content_markdown.ilike(pattern)))

    if normalized_tag:
        statement = (
            statement.join(CommunityPostTag, CommunityPostTag.post_id == CommunityPost.id)
            .join(CommunityTag, CommunityTag.id == CommunityPostTag.tag_id)
            .where(CommunityTag.name == normalized_tag)
        )

    if tab == "recommended":
        preferred_tag_ids = list(
            db.scalars(
                select(CommunityPostTag.tag_id)
                .join(CommunityInteractionEvent, CommunityInteractionEvent.post_id == CommunityPostTag.post_id)
                .where(
                    CommunityInteractionEvent.user_id == user.id,
                    CommunityInteractionEvent.event_type.in_(("like", "bookmark", "comment", "view")),
                )
                .group_by(CommunityPostTag.tag_id)
                .order_by(func.count(CommunityInteractionEvent.id).desc())
                .limit(12)
            )
        )
        followed_tag_ids = list(
            db.scalars(select(CommunityTopicFollow.tag_id).where(CommunityTopicFollow.user_id == user.id))
        )
        discovery_tag_ids = list(dict.fromkeys([*preferred_tag_ids, *followed_tag_ids]))
        recommendation_tag_ids = set(discovery_tag_ids)
        recommendation_ordering = []
        if discovery_tag_ids:
            matching_posts = select(CommunityPostTag.post_id).where(CommunityPostTag.tag_id.in_(discovery_tag_ids))
            recommendation_ordering.append(desc(case((CommunityPost.id.in_(matching_posts), 1), else_=0)))
        statement = statement.order_by(
            *recommendation_ordering,
            desc(CommunityPost.like_count + CommunityPost.comment_count * 2 + CommunityPost.bookmark_count * 3),
            CommunityPost.published_at.desc(),
        )
    elif tab == "bookmarked":
        statement = statement.order_by(CommunityPostBookmark.created_at.desc())
    elif tab == "liked":
        statement = statement.order_by(CommunityPostLike.created_at.desc())
    elif tab == "history":
        statement = statement.order_by(func.max(CommunityInteractionEvent.created_at).desc())
    else:
        statement = statement.order_by(CommunityPost.published_at.desc().nullslast(), CommunityPost.updated_at.desc())

    posts = list(db.scalars(statement.offset(max(offset, 0)).limit(limit + 1)))
    if tab == "recommended":
        posts = _diversify_recommended_posts(posts)
    has_more = len(posts) > limit
    posts = posts[:limit]
    responses = [_post_response(db, post=post, viewer=user) for post in posts]
    if tab == "recommended":
        recommendation_tag_ids_as_text = {str(tag_id) for tag_id in recommendation_tag_ids}
        for response in responses:
            matching_tags = [tag.name for tag in response.tags if tag.id in recommendation_tag_ids_as_text]
            if matching_tags:
                response.recommendation_reason = f"与你关注或近期互动的话题相关：#{' #'.join(matching_tags[:2])}"
            elif response.like_count + response.comment_count + response.bookmark_count > 0:
                response.recommendation_reason = "社区近期互动较多"
            else:
                response.recommendation_reason = "社区最新养殖交流"
    return CommunityPostListResponse(
        items=responses,
        next_offset=offset + limit if has_more else None,
    )


def get_community_post(db: Session, *, user: User, post_id: UUID, count_view: bool = True) -> CommunityPostResponse:
    post = _get_post(db, post_id=post_id)
    _ensure_post_readable(db, post=post, user=user)
    if count_view:
        if post.author_id != user.id:
            post.view_count += 1
            db.add(post)
        _record_interaction(db, user_id=user.id, post_id=post.id, event_type="view")
        db.commit()
        db.refresh(post)
    return _post_response(db, post=post, viewer=user)


def clear_community_view_history(db: Session, *, user: User) -> None:
    """Remove only the current user's post-view events.

    A history reset must not alter the post itself or other durable user assets
    such as likes, bookmarks, comments, and topic follows.
    """
    db.execute(
        delete(CommunityInteractionEvent).where(
            CommunityInteractionEvent.user_id == user.id,
            CommunityInteractionEvent.event_type == "view",
        )
    )
    db.commit()


def reset_community_recommendations(db: Session, *, user: User) -> None:
    """Restore hidden posts and forget passive viewing signals.

    Likes, bookmarks, comments and follows are deliberate user-owned assets,
    so this reset intentionally keeps them intact.
    """

    db.execute(delete(CommunityPostPreference).where(CommunityPostPreference.user_id == user.id))
    db.execute(
        delete(CommunityInteractionEvent).where(
            CommunityInteractionEvent.user_id == user.id,
            CommunityInteractionEvent.event_type.in_(("view", "not_interested")),
        )
    )
    db.commit()


def search_community(db: Session, *, user: User, query: str) -> CommunitySearchResponse:
    normalized_query = " ".join(query.split())
    if not normalized_query:
        return CommunitySearchResponse()
    post_results = list_community_posts(
        db,
        user=user,
        tab="latest",
        query=normalized_query,
        limit=12,
    )
    pattern = f"%{normalized_query}%"
    blocked_user_ids = select(CommunityUserBlock.blocked_id).where(CommunityUserBlock.blocker_id == user.id)
    blocked_viewer_ids = select(CommunityUserBlock.blocker_id).where(CommunityUserBlock.blocked_id == user.id)
    authors = list(
        db.scalars(
            select(User)
            .outerjoin(CommunityProfile, CommunityProfile.user_id == User.id)
            .where(
                User.status == "active",
                User.id.not_in(blocked_user_ids),
                User.id.not_in(blocked_viewer_ids),
                or_(
                    User.display_name.ilike(pattern),
                    User.username.ilike(pattern),
                    CommunityProfile.organization.ilike(pattern),
                    CommunityProfile.region.ilike(pattern),
                ),
            )
            .order_by(User.display_name.asc())
            .limit(8)
        )
    )
    tags = list(
        db.scalars(
            select(CommunityTag)
            .where(CommunityTag.name.ilike(pattern))
            .order_by(CommunityTag.post_count.desc(), CommunityTag.name.asc())
            .limit(8)
        )
    )
    visible_tags = [tag for tag in tags if _is_displayable_community_tag(tag.name)]
    tag_counts = _active_topic_post_counts(db, tag_ids=[tag.id for tag in visible_tags])
    return CommunitySearchResponse(
        posts=post_results.items,
        authors=[_author_response(db, author=author, viewer=user) for author in authors],
        tags=[_tag_response(db, tag=tag, viewer=user, post_count=tag_counts.get(tag.id, 0)) for tag in visible_tags],
    )


def create_community_post(db: Session, *, user: User, payload: CommunityPostCreateRequest) -> CommunityPostResponse:
    _ensure_community_content_allowed(f"{payload.title}\n{payload.content_markdown}")
    _ensure_post_submission_allowed(db, user=user, title=payload.title, content=payload.content_markdown)
    if payload.source_conversation_id is not None:
        _get_current_user_conversation(db, user=user, conversation_id=payload.source_conversation_id)
    if payload.source_husbandry_case_id is not None:
        source_case = db.scalar(
            select(HusbandryCase).where(
                HusbandryCase.id == payload.source_husbandry_case_id,
                HusbandryCase.owner_id == user.id,
            )
        )
        if source_case is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="养殖病例不存在")

    current_time = now_utc()
    post = CommunityPost(
        author_id=user.id,
        source_conversation_id=payload.source_conversation_id,
        source_husbandry_case_id=payload.source_husbandry_case_id,
        title=payload.title,
        content_markdown=payload.content_markdown,
        excerpt=_excerpt(payload.content_markdown),
        post_type=payload.post_type,
        visibility=payload.visibility,
        status="published" if payload.publish else "draft",
        case_data=payload.case_data,
        published_at=current_time if payload.publish else None,
    )
    db.add(post)
    db.flush()
    _sync_post_tags(db, post=post, tag_names=payload.tags)
    _sync_post_assets(db, post=post, user=user, file_ids=payload.file_ids, cover_file_id=payload.cover_file_id)
    if payload.publish:
        _notify_mentions(db, actor=user, content=f"{payload.title}\n{payload.content_markdown}", post_id=post.id)
    db.commit()
    db.refresh(post)
    return _post_response(db, post=post, viewer=user)


def update_community_post(
    db: Session,
    *,
    user: User,
    post_id: UUID,
    payload: CommunityPostUpdateRequest,
) -> CommunityPostResponse:
    post = _get_owned_post(db, user=user, post_id=post_id)
    if post.status == "deleted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="帖子已删除")

    changes = payload.model_dump(exclude_unset=True)
    for field in ("title", "content_markdown", "post_type", "visibility", "case_data"):
        if field in changes:
            setattr(post, field, changes[field])
    if "content_markdown" in changes:
        post.excerpt = _excerpt(post.content_markdown)
    _ensure_community_content_allowed(f"{post.title}\n{post.content_markdown}")
    if "tags" in changes:
        _sync_post_tags(db, post=post, tag_names=changes["tags"])
    if "file_ids" in changes or "cover_file_id" in changes:
        current_assets = list(db.scalars(select(CommunityPostAsset.file_id).where(CommunityPostAsset.post_id == post.id)))
        _sync_post_assets(
            db,
            post=post,
            user=user,
            file_ids=changes.get("file_ids", current_assets),
            cover_file_id=changes.get("cover_file_id", post.cover_file_id),
        )
    if changes.get("publish") is True and post.status == "draft":
        post.status = "published"
        post.published_at = now_utc()
    post.updated_at = now_utc()
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_response(db, post=post, viewer=user)


def delete_community_post(db: Session, *, user: User, post_id: UUID) -> None:
    post = _get_owned_post(db, user=user, post_id=post_id)
    post.status = "deleted"
    post.deleted_at = now_utc()
    post.updated_at = now_utc()
    db.add(post)
    db.commit()


def toggle_community_post_like(db: Session, *, user: User, post_id: UUID) -> CommunityPostResponse:
    post = _get_post(db, post_id=post_id)
    _ensure_post_interactable(post=post)
    existing = db.scalar(
        select(CommunityPostLike).where(CommunityPostLike.post_id == post.id, CommunityPostLike.user_id == user.id)
    )
    if existing is None:
        db.add(CommunityPostLike(post_id=post.id, user_id=user.id))
        _record_interaction(db, user_id=user.id, post_id=post.id, event_type="like")
        post.like_count += 1
        if post.author_id != user.id:
            _create_notification(
                db,
                user_id=post.author_id,
                actor_user_id=user.id,
                post_id=post.id,
                notification_type="post_like",
            )
    else:
        db.delete(existing)
        post.like_count = max(0, post.like_count - 1)
    post.updated_at = now_utc()
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_response(db, post=post, viewer=user)


def toggle_community_post_bookmark(db: Session, *, user: User, post_id: UUID) -> CommunityPostResponse:
    post = _get_post(db, post_id=post_id)
    _ensure_post_interactable(post=post)
    existing = db.scalar(
        select(CommunityPostBookmark).where(CommunityPostBookmark.post_id == post.id, CommunityPostBookmark.user_id == user.id)
    )
    if existing is None:
        db.add(CommunityPostBookmark(post_id=post.id, user_id=user.id))
        _record_interaction(db, user_id=user.id, post_id=post.id, event_type="bookmark")
        post.bookmark_count += 1
    else:
        db.delete(existing)
        post.bookmark_count = max(0, post.bookmark_count - 1)
    post.updated_at = now_utc()
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_response(db, post=post, viewer=user)


def list_community_bookmark_collections(
    db: Session,
    *,
    user: User,
    post_id: UUID | None = None,
) -> CommunityBookmarkCollectionListResponse:
    collections = list(
        db.scalars(
            select(CommunityBookmarkCollection)
            .where(CommunityBookmarkCollection.owner_id == user.id)
            .order_by(CommunityBookmarkCollection.updated_at.desc(), CommunityBookmarkCollection.created_at.desc())
        )
    )
    return CommunityBookmarkCollectionListResponse(
        items=[_bookmark_collection_response(db, collection=collection, post_id=post_id) for collection in collections]
    )


def create_community_bookmark_collection(
    db: Session,
    *,
    user: User,
    payload: CommunityBookmarkCollectionCreateRequest,
) -> CommunityBookmarkCollectionResponse:
    existing = db.scalar(
        select(CommunityBookmarkCollection).where(
            CommunityBookmarkCollection.owner_id == user.id,
            CommunityBookmarkCollection.name == payload.name,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已存在同名收藏夹")
    collection = CommunityBookmarkCollection(owner_id=user.id, name=payload.name, description=payload.description)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return _bookmark_collection_response(db, collection=collection)


def update_community_bookmark_collection(
    db: Session,
    *,
    user: User,
    collection_id: UUID,
    payload: CommunityBookmarkCollectionUpdateRequest,
) -> CommunityBookmarkCollectionResponse:
    collection = _get_owned_bookmark_collection(db, user=user, collection_id=collection_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] != collection.name:
        duplicate = db.scalar(
            select(CommunityBookmarkCollection).where(
                CommunityBookmarkCollection.owner_id == user.id,
                CommunityBookmarkCollection.name == changes["name"],
                CommunityBookmarkCollection.id != collection.id,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="已存在同名收藏夹")
    for field in ("name", "description"):
        if field in changes:
            setattr(collection, field, changes[field])
    collection.updated_at = now_utc()
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return _bookmark_collection_response(db, collection=collection)


def delete_community_bookmark_collection(db: Session, *, user: User, collection_id: UUID) -> None:
    collection = _get_owned_bookmark_collection(db, user=user, collection_id=collection_id)
    db.delete(collection)
    db.commit()


def get_community_bookmark_collection_detail(
    db: Session,
    *,
    user: User,
    collection_id: UUID,
    offset: int = 0,
    limit: int = 30,
) -> CommunityBookmarkCollectionDetailResponse:
    collection = _get_owned_bookmark_collection(db, user=user, collection_id=collection_id)
    posts = list(
        db.scalars(
            select(CommunityPost)
            .join(CommunityBookmarkCollectionItem, CommunityBookmarkCollectionItem.post_id == CommunityPost.id)
            .where(CommunityBookmarkCollectionItem.collection_id == collection.id)
            .order_by(CommunityBookmarkCollectionItem.created_at.desc())
            .offset(max(offset, 0))
            .limit(limit + 1)
        )
    )
    has_more = len(posts) > limit
    posts = posts[:limit]
    visible_posts: list[CommunityPost] = []
    for post in posts:
        try:
            _ensure_post_readable(db, post=post, user=user)
        except HTTPException as error:
            if error.status_code == status.HTTP_403_FORBIDDEN:
                continue
            raise
        visible_posts.append(post)
    return CommunityBookmarkCollectionDetailResponse(
        collection=_bookmark_collection_response(db, collection=collection),
        posts=[_post_response(db, post=post, viewer=user) for post in visible_posts],
        next_offset=offset + limit if has_more else None,
    )


def toggle_community_bookmark_collection_post(
    db: Session,
    *,
    user: User,
    collection_id: UUID,
    post_id: UUID,
) -> CommunityBookmarkCollectionResponse:
    collection = _get_owned_bookmark_collection(db, user=user, collection_id=collection_id)
    post = _get_post(db, post_id=post_id)
    _ensure_post_readable(db, post=post, user=user)
    _ensure_post_interactable(post=post)
    existing = db.scalar(
        select(CommunityBookmarkCollectionItem).where(
            CommunityBookmarkCollectionItem.collection_id == collection.id,
            CommunityBookmarkCollectionItem.post_id == post.id,
        )
    )
    if existing is None:
        db.add(CommunityBookmarkCollectionItem(collection_id=collection.id, post_id=post.id))
        bookmark = db.scalar(
            select(CommunityPostBookmark).where(CommunityPostBookmark.post_id == post.id, CommunityPostBookmark.user_id == user.id)
        )
        if bookmark is None:
            db.add(CommunityPostBookmark(post_id=post.id, user_id=user.id))
            _record_interaction(db, user_id=user.id, post_id=post.id, event_type="bookmark")
            post.bookmark_count += 1
            post.updated_at = now_utc()
            db.add(post)
    else:
        db.delete(existing)
    collection.updated_at = now_utc()
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return _bookmark_collection_response(db, collection=collection, post_id=post.id)


def list_community_comments(
    db: Session,
    *,
    user: User,
    post_id: UUID,
    sort: str = "top",
    offset: int = 0,
    limit: int = 60,
) -> CommunityCommentListResponse:
    post = _get_post(db, post_id=post_id)
    _ensure_post_readable(db, post=post, user=user)
    statement = select(CommunityComment).where(CommunityComment.post_id == post.id, CommunityComment.status != "hidden")
    if sort == "latest":
        statement = statement.order_by(CommunityComment.created_at.desc())
    else:
        ordering = [CommunityComment.like_count.desc(), CommunityComment.created_at.desc()]
        if post.accepted_comment_id:
            accepted_priority = case((CommunityComment.id == post.accepted_comment_id, 1), else_=0)
            ordering.insert(0, desc(accepted_priority))
        statement = statement.order_by(*ordering)
    comments = list(db.scalars(statement.offset(max(offset, 0)).limit(limit + 1)))
    has_more = len(comments) > limit
    comments = comments[:limit]
    return CommunityCommentListResponse(
        items=[_comment_response(db, comment=comment, viewer=user) for comment in comments],
        next_offset=offset + limit if has_more else None,
    )


def create_community_comment(
    db: Session,
    *,
    user: User,
    post_id: UUID,
    content: str,
    parent_comment_id: UUID | None,
) -> CommunityCommentResponse:
    _ensure_community_content_allowed(content)
    _ensure_comment_submission_allowed(db, user=user, content=content)
    post = _get_post(db, post_id=post_id)
    _ensure_post_interactable(post=post)
    parent: CommunityComment | None = None
    if parent_comment_id is not None:
        parent = db.scalar(
            select(CommunityComment).where(CommunityComment.id == parent_comment_id, CommunityComment.post_id == post.id)
        )
        if parent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回复的评论不存在")
    comment = CommunityComment(post_id=post.id, author_id=user.id, parent_comment_id=parent_comment_id, content=content)
    db.add(comment)
    _record_interaction(db, user_id=user.id, post_id=post.id, event_type="comment")
    post.comment_count += 1
    post.updated_at = now_utc()
    db.add(post)
    db.flush()
    recipient_id = parent.author_id if parent is not None else post.author_id
    if recipient_id != user.id:
        _create_notification(
            db,
            user_id=recipient_id,
            actor_user_id=user.id,
            post_id=post.id,
            comment_id=comment.id,
            notification_type="comment_reply" if parent is not None else "post_comment",
        )
    _notify_mentions(db, actor=user, content=content, post_id=post.id, comment_id=comment.id)
    db.commit()
    db.refresh(comment)
    return _comment_response(db, comment=comment, viewer=user)


def update_community_comment(
    db: Session,
    *,
    user: User,
    comment_id: UUID,
    content: str,
) -> CommunityCommentResponse:
    comment = _get_owned_comment(db, user=user, comment_id=comment_id)
    if comment.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该评论不能编辑")
    _ensure_community_content_allowed(content)
    comment.content = content
    comment.updated_at = now_utc()
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _comment_response(db, comment=comment, viewer=user)


def delete_community_comment(db: Session, *, user: User, comment_id: UUID) -> None:
    comment = _get_owned_comment(db, user=user, comment_id=comment_id)
    if comment.status == "deleted":
        return
    post = _get_post(db, post_id=comment.post_id)
    comment.status = "deleted"
    comment.deleted_at = now_utc()
    comment.updated_at = now_utc()
    post.comment_count = max(0, post.comment_count - 1)
    if post.accepted_comment_id == comment.id:
        post.accepted_comment_id = None
        post.question_status = "open"
    post.updated_at = now_utc()
    db.add_all([comment, post])
    db.commit()


def toggle_community_comment_like(db: Session, *, user: User, comment_id: UUID) -> CommunityCommentResponse:
    comment = db.scalar(select(CommunityComment).where(CommunityComment.id == comment_id))
    if comment is None or comment.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评论不存在")
    post = _get_post(db, post_id=comment.post_id)
    _ensure_post_readable(db, post=post, user=user)
    existing = db.scalar(
        select(CommunityCommentLike).where(CommunityCommentLike.comment_id == comment.id, CommunityCommentLike.user_id == user.id)
    )
    if existing is None:
        db.add(CommunityCommentLike(comment_id=comment.id, user_id=user.id))
        comment.like_count += 1
        if comment.author_id != user.id:
            _create_notification(
                db,
                user_id=comment.author_id,
                actor_user_id=user.id,
                post_id=post.id,
                comment_id=comment.id,
                notification_type="comment_like",
            )
    else:
        db.delete(existing)
        comment.like_count = max(0, comment.like_count - 1)
    comment.updated_at = now_utc()
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _comment_response(db, comment=comment, viewer=user)


def toggle_community_follow(db: Session, *, user: User, target_user_id: UUID) -> CommunityAuthorResponse:
    if target_user_id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能关注自己")
    target = db.scalar(select(User).where(User.id == target_user_id, User.status == "active"))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    existing = db.scalar(
        select(CommunityFollow).where(CommunityFollow.follower_id == user.id, CommunityFollow.followed_id == target_user_id)
    )
    if existing is None:
        db.add(CommunityFollow(follower_id=user.id, followed_id=target_user_id))
        _create_notification(db, user_id=target_user_id, actor_user_id=user.id, notification_type="follow")
    else:
        db.delete(existing)
    db.commit()
    return _author_response(db, author=target, viewer=user)


def get_community_profile(db: Session, *, user: User, target_user_id: UUID) -> CommunityAuthorResponse:
    target = db.scalar(select(User).where(User.id == target_user_id, User.status == "active"))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return _author_response(db, author=target, viewer=user)


def get_community_profile_detail(
    db: Session,
    *,
    user: User,
    target_user_id: UUID,
    offset: int = 0,
    limit: int = 12,
) -> CommunityProfileDetailResponse:
    target = db.scalar(select(User).where(User.id == target_user_id, User.status == "active"))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    _ensure_users_can_interact(db, user_id=user.id, target_user_id=target.id)
    following_author_ids = select(CommunityFollow.followed_id).where(CommunityFollow.follower_id == user.id)
    posts = list(
        db.scalars(
            select(CommunityPost)
            .where(
                CommunityPost.author_id == target.id,
                CommunityPost.status == "published",
                or_(
                    CommunityPost.visibility == "public",
                    CommunityPost.author_id == user.id,
                    CommunityPost.author_id.in_(following_author_ids),
                ),
            )
            .order_by(CommunityPost.published_at.desc())
            .offset(max(offset, 0))
            .limit(limit + 1)
        )
    )
    has_more = len(posts) > limit
    posts = posts[:limit]
    return CommunityProfileDetailResponse(
        author=_author_response(db, author=target, viewer=user),
        posts=[_post_response(db, post=post, viewer=user) for post in posts],
        next_offset=offset + limit if has_more else None,
    )


def get_community_relationships(
    db: Session,
    *,
    user: User,
    target_user_id: UUID,
    relationship_type: str,
    offset: int = 0,
    limit: int = 30,
) -> CommunityRelationshipListResponse:
    target = db.scalar(select(User).where(User.id == target_user_id, User.status == "active"))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    _ensure_users_can_interact(db, user_id=user.id, target_user_id=target.id)
    if relationship_type == "followers":
        statement = select(User).join(CommunityFollow, CommunityFollow.follower_id == User.id).where(
            CommunityFollow.followed_id == target.id
        )
    else:
        statement = select(User).join(CommunityFollow, CommunityFollow.followed_id == User.id).where(
            CommunityFollow.follower_id == target.id
        )
    blocked_user_ids = select(CommunityUserBlock.blocked_id).where(CommunityUserBlock.blocker_id == user.id)
    blocked_viewer_ids = select(CommunityUserBlock.blocker_id).where(CommunityUserBlock.blocked_id == user.id)
    members = list(
        db.scalars(
            statement.where(
                User.status == "active",
                User.id.not_in(blocked_user_ids),
                User.id.not_in(blocked_viewer_ids),
            )
            .order_by(CommunityFollow.created_at.desc())
            .offset(max(offset, 0))
            .limit(limit + 1)
        )
    )
    has_more = len(members) > limit
    members = members[:limit]
    return CommunityRelationshipListResponse(
        author=_author_response(db, author=target, viewer=user),
        relationship_type="followers" if relationship_type == "followers" else "following",
        items=[_author_response(db, author=member, viewer=user) for member in members],
        next_offset=offset + limit if has_more else None,
    )


def get_community_creator_overview(db: Session, *, user: User) -> CommunityCreatorOverviewResponse:
    current_time = now_utc()
    published = select(CommunityPost).where(CommunityPost.author_id == user.id, CommunityPost.status == "published")
    post_count = db.scalar(select(func.count()).select_from(published.subquery())) or 0
    published_this_week = db.scalar(
        select(func.count()).select_from(CommunityPost).where(
            CommunityPost.author_id == user.id,
            CommunityPost.status == "published",
            CommunityPost.published_at >= current_time - timedelta(days=7),
        )
    ) or 0
    totals = db.execute(
        select(
            func.coalesce(func.sum(CommunityPost.view_count), 0),
            func.coalesce(func.sum(CommunityPost.like_count), 0),
            func.coalesce(func.sum(CommunityPost.bookmark_count), 0),
            func.coalesce(func.sum(CommunityPost.comment_count), 0),
        ).where(CommunityPost.author_id == user.id, CommunityPost.status == "published")
    ).one()
    follower_count = db.scalar(
        select(func.count()).select_from(CommunityFollow).where(CommunityFollow.followed_id == user.id)
    ) or 0
    following_count = db.scalar(
        select(func.count()).select_from(CommunityFollow).where(CommunityFollow.follower_id == user.id)
    ) or 0
    return CommunityCreatorOverviewResponse(
        post_count=int(post_count),
        published_this_week=int(published_this_week),
        view_count=int(totals[0]),
        received_like_count=int(totals[1]),
        bookmark_count=int(totals[2]),
        comment_count=int(totals[3]),
        follower_count=int(follower_count),
        following_count=int(following_count),
    )


def update_community_profile(
    db: Session,
    *,
    user: User,
    payload: CommunityProfileUpdateRequest,
) -> CommunityAuthorResponse:
    profile = db.scalar(select(CommunityProfile).where(CommunityProfile.user_id == user.id))
    if profile is None:
        profile = CommunityProfile(user_id=user.id)
    profile.identity_type = payload.identity_type
    profile.region = payload.region
    profile.organization = payload.organization
    profile.expertise_tags = payload.expertise_tags
    profile.years_experience = payload.years_experience
    profile.bio = payload.bio
    if payload.request_verification and profile.verification_status in {"unverified", "rejected"}:
        profile.verification_status = "pending"
    profile.updated_at = now_utc()
    db.add(profile)
    db.commit()
    return _author_response(db, author=user, viewer=user)


def list_community_blocked_users(
    db: Session,
    *,
    user: User,
    offset: int = 0,
    limit: int = 30,
) -> CommunityBlockedUserListResponse:
    members = list(
        db.scalars(
            select(User)
            .join(CommunityUserBlock, CommunityUserBlock.blocked_id == User.id)
            .where(
                CommunityUserBlock.blocker_id == user.id,
                User.status == "active",
            )
            .order_by(CommunityUserBlock.created_at.desc())
            .offset(max(offset, 0))
            .limit(limit + 1)
        )
    )
    has_more = len(members) > limit
    members = members[:limit]
    return CommunityBlockedUserListResponse(
        items=[_author_response(db, author=member, viewer=user) for member in members],
        next_offset=offset + limit if has_more else None,
    )


def toggle_community_user_block(db: Session, *, user: User, target_user_id: UUID) -> dict[str, bool]:
    if target_user_id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能屏蔽自己")
    target = db.scalar(select(User.id).where(User.id == target_user_id, User.status == "active"))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    block = db.scalar(
        select(CommunityUserBlock).where(
            CommunityUserBlock.blocker_id == user.id,
            CommunityUserBlock.blocked_id == target_user_id,
        )
    )
    if block is None:
        db.add(CommunityUserBlock(blocker_id=user.id, blocked_id=target_user_id))
        db.execute(
            delete(CommunityFollow).where(
                or_(
                    (CommunityFollow.follower_id == user.id) & (CommunityFollow.followed_id == target_user_id),
                    (CommunityFollow.follower_id == target_user_id) & (CommunityFollow.followed_id == user.id),
                )
            )
        )
        blocked = True
    else:
        db.delete(block)
        blocked = False
    db.commit()
    return {"blocked": blocked}


def list_community_direct_threads(db: Session, *, user: User) -> CommunityDirectThreadListResponse:
    threads = list(
        db.scalars(
            select(CommunityDirectThread)
            .where(
                or_(
                    CommunityDirectThread.participant_one_id == user.id,
                    CommunityDirectThread.participant_two_id == user.id,
                )
            )
            .order_by(CommunityDirectThread.last_message_at.desc())
            .limit(100)
        )
    )
    items: list[CommunityDirectThreadResponse] = []
    for thread in threads:
        counterpart_id = thread.participant_two_id if thread.participant_one_id == user.id else thread.participant_one_id
        counterpart = db.scalar(select(User).where(User.id == counterpart_id, User.status == "active"))
        if counterpart is None:
            continue
        unread_count = db.scalar(
            select(func.count()).select_from(CommunityDirectMessage).where(
                CommunityDirectMessage.thread_id == thread.id,
                CommunityDirectMessage.recipient_id == user.id,
                CommunityDirectMessage.read_at.is_(None),
                CommunityDirectMessage.status == "active",
            )
        ) or 0
        items.append(
            CommunityDirectThreadResponse(
                id=str(thread.id),
                counterpart=_author_response(db, author=counterpart, viewer=user),
                last_message_preview=thread.last_message_preview,
                last_message_at=thread.last_message_at,
                unread_count=int(unread_count),
            )
        )
    return CommunityDirectThreadListResponse(items=items)


def list_community_direct_messages(
    db: Session,
    *,
    user: User,
    thread_id: UUID,
    offset: int = 0,
    limit: int = 80,
) -> CommunityDirectMessageListResponse:
    thread = _get_community_direct_thread(db, user=user, thread_id=thread_id)
    messages = list(
        db.scalars(
            select(CommunityDirectMessage)
            .where(CommunityDirectMessage.thread_id == thread.id)
            .order_by(CommunityDirectMessage.created_at.asc())
            .offset(max(offset, 0))
            .limit(limit + 1)
        )
    )
    has_more = len(messages) > limit
    messages = messages[:limit]
    unread_messages = [
        message for message in messages
        if message.recipient_id == user.id and message.read_at is None and message.status == "active"
    ]
    if unread_messages:
        current_time = now_utc()
        for message in unread_messages:
            message.read_at = current_time
            db.add(message)
        db.commit()
    return CommunityDirectMessageListResponse(
        items=[_direct_message_response(message=message, viewer=user) for message in messages],
        next_offset=offset + limit if has_more else None,
    )


def send_community_direct_message(
    db: Session,
    *,
    user: User,
    target_user_id: UUID,
    content: str,
) -> CommunityDirectMessageResponse:
    _ensure_community_content_allowed(content)
    _ensure_direct_message_submission_allowed(db, user=user, target_user_id=target_user_id, content=content)
    if target_user_id == user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能给自己发送私信")
    target = db.scalar(select(User).where(User.id == target_user_id, User.status == "active"))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    _ensure_users_can_interact(db, user_id=user.id, target_user_id=target.id)
    _ensure_direct_message_permission(db, user=user, target=target)
    participant_one_id, participant_two_id = _direct_thread_pair(user.id, target.id)
    thread = db.scalar(
        select(CommunityDirectThread).where(
            CommunityDirectThread.participant_one_id == participant_one_id,
            CommunityDirectThread.participant_two_id == participant_two_id,
        )
    )
    current_time = now_utc()
    if thread is None:
        thread = CommunityDirectThread(
            participant_one_id=participant_one_id,
            participant_two_id=participant_two_id,
            last_message_preview=_excerpt(content)[:120],
            last_message_at=current_time,
        )
        db.add(thread)
        db.flush()
    else:
        thread.last_message_preview = _excerpt(content)[:120]
        thread.last_message_at = current_time
        db.add(thread)
    message = CommunityDirectMessage(
        thread_id=thread.id,
        sender_id=user.id,
        recipient_id=target.id,
        content=content,
    )
    db.add(message)
    _create_notification(
        db,
        user_id=target.id,
        actor_user_id=user.id,
        notification_type="direct_message",
        payload={"thread_id": str(thread.id)},
    )
    db.commit()
    db.refresh(message)
    return _direct_message_response(message=message, viewer=user)


def hide_community_post(db: Session, *, user: User, post_id: UUID) -> dict[str, bool]:
    post = _get_post(db, post_id=post_id)
    _ensure_post_readable(db, post=post, user=user)
    preference = db.scalar(
        select(CommunityPostPreference).where(
            CommunityPostPreference.user_id == user.id,
            CommunityPostPreference.post_id == post.id,
        )
    )
    if preference is None:
        db.add(CommunityPostPreference(user_id=user.id, post_id=post.id, preference_type="not_interested"))
        _record_interaction(db, user_id=user.id, post_id=post.id, event_type="not_interested")
    else:
        preference.preference_type = "not_interested"
        db.add(preference)
    db.commit()
    return {"hidden": True}


def accept_community_answer(
    db: Session,
    *,
    user: User,
    post_id: UUID,
    comment_id: UUID,
) -> CommunityPostResponse:
    post = _get_owned_post(db, user=user, post_id=post_id)
    if post.post_type != "question" or post.status != "published":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有已发布的问题可以采纳回答")
    comment = db.scalar(
        select(CommunityComment).where(
            CommunityComment.id == comment_id,
            CommunityComment.post_id == post.id,
            CommunityComment.status == "active",
        )
    )
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="回答不存在")
    post.accepted_comment_id = comment.id
    post.question_status = "resolved"
    post.updated_at = now_utc()
    db.add(post)
    if comment.author_id != user.id:
        _create_notification(
            db,
            user_id=comment.author_id,
            actor_user_id=user.id,
            post_id=post.id,
            comment_id=comment.id,
            notification_type="answer_accepted",
        )
    db.commit()
    db.refresh(post)
    return _post_response(db, post=post, viewer=user)


def add_community_case_update(
    db: Session,
    *,
    user: User,
    post_id: UUID,
    occurred_on: date,
    outcome_status: str,
    content: str,
    metrics: dict,
) -> CommunityCaseUpdateResponse:
    post = _get_owned_post(db, user=user, post_id=post_id)
    if post.post_type != "case" or post.status != "published":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有已发布病例可以添加随访")
    update = CommunityCaseUpdate(
        post_id=post.id,
        author_id=user.id,
        occurred_on=occurred_on,
        outcome_status=outcome_status,
        content=content,
        metrics=metrics,
    )
    post.updated_at = now_utc()
    db.add_all([update, post])
    followers = db.scalars(select(CommunityFollow.follower_id).where(CommunityFollow.followed_id == user.id)).all()
    for follower_id in followers:
        _create_notification(
            db,
            user_id=follower_id,
            actor_user_id=user.id,
            post_id=post.id,
            notification_type="case_update",
        )
    db.commit()
    db.refresh(update)
    return _case_update_response(db, update=update, viewer=user)


def create_community_post_draft_from_husbandry_case(
    db: Session,
    *,
    user: User,
    case_id: UUID,
    title: str | None,
) -> CommunityPostResponse:
    case = db.scalar(select(HusbandryCase).where(HusbandryCase.id == case_id, HusbandryCase.owner_id == user.id))
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="养殖病例不存在")
    batch = db.scalar(select(SilkwormBatch).where(SilkwormBatch.id == case.batch_id)) if case.batch_id else None
    farm = db.scalar(select(Farm).where(Farm.id == case.farm_id))
    case_data = {
        "occurred_on": case.occurred_on.isoformat(),
        "farm": farm.name if farm else None,
        "batch_code": batch.batch_code if batch else None,
        "variety": batch.variety if batch else None,
        "instar": batch.instar if batch else None,
        "symptoms": case.symptom_summary,
        "suspected_disease": case.suspected_disease,
        "severity": case.severity,
        "diagnosis": case.diagnosis_summary,
        "measure": case.recommendation,
    }
    content_parts = [
        "## 病例经过",
        case.symptom_summary or "请补充发现经过和主要症状。",
        "## 初步判断",
        case.diagnosis_summary or case.suspected_disease or "待补充。",
        "## 已采取措施",
        case.recommendation or "待补充。",
        "> 由养殖台账生成。发布前请移除位置、联系方式等隐私信息。",
    ]
    post = CommunityPost(
        author_id=user.id,
        source_husbandry_case_id=case.id,
        title=title or case.title,
        content_markdown="\n\n".join(content_parts),
        excerpt=_excerpt(case.symptom_summary or case.title),
        post_type="case",
        status="draft",
        case_data=case_data,
        source_snapshot={"source": "husbandry_case", "case_id": str(case.id), "generated_at": now_utc().isoformat()},
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_response(db, post=post, viewer=user)


def save_community_post_to_husbandry(
    db: Session,
    *,
    user: User,
    post_id: UUID,
    farm_id: UUID,
    batch_id: UUID | None,
) -> dict[str, str]:
    post = _get_post(db, post_id=post_id)
    _ensure_post_readable(db, post=post, user=user)
    if post.post_type != "case":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="只有病例帖可以保存到养殖台账")
    farm = db.scalar(select(Farm).where(Farm.id == farm_id, Farm.owner_id == user.id, Farm.status == "active"))
    if farm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="养殖场不存在")
    batch = None
    if batch_id is not None:
        batch = db.scalar(select(SilkwormBatch).where(SilkwormBatch.id == batch_id, SilkwormBatch.farm_id == farm.id))
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="批次不属于所选养殖场")
    data = post.case_data or {}
    occurred_on = date.today()
    if data.get("occurred_on"):
        try:
            occurred_on = date.fromisoformat(str(data["occurred_on"]))
        except ValueError:
            pass
    husbandry_case = HusbandryCase(
        owner_id=user.id,
        farm_id=farm.id,
        batch_id=batch.id if batch else None,
        title=post.title,
        occurred_on=occurred_on,
        symptom_summary=data.get("symptoms") or post.excerpt,
        suspected_disease=data.get("suspected_disease"),
        severity=data.get("severity") if data.get("severity") in {"low", "medium", "high", "critical"} else "medium",
        status="needs_more_info",
        diagnosis_summary=data.get("diagnosis"),
        recommendation=data.get("measure"),
        source_snapshot={"source": "community_post", "post_id": str(post.id), "author_id": str(post.author_id)},
    )
    db.add(husbandry_case)
    db.commit()
    db.refresh(husbandry_case)
    return {"case_id": str(husbandry_case.id)}


def list_community_notifications(db: Session, *, user: User, offset: int = 0, limit: int = 30) -> CommunityNotificationListResponse:
    notifications = list(
        db.scalars(
            select(CommunityNotification)
            .where(CommunityNotification.user_id == user.id)
            .order_by(CommunityNotification.created_at.desc())
            .offset(max(offset, 0))
            .limit(limit)
        )
    )
    unread_count = db.scalar(
        select(func.count()).select_from(CommunityNotification).where(
            CommunityNotification.user_id == user.id,
            CommunityNotification.read_at.is_(None),
        )
    ) or 0
    return CommunityNotificationListResponse(
        items=[_notification_response(db, notification=item, viewer=user) for item in notifications],
        unread_count=int(unread_count),
    )


def mark_community_notifications_read(db: Session, *, user: User) -> None:
    notifications = db.scalars(
        select(CommunityNotification).where(CommunityNotification.user_id == user.id, CommunityNotification.read_at.is_(None))
    )
    current_time = now_utc()
    for notification in notifications:
        notification.read_at = current_time
        db.add(notification)
    db.commit()


def create_community_report(
    db: Session,
    *,
    user: User,
    post_id: UUID,
    target_type: str,
    reason: str,
    detail: str | None,
    comment_id: UUID | None,
) -> None:
    post = _get_post(db, post_id=post_id)
    _ensure_post_readable(db, post=post, user=user)
    if post.author_id == user.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不能举报自己发布的内容")
    if target_type == "comment":
        if comment_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请选择要举报的评论")
        comment = db.scalar(select(CommunityComment).where(CommunityComment.id == comment_id, CommunityComment.post_id == post.id))
        if comment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评论不存在")
        if comment.author_id == user.id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="不能举报自己发布的评论")
    elif target_type != "post":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="举报目标无效")
    # Serialize submissions from the same reporter. This makes the short-window
    # throttle deterministic and lets the partial unique indexes cover races.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(CAST(:user_id AS text)))"), {"user_id": str(user.id)})
    recent_count = db.scalar(
        select(func.count()).select_from(CommunityReport).where(
            CommunityReport.reporter_id == user.id,
            CommunityReport.created_at >= now_utc() - timedelta(minutes=10),
        )
    ) or 0
    if recent_count >= 5:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="10 分钟内最多提交 5 条举报，请稍后再试")
    duplicate_filter = [CommunityReport.reporter_id == user.id, CommunityReport.status == "pending"]
    duplicate_filter.append(CommunityReport.comment_id == comment_id if target_type == "comment" else CommunityReport.post_id == post.id)
    duplicate = db.scalar(select(CommunityReport.id).where(*duplicate_filter))
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="你已举报过该内容，审核结果会通过通知告知")
    db.add(
        CommunityReport(
            reporter_id=user.id,
            post_id=post.id,
            comment_id=comment_id if target_type == "comment" else None,
            target_type=target_type,
            reason=reason,
            detail=detail,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="你已举报过该内容，审核结果会通过通知告知") from exc


def create_community_post_draft_from_conversation(
    db: Session,
    *,
    user: User,
    conversation_id: UUID,
    title: str | None,
    include_attachment_ids: list[UUID],
) -> CommunityPostResponse:
    conversation = _get_current_user_conversation(db, user=user, conversation_id=conversation_id)
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id, Message.status == "sent", Message.deleted_at.is_(None))
            .order_by(Message.created_at.asc())
        )
    )
    user_message = next((message for message in reversed(messages) if message.sender_type == "user"), None)
    assistant_message = next((message for message in reversed(messages) if message.sender_type == "assistant"), None)
    sections: list[str] = ["## 问诊经验整理"]
    if user_message is not None and user_message.content.strip():
        sections.extend(["### 观察与问题", user_message.content.strip()])
    if assistant_message is not None and assistant_message.content.strip():
        sections.extend(["### 建议与处理方向", assistant_message.content.strip()])
    sections.extend(["", "> 由 CanW 问诊记录生成，发布前请核对内容并移除敏感信息。"])
    content_markdown = "\n\n".join(sections).strip()
    snapshot = {
        "source": "diagnosis_conversation",
        "conversation_id": str(conversation.id),
        "message_ids": [str(message.id) for message in messages[-8:]],
        "generated_at": now_utc().isoformat(),
    }
    post = CommunityPost(
        author_id=user.id,
        source_conversation_id=conversation.id,
        title=title or conversation.title or "我的问诊经验",
        content_markdown=content_markdown,
        excerpt=_excerpt(content_markdown),
        post_type="case",
        status="draft",
        source_snapshot=snapshot,
    )
    db.add(post)
    db.flush()
    valid_attachment_ids = _conversation_attachment_ids(
        db,
        conversation_id=conversation.id,
        requested_ids=include_attachment_ids,
    )
    _sync_post_assets(db, post=post, user=user, file_ids=valid_attachment_ids, cover_file_id=None)
    db.commit()
    db.refresh(post)
    return _post_response(db, post=post, viewer=user)


def list_community_tags(db: Session, *, user: User, limit: int = 20) -> list[CommunityTagResponse]:
    rows = db.execute(
        select(CommunityTag, func.count(CommunityPostTag.post_id).label("active_post_count"))
        .join(CommunityPostTag, CommunityPostTag.tag_id == CommunityTag.id)
        .join(CommunityPost, CommunityPost.id == CommunityPostTag.post_id)
        .where(CommunityPost.status == "published")
        .group_by(CommunityTag.id)
        .order_by(desc("active_post_count"), CommunityTag.name.asc())
        .limit(limit * 3)
    ).all()
    return [
        _tag_response(db, tag=tag, viewer=user, post_count=int(post_count))
        for tag, post_count in rows
        if _is_displayable_community_tag(tag.name)
    ][:limit]


def toggle_community_topic_follow(db: Session, *, user: User, tag_id: UUID) -> CommunityTagResponse:
    tag = db.scalar(select(CommunityTag).where(CommunityTag.id == tag_id))
    if tag is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="话题不存在")
    existing = db.scalar(
        select(CommunityTopicFollow).where(
            CommunityTopicFollow.user_id == user.id,
            CommunityTopicFollow.tag_id == tag.id,
        )
    )
    if existing is None:
        db.add(CommunityTopicFollow(user_id=user.id, tag_id=tag.id))
    else:
        db.delete(existing)
    db.commit()
    post_count = _active_topic_post_counts(db, tag_ids=[tag.id]).get(tag.id, 0)
    return _tag_response(db, tag=tag, viewer=user, post_count=post_count)


def save_community_attachments(
    db: Session,
    *,
    user: User,
    attachments: list[tuple[str, str, bytes]],
) -> list[CommunityUploadedFileResponse]:
    uploaded_files: list[UploadedFile] = []
    for index, (file_name, content_type, content) in enumerate(attachments, start=1):
        if not content:
            continue
        normalized_file_name = _safe_file_name(file_name or f"attachment-{index}")
        normalized_content_type = _content_type_for_community_file(normalized_file_name, content_type)
        file_type = _community_file_type(normalized_file_name, normalized_content_type)
        _ensure_community_file_supported(
            file_name=normalized_file_name,
            content_type=normalized_content_type,
            file_type=file_type,
        )
        file_id = uuid.uuid4()
        object_key = f"community/{user.id}/uploads/{file_id}-{normalized_file_name}"
        storage_url = upload_object_file(
            object_key=object_key,
            content=content,
            content_type=normalized_content_type,
            failure_detail="社区素材上传失败，请稍后再试",
        )
        uploaded_file = UploadedFile(
            id=file_id,
            user_id=user.id,
            file_name=file_name or normalized_file_name,
            file_type=file_type,
            mime_type=normalized_content_type,
            storage_key=object_key,
            storage_url=storage_url,
            file_size=len(content),
            checksum=hashlib.sha256(content).hexdigest(),
            metadata_={"source": "community_upload", "publication_state": "private"},
        )
        db.add(uploaded_file)
        uploaded_files.append(uploaded_file)
    db.commit()
    return [
        CommunityUploadedFileResponse(
            file_id=str(file.id),
            file_name=file.file_name,
            file_type=file.file_type,
            mime_type=file.mime_type,
            storage_url=file.storage_url,
            file_size=int(file.file_size),
        )
        for file in uploaded_files
    ]


def _get_post(db: Session, *, post_id: UUID) -> CommunityPost:
    post = db.scalar(select(CommunityPost).where(CommunityPost.id == post_id))
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")
    return post


def _get_owned_post(db: Session, *, user: User, post_id: UUID) -> CommunityPost:
    post = db.scalar(select(CommunityPost).where(CommunityPost.id == post_id, CommunityPost.author_id == user.id))
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在或无权操作")
    return post


def _get_owned_bookmark_collection(
    db: Session,
    *,
    user: User,
    collection_id: UUID,
) -> CommunityBookmarkCollection:
    collection = db.scalar(
        select(CommunityBookmarkCollection).where(
            CommunityBookmarkCollection.id == collection_id,
            CommunityBookmarkCollection.owner_id == user.id,
        )
    )
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="收藏夹不存在")
    return collection


def _get_owned_comment(db: Session, *, user: User, comment_id: UUID) -> CommunityComment:
    comment = db.scalar(select(CommunityComment).where(CommunityComment.id == comment_id, CommunityComment.author_id == user.id))
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评论不存在或无权操作")
    return comment


def _get_current_user_conversation(db: Session, *, user: User, conversation_id: UUID) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
            Conversation.status != "deleted",
        )
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    return conversation


def _ensure_post_readable(db: Session, *, post: CommunityPost, user: User) -> None:
    if post.author_id == user.id and post.status != "deleted":
        return
    blocked = db.scalar(
        select(CommunityUserBlock.id).where(
            or_(
                (CommunityUserBlock.blocker_id == user.id) & (CommunityUserBlock.blocked_id == post.author_id),
                (CommunityUserBlock.blocker_id == post.author_id) & (CommunityUserBlock.blocked_id == user.id),
            )
        )
    )
    if blocked is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")
    if post.status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子不存在")
    if post.visibility == "followers":
        follow = db.scalar(
            select(CommunityFollow.id).where(
                CommunityFollow.follower_id == user.id,
                CommunityFollow.followed_id == post.author_id,
            )
        )
        if follow is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅作者的关注者可查看")


def _ensure_post_interactable(*, post: CommunityPost) -> None:
    if post.status != "published":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="帖子暂不可互动")


def _sync_post_assets(
    db: Session,
    *,
    post: CommunityPost,
    user: User,
    file_ids: Iterable[UUID],
    cover_file_id: UUID | None,
) -> None:
    normalized_ids = list(dict.fromkeys(file_ids))
    if cover_file_id is not None and cover_file_id not in normalized_ids:
        normalized_ids.insert(0, cover_file_id)
    files = _get_owned_files(db, user=user, file_ids=normalized_ids)
    db.execute(delete(CommunityPostAsset).where(CommunityPostAsset.post_id == post.id))
    for index, file in enumerate(files):
        db.add(
            CommunityPostAsset(
                post_id=post.id,
                file_id=file.id,
                asset_role="cover" if file.id == cover_file_id else "attachment",
                sort_order=index,
            )
        )
    post.cover_file_id = cover_file_id if cover_file_id in {file.id for file in files} else None
    for file in files:
        metadata = dict(file.metadata_ or {})
        metadata["publication_state"] = "community_published"
        metadata["community_post_id"] = str(post.id)
        file.metadata_ = metadata
        db.add(file)
    db.add(post)


def _get_owned_files(db: Session, *, user: User, file_ids: Iterable[UUID]) -> list[UploadedFile]:
    requested_ids = list(dict.fromkeys(file_ids))
    if not requested_ids:
        return []
    found_files = list(
        db.scalars(
            select(UploadedFile).where(
                UploadedFile.id.in_(requested_ids),
                UploadedFile.user_id == user.id,
                UploadedFile.deleted_at.is_(None),
            )
        )
    )
    if len(found_files) != len(requested_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="包含无权发布的素材")
    by_id = {file.id: file for file in found_files}
    return [by_id[file_id] for file_id in requested_ids]


def _sync_post_tags(db: Session, *, post: CommunityPost, tag_names: Iterable[str]) -> None:
    existing_links = list(
        db.scalars(
            select(CommunityPostTag).where(CommunityPostTag.post_id == post.id)
        )
    )
    if existing_links:
        tag_ids = [link.tag_id for link in existing_links]
        existing_tags = list(db.scalars(select(CommunityTag).where(CommunityTag.id.in_(tag_ids))))
        for tag in existing_tags:
            tag.post_count = max(0, tag.post_count - 1)
            db.add(tag)
        db.execute(delete(CommunityPostTag).where(CommunityPostTag.post_id == post.id))

    normalized_names = list(dict.fromkeys(tag_names))
    for tag_name in normalized_names:
        tag = db.scalar(select(CommunityTag).where(CommunityTag.name == tag_name))
        if tag is None:
            tag = CommunityTag(name=tag_name, post_count=0)
            db.add(tag)
            db.flush()
        tag.post_count += 1
        db.add_all([tag, CommunityPostTag(post_id=post.id, tag_id=tag.id)])


def _conversation_attachment_ids(db: Session, *, conversation_id: UUID, requested_ids: list[UUID]) -> list[UUID]:
    if not requested_ids:
        return []
    rows = db.scalars(
        select(MessageFile.file_id)
        .join(Message, Message.id == MessageFile.message_id)
        .where(Message.conversation_id == conversation_id, MessageFile.file_id.in_(requested_ids))
    )
    found = list(rows)
    if len(found) != len(set(requested_ids)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="只能发布该对话中的素材")
    return requested_ids


def _post_response(db: Session, *, post: CommunityPost, viewer: User) -> CommunityPostResponse:
    author = db.scalar(select(User).where(User.id == post.author_id))
    if author is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="帖子作者不存在")
    tags = list(
        db.scalars(
            select(CommunityTag)
            .join(CommunityPostTag, CommunityPostTag.tag_id == CommunityTag.id)
            .where(CommunityPostTag.post_id == post.id)
            .order_by(CommunityTag.name.asc())
        )
    )
    tags = [tag for tag in tags if _is_displayable_community_tag(tag.name)]
    tag_counts = _active_topic_post_counts(db, tag_ids=[tag.id for tag in tags])
    asset_rows = db.execute(
        select(CommunityPostAsset, UploadedFile)
        .join(UploadedFile, UploadedFile.id == CommunityPostAsset.file_id)
        .where(CommunityPostAsset.post_id == post.id)
        .order_by(CommunityPostAsset.sort_order.asc())
    ).all()
    liked = db.scalar(
        select(CommunityPostLike.id).where(CommunityPostLike.post_id == post.id, CommunityPostLike.user_id == viewer.id)
    ) is not None
    bookmarked = db.scalar(
        select(CommunityPostBookmark.id).where(CommunityPostBookmark.post_id == post.id, CommunityPostBookmark.user_id == viewer.id)
    ) is not None
    case_updates = list(
        db.scalars(
            select(CommunityCaseUpdate)
            .where(CommunityCaseUpdate.post_id == post.id)
            .order_by(CommunityCaseUpdate.occurred_on.asc(), CommunityCaseUpdate.created_at.asc())
        )
    ) if post.post_type == "case" else []
    return CommunityPostResponse(
        id=str(post.id),
        title=post.title,
        content_markdown=post.content_markdown,
        excerpt=post.excerpt,
        post_type=post.post_type,
        visibility=post.visibility,
        status=post.status,
        source_conversation_id=str(post.source_conversation_id) if post.source_conversation_id else None,
        source_husbandry_case_id=str(post.source_husbandry_case_id) if post.source_husbandry_case_id else None,
        accepted_comment_id=str(post.accepted_comment_id) if post.accepted_comment_id else None,
        question_status=post.question_status,
        case_data=post.case_data or {},
        case_updates=[_case_update_response(db, update=item, viewer=viewer) for item in case_updates],
        author=_author_response(db, author=author, viewer=viewer),
        tags=[_tag_response(db, tag=tag, viewer=viewer, post_count=tag_counts.get(tag.id, 0)) for tag in tags],
        assets=[_asset_response(asset=asset, file=file) for asset, file in asset_rows],
        like_count=int(post.like_count),
        bookmark_count=int(post.bookmark_count),
        comment_count=int(post.comment_count),
        view_count=int(post.view_count),
        is_liked=liked,
        is_bookmarked=bookmarked,
        is_author=post.author_id == viewer.id,
        created_at=post.created_at,
        updated_at=post.updated_at,
        published_at=post.published_at,
    )


def _bookmark_collection_response(
    db: Session,
    *,
    collection: CommunityBookmarkCollection,
    post_id: UUID | None = None,
) -> CommunityBookmarkCollectionResponse:
    item_count = db.scalar(
        select(func.count()).select_from(CommunityBookmarkCollectionItem).where(
            CommunityBookmarkCollectionItem.collection_id == collection.id
        )
    ) or 0
    contains_post = False
    if post_id is not None:
        contains_post = db.scalar(
            select(CommunityBookmarkCollectionItem.id).where(
                CommunityBookmarkCollectionItem.collection_id == collection.id,
                CommunityBookmarkCollectionItem.post_id == post_id,
            )
        ) is not None
    return CommunityBookmarkCollectionResponse(
        id=str(collection.id),
        name=collection.name,
        description=collection.description,
        item_count=int(item_count),
        contains_post=contains_post,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def _comment_response(db: Session, *, comment: CommunityComment, viewer: User) -> CommunityCommentResponse:
    author = db.scalar(select(User).where(User.id == comment.author_id))
    if author is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="评论作者不存在")
    liked = db.scalar(
        select(CommunityCommentLike.id).where(
            CommunityCommentLike.comment_id == comment.id,
            CommunityCommentLike.user_id == viewer.id,
        )
    ) is not None
    accepted_comment_id = db.scalar(select(CommunityPost.accepted_comment_id).where(CommunityPost.id == comment.post_id))
    return CommunityCommentResponse(
        id=str(comment.id),
        post_id=str(comment.post_id),
        parent_comment_id=str(comment.parent_comment_id) if comment.parent_comment_id else None,
        content="该评论已删除" if comment.status == "deleted" else comment.content,
        status=comment.status,
        like_count=int(comment.like_count),
        is_liked=liked,
        is_author=comment.author_id == viewer.id,
        is_accepted=accepted_comment_id == comment.id,
        author=_author_response(db, author=author, viewer=viewer),
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


def _author_response(db: Session, *, author: User, viewer: User) -> CommunityAuthorResponse:
    followed = False
    if author.id != viewer.id:
        followed = db.scalar(
            select(CommunityFollow.id).where(
                CommunityFollow.follower_id == viewer.id,
                CommunityFollow.followed_id == author.id,
            )
        ) is not None
    display_name = author.display_name.strip() or author.username.strip() or "CanW 用户"
    profile = db.scalar(select(CommunityProfile).where(CommunityProfile.user_id == author.id))
    post_count = db.scalar(
        select(func.count()).select_from(CommunityPost).where(
            CommunityPost.author_id == author.id,
            CommunityPost.status == "published",
        )
    ) or 0
    follower_count = db.scalar(
        select(func.count()).select_from(CommunityFollow).where(CommunityFollow.followed_id == author.id)
    ) or 0
    following_count = db.scalar(
        select(func.count()).select_from(CommunityFollow).where(CommunityFollow.follower_id == author.id)
    ) or 0
    received_like_count = db.scalar(
        select(func.coalesce(func.sum(CommunityPost.like_count), 0)).where(
            CommunityPost.author_id == author.id,
            CommunityPost.status == "published",
        )
    ) or 0
    return CommunityAuthorResponse(
        id=str(author.id),
        display_name=display_name,
        username=author.username,
        avatar_url=author.avatar_url,
        role=author.role,
        is_followed=followed,
        identity_type=profile.identity_type if profile else ("technician" if author.role == "agritech" else "researcher" if author.role == "expert" else "farmer"),
        region=profile.region if profile else None,
        organization=profile.organization if profile else None,
        expertise_tags=list(profile.expertise_tags or []) if profile else [],
        years_experience=profile.years_experience if profile else None,
        bio=profile.bio if profile else None,
        verification_status=profile.verification_status if profile else ("verified" if author.role in {"agritech", "expert"} else "unverified"),
        post_count=int(post_count),
        follower_count=int(follower_count),
        following_count=int(following_count),
        received_like_count=int(received_like_count),
    )


def _case_update_response(
    db: Session,
    *,
    update: CommunityCaseUpdate,
    viewer: User,
) -> CommunityCaseUpdateResponse:
    author = db.scalar(select(User).where(User.id == update.author_id))
    if author is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="随访作者不存在")
    return CommunityCaseUpdateResponse(
        id=str(update.id),
        post_id=str(update.post_id),
        occurred_on=update.occurred_on,
        outcome_status=update.outcome_status,
        content=update.content,
        metrics=update.metrics or {},
        author=_author_response(db, author=author, viewer=viewer),
        created_at=update.created_at,
    )


def _asset_response(*, asset: CommunityPostAsset, file: UploadedFile) -> CommunityAssetResponse:
    return CommunityAssetResponse(
        id=str(asset.id),
        file_id=str(file.id),
        file_name=file.file_name,
        file_type=file.file_type,
        mime_type=file.mime_type,
        storage_url=file.storage_url,
        file_size=int(file.file_size),
        asset_role=asset.asset_role,
        sort_order=int(asset.sort_order),
    )


def _tag_response(
    db: Session,
    *,
    tag: CommunityTag,
    viewer: User,
    post_count: int | None = None,
) -> CommunityTagResponse:
    is_followed = db.scalar(
        select(CommunityTopicFollow.id).where(
            CommunityTopicFollow.user_id == viewer.id,
            CommunityTopicFollow.tag_id == tag.id,
        )
    ) is not None
    return CommunityTagResponse(
        id=str(tag.id),
        name=tag.name,
        post_count=int(tag.post_count if post_count is None else post_count),
        is_followed=is_followed,
    )


def _active_topic_post_counts(db: Session, *, tag_ids: Iterable[UUID]) -> dict[UUID, int]:
    unique_tag_ids = list(dict.fromkeys(tag_ids))
    if not unique_tag_ids:
        return {}
    rows = db.execute(
        select(CommunityPostTag.tag_id, func.count(CommunityPostTag.post_id))
        .join(CommunityPost, CommunityPost.id == CommunityPostTag.post_id)
        .where(
            CommunityPostTag.tag_id.in_(unique_tag_ids),
            CommunityPost.status == "published",
        )
        .group_by(CommunityPostTag.tag_id)
    ).all()
    return {tag_id: int(post_count) for tag_id, post_count in rows}


def _is_displayable_community_tag(name: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", name))


def _notification_response(
    db: Session,
    *,
    notification: CommunityNotification,
    viewer: User,
) -> CommunityNotificationResponse:
    actor = db.scalar(select(User).where(User.id == notification.actor_user_id)) if notification.actor_user_id else None
    return CommunityNotificationResponse(
        id=str(notification.id),
        notification_type=notification.notification_type,
        post_id=str(notification.post_id) if notification.post_id else None,
        comment_id=str(notification.comment_id) if notification.comment_id else None,
        actor=_author_response(db, author=actor, viewer=viewer) if actor else None,
        payload=notification.payload,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


def _create_notification(
    db: Session,
    *,
    user_id: UUID,
    actor_user_id: UUID | None,
    notification_type: str,
    post_id: UUID | None = None,
    comment_id: UUID | None = None,
    payload: dict | None = None,
) -> None:
    normalized_payload = payload or {}
    db.add(
        CommunityNotification(
            user_id=user_id,
            actor_user_id=actor_user_id,
            post_id=post_id,
            comment_id=comment_id,
            notification_type=notification_type,
            payload=normalized_payload,
        )
    )
    community_event_broker.publish(
        user_id,
        {
            "type": "notification",
            "notification_type": notification_type,
            "post_id": str(post_id) if post_id else None,
            "comment_id": str(comment_id) if comment_id else None,
            "payload": normalized_payload,
        },
    )


def _record_interaction(
    db: Session,
    *,
    user_id: UUID,
    post_id: UUID,
    event_type: str,
) -> None:
    db.add(CommunityInteractionEvent(user_id=user_id, post_id=post_id, event_type=event_type))


def _ensure_community_content_allowed(content: str) -> None:
    normalized = " ".join(content.split())
    if any(pattern.search(normalized) for pattern in COMMUNITY_SENSITIVE_CONTACT_PATTERNS):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="为保护社区成员，请移除手机号、微信号等联系方式后再发布。",
        )


def _ensure_post_submission_allowed(db: Session, *, user: User, title: str, content: str) -> None:
    cutoff = now_utc() - timedelta(minutes=10)
    recent_count = db.scalar(
        select(func.count()).select_from(CommunityPost).where(
            CommunityPost.author_id == user.id,
            CommunityPost.created_at >= cutoff,
        )
    ) or 0
    if recent_count >= 5:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="10 分钟内最多发布 5 条帖子，请稍后再试。")
    duplicate = db.scalar(
        select(CommunityPost.id).where(
            CommunityPost.author_id == user.id,
            CommunityPost.status != "deleted",
            CommunityPost.created_at >= now_utc() - timedelta(hours=24),
            CommunityPost.title == title,
            CommunityPost.content_markdown == content,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="检测到相同内容已发布，请编辑原帖或补充新的观察后再发布。")


def _ensure_comment_submission_allowed(db: Session, *, user: User, content: str) -> None:
    cutoff = now_utc() - timedelta(minutes=10)
    recent_count = db.scalar(
        select(func.count()).select_from(CommunityComment).where(
            CommunityComment.author_id == user.id,
            CommunityComment.created_at >= cutoff,
        )
    ) or 0
    if recent_count >= 20:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="评论过于频繁，请稍后再试。")
    duplicate = db.scalar(
        select(CommunityComment.id).where(
            CommunityComment.author_id == user.id,
            CommunityComment.status == "active",
            CommunityComment.created_at >= now_utc() - timedelta(minutes=5),
            CommunityComment.content == content,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请勿重复发布相同评论。")


def _ensure_direct_message_submission_allowed(
    db: Session,
    *,
    user: User,
    target_user_id: UUID,
    content: str,
) -> None:
    cutoff = now_utc() - timedelta(minutes=10)
    recent_count = db.scalar(
        select(func.count()).select_from(CommunityDirectMessage).where(
            CommunityDirectMessage.sender_id == user.id,
            CommunityDirectMessage.created_at >= cutoff,
        )
    ) or 0
    if recent_count >= 30:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="私信发送过于频繁，请稍后再试。")
    duplicate = db.scalar(
        select(CommunityDirectMessage.id).where(
            CommunityDirectMessage.sender_id == user.id,
            CommunityDirectMessage.recipient_id == target_user_id,
            CommunityDirectMessage.status == "active",
            CommunityDirectMessage.created_at >= now_utc() - timedelta(minutes=2),
            CommunityDirectMessage.content == content,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请勿向同一用户重复发送相同私信。")


def _diversify_recommended_posts(posts: list[CommunityPost]) -> list[CommunityPost]:
    """Avoid showing more than two consecutive posts from the same author."""

    remaining = list(posts)
    diversified: list[CommunityPost] = []
    while remaining:
        candidate_index = next(
            (
                index
                for index, candidate in enumerate(remaining)
                if len(diversified) < 2
                or candidate.author_id != diversified[-1].author_id
                or candidate.author_id != diversified[-2].author_id
            ),
            0,
        )
        diversified.append(remaining.pop(candidate_index))
    return diversified


def _notify_mentions(
    db: Session,
    *,
    actor: User,
    content: str,
    post_id: UUID | None = None,
    comment_id: UUID | None = None,
) -> None:
    usernames = {name.lower() for name in re.findall(r"(?<![\w@])@([A-Za-z0-9_-]{1,32})", content)}
    if not usernames:
        return
    mentioned_users = db.scalars(
        select(User).where(
            func.lower(User.username).in_(usernames),
            User.status == "active",
            User.id != actor.id,
        )
    ).all()
    for mentioned_user in mentioned_users:
        if _users_are_blocked(db, first_user_id=actor.id, second_user_id=mentioned_user.id):
            continue
        _create_notification(
            db,
            user_id=mentioned_user.id,
            actor_user_id=actor.id,
            post_id=post_id,
            comment_id=comment_id,
            notification_type="mention",
        )


def _users_are_blocked(db: Session, *, first_user_id: UUID, second_user_id: UUID) -> bool:
    return db.scalar(
        select(CommunityUserBlock.id).where(
            or_(
                (CommunityUserBlock.blocker_id == first_user_id) & (CommunityUserBlock.blocked_id == second_user_id),
                (CommunityUserBlock.blocker_id == second_user_id) & (CommunityUserBlock.blocked_id == first_user_id),
            )
        )
    ) is not None


def _ensure_users_can_interact(db: Session, *, user_id: UUID, target_user_id: UUID) -> None:
    if user_id != target_user_id and _users_are_blocked(db, first_user_id=user_id, second_user_id=target_user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")


def _direct_thread_pair(first_user_id: UUID, second_user_id: UUID) -> tuple[UUID, UUID]:
    return (first_user_id, second_user_id) if str(first_user_id) < str(second_user_id) else (second_user_id, first_user_id)


def _get_community_direct_thread(db: Session, *, user: User, thread_id: UUID) -> CommunityDirectThread:
    thread = db.scalar(select(CommunityDirectThread).where(CommunityDirectThread.id == thread_id))
    if thread is None or user.id not in {thread.participant_one_id, thread.participant_two_id}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="私信会话不存在")
    counterpart_id = thread.participant_two_id if thread.participant_one_id == user.id else thread.participant_one_id
    _ensure_users_can_interact(db, user_id=user.id, target_user_id=counterpart_id)
    return thread


def _ensure_direct_message_permission(db: Session, *, user: User, target: User) -> None:
    connected = db.scalar(
        select(CommunityFollow.id).where(
            or_(
                (CommunityFollow.follower_id == user.id) & (CommunityFollow.followed_id == target.id),
                (CommunityFollow.follower_id == target.id) & (CommunityFollow.followed_id == user.id),
            )
        )
    ) is not None
    if not connected and target.role not in {"admin", "agritech", "expert"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="请先关注对方后再私信")


def _direct_message_response(*, message: CommunityDirectMessage, viewer: User) -> CommunityDirectMessageResponse:
    return CommunityDirectMessageResponse(
        id=str(message.id),
        thread_id=str(message.thread_id),
        sender_id=str(message.sender_id),
        recipient_id=str(message.recipient_id),
        content="该消息已删除" if message.status == "deleted" else message.content,
        status=message.status,
        is_mine=message.sender_id == viewer.id,
        read_at=message.read_at,
        created_at=message.created_at,
    )


def _excerpt(content_markdown: str) -> str:
    plain_text = re.sub(r"[`#>*_\[\]()-]", " ", content_markdown)
    plain_text = " ".join(plain_text.split())
    return plain_text[:180]


def _content_type_for_community_file(file_name: str, content_type: str) -> str:
    normalized = (content_type or "").strip().lower()
    if normalized and normalized != "application/octet-stream":
        return normalized
    guessed_type, _ = mimetypes.guess_type(file_name)
    return (guessed_type or "application/octet-stream").lower()


def _community_file_type(file_name: str, content_type: str) -> str:
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("video/"):
        return "video"
    extension = _file_extension(file_name)
    if content_type in COMMUNITY_DOCUMENT_MIME_TYPES or content_type.startswith("text/") or extension in COMMUNITY_DOCUMENT_EXTENSIONS:
        return "document"
    return "other"


def _ensure_community_file_supported(*, file_name: str, content_type: str, file_type: str) -> None:
    if file_type in {"image", "video", "document"}:
        return
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的社区素材格式：{file_name}")


def _file_extension(file_name: str) -> str:
    match = re.search(r"(\.[A-Za-z0-9]+)$", file_name or "")
    return match.group(1).lower() if match else ""


def _safe_file_name(file_name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", file_name.strip())
    normalized = normalized.strip(".-")
    return normalized[:160] or "attachment"

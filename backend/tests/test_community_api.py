from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select

from app.db.session import SessionLocal, check_database_connection
from app.main import app
from app.models import AuthSession, AuthVerificationCode, LoginEvent, User, UserIdentity


client = TestClient(app)
AUTHOR_EMAIL = "codex-community-author@qq.com"
READER_EMAIL = "codex-community-reader@qq.com"
MODERATOR_EMAIL = "codex-community-moderator@qq.com"


def test_community_routes_require_login() -> None:
    response = client.get("/api/v1/community/feed")

    assert response.status_code == 401


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_community_post_comment_collection_and_history_flow() -> None:
    _cleanup_identity_auth_data(AUTHOR_EMAIL)
    _cleanup_identity_auth_data(READER_EMAIL)
    try:
        author_login = _login_with_email_dev_code(AUTHOR_EMAIL)
        reader_login = _login_with_email_dev_code(READER_EMAIL)
        author_headers = {"Authorization": f"Bearer {author_login['access_token']}"}
        reader_headers = {"Authorization": f"Bearer {reader_login['access_token']}"}

        post_response = client.post(
            "/api/v1/community/posts",
            headers=author_headers,
            json={
                "title": "五龄管理观察记录",
                "content_markdown": "上午给桑后食桑正常，午后加强了通风。",
                "post_type": "experience",
                "visibility": "public",
                "tags": [],
                "file_ids": [],
                "publish": True,
            },
        )
        assert post_response.status_code == 201
        post_id = post_response.json()["id"]

        draft_response = client.post(
            "/api/v1/community/posts",
            headers=author_headers,
            json={
                "title": "五龄管理待补充草稿",
                "content_markdown": "等补充晚间温湿度后再发布。",
                "post_type": "experience",
                "visibility": "public",
                "tags": [],
                "file_ids": [],
                "publish": False,
            },
        )
        assert draft_response.status_code == 201
        draft_id = draft_response.json()["id"]
        mine_response = client.get("/api/v1/community/feed?tab=mine", headers=author_headers)
        assert mine_response.status_code == 200
        assert post_id in [item["id"] for item in mine_response.json()["items"]]
        assert draft_id not in [item["id"] for item in mine_response.json()["items"]]
        drafts_response = client.get("/api/v1/community/feed?tab=drafts", headers=author_headers)
        assert draft_id in [item["id"] for item in drafts_response.json()["items"]]

        author_view_response = client.get(f"/api/v1/community/posts/{post_id}", headers=author_headers)
        assert author_view_response.status_code == 200
        author_history_response = client.get("/api/v1/community/feed?tab=history", headers=author_headers)
        assert [item["id"] for item in author_history_response.json()["items"]] == [post_id]

        comment_response = client.post(
            f"/api/v1/community/posts/{post_id}/comments",
            headers=author_headers,
            json={"content": "后续会继续记录温湿度变化。", "parent_comment_id": None},
        )
        assert comment_response.status_code == 201
        comment_id = comment_response.json()["id"]

        edit_response = client.patch(
            f"/api/v1/community/comments/{comment_id}",
            headers=author_headers,
            json={"content": "后续会持续记录温湿度和食桑变化。"},
        )
        assert edit_response.status_code == 200
        assert edit_response.json()["content"] == "后续会持续记录温湿度和食桑变化。"

        delete_comment_response = client.delete(f"/api/v1/community/comments/{comment_id}", headers=author_headers)
        assert delete_comment_response.status_code == 204
        comments_response = client.get(f"/api/v1/community/posts/{post_id}/comments", headers=author_headers)
        assert comments_response.status_code == 200
        assert comments_response.json()["items"][0]["status"] == "deleted"
        assert comments_response.json()["items"][0]["content"] == "该评论已删除"

        create_collection_response = client.post(
            "/api/v1/community/collections",
            headers=author_headers,
            json={"name": "五龄资料", "description": "用于回看管理经验"},
        )
        assert create_collection_response.status_code == 201
        collection_id = create_collection_response.json()["id"]

        add_to_collection_response = client.post(
            f"/api/v1/community/collections/{collection_id}/posts/{post_id}",
            headers=author_headers,
        )
        assert add_to_collection_response.status_code == 200
        assert add_to_collection_response.json()["contains_post"] is True
        assert add_to_collection_response.json()["item_count"] == 1

        collection_detail_response = client.get(
            f"/api/v1/community/collections/{collection_id}",
            headers=author_headers,
        )
        assert collection_detail_response.status_code == 200
        assert collection_detail_response.json()["posts"][0]["id"] == post_id

        reader_view_response = client.get(f"/api/v1/community/posts/{post_id}", headers=reader_headers)
        assert reader_view_response.status_code == 200
        history_before_clear = client.get("/api/v1/community/feed?tab=history", headers=reader_headers)
        assert history_before_clear.status_code == 200
        assert [item["id"] for item in history_before_clear.json()["items"]] == [post_id]

        clear_history_response = client.delete("/api/v1/community/history", headers=reader_headers)
        assert clear_history_response.status_code == 204
        history_after_clear = client.get("/api/v1/community/feed?tab=history", headers=reader_headers)
        assert history_after_clear.status_code == 200
        assert history_after_clear.json()["items"] == []

        delete_collection_response = client.delete(f"/api/v1/community/collections/{collection_id}", headers=author_headers)
        assert delete_collection_response.status_code == 204
    finally:
        _cleanup_identity_auth_data(AUTHOR_EMAIL)
        _cleanup_identity_auth_data(READER_EMAIL)


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_community_social_interaction_and_moderation_flow() -> None:
    _cleanup_identity_auth_data(AUTHOR_EMAIL)
    _cleanup_identity_auth_data(READER_EMAIL)
    _cleanup_identity_auth_data(MODERATOR_EMAIL)
    try:
        author_login = _login_with_email_dev_code(AUTHOR_EMAIL)
        reader_login = _login_with_email_dev_code(READER_EMAIL)
        moderator_login = _login_with_email_dev_code(MODERATOR_EMAIL)
        _set_user_role(MODERATOR_EMAIL, "admin")
        author_headers = {"Authorization": f"Bearer {author_login['access_token']}"}
        reader_headers = {"Authorization": f"Bearer {reader_login['access_token']}"}
        moderator_headers = {"Authorization": f"Bearer {moderator_login['access_token']}"}

        profile_response = client.put(
            "/api/v1/community/profile",
            headers=author_headers,
            json={
                "identity_type": "technician",
                "region": "Zhejiang",
                "organization": "Community Test Farm",
                "expertise_tags": ["ventilation", "feeding"],
                "years_experience": 8,
                "bio": "Field observations and practical husbandry notes.",
                "request_verification": True,
            },
        )
        assert profile_response.status_code == 200
        author = profile_response.json()
        author_id = author["id"]
        assert author["region"] == "Zhejiang"
        assert author["identity_type"] == "technician"

        post_response = client.post(
            "/api/v1/community/posts",
            headers=author_headers,
            json={
                "title": "Ventilation field question",
                "content_markdown": "What indicators should be tracked after improving ventilation?",
                "post_type": "question",
                "visibility": "public",
                "tags": ["community-flow-ventilation-test", "feeding-test"],
                "file_ids": [],
                "publish": True,
            },
        )
        assert post_response.status_code == 201
        post = post_response.json()
        post_id = post["id"]
        invalid_tag_response = client.post(
            "/api/v1/community/posts",
            headers=author_headers,
            json={
                "title": "Invalid tag validation",
                "content_markdown": "A punctuation-only topic label must be rejected.",
                "post_type": "experience",
                "visibility": "public",
                "tags": ["????"],
                "file_ids": [],
                "publish": True,
            },
        )
        assert invalid_tag_response.status_code == 422
        duplicate_post_response = client.post(
            "/api/v1/community/posts",
            headers=author_headers,
            json={
                "title": "Ventilation field question",
                "content_markdown": "What indicators should be tracked after improving ventilation?",
                "post_type": "question",
                "visibility": "public",
                "tags": ["community-flow-ventilation-test", "feeding-test"],
                "file_ids": [],
                "publish": True,
            },
        )
        assert duplicate_post_response.status_code == 409

        search_response = client.get("/api/v1/community/search?q=Ventilation", headers=reader_headers)
        assert search_response.status_code == 200
        assert post_id in [item["id"] for item in search_response.json()["posts"]]

        tags_response = client.get("/api/v1/community/tags", headers=reader_headers)
        assert tags_response.status_code == 200
        topic = next(item for item in tags_response.json() if item["name"] == "community-flow-ventilation-test")
        follow_topic_response = client.post(
            f"/api/v1/community/tags/{topic['id']}/follow",
            headers=reader_headers,
        )
        assert follow_topic_response.status_code == 200
        assert follow_topic_response.json()["is_followed"] is True
        topic_feed_response = client.get("/api/v1/community/feed?tab=topics", headers=reader_headers)
        assert topic_feed_response.status_code == 200
        assert post_id in [item["id"] for item in topic_feed_response.json()["items"]]
        recommended_feed_response = client.get("/api/v1/community/feed?tab=recommended", headers=reader_headers)
        assert recommended_feed_response.status_code == 200
        recommended_post = next(item for item in recommended_feed_response.json()["items"] if item["id"] == post_id)
        assert recommended_post["recommendation_reason"]

        follow_response = client.post(f"/api/v1/community/users/{author_id}/follow", headers=reader_headers)
        assert follow_response.status_code == 200
        assert follow_response.json()["is_followed"] is True
        profile_posts_response = client.get(f"/api/v1/community/users/{author_id}/posts", headers=reader_headers)
        assert profile_posts_response.status_code == 200
        assert post_id in [item["id"] for item in profile_posts_response.json()["posts"]]
        relationships_response = client.get(
            f"/api/v1/community/users/{author_id}/relationships?relationship_type=followers",
            headers=author_headers,
        )
        assert relationships_response.status_code == 200
        assert reader_login["user"]["id"] in [item["id"] for item in relationships_response.json()["items"]]

        direct_message_response = client.post(
            f"/api/v1/community/users/{author_id}/direct-messages",
            headers=reader_headers,
            json={"content": "Could you share the next observation checkpoint?"},
        )
        assert direct_message_response.status_code == 201
        thread_id = direct_message_response.json()["thread_id"]
        thread_response = client.get("/api/v1/community/direct/threads", headers=author_headers)
        assert thread_response.status_code == 200
        assert thread_id in [item["id"] for item in thread_response.json()["items"]]
        messages_response = client.get(
            f"/api/v1/community/direct/threads/{thread_id}/messages",
            headers=author_headers,
        )
        assert messages_response.status_code == 200
        assert messages_response.json()["items"][0]["content"] == "Could you share the next observation checkpoint?"

        like_response = client.post(f"/api/v1/community/posts/{post_id}/like", headers=reader_headers)
        assert like_response.status_code == 200
        assert like_response.json()["is_liked"] is True
        bookmark_response = client.post(f"/api/v1/community/posts/{post_id}/bookmark", headers=reader_headers)
        assert bookmark_response.status_code == 200
        assert bookmark_response.json()["is_bookmarked"] is True
        assert post_id in [
            item["id"]
            for item in client.get("/api/v1/community/feed?tab=liked", headers=reader_headers).json()["items"]
        ]
        assert post_id in [
            item["id"]
            for item in client.get("/api/v1/community/feed?tab=bookmarked", headers=reader_headers).json()["items"]
        ]

        comment_response = client.post(
            f"/api/v1/community/posts/{post_id}/comments",
            headers=reader_headers,
            json={"content": "Track temperature, humidity, feeding activity, and recovery trend.", "parent_comment_id": None},
        )
        assert comment_response.status_code == 201
        comment_id = comment_response.json()["id"]
        comment_like_response = client.post(f"/api/v1/community/comments/{comment_id}/like", headers=author_headers)
        assert comment_like_response.status_code == 200
        assert comment_like_response.json()["like_count"] == 1
        accept_response = client.post(
            f"/api/v1/community/posts/{post_id}/answers/{comment_id}/accept",
            headers=author_headers,
        )
        assert accept_response.status_code == 200
        assert accept_response.json()["question_status"] == "resolved"
        comments_response = client.get(f"/api/v1/community/posts/{post_id}/comments", headers=reader_headers)
        assert comments_response.status_code == 200
        assert comments_response.json()["items"][0]["is_accepted"] is True

        overview_response = client.get("/api/v1/community/creator/overview", headers=author_headers)
        assert overview_response.status_code == 200
        assert overview_response.json()["post_count"] == 1
        notifications_response = client.get("/api/v1/community/notifications", headers=author_headers)
        assert notifications_response.status_code == 200
        notification_types = {item["notification_type"] for item in notifications_response.json()["items"]}
        assert {"follow", "direct_message", "post_like", "post_comment"}.issubset(notification_types)
        read_response = client.post("/api/v1/community/notifications/read", headers=author_headers)
        assert read_response.status_code == 204
        assert client.get("/api/v1/community/notifications", headers=author_headers).json()["unread_count"] == 0

        report_response = client.post(
            f"/api/v1/community/posts/{post_id}/reports",
            headers=reader_headers,
            json={"target_type": "post", "reason": "needs review", "detail": "Regression-test moderation workflow."},
        )
        assert report_response.status_code == 204
        duplicate_report_response = client.post(
            f"/api/v1/community/posts/{post_id}/reports",
            headers=reader_headers,
            json={"target_type": "post", "reason": "needs review", "detail": "Duplicate report must be rejected."},
        )
        assert duplicate_report_response.status_code == 409
        # User-facing APIs only submit reports. Review decisions must be made
        # through the dedicated administrator service, where RBAC and auditing
        # are enforced together.
        legacy_moderation_response = client.get("/api/v1/community/moderation/reports?report_status=pending", headers=moderator_headers)
        assert legacy_moderation_response.status_code == 404

        hide_response = client.post(f"/api/v1/community/posts/{post_id}/not-interested", headers=reader_headers)
        assert hide_response.status_code == 200
        assert hide_response.json() == {"hidden": True}
        latest_response = client.get("/api/v1/community/feed?tab=latest", headers=reader_headers)
        assert latest_response.status_code == 200
        assert post_id not in [item["id"] for item in latest_response.json()["items"]]
        reset_recommendations_response = client.delete("/api/v1/community/recommendations", headers=reader_headers)
        assert reset_recommendations_response.status_code == 204
        restored_latest_response = client.get("/api/v1/community/feed?tab=latest", headers=reader_headers)
        assert post_id in [item["id"] for item in restored_latest_response.json()["items"]]

        block_response = client.post(f"/api/v1/community/users/{author_id}/block", headers=reader_headers)
        assert block_response.status_code == 200
        assert block_response.json() == {"blocked": True}
        blocked_users_response = client.get("/api/v1/community/blocked-users", headers=reader_headers)
        assert blocked_users_response.status_code == 200
        assert author_id in [item["id"] for item in blocked_users_response.json()["items"]]
        unblock_response = client.post(f"/api/v1/community/users/{author_id}/block", headers=reader_headers)
        assert unblock_response.status_code == 200
        assert unblock_response.json() == {"blocked": False}
        restored_blocked_users_response = client.get("/api/v1/community/blocked-users", headers=reader_headers)
        assert author_id not in [item["id"] for item in restored_blocked_users_response.json()["items"]]

        delete_post_response = client.delete(f"/api/v1/community/posts/{post_id}", headers=author_headers)
        assert delete_post_response.status_code == 204
        tags_after_delete = client.get("/api/v1/community/tags", headers=reader_headers)
        assert "community-flow-ventilation-test" not in [item["name"] for item in tags_after_delete.json()]
    finally:
        _cleanup_identity_auth_data(AUTHOR_EMAIL)
        _cleanup_identity_auth_data(READER_EMAIL)
        _cleanup_identity_auth_data(MODERATOR_EMAIL)


def _login_with_email_dev_code(email: str) -> dict:
    code_response = client.post("/api/v1/auth/email/verification-codes", json={"email": email})
    assert code_response.status_code == 200
    login_response = client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "code": code_response.json()["dev_code"], "device_name": "community-api-pytest"},
    )
    assert login_response.status_code == 200
    return login_response.json()


def _set_user_role(email: str, role: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(
            select(User)
            .join(UserIdentity, UserIdentity.user_id == User.id)
            .where(UserIdentity.provider == "email", UserIdentity.provider_subject == email)
        )
        assert user is not None
        user.role = role
        db.add(user)
        db.commit()


def _cleanup_identity_auth_data(email: str) -> None:
    with SessionLocal() as db:
        user_ids = list(
            db.scalars(
                select(UserIdentity.user_id).where(
                    UserIdentity.provider == "email",
                    UserIdentity.provider_subject == email,
                )
            )
        )
        login_event_filter = LoginEvent.target == email
        if user_ids:
            login_event_filter = or_(login_event_filter, LoginEvent.user_id.in_(user_ids))
        db.execute(delete(LoginEvent).where(login_event_filter))
        db.execute(delete(AuthVerificationCode).where(AuthVerificationCode.target == email))
        if user_ids:
            db.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
            db.execute(delete(UserIdentity).where(UserIdentity.user_id.in_(user_ids)))
            db.execute(delete(User).where(User.id.in_(user_ids)))
        db.commit()

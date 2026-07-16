import pytest
from pydantic import ValidationError
from fastapi import HTTPException

from app.schemas.community import (
    CommunityCreatorOverviewResponse,
    CommunityDirectMessageCreateRequest,
    CommunityBookmarkCollectionCreateRequest,
    CommunityRelationshipListResponse,
    CommunityTagResponse,
)
from app.services.community_service import _ensure_community_content_allowed


def test_direct_message_payload_is_trimmed_and_rejects_blank_content() -> None:
    payload = CommunityDirectMessageCreateRequest(content="  请问这个批次后续恢复得怎么样？  ")

    assert payload.content == "请问这个批次后续恢复得怎么样？"

    with pytest.raises(ValidationError):
        CommunityDirectMessageCreateRequest(content="   ")


def test_topic_response_keeps_follow_state_for_current_user() -> None:
    topic = CommunityTagResponse(id="topic-1", name="病害防控", post_count=12, is_followed=True)

    assert topic.is_followed is True
    assert topic.post_count == 12


def test_creator_overview_exposes_operational_metrics() -> None:
    overview = CommunityCreatorOverviewResponse(
        post_count=8,
        published_this_week=2,
        view_count=320,
        received_like_count=46,
        bookmark_count=19,
        comment_count=12,
        follower_count=31,
        following_count=18,
    )

    assert overview.published_this_week == 2
    assert overview.follower_count == 31
    assert overview.following_count == 18


def test_relationship_response_keeps_followers_and_following_separate() -> None:
    author = {
        "id": "user-1",
        "display_name": "养蚕人",
        "username": "farmer",
        "role": "user",
    }
    response = CommunityRelationshipListResponse(
        author=author,
        relationship_type="followers",
        items=[{**author, "id": "user-2", "display_name": "农技员", "username": "tech"}],
    )

    assert response.relationship_type == "followers"
    assert response.items[0].id == "user-2"


def test_bookmark_collection_payload_normalizes_name_and_description() -> None:
    collection = CommunityBookmarkCollectionCreateRequest(
        name="  五龄管理资料  ",
        description="  温湿度、给桑与异常观察  ",
    )

    assert collection.name == "五龄管理资料"
    assert collection.description == "温湿度、给桑与异常观察"


def test_community_content_guard_rejects_contact_details() -> None:
    with pytest.raises(HTTPException) as error:
        _ensure_community_content_allowed("加我微信：canwen_2026，方便继续交流")

    assert error.value.status_code == 422

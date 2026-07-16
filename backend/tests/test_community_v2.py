from datetime import date

from app.schemas.community import (
    CommunityCaseUpdateCreateRequest,
    CommunityPostCreateRequest,
    CommunityProfileUpdateRequest,
)


def test_structured_case_post_payload_preserves_case_data() -> None:
    payload = CommunityPostCreateRequest(
        title=" 五龄蚕食桑减少病例 ",
        content_markdown="现场观察记录",
        post_type="case",
        tags=[" 病例 ", "#五龄", "病例"],
        case_data={"instar": "五龄第 3 天", "symptoms": "食桑减少"},
    )

    assert payload.title == "五龄蚕食桑减少病例"
    assert payload.tags == ["病例", "五龄"]
    assert payload.case_data["symptoms"] == "食桑减少"


def test_case_update_supports_outcome_timeline() -> None:
    payload = CommunityCaseUpdateCreateRequest(
        occurred_on=date(2026, 7, 11),
        outcome_status="improved",
        content=" 调整通风后食桑量恢复。 ",
    )

    assert payload.content == "调整通风后食桑量恢复。"
    assert payload.outcome_status == "improved"


def test_professional_profile_normalizes_expertise() -> None:
    payload = CommunityProfileUpdateRequest(
        identity_type="technician",
        expertise_tags=[" 病害防控 ", "病害防控", "小蚕共育"],
        request_verification=True,
    )

    assert payload.expertise_tags == ["病害防控", "小蚕共育"]
    assert payload.request_verification is True

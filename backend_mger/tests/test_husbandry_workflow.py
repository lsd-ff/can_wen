import json

from app.models import ExpertReview, WorkItem
from app.routes.reviews import _create_husbandry_review_notification
from app.schemas import HusbandryReviewRequest


def test_husbandry_review_requires_a_current_version() -> None:
    review = HusbandryReviewRequest(
        expected_version=3,
        risk_level="high",
        conclusion="需要继续观察隔离效果",
        recommendation="完成处置后记录一次随访",
        evidence=[{"type": "case_asset", "file_name": "case.jpg"}],
        reason="依据现场材料完成复核",
    )

    assert review.expected_version == 3
    assert review.evidence[0]["file_name"] == "case.jpg"


def test_husbandry_models_define_database_level_deduplication() -> None:
    work_item_indexes = {index.name: index for index in WorkItem.__table__.indexes}
    review_indexes = {index.name: index for index in ExpertReview.__table__.indexes}

    assert work_item_indexes["uq_work_items_active_resource"].unique
    assert review_indexes["uq_expert_reviews_husbandry_case_version"].unique


def test_published_husbandry_review_creates_user_notification_payload() -> None:
    executed: list[tuple[object, dict[str, object]]] = []

    class FakeSession:
        def execute(self, statement: object, params: dict[str, object]) -> None:
            executed.append((statement, params))

    _create_husbandry_review_notification(
        FakeSession(),  # type: ignore[arg-type]
        user_id="11111111-1111-1111-1111-111111111111",
        case_id="22222222-2222-2222-2222-222222222222",  # type: ignore[arg-type]
        review_id="33333333-3333-3333-3333-333333333333",  # type: ignore[arg-type]
        version=2,
        conclusion="  建议隔离异常蚕并完成后续随访。  ",
    )

    payload = json.loads(str(executed[0][1]["payload"]))
    assert payload["kind"] == "husbandry_expert_review"
    assert payload["review_version"] == 2
    assert "完成后续随访" in payload["message"]

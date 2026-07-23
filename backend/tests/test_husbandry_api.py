from datetime import date
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select, text

from app.db.session import SessionLocal, check_database_connection
from app.main import app
from app.models import (
    AuthSession,
    AuthVerificationCode,
    Conversation,
    ExpertReview,
    Farm,
    HusbandryCase,
    LoginEvent,
    Project,
    User,
    UserIdentity,
)
from app.core.security import now_utc


client = TestClient(app)
TEST_EMAIL = "codex-husbandry-api@qq.com"


def test_husbandry_routes_require_login() -> None:
    response = client.get("/api/v1/husbandry/dashboard")

    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_high_risk_case_creates_exactly_one_active_review_task() -> None:
    """The database trigger must be immediate and idempotent, not UI-driven."""
    with SessionLocal() as db:
        try:
            user = User(display_name="husbandry trigger test", username="husbandry-trigger-test")
            db.add(user)
            db.flush()
            farm = Farm(owner_id=user.id, name="trigger test farm", status="active")
            db.add(farm)
            db.flush()
            case = HusbandryCase(
                owner_id=user.id,
                farm_id=farm.id,
                title="trigger test case",
                occurred_on=date.today(),
                severity="high",
                status="suspected",
            )
            db.add(case)
            db.flush()
            case.severity = "critical"
            db.flush()
            active_count = int(db.execute(text("""
                SELECT count(*) FROM admin.work_items
                 WHERE resource_type = 'husbandry_case'
                   AND resource_id = :case_id
                   AND status IN ('open', 'claimed')
            """), {"case_id": str(case.id)}).scalar() or 0)
            assert active_count == 1
        finally:
            db.rollback()


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_husbandry_record_case_and_follow_up_flow() -> None:
    _cleanup_identity_auth_data("email", TEST_EMAIL)
    try:
        login = _login_with_email_dev_code(TEST_EMAIL)
        headers = {"Authorization": f"Bearer {login['access_token']}"}

        farm_response = client.post(
            "/api/v1/husbandry/farms",
            headers=headers,
            json={"name": "测试蚕室", "location": "湖州", "notes": "通风良好"},
        )
        assert farm_response.status_code == 201
        farm = farm_response.json()
        assert farm["name"] == "测试蚕室"

        batch_response = client.post(
            "/api/v1/husbandry/batches",
            headers=headers,
            json={
                "farm_id": farm["id"],
                "batch_code": "2026-夏蚕-A01",
                "variety": "菁松×皓月",
                "instar": "五龄",
                "start_date": "2026-07-01",
                "population_count": 12000,
            },
        )
        assert batch_response.status_code == 201
        batch = batch_response.json()
        assert batch["farm_name"] == "测试蚕室"
        assert batch["instar"] == "五龄"

        record_response = client.put(
            f"/api/v1/husbandry/batches/{batch['id']}/daily-records",
            headers=headers,
            json={
                "record_date": "2026-07-10",
                "temperature_celsius": 27.5,
                "humidity_percent": 79,
                "feedings": 4,
                "sick_count": 3,
                "death_count": 1,
                "observations": "发现少量体色发白的五龄蚕。",
            },
        )
        assert record_response.status_code == 200
        assert record_response.json()["temperature_celsius"] == 27.5

        record_update_response = client.put(
            f"/api/v1/husbandry/batches/{batch['id']}/daily-records",
            headers=headers,
            json={"record_date": "2026-07-10", "temperature_celsius": 28, "death_count": 2},
        )
        assert record_update_response.status_code == 200
        assert record_update_response.json()["death_count"] == 2

        with SessionLocal() as db:
            conversation = Conversation(
                user_id=UUID(login["user"]["id"]),
                title="五龄蚕体色发白怎么办",
                conversation_type="diagnosis",
                status="active",
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            conversation_id = str(conversation.id)

        case_response = client.post(
            "/api/v1/husbandry/cases",
            headers=headers,
            json={
                "farm_id": farm["id"],
                "batch_id": batch["id"],
                "source_conversation_id": conversation_id,
                "title": "五龄蚕体色发白异常",
                "occurred_on": "2026-07-10",
                "symptom_summary": "部分蚕体色发白、食桑减少。",
                "suspected_disease": "白僵病",
                "severity": "high",
                "status": "suspected",
            },
        )
        assert case_response.status_code == 201
        case = case_response.json()
        assert case["source_conversation_id"] == conversation_id
        assert case["source_snapshot"]["conversation_title"] == "五龄蚕体色发白怎么办"

        follow_up_response = client.post(
            f"/api/v1/husbandry/cases/{case['id']}/follow-ups",
            headers=headers,
            json={
                "observed_on": "2026-07-11",
                "action_taken": "隔离异常蚕并加强通风",
                "note": "未见继续扩散",
                "affected_count": 2,
                "death_count": 0,
                "next_follow_up_on": date.today().isoformat(),
            },
        )
        assert follow_up_response.status_code == 200
        assert follow_up_response.json()["follow_ups"][0]["note"] == "未见继续扩散"
        follow_up_id = follow_up_response.json()["follow_ups"][0]["id"]

        follow_up_update_response = client.patch(
            f"/api/v1/husbandry/cases/{case['id']}/follow-ups/{follow_up_id}",
            headers=headers,
            json={"note": "症状减轻，未见继续扩散", "next_follow_up_on": date.today().isoformat()},
        )
        assert follow_up_update_response.status_code == 200
        assert follow_up_update_response.json()["follow_ups"][0]["note"] == "症状减轻，未见继续扩散"

        cases_response = client.get("/api/v1/husbandry/cases", headers=headers)
        assert cases_response.status_code == 200
        assert cases_response.json()[0]["id"] == case["id"]
        assert cases_response.json()[0]["batch_code"] == "2026-夏蚕-A01"

        dashboard_response = client.get("/api/v1/husbandry/dashboard", headers=headers)
        assert dashboard_response.status_code == 200
        dashboard = dashboard_response.json()
        assert dashboard["active_batch_count"] == 1
        assert dashboard["open_case_count"] == 1
        assert dashboard["due_follow_up_count"] == 1

        delete_follow_up_response = client.delete(
            f"/api/v1/husbandry/cases/{case['id']}/follow-ups/{follow_up_id}",
            headers=headers,
        )
        assert delete_follow_up_response.status_code == 204
        assert client.get("/api/v1/husbandry/cases", headers=headers).json()[0]["follow_ups"] == []

        complete_batch_response = client.patch(
            f"/api/v1/husbandry/batches/{batch['id']}",
            headers=headers,
            json={"status": "finished"},
        )
        assert complete_batch_response.status_code == 200
        assert complete_batch_response.json()["status"] == "finished"

        close_case_response = client.patch(
            f"/api/v1/husbandry/cases/{case['id']}",
            headers=headers,
            json={"status": "closed"},
        )
        assert close_case_response.status_code == 409

        protected_update_response = client.patch(
            f"/api/v1/husbandry/cases/{case['id']}",
            headers=headers,
            json={"severity": "low", "recommendation": "user must not replace expert guidance"},
        )
        assert protected_update_response.status_code == 403

        with SessionLocal() as db:
            reviewed_case = db.get(HusbandryCase, UUID(case["id"]))
            assert reviewed_case is not None
            reviewed_case.status = "processing"
            db.add(ExpertReview(
                husbandry_case_id=reviewed_case.id,
                user_id=reviewed_case.owner_id,
                reviewer_id=reviewed_case.owner_id,
                reviewer_name_snapshot="test reviewer",
                status="published",
                risk_level="high",
                conclusion="complete a follow-up before closure",
                recommendation="record the treatment outcome",
                version=1,
                published_at=now_utc(),
            ))
            db.commit()

        post_review_follow_up = client.post(
            f"/api/v1/husbandry/cases/{case['id']}/follow-ups",
            headers=headers,
            json={"observed_on": date.today().isoformat(), "note": "treatment outcome observed"},
        )
        assert post_review_follow_up.status_code == 200

        completed_close_response = client.patch(
            f"/api/v1/husbandry/cases/{case['id']}",
            headers=headers,
            json={"status": "closed"},
        )
        assert completed_close_response.status_code == 200
        assert completed_close_response.json()["status"] == "closed"
        assert completed_close_response.json()["closed_at"] is not None

        delete_case_response = client.delete(f"/api/v1/husbandry/cases/{case['id']}", headers=headers)
        assert delete_case_response.status_code == 409
    finally:
        _cleanup_identity_auth_data("email", TEST_EMAIL)


def _cleanup_identity_auth_data(provider: str, subject: str) -> None:
    with SessionLocal() as db:
        user_ids = list(
            db.scalars(
                select(UserIdentity.user_id).where(
                    UserIdentity.provider == provider,
                    UserIdentity.provider_subject == subject,
                )
            )
        )
        login_event_filter = LoginEvent.target == subject
        if user_ids:
            login_event_filter = or_(login_event_filter, LoginEvent.user_id.in_(user_ids))
        db.execute(delete(LoginEvent).where(login_event_filter))
        db.execute(delete(AuthVerificationCode).where(AuthVerificationCode.target == subject))
        if user_ids:
            case_ids = list(db.scalars(select(HusbandryCase.id).where(HusbandryCase.owner_id.in_(user_ids))))
            if case_ids:
                db.execute(text("""
                    DELETE FROM admin.work_items
                     WHERE resource_type = 'husbandry_case'
                       AND resource_id = ANY(CAST(:case_ids AS text[]))
                """), {"case_ids": [str(case_id) for case_id in case_ids]})
            db.execute(delete(HusbandryCase).where(HusbandryCase.owner_id.in_(user_ids)))
            db.execute(delete(Farm).where(Farm.owner_id.in_(user_ids)))
            db.execute(delete(Project).where(Project.owner_id.in_(user_ids)))
            db.execute(delete(Conversation).where(Conversation.user_id.in_(user_ids)))
            db.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
            db.execute(delete(UserIdentity).where(UserIdentity.user_id.in_(user_ids)))
            db.execute(delete(User).where(User.id.in_(user_ids)))
        db.commit()


def _login_with_email_dev_code(email: str) -> dict:
    code_response = client.post("/api/v1/auth/email/verification-codes", json={"email": email})
    assert code_response.status_code == 200
    login_response = client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "code": code_response.json()["dev_code"], "device_name": "pytest"},
    )
    assert login_response.status_code == 200
    return login_response.json()

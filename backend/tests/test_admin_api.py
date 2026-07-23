from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select

from app.db.session import SessionLocal, check_database_connection
from app.main import app
from app.models import (
    AuthSession,
    AuthVerificationCode,
    ExpertReview,
    Farm,
    HusbandryCase,
    LoginEvent,
    User,
    UserIdentity,
)


client = TestClient(app)
ADMIN_EMAIL = "codex-admin-console@qq.com"
FARMER_EMAIL = "codex-admin-farmer@qq.com"


def test_admin_routes_require_login() -> None:
    response = client.get("/api/v1/admin/dashboard")

    assert response.status_code == 401


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_admin_can_review_case_and_publish_to_farmer() -> None:
    _cleanup(ADMIN_EMAIL)
    _cleanup(FARMER_EMAIL)
    try:
        admin_login = _login(ADMIN_EMAIL)
        farmer_login = _login(FARMER_EMAIL)
        _set_role(ADMIN_EMAIL, "admin")
        admin_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}
        farmer_headers = {"Authorization": f"Bearer {farmer_login['access_token']}"}

        forbidden = client.get("/api/v1/admin/dashboard", headers=farmer_headers)
        assert forbidden.status_code == 403

        farm = client.post(
            "/api/v1/husbandry/farms",
            headers=farmer_headers,
            json={"name": "Admin review farm", "location": "Huzhou"},
        )
        assert farm.status_code == 201
        batch = client.post(
            "/api/v1/husbandry/batches",
            headers=farmer_headers,
            json={"farm_id": farm.json()["id"], "batch_code": "admin-review-2026", "instar": "三龄"},
        )
        assert batch.status_code == 201
        case = client.post(
            "/api/v1/husbandry/cases",
            headers=farmer_headers,
            json={
                "farm_id": farm.json()["id"],
                "batch_id": batch.json()["id"],
                "title": "Body color anomaly",
                "occurred_on": date.today().isoformat(),
                "symptom_summary": "Several silkworms show pale body color.",
                "severity": "high",
                "status": "suspected",
            },
        )
        assert case.status_code == 201
        case_id = case.json()["id"]

        dashboard = client.get("/api/v1/admin/dashboard", headers=admin_headers)
        assert dashboard.status_code == 200
        assert dashboard.json()["metrics"]

        queue = client.get("/api/v1/admin/review-queue", headers=admin_headers)
        assert queue.status_code == 200
        assert case_id in [item["id"] for item in queue.json()]

        review = client.post(
            "/api/v1/admin/reviews",
            headers=admin_headers,
            json={
                "husbandry_case_id": case_id,
                "risk_level": "high",
                "conclusion": "A bacterial infection risk cannot be excluded.",
                "recommendation": "Isolate affected larvae, improve ventilation, and record changes for 48 hours.",
                "status": "published",
            },
        )
        assert review.status_code == 201
        assert review.json()["version"] == 1
        assert review.json()["status"] == "published"

        farmer_cases = client.get("/api/v1/husbandry/cases", headers=farmer_headers)
        assert farmer_cases.status_code == 200
        saved_case = next(item for item in farmer_cases.json() if item["id"] == case_id)
        assert saved_case["expert_reviews"][0]["conclusion"] == "A bacterial infection risk cannot be excluded."

        users = client.get("/api/v1/admin/users?status=active", headers=admin_headers)
        assert users.status_code == 200
        farmer = next(item for item in users.json()["items"] if item["id"] == farmer_login["user"]["id"])
        update_user = client.patch(
            f"/api/v1/admin/users/{farmer['id']}",
            headers=admin_headers,
            json={"role": "agritech"},
        )
        assert update_user.status_code == 200
        assert update_user.json()["role"] == "agritech"
    finally:
        _cleanup(ADMIN_EMAIL)
        _cleanup(FARMER_EMAIL)


def _login(email: str) -> dict:
    code_response = client.post("/api/v1/auth/email/verification-codes", json={"email": email})
    assert code_response.status_code == 200
    login_response = client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "code": code_response.json()["dev_code"], "device_name": "admin-api-pytest"},
    )
    assert login_response.status_code == 200
    return login_response.json()


def _set_role(email: str, role: str) -> None:
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


def _cleanup(email: str) -> None:
    with SessionLocal() as db:
        user_ids = list(
            db.scalars(
                select(UserIdentity.user_id).where(UserIdentity.provider == "email", UserIdentity.provider_subject == email)
            )
        )
        login_event_filter = LoginEvent.target == email
        if user_ids:
            login_event_filter = or_(login_event_filter, LoginEvent.user_id.in_(user_ids))
        db.execute(delete(LoginEvent).where(login_event_filter))
        db.execute(delete(AuthVerificationCode).where(AuthVerificationCode.target == email))
        if user_ids:
            case_ids = list(db.scalars(select(HusbandryCase.id).where(HusbandryCase.owner_id.in_(user_ids))))
            if case_ids:
                db.execute(delete(ExpertReview).where(ExpertReview.husbandry_case_id.in_(case_ids)))
            db.execute(delete(ExpertReview).where(ExpertReview.reviewer_id.in_(user_ids)))
            db.execute(delete(HusbandryCase).where(HusbandryCase.owner_id.in_(user_ids)))
            db.execute(delete(Farm).where(Farm.owner_id.in_(user_ids)))
            db.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
            db.execute(delete(UserIdentity).where(UserIdentity.user_id.in_(user_ids)))
            db.execute(delete(User).where(User.id.in_(user_ids)))
        db.commit()

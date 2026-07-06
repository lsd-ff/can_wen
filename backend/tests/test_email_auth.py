import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select

from app.db.session import SessionLocal, check_database_connection
from app.main import app
from app.models import AuthSession, AuthVerificationCode, LoginEvent, User, UserIdentity


client = TestClient(app)
TEST_EMAIL = "codex-email-login@qq.com"
TEST_PHONE = "+8613800000000"


def test_email_auth_rejects_unsupported_domain() -> None:
    response = client.post(
        "/api/v1/auth/email/verification-codes",
        json={"email": "farmer@gmail.com"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "暂只支持 QQ 邮箱和网易邮箱"}


def test_phone_auth_rejects_invalid_phone_number() -> None:
    response = client.post(
        "/api/v1/auth/phone/verification-codes",
        json={"phone_number": "12345"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "手机号格式不正确"}


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_email_auth_login_flow_with_dev_code() -> None:
    _cleanup_identity_auth_data("email", TEST_EMAIL)
    try:
        code_response = client.post(
            "/api/v1/auth/email/verification-codes",
            json={"email": TEST_EMAIL.upper()},
        )

        assert code_response.status_code == 200
        code_payload = code_response.json()
        assert code_payload["status"] == "dev_sent"
        assert code_payload["email"] == TEST_EMAIL
        assert len(code_payload["dev_code"]) == 6

        login_response = client.post(
            "/api/v1/auth/email/login",
            json={
                "email": TEST_EMAIL,
                "code": code_payload["dev_code"],
                "device_name": "pytest",
            },
        )

        assert login_response.status_code == 200
        login_payload = login_response.json()
        assert login_payload["token_type"] == "bearer"
        assert login_payload["access_token"]
        assert login_payload["refresh_token"]
        assert login_payload["user"]["email"] == TEST_EMAIL
        assert login_payload["user"]["display_name"] == "codex-email-login"
        assert login_payload["user"]["username"] == "codex-email-login"
        assert login_payload["user"]["avatar_url"] is None

        auth_headers = {"Authorization": f"Bearer {login_payload['access_token']}"}
        profile_response = client.get("/api/v1/auth/me", headers=auth_headers)

        assert profile_response.status_code == 200
        assert profile_response.json() == {
            "id": login_payload["user"]["id"],
            "display_name": "codex-email-login",
            "username": "codex-email-login",
            "email": TEST_EMAIL,
            "phone_number": "",
            "avatar_url": None,
        }

        update_profile_response = client.patch(
            "/api/v1/auth/me",
            headers=auth_headers,
            json={
                "display_name": "资料测试用户",
                "username": "profile_test_user",
                "avatar_url": "data:image/png;base64,dGVzdA==",
            },
        )

        assert update_profile_response.status_code == 200
        assert update_profile_response.json() == {
            "id": login_payload["user"]["id"],
            "display_name": "资料测试用户",
            "username": "profile_test_user",
            "email": TEST_EMAIL,
            "phone_number": "",
            "avatar_url": "data:image/png;base64,dGVzdA==",
        }

        refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_payload["refresh_token"]},
        )

        assert refresh_response.status_code == 200
        refresh_payload = refresh_response.json()
        assert refresh_payload["token_type"] == "bearer"
        assert refresh_payload["access_token"]
        assert refresh_payload["user"]["email"] == TEST_EMAIL

        logout_response = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": login_payload["refresh_token"]},
        )

        assert logout_response.status_code == 200
        assert logout_response.json() == {"status": "ok"}

        with SessionLocal() as db:
            user_id = db.scalar(
                select(UserIdentity.user_id).where(
                    UserIdentity.provider == "email",
                    UserIdentity.provider_subject == TEST_EMAIL,
                )
            )
            session = db.scalar(select(AuthSession).where(AuthSession.user_id == user_id))
            assert session is not None
            assert session.status == "revoked"
            assert session.revoked_at is not None

        repeated_logout_response = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": login_payload["refresh_token"]},
        )

        assert repeated_logout_response.status_code == 200
        assert repeated_logout_response.json() == {"status": "ok"}

        expired_profile_response = client.get("/api/v1/auth/me", headers=auth_headers)

        assert expired_profile_response.status_code == 401

        refresh_after_logout_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_payload["refresh_token"]},
        )

        assert refresh_after_logout_response.status_code == 401
    finally:
        _cleanup_identity_auth_data("email", TEST_EMAIL)


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_phone_auth_login_flow_with_dev_code() -> None:
    _cleanup_identity_auth_data("phone", TEST_PHONE)
    try:
        code_response = client.post(
            "/api/v1/auth/phone/verification-codes",
            json={"phone_number": "138 0000 0000"},
        )

        assert code_response.status_code == 200
        code_payload = code_response.json()
        assert code_payload["status"] == "dev_sent"
        assert code_payload["phone_number"] == TEST_PHONE
        assert len(code_payload["dev_code"]) == 6

        repeated_code_response = client.post(
            "/api/v1/auth/phone/verification-codes",
            json={"phone_number": "13800000000"},
        )

        assert repeated_code_response.status_code == 429

        login_response = client.post(
            "/api/v1/auth/phone/login",
            json={
                "phone_number": "13800000000",
                "code": code_payload["dev_code"],
                "device_name": "pytest",
            },
        )

        assert login_response.status_code == 200
        login_payload = login_response.json()
        assert login_payload["access_token"]
        assert login_payload["refresh_token"]
        assert login_payload["user"]["email"] == ""
        assert login_payload["user"]["phone_number"] == TEST_PHONE
        assert login_payload["user"]["display_name"] == "用户0000"

        with SessionLocal() as db:
            user_id = db.scalar(
                select(UserIdentity.user_id).where(
                    UserIdentity.provider == "phone",
                    UserIdentity.provider_subject == TEST_PHONE,
                )
            )
            session = db.scalar(select(AuthSession).where(AuthSession.user_id == user_id))
            assert session is not None
            assert session.status == "active"

        logout_response = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": login_payload["refresh_token"]},
        )

        assert logout_response.status_code == 200
    finally:
        _cleanup_identity_auth_data("phone", TEST_PHONE)


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
            db.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
            db.execute(
                delete(UserIdentity).where(
                    UserIdentity.provider == provider,
                    UserIdentity.provider_subject == subject,
                )
            )
            db.execute(delete(User).where(User.id.in_(user_ids)))
        db.commit()

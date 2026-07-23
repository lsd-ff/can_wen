import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select
from uuid import UUID

from app.db.session import SessionLocal, check_database_connection
from app.main import app
from app.models import AuthSession, AuthVerificationCode, LoginEvent, User, UserIdentity
from app.services import auth_service


client = TestClient(app)
TEST_EMAIL = "codex-email-login@qq.com"
TEST_AVATAR_EMAIL = "codex-avatar-upload@qq.com"
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
        assert login_payload["user"]["role"] == "farmer"
        assert login_payload["user"]["avatar_url"] is None

        auth_headers = {"Authorization": f"Bearer {login_payload['access_token']}"}
        profile_response = client.get("/api/v1/auth/me", headers=auth_headers)

        assert profile_response.status_code == 200
        assert profile_response.json() == {
            "id": login_payload["user"]["id"],
            "display_name": "codex-email-login",
            "username": "codex-email-login",
            "role": "farmer",
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
            },
        )

        assert update_profile_response.status_code == 200
        assert update_profile_response.json() == {
            "id": login_payload["user"]["id"],
            "display_name": "资料测试用户",
            "username": "profile_test_user",
            "role": "farmer",
            "email": TEST_EMAIL,
            "phone_number": "",
            "avatar_url": None,
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
        assert refresh_payload["user"]["role"] == "farmer"

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


def test_avatar_upload_requires_login() -> None:
    response = client.post(
        "/api/v1/auth/me/avatar",
        files={"avatar": ("avatar.jpg", b"fake-jpeg", "image/jpeg")},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_avatar_upload_validation_and_mock_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    _cleanup_identity_auth_data("email", TEST_AVATAR_EMAIL)
    try:
        login_payload = _login_with_email_dev_code(TEST_AVATAR_EMAIL)
        auth_headers = {"Authorization": f"Bearer {login_payload['access_token']}"}

        rejected_patch_response = client.patch(
            "/api/v1/auth/me",
            headers=auth_headers,
            json={
                "display_name": "codex-avatar-upload",
                "username": "codex-avatar-upload",
                "avatar_url": "https://cdn.example.com/forbidden.jpg",
            },
        )
        assert rejected_patch_response.status_code == 422

        invalid_type_response = client.post(
            "/api/v1/auth/me/avatar",
            headers=auth_headers,
            files={"avatar": ("avatar.txt", b"not-image", "text/plain")},
        )
        assert invalid_type_response.status_code == 400
        assert invalid_type_response.json() == {"detail": "头像只支持 JPG、PNG 或 WebP 图片"}

        oversized_response = client.post(
            "/api/v1/auth/me/avatar",
            headers=auth_headers,
            files={"avatar": ("avatar.jpg", b"x" * (2 * 1024 * 1024 + 1), "image/jpeg")},
        )
        assert oversized_response.status_code == 400
        assert oversized_response.json() == {"detail": "头像图片不能超过 2MB"}

        def fake_upload_public_file(*, object_key: str, content: bytes, content_type: str) -> str:
            assert object_key.startswith(f"avatars/{login_payload['user']['id']}/")
            assert object_key.endswith(".jpg")
            assert content == b"\xff\xd8\xff\xe0fake-jpeg"
            assert content_type == "image/jpeg"
            return f"https://cdn.example.com/{object_key}"

        monkeypatch.setattr(auth_service, "upload_public_file", fake_upload_public_file)

        upload_response = client.post(
            "/api/v1/auth/me/avatar",
            headers=auth_headers,
            files={"avatar": ("avatar.jpg", b"\xff\xd8\xff\xe0fake-jpeg", "image/jpeg")},
        )

        assert upload_response.status_code == 200
        avatar_url = upload_response.json()["avatar_url"]
        assert avatar_url.startswith(f"https://cdn.example.com/avatars/{login_payload['user']['id']}/")
        assert avatar_url.endswith(".jpg")

        update_profile_response = client.patch(
            "/api/v1/auth/me",
            headers=auth_headers,
            json={
                "display_name": "头像测试用户",
                "username": "avatar_test_user",
            },
        )
        assert update_profile_response.status_code == 200
        assert update_profile_response.json()["avatar_url"] == avatar_url

        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.id == UUID(login_payload["user"]["id"])))
            assert user is not None
            assert user.avatar_url == avatar_url
    finally:
        _cleanup_identity_auth_data("email", TEST_AVATAR_EMAIL)


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


def _login_with_email_dev_code(email: str) -> dict:
    code_response = client.post(
        "/api/v1/auth/email/verification-codes",
        json={"email": email},
    )
    assert code_response.status_code == 200
    code_payload = code_response.json()

    login_response = client.post(
        "/api/v1/auth/email/login",
        json={
            "email": email,
            "code": code_payload["dev_code"],
            "device_name": "pytest",
        },
    )
    assert login_response.status_code == 200
    return login_response.json()

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select
from uuid import UUID

from app.db.session import SessionLocal, check_database_connection
from app.main import app
from app.models import AuthSession, AuthVerificationCode, Conversation, LoginEvent, Project, ProjectShare, User, UserIdentity


client = TestClient(app)
TEST_EMAIL = "codex-projects-api@qq.com"


def test_projects_require_login() -> None:
    response = client.post("/api/v1/projects", json={"name": "真实项目文件夹"})

    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_create_and_list_current_user_projects() -> None:
    _cleanup_identity_auth_data("email", TEST_EMAIL)
    try:
        login_payload = _login_with_email_dev_code(TEST_EMAIL)
        auth_headers = {"Authorization": f"Bearer {login_payload['access_token']}"}

        create_response = client.post(
            "/api/v1/projects",
            headers=auth_headers,
            json={
                "name": "真实项目文件夹",
                "icon_key": "folder",
                "color": "#11110f",
            },
        )

        assert create_response.status_code == 201
        created_project = create_response.json()
        assert created_project["id"]
        assert created_project["name"] == "真实项目文件夹"
        assert created_project["description"] is None
        assert created_project["icon_key"] == "folder"
        assert created_project["color"] == "#11110f"
        assert created_project["status"] == "active"
        assert created_project["created_at"]
        assert created_project["updated_at"]

        list_response = client.get("/api/v1/projects", headers=auth_headers)

        assert list_response.status_code == 200
        projects = list_response.json()
        assert projects[0]["id"] == created_project["id"]
        assert projects[0]["name"] == "真实项目文件夹"

        update_response = client.patch(
            f"/api/v1/projects/{created_project['id']}",
            headers=auth_headers,
            json={
                "name": "更新后的项目",
                "description": "项目描述已经更新",
                "icon_key": "book",
                "color": "#ff4338",
            },
        )

        assert update_response.status_code == 200
        updated_project = update_response.json()
        assert updated_project["id"] == created_project["id"]
        assert updated_project["name"] == "更新后的项目"
        assert updated_project["description"] == "项目描述已经更新"
        assert updated_project["icon_key"] == "book"
        assert updated_project["color"] == "#ff4338"

        detail_response = client.get(f"/api/v1/projects/{created_project['id']}", headers=auth_headers)
        assert detail_response.status_code == 200
        assert detail_response.json()["name"] == "更新后的项目"

        pin_response = client.patch(
            f"/api/v1/projects/{created_project['id']}/pin",
            headers=auth_headers,
            json={"pinned": True},
        )
        assert pin_response.status_code == 200
        assert pin_response.json()["pinned_at"] is not None

        unpin_response = client.patch(
            f"/api/v1/projects/{created_project['id']}/pin",
            headers=auth_headers,
            json={"pinned": False},
        )
        assert unpin_response.status_code == 200
        assert unpin_response.json()["pinned_at"] is None

        with SessionLocal() as db:
            saved_project = db.scalar(select(Project).where(Project.id == created_project["id"]))
            assert saved_project is not None
            assert str(saved_project.owner_id) == login_payload["user"]["id"]
            assert saved_project.name == "更新后的项目"
            assert saved_project.description == "项目描述已经更新"
            assert saved_project.icon_key == "book"
            assert saved_project.color == "#ff4338"

            conversation = Conversation(
                user_id=UUID(login_payload["user"]["id"]),
                project_id=UUID(created_project["id"]),
                title="项目内问诊",
                conversation_type="diagnosis",
                status="active",
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            conversation_id = str(conversation.id)

        project_conversations_response = client.get(
            f"/api/v1/projects/{created_project['id']}/conversations",
            headers=auth_headers,
        )
        assert project_conversations_response.status_code == 200
        project_conversations = project_conversations_response.json()
        assert project_conversations[0]["id"] == conversation_id
        assert project_conversations[0]["project_id"] == created_project["id"]

        move_out_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/project",
            headers=auth_headers,
            json={"project_id": None},
        )
        assert move_out_response.status_code == 200
        assert move_out_response.json()["project_id"] is None

        move_in_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/project",
            headers=auth_headers,
            json={"project_id": created_project["id"]},
        )
        assert move_in_response.status_code == 200
        assert move_in_response.json()["project_id"] == created_project["id"]

        share_response = client.post(
            f"/api/v1/projects/{created_project['id']}/shares",
            headers=auth_headers,
            json={
                "title": "更新后的项目",
                "variant": "summary",
                "content_markdown": "# CanW 家蚕问诊项目摘要\n\n项目内问诊需要交接。",
            },
        )

        assert share_response.status_code == 200
        share_payload = share_response.json()
        assert share_payload["project_id"] == created_project["id"]
        assert share_payload["title"] == "更新后的项目"
        assert share_payload["share_url"].endswith(f"/project-share/{share_payload['share_token']}")

        public_share_response = client.get(f"/api/v1/projects/shares/{share_payload['share_token']}")

        assert public_share_response.status_code == 200
        public_share_payload = public_share_response.json()
        assert public_share_payload["title"] == "更新后的项目"
        assert public_share_payload["content_markdown"].startswith("# CanW 家蚕问诊项目摘要")

        with SessionLocal() as db:
            saved_share = db.scalar(select(ProjectShare).where(ProjectShare.share_token == share_payload["share_token"]))
            assert saved_share is not None
            assert saved_share.view_count == 1

        archive_response = client.patch(f"/api/v1/projects/{created_project['id']}/archive", headers=auth_headers)
        assert archive_response.status_code == 200
        assert archive_response.json()["status"] == "archived"
        assert archive_response.json()["pinned_at"] is None

        with SessionLocal() as db:
            archived_conversation = db.scalar(select(Conversation).where(Conversation.id == UUID(conversation_id)))
            assert archived_conversation is not None
            assert archived_conversation.status == "archived"

        list_after_archive_response = client.get("/api/v1/projects", headers=auth_headers)
        assert list_after_archive_response.status_code == 200
        assert all(project["id"] != created_project["id"] for project in list_after_archive_response.json())

        archived_projects_response = client.get("/api/v1/projects/archived", headers=auth_headers)
        assert archived_projects_response.status_code == 200
        assert archived_projects_response.json()[0]["id"] == created_project["id"]

        restore_response = client.patch(f"/api/v1/projects/{created_project['id']}/restore", headers=auth_headers)
        assert restore_response.status_code == 200
        assert restore_response.json()["status"] == "active"

        with SessionLocal() as db:
            restored_conversation = db.scalar(select(Conversation).where(Conversation.id == UUID(conversation_id)))
            assert restored_conversation is not None
            assert restored_conversation.status == "active"

        delete_response = client.delete(f"/api/v1/projects/{created_project['id']}", headers=auth_headers)
        assert delete_response.status_code == 204

        list_after_delete_response = client.get("/api/v1/projects", headers=auth_headers)
        assert list_after_delete_response.status_code == 200
        assert all(project["id"] != created_project["id"] for project in list_after_delete_response.json())

        with SessionLocal() as db:
            deleted_project = db.scalar(select(Project).where(Project.id == created_project["id"]))
            saved_conversation = db.scalar(select(Conversation).where(Conversation.id == UUID(conversation_id)))
            assert deleted_project is not None
            assert deleted_project.status == "deleted"
            assert deleted_project.deleted_at is not None
            assert saved_conversation is not None
            assert saved_conversation.project_id is None
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
            db.execute(delete(AuthSession).where(AuthSession.user_id.in_(user_ids)))
            db.execute(delete(Project).where(Project.owner_id.in_(user_ids)))
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

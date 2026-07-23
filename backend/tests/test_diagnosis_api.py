import json
import io
import zipfile
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, or_, select

from app.agents.diagnosis.types import AgentPublicEvent, DiagnosisAgentResult
from app.core.config import Settings, get_settings
from app.core.security import now_utc
from app.db.session import SessionLocal, check_database_connection
from app.main import app
from app.models import (
    AuthSession,
    AuthVerificationCode,
    Conversation,
    ConversationShare,
    DiagnosisMultimodalAnalysis,
    LoginEvent,
    Message,
    Project,
    User,
    UserIdentity,
    UploadedFile,
)
from app.services import diagnosis_service as diagnosis_service_module
from app.services.diagnosis_agent_service import DiagnosisAgentExecution
from app.services.llm_client import OpenAICompatibleModelConfig


client = TestClient(app)
TEST_EMAIL = "codex-diagnosis-api@qq.com"


def _fake_agent_execution(question: str, *, answer: str | None = None) -> DiagnosisAgentExecution:
    return DiagnosisAgentExecution(
        run_id=uuid4(),
        result=DiagnosisAgentResult(
            answer=answer or f"智能体回复：{question}",
            status="completed",
            route="hybrid",
            risk_level="low",
            original_question=question,
            rewritten_question=question,
            evidence_status="sufficient",
            metrics={"test_execution": True},
        ),
        events=[],
    )


def test_diagnosis_conversations_require_login() -> None:
    response = client.get("/api/v1/diagnosis/conversations")

    assert response.status_code == 401
    assert response.json() == {"detail": "请先登录"}


def test_legacy_direct_model_chat_is_not_exposed() -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/diagnosis/chat" not in paths


def test_diagnosis_title_uses_a_concise_question_summary() -> None:
    assert diagnosis_service_module._title_from_message("给我介绍下微粒子病") == "微粒子病：基础介绍"
    assert diagnosis_service_module._title_from_message("五龄蚕发白变硬怎么办？") == "五龄蚕发白变硬：处置咨询"
    assert diagnosis_service_module._summary_from_message("给我介绍下微粒子病") == "给我介绍下微粒子病"
    assert diagnosis_service_module._is_placeholder_diagnosis_title("新问诊")


def test_docx_attachment_context_is_ready_for_multimodal_observation_extraction() -> None:
    docx_buffer = io.BytesIO()
    with zipfile.ZipFile(docx_buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>五龄蚕体色发白，食桑减少</w:t></w:r></w:p></w:body></w:document>"
            ),
        )

    context = diagnosis_service_module._extract_attachment_analysis_context(
        file_name="记录.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_type="document",
        content=docx_buffer.getvalue(),
    )

    assert context["extraction_status"] == "direct_url_ready"
    assert "原始文档 URL" in context["extraction_note"]
    assert "五龄蚕体色发白" in context["extracted_text"]


def test_multimodal_analysis_messages_include_document_text_and_inline_image() -> None:
    image_file = UploadedFile(
        id=uuid4(),
        user_id=uuid4(),
        file_name="symptom.jpg",
        file_type="image",
        mime_type="image/jpeg",
        storage_key="diagnosis/demo/symptom.jpg",
        storage_url="https://oss.test/diagnosis/demo/symptom.jpg",
        file_size=12,
        checksum="image-checksum",
        metadata_={
            "analysis_context": {
                "file_name": "symptom.jpg",
                "file_type": "image",
                "mime_type": "image/jpeg",
                "extraction_status": "vision_ready",
            }
        },
    )
    setattr(image_file, "_analysis_content", b"fake-image")
    document_file = UploadedFile(
        id=uuid4(),
        user_id=uuid4(),
        file_name="records.txt",
        file_type="document",
        mime_type="text/plain",
        storage_key="diagnosis/demo/records.txt",
        storage_url="https://oss.test/diagnosis/demo/records.txt",
        file_size=20,
        checksum="document-checksum",
        metadata_={
            "analysis_context": {
                "file_name": "records.txt",
                "file_type": "document",
                "mime_type": "text/plain",
                "extraction_status": "text_extracted",
                "extracted_text": "温度 30℃，湿度偏高，死亡率上升。",
            }
        },
    )

    messages = diagnosis_service_module._build_multimodal_analysis_messages(
        message="请综合判断",
        files=[image_file, document_file],
        structured_data={"silkworm_age": "五龄"},
        include_inline_images=True,
    )

    user_content = messages[1]["content"]
    assert user_content[0]["type"] == "text"
    assert "温度 30℃" in user_content[0]["text"]
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_persistent_diagnosis_conversation_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    _cleanup_identity_auth_data("email", TEST_EMAIL)

    def fake_settings() -> Settings:
        return Settings(openai_api_key="test-key", openai_base_url="https://example.test/v1", openai_model_id="gpt-5-nano")

    calls: list[tuple[str, int]] = []

    def fake_execute_diagnosis_agent(*args, original_question: str, history: list, model_config, **kwargs):
        assert model_config is not None
        calls.append((original_question, len(history)))
        return _fake_agent_execution(original_question)

    monkeypatch.setattr("app.services.diagnosis_service.execute_diagnosis_agent", fake_execute_diagnosis_agent)
    monkeypatch.setattr(
        "app.services.diagnosis_service.resolve_current_user_llm_config",
        lambda *args, **kwargs: OpenAICompatibleModelConfig(
            provider_name="Environment",
            model_id="gpt-5-nano",
            api_key="test-key",
            api_request_url="https://example.test/v1",
        ),
    )
    app.dependency_overrides[get_settings] = fake_settings

    try:
        login_payload = _login_with_email_dev_code(TEST_EMAIL)
        auth_headers = {"Authorization": f"Bearer {login_payload['access_token']}"}

        create_response = client.post(
            "/api/v1/diagnosis/conversations",
            headers=auth_headers,
            json={"message": "五龄蚕发白变硬怎么办？"},
        )

        assert create_response.status_code == 200
        created_turn = create_response.json()
        conversation_id = created_turn["conversation"]["id"]
        assert created_turn["conversation"]["title"].startswith("五龄蚕发白变硬")
        assert created_turn["user_message"]["role"] == "user"
        assert created_turn["assistant_message"]["role"] == "assistant"
        assert created_turn["assistant_message"]["content"] == "智能体回复：五龄蚕发白变硬怎么办？"
        assert created_turn["agent_run"]["route"] == "hybrid"
        assert created_turn["assistant_message"]["agent_run"]["evidence_status"] == "sufficient"
        assert calls == [("五龄蚕发白变硬怎么办？", 0)]

        list_response = client.get("/api/v1/diagnosis/conversations", headers=auth_headers)

        assert list_response.status_code == 200
        conversations = list_response.json()
        assert conversations[0]["id"] == conversation_id

        rename_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}",
            headers=auth_headers,
            json={"title": "renamed diagnosis conversation"},
        )

        assert rename_response.status_code == 200
        assert rename_response.json()["title"] == "renamed diagnosis conversation"

        renamed_list_response = client.get("/api/v1/diagnosis/conversations", headers=auth_headers)
        assert renamed_list_response.status_code == 200
        assert renamed_list_response.json()[0]["title"] == "renamed diagnosis conversation"

        pin_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/pin",
            headers=auth_headers,
            json={"pinned": True},
        )
        assert pin_response.status_code == 200
        assert pin_response.json()["pinned_at"] is not None

        unpin_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/pin",
            headers=auth_headers,
            json={"pinned": False},
        )
        assert unpin_response.status_code == 200
        assert unpin_response.json()["pinned_at"] is None

        detail_response = client.get(f"/api/v1/diagnosis/conversations/{conversation_id}", headers=auth_headers)

        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["title"] == "renamed diagnosis conversation"
        assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]

        share_response = client.post(
            f"/api/v1/diagnosis/conversations/{conversation_id}/shares",
            headers=auth_headers,
            json={
                "title": "交接给农技专家",
                "variant": "summary",
                "content_markdown": "# CanW 家蚕问诊会话摘要\n\n需要复核五龄蚕发白变硬问题。",
            },
        )

        assert share_response.status_code == 200
        share_payload = share_response.json()
        assert share_payload["conversation_id"] == conversation_id
        assert share_payload["title"] == "交接给农技专家"
        assert share_payload["share_url"].endswith(f"/share/{share_payload['share_token']}")

        public_share_response = client.get(f"/api/v1/diagnosis/shares/{share_payload['share_token']}")

        assert public_share_response.status_code == 200
        public_share_payload = public_share_response.json()
        assert public_share_payload["title"] == "交接给农技专家"
        assert public_share_payload["content_markdown"].startswith("# CanW 家蚕问诊会话摘要")

        with SessionLocal() as db:
            saved_share = db.scalar(select(ConversationShare).where(ConversationShare.share_token == share_payload["share_token"]))
            assert saved_share is not None
            assert saved_share.view_count == 1

        append_response = client.post(
            f"/api/v1/diagnosis/conversations/{conversation_id}/messages",
            headers=auth_headers,
            json={"message": "需要怎么消毒？"},
        )

        assert append_response.status_code == 200
        assert append_response.json()["assistant_message"]["content"] == "智能体回复：需要怎么消毒？"
        assert calls[-1] == ("需要怎么消毒？", 2)

        with SessionLocal() as db:
            saved_messages = list(
                db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc()))
            )
            assert [message.sender_type for message in saved_messages] == ["user", "assistant", "user", "assistant"]
            first_user_id = str(saved_messages[0].id)
            second_user_id = str(saved_messages[2].id)
            second_assistant_id = str(saved_messages[3].id)

        feedback_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/messages/{second_assistant_id}/feedback",
            headers=auth_headers,
            json={"feedback": "like"},
        )

        assert feedback_response.status_code == 200
        assert feedback_response.json()["message"]["feedback"] == "like"

        dislike_feedback_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/messages/{second_assistant_id}/feedback",
            headers=auth_headers,
            json={
                "feedback": "dislike",
                "feedback_reasons": ["不正确或不完整", "其他"],
                "feedback_detail": "回答缺少消毒比例。",
            },
        )

        assert dislike_feedback_response.status_code == 200
        dislike_feedback_message = dislike_feedback_response.json()["message"]
        assert dislike_feedback_message["feedback"] == "dislike"
        assert dislike_feedback_message["feedback_reasons"] == ["不正确或不完整", "其他"]
        assert dislike_feedback_message["feedback_detail"] == "回答缺少消毒比例。"

        clear_feedback_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/messages/{second_assistant_id}/feedback",
            headers=auth_headers,
            json={"feedback": None},
        )

        assert clear_feedback_response.status_code == 200
        clear_feedback_message = clear_feedback_response.json()["message"]
        assert clear_feedback_message["feedback"] is None
        assert clear_feedback_message["feedback_reasons"] == []
        assert clear_feedback_message["feedback_detail"] is None

        archive_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/archive",
            headers=auth_headers,
        )
        assert archive_response.status_code == 200
        assert archive_response.json()["status"] == "archived"

        list_after_archive_response = client.get("/api/v1/diagnosis/conversations", headers=auth_headers)
        assert list_after_archive_response.status_code == 200
        assert all(conversation["id"] != conversation_id for conversation in list_after_archive_response.json())

        archived_list_response = client.get("/api/v1/diagnosis/conversations/archived", headers=auth_headers)
        assert archived_list_response.status_code == 200
        assert archived_list_response.json()[0]["id"] == conversation_id

        restore_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/restore",
            headers=auth_headers,
        )
        assert restore_response.status_code == 200
        assert restore_response.json()["status"] == "active"

        invalid_feedback_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/messages/{first_user_id}/feedback",
            headers=auth_headers,
            json={"feedback": "like"},
        )

        assert invalid_feedback_response.status_code == 400

        edit_response = client.patch(
            f"/api/v1/diagnosis/conversations/{conversation_id}/messages/{second_user_id}",
            headers=auth_headers,
            json={"content": "需要如何清理蚕座？"},
        )

        assert edit_response.status_code == 200
        assert edit_response.json()["message"]["content"] == "需要如何清理蚕座？"

        regenerate_response = client.post(
            f"/api/v1/diagnosis/conversations/{conversation_id}/messages/{second_assistant_id}/regenerate",
            headers=auth_headers,
            json={},
        )

        assert regenerate_response.status_code == 200
        assert regenerate_response.json()["message"]["content"] == "智能体回复：需要如何清理蚕座？"
        assert regenerate_response.json()["message"]["feedback"] is None
        assert calls[-1] == ("需要如何清理蚕座？", 2)

        regenerated_message = regenerate_response.json()["message"]
        assert regenerated_message["displayed_at"] != regenerated_message["created_at"]

        message_delete_response = client.delete(
            f"/api/v1/diagnosis/conversations/{conversation_id}/messages/{second_assistant_id}",
            headers=auth_headers,
        )

        assert message_delete_response.status_code == 200
        assert [message["role"] for message in message_delete_response.json()["messages"]] == ["user", "assistant"]

        with SessionLocal() as db:
            edited_user_message = db.scalar(select(Message).where(Message.id == second_user_id))
            deleted_assistant_message = db.scalar(select(Message).where(Message.id == second_assistant_id))
            assert edited_user_message is not None
            assert edited_user_message.deleted_at is not None
            assert edited_user_message.content == "需要如何清理蚕座？"
            assert deleted_assistant_message is not None
            assert deleted_assistant_message.deleted_at is not None

        delete_response = client.delete(f"/api/v1/diagnosis/conversations/{conversation_id}", headers=auth_headers)

        assert delete_response.status_code == 204

        deleted_list_response = client.get("/api/v1/diagnosis/conversations", headers=auth_headers)
        assert deleted_list_response.status_code == 200
        assert all(conversation["id"] != conversation_id for conversation in deleted_list_response.json())

        deleted_detail_response = client.get(f"/api/v1/diagnosis/conversations/{conversation_id}", headers=auth_headers)
        assert deleted_detail_response.status_code == 404

        with SessionLocal() as db:
            deleted_conversation = db.scalar(select(Conversation).where(Conversation.id == conversation_id))
            assert deleted_conversation is not None
            assert deleted_conversation.status == "deleted"
            assert deleted_conversation.deleted_at is not None
            saved_messages = list(
                db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc()))
            )
            assert [message.sender_type for message in saved_messages] == ["user", "assistant", "user", "assistant"]
    finally:
        app.dependency_overrides.pop(get_settings, None)
        _cleanup_identity_auth_data("email", TEST_EMAIL)


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_streaming_diagnosis_turn_emits_public_process_before_final(monkeypatch: pytest.MonkeyPatch) -> None:
    email = "codex-diagnosis-stream@qq.com"
    _cleanup_identity_auth_data("email", email)

    def fake_settings() -> Settings:
        return Settings(
            openai_api_key="test-key",
            openai_base_url="https://example.test/v1",
            openai_model_id="gpt-5-nano",
        )

    monkeypatch.setattr(
        "app.services.diagnosis_service.resolve_current_user_llm_config",
        lambda *args, **kwargs: OpenAICompatibleModelConfig(
            provider_name="Environment",
            model_id="gpt-5-nano",
            api_key="test-key",
            api_request_url="https://example.test/v1",
        ),
    )

    def fake_execute(*args, original_question: str, event_callback=None, **kwargs):
        execution = _fake_agent_execution(original_question)
        if event_callback is not None:
            event_callback(
                AgentPublicEvent(
                    run_id=str(execution.run_id),
                    sequence=1,
                    agent="agent1_context_router",
                    stage="route",
                    status="completed",
                    title="问题理解与路由完成",
                    summary="已选择 RAG + KG 联合检索。",
                    payload={"route": "hybrid", "risk_level": "low"},
                    created_at=now_utc(),
                )
            )
        return execution

    monkeypatch.setattr("app.services.diagnosis_service.execute_diagnosis_agent", fake_execute)
    app.dependency_overrides[get_settings] = fake_settings

    try:
        login_payload = _login_with_email_dev_code(email)
        auth_headers = {"Authorization": f"Bearer {login_payload['access_token']}"}
        response = client.post(
            "/api/v1/diagnosis/conversations/stream",
            headers=auth_headers,
            json={"message": "五龄蚕发白变硬怎么办？"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        blocks = [block for block in response.text.split("\n\n") if block.strip()]
        event_names = [
            next(line.removeprefix("event: ") for line in block.splitlines() if line.startswith("event: "))
            for block in blocks
        ]
        assert event_names == ["ready", "process", "final"]
        process_payload = json.loads(
            next(line.removeprefix("data: ") for line in blocks[1].splitlines() if line.startswith("data: "))
        )
        final_payload = json.loads(
            next(line.removeprefix("data: ") for line in blocks[2].splitlines() if line.startswith("data: "))
        )
        assert process_payload["agent"] == "agent1_context_router"
        assert process_payload["payload"]["route"] == "hybrid"
        assert final_payload["assistant_message"]["content"] == "智能体回复：五龄蚕发白变硬怎么办？"
        assert final_payload["agent_run"]["route"] == "hybrid"

        conversation_id = final_payload["conversation"]["id"]
        assistant_message_id = final_payload["assistant_message"]["id"]
        regenerate_response = client.post(
            f"/api/v1/diagnosis/conversations/{conversation_id}/messages/{assistant_message_id}/regenerate/stream",
            headers=auth_headers,
            json={},
        )
        assert regenerate_response.status_code == 200
        regenerate_events = [
            next(line.removeprefix("event: ") for line in block.splitlines() if line.startswith("event: "))
            for block in regenerate_response.text.split("\n\n")
            if block.strip()
        ]
        assert regenerate_events == ["ready", "process", "final"]
    finally:
        app.dependency_overrides.pop(get_settings, None)
        _cleanup_identity_auth_data("email", email)


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_voice_transcription_returns_text_without_persisting_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    email = "codex-diagnosis-voice@qq.com"
    _cleanup_identity_auth_data("email", email)

    def fake_settings() -> Settings:
        return Settings(
            openai_api_key="test-key",
            openai_base_url="https://example.test/v1",
            openai_model_id="gpt-5-nano",
            openai_transcription_model_id="whisper-test",
        )

    monkeypatch.setattr(
        "app.services.diagnosis_service.resolve_current_user_llm_config",
        lambda *args, **kwargs: OpenAICompatibleModelConfig(
            provider_name="Environment",
            model_id="gpt-5-nano",
            api_key="test-key",
            api_request_url="https://example.test/v1",
        ),
    )

    def fake_transcription(
        model_config: OpenAICompatibleModelConfig,
        *,
        audio_content: bytes,
        file_name: str,
        content_type: str,
        timeout_seconds: float,
        language: str = "zh",
    ) -> str:
        assert model_config.model_id == "whisper-test"
        assert audio_content == b"fake-audio-bytes"
        assert file_name == "voice.webm"
        assert content_type == "audio/webm"
        assert language == "zh"
        return "五龄蚕最近不吃桑叶，体色发白"

    monkeypatch.setattr("app.services.diagnosis_service.request_openai_compatible_transcription", fake_transcription)
    app.dependency_overrides[get_settings] = fake_settings

    try:
        login_payload = _login_with_email_dev_code(email)
        auth_headers = {"Authorization": f"Bearer {login_payload['access_token']}"}
        with SessionLocal() as db:
            before_count = len(list(db.scalars(select(UploadedFile))))

        response = client.post(
            "/api/v1/diagnosis/transcribe",
            headers=auth_headers,
            files={"audio": ("voice.webm", b"fake-audio-bytes", "audio/webm")},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload == {
            "text": "五龄蚕最近不吃桑叶，体色发白",
            "model": "whisper-test",
            "provider": "Environment",
        }
        with SessionLocal() as db:
            after_count = len(list(db.scalars(select(UploadedFile))))
        assert after_count == before_count
    finally:
        app.dependency_overrides.pop(get_settings, None)
        _cleanup_identity_auth_data("email", email)


@pytest.mark.skipif(not check_database_connection(), reason="database is not available")
def test_multimodal_diagnosis_upload_persists_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    email = "codex-diagnosis-multimodal@qq.com"
    _cleanup_identity_auth_data("email", email)

    def fake_settings() -> Settings:
        return Settings(openai_api_key="test-key", openai_base_url="https://example.test/v1", openai_model_id="gpt-5-nano")

    monkeypatch.setattr(
        "app.services.diagnosis_service.resolve_current_user_llm_config",
        lambda *args, **kwargs: OpenAICompatibleModelConfig(
            provider_name="Environment",
            model_id="gpt-5-nano",
            api_key="test-key",
            api_request_url="https://example.test/v1",
        ),
    )
    monkeypatch.setattr(
        "app.services.diagnosis_service.upload_object_file",
        lambda *, object_key, content, content_type, failure_detail="文件上传失败，请稍后再试": f"https://oss.test/{object_key}",
    )

    def fake_analyze_multimodal_materials(
        settings: Settings,
        *,
        message: str,
        files: list,
        structured_data: dict,
        model_config: OpenAICompatibleModelConfig,
    ) -> tuple[dict, str]:
        assert model_config.model_id == "gpt-5-nano"
        assert message == "帮我看一下这张蚕病图片"
        assert len(files) == 1
        assert files[0].file_name == "symptom.jpg"
        assert files[0].file_type == "image"
        assert structured_data == {"silkworm_age": "五龄"}
        return (
            {"mode": "multimodal_analysis", "fallback_used": False, "file_contexts": [{"file_type": "image"}]},
            "已解析 1 个多模态材料，提取结果将作为检索查询上下文。",
        )

    monkeypatch.setattr(
        "app.services.diagnosis_service.analyze_multimodal_materials",
        fake_analyze_multimodal_materials,
    )
    monkeypatch.setattr(
        "app.services.diagnosis_service.execute_diagnosis_agent",
        lambda *args, original_question, **kwargs: _fake_agent_execution(
            original_question,
            answer="已根据图片解析和知识证据生成问诊回复。",
        ),
    )
    app.dependency_overrides[get_settings] = fake_settings

    try:
        login_payload = _login_with_email_dev_code(email)
        auth_headers = {"Authorization": f"Bearer {login_payload['access_token']}"}

        response = client.post(
            "/api/v1/diagnosis/conversations/multimodal",
            headers=auth_headers,
            data={
                "message": "帮我看一下这张蚕病图片",
                "structured_data": json.dumps({"silkworm_age": "五龄"}),
            },
            files=[("attachments", ("symptom.jpg", b"fake-image-bytes", "image/jpeg"))],
        )

        assert response.status_code == 200
        payload = response.json()
        conversation_id = UUID(payload["conversation"]["id"])
        assert payload["user_message"]["attachments"][0]["file_name"] == "symptom.jpg"
        assert payload["user_message"]["attachments"][0]["file_type"] == "image"
        assert payload["user_message"]["attachments"][0]["storage_url"].startswith("https://oss.test/")
        assert payload["assistant_message"]["content"] == "已根据图片解析和知识证据生成问诊回复。"
        assert payload["agent_run"]["route"] == "hybrid"

        with SessionLocal() as db:
            analysis = db.scalar(
                select(DiagnosisMultimodalAnalysis).where(DiagnosisMultimodalAnalysis.conversation_id == conversation_id)
            )
            assert analysis is not None
            assert analysis.status == "completed"
            assert analysis.analysis_json["mode"] == "multimodal_analysis"
            assert analysis.analysis_text == "已解析 1 个多模态材料，提取结果将作为检索查询上下文。"
            assert len(analysis.file_ids) == 1
    finally:
        app.dependency_overrides.pop(get_settings, None)
        _cleanup_identity_auth_data("email", email)


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
            db.execute(delete(Conversation).where(Conversation.user_id.in_(user_ids)))
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

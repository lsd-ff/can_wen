from datetime import UTC, datetime, timedelta

from app.security import (
    _totp_code,
    create_access_token,
    create_mfa_ticket,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    now_utc,
    verify_password,
    verify_totp,
)
from app.routes.system import DEFAULT_RISK_RULES, HEALTH_SERVICE_ORDER, RISK_EVENT_SOURCES_SQL, _model_dict, _risk_event_params, _validate_health_settings, _validate_risk_rules
from app.schemas import AssetLifecycleRequest, ModelConfigRequest, RiskIncidentActionRequest
from app.services import write_audit


def test_password_hash_is_salted_and_verifiable() -> None:
    encoded = hash_password("a-long-administrator-password")

    assert verify_password("a-long-administrator-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_access_and_mfa_tokens_have_distinct_types() -> None:
    token, _ = create_access_token(account_id="11111111-1111-1111-1111-111111111111", session_id="22222222-2222-2222-2222-222222222222")
    ticket = create_mfa_ticket(account_id="11111111-1111-1111-1111-111111111111", purpose="login")

    assert decode_token(token, expected_type="access")["aud"] == "canw-admin"
    assert decode_token(ticket, expected_type="mfa-ticket")["purpose"] == "login"


def test_totp_and_encrypted_factor_secret_round_trip() -> None:
    secret = "JBSWY3DPEHPK3PXP"
    code = _totp_code(secret, int(now_utc().timestamp()) // 30)

    assert verify_totp(secret, code)
    assert decrypt_secret(encrypt_secret(secret)) == secret


def test_audit_payloads_are_json_safe() -> None:
    recorded = []

    class FakeSession:
        def add(self, value: object) -> None:
            recorded.append(value)

    write_audit(
        FakeSession(),  # type: ignore[arg-type]
        actor_id=None,
        action="models.tested",
        resource_type="system_model",
        resource_id="model-1",
        before_data={"tested_at": datetime(2026, 7, 13, tzinfo=UTC)},
    )

    assert recorded[0].before_data == {"tested_at": "2026-07-13T00:00:00+00:00"}


def test_risk_events_exclude_plain_business_todos() -> None:
    """A single ordinary report belongs in business review, not the risk queue."""
    query = RISK_EVENT_SOURCES_SQL.lower()

    assert "pending_report" not in query
    for event_type in (
        "repeated_login_failure",
        "unusual_login_ip",
        "admin_permission_change",
        "sensitive_admin_action",
        "multimodal_failure",
        "background_job_failure",
        "report_surge",
        "posting_spike",
        "critical_case_overdue",
    ):
        assert event_type in query


def test_risk_incident_source_query_has_stable_deduplication_identity() -> None:
    query = RISK_EVENT_SOURCES_SQL.lower()

    assert "fingerprint" in query
    assert "resource_type" in query
    assert "resource_id" in query
    assert "pending_report" not in query
    params = _risk_event_params(DEFAULT_RISK_RULES)
    assert params["login_failure_count"] == 3
    assert params["critical_case_sla_hours"] == 4


def test_risk_action_and_rules_validation() -> None:
    assert RiskIncidentActionRequest(action="resolve", note="已核查并完成修复").action == "resolve"
    assert RiskIncidentActionRequest(action="suppress", note="维护窗口内由值班人员跟进", suppress_hours=24).suppress_hours == 24
    _validate_risk_rules({"login_failure_count": 4, "sla_hours": {"critical": 2, "high": 12}})


def test_health_settings_validate_probe_and_maintenance_contract() -> None:
    _validate_health_settings({
        "probes": {"user_api_url": "http://127.0.0.1:8010/healthz", "object_storage_url": "https://storage.example.com/healthz", "timeout_seconds": 3},
        "maintenance": {
            "enabled": True,
            "services": ["object_storage"],
            "ends_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "message": "存储供应商例行升级",
        },
    })
    assert {"redis", "qdrant", "opensearch", "neo4j"} <= set(HEALTH_SERVICE_ORDER)


def test_asset_lifecycle_request_allows_only_reversible_governance_actions() -> None:
    assert AssetLifecycleRequest(action="quarantine", reason="疑似不合规附件，等待核查").action == "quarantine"
    assert AssetLifecycleRequest(action="restore", reason="核查后确认文件正常").action == "restore"
    assert AssetLifecycleRequest(action="delete", reason="重复上传，执行软删除").action == "delete"


def test_model_config_can_explicitly_clear_an_independent_key() -> None:
    payload = ModelConfigRequest(
        key="qa",
        label="QA 抽取模型",
        model_id="qwen-plus",
        api_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        capability="chat",
        clear_api_key=True,
        reason="改用系统统一凭证",
    )

    assert payload.clear_api_key is True
    assert payload.api_key is None


def test_model_payload_reports_the_real_credential_source(monkeypatch) -> None:
    from types import SimpleNamespace

    import app.routes.system as system_routes

    monkeypatch.setattr(system_routes.settings, "dashscope_api_key", "system-key")
    item = SimpleNamespace(
        id="model-1",
        key="qa",
        label="QA 抽取模型",
        model_id="qwen-plus",
        api_base_url="https://example.test/v1",
        capability="chat",
        enabled=True,
        api_key_ciphertext=None,
        last_test_status="passed",
        last_test_message="连接成功",
        last_test_at=None,
        created_at=None,
        updated_at=None,
    )

    assert _model_dict(item)["credential_source"] == "system"
    item.api_key_ciphertext = "encrypted"
    assert _model_dict(item)["credential_source"] == "model"

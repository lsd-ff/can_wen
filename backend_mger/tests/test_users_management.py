from app.main import app
from app.routes.users import _build_user_filters, _user_row, _user_sort


def test_attention_filter_uses_account_bound_security_history() -> None:
    _where, params = _build_user_filters(
        q=None,
        status_filter=None,
        role=None,
        verification_status=None,
        created_since=None,
        attention="security",
    )

    condition = " ".join(_where)
    assert "login_identity" in condition
    assert "count(*) FROM login_events" in condition
    assert ")) >= 3" in condition
    assert params == {}


def test_user_row_marks_deleted_accounts_as_deleted() -> None:
    row = {
        "id": "4c15df40-121a-4596-8e17-cc70ec2ac071",
        "display_name": "Test User",
        "role": "farmer",
        "status": "active",
        "deleted_at": "2026-07-15T08:00:00+08:00",
        "email": "test@example.com",
        "phone_number": None,
        "registered_at": "2026-07-15T08:00:00+08:00",
        "last_seen_at": None,
        "conversation_count": 0,
        "post_count": 0,
        "open_case_count": 0,
        "active_session_count": 0,
        "pending_report_count": 0,
        "login_failure_count_7d": 0,
        "verification_failure_count_7d": 0,
        "latest_security_event_at": None,
        "attention_level": "none",
    }

    item = _user_row(row)

    assert item["status"] == "deleted"
    assert item["attention_level"] == "none"
    assert item["active_session_count"] == 0


def test_attention_sort_uses_source_columns_instead_of_select_alias() -> None:
    order_by = _user_sort("attention")

    assert "attention_level" not in order_by
    assert "reports.pending_report_count" in order_by
    assert "security.login_failure_count_7d" in order_by
    assert "cp.verification_status" in order_by


def test_user_management_routes_are_exposed() -> None:
    paths = app.openapi()["paths"]

    assert "/api/admin/v1/users/overview" in paths
    assert "/api/admin/v1/users/batch-action" in paths


def test_user_list_contract_keeps_attention_sort_available() -> None:
    parameters = app.openapi()["paths"]["/api/admin/v1/users"]["get"]["parameters"]
    sort = next(parameter for parameter in parameters if parameter["name"] == "sort")

    assert "attention" in sort["schema"]["pattern"]

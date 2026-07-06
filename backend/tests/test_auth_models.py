from app.db.base import Base
import app.models  # noqa: F401
from app.models import (
    AuthSession,
    AuthVerificationCode,
    LoginEvent,
    User,
    UserIdentity,
)


def test_auth_models_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "auth_sessions",
        "auth_verification_codes",
        "login_events",
        "user_identities",
        "users",
    }


def test_auth_models_map_metadata_columns() -> None:
    assert UserIdentity.metadata_.property.columns[0].name == "metadata"
    assert AuthVerificationCode.metadata_.property.columns[0].name == "metadata"
    assert AuthSession.metadata_.property.columns[0].name == "metadata"
    assert LoginEvent.metadata_.property.columns[0].name == "metadata"


def test_auth_model_relationships() -> None:
    assert User.identities.property.mapper.class_ is UserIdentity
    assert User.sessions.property.mapper.class_ is AuthSession
    assert User.login_events.property.mapper.class_ is LoginEvent

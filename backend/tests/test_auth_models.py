from app.db.base import Base
import app.models  # noqa: F401
from app.models import (
    AuthSession,
    AuthVerificationCode,
    Diagnosis,
    DiagnosisEvidence,
    DiagnosisMultimodalAnalysis,
    ExpertReview,
    LLMModelConfig,
    Message,
    LoginEvent,
    Project,
    User,
    UserIdentity,
    UploadedFile,
)


def test_auth_models_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "admin.expert_reviews",
        "auth_sessions",
        "auth_verification_codes",
        "community_bookmark_collection_items",
        "community_bookmark_collections",
        "community_case_updates",
        "community_comment_likes",
        "community_comments",
        "community_direct_messages",
        "community_direct_threads",
        "community_follows",
        "community_interaction_events",
        "community_notifications",
        "community_post_assets",
        "community_post_bookmarks",
        "community_post_likes",
        "community_post_preferences",
        "community_post_tags",
        "community_posts",
        "community_profiles",
        "community_reports",
        "community_tags",
        "community_topic_follows",
        "community_user_blocks",
        "conversation_shares",
        "conversation_tags",
        "conversations",
        "diagnosis_evidence",
        "diagnosis_multimodal_analyses",
        "diagnoses",
        "farms",
        "files",
        "husbandry_case_follow_ups",
        "husbandry_cases",
        "husbandry_daily_records",
        "husbandry_record_assets",
        "login_events",
        "llm_model_configs",
        "message_files",
        "messages",
        "project_shares",
        "projects",
        "silkworm_batches",
        "user_identities",
        "user_settings",
        "users",
    }


def test_expert_review_model_uses_admin_schema() -> None:
    assert ExpertReview.__table__.schema == "admin"


def test_auth_models_map_metadata_columns() -> None:
    assert UserIdentity.metadata_.property.columns[0].name == "metadata"
    assert AuthVerificationCode.metadata_.property.columns[0].name == "metadata"
    assert AuthSession.metadata_.property.columns[0].name == "metadata"
    assert LoginEvent.metadata_.property.columns[0].name == "metadata"
    assert Message.metadata_.property.columns[0].name == "metadata"
    assert UploadedFile.metadata_.property.columns[0].name == "metadata"
    assert Diagnosis.metadata_.property.columns[0].name == "metadata"
    assert DiagnosisEvidence.metadata_.property.columns[0].name == "metadata"
    assert LLMModelConfig.metadata_.property.columns[0].name == "metadata"


def test_auth_model_relationships() -> None:
    assert User.identities.property.mapper.class_ is UserIdentity
    assert User.sessions.property.mapper.class_ is AuthSession
    assert User.login_events.property.mapper.class_ is LoginEvent


def test_p0_model_relationships() -> None:
    assert Project.conversations.property.mapper.class_.__name__ == "Conversation"
    assert Project.files.property.mapper.class_ is UploadedFile
    assert Message.conversation.property.mapper.class_.__name__ == "Conversation"
    assert Message.multimodal_analyses.property.mapper.class_ is DiagnosisMultimodalAnalysis
    assert Diagnosis.evidence.property.mapper.class_ is DiagnosisEvidence

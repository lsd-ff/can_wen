"""community v2 structured cases and professional collaboration

Revision ID: 20260711_0011
Revises: 20260710_0010
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op


revision = "20260711_0011"
down_revision = "20260710_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS source_husbandry_case_id uuid REFERENCES husbandry_cases(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS accepted_comment_id uuid")
    op.execute("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS question_status text NOT NULL DEFAULT 'open'")
    op.execute("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS knowledge_status text NOT NULL DEFAULT 'none'")
    op.execute("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS case_data jsonb NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE community_posts DROP CONSTRAINT IF EXISTS community_posts_question_status_allowed")
    op.execute("ALTER TABLE community_posts ADD CONSTRAINT community_posts_question_status_allowed CHECK (question_status IN ('open', 'resolved'))")
    op.execute("ALTER TABLE community_posts DROP CONSTRAINT IF EXISTS community_posts_knowledge_status_allowed")
    op.execute("ALTER TABLE community_posts ADD CONSTRAINT community_posts_knowledge_status_allowed CHECK (knowledge_status IN ('none', 'pending', 'approved', 'rejected'))")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_posts_source_husbandry_case ON community_posts (source_husbandry_case_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_posts_question_status ON community_posts (post_type, question_status, published_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_case_updates (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            author_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            occurred_on date NOT NULL DEFAULT CURRENT_DATE,
            outcome_status text NOT NULL DEFAULT 'observing' CHECK (outcome_status IN ('observing', 'improved', 'stable', 'worsened', 'resolved')),
            content text NOT NULL,
            metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_case_updates_post_date ON community_case_updates (post_id, occurred_on DESC)")
    op.execute("DROP TRIGGER IF EXISTS trg_community_case_updates_updated_at ON community_case_updates")
    op.execute("CREATE TRIGGER trg_community_case_updates_updated_at BEFORE UPDATE ON community_case_updates FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_profiles (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            identity_type text NOT NULL DEFAULT 'farmer' CHECK (identity_type IN ('farmer', 'technician', 'researcher', 'other')),
            region text,
            organization text,
            expertise_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
            years_experience integer CHECK (years_experience IS NULL OR years_experience >= 0),
            bio text,
            verification_status text NOT NULL DEFAULT 'unverified' CHECK (verification_status IN ('unverified', 'pending', 'verified', 'rejected')),
            verified_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_profiles_discovery ON community_profiles (verification_status, identity_type)")
    op.execute("DROP TRIGGER IF EXISTS trg_community_profiles_updated_at ON community_profiles")
    op.execute("CREATE TRIGGER trg_community_profiles_updated_at BEFORE UPDATE ON community_profiles FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_user_blocks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            blocker_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            blocked_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT community_user_blocks_distinct_users CHECK (blocker_id <> blocked_id),
            CONSTRAINT uq_community_user_blocks_pair UNIQUE (blocker_id, blocked_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_user_blocks_blocker ON community_user_blocks (blocker_id, blocked_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_post_preferences (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            post_id uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            preference_type text NOT NULL DEFAULT 'not_interested' CHECK (preference_type IN ('not_interested', 'hidden')),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_community_post_preferences_user_post UNIQUE (user_id, post_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_post_preferences_user ON community_post_preferences (user_id, created_at DESC)")

    op.execute("ALTER TABLE community_posts DROP CONSTRAINT IF EXISTS fk_community_posts_accepted_comment")
    op.execute("ALTER TABLE community_posts ADD CONSTRAINT fk_community_posts_accepted_comment FOREIGN KEY (accepted_comment_id) REFERENCES community_comments(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE community_notifications DROP CONSTRAINT IF EXISTS community_notifications_type_allowed")
    op.execute("ALTER TABLE community_notifications ADD CONSTRAINT community_notifications_type_allowed CHECK (notification_type IN ('post_like', 'post_comment', 'comment_reply', 'comment_like', 'follow', 'moderation', 'answer_accepted', 'case_update'))")


def downgrade() -> None:
    op.execute("ALTER TABLE community_notifications DROP CONSTRAINT IF EXISTS community_notifications_type_allowed")
    op.execute("ALTER TABLE community_notifications ADD CONSTRAINT community_notifications_type_allowed CHECK (notification_type IN ('post_like', 'post_comment', 'comment_reply', 'comment_like', 'follow', 'moderation'))")
    op.execute("ALTER TABLE community_posts DROP CONSTRAINT IF EXISTS fk_community_posts_accepted_comment")
    op.execute("DROP TABLE IF EXISTS community_post_preferences")
    op.execute("DROP TABLE IF EXISTS community_user_blocks")
    op.execute("DROP TRIGGER IF EXISTS trg_community_profiles_updated_at ON community_profiles")
    op.execute("DROP TABLE IF EXISTS community_profiles")
    op.execute("DROP TRIGGER IF EXISTS trg_community_case_updates_updated_at ON community_case_updates")
    op.execute("DROP TABLE IF EXISTS community_case_updates")
    op.execute("DROP INDEX IF EXISTS idx_community_posts_question_status")
    op.execute("DROP INDEX IF EXISTS idx_community_posts_source_husbandry_case")
    op.execute("ALTER TABLE community_posts DROP COLUMN IF EXISTS case_data")
    op.execute("ALTER TABLE community_posts DROP COLUMN IF EXISTS knowledge_status")
    op.execute("ALTER TABLE community_posts DROP COLUMN IF EXISTS question_status")
    op.execute("ALTER TABLE community_posts DROP COLUMN IF EXISTS accepted_comment_id")
    op.execute("ALTER TABLE community_posts DROP COLUMN IF EXISTS source_husbandry_case_id")

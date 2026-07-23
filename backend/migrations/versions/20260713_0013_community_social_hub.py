"""community social hub: topics, discovery signals and direct messages

Revision ID: 20260713_0013
Revises: 9616b2eaa448
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op


revision = "20260713_0013"
down_revision = "9616b2eaa448"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_topic_follows (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tag_id uuid NOT NULL REFERENCES community_tags(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_community_topic_follows_user_tag UNIQUE (user_id, tag_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_topic_follows_user_created ON community_topic_follows (user_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_topic_follows_tag ON community_topic_follows (tag_id, user_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_interaction_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            post_id uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            event_type text NOT NULL CHECK (event_type IN ('view', 'like', 'bookmark', 'comment', 'not_interested')),
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_interaction_events_user_created ON community_interaction_events (user_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_interaction_events_user_post ON community_interaction_events (user_id, post_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_direct_threads (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            participant_one_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            participant_two_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            last_message_preview text NOT NULL DEFAULT '',
            last_message_at timestamptz NOT NULL DEFAULT now(),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT community_direct_threads_distinct_users CHECK (participant_one_id <> participant_two_id),
            CONSTRAINT uq_community_direct_threads_pair UNIQUE (participant_one_id, participant_two_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_direct_threads_one_recent ON community_direct_threads (participant_one_id, last_message_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_direct_threads_two_recent ON community_direct_threads (participant_two_id, last_message_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_direct_messages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id uuid NOT NULL REFERENCES community_direct_threads(id) ON DELETE CASCADE,
            sender_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            recipient_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content text NOT NULL,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleted')),
            read_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_direct_messages_thread_created ON community_direct_messages (thread_id, created_at ASC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_direct_messages_recipient_unread ON community_direct_messages (recipient_id, read_at)")

    op.execute("ALTER TABLE community_notifications DROP CONSTRAINT IF EXISTS community_notifications_type_allowed")
    op.execute(
        """
        ALTER TABLE community_notifications
        ADD CONSTRAINT community_notifications_type_allowed
        CHECK (notification_type IN (
            'post_like', 'post_comment', 'comment_reply', 'comment_like', 'follow',
            'moderation', 'answer_accepted', 'case_update', 'mention', 'direct_message'
        ))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE community_notifications DROP CONSTRAINT IF EXISTS community_notifications_type_allowed")
    op.execute(
        """
        ALTER TABLE community_notifications
        ADD CONSTRAINT community_notifications_type_allowed
        CHECK (notification_type IN (
            'post_like', 'post_comment', 'comment_reply', 'comment_like', 'follow',
            'moderation', 'answer_accepted', 'case_update'
        ))
        """
    )
    op.execute("DROP TABLE IF EXISTS community_direct_messages")
    op.execute("DROP TABLE IF EXISTS community_direct_threads")
    op.execute("DROP TABLE IF EXISTS community_interaction_events")
    op.execute("DROP TABLE IF EXISTS community_topic_follows")

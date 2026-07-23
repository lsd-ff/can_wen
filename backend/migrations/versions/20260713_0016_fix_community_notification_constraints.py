"""fix community notification type constraints

Revision ID: 20260713_0016
Revises: 20260713_0015
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op


revision = "20260713_0016"
down_revision = "20260713_0015"
branch_labels = None
depends_on = None


_CURRENT_NOTIFICATION_TYPES = (
    "'post_like', 'post_comment', 'comment_reply', 'comment_like', 'follow', "
    "'moderation', 'answer_accepted', 'case_update', 'mention', 'direct_message'"
)


def upgrade() -> None:
    # The initial inline constraint received PostgreSQL's generated name while
    # later migrations only replaced the explicitly named constraint. Both
    # must be removed so the application-supported notification types work.
    op.execute("ALTER TABLE community_notifications DROP CONSTRAINT IF EXISTS community_notifications_notification_type_check")
    op.execute("ALTER TABLE community_notifications DROP CONSTRAINT IF EXISTS community_notifications_type_allowed")
    op.execute(
        "ALTER TABLE community_notifications ADD CONSTRAINT community_notifications_type_allowed "
        f"CHECK (notification_type IN ({_CURRENT_NOTIFICATION_TYPES}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE community_notifications DROP CONSTRAINT IF EXISTS community_notifications_type_allowed")
    op.execute(
        "ALTER TABLE community_notifications ADD CONSTRAINT community_notifications_notification_type_check "
        "CHECK (notification_type IN ('post_like', 'post_comment', 'comment_reply', 'comment_like', 'follow', 'moderation'))"
    )
    op.execute(
        "ALTER TABLE community_notifications ADD CONSTRAINT community_notifications_type_allowed "
        f"CHECK (notification_type IN ({_CURRENT_NOTIFICATION_TYPES}))"
    )

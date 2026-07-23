"""add pinned timestamps to projects and conversations

Revision ID: 20260709_0006
Revises: 20260708_0005
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op


revision = "20260709_0006"
down_revision = "20260708_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS pinned_at timestamptz")
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS pinned_at timestamptz")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_projects_owner_status_pinned_updated
            ON projects (owner_id, status, pinned_at DESC NULLS LAST, updated_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_user_status_pinned_last
            ON conversations (user_id, status, pinned_at DESC NULLS LAST, last_message_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_project_status_pinned_updated
            ON conversations (project_id, status, pinned_at DESC NULLS LAST, updated_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_conversations_project_status_pinned_updated")
    op.execute("DROP INDEX IF EXISTS idx_conversations_user_status_pinned_last")
    op.execute("DROP INDEX IF EXISTS idx_projects_owner_status_pinned_updated")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS pinned_at")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS pinned_at")

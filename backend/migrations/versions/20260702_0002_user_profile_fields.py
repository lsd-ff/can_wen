"""add user profile fields

Revision ID: 20260702_0002
Revises: 20260702_0001
Create Date: 2026-07-02
"""

from __future__ import annotations

from alembic import op


revision = "20260702_0002"
down_revision = "20260702_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username text NOT NULL DEFAULT ''")
    op.execute("COMMENT ON COLUMN users.username IS '用户公开用户名，用于个人资料展示。'")
    op.execute(
        """
        UPDATE users
        SET username = left(display_name, 32)
        WHERE username = ''
          AND display_name <> ''
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS username")

"""persisted user settings and account preferences

Revision ID: 20260711_0012
Revises: 20260711_0011
Create Date: 2026-07-11
"""

from __future__ import annotations

from alembic import op


revision = "20260711_0012"
down_revision = "20260711_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_user_settings_updated_at ON user_settings")
    op.execute(
        "CREATE TRIGGER trg_user_settings_updated_at BEFORE UPDATE ON user_settings "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_user_settings_updated_at ON user_settings")
    op.execute("DROP TABLE IF EXISTS user_settings")

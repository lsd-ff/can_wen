"""create llm model configs

Revision ID: 20260707_0004
Revises: 20260706_0003
Create Date: 2026-07-07
"""

from __future__ import annotations

from alembic import op


revision = "20260707_0004"
down_revision = "20260706_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_model_configs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider_name text NOT NULL,
            model_id text NOT NULL,
            api_key_ciphertext text NOT NULL,
            api_request_url text NOT NULL,
            is_enabled boolean NOT NULL DEFAULT true,
            is_default boolean NOT NULL DEFAULT false,
            last_test_status text
                CHECK (last_test_status IS NULL OR last_test_status IN ('success', 'failed')),
            last_test_message text,
            last_test_at timestamptz,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_llm_model_configs_user_created
            ON llm_model_configs (user_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_llm_model_configs_user_default
            ON llm_model_configs (user_id, is_default)
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_llm_model_configs_updated_at ON llm_model_configs")
    op.execute(
        """
        CREATE TRIGGER trg_llm_model_configs_updated_at
            BEFORE UPDATE ON llm_model_configs
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_llm_model_configs_updated_at ON llm_model_configs")
    op.execute("DROP TABLE IF EXISTS llm_model_configs")

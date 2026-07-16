"""create conversation share table

Revision ID: 20260709_0007
Revises: 20260709_0006
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op


revision = "20260709_0007"
down_revision = "20260709_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_shares (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            share_token text NOT NULL,
            title text NOT NULL,
            variant text NOT NULL DEFAULT 'summary'
                CHECK (variant IN ('summary', 'full-record', 'expert-review')),
            content_markdown text NOT NULL,
            status text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'revoked', 'deleted')),
            view_count bigint NOT NULL DEFAULT 0,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz,
            revoked_at timestamptz,
            CONSTRAINT uq_conversation_shares_share_token UNIQUE (share_token)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_shares_conversation_created
            ON conversation_shares (conversation_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_shares_token_status
            ON conversation_shares (share_token, status)
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_conversation_shares_updated_at ON conversation_shares")
    op.execute(
        """
        CREATE TRIGGER trg_conversation_shares_updated_at
            BEFORE UPDATE ON conversation_shares
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )
    op.execute("COMMENT ON TABLE conversation_shares IS '会话分享表：保存可公开访问的问诊会话 Markdown 快照。'")
    op.execute("COMMENT ON COLUMN conversation_shares.share_token IS '公开分享访问令牌。'")
    op.execute("COMMENT ON COLUMN conversation_shares.content_markdown IS '分享时生成的 Markdown 快照。'")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_conversation_shares_updated_at ON conversation_shares")
    op.execute("DROP TABLE IF EXISTS conversation_shares")

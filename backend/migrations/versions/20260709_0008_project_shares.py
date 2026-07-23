"""create project share table

Revision ID: 20260709_0008
Revises: 20260709_0007
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op


revision = "20260709_0008"
down_revision = "20260709_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS project_shares (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
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
            CONSTRAINT uq_project_shares_share_token UNIQUE (share_token)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_project_shares_project_created
            ON project_shares (project_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_project_shares_token_status
            ON project_shares (share_token, status)
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_project_shares_updated_at ON project_shares")
    op.execute(
        """
        CREATE TRIGGER trg_project_shares_updated_at
            BEFORE UPDATE ON project_shares
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )
    op.execute("COMMENT ON TABLE project_shares IS '项目分享表：保存可公开访问的项目 Markdown 快照。'")
    op.execute("COMMENT ON COLUMN project_shares.share_token IS '公开分享访问令牌。'")
    op.execute("COMMENT ON COLUMN project_shares.content_markdown IS '分享时生成的 Markdown 快照。'")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_project_shares_updated_at ON project_shares")
    op.execute("DROP TABLE IF EXISTS project_shares")

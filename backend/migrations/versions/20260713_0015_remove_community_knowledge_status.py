"""remove unused community knowledge-review state

Revision ID: 20260713_0015
Revises: 20260713_0014
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op


revision = "20260713_0015"
down_revision = "20260713_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE community_posts DROP CONSTRAINT IF EXISTS community_posts_knowledge_status_allowed")
    op.execute("ALTER TABLE community_posts DROP COLUMN IF EXISTS knowledge_status")


def downgrade() -> None:
    op.execute("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS knowledge_status text NOT NULL DEFAULT 'none'")
    op.execute("ALTER TABLE community_posts DROP CONSTRAINT IF EXISTS community_posts_knowledge_status_allowed")
    op.execute(
        "ALTER TABLE community_posts ADD CONSTRAINT community_posts_knowledge_status_allowed "
        "CHECK (knowledge_status IN ('none', 'pending', 'approved', 'rejected'))"
    )

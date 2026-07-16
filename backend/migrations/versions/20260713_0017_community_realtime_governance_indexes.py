"""add community governance query indexes

Revision ID: 20260713_0017
Revises: 20260713_0016
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op


revision = "20260713_0017"
down_revision = "20260713_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_posts_author_created ON community_posts (author_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_comments_author_created ON community_comments (author_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_direct_messages_sender_created ON community_direct_messages (sender_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_community_direct_messages_sender_created")
    op.execute("DROP INDEX IF EXISTS idx_community_comments_author_created")
    op.execute("DROP INDEX IF EXISTS idx_community_posts_author_created")

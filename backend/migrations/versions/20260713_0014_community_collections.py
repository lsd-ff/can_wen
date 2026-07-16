"""community bookmark collections

Revision ID: 20260713_0014
Revises: 20260713_0013
Create Date: 2026-07-13
"""

from __future__ import annotations

from alembic import op


revision = "20260713_0014"
down_revision = "20260713_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_bookmark_collections (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name text NOT NULL,
            description text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_community_bookmark_collections_owner_name UNIQUE (owner_id, name)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_community_bookmark_collections_owner_updated "
        "ON community_bookmark_collections (owner_id, updated_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_bookmark_collection_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            collection_id uuid NOT NULL REFERENCES community_bookmark_collections(id) ON DELETE CASCADE,
            post_id uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_community_bookmark_collection_items_collection_post UNIQUE (collection_id, post_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_community_bookmark_collection_items_collection_created "
        "ON community_bookmark_collection_items (collection_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS community_bookmark_collection_items")
    op.execute("DROP TABLE IF EXISTS community_bookmark_collections")

"""remove obsolete expert review indexes

Revision ID: 20260722_0007
Revises: 20260720_0006
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op


revision = "20260722_0007"
down_revision = "20260720_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS admin.idx_expert_reviews_case")
    op.execute("DROP INDEX IF EXISTS admin.idx_expert_reviews_conversation")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_expert_reviews_case_status "
        "ON admin.expert_reviews (husbandry_case_id, status, published_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_expert_reviews_conversation_status "
        "ON admin.expert_reviews (conversation_id, status, published_at DESC)"
    )


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_expert_reviews_case "
        "ON admin.expert_reviews (husbandry_case_id, published_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_expert_reviews_conversation "
        "ON admin.expert_reviews (conversation_id, published_at DESC)"
    )

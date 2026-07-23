"""add husbandry record assets

Revision ID: 20260714_0018
Revises: 20260713_0017
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op


revision = "20260714_0018"
down_revision = "20260713_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE husbandry_record_assets (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            daily_record_id uuid REFERENCES husbandry_daily_records(id) ON DELETE CASCADE,
            case_id uuid REFERENCES husbandry_cases(id) ON DELETE CASCADE,
            file_id uuid NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT husbandry_record_assets_single_owner CHECK (
                (daily_record_id IS NOT NULL AND case_id IS NULL)
                OR (daily_record_id IS NULL AND case_id IS NOT NULL)
            ),
            CONSTRAINT uq_husbandry_daily_record_assets_file UNIQUE (daily_record_id, file_id),
            CONSTRAINT uq_husbandry_case_assets_file UNIQUE (case_id, file_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_husbandry_record_assets_daily ON husbandry_record_assets (daily_record_id, created_at ASC)")
    op.execute("CREATE INDEX idx_husbandry_record_assets_case ON husbandry_record_assets (case_id, created_at ASC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS husbandry_record_assets")

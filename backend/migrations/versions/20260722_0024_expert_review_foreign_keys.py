"""ensure expert review foreign keys exist

Revision ID: 20260722_0024
Revises: 20260722_0023
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op


revision = "20260722_0024"
down_revision = "20260722_0023"
branch_labels = None
depends_on = None


FOREIGN_KEYS = (
    ("conversation_id", "public.conversations", "CASCADE"),
    ("source_message_id", "public.messages", "SET NULL"),
    ("diagnosis_id", "public.diagnoses", "SET NULL"),
    ("husbandry_case_id", "public.husbandry_cases", "CASCADE"),
    ("user_id", "public.users", "SET NULL"),
    ("reviewer_id", "public.users", "RESTRICT"),
)


def upgrade() -> None:
    for column_name, target_table, on_delete in FOREIGN_KEYS:
        constraint_name = f"fk_expert_reviews_{column_name}_{target_table.split('.')[-1]}"
        op.execute(
            f"""
            DO $$
            BEGIN
                IF to_regclass('admin.expert_reviews') IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1
                       FROM pg_constraint AS constraint_row
                       JOIN pg_attribute AS source_column
                         ON source_column.attrelid = constraint_row.conrelid
                        AND source_column.attnum = constraint_row.conkey[1]
                       WHERE constraint_row.contype = 'f'
                         AND constraint_row.conrelid = 'admin.expert_reviews'::regclass
                         AND source_column.attname = '{column_name}'
                         AND constraint_row.confrelid = '{target_table}'::regclass
                   ) THEN
                    ALTER TABLE admin.expert_reviews
                    ADD CONSTRAINT {constraint_name}
                    FOREIGN KEY ({column_name}) REFERENCES {target_table}(id)
                    ON DELETE {on_delete}
                    NOT VALID;
                END IF;
            END
            $$;
            """
        )


def downgrade() -> None:
    for column_name, target_table, _ in reversed(FOREIGN_KEYS):
        constraint_name = f"fk_expert_reviews_{column_name}_{target_table.split('.')[-1]}"
        op.execute(f"ALTER TABLE admin.expert_reviews DROP CONSTRAINT IF EXISTS {constraint_name}")

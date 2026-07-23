"""add administrator management and expert reviews

Revision ID: 20260714_0019
Revises: 20260714_0018
Create Date: 2026-07-14
"""

from __future__ import annotations

from alembic import op


revision = "20260714_0019"
down_revision = "20260714_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS admin")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.expert_reviews (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid REFERENCES public.conversations(id) ON DELETE CASCADE,
            source_message_id uuid REFERENCES public.messages(id) ON DELETE SET NULL,
            diagnosis_id uuid REFERENCES public.diagnoses(id) ON DELETE SET NULL,
            husbandry_case_id uuid REFERENCES public.husbandry_cases(id) ON DELETE CASCADE,
            user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,
            reviewer_id uuid NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
            reviewer_name_snapshot text NOT NULL,
            risk_level text NOT NULL DEFAULT 'medium',
            conclusion text NOT NULL,
            recommendation text NOT NULL,
            evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
            status text NOT NULL DEFAULT 'draft',
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            published_at timestamptz,
            CONSTRAINT expert_reviews_risk_allowed CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
            CONSTRAINT expert_reviews_status_allowed CHECK (status IN ('draft', 'published', 'superseded'))
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_expert_reviews_case_status "
        "ON admin.expert_reviews (husbandry_case_id, status, published_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_expert_reviews_conversation_status "
        "ON admin.expert_reviews (conversation_id, status, published_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin.expert_reviews")

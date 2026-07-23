"""create husbandry workbench tables

Revision ID: 20260710_0010
Revises: 20260710_0009
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op


revision = "20260710_0010"
down_revision = "20260710_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS farms (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name text NOT NULL,
            location text,
            notes text,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_farms_owner_status_created ON farms (owner_id, status, created_at DESC)")
    op.execute("DROP TRIGGER IF EXISTS trg_farms_updated_at ON farms")
    op.execute(
        """
        CREATE TRIGGER trg_farms_updated_at
            BEFORE UPDATE ON farms
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS silkworm_batches (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            farm_id uuid NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
            project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
            batch_code text,
            variety text,
            instar text,
            start_date date,
            expected_cocooning_date date,
            population_count integer CHECK (population_count IS NULL OR population_count >= 0),
            environment_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            notes text,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'finished', 'archived')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_silkworm_batches_farm_status_created ON silkworm_batches (farm_id, status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_silkworm_batches_project_status ON silkworm_batches (project_id, status)")
    op.execute("DROP TRIGGER IF EXISTS trg_silkworm_batches_updated_at ON silkworm_batches")
    op.execute(
        """
        CREATE TRIGGER trg_silkworm_batches_updated_at
            BEFORE UPDATE ON silkworm_batches
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS husbandry_daily_records (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id uuid NOT NULL REFERENCES silkworm_batches(id) ON DELETE CASCADE,
            record_date date NOT NULL,
            temperature_celsius numeric(4, 1) CHECK (temperature_celsius IS NULL OR (temperature_celsius >= -30 AND temperature_celsius <= 80)),
            humidity_percent numeric(5, 2) CHECK (humidity_percent IS NULL OR (humidity_percent >= 0 AND humidity_percent <= 100)),
            feedings integer CHECK (feedings IS NULL OR feedings >= 0),
            leaf_amount_kg numeric(8, 2) CHECK (leaf_amount_kg IS NULL OR leaf_amount_kg >= 0),
            sick_count integer CHECK (sick_count IS NULL OR sick_count >= 0),
            death_count integer CHECK (death_count IS NULL OR death_count >= 0),
            observations text,
            management_notes text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_husbandry_daily_records_batch_date UNIQUE (batch_id, record_date)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_husbandry_daily_records_batch_date ON husbandry_daily_records (batch_id, record_date DESC)")
    op.execute("DROP TRIGGER IF EXISTS trg_husbandry_daily_records_updated_at ON husbandry_daily_records")
    op.execute(
        """
        CREATE TRIGGER trg_husbandry_daily_records_updated_at
            BEFORE UPDATE ON husbandry_daily_records
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS husbandry_cases (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            farm_id uuid NOT NULL REFERENCES farms(id) ON DELETE RESTRICT,
            batch_id uuid REFERENCES silkworm_batches(id) ON DELETE SET NULL,
            project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
            source_conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
            title text NOT NULL,
            occurred_on date NOT NULL DEFAULT CURRENT_DATE,
            symptom_summary text,
            suspected_disease text,
            severity text NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
            status text NOT NULL DEFAULT 'needs_more_info' CHECK (status IN ('needs_more_info', 'suspected', 'processing', 'closed')),
            diagnosis_summary text,
            recommendation text,
            source_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            closed_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_husbandry_cases_owner_status_created ON husbandry_cases (owner_id, status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_husbandry_cases_batch_status_occurred ON husbandry_cases (batch_id, status, occurred_on DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_husbandry_cases_conversation ON husbandry_cases (source_conversation_id)")
    op.execute("DROP TRIGGER IF EXISTS trg_husbandry_cases_updated_at ON husbandry_cases")
    op.execute(
        """
        CREATE TRIGGER trg_husbandry_cases_updated_at
            BEFORE UPDATE ON husbandry_cases
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS husbandry_case_follow_ups (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id uuid NOT NULL REFERENCES husbandry_cases(id) ON DELETE CASCADE,
            observed_on date NOT NULL DEFAULT CURRENT_DATE,
            action_taken text,
            note text,
            affected_count integer CHECK (affected_count IS NULL OR affected_count >= 0),
            death_count integer CHECK (death_count IS NULL OR death_count >= 0),
            next_follow_up_on date,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_husbandry_case_follow_ups_case_observed ON husbandry_case_follow_ups (case_id, observed_on DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_husbandry_case_follow_ups_next_follow_up ON husbandry_case_follow_ups (next_follow_up_on)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS husbandry_case_follow_ups")
    op.execute("DROP TRIGGER IF EXISTS trg_husbandry_cases_updated_at ON husbandry_cases")
    op.execute("DROP TABLE IF EXISTS husbandry_cases")
    op.execute("DROP TRIGGER IF EXISTS trg_husbandry_daily_records_updated_at ON husbandry_daily_records")
    op.execute("DROP TABLE IF EXISTS husbandry_daily_records")
    op.execute("DROP TRIGGER IF EXISTS trg_silkworm_batches_updated_at ON silkworm_batches")
    op.execute("DROP TABLE IF EXISTS silkworm_batches")
    op.execute("DROP TRIGGER IF EXISTS trg_farms_updated_at ON farms")
    op.execute("DROP TABLE IF EXISTS farms")

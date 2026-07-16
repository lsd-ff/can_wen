"""add service health snapshots

Revision ID: 20260715_0003
Revises: 20260715_0002
Create Date: 2026-07-15
"""

from alembic import op


revision = "20260715_0003"
down_revision = "20260715_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.service_health_snapshots (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            service_key text NOT NULL,
            service_label text NOT NULL,
            status text NOT NULL,
            latency_ms integer,
            status_code integer,
            detail text NOT NULL DEFAULT '',
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            checked_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT service_health_snapshots_status_allowed
                CHECK (status IN ('healthy', 'degraded', 'failed', 'maintenance', 'unknown'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_service_health_snapshots_service_checked ON admin.service_health_snapshots (service_key, checked_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_service_health_snapshots_checked ON admin.service_health_snapshots (checked_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin.service_health_snapshots")

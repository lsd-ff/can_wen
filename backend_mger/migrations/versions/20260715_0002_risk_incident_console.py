"""add persistent risk incident console

Revision ID: 20260715_0002
Revises: 20260713_0001
Create Date: 2026-07-15
"""

from alembic import op


revision = "20260715_0002"
down_revision = "20260713_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.risk_incidents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            fingerprint text NOT NULL UNIQUE,
            risk_type text NOT NULL,
            risk_level text NOT NULL,
            priority text NOT NULL,
            subject text NOT NULL,
            detail text NOT NULL,
            resource_type text NOT NULL,
            resource_id text NOT NULL,
            status text NOT NULL DEFAULT 'open',
            assignee_id uuid,
            due_at timestamptz,
            first_seen_at timestamptz NOT NULL,
            last_detected_at timestamptz NOT NULL,
            last_seen_at timestamptz NOT NULL,
            resolved_at timestamptz,
            suppressed_until timestamptz,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT risk_incidents_level_allowed CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
            CONSTRAINT risk_incidents_priority_allowed CHECK (priority IN ('low', 'medium', 'high', 'critical')),
            CONSTRAINT risk_incidents_status_allowed CHECK (status IN ('open', 'acknowledged', 'in_progress', 'resolved', 'dismissed', 'suppressed'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_risk_incidents_queue ON admin.risk_incidents (status, priority, due_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_risk_incidents_seen ON admin.risk_incidents (last_detected_at DESC)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.risk_incident_activities (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id uuid NOT NULL REFERENCES admin.risk_incidents(id) ON DELETE CASCADE,
            actor_id uuid,
            activity_type text NOT NULL,
            content text NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_risk_incident_activities_timeline ON admin.risk_incident_activities (incident_id, created_at DESC)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.risk_notification_receipts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            incident_id uuid NOT NULL REFERENCES admin.risk_incidents(id) ON DELETE CASCADE,
            admin_account_id uuid NOT NULL REFERENCES admin.admin_accounts(id) ON DELETE CASCADE,
            read_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_risk_notification_receipts_incident_admin UNIQUE (incident_id, admin_account_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_risk_notification_receipts_admin ON admin.risk_notification_receipts (admin_account_id, read_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin.risk_notification_receipts")
    op.execute("DROP TABLE IF EXISTS admin.risk_incident_activities")
    op.execute("DROP TABLE IF EXISTS admin.risk_incidents")

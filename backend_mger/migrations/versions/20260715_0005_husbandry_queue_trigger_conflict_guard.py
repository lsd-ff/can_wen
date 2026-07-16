"""make high risk case trigger insert race safe

Revision ID: 20260715_0005
Revises: 20260715_0004
Create Date: 2026-07-15
"""

from alembic import op


revision = "20260715_0005"
down_revision = "20260715_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION public.enqueue_husbandry_high_risk_review()
        RETURNS trigger AS $$
        BEGIN
          IF NEW.status <> 'closed' AND NEW.severity IN ('high', 'critical') THEN
            IF to_regclass('admin.work_items') IS NOT NULL THEN
              INSERT INTO admin.work_items (item_type, resource_type, resource_id, title, priority, due_at, metadata)
              VALUES (
                'high_risk_case', 'husbandry_case', NEW.id::text,
                '复核高风险养殖病例：' || NEW.title,
                CASE WHEN NEW.severity = 'critical' THEN 'critical' ELSE 'high' END,
                now() + interval '12 hours',
                jsonb_build_object('source', 'husbandry_case_trigger', 'risk_level', NEW.severity)
              )
              ON CONFLICT (resource_type, resource_id) WHERE status IN ('open', 'claimed') DO NOTHING;
            END IF;
          ELSIF to_regclass('admin.work_items') IS NOT NULL THEN
            UPDATE admin.work_items item
               SET status = 'completed', completed_at = COALESCE(item.completed_at, now()),
                   updated_at = now(), version = item.version + 1
             WHERE item.resource_type = 'husbandry_case' AND item.resource_id = NEW.id::text
               AND item.item_type = 'high_risk_case' AND item.status IN ('open', 'claimed');
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    pass

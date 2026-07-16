"""make husbandry review work items and review versions concurrency safe

Revision ID: 20260715_0021
Revises: 20260715_0020
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op


revision = "20260715_0021"
down_revision = "20260715_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Historical data may have been created by the previous lazy queue sync.
    # Keep a claimed item when possible and close the redundant active rows
    # before making the invariant database-enforced.
    op.execute("""
        DO $$
        BEGIN
          IF to_regclass('admin.work_items') IS NOT NULL THEN
            WITH ranked AS (
              SELECT id,
                     row_number() OVER (
                       PARTITION BY resource_type, resource_id
                       ORDER BY CASE status WHEN 'claimed' THEN 0 ELSE 1 END, created_at ASC, id ASC
                     ) AS position
                FROM admin.work_items
               WHERE status IN ('open', 'claimed')
            )
            UPDATE admin.work_items item
               SET status = 'cancelled',
                   completed_at = COALESCE(item.completed_at, now()),
                   updated_at = now(),
                   version = item.version + 1,
                   metadata = COALESCE(item.metadata, '{}'::jsonb) || jsonb_build_object('deduplicated_at', now())
              FROM ranked
             WHERE item.id = ranked.id AND ranked.position > 1;
            EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS uq_work_items_active_resource '
                 || 'ON admin.work_items (resource_type, resource_id) '
                 || 'WHERE status IN (''open'', ''claimed'')';
          END IF;

          IF to_regclass('admin.expert_reviews') IS NOT NULL THEN
            WITH ranked AS (
              SELECT id,
                     row_number() OVER (
                       PARTITION BY husbandry_case_id
                       ORDER BY version ASC, created_at ASC, id ASC
                     ) AS next_version
                FROM admin.expert_reviews
               WHERE husbandry_case_id IS NOT NULL
            )
            UPDATE admin.expert_reviews review
               SET version = ranked.next_version
              FROM ranked
             WHERE review.id = ranked.id AND review.version <> ranked.next_version;
            EXECUTE 'CREATE UNIQUE INDEX IF NOT EXISTS uq_expert_reviews_husbandry_case_version '
                 || 'ON admin.expert_reviews (husbandry_case_id, version) '
                 || 'WHERE husbandry_case_id IS NOT NULL';
          END IF;
        END $$;
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION public.enqueue_husbandry_high_risk_review()
        RETURNS trigger AS $$
        BEGIN
          IF NEW.status <> 'closed' AND NEW.severity IN ('high', 'critical') THEN
            IF to_regclass('admin.work_items') IS NOT NULL THEN
              INSERT INTO admin.work_items (
                item_type, resource_type, resource_id, title, priority, due_at, metadata
              )
              SELECT
                'high_risk_case',
                'husbandry_case',
                NEW.id::text,
                '复核高风险养殖病例：' || NEW.title,
                CASE WHEN NEW.severity = 'critical' THEN 'critical' ELSE 'high' END,
                now() + interval '12 hours',
                jsonb_build_object('source', 'husbandry_case_trigger', 'risk_level', NEW.severity)
              WHERE NOT EXISTS (
                SELECT 1 FROM admin.work_items item
                 WHERE item.resource_type = 'husbandry_case'
                   AND item.resource_id = NEW.id::text
                   AND item.status IN ('open', 'claimed')
              );
            END IF;
          ELSIF to_regclass('admin.work_items') IS NOT NULL THEN
            UPDATE admin.work_items item
               SET status = 'completed',
                   completed_at = COALESCE(item.completed_at, now()),
                   updated_at = now(),
                   version = item.version + 1
             WHERE item.resource_type = 'husbandry_case'
               AND item.resource_id = NEW.id::text
               AND item.item_type = 'high_risk_case'
               AND item.status IN ('open', 'claimed');
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_husbandry_cases_enqueue_high_risk_review ON husbandry_cases")
    op.execute("""
        CREATE TRIGGER trg_husbandry_cases_enqueue_high_risk_review
        AFTER INSERT OR UPDATE OF severity, status ON husbandry_cases
        FOR EACH ROW EXECUTE FUNCTION public.enqueue_husbandry_high_risk_review()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_husbandry_cases_enqueue_high_risk_review ON husbandry_cases")
    op.execute("DROP FUNCTION IF EXISTS public.enqueue_husbandry_high_risk_review()")
    op.execute("DROP INDEX IF EXISTS admin.uq_expert_reviews_husbandry_case_version")
    op.execute("DROP INDEX IF EXISTS admin.uq_work_items_active_resource")

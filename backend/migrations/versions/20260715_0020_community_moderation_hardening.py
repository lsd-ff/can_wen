"""harden community moderation workflow

Revision ID: 20260715_0020
Revises: 20260714_0019
Create Date: 2026-07-15
"""

from __future__ import annotations

from alembic import op


revision = "20260715_0020"
down_revision = "20260714_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Persist both the decision and its optimistic-lock version on the business
    # records. The audit log remains the immutable operation ledger.
    op.execute("ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS review_action text")
    op.execute("ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS resolution_reason text")
    op.execute("ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS reviewed_by_admin_id uuid")
    op.execute("ALTER TABLE community_reports ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE community_profiles ADD COLUMN IF NOT EXISTS verification_version integer NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE community_posts ADD COLUMN IF NOT EXISTS moderation_version integer NOT NULL DEFAULT 1")

    # Preserve a single pending report when historical data contains duplicate
    # submissions, then enforce the same rule at the database boundary.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY reporter_id, post_id
                ORDER BY created_at ASC, id ASC
            ) AS position
              FROM community_reports
             WHERE status = 'pending' AND target_type = 'post' AND post_id IS NOT NULL
        )
        UPDATE community_reports report
           SET status = 'dismissed',
               review_action = 'duplicate_merged',
               resolution_reason = '系统合并了同一用户对同一内容的重复举报。',
               reviewed_at = now(),
               version = report.version + 1
          FROM ranked
         WHERE report.id = ranked.id AND ranked.position > 1
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY reporter_id, comment_id
                ORDER BY created_at ASC, id ASC
            ) AS position
              FROM community_reports
             WHERE status = 'pending' AND target_type = 'comment' AND comment_id IS NOT NULL
        )
        UPDATE community_reports report
           SET status = 'dismissed',
               review_action = 'duplicate_merged',
               resolution_reason = '系统合并了同一用户对同一内容的重复举报。',
               reviewed_at = now(),
               version = report.version + 1
          FROM ranked
         WHERE report.id = ranked.id AND ranked.position > 1
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_community_reports_pending_post_reporter "
        "ON community_reports (reporter_id, post_id) "
        "WHERE status = 'pending' AND target_type = 'post' AND post_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_community_reports_pending_comment_reporter "
        "ON community_reports (reporter_id, comment_id) "
        "WHERE status = 'pending' AND target_type = 'comment' AND comment_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_community_reports_reporter_created "
        "ON community_reports (reporter_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_community_reports_reporter_created")
    op.execute("DROP INDEX IF EXISTS uq_community_reports_pending_comment_reporter")
    op.execute("DROP INDEX IF EXISTS uq_community_reports_pending_post_reporter")
    op.execute("ALTER TABLE community_posts DROP COLUMN IF EXISTS moderation_version")
    op.execute("ALTER TABLE community_profiles DROP COLUMN IF EXISTS verification_version")
    op.execute("ALTER TABLE community_reports DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE community_reports DROP COLUMN IF EXISTS reviewed_by_admin_id")
    op.execute("ALTER TABLE community_reports DROP COLUMN IF EXISTS resolution_reason")
    op.execute("ALTER TABLE community_reports DROP COLUMN IF EXISTS review_action")

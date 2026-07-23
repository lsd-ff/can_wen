"""create community tables

Revision ID: 20260710_0009
Revises: 20260709_0008
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op


revision = "20260710_0009"
down_revision = "20260709_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_posts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            author_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            source_conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
            cover_file_id uuid REFERENCES files(id) ON DELETE SET NULL,
            title text NOT NULL,
            content_markdown text NOT NULL DEFAULT '',
            excerpt text NOT NULL DEFAULT '',
            post_type text NOT NULL DEFAULT 'experience'
                CHECK (post_type IN ('experience', 'case', 'question', 'reference', 'announcement')),
            visibility text NOT NULL DEFAULT 'public'
                CHECK (visibility IN ('public', 'followers')),
            status text NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'published', 'hidden', 'deleted')),
            source_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            like_count bigint NOT NULL DEFAULT 0,
            bookmark_count bigint NOT NULL DEFAULT 0,
            comment_count bigint NOT NULL DEFAULT 0,
            view_count bigint NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            published_at timestamptz,
            deleted_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_posts_feed ON community_posts (status, visibility, published_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_posts_author ON community_posts (author_id, status, updated_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_posts_source_conversation ON community_posts (source_conversation_id)")
    op.execute("DROP TRIGGER IF EXISTS trg_community_posts_updated_at ON community_posts")
    op.execute(
        """
        CREATE TRIGGER trg_community_posts_updated_at
            BEFORE UPDATE ON community_posts
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_post_assets (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            file_id uuid NOT NULL REFERENCES files(id) ON DELETE RESTRICT,
            asset_role text NOT NULL DEFAULT 'attachment' CHECK (asset_role IN ('attachment', 'cover')),
            sort_order smallint NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_community_post_assets_post_file UNIQUE (post_id, file_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_post_assets_post_order ON community_post_assets (post_id, sort_order)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_tags (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL,
            post_count bigint NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_community_tags_name UNIQUE (name)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_tags_usage ON community_tags (post_count DESC)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_post_tags (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            tag_id uuid NOT NULL REFERENCES community_tags(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_community_post_tags_post_tag UNIQUE (post_id, tag_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_post_tags_tag_post ON community_post_tags (tag_id, post_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_post_likes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_community_post_likes_post_user UNIQUE (post_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_post_likes_user_created ON community_post_likes (user_id, created_at DESC)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_post_bookmarks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_community_post_bookmarks_post_user UNIQUE (post_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_post_bookmarks_user_created ON community_post_bookmarks (user_id, created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_comments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            post_id uuid NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
            author_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            parent_comment_id uuid REFERENCES community_comments(id) ON DELETE CASCADE,
            content text NOT NULL,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'hidden', 'deleted')),
            like_count bigint NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_comments_post_created ON community_comments (post_id, created_at ASC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_comments_parent_created ON community_comments (parent_comment_id, created_at ASC)")
    op.execute("DROP TRIGGER IF EXISTS trg_community_comments_updated_at ON community_comments")
    op.execute(
        """
        CREATE TRIGGER trg_community_comments_updated_at
            BEFORE UPDATE ON community_comments
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_comment_likes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            comment_id uuid NOT NULL REFERENCES community_comments(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_community_comment_likes_comment_user UNIQUE (comment_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_comment_likes_user_created ON community_comment_likes (user_id, created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_follows (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            follower_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            followed_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_community_follows_distinct_users CHECK (follower_id <> followed_id),
            CONSTRAINT uq_community_follows_pair UNIQUE (follower_id, followed_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_follows_followed ON community_follows (followed_id, created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_notifications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            post_id uuid REFERENCES community_posts(id) ON DELETE CASCADE,
            comment_id uuid REFERENCES community_comments(id) ON DELETE CASCADE,
            notification_type text NOT NULL CHECK (notification_type IN ('post_like', 'post_comment', 'comment_reply', 'comment_like', 'follow', 'moderation')),
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            read_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_notifications_user_created ON community_notifications (user_id, created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS community_reports (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            reporter_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            post_id uuid REFERENCES community_posts(id) ON DELETE CASCADE,
            comment_id uuid REFERENCES community_comments(id) ON DELETE CASCADE,
            target_type text NOT NULL CHECK (target_type IN ('post', 'comment')),
            reason text NOT NULL,
            detail text,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'reviewed', 'dismissed')),
            created_at timestamptz NOT NULL DEFAULT now(),
            reviewed_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_community_reports_status_created ON community_reports (status, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS community_reports")
    op.execute("DROP TABLE IF EXISTS community_notifications")
    op.execute("DROP TABLE IF EXISTS community_follows")
    op.execute("DROP TABLE IF EXISTS community_comment_likes")
    op.execute("DROP TRIGGER IF EXISTS trg_community_comments_updated_at ON community_comments")
    op.execute("DROP TABLE IF EXISTS community_comments")
    op.execute("DROP TABLE IF EXISTS community_post_bookmarks")
    op.execute("DROP TABLE IF EXISTS community_post_likes")
    op.execute("DROP TABLE IF EXISTS community_post_tags")
    op.execute("DROP TABLE IF EXISTS community_tags")
    op.execute("DROP TABLE IF EXISTS community_post_assets")
    op.execute("DROP TRIGGER IF EXISTS trg_community_posts_updated_at ON community_posts")
    op.execute("DROP TABLE IF EXISTS community_posts")

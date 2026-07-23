"""add RAG and knowledge-graph build pipeline

Revision ID: 20260720_0006
Revises: 20260715_0005
Create Date: 2026-07-20
"""

from alembic import op


revision = "20260720_0006"
down_revision = "20260715_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE admin.system_model_configs DROP CONSTRAINT IF EXISTS system_model_configs_capability_allowed")
    op.execute(
        """
        ALTER TABLE admin.system_model_configs
        ADD CONSTRAINT system_model_configs_capability_allowed
        CHECK (capability IN ('chat', 'vision', 'embedding', 'rerank', 'speech'))
        """
    )

    op.execute("ALTER TABLE admin.knowledge_sources ADD COLUMN IF NOT EXISTS original_filename text")
    op.execute("ALTER TABLE admin.knowledge_sources ADD COLUMN IF NOT EXISTS mime_type text")
    op.execute("ALTER TABLE admin.knowledge_sources ADD COLUMN IF NOT EXISTS storage_uri text")
    op.execute("ALTER TABLE admin.knowledge_sources ADD COLUMN IF NOT EXISTS content_sha256 text")
    op.execute("ALTER TABLE admin.knowledge_sources ADD COLUMN IF NOT EXISTS published_version_id uuid")
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_sources_sha256 ON admin.knowledge_sources (content_sha256)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.knowledge_source_versions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source_id uuid NOT NULL REFERENCES admin.knowledge_sources(id) ON DELETE CASCADE,
            version text NOT NULL,
            status text NOT NULL DEFAULT 'uploaded',
            content_sha256 text NOT NULL,
            original_storage_uri text NOT NULL,
            markdown_storage_uri text,
            parser text NOT NULL DEFAULT 'markdown',
            parser_task_id text,
            parser_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            heading_count integer NOT NULL DEFAULT 0,
            chunk_count integer NOT NULL DEFAULT 0,
            created_by_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT knowledge_source_versions_status_allowed
                CHECK (status IN ('uploaded', 'parsing', 'parsed', 'failed', 'disabled')),
            CONSTRAINT uq_knowledge_source_versions_source_version UNIQUE (source_id, version)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_source_versions_source_created ON admin.knowledge_source_versions (source_id, created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.knowledge_build_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source_version_id uuid NOT NULL REFERENCES admin.knowledge_source_versions(id) ON DELETE CASCADE,
            job_id uuid REFERENCES admin.background_jobs(id) ON DELETE SET NULL,
            targets jsonb NOT NULL DEFAULT '[]'::jsonb,
            status text NOT NULL DEFAULT 'queued',
            current_node text,
            progress integer NOT NULL DEFAULT 0,
            graph_thread_id text NOT NULL,
            config_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
            error_message text,
            requested_by_id uuid,
            started_at timestamptz,
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT knowledge_build_runs_status_allowed
                CHECK (status IN ('queued', 'running', 'awaiting_review', 'publishing', 'succeeded', 'failed', 'cancelled'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_build_runs_status_created ON admin.knowledge_build_runs (status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_build_runs_version_created ON admin.knowledge_build_runs (source_version_id, created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.knowledge_chunks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source_version_id uuid NOT NULL REFERENCES admin.knowledge_source_versions(id) ON DELETE CASCADE,
            build_run_id uuid NOT NULL REFERENCES admin.knowledge_build_runs(id) ON DELETE CASCADE,
            stable_key text NOT NULL,
            ordinal integer NOT NULL,
            start_line integer,
            end_line integer,
            heading_path jsonb NOT NULL DEFAULT '[]'::jsonb,
            heading_level integer,
            content text NOT NULL,
            content_sha256 text NOT NULL,
            token_count integer NOT NULL,
            quality_score double precision NOT NULL DEFAULT 1.0,
            quality_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
            split_strategy text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_knowledge_chunks_run_key UNIQUE (build_run_id, stable_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_version_ordinal ON admin.knowledge_chunks (source_version_id, ordinal)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_run_ordinal ON admin.knowledge_chunks (build_run_id, ordinal)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.knowledge_qa_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            build_run_id uuid NOT NULL REFERENCES admin.knowledge_build_runs(id) ON DELETE CASCADE,
            chunk_id uuid NOT NULL REFERENCES admin.knowledge_chunks(id) ON DELETE CASCADE,
            question text NOT NULL,
            question_sha256 text NOT NULL,
            answer text NOT NULL,
            evidence_text text NOT NULL,
            keywords jsonb NOT NULL DEFAULT '[]'::jsonb,
            knowledge_types jsonb NOT NULL DEFAULT '[]'::jsonb,
            extraction_confidence double precision NOT NULL DEFAULT 0.0,
            rule_score double precision NOT NULL DEFAULT 0.0,
            expert_score double precision,
            expert_assessment jsonb NOT NULL DEFAULT '{}'::jsonb,
            risk_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
            review_status text NOT NULL DEFAULT 'pending',
            review_note text,
            reviewed_by_id uuid,
            reviewed_at timestamptz,
            qdrant_point_id text,
            opensearch_document_id text,
            published_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT knowledge_qa_items_review_status_allowed
                CHECK (review_status IN ('pending', 'needs_review', 'approved', 'rejected', 'published')),
            CONSTRAINT uq_knowledge_qa_items_run_question UNIQUE (build_run_id, question_sha256)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_qa_items_review_created ON admin.knowledge_qa_items (review_status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_qa_items_chunk ON admin.knowledge_qa_items (chunk_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.knowledge_triples (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            build_run_id uuid NOT NULL REFERENCES admin.knowledge_build_runs(id) ON DELETE CASCADE,
            chunk_id uuid NOT NULL REFERENCES admin.knowledge_chunks(id) ON DELETE CASCADE,
            triple_key text NOT NULL,
            subject_name text NOT NULL,
            subject_type text NOT NULL,
            subject_canonical_name text NOT NULL,
            relation text NOT NULL,
            object_name text NOT NULL,
            object_type text NOT NULL,
            object_canonical_name text NOT NULL,
            evidence_text text NOT NULL,
            extraction_confidence double precision NOT NULL DEFAULT 0.0,
            rule_score double precision NOT NULL DEFAULT 0.0,
            expert_score double precision,
            expert_assessment jsonb NOT NULL DEFAULT '{}'::jsonb,
            risk_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
            resolution_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            review_status text NOT NULL DEFAULT 'pending',
            review_note text,
            reviewed_by_id uuid,
            reviewed_at timestamptz,
            neo4j_synced_at timestamptz,
            published_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT knowledge_triples_review_status_allowed
                CHECK (review_status IN ('pending', 'needs_review', 'approved', 'rejected', 'published')),
            CONSTRAINT uq_knowledge_triples_run_key UNIQUE (build_run_id, triple_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_triples_review_created ON admin.knowledge_triples (review_status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_triples_chunk ON admin.knowledge_triples (chunk_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.knowledge_review_items (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            build_run_id uuid NOT NULL REFERENCES admin.knowledge_build_runs(id) ON DELETE CASCADE,
            item_type text NOT NULL,
            resource_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'open',
            priority text NOT NULL DEFAULT 'medium',
            reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
            model_assessment jsonb NOT NULL DEFAULT '{}'::jsonb,
            assignee_id uuid,
            reviewed_by_id uuid,
            decision_note text,
            version integer NOT NULL DEFAULT 1,
            reviewed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT knowledge_review_items_type_allowed CHECK (item_type IN ('chunk', 'qa', 'triple', 'conflict')),
            CONSTRAINT knowledge_review_items_status_allowed CHECK (status IN ('open', 'claimed', 'approved', 'rejected')),
            CONSTRAINT knowledge_review_items_priority_allowed CHECK (priority IN ('low', 'medium', 'high', 'critical'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_review_items_queue ON admin.knowledge_review_items (status, priority, created_at ASC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.knowledge_build_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            build_run_id uuid NOT NULL REFERENCES admin.knowledge_build_runs(id) ON DELETE CASCADE,
            node text NOT NULL,
            level text NOT NULL DEFAULT 'info',
            message text NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT knowledge_build_events_level_allowed CHECK (level IN ('debug', 'info', 'warning', 'error'))
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_build_events_run_created ON admin.knowledge_build_events (build_run_id, created_at)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.knowledge_publications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            build_run_id uuid NOT NULL REFERENCES admin.knowledge_build_runs(id) ON DELETE CASCADE,
            version text NOT NULL,
            status text NOT NULL DEFAULT 'staging',
            qdrant_collection text,
            opensearch_index text,
            neo4j_database text,
            counts jsonb NOT NULL DEFAULT '{}'::jsonb,
            error_message text,
            published_by_id uuid,
            published_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT knowledge_publications_status_allowed CHECK (status IN ('staging', 'published', 'failed', 'rolled_back')),
            CONSTRAINT uq_knowledge_publications_run UNIQUE (build_run_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_publications_status_created ON admin.knowledge_publications (status, created_at DESC)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin.knowledge_sync_outbox (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            build_run_id uuid NOT NULL REFERENCES admin.knowledge_build_runs(id) ON DELETE CASCADE,
            event_key text NOT NULL,
            target text NOT NULL,
            operation text NOT NULL DEFAULT 'upsert',
            aggregate_type text NOT NULL,
            aggregate_id uuid NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            status text NOT NULL DEFAULT 'pending',
            attempts integer NOT NULL DEFAULT 0,
            error_message text,
            processed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT knowledge_sync_outbox_target_allowed CHECK (target IN ('qdrant', 'opensearch', 'neo4j')),
            CONSTRAINT knowledge_sync_outbox_operation_allowed CHECK (operation IN ('upsert', 'delete')),
            CONSTRAINT knowledge_sync_outbox_status_allowed CHECK (status IN ('pending', 'processing', 'succeeded', 'failed')),
            CONSTRAINT uq_knowledge_sync_outbox_event_key UNIQUE (event_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_sync_outbox_pending ON admin.knowledge_sync_outbox (status, target, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin.knowledge_sync_outbox")
    op.execute("DROP TABLE IF EXISTS admin.knowledge_publications")
    op.execute("DROP TABLE IF EXISTS admin.knowledge_build_events")
    op.execute("DROP TABLE IF EXISTS admin.knowledge_review_items")
    op.execute("DROP TABLE IF EXISTS admin.knowledge_triples")
    op.execute("DROP TABLE IF EXISTS admin.knowledge_qa_items")
    op.execute("DROP TABLE IF EXISTS admin.knowledge_chunks")
    op.execute("DROP TABLE IF EXISTS admin.knowledge_build_runs")
    op.execute("DROP TABLE IF EXISTS admin.knowledge_source_versions")
    op.execute("DROP INDEX IF EXISTS admin.idx_knowledge_sources_sha256")
    op.execute("ALTER TABLE admin.knowledge_sources DROP COLUMN IF EXISTS published_version_id")
    op.execute("ALTER TABLE admin.knowledge_sources DROP COLUMN IF EXISTS content_sha256")
    op.execute("ALTER TABLE admin.knowledge_sources DROP COLUMN IF EXISTS storage_uri")
    op.execute("ALTER TABLE admin.knowledge_sources DROP COLUMN IF EXISTS mime_type")
    op.execute("ALTER TABLE admin.knowledge_sources DROP COLUMN IF EXISTS original_filename")
    op.execute("ALTER TABLE admin.system_model_configs DROP CONSTRAINT IF EXISTS system_model_configs_capability_allowed")
    op.execute(
        """
        ALTER TABLE admin.system_model_configs
        ADD CONSTRAINT system_model_configs_capability_allowed
        CHECK (capability IN ('chat', 'vision', 'embedding', 'speech'))
        """
    )

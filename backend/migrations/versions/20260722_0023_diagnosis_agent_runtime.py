"""add diagnosis agent runtime, events and evidence

Revision ID: 20260722_0023
Revises: 20260715_0022
Create Date: 2026-07-22
"""

from alembic import op


revision = "20260722_0023"
down_revision = "20260715_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE agent_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            trigger_message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            assistant_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'waiting_for_user', 'completed', 'degraded', 'failed', 'cancelled')),
            route text CHECK (route IS NULL OR route IN ('rag', 'kg', 'hybrid', 'clarify', 'out_of_domain', 'non_knowledge')),
            risk_level text CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high', 'critical')),
            original_question text NOT NULL,
            rewritten_question text,
            context_pack jsonb NOT NULL DEFAULT '{}'::jsonb,
            knowledge_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
            metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
            error_message text,
            started_at timestamptz,
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE agent_run_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
            sequence bigint NOT NULL,
            agent_key text NOT NULL,
            stage text NOT NULL,
            status text NOT NULL
                CHECK (status IN ('started', 'progress', 'completed', 'waiting', 'degraded', 'failed')),
            public_title text NOT NULL,
            public_summary text,
            public_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            internal_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_agent_run_events_run_sequence UNIQUE (agent_run_id, sequence)
        );

        CREATE TABLE agent_evidence (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_run_id uuid NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
            evidence_key text NOT NULL,
            evidence_type text NOT NULL
                CHECK (evidence_type IN ('rag_document', 'kg_path', 'multimodal_observation', 'user_context')),
            retriever text NOT NULL,
            title text NOT NULL,
            content text NOT NULL,
            source_name text,
            source_uri text,
            source_version text,
            source_page text,
            score numeric(10, 6),
            rank_order bigint,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_agent_evidence_run_key UNIQUE (agent_run_id, evidence_key)
        );

        CREATE INDEX idx_agent_runs_user_created ON agent_runs (user_id, created_at DESC);
        CREATE INDEX idx_agent_runs_conversation_created ON agent_runs (conversation_id, created_at DESC);
        CREATE INDEX idx_agent_runs_trigger_message ON agent_runs (trigger_message_id);
        CREATE INDEX idx_agent_run_events_run_sequence ON agent_run_events (agent_run_id, sequence);
        CREATE INDEX idx_agent_evidence_run_rank ON agent_evidence (agent_run_id, rank_order);

        COMMENT ON TABLE agent_runs IS '问诊智能体运行表：保存四智能体编排状态、知识发布快照和可审计结果。';
        COMMENT ON TABLE agent_run_events IS '问诊智能体公开过程事件：支持前端实时展示、刷新回放和断线续传。';
        COMMENT ON TABLE agent_evidence IS '问诊智能体统一证据表：保存最终采用的 RAG、KG 与现场观察证据。';
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_agent_runs_updated_at
        BEFORE UPDATE ON agent_runs
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_agent_runs_updated_at ON agent_runs")
    op.execute("DROP TABLE IF EXISTS agent_evidence")
    op.execute("DROP TABLE IF EXISTS agent_run_events")
    op.execute("DROP TABLE IF EXISTS agent_runs")

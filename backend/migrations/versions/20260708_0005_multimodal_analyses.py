"""create multimodal analysis table

Revision ID: 20260708_0005
Revises: 20260707_0004
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op


revision = "20260708_0005"
down_revision = "20260707_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnosis_multimodal_analyses (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            file_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            model_id text,
            analysis_json jsonb NOT NULL DEFAULT '{}'::jsonb,
            analysis_text text,
            error_message text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_diagnosis_multimodal_analyses_message_created
            ON diagnosis_multimodal_analyses (message_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_diagnosis_multimodal_analyses_conversation_created
            ON diagnosis_multimodal_analyses (conversation_id, created_at DESC)
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_diagnosis_multimodal_analyses_updated_at ON diagnosis_multimodal_analyses")
    op.execute(
        """
        CREATE TRIGGER trg_diagnosis_multimodal_analyses_updated_at
            BEFORE UPDATE ON diagnosis_multimodal_analyses
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
        """
    )
    op.execute(
        "COMMENT ON TABLE diagnosis_multimodal_analyses IS '多模态解析表：保存多模态模型对消息附件的结构化观察结果。'"
    )
    op.execute("COMMENT ON COLUMN diagnosis_multimodal_analyses.file_ids IS '参与本次解析的文件 ID 列表。'")
    op.execute("COMMENT ON COLUMN diagnosis_multimodal_analyses.analysis_json IS '多模态模型输出的结构化解析结果。'")
    op.execute("COMMENT ON COLUMN diagnosis_multimodal_analyses.analysis_text IS '多模态解析结果的文本版摘要。'")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_diagnosis_multimodal_analyses_updated_at ON diagnosis_multimodal_analyses")
    op.execute("DROP TABLE IF EXISTS diagnosis_multimodal_analyses")

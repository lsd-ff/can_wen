"""create p0 core business tables

Revision ID: 20260706_0003
Revises: 20260702_0002
Create Date: 2026-07-06
"""

from __future__ import annotations

from alembic import op


revision = "20260706_0003"
down_revision = "20260702_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name text NOT NULL,
            description text,
            icon_key text NOT NULL DEFAULT 'folder',
            color text NOT NULL DEFAULT '#11110f',
            status text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'archived', 'deleted')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
            title text NOT NULL DEFAULT '',
            summary text,
            conversation_type text NOT NULL DEFAULT 'diagnosis'
                CHECK (conversation_type IN ('diagnosis', 'video', 'general')),
            status text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'archived', 'deleted')),
            last_message_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_tags (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_conversation_tags_conversation_name UNIQUE (conversation_id, name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            sender_type text NOT NULL CHECK (sender_type IN ('user', 'assistant', 'system')),
            content text NOT NULL DEFAULT '',
            message_type text NOT NULL DEFAULT 'text'
                CHECK (message_type IN ('text', 'image', 'video', 'file', 'diagnosis_result')),
            status text NOT NULL DEFAULT 'sent'
                CHECK (status IN ('sending', 'sent', 'failed')),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
            file_name text NOT NULL,
            file_type text NOT NULL CHECK (file_type IN ('image', 'video', 'document', 'audio', 'other')),
            mime_type text NOT NULL,
            storage_key text NOT NULL,
            storage_url text,
            file_size bigint NOT NULL CHECK (file_size >= 0),
            checksum text,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS message_files (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            file_id uuid NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_message_files_message_file UNIQUE (message_id, file_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnoses (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            trigger_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            disease_name text,
            confidence numeric(5, 4)
                CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            result_summary text,
            suggestion text,
            follow_up_question text,
            model_name text,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS diagnosis_evidence (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            diagnosis_id uuid NOT NULL REFERENCES diagnoses(id) ON DELETE CASCADE,
            evidence_type text NOT NULL
                CHECK (evidence_type IN ('symptom', 'rag_document', 'graph_path', 'rule', 'image')),
            title text NOT NULL,
            content text NOT NULL,
            source text,
            score numeric(8, 4),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    _create_indexes()
    _create_comments()
    _recreate_updated_at_triggers()


def downgrade() -> None:
    for trigger_name, table_name in {
        "trg_diagnoses_updated_at": "diagnoses",
        "trg_messages_updated_at": "messages",
        "trg_conversations_updated_at": "conversations",
        "trg_projects_updated_at": "projects",
    }.items():
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")

    op.execute("DROP TABLE IF EXISTS diagnosis_evidence")
    op.execute("DROP TABLE IF EXISTS diagnoses")
    op.execute("DROP TABLE IF EXISTS message_files")
    op.execute("DROP TABLE IF EXISTS files")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS conversation_tags")
    op.execute("DROP TABLE IF EXISTS conversations")
    op.execute("DROP TABLE IF EXISTS projects")


def _create_indexes() -> None:
    indexes = [
        """
        CREATE INDEX IF NOT EXISTS idx_projects_owner_status_created
            ON projects (owner_id, status, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_user_status_last_message
            ON conversations (user_id, status, last_message_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_conversations_project_status_updated
            ON conversations (project_id, status, updated_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_conversation_tags_conversation
            ON conversation_tags (conversation_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
            ON messages (conversation_id, created_at ASC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_files_user_created
            ON files (user_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_files_project_created
            ON files (project_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_message_files_message
            ON message_files (message_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_message_files_file
            ON message_files (file_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_diagnoses_user_status_created
            ON diagnoses (user_id, status, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_diagnoses_conversation_created
            ON diagnoses (conversation_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_diagnosis_evidence_diagnosis_created
            ON diagnosis_evidence (diagnosis_id, created_at ASC)
        """,
    ]
    for index in indexes:
        op.execute(index)


def _recreate_updated_at_triggers() -> None:
    triggers = {
        "trg_projects_updated_at": "projects",
        "trg_conversations_updated_at": "conversations",
        "trg_messages_updated_at": "messages",
        "trg_diagnoses_updated_at": "diagnoses",
    }
    for trigger_name, table_name in triggers.items():
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
        op.execute(
            f"""
            CREATE TRIGGER {trigger_name}
                BEFORE UPDATE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION set_updated_at()
            """
        )


def _create_comments() -> None:
    comments = [
        "COMMENT ON TABLE projects IS '项目文件夹表：保存用户创建的项目，用于组织项目内问诊对话和文件。'",
        "COMMENT ON TABLE conversations IS '问诊对话表：保存项目内或项目外的对话主体。'",
        "COMMENT ON TABLE conversation_tags IS '对话标签表：保存对话的用户侧标签。'",
        "COMMENT ON TABLE messages IS '对话消息表：保存用户、助手和系统消息。'",
        "COMMENT ON TABLE files IS '上传文件表：保存图片、视频、文档等文件的存储信息。'",
        "COMMENT ON TABLE message_files IS '消息文件关联表：记录一条消息引用了哪些上传文件。'",
        "COMMENT ON TABLE diagnoses IS '诊断任务表：保存一次疾病诊断任务及其结构化结论。'",
        "COMMENT ON TABLE diagnosis_evidence IS '诊断依据表：保存诊断结论对应的症状、文档、图谱、规则或图片依据。'",
        "COMMENT ON COLUMN conversations.project_id IS '所属项目 ID。为空表示普通对话，不在项目文件夹中。'",
        "COMMENT ON COLUMN messages.metadata IS '消息扩展信息，例如模型调用、客户端临时 ID、流式输出状态。'",
        "COMMENT ON COLUMN files.metadata IS '文件扩展信息，例如图片宽高、视频时长、转码状态。'",
        "COMMENT ON COLUMN diagnoses.metadata IS '诊断扩展信息，例如 prompt 版本、工具调用摘要、错误原因。'",
        "COMMENT ON COLUMN diagnosis_evidence.metadata IS '依据扩展信息，例如原始检索结果、图谱路径节点、图片区域。'",
    ]
    for comment in comments:
        op.execute(comment)

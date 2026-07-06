-- Can Wen database schema draft v1.
-- Target database: PostgreSQL 16.
-- Scope: business data model with first-pass auth tables.
-- Current auth scope: phone verification-code login and email verification-code login.
-- WeChat login, OAuth state, and password credentials are intentionally omitted for now.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name text NOT NULL DEFAULT '',
    username text NOT NULL DEFAULT '',
    avatar_url text,
    role text NOT NULL DEFAULT 'farmer'
        CHECK (role IN ('farmer', 'agritech', 'expert', 'admin')),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled', 'deleted')),
    locale text NOT NULL DEFAULT 'zh-CN',
    timezone text NOT NULL DEFAULT 'Asia/Shanghai',
    registered_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE user_identities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider text NOT NULL CHECK (provider IN ('phone', 'email')),
    provider_subject text NOT NULL,
    phone_country_code text,
    phone_number text,
    email citext,
    is_primary boolean NOT NULL DEFAULT false,
    verified_at timestamptz,
    bound_at timestamptz NOT NULL DEFAULT now(),
    unbound_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (provider <> 'phone' OR phone_number IS NOT NULL),
    CHECK (provider <> 'email' OR email IS NOT NULL)
);

CREATE UNIQUE INDEX uq_user_identities_active_subject
    ON user_identities (provider, provider_subject)
    WHERE unbound_at IS NULL;

CREATE UNIQUE INDEX uq_user_identities_primary_per_provider
    ON user_identities (user_id, provider)
    WHERE is_primary AND unbound_at IS NULL;

CREATE TABLE auth_verification_codes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider text NOT NULL CHECK (provider IN ('phone', 'email')),
    target text NOT NULL,
    code_hash text NOT NULL,
    purpose text NOT NULL DEFAULT 'login'
        CHECK (purpose IN ('login', 'bind_identity')),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'used', 'expired', 'blocked')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    request_ip inet,
    request_user_agent text,
    sent_at timestamptz,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auth_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    identity_id uuid REFERENCES user_identities(id) ON DELETE SET NULL,
    refresh_token_hash text NOT NULL,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'revoked', 'expired')),
    device_id text,
    device_name text,
    ip_address inet,
    user_agent text,
    expires_at timestamptz NOT NULL,
    last_used_at timestamptz,
    revoked_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_auth_sessions_refresh_token_hash
    ON auth_sessions (refresh_token_hash);

CREATE TABLE login_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    identity_id uuid REFERENCES user_identities(id) ON DELETE SET NULL,
    session_id uuid REFERENCES auth_sessions(id) ON DELETE SET NULL,
    provider text CHECK (provider IS NULL OR provider IN ('phone', 'email')),
    target text,
    event_type text NOT NULL
        CHECK (
            event_type IN (
                'verification_requested',
                'verification_succeeded',
                'verification_failed',
                'login_success',
                'login_failed',
                'logout',
                'session_refreshed',
                'session_revoked',
                'identity_bound'
            )
        ),
    failure_reason text,
    ip_address inet,
    user_agent text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_profiles (
    user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    real_name text,
    organization text,
    job_title text,
    province text,
    city text,
    county text,
    address text,
    expertise_tags text[] NOT NULL DEFAULT '{}'::text[],
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_consents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    consent_type text NOT NULL
        CHECK (consent_type IN ('terms', 'privacy', 'memory_write', 'case_research')),
    version text NOT NULL,
    status text NOT NULL DEFAULT 'granted'
        CHECK (status IN ('granted', 'revoked')),
    granted_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX uq_user_consents_active
    ON user_consents (user_id, consent_type, version)
    WHERE revoked_at IS NULL;

CREATE TABLE farms (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name text NOT NULL,
    province text,
    city text,
    county text,
    address text,
    latitude numeric(9, 6),
    longitude numeric(9, 6),
    farm_size_mu numeric(10, 2),
    silkworm_room_count integer,
    notes text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz
);

CREATE TABLE silkworm_batches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    farm_id uuid NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    batch_code text,
    variety text,
    instar text,
    start_date date,
    expected_cocooning_date date,
    population_count integer CHECK (population_count IS NULL OR population_count >= 0),
    feeding_method text,
    environment_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'finished', 'archived')),
    notes text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE conversation_folders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name text NOT NULL,
    position integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz
);

CREATE TABLE conversation_threads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    folder_id uuid REFERENCES conversation_folders(id) ON DELETE SET NULL,
    farm_id uuid REFERENCES farms(id) ON DELETE SET NULL,
    batch_id uuid REFERENCES silkworm_batches(id) ON DELETE SET NULL,
    title text NOT NULL,
    thread_type text NOT NULL DEFAULT 'diagnosis'
        CHECK (thread_type IN ('diagnosis', 'video', 'history', 'memory', 'tools', 'settings')),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived', 'deleted')),
    summary text,
    tags text[] NOT NULL DEFAULT '{}'::text[],
    last_message_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    archived_at timestamptz
);

CREATE TABLE messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id uuid NOT NULL REFERENCES conversation_threads(id) ON DELETE CASCADE,
    sender_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    parent_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
    role text NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content_type text NOT NULL DEFAULT 'text'
        CHECK (content_type IN ('text', 'multimodal', 'json')),
    content text NOT NULL DEFAULT '',
    parts jsonb NOT NULL DEFAULT '[]'::jsonb,
    status text NOT NULL DEFAULT 'complete'
        CHECK (status IN ('pending', 'streaming', 'complete', 'failed', 'deleted')),
    model_name text,
    token_usage jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE attachments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id uuid REFERENCES conversation_threads(id) ON DELETE SET NULL,
    message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
    farm_id uuid REFERENCES farms(id) ON DELETE SET NULL,
    batch_id uuid REFERENCES silkworm_batches(id) ON DELETE SET NULL,
    object_key text NOT NULL,
    storage_bucket text NOT NULL DEFAULT 'can-wen-media',
    original_filename text,
    media_type text NOT NULL
        CHECK (media_type IN ('image', 'video', 'audio', 'document', 'other')),
    mime_type text,
    size_bytes bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
    checksum_sha256 text,
    width integer,
    height integer,
    duration_seconds numeric(12, 3),
    processing_status text NOT NULL DEFAULT 'pending'
        CHECK (processing_status IN ('pending', 'processing', 'ready', 'failed', 'deleted')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE media_processing_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    attachment_id uuid NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    job_type text NOT NULL
        CHECK (job_type IN ('image_analysis', 'video_frame_extract', 'asr', 'ocr', 'embedding')),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')),
    progress_pct integer NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
    result jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agent_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    thread_id uuid REFERENCES conversation_threads(id) ON DELETE SET NULL,
    entry_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
    run_type text NOT NULL
        CHECK (run_type IN ('diagnosis', 'memory_write', 'rag_search', 'kg_search', 'video_analysis', 'general_chat')),
    graph_name text,
    model_name text,
    status text NOT NULL DEFAULT 'running'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'canceled')),
    input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tool_invocations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_run_id uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    thread_id uuid REFERENCES conversation_threads(id) ON DELETE SET NULL,
    message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
    tool_name text NOT NULL,
    status text NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'succeeded', 'failed', 'skipped')),
    input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE diagnosis_cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    farm_id uuid REFERENCES farms(id) ON DELETE SET NULL,
    batch_id uuid REFERENCES silkworm_batches(id) ON DELETE SET NULL,
    thread_id uuid REFERENCES conversation_threads(id) ON DELETE SET NULL,
    source_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
    title text NOT NULL,
    symptoms jsonb NOT NULL DEFAULT '{}'::jsonb,
    disease_name text,
    disease_code text,
    conclusion text,
    confidence numeric(5, 4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    severity text CHECK (severity IS NULL OR severity IN ('low', 'medium', 'high', 'critical')),
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'needs_more_info', 'suspected', 'confirmed', 'rejected', 'closed')),
    recommendation text,
    follow_up_required boolean NOT NULL DEFAULT false,
    tags text[] NOT NULL DEFAULT '{}'::text[],
    occurred_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz
);

CREATE TABLE case_observations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL REFERENCES diagnosis_cases(id) ON DELETE CASCADE,
    observation_type text NOT NULL
        CHECK (observation_type IN ('symptom', 'environment', 'management', 'media_signal')),
    label text NOT NULL,
    value_text text,
    value_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    confidence numeric(5, 4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    source_attachment_id uuid REFERENCES attachments(id) ON DELETE SET NULL,
    source_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
    observed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE diagnosis_evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id uuid NOT NULL REFERENCES diagnosis_cases(id) ON DELETE CASCADE,
    evidence_type text NOT NULL
        CHECK (evidence_type IN ('user_input', 'rag_document', 'kg_path', 'bm25_term', 'similar_case', 'model_reasoning')),
    title text NOT NULL,
    source_name text,
    source_uri text,
    snippet text,
    score numeric(10, 4),
    rank_order integer,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
    case_id uuid REFERENCES diagnosis_cases(id) ON DELETE SET NULL,
    rating text NOT NULL CHECK (rating IN ('up', 'down')),
    reason text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (message_id IS NOT NULL OR case_id IS NOT NULL)
);

CREATE TABLE user_memories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    memory_key text,
    scope text NOT NULL DEFAULT 'profile'
        CHECK (scope IN ('profile', 'farm', 'case', 'preference', 'risk', 'other')),
    memory_type text NOT NULL DEFAULT 'fact'
        CHECK (memory_type IN ('fact', 'summary', 'preference', 'rule')),
    content text NOT NULL,
    content_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'rejected', 'deleted')),
    visibility text NOT NULL DEFAULT 'private'
        CHECK (visibility IN ('private', 'expert_visible', 'admin_visible')),
    confidence numeric(5, 4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    source_thread_id uuid REFERENCES conversation_threads(id) ON DELETE SET NULL,
    source_message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
    source_case_id uuid REFERENCES diagnosis_cases(id) ON DELETE SET NULL,
    qdrant_collection text,
    qdrant_point_id text,
    created_by text NOT NULL DEFAULT 'assistant'
        CHECK (created_by IN ('user', 'assistant', 'admin')),
    approved_at timestamptz,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE UNIQUE INDEX uq_user_memories_active_key
    ON user_memories (user_id, memory_key)
    WHERE memory_key IS NOT NULL AND status = 'active' AND deleted_at IS NULL;

CREATE TABLE memory_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id uuid NOT NULL REFERENCES user_memories(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type text NOT NULL
        CHECK (event_type IN ('proposed', 'approved', 'updated', 'merged', 'rejected', 'deleted')),
    old_value jsonb NOT NULL DEFAULT '{}'::jsonb,
    new_value jsonb NOT NULL DEFAULT '{}'::jsonb,
    reason text,
    actor_type text NOT NULL DEFAULT 'assistant'
        CHECK (actor_type IN ('user', 'assistant', 'admin', 'system')),
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_settings (
    user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    model_provider text NOT NULL DEFAULT 'qwen',
    model_name text,
    reasoning_mode text NOT NULL DEFAULT 'evidence_first'
        CHECK (reasoning_mode IN ('evidence_first', 'expert', 'quick')),
    temperature numeric(3, 2) NOT NULL DEFAULT 0.20 CHECK (temperature BETWEEN 0 AND 2),
    enable_kg boolean NOT NULL DEFAULT true,
    enable_rag boolean NOT NULL DEFAULT true,
    enable_long_term_memory boolean NOT NULL DEFAULT true,
    allow_memory_write boolean NOT NULL DEFAULT true,
    ui_preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
    privacy_preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
    notification_preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type text NOT NULL
        CHECK (source_type IN ('document', 'book', 'article', 'kg', 'dataset', 'web')),
    name text NOT NULL,
    version text,
    uri text,
    license text,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived', 'disabled')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE knowledge_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    chunk_key text NOT NULL,
    title text,
    content text NOT NULL,
    language text NOT NULL DEFAULT 'zh-CN',
    token_count integer CHECK (token_count IS NULL OR token_count >= 0),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    qdrant_collection text,
    qdrant_point_id text,
    opensearch_doc_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, chunk_key)
);

CREATE TABLE kg_entities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id text,
    entity_type text NOT NULL
        CHECK (entity_type IN ('disease', 'symptom', 'pathogen', 'drug', 'measure', 'environment', 'silkworm_stage', 'other')),
    name text NOT NULL,
    aliases text[] NOT NULL DEFAULT '{}'::text[],
    description text,
    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    neo4j_node_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (external_id)
);

CREATE TABLE kg_relationships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity_id uuid NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    target_entity_id uuid NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
    relation_type text NOT NULL,
    description text,
    weight numeric(8, 4),
    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
    neo4j_relationship_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_entity_id, target_entity_id, relation_type)
);

CREATE TABLE user_data_exports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    export_format text NOT NULL CHECK (export_format IN ('json', 'csv')),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'expired')),
    object_key text,
    error_message text,
    requested_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    expires_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    action text NOT NULL,
    resource_type text NOT NULL,
    resource_id uuid,
    ip_address inet,
    user_agent text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_identities_user_id ON user_identities (user_id);
CREATE INDEX idx_auth_verification_codes_target
    ON auth_verification_codes (provider, target, purpose, created_at DESC);
CREATE INDEX idx_auth_verification_codes_expires_at
    ON auth_verification_codes (expires_at);
CREATE INDEX idx_auth_sessions_user_id ON auth_sessions (user_id);
CREATE INDEX idx_auth_sessions_expires_at ON auth_sessions (expires_at);
CREATE INDEX idx_login_events_user_created_at ON login_events (user_id, created_at DESC);
CREATE INDEX idx_login_events_target_created_at ON login_events (provider, target, created_at DESC);
CREATE INDEX idx_user_profiles_expertise_tags ON user_profiles USING gin (expertise_tags);
CREATE INDEX idx_user_consents_user_id ON user_consents (user_id);
CREATE INDEX idx_farms_owner_user_id ON farms (owner_user_id);
CREATE INDEX idx_silkworm_batches_farm_id ON silkworm_batches (farm_id);
CREATE INDEX idx_conversation_folders_user_id ON conversation_folders (user_id);
CREATE INDEX idx_conversation_threads_user_id ON conversation_threads (user_id);
CREATE INDEX idx_conversation_threads_folder_id ON conversation_threads (folder_id);
CREATE INDEX idx_conversation_threads_last_message_at ON conversation_threads (last_message_at DESC);
CREATE INDEX idx_conversation_threads_tags ON conversation_threads USING gin (tags);
CREATE INDEX idx_messages_thread_created_at ON messages (thread_id, created_at);
CREATE INDEX idx_messages_sender_user_id ON messages (sender_user_id);
CREATE INDEX idx_messages_parts ON messages USING gin (parts jsonb_path_ops);
CREATE INDEX idx_attachments_owner_user_id ON attachments (owner_user_id);
CREATE INDEX idx_attachments_thread_id ON attachments (thread_id);
CREATE INDEX idx_attachments_message_id ON attachments (message_id);
CREATE INDEX idx_media_processing_jobs_attachment_id ON media_processing_jobs (attachment_id);
CREATE INDEX idx_agent_runs_thread_id ON agent_runs (thread_id);
CREATE INDEX idx_agent_runs_user_id ON agent_runs (user_id);
CREATE INDEX idx_tool_invocations_agent_run_id ON tool_invocations (agent_run_id);
CREATE INDEX idx_diagnosis_cases_user_created_at ON diagnosis_cases (user_id, created_at DESC);
CREATE INDEX idx_diagnosis_cases_thread_id ON diagnosis_cases (thread_id);
CREATE INDEX idx_diagnosis_cases_tags ON diagnosis_cases USING gin (tags);
CREATE INDEX idx_case_observations_case_id ON case_observations (case_id);
CREATE INDEX idx_diagnosis_evidence_case_id ON diagnosis_evidence (case_id);
CREATE INDEX idx_feedback_user_id ON feedback (user_id);
CREATE INDEX idx_user_memories_user_status ON user_memories (user_id, status);
CREATE INDEX idx_user_memories_content_json ON user_memories USING gin (content_json jsonb_path_ops);
CREATE INDEX idx_memory_events_memory_id ON memory_events (memory_id);
CREATE INDEX idx_knowledge_chunks_source_id ON knowledge_chunks (source_id);
CREATE INDEX idx_knowledge_chunks_qdrant_point ON knowledge_chunks (qdrant_collection, qdrant_point_id);
CREATE INDEX idx_kg_entities_name ON kg_entities (name);
CREATE INDEX idx_kg_entities_aliases ON kg_entities USING gin (aliases);
CREATE INDEX idx_kg_relationships_source ON kg_relationships (source_entity_id);
CREATE INDEX idx_kg_relationships_target ON kg_relationships (target_entity_id);
CREATE INDEX idx_user_data_exports_user_id ON user_data_exports (user_id);
CREATE INDEX idx_audit_logs_actor_created_at ON audit_logs (actor_user_id, created_at DESC);
CREATE INDEX idx_audit_logs_resource ON audit_logs (resource_type, resource_id);

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_identities_updated_at
BEFORE UPDATE ON user_identities
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_auth_verification_codes_updated_at
BEFORE UPDATE ON auth_verification_codes
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_auth_sessions_updated_at
BEFORE UPDATE ON auth_sessions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_profiles_updated_at
BEFORE UPDATE ON user_profiles
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_farms_updated_at
BEFORE UPDATE ON farms
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_silkworm_batches_updated_at
BEFORE UPDATE ON silkworm_batches
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_conversation_folders_updated_at
BEFORE UPDATE ON conversation_folders
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_conversation_threads_updated_at
BEFORE UPDATE ON conversation_threads
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_messages_updated_at
BEFORE UPDATE ON messages
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_attachments_updated_at
BEFORE UPDATE ON attachments
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_media_processing_jobs_updated_at
BEFORE UPDATE ON media_processing_jobs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_agent_runs_updated_at
BEFORE UPDATE ON agent_runs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_diagnosis_cases_updated_at
BEFORE UPDATE ON diagnosis_cases
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_memories_updated_at
BEFORE UPDATE ON user_memories
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_user_settings_updated_at
BEFORE UPDATE ON user_settings
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_knowledge_sources_updated_at
BEFORE UPDATE ON knowledge_sources
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_knowledge_chunks_updated_at
BEFORE UPDATE ON knowledge_chunks
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_kg_entities_updated_at
BEFORE UPDATE ON kg_entities
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 登录相关表设计
-- 当前范围：手机号验证码登录、邮箱验证码登录。
-- 暂不包含：微信登录、密码登录、第三方 OAuth 登录。

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

COMMENT ON TABLE users IS '用户主表：保存系统内的用户主体，不直接区分手机号、邮箱等登录方式。';
COMMENT ON COLUMN users.id IS '用户 ID，系统内部用户唯一标识。';
COMMENT ON COLUMN users.display_name IS '用户显示名称，注册初期可为空字符串。';
COMMENT ON COLUMN users.username IS '用户公开用户名，用于个人资料展示。';
COMMENT ON COLUMN users.avatar_url IS '用户头像地址。';
COMMENT ON COLUMN users.role IS '用户角色：farmer 农户、agritech 农技人员、expert 专家、admin 管理员。';
COMMENT ON COLUMN users.status IS '用户状态：active 正常、disabled 禁用、deleted 已删除。';
COMMENT ON COLUMN users.locale IS '用户界面语言，默认 zh-CN。';
COMMENT ON COLUMN users.timezone IS '用户所在时区，默认 Asia/Shanghai。';
COMMENT ON COLUMN users.registered_at IS '用户首次注册时间。';
COMMENT ON COLUMN users.last_seen_at IS '用户最近一次活跃时间。';
COMMENT ON COLUMN users.created_at IS '记录创建时间。';
COMMENT ON COLUMN users.updated_at IS '记录最后更新时间。';
COMMENT ON COLUMN users.deleted_at IS '软删除时间，未删除时为空。';

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

COMMENT ON TABLE user_identities IS '用户登录身份表：保存用户绑定的手机号或邮箱。一个用户可同时绑定手机号和邮箱。';
COMMENT ON COLUMN user_identities.id IS '登录身份 ID。';
COMMENT ON COLUMN user_identities.user_id IS '所属用户 ID。';
COMMENT ON COLUMN user_identities.provider IS '登录身份类型：phone 手机号、email 邮箱。';
COMMENT ON COLUMN user_identities.provider_subject IS '标准化后的登录账号，用于唯一识别。例如手机号建议存 E.164 格式，邮箱建议存小写格式。';
COMMENT ON COLUMN user_identities.phone_country_code IS '手机号国家或地区区号，例如 +86。';
COMMENT ON COLUMN user_identities.phone_number IS '手机号，不含或含区号取决于业务标准，建议与 provider_subject 保持可追溯。';
COMMENT ON COLUMN user_identities.email IS '邮箱地址，citext 类型表示大小写不敏感。';
COMMENT ON COLUMN user_identities.is_primary IS '是否为该登录类型下的主身份。';
COMMENT ON COLUMN user_identities.verified_at IS '该手机号或邮箱完成验证的时间。';
COMMENT ON COLUMN user_identities.bound_at IS '绑定到用户账号的时间。';
COMMENT ON COLUMN user_identities.unbound_at IS '解绑时间。为空表示当前仍有效。';
COMMENT ON COLUMN user_identities.metadata IS '扩展信息，预留给来源渠道、运营标记等非核心字段。';
COMMENT ON COLUMN user_identities.created_at IS '记录创建时间。';
COMMENT ON COLUMN user_identities.updated_at IS '记录最后更新时间。';

CREATE UNIQUE INDEX uq_user_identities_active_subject
    ON user_identities (provider, provider_subject)
    WHERE unbound_at IS NULL;

CREATE UNIQUE INDEX uq_user_identities_primary_per_provider
    ON user_identities (user_id, provider)
    WHERE is_primary AND unbound_at IS NULL;

COMMENT ON INDEX uq_user_identities_active_subject IS '保证同一个有效手机号或邮箱只能绑定到一个用户。';
COMMENT ON INDEX uq_user_identities_primary_per_provider IS '保证同一用户在同一种登录类型下最多只有一个主身份。';

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

COMMENT ON TABLE auth_verification_codes IS '登录验证码表：保存手机号或邮箱验证码的哈希、有效期、尝试次数和使用状态。';
COMMENT ON COLUMN auth_verification_codes.id IS '验证码记录 ID。';
COMMENT ON COLUMN auth_verification_codes.provider IS '验证码发送渠道：phone 手机短信、email 邮箱。';
COMMENT ON COLUMN auth_verification_codes.target IS '验证码接收目标，手机号或邮箱，建议与 user_identities.provider_subject 使用同一标准化规则。';
COMMENT ON COLUMN auth_verification_codes.code_hash IS '验证码哈希值，只存哈希，不存明文验证码。';
COMMENT ON COLUMN auth_verification_codes.purpose IS '验证码用途：login 登录、bind_identity 绑定手机号或邮箱。';
COMMENT ON COLUMN auth_verification_codes.status IS '验证码状态：pending 待验证、used 已使用、expired 已过期、blocked 已锁定。';
COMMENT ON COLUMN auth_verification_codes.attempt_count IS '已验证尝试次数。';
COMMENT ON COLUMN auth_verification_codes.max_attempts IS '最大允许验证次数，超过后可置为 blocked。';
COMMENT ON COLUMN auth_verification_codes.request_ip IS '请求发送验证码时的 IP 地址。';
COMMENT ON COLUMN auth_verification_codes.request_user_agent IS '请求发送验证码时的 User-Agent。';
COMMENT ON COLUMN auth_verification_codes.sent_at IS '验证码实际发送时间。';
COMMENT ON COLUMN auth_verification_codes.expires_at IS '验证码过期时间。';
COMMENT ON COLUMN auth_verification_codes.used_at IS '验证码验证成功并被使用的时间。';
COMMENT ON COLUMN auth_verification_codes.metadata IS '扩展信息，例如短信服务商返回 ID、邮件模板 ID。';
COMMENT ON COLUMN auth_verification_codes.created_at IS '记录创建时间。';
COMMENT ON COLUMN auth_verification_codes.updated_at IS '记录最后更新时间。';

CREATE INDEX idx_auth_verification_codes_target
    ON auth_verification_codes (provider, target, purpose, status, created_at DESC);

CREATE INDEX idx_auth_verification_codes_expires_at
    ON auth_verification_codes (expires_at);

COMMENT ON INDEX idx_auth_verification_codes_target IS '按手机号或邮箱查询最近一次验证码，用于验证和限流。';
COMMENT ON INDEX idx_auth_verification_codes_expires_at IS '按过期时间清理验证码记录。';

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

COMMENT ON TABLE auth_sessions IS '登录会话表：保存登录成功后的 refresh token 哈希、设备信息、过期和退出状态。';
COMMENT ON COLUMN auth_sessions.id IS '会话 ID。';
COMMENT ON COLUMN auth_sessions.user_id IS '会话所属用户 ID。';
COMMENT ON COLUMN auth_sessions.identity_id IS '本次登录使用的手机号或邮箱身份 ID。';
COMMENT ON COLUMN auth_sessions.refresh_token_hash IS '刷新令牌哈希值，只存哈希，不存明文 refresh token。';
COMMENT ON COLUMN auth_sessions.status IS '会话状态：active 有效、revoked 已主动失效、expired 已过期。';
COMMENT ON COLUMN auth_sessions.device_id IS '客户端设备 ID，可由前端生成并持久化。';
COMMENT ON COLUMN auth_sessions.device_name IS '设备名称，例如 iPhone、Chrome on Windows。';
COMMENT ON COLUMN auth_sessions.ip_address IS '登录或最近刷新会话的 IP 地址。';
COMMENT ON COLUMN auth_sessions.user_agent IS '登录或最近刷新会话的 User-Agent。';
COMMENT ON COLUMN auth_sessions.expires_at IS '会话过期时间。';
COMMENT ON COLUMN auth_sessions.last_used_at IS '会话最近一次使用时间。';
COMMENT ON COLUMN auth_sessions.revoked_at IS '会话被主动撤销或退出登录的时间。';
COMMENT ON COLUMN auth_sessions.metadata IS '扩展信息，例如 App 版本、渠道、风控标记。';
COMMENT ON COLUMN auth_sessions.created_at IS '记录创建时间。';
COMMENT ON COLUMN auth_sessions.updated_at IS '记录最后更新时间。';

CREATE UNIQUE INDEX uq_auth_sessions_refresh_token_hash
    ON auth_sessions (refresh_token_hash);

CREATE INDEX idx_auth_sessions_user_id
    ON auth_sessions (user_id, status, created_at DESC);

CREATE INDEX idx_auth_sessions_expires_at
    ON auth_sessions (expires_at);

COMMENT ON INDEX uq_auth_sessions_refresh_token_hash IS '保证 refresh token 哈希唯一，避免同一令牌对应多个会话。';
COMMENT ON INDEX idx_auth_sessions_user_id IS '按用户查询有效会话和登录设备列表。';
COMMENT ON INDEX idx_auth_sessions_expires_at IS '按过期时间清理会话。';

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

COMMENT ON TABLE login_events IS '登录事件表：记录验证码发送、验证成功或失败、登录成功或失败、退出登录、刷新会话等审计事件。';
COMMENT ON COLUMN login_events.id IS '登录事件 ID。';
COMMENT ON COLUMN login_events.user_id IS '事件关联用户 ID。登录失败或未识别用户时可为空。';
COMMENT ON COLUMN login_events.identity_id IS '事件关联的手机号或邮箱身份 ID。未匹配到身份时可为空。';
COMMENT ON COLUMN login_events.session_id IS '事件关联会话 ID。只有登录成功、刷新、退出等会话事件通常会有值。';
COMMENT ON COLUMN login_events.provider IS '事件涉及的登录渠道：phone 手机号、email 邮箱。';
COMMENT ON COLUMN login_events.target IS '事件涉及的手机号或邮箱。';
COMMENT ON COLUMN login_events.event_type IS '事件类型，例如 verification_requested、login_success、logout。';
COMMENT ON COLUMN login_events.failure_reason IS '失败原因，例如 code_expired、code_invalid、too_many_attempts。';
COMMENT ON COLUMN login_events.ip_address IS '触发事件的 IP 地址。';
COMMENT ON COLUMN login_events.user_agent IS '触发事件的 User-Agent。';
COMMENT ON COLUMN login_events.metadata IS '扩展信息，用于记录风控结果、服务商返回值等。';
COMMENT ON COLUMN login_events.created_at IS '事件发生时间。';

CREATE INDEX idx_login_events_user_created_at
    ON login_events (user_id, created_at DESC);

CREATE INDEX idx_login_events_target_created_at
    ON login_events (provider, target, created_at DESC);

COMMENT ON INDEX idx_login_events_user_created_at IS '按用户倒序查询登录事件。';
COMMENT ON INDEX idx_login_events_target_created_at IS '按手机号或邮箱倒序查询登录事件，用于审计和风控排查。';

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

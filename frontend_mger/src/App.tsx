import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
  Activity,
  ArrowUpRight,
  AlertTriangle,
  Archive,
  BarChart3,
  Bell,
  BookOpenCheck,
  Bot,
  CheckCircle2,
  Clock3,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Database,
  Download,
  FileArchive,
  FileText,
  ExternalLink,
  Flag,
  FolderTree,
  Gauge,
  HeartPulse,
  KeyRound,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  Menu,
  MessageSquare,
  MessageCircleMore,
  MoreHorizontal,
  PackageSearch,
  PanelLeftClose,
  PanelLeftOpen,
  PlayCircle,
  Plus,
  RefreshCcw,
  RotateCcw,
  Search,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Siren,
  SlidersHorizontal,
  Sparkles,
  UserCog,
  UserCheck,
  UserPlus,
  UserRoundCheck,
  Users,
  Wrench,
  X,
  type LucideIcon,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_ADMIN_API_BASE_URL ?? 'http://127.0.0.1:8020/api/admin/v1';
const SESSION_KEY = 'canw-admin-session-v1';
const SESSION_REFRESHED_EVENT = 'canw-admin-session-refreshed';
const SESSION_EXPIRED_EVENT = 'canw-admin-session-expired';
const ACCESS_TOKEN_REFRESH_LEEWAY_MS = 60_000;

type Row = Record<string, unknown>;
type PageKey =
  | 'dashboard' | 'queue' | 'users' | 'community' | 'diagnosis' | 'husbandry'
  | 'knowledge' | 'models' | 'operations' | 'system';

type AdminIdentity = {
  id: string;
  email: string;
  display_name: string;
  roles: string[];
  permissions: string[];
  mfa_enrolled: boolean;
};

type AdminSession = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  expires_at: number;
  admin: AdminIdentity;
};

type ListResponse = { items: Row[]; total?: number; page?: number; page_size?: number };
type LoadState<T> = { data: T | null; loading: boolean; error: string };

class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function withSessionExpiry(session: Omit<AdminSession, 'expires_at'> & Partial<Pick<AdminSession, 'expires_at'>>): AdminSession {
  return { ...session, expires_at: session.expires_at ?? Date.now() + session.expires_in * 1000 };
}

function readSession(): AdminSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return withSessionExpiry(JSON.parse(raw) as AdminSession);
  } catch {
    return null;
  }
}

function saveSession(session: AdminSession | null) {
  if (session) window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else window.localStorage.removeItem(SESSION_KEY);
}

function responseMessage(payload: unknown): string {
  return typeof payload === 'object' && payload !== null && 'detail' in payload ? String(payload.detail) : '请求失败，请稍后重试';
}

function notifySessionRefreshed(session: AdminSession) {
  saveSession(session);
  window.dispatchEvent(new CustomEvent<AdminSession>(SESSION_REFRESHED_EVENT, { detail: session }));
}

function expireSession() {
  saveSession(null);
  window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
}

let refreshInFlight: Promise<AdminSession> | null = null;

async function refreshAccessToken(session: AdminSession): Promise<AdminSession> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ refresh_token: session.refresh_token }),
      });
      const payload: unknown = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) expireSession();
        throw new ApiError(response.status, responseMessage(payload));
      }
      const refreshed = withSessionExpiry(payload as Omit<AdminSession, 'expires_at'>);
      notifySessionRefreshed(refreshed);
      return refreshed;
    })().finally(() => { refreshInFlight = null; });
  }
  const refreshed = await refreshInFlight;
  Object.assign(session, refreshed);
  return refreshed;
}

async function api<T>(path: string, session: AdminSession | null, options: RequestInit = {}): Promise<T> {
  const request = (accessToken: string | null) => {
    const headers = new Headers(options.headers);
    if (options.body && !headers.has('content-type')) headers.set('content-type', 'application/json');
    if (accessToken) headers.set('authorization', `Bearer ${accessToken}`);
    return fetch(`${API_BASE}${path}`, { ...options, headers });
  };
  let response = await request(session?.access_token ?? null);
  if (response.status === 401 && session && path !== '/auth/refresh') {
    const refreshed = await refreshAccessToken(session);
    response = await request(refreshed.access_token);
  }
  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(response.status, responseMessage(payload));
  }
  return payload as T;
}

async function downloadFile(path: string, session: AdminSession): Promise<void> {
  const request = (accessToken: string) => fetch(`${API_BASE}${path}`, {
    headers: { authorization: `Bearer ${accessToken}` },
  });
  let response = await request(session.access_token);
  if (response.status === 401) {
    const refreshed = await refreshAccessToken(session);
    response = await request(refreshed.access_token);
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => ({}));
    throw new ApiError(response.status, responseMessage(payload));
  }
  const disposition = response.headers.get('content-disposition') ?? '';
  const filename = disposition.match(/filename=([^;]+)/i)?.[1]?.replaceAll('"', '') || 'canw-users.csv';
  const blobUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 0);
}

function useResource<T>(session: AdminSession | null, path: string, enabled = true): LoadState<T> & { reload: () => void } {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<LoadState<T>>({ data: null, loading: enabled, error: '' });
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    let cancelled = false;
    if (!enabled) {
      setState({ data: null, loading: false, error: '' });
      return () => { cancelled = true; };
    }
    setState((current) => ({ ...current, loading: true, error: '' }));
    void api<T>(path, session)
      .then((data) => { if (!cancelled) setState({ data, loading: false, error: '' }); })
      .catch((error: unknown) => {
        if (!cancelled) setState({ data: null, loading: false, error: error instanceof Error ? error.message : '加载失败' });
      });
    return () => { cancelled = true; };
  }, [enabled, path, revision, session?.access_token]);
  return { ...state, reload };
}

function text(value: unknown, fallback = '—'): string {
  if (value === null || value === undefined || value === '') return fallback;
  return String(value);
}

function number(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function dateTime(value: unknown): string {
  if (!value) return '—';
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.valueOf()) ? String(value) : parsed.toLocaleString('zh-CN', { hour12: false });
}

function shortDate(value: unknown): string {
  if (!value) return '—';
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.valueOf()) ? String(value) : parsed.toLocaleDateString('zh-CN');
}

function asItems(data: ListResponse | null): Row[] {
  return data?.items ?? [];
}

function hasPermission(session: AdminSession, permission: string): boolean {
  return session.admin.permissions.includes(permission);
}

type ReasonDialogOptions = {
  confirmLabel?: string;
  description?: string;
  tone?: 'default' | 'danger';
};
type ReasonDialogRequest = ReasonDialogOptions & { label: string; resolve: (value: string | null) => void };
let requestReasonDialog: ((label: string, options?: ReasonDialogOptions) => Promise<string | null>) | null = null;

function askReasonInDialog(label: string, options?: ReasonDialogOptions): Promise<string | null> {
  return requestReasonDialog ? requestReasonDialog(label, options) : Promise.resolve(null);
}

function App() {
  const [session, setSession] = useState<AdminSession | null>(readSession);
  const [toast, setToast] = useState('');
  const [reasonDialog, setReasonDialog] = useState<ReasonDialogRequest | null>(null);
  const openReasonDialog = useCallback((label: string, options: ReasonDialogOptions = {}) => new Promise<string | null>((resolve) => setReasonDialog({ label, ...options, resolve })), []);
  const resolveReasonDialog = useCallback((value: string | null) => {
    setReasonDialog((current) => { current?.resolve(value); return null; });
  }, []);
  const completeLogin = useCallback((next: AdminSession) => {
    const sessionWithExpiry = withSessionExpiry(next);
    saveSession(sessionWithExpiry);
    setSession(sessionWithExpiry);
  }, []);
  const logout = useCallback(async () => {
    if (session) await api('/auth/logout', session, { method: 'POST', body: JSON.stringify({ refresh_token: session.refresh_token }) }).catch(() => undefined);
    saveSession(null);
    setSession(null);
  }, [session]);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(''), 3600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    const handleRefreshed = (event: Event) => setSession((event as CustomEvent<AdminSession>).detail);
    const handleExpired = () => setSession(null);
    window.addEventListener(SESSION_REFRESHED_EVENT, handleRefreshed);
    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpired);
    return () => {
      window.removeEventListener(SESSION_REFRESHED_EVENT, handleRefreshed);
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpired);
    };
  }, []);

  useEffect(() => {
    if (!session) return undefined;
    const delay = Math.max(1_000, session.expires_at - Date.now() - ACCESS_TOKEN_REFRESH_LEEWAY_MS);
    const timer = window.setTimeout(() => { void refreshAccessToken(session).catch(() => undefined); }, delay);
    return () => window.clearTimeout(timer);
  }, [session?.access_token, session?.expires_at]);

  useEffect(() => {
    requestReasonDialog = openReasonDialog;
    return () => { requestReasonDialog = null; };
  }, [openReasonDialog]);

  if (!session) return <AuthPage onComplete={completeLogin} />;
  return <><AdminShell session={session} onLogout={logout} onToast={setToast} toast={toast} />{reasonDialog && <ReasonDialog request={reasonDialog} onResolve={resolveReasonDialog} />}</>;
}

function AuthPage({ onComplete }: { onComplete: (session: AdminSession) => void }) {
  const [mode, setMode] = useState<'login' | 'invite'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [inviteToken, setInviteToken] = useState('');
  const [mfaTicket, setMfaTicket] = useState('');
  const [mfaSetupRequired, setMfaSetupRequired] = useState(false);
  const [mfaSecret, setMfaSecret] = useState('');
  const [mfaUri, setMfaUri] = useState('');
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const showMfa = async (ticket: string, setupRequired: boolean) => {
    setMfaTicket(ticket);
    setMfaSetupRequired(setupRequired);
    if (setupRequired) {
      const setup = await api<{ secret: string; otpauth_uri: string }>('/auth/mfa/setup', null, { method: 'POST', body: JSON.stringify({ mfa_ticket: ticket }) });
      setMfaSecret(setup.secret);
      setMfaUri(setup.otpauth_uri);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true); setError('');
    try {
      if (mode === 'invite') {
        const result = await api<{ mfa_ticket: string; mfa_setup_required: boolean }>('/auth/invitations/accept', null, { method: 'POST', body: JSON.stringify({ token: inviteToken, password }) });
        await showMfa(result.mfa_ticket, result.mfa_setup_required);
      } else {
        const result = await api<AdminSession | { mfa_ticket: string; mfa_setup_required: boolean }>('/auth/login', null, { method: 'POST', body: JSON.stringify({ email, password, device_name: navigator.userAgent.slice(0, 120) }) });
        if ('access_token' in result) onComplete(result);
        else await showMfa(result.mfa_ticket, result.mfa_setup_required);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '登录失败');
    } finally { setLoading(false); }
  };

  const verifyMfa = async (event: FormEvent) => {
    event.preventDefault(); setLoading(true); setError('');
    try {
      const result = await api<AdminSession>('/auth/mfa/verify', null, { method: 'POST', body: JSON.stringify({ mfa_ticket: mfaTicket, code, device_name: navigator.userAgent.slice(0, 120) }) });
      onComplete(result);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : '验证失败'); }
    finally { setLoading(false); }
  };

  if (mfaTicket) return <main className="auth-page"><section className="auth-card mfa-card"><div className="auth-brand"><ShieldCheck /><span>CanW 管理工作台</span></div><h1>{mfaSetupRequired ? '绑定验证器' : '验证身份'}</h1><p>{mfaSetupRequired ? '使用身份验证器扫描密钥后输入 6 位代码。此设备将只在验证成功后进入后台。' : '输入身份验证器中的 6 位动态代码。'}</p>{mfaSetupRequired && <div className="totp-secret"><code>{mfaSecret}</code><small>手动密钥；二维码链接已生成，可在支持的验证器中导入。</small><a href={mfaUri}>打开验证器</a></div>}<form onSubmit={verifyMfa}><label>动态代码<input autoFocus inputMode="numeric" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} placeholder="000000" /></label>{error && <p className="form-error">{error}</p>}<button className="primary-button" disabled={loading || code.length !== 6}>{loading ? '正在验证' : '验证并进入工作台'}</button></form><button className="text-button" onClick={() => { setMfaTicket(''); setCode(''); setError(''); }}>返回登录</button></section></main>;

  return <main className="auth-page"><section className="auth-card"><div className="auth-brand"><ShieldCheck /><span>CanW 管理工作台</span></div><span className="eyebrow">SILKWORM OPERATIONS CONSOLE</span><h1>{mode === 'login' ? '进入管理工作台' : '接受管理员邀请'}</h1><p>{mode === 'login' ? '仅限受邀的 CanW 平台运营、审核和专家人员使用。' : '设置管理员密码后，还需要绑定身份验证器。'}</p><form onSubmit={submit}>{mode === 'login' ? <label>管理员邮箱<input autoFocus type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="admin@example.com" required /></label> : <label>邀请令牌<input autoFocus value={inviteToken} onChange={(event) => setInviteToken(event.target.value)} placeholder="粘贴邀请令牌" required /></label>}<label>密码<input type="password" minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="至少 12 位" required /></label>{error && <p className="form-error">{error}</p>}<button className="primary-button" disabled={loading}>{loading ? '正在处理' : mode === 'login' ? '继续验证' : '接受邀请并继续'}</button></form><button className="text-button" onClick={() => { setMode((current) => current === 'login' ? 'invite' : 'login'); setError(''); }}>{mode === 'login' ? '使用邀请令牌激活账号' : '返回管理员登录'}</button></section></main>;
}

type NavItem = { key: PageKey; label: string; icon: LucideIcon; permission?: string };
const navigation: Array<{ label: string; items: NavItem[] }> = [
  { label: '工作台', items: [{ key: 'dashboard', label: '运营总览', icon: LayoutDashboard, permission: 'dashboard.read' }, { key: 'queue', label: '待办中心', icon: ClipboardCheck, permission: 'work_items.read' }] },
  { label: '业务管理', items: [{ key: 'users', label: '用户管理', icon: Users, permission: 'users.read' }, { key: 'community', label: '社区审核', icon: MessageSquare, permission: 'community.read' }, { key: 'diagnosis', label: '智能问诊', icon: Bot, permission: 'diagnosis.read' }, { key: 'husbandry', label: '养殖病例', icon: HeartPulse, permission: 'husbandry.read' }] },
  { label: '知识与模型', items: [{ key: 'knowledge', label: '知识中心', icon: BookOpenCheck, permission: 'knowledge.read' }, { key: 'models', label: '模型与任务', icon: Sparkles, permission: 'models.read' }] },
  { label: '运营与安全', items: [{ key: 'operations', label: '数据与安全', icon: ShieldAlert, permission: 'analytics.read' }] },
  { label: '系统管理', items: [{ key: 'system', label: '权限与审计', icon: Settings, permission: 'admins.read' }] },
];

function hashQuery(name: string): string {
  const query = window.location.hash.split('?')[1] ?? '';
  return new URLSearchParams(query).get(name) ?? '';
}

function initialPage(session: AdminSession): PageKey {
  const hash = window.location.hash.replace('#/', '').split('?')[0] as PageKey;
  const available = navigation.flatMap((section) => section.items).find((item) => item.key === hash && (!item.permission || hasPermission(session, item.permission)));
  return available?.key ?? 'dashboard';
}

function AdminShell({ session, onLogout, onToast, toast }: { session: AdminSession; onLogout: () => void; onToast: (message: string) => void; toast: string }) {
  const [page, setPage] = useState<PageKey>(() => initialPage(session));
  const [collapsed, setCollapsed] = useState(false);
  const [search, setSearch] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const searchResource = useResource<{ items: Row[] }>(session, `/search?q=${encodeURIComponent(search)}`, page !== 'dashboard' && search.trim().length >= 2);
  const notificationResource = useResource<Row>(session, '/dashboard', hasPermission(session, 'dashboard.read'));
  const notifications = Array.isArray(notificationResource.data?.alerts) ? notificationResource.data.alerts as Row[] : [];
  const meta = useMemo(() => navigation.flatMap((section) => section.items).find((item) => item.key === page), [page]);
  const navigate = (next: PageKey) => { window.location.hash = `/${next}`; setPage(next); setSearchOpen(false); };

  useEffect(() => {
    const syncPage = () => setPage(initialPage(session));
    window.addEventListener('hashchange', syncPage);
    return () => window.removeEventListener('hashchange', syncPage);
  }, [session]);

  useEffect(() => {
    const timer = window.setInterval(notificationResource.reload, 60_000);
    return () => window.clearInterval(timer);
  }, [notificationResource.reload]);

  return (
    <div className={`admin-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-copy"><strong>CanW</strong><span>管理工作台</span></div>
          <button aria-label="折叠导航" onClick={() => setCollapsed((value) => !value)}>
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
        </div>
        <nav>
          {navigation.map((section) => {
            const items = section.items.filter((item) => !item.permission || hasPermission(session, item.permission));
            if (!items.length) return null;
            return <section className="nav-group" key={section.label}>
              <h2>{section.label}</h2>
              {items.map((item) => <button className={page === item.key ? 'active' : ''} onClick={() => navigate(item.key)} key={item.key} title={item.label}>
                <item.icon size={18} /><span className="nav-label">{item.label}</span>
              </button>)}
            </section>;
          })}
        </nav>
        <div className="sidebar-footer"><span className="status-dot" /><small>已启用审计保护</small></div>
      </aside>
      <main className="admin-main">
        <header className="topbar">
          <div className="mobile-menu"><button onClick={() => setCollapsed((value) => !value)}><Menu size={20} /></button></div>
          <div><span className="topbar-kicker">CANW / {meta?.label ?? '工作台'}</span><h1>{meta?.label ?? '管理工作台'}</h1></div>
          <div className="topbar-actions">
            {page !== 'dashboard' && <div className="global-search"><Search size={16} /><input value={search} onFocus={() => setSearchOpen(true)} onChange={(event) => setSearch(event.target.value)} placeholder="搜索用户、问诊、帖子…" />
              {searchOpen && search.trim().length >= 2 && <div className="search-results">{searchResource.loading && <span>正在搜索…</span>}{searchResource.error && <span>{searchResource.error}</span>}{(searchResource.data?.items ?? []).map((item) => <button key={`${text(item.type)}-${text(item.id)}`} onClick={() => { const target = text(item.type); navigate(target === 'user' ? 'users' : target === 'conversation' ? 'diagnosis' : 'community'); }}><small>{text(item.type)}</small><strong>{text(item.title)}</strong><span>{text(item.status)}</span></button>)}</div>}
            </div>}
            {hasPermission(session, 'dashboard.read') && <div className="notification-center"><button className="notification-trigger" aria-label={`当前运营预警 ${notifications.length} 项`} onClick={() => setNotificationsOpen((value) => !value)}><Bell size={17} />{notifications.length > 0 && <b>{notifications.length > 9 ? '9+' : notifications.length}</b>}</button>{notificationsOpen && <div className="notification-popover"><header><strong>当前运营预警</strong><button onClick={notificationResource.reload}><RefreshCcw size={14} /></button></header>{notificationResource.loading && <p>正在更新预警…</p>}{!notificationResource.loading && notifications.length === 0 && <p>当前没有需要处理的运营预警。</p>}{notifications.map((alert) => <button className="notification-item" key={`${text(alert.title)}-${text(alert.level)}`} onClick={() => { window.location.hash = text(alert.target); setNotificationsOpen(false); }}><Status value={text(alert.level)} /><span><strong>{text(alert.title)}</strong><small>{text(alert.detail)}</small></span><ChevronRight size={14} /></button>)}</div>}</div>}
            <div className="admin-profile"><div><strong>{session.admin.display_name}</strong><small>{session.admin.roles[0] ?? '管理员'}</small></div><button title="退出登录" onClick={onLogout}><LogOut size={17} /></button></div>
          </div>
        </header>
        <section className="page-content"><PageRouter page={page} session={session} onToast={onToast} /></section>
      </main>
      {toast && <div className="toast"><CheckCircle2 size={16} />{toast}<button onClick={() => onToast('')}><X size={15} /></button></div>}
    </div>
  );
}

function PageRouter({ page, session, onToast }: { page: PageKey; session: AdminSession; onToast: (message: string) => void }) {
  switch (page) {
    case 'dashboard': return <DashboardPage session={session} />;
    case 'queue': return <QueuePage session={session} onToast={onToast} />;
    case 'users': return <UsersPage session={session} onToast={onToast} />;
    case 'community': return <CommunityPage session={session} onToast={onToast} />;
    case 'diagnosis': return <DiagnosisPage session={session} onToast={onToast} />;
    case 'husbandry': return <HusbandryPage session={session} onToast={onToast} />;
    case 'knowledge': return <KnowledgePage session={session} onToast={onToast} />;
    case 'models': return <ModelsPage session={session} onToast={onToast} />;
    case 'operations': return <OperationsPage session={session} onToast={onToast} />;
    case 'system': return <SystemPage session={session} onToast={onToast} />;
  }
}

function LoadingState({ loading, error, children }: { loading: boolean; error: string; children: ReactNode }) {
  if (loading) return <div className="loading-state"><RefreshCcw size={18} />正在整理数据…</div>;
  if (error) return <div className="error-state"><AlertTriangle size={19} /><div><strong>暂时无法加载</strong><span>{error}</span></div></div>;
  return <>{children}</>;
}

function PageHeader({ eyebrow, title, description, actions }: { eyebrow: string; title: string; description: string; actions?: ReactNode }) {
  return <header className="page-header"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{description}</p></div>{actions && <div className="page-header-actions">{actions}</div>}</header>;
}

function DashboardPage({ session }: { session: AdminSession }) {
  const resource = useResource<Row>(session, '/dashboard');
  const metrics = (resource.data?.metrics ?? {}) as Row;
  const taskSummary = (resource.data?.task_summary ?? {}) as Row;
  const lifecycle = Array.isArray(resource.data?.lifecycle) ? resource.data.lifecycle as Row[] : [];
  const workItems = Array.isArray(resource.data?.work_items) ? resource.data.work_items as Row[] : [];
  const alerts = Array.isArray(resource.data?.alerts) ? resource.data.alerts as Row[] : [];
  const trend = Array.isArray(resource.data?.trend) ? resource.data.trend as Row[] : [];
  const comparison = (resource.data?.period_comparison ?? {}) as Row;
  const trendFields: Array<{ key: 'users' | 'conversations' | 'cases' | 'posts'; label: string; permission: string }> = [
    { key: 'users', label: '用户', permission: 'users.read' }, { key: 'conversations', label: '问诊', permission: 'diagnosis.read' },
    { key: 'cases', label: '病例', permission: 'husbandry.read' }, { key: 'posts', label: '帖子', permission: 'community.read' },
  ].filter((item) => hasPermission(session, item.permission));
  const trendMax = Math.max(1, ...trend.flatMap((item) => trendFields.map((field) => number(item[field.key]))));
  const navigate = (target: string) => { window.location.hash = target; };
  const cards: Array<{ label: string; value: number; icon: LucideIcon; target: string; note: string; permission: string }> = [
    { label: '今日新增用户', value: number(metrics.new_users_today), icon: Users, target: '/users?created_since=today', note: '查看今日注册用户', permission: 'users.read' },
    { label: '今日问诊', value: number(metrics.conversations_today), icon: Bot, target: '/diagnosis?created_since=today&review_status=all', note: '查看今日问诊队列', permission: 'diagnosis.read' },
    { label: '待处理举报', value: number(metrics.pending_reports), icon: Flag, target: '/community?tab=reports', note: '进入举报审核', permission: 'community.read' },
    { label: '高风险病例', value: number(metrics.high_risk_cases), icon: HeartPulse, target: '/husbandry?high_risk=true', note: '进入病例复核', permission: 'husbandry.read' },
    { label: '多模态失败', value: number(metrics.failed_multimodal_jobs), icon: AlertTriangle, target: '/diagnosis?tab=jobs&job_status=failed', note: '查看失败任务', permission: 'diagnosis.read' },
    { label: '开放待办', value: number(metrics.open_work_items), icon: ClipboardCheck, target: '/queue?status=open', note: '前往待办中心', permission: 'work_items.read' },
  ];
  const userChange = number(comparison.users_current) - number(comparison.users_previous);
  const canWorkItems = hasPermission(session, 'work_items.read');
  const factRows = [
    { label: '7 日活跃用户', value: number(metrics.active_users_7d), permission: 'users.read' },
    { label: '待认证专业资料', value: number(metrics.pending_verifications), permission: 'community.read' },
    { label: '今日社区帖子', value: number(metrics.community_posts_today), permission: 'community.read' },
    { label: '高风险养殖病例', value: number(metrics.high_risk_cases), permission: 'husbandry.read' },
  ].filter((item) => hasPermission(session, item.permission));

  return <><PageHeader eyebrow="系统巡检" title="平台运营总览" description="从这里识别风险、领取任务并进入对应业务处置。" actions={<><small className="dashboard-updated">业务数据聚合于 {dateTime(resource.data?.generated_at)}</small><button className="quiet-button" onClick={resource.reload}><RefreshCcw size={15} />刷新数据</button></>} /><LoadingState loading={resource.loading} error={resource.error}>
    <section className="metric-grid">{cards.filter((card) => hasPermission(session, card.permission)).map(({ label, value, icon: Icon, target, note }) => <button className="metric-card metric-link" key={label} onClick={() => navigate(target)} aria-label={`${note}，当前 ${value}`}><Icon size={18} /><span>{label}</span><strong>{value.toLocaleString('zh-CN')}</strong><small>{note}<ChevronRight size={13} /></small></button>)}</section>
    <section className="dashboard-command-grid">
      {canWorkItems && <article className="dashboard-command my-work-command"><div><span className="eyebrow">我的工作</span><h3>我处理中 <b>{number(taskSummary.my_claimed)}</b> 项</h3><p>只显示已由你领取、仍需在业务页面处理的待办。</p></div><button onClick={() => navigate('/queue?status=claimed&assignee=me')}>查看我的待办<ChevronRight size={15} /></button></article>}
      {canWorkItems && <article className="dashboard-command sla-command"><div><span className="eyebrow">SLA 时效</span><h3>处理时限</h3></div><div className="sla-numbers"><button onClick={() => navigate('/queue?status=active')}><b>{number(taskSummary.overdue)}</b><span>已超时</span></button><button onClick={() => navigate('/queue?status=active')}><b>{number(taskSummary.due_soon)}</b><span>4 小时内到期</span></button><button onClick={() => navigate('/queue?status=open')}><b>{number(taskSummary.unclaimed)}</b><span>待领取</span></button></div></article>}
      <article className="dashboard-command alert-command"><div><span className="eyebrow">当前预警</span><h3>{alerts.length ? `${alerts.length} 项需要关注` : '运行平稳'}</h3></div><div className="alert-stack">{alerts.length ? alerts.slice(0, 3).map((alert) => <button className={`alert-row ${text(alert.level)}`} onClick={() => navigate(text(alert.target))} key={`${text(alert.title)}-${text(alert.level)}`}><Status value={text(alert.level)} /><span><strong>{text(alert.title)}</strong><small>{text(alert.detail)}</small></span><ChevronRight size={14} /></button>) : <p>当前没有触发运营预警。</p>}</div></article>
    </section>
    {trendFields.length > 0 && <section className="trend-panel"><header><div><span className="eyebrow">七日业务脉冲</span><h3>连续观察当前职责范围内的业务活跃度</h3>{hasPermission(session, 'users.read') && <p>近 7 日新增用户 {number(comparison.users_current)} 人，较前 7 日 {userChange >= 0 ? '+' : ''}{userChange}。</p>}</div><div className="trend-legend">{trendFields.map((field) => <span key={field.key}><i className={field.key} />{field.label}</span>)}</div></header><div className="trend-chart">{trend.map((item) => <div className="trend-day" key={text(item.day)}><div className="trend-bars">{trendFields.map((field) => <i className={field.key} style={{ height: `${Math.max(7, number(item[field.key]) / trendMax * 100)}%` }} title={`${field.label} ${number(item[field.key])}`} key={field.key} />)}</div><small>{shortDate(item.day)}</small></div>)}</div></section>}
    {lifecycle.length > 0 && <section className="lifecycle-card"><header><div><span className="eyebrow">业务全链路巡检带</span><h3>异常会直接落到待办中心</h3></div><small>更新时间：{dateTime(resource.data?.generated_at)}</small></header><div className="lifecycle-track">{lifecycle.map((stage, index) => <div className="lifecycle-stage" key={text(stage.key)}><span className="lifecycle-index">{String(index + 1).padStart(2, '0')}</span><strong>{text(stage.label)}</strong><b>{number(stage.value).toLocaleString('zh-CN')}</b><small className={number(stage.issue_count) > 0 ? 'has-issue' : ''}>{number(stage.issue_count) > 0 ? `${number(stage.issue_count)} 项异常` : '运行正常'}</small></div>)}</div></section>}
    {(canWorkItems || factRows.length > 0) && <section className="split-grid">{canWorkItems && <article className="panel"><PanelTitle icon={ClipboardCheck} title="优先待办" note="按 SLA 与风险排序" /><SimpleTable columns={['待办', '优先级', '状态', '截止时间']} rows={workItems} render={(item) => [text(item.title), <Status key="priority" value={text(item.priority)} />, <Status key="status" value={text(item.status)} />, dateTime(item.due_at)]} empty="当前没有待处理事项" /></article>}{factRows.length > 0 && <article className="panel"><PanelTitle icon={Gauge} title="运营状态" note="仅显示你有权查看的业务数据" /><dl className="fact-list">{factRows.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value.toLocaleString('zh-CN')}</dd></div>)}</dl></article>}</section>}
  </LoadingState></>;
}

function QueuePage({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  return <QueueWorkspace session={session} onToast={onToast} />;

  const [filter, setFilter] = useState(() => {
    const initial = hashQuery('status');
    return ['open', 'claimed', 'completed', 'active', 'all'].includes(initial) ? initial : 'open';
  });
  const path = filter === 'claimed' ? '/work-items?status=claimed&assignee=me' : `/work-items?status=${filter}`;
  const resource = useResource<ListResponse>(session, path);
  const goToBusiness = (item: Row) => {
    const destination: Record<string, PageKey> = { community_report: 'community', community_profile: 'community', husbandry_case: 'husbandry', diagnosis_conversation: 'diagnosis' };
    const page = destination[text(item.resource_type)];
    if (page) window.location.hash = `/${page}`;
    else onToast('该待办暂未配置业务处理页面');
  };
  const change = async (item: Row, action: string) => {
    const reason = action === 'claim' ? '领取待办处理' : await askReasonInDialog(action === 'complete' ? '完成待办' : '释放待办');
    if (!reason) return;
    try {
      await api(`/work-items/${text(item.id)}`, session, { method: 'PATCH', body: JSON.stringify({ action, version: number(item.version), reason }) });
      onToast('待办状态已更新');
      if (action === 'claim') goToBusiness(item);
      else resource.reload();
    } catch (error) { onToast(error instanceof Error ? error.message : '操作失败'); }
  };
  return <><PageHeader eyebrow="任务分派" title="待办中心" description="领取后前往对应业务页面处理；业务审核完成时待办会自动闭环并保留审计记录。" actions={<div className="segmented">{['open', 'claimed', 'active', 'completed'].map((value) => <button className={filter === value ? 'active' : ''} onClick={() => setFilter(value)} key={value}>{value === 'open' ? '待领取' : value === 'claimed' ? '我处理中' : value === 'active' ? '全部进行中' : '已完成'}</button>)}</div>} /><LoadingState loading={resource.loading} error={resource.error}><article className="panel full-panel"><SimpleTable columns={['事项', '优先级', '负责人', '截止时间', '操作']} rows={asItems(resource.data)} render={(item) => [<div key="title"><strong>{text(item.title)}</strong><small>{text(item.item_type)} · {text(item.resource_id)}</small></div>, <Status key="priority" value={text(item.priority)} />, text(item.assignee_id) === session.admin.id ? '我' : text(item.assignee_id, '未领取'), dateTime(item.due_at), <div className="row-actions" key="actions">{text(item.status) === 'open' && <button onClick={() => void change(item, 'claim')}>领取并处理</button>}{text(item.status) === 'claimed' && <><button onClick={() => goToBusiness(item)}>前往处理</button><button className="quiet" onClick={() => void change(item, 'release')}>释放</button></>}{text(item.status) === 'completed' && <button className="quiet" onClick={() => goToBusiness(item)}>查看业务</button>}</div>]} empty="没有符合筛选条件的待办" /></article></LoadingState></>;
}

function QueueWorkspace({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [filter, setFilter] = useState(() => {
    const initial = hashQuery('status');
    return ['open', 'claimed', 'completed', 'active', 'all'].includes(initial) ? initial : 'open';
  });
  const [query, setQuery] = useState('');
  const [priority, setPriority] = useState('');
  const [resourceType, setResourceType] = useState(() => {
    const initial = hashQuery('resource_type');
    return ['community_report', 'community_profile', 'husbandry_case', 'diagnosis_conversation'].includes(initial) ? initial : '';
  });
  const [sla, setSla] = useState(() => ['overdue', 'due_soon', 'on_track'].includes(hashQuery('sla')) ? hashQuery('sla') : '');
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [detailId, setDetailId] = useState('');
  const [transferItem, setTransferItem] = useState<Row | null>(null);
  const params = new URLSearchParams({
    status: filter,
    ...(filter === 'claimed' ? { assignee: 'me' } : {}),
    ...(query.trim() ? { q: query.trim() } : {}),
    ...(priority ? { priority } : {}),
    ...(resourceType ? { resource_type: resourceType } : {}),
    ...(sla ? { sla } : {}),
    page: String(page),
    page_size: '20',
  });
  const resource = useResource<ListResponse>(session, `/work-items?${params.toString()}`);
  const detail = useResource<Row>(session, detailId ? `/work-items/${detailId}` : '/work-items/not-selected', Boolean(detailId));
  const assignees = useResource<ListResponse>(session, '/work-items/assignees', Boolean(transferItem));
  const items = asItems(resource.data);
  const total = number(resource.data?.total);
  const pageSize = number(resource.data?.page_size) || 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  useEffect(() => {
    const timer = window.setInterval(resource.reload, 30_000);
    return () => window.clearInterval(timer);
  }, [resource.reload]);
  useEffect(() => { setPage(1); setSelectedIds([]); }, [filter, query, priority, resourceType, sla]);
  const selectedOpenIds = selectedIds.filter((id) => items.some((item) => text(item.id) === id && text(item.status) === 'open'));
  const goToBusiness = (item: Row) => {
    const resourceId = encodeURIComponent(text(item.resource_id));
    const target: Record<string, string> = {
      community_report: `/community?tab=reports&report_id=${resourceId}`,
      community_profile: `/community?tab=verifications&user_id=${resourceId}`,
      husbandry_case: `/husbandry?case_id=${resourceId}`,
      diagnosis_conversation: `/diagnosis?conversation_id=${resourceId}`,
    };
    const destination = target[text(item.resource_type)];
    if (destination) window.location.hash = destination;
    else onToast('该待办暂未配置对应的业务处理页');
  };
  const change = async (item: Row, action: 'claim' | 'release') => {
    const reason = action === 'claim' ? '领取待办处理' : await askReasonInDialog('释放待办');
    if (!reason) return;
    try {
      await api(`/work-items/${text(item.id)}`, session, { method: 'PATCH', body: JSON.stringify({ action, version: number(item.version), reason }) });
      onToast(action === 'claim' ? '已领取，正在打开对应业务记录' : '待办已释放回公共队列');
      if (action === 'claim') goToBusiness(item);
      else resource.reload();
    } catch (error) { onToast(error instanceof Error ? error.message : '操作失败'); }
  };
  const batchClaim = async () => {
    if (!selectedOpenIds.length) return;
    const reason = await askReasonInDialog(`批量领取 ${selectedOpenIds.length} 项待办`);
    if (!reason) return;
    try {
      const result = await api<Row>('/work-items/batch-claim', session, { method: 'POST', body: JSON.stringify({ item_ids: selectedOpenIds, reason }) });
      onToast(`已领取 ${number(result.claimed)} 项待办`);
      setSelectedIds([]);
      resource.reload();
    } catch (error) { onToast(error instanceof Error ? error.message : '批量领取失败，请刷新后重试'); }
  };
  const transfer = async (targetAdminId: string) => {
    if (!transferItem) return;
    const reason = await askReasonInDialog('转派待办');
    if (!reason) return;
    try {
      await api(`/work-items/${text(transferItem.id)}/transfer`, session, { method: 'POST', body: JSON.stringify({ target_admin_id: targetAdminId, reason }) });
      onToast('待办已转派，处理轨迹已记录');
      setTransferItem(null);
      resource.reload();
    } catch (error) { onToast(error instanceof Error ? error.message : '转派失败'); }
  };
  const toggleSelected = (id: string) => setSelectedIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id]);
  const allOpenSelected = items.filter((item) => text(item.status) === 'open').length > 0 && items.filter((item) => text(item.status) === 'open').every((item) => selectedOpenIds.includes(text(item.id)));
  const toggleAllOpen = () => setSelectedIds(allOpenSelected ? [] : items.filter((item) => text(item.status) === 'open').map((item) => text(item.id)));
  const timeline = Array.isArray(detail.data?.timeline) ? detail.data.timeline as Row[] : [];
  const detailItem = (detail.data?.item ?? {}) as Row;
  const eligibleAssignees = asItems(assignees.data).filter((candidate) => Array.isArray(candidate.resource_types) && (candidate.resource_types as unknown[]).includes(text(transferItem?.resource_type)));
  const queueCounts = {
    overdue: items.filter((item) => text(item.sla_status) === 'overdue').length,
    dueSoon: items.filter((item) => text(item.sla_status) === 'due_soon').length,
    claimed: items.filter((item) => text(item.assignee_id) === session.admin.id && text(item.status) === 'claimed').length,
  };
  const queueViewLabel: Record<string, string> = { open: '待领取', claimed: '我处理中', active: '进行中', completed: '已完成', all: '全部待办' };
  return <>
    <PageHeader eyebrow="任务分派" title="待办中心" description="按 SLA 排序领取任务；业务审核完成后待办自动闭环，所有领取、释放和转派均会写入处理轨迹。" actions={<div className="segmented">{[['open', '待领取'], ['claimed', '我处理中'], ['active', '全部进行中'], ['completed', '已完成']].map(([value, label]) => <button className={filter === value ? 'active' : ''} onClick={() => { setFilter(value); setSelectedIds([]); }} key={value}>{label}</button>)}</div>} />
    <section className="queue-command" aria-label="当前待办概览"><div className="queue-command-copy"><span>LIVE QUEUE</span><h2>先处理时间最紧的工作。</h2><p>当前视图：{queueViewLabel[filter]}，共 {total} 项待办。</p></div><div className="queue-pulse"><div className="queue-pulse-item overdue"><span>已超时</span><strong>{queueCounts.overdue}</strong><i /></div><div className="queue-pulse-item due-soon"><span>即将到期</span><strong>{queueCounts.dueSoon}</strong><i /></div><div className="queue-pulse-item mine"><span>我处理中</span><strong>{queueCounts.claimed}</strong><i /></div></div></section>
    <section className="queue-pagination" aria-label="待办分页"><span>共 {total} 项 · 第 {page} / {totalPages} 页</span><div><button className="quiet-button" disabled={page <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))}>上一页</button><button className="quiet-button" disabled={page >= totalPages} onClick={() => setPage((current) => Math.min(totalPages, current + 1))}>下一页</button></div></section>
    <article className="panel full-panel queue-panel">
      <div className="table-toolbar queue-toolbar"><label className="input-with-icon"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索待办标题或业务 ID" /></label><select value={priority} onChange={(event) => setPriority(event.target.value)}><option value="">全部优先级</option><option value="critical">紧急</option><option value="high">高风险</option><option value="medium">需关注</option><option value="low">低风险</option></select><select value={resourceType} onChange={(event) => setResourceType(event.target.value)}><option value="">全部来源</option><option value="community_report">社区举报</option><option value="community_profile">专业认证</option><option value="husbandry_case">养殖病例</option><option value="diagnosis_conversation">问诊复核</option></select><select value={sla} onChange={(event) => setSla(event.target.value)}><option value="">全部 SLA</option><option value="overdue">已超时</option><option value="due_soon">4 小时内到期</option><option value="on_track">时效正常</option></select></div>
      {filter === 'open' && <div className="queue-bulkbar"><label><input type="checkbox" checked={allOpenSelected} onChange={toggleAllOpen} /> 全选当前页未领取待办</label><span>{selectedOpenIds.length ? `已选 ${selectedOpenIds.length} 项` : '可批量领取同页待办'}</span><button className="primary-button" disabled={!selectedOpenIds.length} onClick={() => void batchClaim()}>批量领取</button></div>}
      <LoadingState loading={resource.loading} error={resource.error}><SimpleTable columns={['', '事项', '优先级', 'SLA', '负责人', '截止时间', '操作']} rows={items} render={(item) => [<input aria-label="选择待办" key="select" type="checkbox" disabled={text(item.status) !== 'open'} checked={selectedOpenIds.includes(text(item.id))} onChange={() => toggleSelected(text(item.id))} />, <button className="table-link" onClick={() => setDetailId(text(item.id))} key="title"><strong>{text(item.title)}</strong><small>{text(item.item_type)} · {text(item.resource_id)}</small></button>, <Status key="priority" value={text(item.priority)} />, <span className={`sla-chip ${text(item.sla_status)}`} key="sla">{queueSlaText(item)}</span>, text(item.assignee_id) === session.admin.id ? '我' : text(item.assignee_name, text(item.assignee_id, '未领取')), <div key="due"><strong>{dateTime(item.due_at)}</strong><small>{queueSlaHint(item)}</small></div>, <div className="row-actions" key="actions"><button className="quiet" onClick={() => setDetailId(text(item.id))}>轨迹</button>{text(item.status) === 'open' && <button onClick={() => void change(item, 'claim')}>领取处理</button>}{text(item.status) === 'claimed' && <><button onClick={() => goToBusiness(item)}>前往处理</button>{text(item.assignee_id) === session.admin.id && <><button className="quiet" onClick={() => setTransferItem(item)}>转派</button><button className="quiet" onClick={() => void change(item, 'release')}>释放</button></>}</>}{text(item.status) === 'completed' && <button className="quiet" onClick={() => goToBusiness(item)}>查看业务</button>}</div>]} empty="没有符合筛选条件的待办" /></LoadingState>
    </article>
    {detailId && <Modal title="待办处理轨迹" onClose={() => setDetailId('')}><LoadingState loading={detail.loading} error={detail.error}>{detail.data ? <><div className="queue-detail-heading"><div><span className="eyebrow">{text(detailItem.item_type)}</span><h3>{text(detailItem.title)}</h3><p>{text(detailItem.resource_id)} · 截止 {dateTime(detailItem.due_at)}</p></div><div><Status value={text(detailItem.status)} /><span className={`sla-chip ${text(detailItem.sla_status)}`}>{queueSlaText(detailItem)}</span></div></div><button className="quiet-button wide" onClick={() => goToBusiness(detailItem)}>前往对应业务记录</button><h4>处理时间线</h4><Timeline rows={timeline} label={(event) => `${dateTime(event.created_at)} · ${text(event.actor_name)} · ${text(event.action)}${text(event.reason) ? `：${text(event.reason)}` : ''}`} /></> : <EmptySelection text="暂无待办详情" />}</LoadingState></Modal>}
    {transferItem && <Modal title="转派待办" onClose={() => setTransferItem(null)}><p className="queue-modal-note">仅显示具备该业务处理权限的在岗管理员。转派后，原负责人不能继续处理该待办。</p><LoadingState loading={assignees.loading} error={assignees.error}>{eligibleAssignees.length ? <div className="queue-assignee-list">{eligibleAssignees.map((candidate) => <button key={text(candidate.id)} onClick={() => void transfer(text(candidate.id))}><span><strong>{text(candidate.display_name)}</strong><small>{text(candidate.email)} · {Array.isArray(candidate.roles) ? (candidate.roles as unknown[]).join('、') : ''}</small></span><ChevronRight size={16} /></button>)}</div> : <EmptySelection text="暂无可接手该业务待办的管理员" />}</LoadingState></Modal>}
  </>;
}

function queueSlaText(item: Row): string {
  const value = text(item.sla_status);
  return value === 'overdue' ? '已超时' : value === 'due_soon' ? '即将到期' : '时效正常';
}

function queueSlaHint(item: Row): string {
  const remaining = item.remaining_seconds;
  if (remaining === null || remaining === undefined) return '未设置截止时间';
  const seconds = number(remaining);
  const absolute = Math.abs(seconds);
  const hours = Math.floor(absolute / 3600);
  const minutes = Math.floor((absolute % 3600) / 60);
  const duration = hours ? `${hours} 小时 ${minutes} 分` : `${minutes} 分`;
  return seconds < 0 ? `已超时 ${duration}` : `剩余 ${duration}`;
}

function UsersPage({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [query, setQuery] = useState(() => hashQuery('q'));
  const [statusFilter, setStatusFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [verificationFilter, setVerificationFilter] = useState('');
  const [attentionFilter, setAttentionFilter] = useState(() => ['reports', 'security', 'verification'].includes(hashQuery('attention')) ? hashQuery('attention') : '');
  const [createdSince, setCreatedSince] = useState(() => ['today', '7d'].includes(hashQuery('created_since')) ? hashQuery('created_since') : '');
  const [sortBy, setSortBy] = useState<'attention' | 'last_seen' | 'registered'>('attention');
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState(() => hashQuery('id'));
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [detailTab, setDetailTab] = useState<'overview' | 'sessions' | 'activity' | 'history'>('overview');
  const [exporting, setExporting] = useState(false);
  const pageSize = 20;

  useEffect(() => {
    setPage(1);
  }, [query, statusFilter, roleFilter, verificationFilter, attentionFilter, createdSince, sortBy]);

  useEffect(() => {
    setSelectedIds([]);
  }, [query, statusFilter, roleFilter, verificationFilter, attentionFilter, createdSince, page]);

  const filters = useMemo(() => ({
    ...(query ? { q: query } : {}),
    ...(statusFilter ? { status: statusFilter } : {}),
    ...(roleFilter ? { role: roleFilter } : {}),
    ...(verificationFilter ? { verification_status: verificationFilter } : {}),
    ...(attentionFilter ? { attention: attentionFilter } : {}),
    ...(createdSince ? { created_since: createdSince } : {}),
    sort: sortBy,
  }), [query, statusFilter, roleFilter, verificationFilter, attentionFilter, createdSince, sortBy]);
  const path = `/users?${new URLSearchParams({ ...filters, page: String(page), page_size: String(pageSize) }).toString()}`;
  const overview = useResource<Row>(session, '/users/overview');
  const resource = useResource<ListResponse>(session, path);
  const detail = useResource<Row>(session, selectedId ? `/users/${selectedId}` : '/users/not-selected', Boolean(selectedId));
  const canManage = hasPermission(session, 'users.manage');
  const canReadCommunity = hasPermission(session, 'community.read');
  const canVerify = hasPermission(session, 'community.verify');
  const rows = asItems(resource.data);
  const total = number(resource.data?.total);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const overviewSummary = (overview.data?.summary ?? {}) as Row;
  const summary = (detail.data?.summary ?? {}) as Row;
  const profile = (detail.data?.profile ?? {}) as Row;
  const sessions = Array.isArray(detail.data?.sessions) ? detail.data.sessions as Row[] : [];
  const activity = Array.isArray(detail.data?.activity) ? detail.data.activity as Row[] : [];
  const moderationHistory = Array.isArray(detail.data?.moderation_history) ? detail.data.moderation_history as Row[] : [];
  const activeSessionCount = number(summary.active_session_count);
  const detailDeleted = text(detail.data?.status) === 'deleted';
  const selectableIds = rows.filter((item) => text(item.status) !== 'deleted').map((item) => text(item.id));
  const selectedAll = selectableIds.length > 0 && selectableIds.every((id) => selectedIds.includes(id));
  const selectedCount = selectedIds.length;

  const refreshAll = () => {
    overview.reload();
    resource.reload();
    detail.reload();
  };

  const selectUser = (userId: string) => {
    setSelectedId(userId);
    setDetailTab('overview');
  };

  const toggleSelection = (userId: string) => {
    setSelectedIds((current) => current.includes(userId) ? current.filter((id) => id !== userId) : [...current, userId]);
  };

  const toggleSelectAll = () => {
    setSelectedIds(selectedAll ? [] : selectableIds);
  };

  const updateUser = async (newStatus: 'active' | 'disabled') => {
    if (!selectedId || detailDeleted) return;
    const isDisable = newStatus === 'disabled';
    const reason = await askReasonInDialog(
      isDisable ? `禁用用户并撤销 ${activeSessionCount} 个活跃会话` : '恢复用户账号',
      { tone: isDisable ? 'danger' : 'default', confirmLabel: isDisable ? '确认禁用' : '确认恢复', description: isDisable ? '禁用后会立即撤销当前全部登录会话；用户不能继续访问系统。' : '恢复账号不会恢复已撤销的登录会话，用户需要重新登录。' },
    );
    if (!reason) return;
    try {
      await api(`/users/${selectedId}/status`, session, { method: 'PATCH', body: JSON.stringify({ status: newStatus, reason }) });
      onToast(isDisable ? '用户已禁用，活跃会话已撤销' : '用户已恢复');
      refreshAll();
    } catch (error) {
      onToast(error instanceof Error ? error.message : '操作失败');
    }
  };

  const revokeAllSessions = async () => {
    if (!selectedId) return;
    const reason = await askReasonInDialog(`撤销该用户全部 ${activeSessionCount} 个活跃会话`);
    if (!reason) return;
    try {
      const result = await api<{ revoked_sessions: number }>(`/users/${selectedId}/sessions/revoke`, session, { method: 'POST', body: JSON.stringify({ reason }) });
      onToast(`已撤销 ${number(result.revoked_sessions)} 个登录会话`);
      refreshAll();
    } catch (error) {
      onToast(error instanceof Error ? error.message : '操作失败');
    }
  };

  const revokeOneSession = async (sessionId: string, deviceName: string) => {
    if (!selectedId) return;
    const reason = await askReasonInDialog(`撤销设备“${deviceName}”的登录会话`);
    if (!reason) return;
    try {
      await api(`/users/${selectedId}/sessions/${sessionId}/revoke`, session, { method: 'POST', body: JSON.stringify({ reason }) });
      onToast('该设备已下线');
      refreshAll();
    } catch (error) {
      onToast(error instanceof Error ? error.message : '操作失败');
    }
  };

  const applyBatchAction = async (action: 'disable' | 'restore' | 'revoke_sessions') => {
    if (!selectedCount) return;
    const labels = {
      disable: '批量禁用用户',
      restore: '批量恢复用户',
      revoke_sessions: '批量撤销登录会话',
    };
    const reason = await askReasonInDialog(labels[action], {
      tone: action === 'disable' ? 'danger' : 'default',
      confirmLabel: action === 'disable' ? '确认禁用' : '确认操作',
      description: action === 'disable' ? `将禁用 ${selectedCount} 个账号并撤销活跃会话。已删除账号会保持只读。` : `将对选中的 ${selectedCount} 个用户执行操作，并写入每个账号的处置记录。`,
    });
    if (!reason) return;
    try {
      const result = await api<Row>('/users/batch-action', session, { method: 'POST', body: JSON.stringify({ user_ids: selectedIds, action, reason }) });
      const changed = number(result.changed_user_count);
      const revoked = number(result.revoked_session_count);
      const skipped = number(result.skipped_deleted_count);
      const suffix = skipped ? `，跳过 ${skipped} 个已删除账号` : '';
      onToast(action === 'revoke_sessions' ? `已撤销 ${revoked} 个用户的登录会话${suffix}` : `已处理 ${changed} 个用户${revoked ? `，并撤销 ${revoked} 个活跃会话` : ''}${suffix}`);
      setSelectedIds([]);
      refreshAll();
    } catch (error) {
      onToast(error instanceof Error ? error.message : '批量操作失败');
    }
  };

  const openCommunityContext = (tab: 'reports' | 'verifications') => {
    if (!selectedId) return;
    window.location.hash = tab === 'reports' ? `/community?tab=reports&author_id=${encodeURIComponent(selectedId)}` : `/community?tab=verifications&user_id=${encodeURIComponent(selectedId)}`;
  };

  const exportUsers = async () => {
    setExporting(true);
    try {
      await downloadFile(`/users/export?${new URLSearchParams(filters).toString()}`, session);
      onToast('已导出当前筛选条件下的脱敏用户清单');
    } catch (error) {
      onToast(error instanceof Error ? error.message : '导出失败');
    } finally {
      setExporting(false);
    }
  };

  return <>
    <PageHeader
      eyebrow="Identity & account control"
      title="用户管理"
      description="集中处理账号状态、身份认证、会话安全与社区风险。"
      actions={<><button className="quiet-button users-refresh-button" type="button" disabled={overview.loading || resource.loading} onClick={refreshAll}><RefreshCcw size={15} className={overview.loading || resource.loading ? 'is-spinning' : ''} />刷新</button><button className="quiet-button users-export-button" type="button" disabled={exporting} onClick={() => void exportUsers()}><Download size={15} />{exporting ? '正在导出…' : '导出脱敏清单'}</button></>}
    />
    <section className="users-console">
      <section className="users-trust-strip">
        <div><span><ShieldCheck size={14} />账号健康</span><h3>先处理影响账户安全与社区信任的用户。</h3></div>
        <div className="users-trust-actions"><button type="button" className={attentionFilter === 'reports' ? 'active' : ''} onClick={() => setAttentionFilter((value) => value === 'reports' ? '' : 'reports')}><Flag size={14} /><strong>{number(overviewSummary.users_with_pending_reports)}</strong><small>待处理举报</small></button><button type="button" className={attentionFilter === 'security' ? 'active' : ''} onClick={() => setAttentionFilter((value) => value === 'security' ? '' : 'security')}><ShieldAlert size={14} /><strong>{number(overviewSummary.users_with_security_events)}</strong><small>登录异常</small></button><button type="button" className={attentionFilter === 'verification' ? 'active' : ''} onClick={() => setAttentionFilter((value) => value === 'verification' ? '' : 'verification')}><UserRoundCheck size={14} /><strong>{number(overviewSummary.pending_verifications)}</strong><small>待认证</small></button></div>
      </section>
      <section className="users-metric-grid" aria-label="用户运营概览">
        <article><Users size={16} /><span>有效用户</span><strong>{number(overviewSummary.total_users)}</strong><small>正常 {number(overviewSummary.active_users)}</small></article>
        <article><UserPlus size={16} /><span>今日新增</span><strong>{number(overviewSummary.new_today)}</strong><small>近 7 天 {number(overviewSummary.new_7d)}</small></article>
        <article className="attention"><ShieldAlert size={16} /><span>已禁用</span><strong>{number(overviewSummary.disabled_users)}</strong><small>账号不可访问</small></article>
        <article><Activity size={16} /><span>活跃会话</span><strong>{number(overviewSummary.active_sessions)}</strong><small>{number(overviewSummary.users_with_active_sessions)} 位用户</small></article>
        <article className="attention"><Flag size={16} /><span>社区关注</span><strong>{number(overviewSummary.users_with_pending_reports)}</strong><small>待审核关联用户</small></article>
        <article><UserCheck size={16} /><span>认证待审</span><strong>{number(overviewSummary.pending_verifications)}</strong><small>专业身份资料</small></article>
      </section>
      <section className="workspace-grid users-workspace">
        <article className="panel list-panel users-list-panel">
          <header className="users-list-header"><div><span>用户目录</span><h3>按风险与活跃度查看</h3></div><small>{selectedCount ? `已选择 ${selectedCount} 位用户` : `${total.toLocaleString('zh-CN')} 位匹配用户`}</small></header>
          {selectedCount > 0 && canManage && <div className="users-batch-bar"><span>批量操作</span><button className="danger-button" onClick={() => void applyBatchAction('disable')}>禁用账号</button><button className="quiet-button" onClick={() => void applyBatchAction('restore')}>恢复账号</button><button className="quiet-button" onClick={() => void applyBatchAction('revoke_sessions')}>撤销会话</button><button className="text-button" onClick={() => setSelectedIds([])}>取消选择</button></div>}
        <div className="table-toolbar users-toolbar">
          <label className="input-with-icon users-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="姓名、用户名、ID 或脱敏身份" /></label>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="">所有状态</option><option value="active">正常</option><option value="disabled">已禁用</option><option value="deleted">已删除</option></select>
          <select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}><option value="">所有角色</option><option value="farmer">养殖户</option><option value="agritech">农技人员</option><option value="expert">专家</option><option value="admin">管理员</option></select>
          <select value={verificationFilter} onChange={(event) => setVerificationFilter(event.target.value)}><option value="">全部认证</option><option value="unverified">未认证</option><option value="pending">认证中</option><option value="verified">已认证</option><option value="rejected">已驳回</option></select>
          <select value={attentionFilter} onChange={(event) => setAttentionFilter(event.target.value)}><option value="">全部关注</option><option value="reports">待处理举报</option><option value="security">登录异常</option><option value="verification">认证待审</option></select>
          <select value={createdSince} onChange={(event) => setCreatedSince(event.target.value)}><option value="">全部时间</option><option value="today">今日注册</option><option value="7d">近 7 天注册</option></select>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value as 'attention' | 'last_seen' | 'registered')}><option value="attention">关注优先</option><option value="last_seen">按最近活跃</option><option value="registered">按注册时间</option></select>
        </div>
        <LoadingState loading={resource.loading} error={resource.error}>
          <SimpleTable
            columns={[<input className="users-row-select" aria-label="选择当前页用户" type="checkbox" checked={selectedAll} disabled={!selectableIds.length} onChange={toggleSelectAll} />, '用户', '账号与身份', '关注', '最近活跃']}
            rows={rows}
            render={(item) => [
              <input className="users-row-select" aria-label={`选择用户 ${text(item.display_name)}`} type="checkbox" disabled={text(item.status) === 'deleted'} checked={selectedIds.includes(text(item.id))} onChange={() => toggleSelection(text(item.id))} />,
              <button className={`table-link${text(item.id) === selectedId ? ' selected' : ''}`} onClick={() => selectUser(text(item.id))} key="user"><strong>{text(item.display_name)}</strong><small>{text(item.email) || text(item.phone_number) || '未绑定身份'} · {userRoleLabel(text(item.role))}</small></button>,
              <div className="users-account-cell"><Status value={text(item.status)} /><small>{number(item.active_session_count)} 个活跃会话 · {number(item.conversation_count)} 条对话</small></div>,
              <div className="users-attention-cell">{text(item.attention_level) !== 'none' ? <Status value={`user_${text(item.attention_level)}`} /> : <span className="users-clear-state">正常</span>}<small>{userAttentionHint(item)}</small></div>,
              dateTime(item.last_seen_at),
            ]}
            empty="没有匹配的用户"
          />
          <footer className="users-pagination"><span>共 {total.toLocaleString('zh-CN')} 位用户，第 {Math.min(page, totalPages)} / {totalPages} 页</span><div><button className="quiet-button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button><button className="quiet-button" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>下一页</button></div></footer>
        </LoadingState>
        </article>

        <aside className="detail-panel users-detail-panel">
        <LoadingState loading={detail.loading} error={detail.error}>
          {detail.data ? <>
            <div className="detail-heading users-detail-heading"><div><span className="eyebrow">用户档案</span><h3>{text(detail.data.display_name)}</h3><p>{text(detail.data.email) || text(detail.data.phone_number) || '未展示登录身份'}</p></div><div className="users-detail-status"><Status value={text(detail.data.status)} />{text(detail.data.attention_level) !== 'none' && <Status value={`user_${text(detail.data.attention_level)}`} />}</div></div>
            <dl className="fact-list compact"><div><dt>角色</dt><dd>{userRoleLabel(text(detail.data.role))}</dd></div><div><dt>专业认证</dt><dd><Status value={text(detail.data.verification_status)} /></dd></div><div><dt>所属地区</dt><dd>{text(profile.region, '未填写')}</dd></div><div><dt>注册时间</dt><dd>{dateTime(detail.data.registered_at)}</dd></div><div><dt>最近活跃</dt><dd>{dateTime(detail.data.last_seen_at)}</dd></div></dl>
            <div className="users-detail-tabs" role="tablist"><button role="tab" aria-selected={detailTab === 'overview'} className={detailTab === 'overview' ? 'active' : ''} onClick={() => setDetailTab('overview')}>概览</button><button role="tab" aria-selected={detailTab === 'sessions'} className={detailTab === 'sessions' ? 'active' : ''} onClick={() => setDetailTab('sessions')}>设备 {activeSessionCount}</button><button role="tab" aria-selected={detailTab === 'activity'} className={detailTab === 'activity' ? 'active' : ''} onClick={() => setDetailTab('activity')}>业务</button><button role="tab" aria-selected={detailTab === 'history'} className={detailTab === 'history' ? 'active' : ''} onClick={() => setDetailTab('history')}>处置</button></div>

            {detailTab === 'overview' && <><h4>账户与业务状态</h4><div className="user-summary-grid">{[['活跃会话', 'active_session_count'], ['近 7 天登录失败', 'login_failure_count_7d'], ['待处理举报', 'pending_report_count'], ['待跟进病例', 'open_case_count'], ['对话', 'conversation_count'], ['帖子', 'post_count'], ['养殖场', 'farm_count'], ['项目', 'project_count']].map(([label, key]) => <span key={key}><b>{number(summary[key])}</b>{label}</span>)}</div><h4>账号处置</h4>{detailDeleted ? <div className="users-readonly-state"><FileArchive size={15} /><span>该账号已删除，当前仅保留审计档案，不提供恢复或会话操作。</span></div> : canManage ? <div className="stack-actions users-safety-actions">{text(detail.data.status) === 'active' ? <button className="danger-button" onClick={() => void updateUser('disabled')}>禁用用户</button> : <button className="primary-button" onClick={() => void updateUser('active')}>恢复用户</button>}<button className="quiet-button" disabled={!activeSessionCount} onClick={() => void revokeAllSessions()}>撤销全部登录会话</button>{text(detail.data.verification_status) === 'pending' && canVerify && <button className="quiet-button" onClick={() => openCommunityContext('verifications')}>审核认证</button>}{number(summary.pending_report_count) > 0 && canReadCommunity && <button className="quiet-button" onClick={() => openCommunityContext('reports')}>查看举报</button>}</div> : <p className="empty-note">当前账号仅拥有查看权限。</p>}<h4>最近登录</h4><Timeline rows={Array.isArray(detail.data.login_events) ? detail.data.login_events as Row[] : []} label={userLoginEventLabel} /></>}

            {detailTab === 'sessions' && <section className="user-session-list">{sessions.length ? sessions.map((item) => { const deviceName = text(item.device_name, '未知设备'); const isActive = text(item.status) === 'active'; return <article key={text(item.id)}><div><strong>{deviceName}</strong><small>{text(item.ip_address, '未记录 IP')} · 最近使用 {dateTime(item.last_used_at)}</small></div><div><Status value={text(item.status)} />{canManage && isActive && <button className="quiet-button" onClick={() => void revokeOneSession(text(item.id), deviceName)}>下线</button>}</div></article>; }) : <p className="empty-note">暂无登录设备记录</p>}</section>}

            {detailTab === 'activity' && <section className="user-activity-list">{activity.length ? activity.map((item) => <article key={`${text(item.type)}-${text(item.id)}`}><div><span>{({ conversation: '对话', case: '病例', post: '社区帖子' }[text(item.type)] ?? '业务记录')}</span><strong>{text(item.title, '未命名记录')}</strong><small>{dateTime(item.occurred_at)}</small></div><Status value={text(item.status)} /></article>) : <p className="empty-note">暂无关联业务记录</p>}</section>}

            {detailTab === 'history' && <section className="user-history-list">{moderationHistory.length ? moderationHistory.map((item, index) => <article key={`${text(item.action_type)}-${index}`}><span /><div><strong>{userActionLabel(text(item.action_type))}</strong><p>{text(item.reason, '未填写处置理由')}</p><small>{dateTime(item.created_at)}</small></div></article>) : <p className="empty-note">暂无账号处置记录</p>}</section>}
          </> : <EmptySelection text="从左侧选择一位用户，查看其脱敏档案、设备和关联业务。" />}
        </LoadingState>
        </aside>
      </section>
    </section>
  </>;
}

function userRoleLabel(value: string): string {
  return (({ farmer: '养殖户', agritech: '农技人员', expert: '专家', admin: '管理员' }[value] ?? value) || '未设置角色');
}

function userAttentionHint(item: Row): string {
  const level = text(item.attention_level);
  if (level === 'reports') return `${number(item.pending_report_count)} 条待处理举报`;
  if (level === 'security') return `近 7 天 ${number(item.login_failure_count_7d)} 次失败`;
  if (level === 'verification') return '等待专业身份审核';
  return '未发现待处理信号';
}

function userLoginEventLabel(event: Row): string {
  const labels: Record<string, string> = { login_success: '登录成功', login_failed: '登录失败', verification_failed: '验证码失败', verification_succeeded: '验证码通过', identity_bound: '绑定登录身份', logout: '主动退出', session_refreshed: '刷新会话', session_revoked: '会话已撤销' };
  const eventType = text(event.event_type);
  return `${labels[eventType] ?? eventType} · ${text(event.failure_reason, '正常')} · ${dateTime(event.created_at)}`;
}

function userActionLabel(value: string): string {
  return ({ user_disabled: '禁用账号', user_active: '恢复账号', user_sessions_revoked: '撤销登录会话' }[value] ?? value);
}

function LegacyCommunityPage({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [tab, setTab] = useState<'reports' | 'verifications' | 'posts' | 'tags'>(() => {
    const initial = hashQuery('tab');
    return ['reports', 'verifications', 'posts', 'tags'].includes(initial) ? initial as 'reports' | 'verifications' | 'posts' | 'tags' : 'reports';
  });
  const reportId = hashQuery('report_id'); const verificationUserId = hashQuery('user_id');
  const paths = { reports: `/community/reports?status=pending${reportId ? `&id=${encodeURIComponent(reportId)}` : ''}`, verifications: `/community/verifications?status=pending${verificationUserId ? `&user_id=${encodeURIComponent(verificationUserId)}` : ''}`, posts: '/community/content/posts', tags: '/community/tags' };
  const resource = useResource<ListResponse>(session, paths[tab]);
  const renameTag = async (_item: Row) => { onToast('请使用新的标签治理工作台完成重命名'); };
  const mergeTag = async (_item: Row) => { onToast('请使用新的标签治理工作台完成合并'); };
  const reviewReport = async (item: Row, action: 'none' | 'hide' | 'restore' | 'warn' | 'disable_author') => { const reason = await askReasonInDialog('处理社区举报'); if (!reason) return; try { await api(`/community/reports/${text(item.id)}`, session, { method: 'PATCH', body: JSON.stringify({ status: action === 'none' ? 'dismissed' : 'reviewed', action, version: Math.max(1, number(item.version)), reason }) }); onToast('举报已处理'); resource.reload(); } catch (error) { onToast(error instanceof Error ? error.message : '操作失败'); } };
  const reviewVerification = async (item: Row, verificationStatus: 'verified' | 'rejected') => { const reason = await askReasonInDialog(verificationStatus === 'verified' ? '通过专业认证' : '驳回专业认证'); if (!reason) return; try { await api(`/community/verifications/${text(item.user_id)}`, session, { method: 'PATCH', body: JSON.stringify({ status: verificationStatus, version: Math.max(1, number(item.verification_version)), reason }) }); onToast('认证状态已更新'); resource.reload(); } catch (error) { onToast(error instanceof Error ? error.message : '操作失败'); } };
  const updatePost = async (item: Row, postStatus: 'published' | 'hidden' | 'deleted') => { const reason = await askReasonInDialog(postStatus === 'hidden' ? '隐藏帖子' : '更新帖子状态'); if (!reason) return; try { await api(`/community/content/posts/${text(item.id)}/status`, session, { method: 'PATCH', body: JSON.stringify({ status: postStatus, version: Math.max(1, number(item.moderation_version)), reason }) }); onToast('内容状态已更新'); resource.reload(); } catch (error) { onToast(error instanceof Error ? error.message : '操作失败'); } };
  return <><PageHeader eyebrow="内容与信任" title="社区审核" description="举报、认证和内容处置共享同一条可追溯审核链路。" actions={<Tabs current={tab} onChange={setTab} values={[['reports', '举报队列'], ['verifications', '专业认证'], ['posts', '内容管理'], ['tags', '标签']]} />} /><article className="panel full-panel"><LoadingState loading={resource.loading} error={resource.error}>{tab === 'reports' && <SimpleTable columns={['举报原因', '目标内容', '提交人', '状态', '处置']} rows={asItems(resource.data)} render={(item) => [<div key="reason"><strong>{text(item.reason)}</strong><small>{text(item.detail)}</small></div>, <div key="target"><strong>{text(item.target_summary)}</strong><small>{text(item.target_type)} · {text(item.target_status)}</small></div>, text(item.reporter_name), <Status key="status" value={text(item.status)} />, <div className="row-actions" key="action"><button onClick={() => void reviewReport(item, 'hide')}>隐藏</button><button onClick={() => void reviewReport(item, 'none')}>驳回</button><button className="danger" onClick={() => void reviewReport(item, 'disable_author')}>禁用作者</button></div>]} empty="没有待处理举报" />}{tab === 'verifications' && <SimpleTable columns={['申请人', '身份资料', '状态', '提交时间', '处置']} rows={asItems(resource.data)} render={(item) => [<div key="name"><strong>{text(item.display_name)}</strong><small>{text(item.user_status)}</small></div>, <div key="profile"><strong>{text(item.identity_type)}</strong><small>{text(item.organization)} · {text(item.region)}</small></div>, <Status key="status" value={text(item.verification_status)} />, dateTime(item.updated_at), <div className="row-actions" key="action"><button onClick={() => void reviewVerification(item, 'verified')}>通过</button><button className="quiet" onClick={() => void reviewVerification(item, 'rejected')}>驳回</button></div>]} empty="没有待审核的专业资料" />}{tab === 'posts' && <SimpleTable columns={['帖子', '作者', '类型', '互动', '状态', '处置']} rows={asItems(resource.data)} render={(item) => [<div key="title"><strong>{text(item.title)}</strong><small>{text(item.excerpt)}</small></div>, text(item.author_name), text(item.post_type), `${number(item.like_count)} 赞 · ${number(item.comment_count)} 评`, <Status key="status" value={text(item.status)} />, <div className="row-actions" key="action"><button onClick={() => void updatePost(item, 'hidden')}>隐藏</button><button className="quiet" onClick={() => void updatePost(item, 'published')}>恢复</button></div>]} empty="没有社区内容" />}{tab === 'tags' && <SimpleTable columns={['标签', '关联帖子', '创建时间', '治理']} rows={asItems(resource.data)} render={(item) => [<strong key="name">#{text(item.name)}</strong>, number(item.post_count).toLocaleString('zh-CN'), dateTime(item.created_at), <div className="row-actions" key="action"><button onClick={() => void renameTag(item)}>重命名</button><button className="quiet" onClick={() => void mergeTag(item)}>合并</button></div>]} empty="暂无标签" />}</LoadingState></article></>;
}

type CommunitySelection = { kind: 'report' | 'verification' | 'post'; id: string };
type TagGovernanceRequest = { mode: 'rename' | 'merge'; tag: Row };
type CommunityTab = 'reports' | 'verifications' | 'posts' | 'tags';
type CommunityQueueTab = Exclude<CommunityTab, 'tags'>;

function CommunityPage({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [tab, setTab] = useState<CommunityTab>(() => {
    const initial = hashQuery('tab');
    return ['reports', 'verifications', 'posts', 'tags'].includes(initial) ? initial as CommunityTab : 'reports';
  });
  const [reportStatus, setReportStatus] = useState(() => hashQuery('report_id') || hashQuery('author_id') ? 'all' : 'pending');
  const [verificationStatus, setVerificationStatus] = useState(() => hashQuery('user_id') ? 'all' : 'pending');
  const [postStatus, setPostStatus] = useState(''); const [query, setQuery] = useState(''); const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<CommunitySelection | null>(() => {
    const reportId = hashQuery('report_id'); const userId = hashQuery('user_id');
    return reportId ? { kind: 'report', id: reportId } : userId ? { kind: 'verification', id: userId } : null;
  });
  const [tagDialog, setTagDialog] = useState<TagGovernanceRequest | null>(null);
  const params = new URLSearchParams({ page: String(page), page_size: '20' });
  if (query.trim()) params.set('q', query.trim());
  const reportId = hashQuery('report_id'); const reportAuthorId = hashQuery('author_id'); const verificationUserId = hashQuery('user_id');
  const paths = {
    reports: `/community/reports?status=${reportStatus}${reportId ? `&id=${encodeURIComponent(reportId)}` : ''}${reportAuthorId ? `&author_id=${encodeURIComponent(reportAuthorId)}` : ''}&${params.toString()}`,
    verifications: `/community/verifications?status=${verificationStatus}${verificationUserId ? `&user_id=${encodeURIComponent(verificationUserId)}` : ''}&${params.toString()}`,
    posts: `/community/content/posts?${postStatus ? `status=${postStatus}&` : ''}${params.toString()}`,
    tags: `/community/tags?${params.toString()}`,
  };
  const resource = useResource<ListResponse>(session, paths[tab]);
  const detailPath = selected?.kind === 'report' ? `/community/reports/${selected.id}` : selected?.kind === 'verification' ? `/community/verifications/${selected.id}` : selected?.kind === 'post' ? `/community/content/posts/${selected.id}` : '/community/not-selected';
  const detail = useResource<Row>(session, detailPath, Boolean(selected));
  const tagOptions = useResource<ListResponse>(session, '/community/tags?page_size=100', Boolean(tagDialog));
  const canModerate = hasPermission(session, 'community.moderate'); const canVerify = hasPermission(session, 'community.verify');
  const reload = () => { resource.reload(); detail.reload(); };
  const switchTab = (next: CommunityTab) => { setTab(next); setSelected(null); setQuery(''); setPage(1); };
  const reviewReport = async (item: Row, action: 'none' | 'hide' | 'restore' | 'warn' | 'disable_author') => {
    const labels = { none: '忽略社区举报', hide: '隐藏被举报内容', restore: '恢复被举报内容', warn: '向作者发送社区警告', disable_author: '禁用内容作者' };
    const reason = await askReasonInDialog(labels[action], { confirmLabel: '确认处置', tone: action === 'disable_author' ? 'danger' : 'default', description: '处置原因会写入审计记录，并同步给相关用户。' });
    if (!reason) return;
    try { await api(`/community/reports/${text(item.id)}`, session, { method: 'PATCH', body: JSON.stringify({ status: action === 'none' ? 'dismissed' : 'reviewed', action, version: Math.max(1, number(item.version)), reason }) }); onToast('举报已处理，处理结果已通知相关用户'); setSelected(null); reload(); } catch (error) { onToast(error instanceof Error ? error.message : '操作失败'); }
  };
  const reviewVerification = async (item: Row, status: 'verified' | 'rejected') => {
    const reason = await askReasonInDialog(status === 'verified' ? '通过专业认证' : '驳回专业认证', { confirmLabel: status === 'verified' ? '确认通过' : '确认驳回', description: '审核结论会通知申请人。' });
    if (!reason) return;
    try { await api(`/community/verifications/${text(item.user_id)}`, session, { method: 'PATCH', body: JSON.stringify({ status, version: Math.max(1, number(item.verification_version)), reason }) }); onToast('认证结果已更新并通知申请人'); setSelected(null); reload(); } catch (error) { onToast(error instanceof Error ? error.message : '操作失败'); }
  };
  const updatePost = async (item: Row, status: 'published' | 'hidden' | 'deleted') => {
    const labels = { published: '恢复发布帖子', hidden: '隐藏帖子', deleted: '删除帖子' };
    const reason = await askReasonInDialog(labels[status], { confirmLabel: status === 'deleted' ? '确认删除' : '确认处置', tone: status === 'deleted' ? 'danger' : 'default', description: status === 'deleted' ? '删除后不可恢复，作者会收到通知。' : '作者会收到本次内容处置通知。' });
    if (!reason) return;
    try { await api(`/community/content/posts/${text(item.id)}/status`, session, { method: 'PATCH', body: JSON.stringify({ status, version: Math.max(1, number(item.moderation_version)), reason }) }); onToast('内容状态已更新并通知作者'); setSelected(null); reload(); } catch (error) { onToast(error instanceof Error ? error.message : '操作失败'); }
  };
  const submitTag = async (payload: { mode: 'rename' | 'merge'; tag: Row; name?: string; targetTagId?: string; reason: string }) => {
    try {
      if (payload.mode === 'rename') await api(`/community/tags/${text(payload.tag.id)}`, session, { method: 'PATCH', body: JSON.stringify({ name: payload.name, reason: payload.reason }) });
      else await api(`/community/tags/${text(payload.tag.id)}/merge`, session, { method: 'POST', body: JSON.stringify({ target_tag_id: payload.targetTagId, reason: payload.reason }) });
      onToast(payload.mode === 'rename' ? '标签名称已更新' : '标签已合并'); setTagDialog(null); resource.reload();
    } catch (error) { onToast(error instanceof Error ? error.message : '标签治理操作失败'); }
  };
  const rows = asItems(resource.data);
  const total = number(resource.data?.total);
  const queueTab = tab === 'tags' ? null : tab;
  const queueMeta = tab === 'reports'
    ? { kicker: 'REPORT INTAKE', title: '先判断内容风险，再决定处置。', description: '举报、认证和内容处置都从同一个审核台进入；每次决定都会写入可追溯记录。', queueTitle: '举报队列', queueHint: '按待处理状态与最新提交排序', actionLabel: '查看审核', empty: '当前筛选下没有举报记录' }
    : tab === 'verifications'
      ? { kicker: 'IDENTITY REVIEW', title: '核验专业身份，也保留业务语境。', description: '先看申请资料与社区历史，再做通过或驳回决定，避免只凭单一字段判断。', queueTitle: '认证队列', queueHint: '按申请状态与最近更新排序', actionLabel: '查看资料', empty: '当前筛选下没有认证申请' }
      : tab === 'posts'
        ? { kicker: 'CONTENT SAFETY', title: '让内容治理既及时，也有依据。', description: '从帖子状态、互动与举报线索进入处置，必要时查看完整历史再做决定。', queueTitle: '内容队列', queueHint: '按内容状态与最近更新时间排序', actionLabel: '查看内容', empty: '当前筛选下没有社区内容' }
        : { kicker: 'TAG GOVERNANCE', title: '让话题入口保持可理解和可复用。', description: '统一治理重复或不规范标签，保留每次改名与合并的审计理由。', queueTitle: '标签治理', queueHint: '按标签创建时间排序', actionLabel: '管理标签', empty: '当前筛选下没有标签' };
  const attentionCount = rows.filter((item) => tab === 'reports'
    ? text(item.status) === 'pending'
    : tab === 'verifications'
      ? text(item.verification_status) === 'pending'
      : tab === 'posts'
        ? ['hidden', 'draft'].includes(text(item.status))
        : false).length;
  const statusLabel = tab === 'reports' ? reportStatus === 'pending' ? '待处理' : reportStatus === 'reviewed' ? '已处置' : reportStatus === 'dismissed' ? '已忽略' : '全部状态'
    : tab === 'verifications' ? verificationStatus === 'pending' ? '待审核' : verificationStatus === 'verified' ? '已认证' : verificationStatus === 'rejected' ? '已驳回' : '全部状态'
      : tab === 'posts' ? postStatus ? ({ published: '已发布', hidden: '已隐藏', deleted: '已删除', draft: '草稿' }[postStatus] ?? '全部状态') : '全部状态'
        : '全部标签';
  const clearFilters = () => { setQuery(''); setPage(1); if (tab === 'reports') setReportStatus('pending'); if (tab === 'verifications') setVerificationStatus('pending'); if (tab === 'posts') setPostStatus(''); };
  const toolbar = <div className="community-filter-bar"><label className="input-with-icon"><Search size={15} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder={tab === 'reports' ? '搜索举报原因、内容或提交人' : tab === 'posts' ? '搜索标题、正文或 ID' : tab === 'verifications' ? '搜索姓名、机构或地区' : '搜索标签'} /></label>{tab === 'reports' && <select value={reportStatus} onChange={(event) => { setReportStatus(event.target.value); setPage(1); }}><option value="pending">待处理</option><option value="reviewed">已处置</option><option value="dismissed">已忽略</option><option value="all">全部状态</option></select>}{tab === 'verifications' && <select value={verificationStatus} onChange={(event) => { setVerificationStatus(event.target.value); setPage(1); }}><option value="pending">待审核</option><option value="verified">已认证</option><option value="rejected">已驳回</option><option value="all">全部状态</option></select>}{tab === 'posts' && <select value={postStatus} onChange={(event) => { setPostStatus(event.target.value); setPage(1); }}><option value="">全部状态</option><option value="published">已发布</option><option value="hidden">已隐藏</option><option value="deleted">已删除</option><option value="draft">草稿</option></select>}</div>;
  return <><PageHeader eyebrow="内容与信任" title="社区审核" description="把举报、专业认证和内容治理收进同一个可追溯的审核工作台。" actions={<div className="community-page-actions"><Tabs current={tab} onChange={switchTab} values={[['reports', '举报队列'], ['verifications', '专业认证'], ['posts', '内容管理'], ['tags', '标签治理']]} /><button className="quiet-button" type="button" disabled={resource.loading} onClick={reload}><RefreshCcw size={15} className={resource.loading ? 'is-spinning' : ''} />刷新</button></div>} /><section className="community-console"><section className="community-hero"><div><span>{queueMeta.kicker}</span><h2>{queueMeta.title}</h2><p>{queueMeta.description}</p></div><div className="community-hero-orbit"><span>当前队列</span><strong>{total.toLocaleString('zh-CN')}<i>项</i></strong><small>{statusLabel} · 本页 {rows.length} 项</small></div></section><section className="community-summary-grid" aria-label="社区审核概览"><article><Flag size={16} /><span>当前匹配</span><strong>{total.toLocaleString('zh-CN')}</strong><small>{queueMeta.queueTitle}</small></article><article className={attentionCount ? 'attention' : ''}><ShieldAlert size={16} /><span>本页待判断</span><strong>{attentionCount.toLocaleString('zh-CN')}</strong><small>{tab === 'posts' ? '隐藏或草稿内容' : '需要人工决策的记录'}</small></article><article><CheckCircle2 size={16} /><span>当前选择</span><strong>{selected ? '1' : '0'}</strong><small>{selected ? '详情已在右侧打开' : '从队列选择一项'}</small></article></section>{queueTab && attentionCount > 0 && <section className="community-attention-strip"><div><span>优先处理</span><strong>{tab === 'reports' ? '先处理仍在公开展示的举报内容' : tab === 'verifications' ? '先核验待认证的专业资料' : '先确认隐藏和草稿内容的后续状态'}</strong></div><div><span>{attentionCount} 项本页记录需要人工判断</span><button className="text-button" type="button" onClick={clearFilters}>恢复默认队列</button></div></section>}{tab === 'tags' ? <article className="community-tags-panel"><header><div><span>标签目录</span><h3>统一命名，再决定是否合并</h3></div><small>{total.toLocaleString('zh-CN')} 个匹配标签</small></header>{toolbar}<LoadingState loading={resource.loading} error={resource.error}><SimpleTable columns={['标签', '关联帖子', '创建时间', '治理']} rows={rows} render={(item) => [<strong key="name">#{text(item.name)}</strong>, number(item.post_count).toLocaleString('zh-CN'), dateTime(item.created_at), <div className="row-actions" key="action"><button onClick={() => setTagDialog({ mode: 'rename', tag: item })}>重命名</button><button className="quiet" onClick={() => setTagDialog({ mode: 'merge', tag: item })}>合并</button></div>]} empty="当前筛选下没有标签" /></LoadingState><Pagination total={total} page={page} pageSize={number(resource.data?.page_size) || 20} onChange={setPage} /></article> : <section className="community-review-workspace"><article className="community-list-panel"><header><div><span>{queueMeta.queueTitle}</span><h3>{queueMeta.queueHint}</h3></div><b>{total.toLocaleString('zh-CN')}</b></header>{toolbar}<div className="community-result-bar"><span>共 {total.toLocaleString('zh-CN')} 项，第 {page} / {Math.max(1, Math.ceil(total / (number(resource.data?.page_size) || 20)))} 页</span><div><button className="quiet-button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button><button className="quiet-button" disabled={page >= Math.max(1, Math.ceil(total / (number(resource.data?.page_size) || 20)))} onClick={() => setPage((value) => value + 1)}>下一页</button></div></div><LoadingState loading={resource.loading} error={resource.error}><CommunityReviewQueue tab={queueTab} rows={rows} selected={selected} onSelect={setSelected} actionLabel={queueMeta.actionLabel} empty={queueMeta.empty} /></LoadingState></article><aside className="community-detail-panel"><LoadingState loading={detail.loading} error={detail.error}>{selected && detail.data ? <CommunityReviewDetail selected={selected} detail={detail.data} canModerate={canModerate} canVerify={canVerify} onReviewReport={reviewReport} onReviewVerification={reviewVerification} onUpdatePost={updatePost} /> : <EmptySelection text="从左侧选择一项记录，先查看上下文和历史，再做审核决定。" />}</LoadingState></aside></section>}</section>{tagDialog && <TagGovernanceDialog request={tagDialog} candidates={asItems(tagOptions.data)} onClose={() => setTagDialog(null)} onSubmit={submitTag} />}</>;
}

function CommunityReviewQueue({ tab, rows, selected, onSelect, actionLabel, empty }: { tab: CommunityQueueTab; rows: Row[]; selected: CommunitySelection | null; onSelect: (value: CommunitySelection) => void; actionLabel: string; empty: string }) {
  const kind: CommunitySelection['kind'] = tab === 'reports' ? 'report' : tab === 'verifications' ? 'verification' : 'post';
  if (!rows.length) return <div className="community-queue-empty"><MessageSquare size={20} /><span>{empty}</span></div>;
  return <div className="community-review-queue">{rows.map((item) => {
    const id = tab === 'verifications' ? text(item.user_id) : text(item.id);
    const status = tab === 'verifications' ? text(item.verification_status) : text(item.status);
    const title = tab === 'reports' ? text(item.reason, '未命名举报') : tab === 'verifications' ? text(item.display_name, '未命名申请人') : text(item.title, '未命名帖子');
    const summary = tab === 'reports' ? `${text(item.target_summary, '目标内容不可用')} · ${text(item.author_name, '未知作者')}` : tab === 'verifications' ? `${text(item.identity_type, '未填写身份类型')} · ${text(item.organization, '未填写机构')}` : text(item.excerpt, '暂无帖子摘要');
    const meta = tab === 'reports' ? `${text(item.reporter_name, '匿名提交')} · ${dateTime(item.created_at)}` : tab === 'verifications' ? `${text(item.region, '未填写地区')} · ${dateTime(item.updated_at)}` : `${text(item.author_name, '未知作者')} · ${number(item.like_count)} 赞 · ${number(item.comment_count)} 评`;
    const value = { kind, id } as CommunitySelection;
    const active = selected?.kind === kind && selected.id === id;
    return <article className={active ? 'selected' : ''} key={`${kind}-${id}`}><button className="community-queue-main" onClick={() => onSelect(value)}><div className="community-row-top"><Status value={status} />{tab === 'reports' && <span className="community-context-pill">{text(item.target_status, '内容状态')}</span>}{tab === 'posts' && <span className="community-context-pill">{text(item.post_type, '社区内容')}</span>}</div><strong>{title}</strong><p>{summary}</p><small>{meta}</small></button><button className="quiet-button" onClick={() => onSelect(value)}>{actionLabel}</button></article>;
  })}</div>;
}

function CommunityReviewDetail({ selected, detail, canModerate, canVerify, onReviewReport, onReviewVerification, onUpdatePost }: { selected: CommunitySelection; detail: Row; canModerate: boolean; canVerify: boolean; onReviewReport: (item: Row, action: 'none' | 'hide' | 'restore' | 'warn' | 'disable_author') => Promise<void>; onReviewVerification: (item: Row, status: 'verified' | 'rejected') => Promise<void>; onUpdatePost: (item: Row, status: 'published' | 'hidden' | 'deleted') => Promise<void> }) {
  if (selected.kind === 'report') return <ReportReviewDetail detail={detail} canModerate={canModerate} onReview={onReviewReport} />;
  if (selected.kind === 'verification') return <VerificationReviewDetail detail={detail} canVerify={canVerify} onReview={onReviewVerification} />;
  return <PostReviewDetail detail={detail} canModerate={canModerate} onUpdate={onUpdatePost} />;
}

function ReportReviewDetail({ detail, canModerate, onReview }: { detail: Row; canModerate: boolean; onReview: (item: Row, action: 'none' | 'hide' | 'restore' | 'warn' | 'disable_author') => Promise<void> }) {
  const report = (detail.report ?? {}) as Row; const priorReports = Array.isArray(detail.prior_reports) ? detail.prior_reports as Row[] : []; const history = Array.isArray(detail.history) ? detail.history as Row[] : []; const assets = Array.isArray(detail.assets) ? detail.assets as Row[] : []; const summary = (detail.author_summary ?? {}) as Row; const isPending = text(report.status) === 'pending';
  return <><div className="detail-heading"><div><span className="eyebrow">举报审核工作台</span><h3>{text(report.target_title)}</h3><p>{text(report.author_name)} · {dateTime(report.created_at)}</p></div><Status value={text(report.status)} /></div><section className="moderation-evidence"><span>举报原因</span><strong>{text(report.reason)}</strong><p>{text(report.detail, '提交人没有补充说明。')}</p></section><section className="review-content"><span>被举报内容</span><p>{text(report.target_content, '内容已删除或不可读取。')}</p>{assets.length > 0 && <div className="review-assets">{assets.map((asset) => <span key={text(asset.id)}><FileText size={13} />{text(asset.file_name)}</span>)}</div>}</section><div className="community-risk-grid"><span><b>{number(summary.pending_reports)}</b>未结举报</span><span><b>{number(summary.reviewed_reports)}</b>已处置</span><span><b>{number(summary.warning_count)}</b>警告记录</span><span><b>{number(summary.total_reports)}</b>累计举报</span></div>{isPending && canModerate && <section className="review-action-stack"><span>建议动作</span><div>{text(report.target_status) === 'hidden' ? <button className="quiet-button" onClick={() => void onReview(report, 'restore')}>恢复内容</button> : <button className="primary-button" onClick={() => void onReview(report, 'hide')}>隐藏内容</button>}<button className="quiet-button" onClick={() => void onReview(report, 'warn')}>发送警告</button><button className="danger-button" onClick={() => void onReview(report, 'disable_author')}>禁用作者</button><button className="text-button" onClick={() => void onReview(report, 'none')}>忽略举报</button></div></section>}<h4>同一内容的举报轨迹</h4><Timeline rows={priorReports} label={(entry) => `${text(entry.reason)} · ${text(entry.status)} · ${dateTime(entry.created_at)}`} /><h4>处置记录</h4><Timeline rows={history} label={(entry) => `${text(entry.actor_name, '系统')}：${text(entry.action_type)} · ${text(entry.reason)} · ${dateTime(entry.created_at)}`} /></>;
}

function VerificationReviewDetail({ detail, canVerify, onReview }: { detail: Row; canVerify: boolean; onReview: (item: Row, status: 'verified' | 'rejected') => Promise<void> }) {
  const profile = (detail.profile ?? {}) as Row; const posts = Array.isArray(detail.recent_posts) ? detail.recent_posts as Row[] : []; const history = Array.isArray(detail.history) ? detail.history as Row[] : []; const summary = (detail.summary ?? {}) as Row;
  return <><div className="detail-heading"><div><span className="eyebrow">专业认证核验</span><h3>{text(profile.display_name)}</h3><p>{text(profile.organization, '未填写机构')} · {text(profile.region, '未填写地区')}</p></div><Status value={text(profile.verification_status)} /></div><dl className="fact-list"><div><dt>身份类型</dt><dd>{text(profile.identity_type)}</dd></div><div><dt>从业年限</dt><dd>{number(profile.years_experience)} 年</dd></div><div><dt>专长标签</dt><dd>{Array.isArray(profile.expertise_tags) ? profile.expertise_tags.join(' · ') : '未填写'}</dd></div></dl><section className="moderation-evidence"><span>个人简介</span><p>{text(profile.bio, '未填写简介')}</p></section><div className="community-risk-grid"><span><b>{number(summary.post_count)}</b>发布内容</span><span><b>{number(summary.hidden_post_count)}</b>已隐藏</span><span><b>{number(summary.deleted_post_count)}</b>已删除</span></div>{text(profile.verification_status) === 'pending' && canVerify && <div className="review-action-stack"><span>审核决定</span><div><button className="primary-button" onClick={() => void onReview(profile, 'verified')}>通过认证</button><button className="quiet-button" onClick={() => void onReview(profile, 'rejected')}>驳回申请</button></div></div>}<h4>最近社区内容</h4><Timeline rows={posts} label={(entry) => `${text(entry.title)} · ${text(entry.status)} · ${dateTime(entry.created_at)}`} /><h4>认证记录</h4><Timeline rows={history} label={(entry) => `${text(entry.actor_name, '系统')}：${text(entry.action_type)} · ${text(entry.reason)} · ${dateTime(entry.created_at)}`} /></>;
}

function PostReviewDetail({ detail, canModerate, onUpdate }: { detail: Row; canModerate: boolean; onUpdate: (item: Row, status: 'published' | 'hidden' | 'deleted') => Promise<void> }) {
  const post = (detail.post ?? {}) as Row; const tags = Array.isArray(detail.tags) ? detail.tags as Row[] : []; const history = Array.isArray(detail.history) ? detail.history as Row[] : []; const reports = (detail.reports_summary ?? {}) as Row; const status = text(post.status);
  return <><div className="detail-heading"><div><span className="eyebrow">内容处置工作台</span><h3>{text(post.title)}</h3><p>{text(post.author_name)} · {dateTime(post.created_at)}</p></div><Status value={status} /></div><div className="review-tags">{tags.map((tag) => <span key={text(tag.id)}>#{text(tag.name)}</span>)}</div><section className="review-content"><span>帖子正文</span><p>{text(post.content_markdown, '暂无正文')}</p></section><div className="community-risk-grid"><span><b>{number(reports.pending)}</b>未结举报</span><span><b>{number(reports.reviewed)}</b>已处置</span><span><b>{number(post.comment_count)}</b>评论</span></div>{canModerate && <div className="review-action-stack"><span>内容状态</span><div>{status === 'published' && <><button className="primary-button" onClick={() => void onUpdate(post, 'hidden')}>隐藏帖子</button><button className="danger-button" onClick={() => void onUpdate(post, 'deleted')}>删除帖子</button></>}{status === 'hidden' && <><button className="primary-button" onClick={() => void onUpdate(post, 'published')}>恢复发布</button><button className="danger-button" onClick={() => void onUpdate(post, 'deleted')}>删除帖子</button></>}{(status === 'deleted' || status === 'draft') && <p className="empty-note">该状态不允许在管理端直接变更。</p>}</div></div>}<h4>内容处置记录</h4><Timeline rows={history} label={(entry) => `${text(entry.actor_name, '系统')}：${text(entry.action_type)} · ${text(entry.reason)} · ${dateTime(entry.created_at)}`} /></>;
}

function TagGovernanceDialog({ request, candidates, onClose, onSubmit }: { request: TagGovernanceRequest; candidates: Row[]; onClose: () => void; onSubmit: (payload: { mode: 'rename' | 'merge'; tag: Row; name?: string; targetTagId?: string; reason: string }) => Promise<void> }) {
  const [name, setName] = useState(text(request.tag.name)); const [targetTagId, setTargetTagId] = useState(''); const [reason, setReason] = useState(''); const [error, setError] = useState(''); const isMerge = request.mode === 'merge';
  const submit = async (event: FormEvent) => { event.preventDefault(); if (reason.trim().length < 3) { setError('请填写至少 3 个字的治理理由'); return; } if (!isMerge && !name.trim()) { setError('标签名称不能为空'); return; } if (isMerge && !targetTagId) { setError('请选择目标标签'); return; } await onSubmit({ mode: request.mode, tag: request.tag, name: name.trim(), targetTagId, reason: reason.trim() }); };
  return <Modal title={isMerge ? '合并社区标签' : '重命名社区标签'} onClose={onClose}><form className="role-assignment-form tag-governance-form" onSubmit={submit}><div className="role-assignment-heading"><div className="role-assignment-avatar"><FolderTree size={19} /></div><div><span>标签治理</span><strong>#{text(request.tag.name)}</strong><small>{isMerge ? '原标签会合并到目标标签，关联帖子会自动保留。' : '名称变更会立即在社区中生效。'}</small></div></div>{isMerge ? <label className="role-reason-field">目标标签<select value={targetTagId} onChange={(event) => { setTargetTagId(event.target.value); setError(''); }}><option value="">选择目标标签</option>{candidates.filter((item) => text(item.id) !== text(request.tag.id)).map((item) => <option value={text(item.id)} key={text(item.id)}>#{text(item.name)} · {number(item.post_count)} 篇</option>)}</select></label> : <label className="role-reason-field">新标签名称<input autoFocus value={name} maxLength={80} onChange={(event) => { setName(event.target.value); setError(''); }} /></label>}<label className="role-reason-field">治理理由<textarea value={reason} minLength={3} required onChange={(event) => { setReason(event.target.value); setError(''); }} placeholder="说明本次标签治理的原因，系统会写入审计日志。" /></label>{error && <p className="form-error">{error}</p>}<footer className="modal-actions"><button className="quiet-button" type="button" onClick={onClose}>取消</button><button className={isMerge ? 'danger-confirm-button' : 'primary-button'}>{isMerge ? '确认合并' : '保存名称'}</button></footer></form></Modal>;
}

function DiagnosisPage({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [tab, setTab] = useState<'reviews' | 'quality' | 'jobs'>(() => {
    const initial = hashQuery('tab');
    return ['reviews', 'quality', 'jobs'].includes(initial) ? initial as 'reviews' | 'quality' | 'jobs' : 'reviews';
  });
  const [selected, setSelected] = useState(() => hashQuery('conversation_id'));
  const [sensitiveUnlocked, setSensitiveUnlocked] = useState(false);
  const [query, setQuery] = useState('');
  const [reviewStatus, setReviewStatus] = useState(() => {
    const initial = hashQuery('review_status');
    return ['all', 'unreviewed', 'draft', 'published'].includes(initial) ? initial : 'unreviewed';
  });
  const [riskFilter, setRiskFilter] = useState('');
  const [createdSince, setCreatedSince] = useState(() => ['today', '7d'].includes(hashQuery('created_since')) ? hashQuery('created_since') : '');
  const [jobStatus, setJobStatus] = useState(() => ['pending', 'running', 'completed', 'failed'].includes(hashQuery('job_status')) ? hashQuery('job_status') : '');
  const [page, setPage] = useState(1);
  const pageSize = 16;
  const canReview = hasPermission(session, 'diagnosis.review');
  const reviewPath = useMemo(() => {
    const params = new URLSearchParams({ status: reviewStatus, page: String(page), page_size: String(pageSize) });
    if (query.trim()) params.set('q', query.trim());
    if (riskFilter) params.set('risk_level', riskFilter);
    if (createdSince) params.set('created_since', createdSince);
    return `/diagnosis/reviews?${params.toString()}`;
  }, [createdSince, page, query, reviewStatus, riskFilter]);
  const overview = useResource<Row>(session, '/diagnosis/overview');
  const reviewsResource = useResource<ListResponse>(session, reviewPath, tab === 'reviews');
  const qualityResource = useResource<Row>(session, '/diagnosis/quality', tab === 'quality');
  const jobsResource = useResource<ListResponse>(session, `/multimodal-jobs${jobStatus ? `?status=${jobStatus}` : ''}`, tab === 'jobs');
  const detail = useResource<Row>(session, selected ? `/diagnosis/reviews/${selected}${sensitiveUnlocked ? '?include_sensitive=true' : ''}` : '/diagnosis/reviews/not-selected', Boolean(selected));
  const rows = asItems(reviewsResource.data);
  const total = number(reviewsResource.data?.total);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const overviewSummary = (overview.data?.summary ?? {}) as Row;
  const overviewQuality = (overview.data?.quality ?? {}) as Row;
  const overviewMultimodal = (overview.data?.multimodal ?? {}) as Row;
  const attention = Array.isArray(overview.data?.attention) ? overview.data?.attention as Row[] : [];
  useEffect(() => { setPage(1); }, [query, reviewStatus, riskFilter, createdSince]);
  const selectConversation = (conversationId: string) => { setSensitiveUnlocked(false); setSelected(conversationId); };
  const refreshDiagnosis = () => { overview.reload(); reviewsResource.reload(); detail.reload(); };
  const grantAndLoad = async (workItemId?: string) => {
    if (!selected) return;
    const reason = await askReasonInDialog('查看问诊原文', { description: '原文、附件与多模态材料属于敏感业务数据；授权会在到期后自动失效。' });
    if (!reason) return;
    try {
      await api('/sensitive-access-grants', session, { method: 'POST', body: JSON.stringify({ resource_type: 'conversation', resource_id: selected, work_item_id: workItemId, reason }) });
      setSensitiveUnlocked(true);
      onToast('已获得临时原文查看权限');
    } catch (error) { onToast(error instanceof Error ? error.message : '授权失败'); }
  };
  const queueReview = async (conversationId: string, riskLevel: string) => {
    if (!canReview) { onToast('当前账号没有纳入专家复核队列的权限'); return; }
    const reason = await askReasonInDialog('纳入专家复核队列', { description: '该问诊会进入待办中心，领取、转派和发布都会留下审计记录。' });
    if (!reason) return;
    try {
      const result = await api<{ created: boolean }>(`/diagnosis/reviews/${conversationId}/queue`, session, { method: 'POST', body: JSON.stringify({ risk_level: ['low', 'medium', 'high', 'critical'].includes(riskLevel) ? riskLevel : 'medium', reason }) });
      onToast(result.created ? '已纳入专家复核队列' : '复核待办已更新');
      refreshDiagnosis();
    } catch (error) { onToast(error instanceof Error ? error.message : '纳入复核失败'); }
  };
  const saveReview = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    const publish = form.get('publish') === 'on';
    try {
      await api(`/diagnosis/reviews/${selected}`, session, { method: 'POST', body: JSON.stringify({ risk_level: form.get('risk_level'), conclusion: form.get('conclusion'), recommendation: form.get('recommendation'), evidence: [], publish, reason: form.get('reason') }) });
      onToast(publish ? '专家复核已发布，用户端可立即查看' : '专家复核草稿已保存');
      refreshDiagnosis();
    } catch (error) { onToast(error instanceof Error ? error.message : '保存失败'); }
  };
  return <>
    <PageHeader eyebrow="诊断运营" title="智能问诊" description="将高风险问诊纳入人工复核，发布意见后同步给用户，并把每一步保留为可追溯记录。" actions={<Tabs current={tab} onChange={setTab} values={[['reviews', '复核工作台'], ['quality', '回复质量'], ['jobs', '多模态材料']]} />} />
    {tab === 'reviews' && <section className="diagnosis-console">
      <section className="diagnosis-hero"><div><span>DIAGNOSIS DESK</span><h2>先看需要人工判断的问诊。</h2><p>纳入队列后由具备复核权限的专家领取处理；发布后的意见会自动回写用户端，并关闭相应待办。</p></div><div className="diagnosis-hero-actions"><button className="quiet-button" onClick={() => { window.location.hash = '/queue?resource_type=diagnosis_conversation&status=active'; }}><ClipboardCheck size={15} />复核待办</button><button className="quiet-button" onClick={refreshDiagnosis}><RefreshCcw size={15} />刷新</button></div></section>
      <section className="diagnosis-summary-grid" aria-label="问诊复核概览"><article><span>待复核或草稿</span><strong>{number(overviewSummary.awaiting_review)}</strong><small>需要确认结论或发布</small></article><article className="attention"><span>高风险未闭环</span><strong>{number(overviewSummary.high_risk_open)}</strong><small>高风险与紧急优先处理</small></article><article><span>复核待办</span><strong>{number(overviewSummary.queued_reviews)}</strong><small>已进入人工工作队列</small></article><article><span>近 24 小时材料失败</span><strong>{number(overviewMultimodal.failed_24h)}</strong><small>需检查模型或材料状态</small></article><article><span>今日已发布</span><strong>{number(overviewSummary.published_today)}</strong><small>已同步至用户端</small></article></section>
      {attention.length > 0 && <section className="diagnosis-attention-strip"><div><span>处理提示</span><strong>以下问诊仍需要人工关注</strong></div><div>{attention.slice(0, 4).map((item) => <button key={text(item.conversation_id)} onClick={() => selectConversation(text(item.conversation_id))}><Status value={text(item.risk_level)} /><span><strong>{text(item.title)}</strong><small>{text(item.user_name)} · {dateTime(item.last_message_at)}</small></span>{Boolean(item.has_failed_multimodal) && <AlertTriangle size={14} />}</button>)}</div></section>}
      <section className="diagnosis-review-workspace"><article className="diagnosis-list-panel"><header><div><span>复核队列</span><h3>按风险和处理状态排序</h3></div><b>{total}</b></header><div className="diagnosis-filter-bar"><label className="input-with-icon"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索问诊、摘要或用户" /></label><select value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value)}><option value="unreviewed">待复核</option><option value="draft">复核草稿</option><option value="published">已发布</option><option value="all">全部问诊</option></select><select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}><option value="">全部风险</option><option value="critical">紧急</option><option value="high">高风险</option><option value="medium">需关注</option><option value="low">低风险</option></select><select value={createdSince} onChange={(event) => setCreatedSince(event.target.value)}><option value="">全部时间</option><option value="today">今天</option><option value="7d">近 7 天</option></select></div><div className="diagnosis-result-bar"><span>共 {total} 条，第 {page} / {totalPages} 页</span><div><button className="quiet-button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button><button className="quiet-button" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>下一页</button></div></div><LoadingState loading={reviewsResource.loading} error={reviewsResource.error}><div className="diagnosis-review-list">{rows.length ? rows.map((item) => <article className={text(item.conversation_id) === selected ? 'selected' : ''} key={text(item.conversation_id)}><button className="diagnosis-review-main" onClick={() => selectConversation(text(item.conversation_id))}><div className="diagnosis-row-top"><Status value={text(item.risk_level)} />{text(item.review_status) !== '—' && <Status value={text(item.review_status)} />}{text(item.work_item_status) !== '—' && <span className="diagnosis-task-pill">{text(item.work_item_status) === 'claimed' ? `处理中 · ${text(item.work_item_assignee, '已领取')}` : '已纳入待办'}</span>}</div><strong>{text(item.title)}</strong><p>{text(item.summary, '未生成问诊摘要')}</p><small>{text(item.user_name)} · {number(item.message_count)} 条消息 · {number(item.attachment_count)} 份材料 · {dateTime(item.last_message_at)}</small>{(Boolean(item.has_ai_error) || Boolean(item.has_failed_multimodal)) && <span className="diagnosis-row-warning"><AlertTriangle size={12} />{Boolean(item.has_failed_multimodal) ? '多模态材料失败' : 'AI 回复异常'}</span>}</button><div className="diagnosis-row-actions">{text(item.work_item_status) === '—' && canReview && <button className="quiet-button" onClick={() => void queueReview(text(item.conversation_id), text(item.risk_level, 'medium'))}>纳入复核</button>}<button className="quiet-button" onClick={() => selectConversation(text(item.conversation_id))}>查看</button></div></article>) : <div className="diagnosis-empty"><Bot size={20} />当前筛选下没有问诊记录</div>}</div></LoadingState></article><aside className="diagnosis-detail-panel"><LoadingState loading={detail.loading} error={detail.error}>{detail.data ? <DiagnosisReviewDetail key={selected} detail={detail.data} canReview={canReview} onGrant={grantAndLoad} onQueue={(riskLevel) => void queueReview(selected, riskLevel)} onSubmit={saveReview} /> : <EmptySelection text="选择一条问诊后，可先查看脱敏摘要；需要读取原文与附件时再申请临时授权。" />}</LoadingState></aside></section>
    </section>}
    {tab === 'quality' && <section className="diagnosis-console"><section className="diagnosis-hero compact"><div><span>RESPONSE QUALITY</span><h2>把失败和反馈变成下一次改进。</h2><p>只统计业务结果，不读取用户原文；需要逐条复核时回到复核工作台申请临时授权。</p></div><div className="diagnosis-hero-actions"><button className="quiet-button" onClick={qualityResource.reload}><RefreshCcw size={15} />刷新</button></div></section><LoadingState loading={qualityResource.loading} error={qualityResource.error}><QualityPanel data={qualityResource.data ?? {}} overviewQuality={overviewQuality} /></LoadingState></section>}
    {tab === 'jobs' && <section className="diagnosis-console"><section className="diagnosis-hero compact"><div><span>MULTIMODAL TRACE</span><h2>材料直接进入模型，异常必须可定位。</h2><p>这里追踪图片、视频和文档的直接材料分析状态；失败记录保留模型、时间与错误信息，便于定位配置或材料问题。</p></div><div className="diagnosis-hero-actions"><select value={jobStatus} onChange={(event) => setJobStatus(event.target.value)}><option value="">全部状态</option><option value="running">运行中</option><option value="pending">等待中</option><option value="completed">已完成</option><option value="failed">失败</option></select><button className="quiet-button" onClick={jobsResource.reload}><RefreshCcw size={15} />刷新</button></div></section><LoadingState loading={jobsResource.loading} error={jobsResource.error}><MultimodalJobsPanel rows={asItems(jobsResource.data)} onOpen={(conversationId) => { setTab('reviews'); selectConversation(conversationId); }} /></LoadingState></section>}
  </>;
}

function DiagnosisReviewDetail({ detail, canReview, onGrant, onQueue, onSubmit }: { detail: Row; canReview: boolean; onGrant: (workItemId?: string) => void; onQueue: (riskLevel: string) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const conversation = (detail.conversation ?? {}) as Row;
  const messages = Array.isArray(detail.messages) ? detail.messages as Row[] : [];
  const reviews = Array.isArray(detail.expert_reviews) ? detail.expert_reviews as Row[] : [];
  const analyses = Array.isArray(detail.multimodal_analyses) ? detail.multimodal_analyses as Row[] : [];
  const reviewTask = (detail.review_task ?? null) as Row | null;
  const latestReview = reviews[0];
  const defaultRisk = text(latestReview?.risk_level, 'medium');
  return <div className="diagnosis-detail"><div className="diagnosis-detail-heading"><div><span>问诊复核</span><h3>{text(conversation.title)}</h3><p>{text(conversation.user_name)} · 最后更新 {dateTime(conversation.last_message_at)}</p></div><Status value={detail.sensitive ? '已解锁原文' : '脱敏模式'} /></div>{reviewTask ? <section className="diagnosis-task-summary"><div><span>当前复核待办</span><strong>{text(reviewTask.assignee_name, text(reviewTask.status) === 'claimed' ? '已领取' : '待领取')}</strong><small>{text(reviewTask.status) === 'claimed' ? '处理中' : '等待专家领取'} · 截止 {dateTime(reviewTask.due_at)}</small></div><Status value={text(reviewTask.priority)} /></section> : <section className="diagnosis-task-summary vacant"><div><span>当前复核待办</span><strong>尚未纳入人工队列</strong><small>确认需要专家处理后再创建待办，避免所有问诊都进入人工处理。</small></div>{canReview && <button className="quiet-button" onClick={() => onQueue(defaultRisk)}>纳入复核</button>}</section>}{!detail.sensitive && <button className="quiet-button wide" onClick={() => onGrant(reviewTask ? text(reviewTask.id) : undefined)}><LockKeyhole size={15} />申请查看原文与材料</button>}<section className="diagnosis-detail-section"><header><span>对话摘要</span><small>{detail.sensitive ? '已授权查看原文' : '用户内容已脱敏'}</small></header><div className="review-transcript">{messages.map((message) => { const files = Array.isArray(message.files) ? message.files as Row[] : []; return <article className={`transcript-message ${text(message.sender_type)}`} key={text(message.id)}><small>{text(message.sender_type) === 'assistant' ? 'CanW 助手' : '用户'} · {dateTime(message.created_at)}</small><p>{text(message.content)}</p>{files.length > 0 && <div className="transcript-files">{files.map((file) => <span key={text(file.id)}>{text(file.name)}</span>)}</div>}</article>; })}</div></section><section className="diagnosis-detail-section"><header><span>多模态材料</span><small>{analyses.length} 条分析记录</small></header>{analyses.length ? <div className="diagnosis-analysis-list">{analyses.map((analysis) => <article key={text(analysis.id)}><div><Status value={text(analysis.status)} /><strong>{text(analysis.model_id, '未记录模型')}</strong><small>{dateTime(analysis.updated_at)}</small></div><p>{text(analysis.status) === 'failed' ? text(analysis.error_message, '未记录失败原因') : text(analysis.analysis_text, '已完成直接材料分析')}</p></article>)}</div> : <p className="empty-note">该问诊没有上传多模态材料。</p>}</section><section className="diagnosis-detail-section"><header><span>专家复核版本</span><small>{reviews.length ? `已有 ${reviews.length} 个版本` : '尚无复核意见'}</small></header>{reviews.length ? <div className="diagnosis-review-history">{reviews.map((review) => <article key={text(review.id)}><div><Status value={text(review.status)} /><Status value={text(review.risk_level)} /><small>v{text(review.version)} · {text(review.reviewer_name_snapshot)} · {dateTime(review.published_at ?? review.created_at)}</small></div><strong>{text(review.conclusion)}</strong><p>{text(review.recommendation)}</p></article>)}</div> : <p className="empty-note">尚未创建专家复核。</p>}</section>{canReview ? <form className="review-form diagnosis-review-form" onSubmit={onSubmit}><header><div><span>专家复核</span><h4>{latestReview && text(latestReview.status) === 'draft' ? '继续编辑草稿' : '新增复核版本'}</h4></div><label className="publish-switch"><input name="publish" type="checkbox" defaultChecked />保存后发布给用户</label></header><label>风险等级<select name="risk_level" defaultValue={defaultRisk}><option value="low">低风险</option><option value="medium">需关注</option><option value="high">高风险</option><option value="critical">紧急</option></select></label><label>复核结论<textarea name="conclusion" minLength={3} required defaultValue={text(latestReview?.status) === 'draft' ? text(latestReview?.conclusion, '') : ''} placeholder="明确说明判断依据、当前风险和需要重点观察的现象。" /></label><label>处置建议<textarea name="recommendation" minLength={3} required defaultValue={text(latestReview?.status) === 'draft' ? text(latestReview?.recommendation, '') : ''} placeholder="给出可执行、可验证的处置步骤与后续观察建议。" /></label><label>处理理由<input name="reason" minLength={3} required placeholder="会写入审计记录，方便后续追溯" /></label><button className="primary-button">保存复核意见</button></form> : <p className="diagnosis-readonly-note"><LockKeyhole size={15} />当前账号可查看问诊摘要，但没有发布专家复核的权限。</p>}</div>;
}

function QualityPanel({ data, overviewQuality }: { data: Row; overviewQuality: Row }) {
  const daily = Array.isArray(data.daily) ? data.daily as Row[] : [];
  const feedback = Array.isArray(data.feedback) ? data.feedback as Row[] : [];
  const summary = (data.summary ?? {}) as Row;
  return <div className="diagnosis-quality-layout"><section className="diagnosis-quality-metrics"><article><span>近 14 日回复</span><strong>{number(summary.assistant_messages)}</strong><small>模型成功与失败回复总量</small></article><article className="attention"><span>失败率</span><strong>{number(summary.failure_rate)}%</strong><small>{number(summary.failed_messages)} 条回复异常</small></article><article><span>用户反馈</span><strong>{number(summary.feedback_messages)}</strong><small>需要回看质量样本</small></article><article><span>近 7 日失败率</span><strong>{number(overviewQuality.failure_rate)}%</strong><small>用于观察短期波动</small></article></section><section className="quality-grid"><article className="panel"><PanelTitle icon={BarChart3} title="近 14 日回复质量" note="从真实消息状态和反馈元数据聚合" /><SimpleTable columns={['日期', '助手回复', '失败', '反馈']} rows={daily} render={(item) => [shortDate(item.day), number(item.assistant_messages), number(item.failed_messages), number(item.feedback_count)]} empty="暂无质量数据" /></article><article className="panel"><PanelTitle icon={HeartPulse} title="反馈分布" note="用于定位需要复核的对话样本" /><SimpleTable columns={['反馈类型', '数量']} rows={feedback} render={(item) => [text(item.feedback), number(item.count)]} empty="尚无用户反馈" /></article></section></div>;
}

function MultimodalJobsPanel({ rows, onOpen }: { rows: Row[]; onOpen: (conversationId: string) => void }) { return <article className="diagnosis-jobs-panel"><div className="diagnosis-jobs-head"><span>直接材料分析记录</span><small>图片、视频和文档由用户端上传后直接交给多模态模型处理。</small></div>{rows.length ? <div className="diagnosis-job-list">{rows.map((item) => <article key={text(item.id)}><div className="diagnosis-job-status"><Status value={text(item.status)} /><span>{number(item.file_count)} 份材料</span></div><div><strong>{text(item.conversation_title, '已删除或未命名问诊')}</strong><p>{text(item.user_name)} · {text(item.model_id, '未记录模型')} · {dateTime(item.updated_at)}</p>{text(item.status) === 'failed' && <small className="diagnosis-job-error">{text(item.error_message, '未记录失败原因')}</small>}</div><button className="quiet-button" onClick={() => onOpen(text(item.conversation_id))}>查看问诊</button></article>)}</div> : <div className="diagnosis-empty"><FileText size={20} />当前筛选下没有多模态任务</div>}</article>; }

function HusbandryPage({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [selected, setSelected] = useState(() => hashQuery('case_id'));
  const [sensitiveUnlocked, setSensitiveUnlocked] = useState(false);
  const [query, setQuery] = useState('');
  const [caseStatus, setCaseStatus] = useState(() => ['all', 'open', 'needs_more_info', 'suspected', 'processing', 'closed'].includes(hashQuery('status')) ? hashQuery('status') : 'open');
  const [riskFilter, setRiskFilter] = useState(() => hashQuery('high_risk') === 'true' ? 'high_risk' : '');
  const [followUpFilter, setFollowUpFilter] = useState('');
  const [createdSince, setCreatedSince] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = 16;
  const canReview = hasPermission(session, 'husbandry.review');
  const listPath = `/husbandry/cases?status=${caseStatus}&page=${page}&page_size=${pageSize}${riskFilter === 'high_risk' ? '&high_risk=true' : riskFilter ? `&severity=${riskFilter}` : ''}${followUpFilter ? `&follow_up=${followUpFilter}` : ''}${createdSince ? `&created_since=${createdSince}` : ''}${query.trim() ? `&q=${encodeURIComponent(query.trim())}` : ''}`;
  const overview = useResource<Row>(session, '/husbandry/overview');
  const resource = useResource<ListResponse>(session, listPath);
  const detail = useResource<Row>(session, selected ? `/husbandry/cases/${selected}${sensitiveUnlocked ? '?include_sensitive=true' : ''}` : '/husbandry/cases/not-selected', Boolean(selected));
  const rows = asItems(resource.data);
  const total = number(resource.data?.total);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const overviewSummary = (overview.data?.summary ?? {}) as Row;
  const attention = Array.isArray(overview.data?.attention) ? overview.data?.attention as Row[] : [];
  const selectCase = (caseId: string) => { setSensitiveUnlocked(false); setSelected(caseId); };
  const refreshCases = () => { overview.reload(); resource.reload(); detail.reload(); };
  const grantAndLoad = async (workItemId?: string) => {
    if (!selected) return;
    const reason = await askReasonInDialog('查看病例原文与现场材料');
    if (!reason) return;
    try {
      await api('/sensitive-access-grants', session, { method: 'POST', body: JSON.stringify({ resource_type: 'husbandry_case', resource_id: selected, work_item_id: workItemId ?? null, reason }) });
      setSensitiveUnlocked(true);
      onToast('已获得病例原文查看权限');
    } catch (error) { onToast(error instanceof Error ? error.message : '授权失败'); }
  };
  const queueReview = async (caseId: string, riskLevel: string) => {
    const reason = await askReasonInDialog('纳入病例复核');
    if (!reason) return;
    try {
      const result = await api<Row>(`/husbandry/cases/${caseId}/queue`, session, { method: 'POST', body: JSON.stringify({ risk_level: riskLevel, reason }) });
      onToast(result.created ? '病例已纳入专家复核待办' : '已有待办，已同步风险等级');
      refreshCases();
    } catch (error) { onToast(error instanceof Error ? error.message : '纳入复核失败'); }
  };
  const saveReview = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
      const publish = form.get('publish') === 'on';
      try {
      const reviewHistory = Array.isArray(detail.data?.expert_reviews) ? detail.data.expert_reviews as Row[] : [];
      const evidence = (Array.isArray(detail.data?.assets) ? detail.data.assets as Row[] : []).slice(0, 12).map((asset) => ({ type: 'case_asset', asset_id: text(asset.id), file_name: text(asset.file_name), file_type: text(asset.file_type) }));
      await api(`/husbandry/cases/${selected}/review`, session, { method: 'POST', body: JSON.stringify({ expected_version: number(reviewHistory[0]?.version), risk_level: form.get('risk_level'), conclusion: form.get('conclusion'), recommendation: form.get('recommendation'), evidence, publish, reason: form.get('reason') }) });
      onToast(publish ? '复核意见已发布，病例已进入处理与随访阶段' : '病例复核草稿已保存');
      refreshCases();
    } catch (error) { onToast(error instanceof Error ? error.message : '保存失败'); }
  };
  return <>
    <PageHeader eyebrow="养殖风险与随访" title="养殖病例" description="从异常发现到专家处置、用户随访和病例结案，所有状态都在同一条可追溯链路中流转。" />
    <section className="case-console">
      <section className="case-hero"><div><span>CASE OPERATIONS</span><h2>把每一例异常带到可验证的结论。</h2><p>高风险病例自动进入专家待办；发布复核后病例转入处理中，用户完成随访并结案，管理端持续看见到期与缺失环节。</p></div><div className="case-hero-actions"><button className="quiet-button" onClick={() => { window.location.hash = '/queue?resource_type=husbandry_case&status=active'; }}><ClipboardCheck size={15} />病例待办</button><button className="quiet-button" onClick={refreshCases}><RefreshCcw size={15} />刷新</button></div></section>
      <section className="case-summary-grid" aria-label="病例运营概览"><article><span>处理中病例</span><strong>{number(overviewSummary.active_cases)}</strong><small>尚未由用户结案</small></article><article className="attention"><span>高风险未结案</span><strong>{number(overviewSummary.high_risk_open)}</strong><small>高风险与紧急优先处理</small></article><article><span>待专家判断</span><strong>{number(overviewSummary.awaiting_review)}</strong><small>尚无已发布意见</small></article><article className="warning"><span>到期随访</span><strong>{number(overviewSummary.follow_up_due)}</strong><small>需要回访确认处置效果</small></article><article><span>处理中未排随访</span><strong>{number(overviewSummary.follow_up_unscheduled)}</strong><small>发布意见后仍未约定下一次观察</small></article><article><span>近 7 日结案</span><strong>{number(overviewSummary.closed_7d)}</strong><small>用户已完成处理闭环</small></article></section>
      {attention.length > 0 && <section className="case-attention-strip"><div><span>优先处理</span><strong>风险、随访与待办中断点</strong></div><div>{attention.slice(0, 4).map((item) => <button key={text(item.case_id)} onClick={() => selectCase(text(item.case_id))}><Status value={text(item.severity)} /><span><strong>{text(item.title)}</strong><small>{text(item.farm_name)} · {text(item.batch_code, '未关联批次')} · 下次随访 {shortDate(item.next_follow_up_on)}</small></span>{text(item.work_item_status) !== '—' && <ClipboardCheck size={14} />}</button>)}</div></section>}
      <section className="case-review-workspace"><article className="case-list-panel"><header><div><span>病例队列</span><h3>按风险、随访和待办状态排序</h3></div><b>{total}</b></header><div className="case-filter-bar"><label className="input-with-icon"><Search size={15} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="搜索病例、养殖场、疑似疾病或用户" /></label><select value={caseStatus} onChange={(event) => { setCaseStatus(event.target.value); setPage(1); }}><option value="open">未结案</option><option value="needs_more_info">待补充</option><option value="suspected">疑似</option><option value="processing">处理中</option><option value="closed">已结案</option><option value="all">全部病例</option></select><select value={riskFilter} onChange={(event) => { setRiskFilter(event.target.value); setPage(1); }}><option value="">全部风险</option><option value="high_risk">高风险与紧急</option><option value="critical">紧急</option><option value="high">高风险</option><option value="medium">需关注</option><option value="low">低风险</option></select><select value={followUpFilter} onChange={(event) => { setFollowUpFilter(event.target.value); setPage(1); }}><option value="">全部随访</option><option value="due">已到期</option><option value="unscheduled">未排随访</option></select><select value={createdSince} onChange={(event) => { setCreatedSince(event.target.value); setPage(1); }}><option value="">全部时间</option><option value="today">今天</option><option value="7d">近 7 天</option></select></div><div className="case-result-bar"><span>共 {total} 例，第 {page} / {totalPages} 页</span><div><button className="quiet-button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button><button className="quiet-button" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>下一页</button></div></div><LoadingState loading={resource.loading} error={resource.error}><div className="case-review-list">{rows.length ? rows.map((item) => <article className={text(item.id) === selected ? 'selected' : ''} key={text(item.id)}><button className="case-review-main" onClick={() => selectCase(text(item.id))}><div className="case-row-top"><Status value={text(item.severity)} /><Status value={text(item.status)} />{text(item.review_status) !== '—' && <Status value={text(item.review_status)} />}{text(item.work_item_status) !== '—' && <span className="case-task-pill">{text(item.work_item_status) === 'claimed' ? `处理中 · ${text(item.work_item_assignee, '已领取')}` : '已纳入待办'}</span>}</div><strong>{text(item.title)}</strong><p>{text(item.suspected_disease, '尚未填写疑似疾病')} · {text(item.farm_name)} / {text(item.batch_code, '未关联批次')}</p><small>{text(item.user_name)} · 发生于 {shortDate(item.occurred_on)} · 下次随访 {shortDate(item.next_follow_up_on)}</small>{Boolean(item.follow_up_due) && <span className="case-row-warning"><Clock3 size={12} />随访已到期</span>}</button><div className="case-row-actions">{text(item.work_item_status) === '—' && text(item.status) !== 'closed' && canReview && <button className="quiet-button" onClick={() => void queueReview(text(item.id), text(item.severity, 'medium'))}>纳入复核</button>}<button className="quiet-button" onClick={() => selectCase(text(item.id))}>查看</button></div></article>) : <div className="case-empty"><HeartPulse size={20} />当前筛选下没有病例记录</div>}</div></LoadingState></article><aside className="case-detail-panel"><LoadingState loading={detail.loading} error={detail.error}>{detail.data ? <HusbandryDetail key={selected} detail={detail.data} canReview={canReview} onGrant={grantAndLoad} onQueue={(riskLevel) => void queueReview(selected, riskLevel)} onSubmit={saveReview} /> : <EmptySelection text="选择病例后先查看脱敏摘要；需要读取现场记录和附件时，再申请临时查看授权。" />}</LoadingState></aside></section>
    </section>
  </>;
}

function HusbandryDetail({ detail, canReview, onGrant, onQueue, onSubmit }: { detail: Row; canReview: boolean; onGrant: (workItemId?: string) => void; onQueue: (riskLevel: string) => void; onSubmit: (event: FormEvent<HTMLFormElement>) => void }) {
  const item = (detail.case ?? {}) as Row;
  const followUps = Array.isArray(detail.follow_ups) ? detail.follow_ups as Row[] : [];
  const assets = Array.isArray(detail.assets) ? detail.assets as Row[] : [];
  const reviews = Array.isArray(detail.expert_reviews) ? detail.expert_reviews as Row[] : [];
  const reviewTask = (detail.review_task ?? null) as Row | null;
  const latestReview = reviews[0];
  const defaultRisk = text(latestReview?.risk_level, text(item.severity, 'medium'));
  const isClosed = text(item.status) === 'closed';
  return <div className="case-detail"><div className="case-detail-heading"><div><span>病例复核</span><h3>{text(item.title)}</h3><p>{text(item.user_name)} · {text(item.farm_name)} · {text(item.batch_code, '未关联批次')}</p></div><div><Status value={text(item.status)} /><Status value={text(item.severity)} /></div></div>{reviewTask ? <section className="case-task-summary"><div><span>当前专家待办</span><strong>{text(reviewTask.assignee_name, text(reviewTask.status) === 'claimed' ? '已领取' : '待领取')}</strong><small>{text(reviewTask.status) === 'claimed' ? '正在复核' : '等待专家领取'} · 截止 {dateTime(reviewTask.due_at)}</small></div><Status value={text(reviewTask.priority)} /></section> : !isClosed && <section className="case-task-summary vacant"><div><span>当前专家待办</span><strong>尚未纳入人工队列</strong><small>普通病例可由运营或专家按需纳入；高风险病例会自动创建待办。</small></div>{canReview && <button className="quiet-button" onClick={() => onQueue(defaultRisk)}>纳入复核</button>}</section>}{!detail.sensitive && <button className="quiet-button wide" onClick={() => onGrant(reviewTask ? text(reviewTask.id) : undefined)}><LockKeyhole size={15} />申请查看原文与现场材料</button>}<section className="case-detail-section"><header><span>病例摘要</span><small>{detail.sensitive ? '已授权查看完整记录' : '用户内容已脱敏'}</small></header><dl className="case-fact-list"><div><dt>疑似疾病</dt><dd>{text(item.suspected_disease)}</dd></div><div><dt>发生时间</dt><dd>{shortDate(item.occurred_on)}</dd></div><div><dt>养殖批次</dt><dd>{text(item.batch_code, '未关联批次')} · {text(item.instar, '龄期未填')}</dd></div><div><dt>症状摘要</dt><dd>{text(item.symptom_summary)}</dd></div><div><dt>当前处置</dt><dd>{text(item.recommendation)}</dd></div></dl>{text(item.source_conversation_id) !== '—' && <button className="case-source-link" onClick={() => { window.location.hash = `/diagnosis?conversation_id=${text(item.source_conversation_id)}`; }}><MessageSquare size={14} />查看来源问诊</button>}</section><section className="case-detail-section"><header><span>随访轨迹</span><small>{followUps.length ? `${followUps.length} 次观察` : '尚未记录'}</small></header>{followUps.length ? <div className="case-follow-up-list">{followUps.map((followUp) => <article key={text(followUp.id)}><span /><div><strong>{shortDate(followUp.observed_on)}</strong><p>{text(followUp.action_taken, '未记录处置')} · {text(followUp.note, '未补充观察情况')}</p><small>发病 {number(followUp.affected_count)} · 新增死亡 {number(followUp.death_count)} · 下次 {shortDate(followUp.next_follow_up_on)}</small></div></article>)}</div> : <p className="empty-note">发布意见后，请提醒用户记录处置结果并安排下一次随访。</p>}</section><section className="case-detail-section"><header><span>现场材料</span><small>{assets.length} 份</small></header>{assets.length ? <div className="case-material-list">{assets.map((asset) => <article key={text(asset.id)}><FileText size={15} /><span><strong>{text(asset.file_name)}</strong><small>{text(asset.file_type)} · {number(asset.file_size)} B</small></span></article>)}</div> : <p className="empty-note">该病例没有关联现场图片或视频。</p>}</section><section className="case-detail-section"><header><span>专家复核版本</span><small>{reviews.length ? `已有 ${reviews.length} 个版本` : '尚无复核意见'}</small></header>{reviews.length ? <div className="case-review-history">{reviews.map((review) => <article key={text(review.id)}><div><Status value={text(review.status)} /><Status value={text(review.risk_level)} /><small>v{text(review.version)} · {text(review.reviewer_name_snapshot)} · {dateTime(review.published_at ?? review.created_at)}</small></div><strong>{text(review.conclusion)}</strong><p>{text(review.recommendation)}</p></article>)}</div> : <p className="empty-note">尚未创建专家复核。</p>}</section>{canReview && !isClosed ? <form className="review-form case-review-form" onSubmit={onSubmit}><header><div><span>专家处置</span><h4>{latestReview && text(latestReview.status) === 'draft' ? '继续编辑草稿' : '新增复核版本'}</h4></div><label className="publish-switch"><input name="publish" type="checkbox" defaultChecked />保存后同步用户</label></header><label>风险等级<select name="risk_level" defaultValue={defaultRisk}><option value="low">低风险</option><option value="medium">需关注</option><option value="high">高风险</option><option value="critical">紧急</option></select></label><label>复核结论<textarea name="conclusion" minLength={3} required defaultValue={text(latestReview?.status) === 'draft' ? text(latestReview?.conclusion, '') : ''} placeholder="说明判断依据、当前风险和需要持续观察的信号。" /></label><label>处置建议<textarea name="recommendation" minLength={3} required defaultValue={text(latestReview?.status) === 'draft' ? text(latestReview?.recommendation, '') : ''} placeholder="给出可执行的处置步骤，并明确下次随访要记录什么。" /></label><label>处理理由<input name="reason" minLength={3} required placeholder="会写入审计记录，方便追溯" /></label><button className="primary-button">保存专家意见</button></form> : <p className="case-readonly-note"><CheckCircle2 size={15} />{isClosed ? '该病例已由用户结案，历史记录仍可回看。' : '当前账号可查看病例摘要，但没有发布专家意见的权限。'}</p>}</div>;
}

function KnowledgePage({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  void session;
  void onToast;
  return <><PageHeader eyebrow="能力规划" title="知识中心暂未启用" description="真实 RAG、知识图谱、诊断证据链与长期记忆已明确延期；在能力落地前，管理端不会创建或索引任何知识源。" /><article className="panel full-panel"><EmptySelection text="知识源管理将在真实检索、版本治理和引用链路一并完成后开放。" /></article></>;
}

function ModelsPage({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [tab, setTab] = useState<'models' | 'jobs'>(() => hashQuery('tab') === 'jobs' ? 'jobs' : 'models'); const [open, setOpen] = useState(false); const resource = useResource<ListResponse>(session, tab === 'models' ? '/models' : '/jobs');
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); try { await api('/models', session, { method: 'POST', body: JSON.stringify({ key: form.get('key'), label: form.get('label'), model_id: form.get('model_id'), api_base_url: form.get('api_base_url'), api_key: form.get('api_key') || null, capability: form.get('capability'), enabled: true, reason: form.get('reason') }) }); setOpen(false); onToast('平台级模型已保存，密钥不会回显'); resource.reload(); } catch (error) { onToast(error instanceof Error ? error.message : '保存失败'); } };
  const patchJob = async (item: Row, action: 'retry' | 'cancel') => { const reason = await askReasonInDialog(action === 'retry' ? '重试任务' : '取消任务'); if (!reason) return; try { await api(`/jobs/${text(item.id)}`, session, { method: 'PATCH', body: JSON.stringify({ action, reason }) }); onToast('任务状态已更新'); resource.reload(); } catch (error) { onToast(error instanceof Error ? error.message : '操作失败'); } };
  const testModel = async (item: Row) => { const reason = await askReasonInDialog('测试系统模型连通性'); if (!reason) return; try { const result = await api<Row>(`/models/${text(item.id)}/test`, session, { method: 'POST', body: JSON.stringify({ reason }) }); onToast(text(result.last_test_status) === 'passed' ? '模型接口连通' : `模型测试失败：${text(result.last_test_message)}`); resource.reload(); } catch (error) { onToast(error instanceof Error ? error.message : '模型测试失败'); } };
  return <><PageHeader eyebrow="平台能力" title="模型与任务" description="系统模型与异步任务与用户自定义模型隔离，管理端不会读取用户 API Key。" actions={<Tabs current={tab} onChange={setTab} values={[['models', '系统模型'], ['jobs', '后台任务']]} />} />{tab === 'models' && <button className="primary-button page-float-action" onClick={() => setOpen(true)}><Plus size={16} />添加系统模型</button>}<article className="panel full-panel"><LoadingState loading={resource.loading} error={resource.error}>{tab === 'models' ? <SimpleTable columns={['名称', '模型 ID', '能力', '密钥', '状态', '最近测试', '操作']} rows={asItems(resource.data)} render={(item) => [<div key="label"><strong>{text(item.label)}</strong><small>{text(item.key)}</small></div>, text(item.model_id), text(item.capability), item.has_api_key ? '已配置' : '未配置', <Status key="status" value={item.enabled ? 'enabled' : 'disabled'} />, text(item.last_test_status), <button key="test" onClick={() => void testModel(item)}>测试</button>]} empty="尚未配置平台级模型" /> : <SimpleTable columns={['任务', '状态', '进度', '错误', '操作']} rows={asItems(resource.data)} render={(item) => [text(item.job_type), <Status key="status" value={text(item.status)} />, `${number(item.progress)}%`, text(item.error_message), <div className="row-actions" key="action">{text(item.status) === 'failed' && <button onClick={() => void patchJob(item, 'retry')}>重试</button>}{['queued', 'running'].includes(text(item.status)) && <button className="danger" onClick={() => void patchJob(item, 'cancel')}>取消</button>}</div>]} empty="没有后台任务" />}</LoadingState></article>{open && <Modal title="添加系统模型" onClose={() => setOpen(false)}><form className="form-grid" onSubmit={submit}><label>内部标识<input name="key" required placeholder="vision-primary" /></label><label>显示名称<input name="label" required /></label><label>模型 ID<input name="model_id" required /></label><label>API 地址<input name="api_base_url" required type="url" /></label><label>能力<select name="capability"><option value="chat">对话</option><option value="vision">视觉</option><option value="embedding">嵌入</option><option value="speech">语音</option></select></label><label>API Key（仅写入）<input name="api_key" type="password" /></label><label>保存理由<input name="reason" required minLength={3} /></label><button className="primary-button">保存模型</button></form></Modal>}</>;
}

function OperationsPage({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [tab, setTab] = useState<'analytics' | 'assets' | 'risk' | 'health'>(() => {
    const requested = hashQuery('tab');
    return requested === 'assets' || requested === 'risk' || requested === 'health' ? requested : 'analytics';
  });
  const [analyticsDays, setAnalyticsDays] = useState(14);
  const resource = useResource<Row>(session, `/analytics/overview?days=${analyticsDays}`, tab === 'analytics');
  return <><PageHeader eyebrow="运营数据与安全" title="数据与安全" description="数据分析坚持脱敏与聚合；风险页只展示需要管理员处置的登录、权限、敏感操作、服务与运营异常，普通举报和病例待办请在业务模块处理。" actions={<Tabs current={tab} onChange={setTab} values={[['analytics', '运营分析'], ['assets', '文件资产'], ['risk', '风险事件'], ['health', '服务健康']]} />} />
    {tab === 'risk' ? <RiskPanel session={session} onToast={onToast} /> : tab === 'analytics' ? <LoadingState loading={resource.loading} error={resource.error}><AnalyticsPanel data={resource.data as Row} session={session} days={analyticsDays} onDaysChange={setAnalyticsDays} /></LoadingState> : tab === 'assets' ? <article className="panel full-panel"><AssetsPanel session={session} onToast={onToast} /></article> : <HealthPanel session={session} onToast={onToast} />}
  </>;
}

type RiskAction = 'acknowledge' | 'start' | 'claim' | 'release' | 'resolve' | 'dismiss' | 'suppress' | 'reopen' | 'assign' | 'note';

function RiskPanel({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [scope, setScope] = useState<'active' | 'all' | 'archive'>('active');
  const [priority, setPriority] = useState('');
  const [assignee, setAssignee] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [actionTarget, setActionTarget] = useState<{ incident: Row; action: RiskAction } | null>(null);
  const [actionError, setActionError] = useState('');
  const [actionSaving, setActionSaving] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [rulesSaving, setRulesSaving] = useState(false);
  const [rulesError, setRulesError] = useState('');
  const canManage = hasPermission(session, 'security.manage');
  const path = useMemo(() => {
    const params = new URLSearchParams({ scope });
    if (priority) params.set('priority', priority);
    if (assignee) params.set('assignee', assignee);
    return `/risk-events?${params.toString()}`;
  }, [assignee, priority, scope]);
  const resource = useResource<Row>(session, path);
  const items = Array.isArray(resource.data?.items) ? resource.data.items as Row[] : [];
  const selectedPresent = items.some((item) => text(item.id) === selectedId);
  useEffect(() => { if (!selectedPresent) setSelectedId(items.length ? text(items[0].id) : ''); }, [items.length, selectedPresent]);
  const detail = useResource<Row>(session, selectedId ? `/risk-events/${selectedId}` : '/risk-events/not-selected', Boolean(selectedId));
  const summary = (resource.data?.summary ?? {}) as Row;
  const notifications = (resource.data?.notifications ?? {}) as Row;
  const notificationItems = Array.isArray(notifications.items) ? notifications.items as Row[] : [];
  const trends = Array.isArray(resource.data?.trends) ? resource.data.trends as Row[] : [];
  const topTypes = Array.isArray(resource.data?.top_types) ? resource.data.top_types as Row[] : [];
  const assignees = Array.isArray(resource.data?.assignees) ? resource.data.assignees as Row[] : [];
  const rules = (resource.data?.rules ?? {}) as Row;
  const incident = (detail.data?.incident ?? {}) as Row;
  const evidence = Array.isArray(detail.data?.evidence) ? detail.data.evidence as Row[] : [];
  const timeline = Array.isArray(detail.data?.timeline) ? detail.data.timeline as Row[] : [];
  const maxTrend = Math.max(1, ...trends.map((item) => number(item.total)));
  const actionCopy: Record<RiskAction, { title: string; confirm: string; description: string; needsNote?: boolean }> = {
    acknowledge: { title: '确认风险', confirm: '确认已知悉', description: '确认后仍会保留在处置队列，直到完成闭环。' },
    start: { title: '开始处置', confirm: '开始处置', description: '将事件标为处理中，便于团队识别当前进展。' },
    claim: { title: '领取风险', confirm: '领取并开始处置', description: '领取后会把当前管理员设为负责人，并进入处理中状态。' },
    release: { title: '释放负责人', confirm: '释放负责人', description: '释放后事件回到待分配状态，处理记录会被保留。' },
    resolve: { title: '标记风险已解决', confirm: '确认解决', description: '请记录实际处置结果，便于后续复盘与同类事件判断。', needsNote: true },
    dismiss: { title: '忽略风险', confirm: '确认忽略', description: '仅用于确认不构成风险或已由其它渠道完成处置的事件。', needsNote: true },
    suppress: { title: '抑制同类提醒', confirm: '开始抑制', description: '在指定窗口内不再提醒这一稳定指纹的同类信号；不会删除事件和审计记录。', needsNote: true },
    reopen: { title: '重新打开风险', confirm: '重新打开', description: '重新打开后会重新计算该事件的 SLA 截止时间。' },
    assign: { title: '指派负责人', confirm: '保存负责人', description: '仅可指派给当前可用的管理人员，所有变更会进入处置时间线。' },
    note: { title: '补充处置备注', confirm: '保存备注', description: '备注会形成独立的处置节点，不会改变事件状态。', needsNote: true },
  };
  const openAction = (nextAction: RiskAction) => { if (!selectedId) return; const target = items.find((item) => text(item.id) === selectedId) ?? incident; setActionTarget({ incident: target, action: nextAction }); setActionError(''); };
  const submitAction = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!actionTarget) return;
    const form = new FormData(event.currentTarget);
    const note = String(form.get('note') ?? '').trim();
    const selectedAction = actionTarget.action;
    if (actionCopy[selectedAction].needsNote && note.length < 3) { setActionError('请填写至少 3 个字的处置说明。'); return; }
    setActionSaving(true); setActionError('');
    try {
      await api(`/risk-events/${text(actionTarget.incident.id)}`, session, { method: 'PATCH', body: JSON.stringify({ action: selectedAction, note: note || null, assignee_id: form.get('assignee_id') || null, suppress_hours: form.get('suppress_hours') ? Number(form.get('suppress_hours')) : null }) });
      onToast(`${actionCopy[selectedAction].title}已记录`);
      setActionTarget(null); resource.reload(); detail.reload();
    } catch (error) { setActionError(error instanceof Error ? error.message : '风险事件更新失败'); } finally { setActionSaving(false); }
  };
  const openNotification = async (item: Row) => {
    setSelectedId(text(item.id));
    try { await api(`/risk-events/${text(item.id)}/notifications/read`, session, { method: 'POST' }); resource.reload(); } catch { /* Reading an alert must never block opening the incident. */ }
  };
  const goToRelated = (item: Row) => {
    const destination = (item.destination ?? {}) as Row;
    window.location.hash = text(destination.hash, '/operations');
  };
  const slaText = (item: Row) => {
    const state = text(item.sla_state);
    if (state === 'overdue') return 'SLA 已超时';
    if (state === 'due_soon') return `即将到期 · ${dateTime(item.due_at)}`;
    if (state === 'closed') return '已结束';
    return `SLA · ${dateTime(item.due_at)}`;
  };
  return <div className="risk-console">
    <section className="risk-hero">
      <div className="risk-hero-copy"><span className="eyebrow">incident command</span><h3>把信号变成有负责人、有时限的处置闭环。</h3><p>只聚合需要管理员关注的异常。系统用稳定指纹去重；确认、分派、抑制和解决都保留证据与时间线。</p></div>
      <div className="risk-hero-signal"><Siren size={19} /><span>需要响应</span><strong>{number(summary.active)}</strong><small>{number(summary.overdue)} 项超时 · {number(summary.unassigned)} 项待分配</small></div>
    </section>
    {number(notifications.unread_count) > 0 && <section className="risk-notice" aria-live="polite"><div><Bell size={17} /><span><strong>{number(notifications.unread_count)} 个高优先级风险需要查看</strong><small>点击卡片直接进入处置详情；阅读状态按管理员分别记录。</small></span></div><div className="risk-notice-list">{notificationItems.map((item) => <button type="button" onClick={() => void openNotification(item)} key={text(item.id)}><Status value={text(item.priority)} /><span>{text(item.subject)}</span><ArrowUpRight size={14} /></button>)}</div></section>}
    <section className="risk-summary-grid" aria-label="风险处置概览"><article><span>进行中风险</span><strong>{number(summary.active)}</strong><small>已去重后的唯一事件</small></article><article><span>紧急优先级</span><strong>{number(summary.critical)}</strong><small>需要优先协调处理</small></article><article><span>SLA 已超时</span><strong>{number(summary.overdue)}</strong><small>系统已自动上调一级优先级</small></article><article><span>抑制中的信号</span><strong>{number(summary.suppressed)}</strong><small>保留审计，不会丢失来源</small></article></section>
    <section className="risk-insight-grid"><article className="risk-trend-card"><header><div><span className="eyebrow">14 日复盘</span><h3>风险发现与闭环</h3></div><small>按首次发现日期聚合</small></header><div className="risk-trend-bars">{trends.map((item, index) => <div className="risk-trend-day" key={text(item.day)} title={`${shortDate(item.day)}：发现 ${number(item.total)}，紧急 ${number(item.critical)}，关闭 ${number(item.closed)}`}><i className="risk-trend-total" style={{ height: `${Math.max(4, number(item.total) / maxTrend * 100)}%` }} /><b className="risk-trend-critical" style={{ height: `${Math.max(2, number(item.critical) / maxTrend * 100)}%` }} />{(index === 0 || index === trends.length - 1 || index % 4 === 0) && <small>{shortDate(item.day).replace(/^\d{4}\//, '')}</small>}</div>)}</div><footer><span><i className="risk-total-dot" />新发现</span><span><i className="risk-critical-dot" />紧急</span></footer></article><article className="risk-type-card"><header><div><span className="eyebrow">近 30 日</span><h3>高频风险类型</h3></div></header><div>{topTypes.length ? topTypes.map((item) => <button type="button" key={text(item.type)} onClick={() => { setPriority(''); setScope('all'); }}><Status value={text(item.type)} /><strong>{number(item.total)}</strong><small>{number(item.active)} 项仍在处置</small></button>) : <p>尚未形成风险复盘样本。</p>}</div></article></section>
    <section className="risk-workspace">
      <article className="risk-list-panel"><header className="risk-list-header"><div><span className="eyebrow">处置队列</span><h3>{scope === 'active' ? '当前需要响应的风险' : scope === 'archive' ? '已结束与已抑制记录' : '全部风险记录'}</h3></div><div className="risk-list-actions"><button className="quiet-button" type="button" onClick={resource.reload}><RefreshCcw size={14} />刷新</button>{canManage && <button className="quiet-button" type="button" onClick={() => { setRulesOpen(true); setRulesError(''); }}><Settings size={14} />规则</button>}</div></header><div className="risk-filter-bar"><div className="segmented" aria-label="风险范围"><button className={scope === 'active' ? 'active' : ''} onClick={() => setScope('active')}>待处置</button><button className={scope === 'all' ? 'active' : ''} onClick={() => setScope('all')}>全部</button><button className={scope === 'archive' ? 'active' : ''} onClick={() => setScope('archive')}>归档</button></div><select value={priority} onChange={(event) => setPriority(event.target.value)}><option value="">全部优先级</option><option value="critical">紧急</option><option value="high">高风险</option><option value="medium">需关注</option><option value="low">低风险</option></select><select value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="">全部负责人</option><option value="mine">我负责的</option><option value="unassigned">待分配</option></select></div><LoadingState loading={resource.loading} error={resource.error}><div className="risk-list">{items.length ? items.map((item) => <button type="button" className={`risk-row${selectedId === text(item.id) ? ' selected' : ''}`} onClick={() => setSelectedId(text(item.id))} key={text(item.id)}><span className={`risk-row-severity ${text(item.priority)}`}><Siren size={15} /></span><span className="risk-row-copy"><span><Status value={text(item.type)} /><Status value={text(item.status)} /></span><strong>{text(item.subject)}</strong><small>{text(item.detail)}</small><em className={`risk-sla ${text(item.sla_state)}`}>{slaText(item)}</em></span><span className="risk-row-meta"><Status value={text(item.priority)} /><small>{text(item.assignee_name, '待分配')}</small></span></button>) : <EmptySelection text="当前范围内没有风险事件。系统会在达到规则阈值时自动生成并去重。" />}</div></LoadingState></article>
      <aside className="risk-detail-panel"><LoadingState loading={detail.loading} error={detail.error}>{selectedId && detail.data ? <><header className="risk-detail-heading"><div><span className="eyebrow">事件详情</span><h3>{text(incident.subject)}</h3><p>{text(incident.detail)}</p></div><div><Status value={text(incident.priority)} /><Status value={text(incident.status)} /></div></header><div className="risk-detail-actions"><button className="quiet-button" type="button" onClick={() => goToRelated(incident)}><ExternalLink size={14} />{text(((incident.destination ?? {}) as Row).label, '查看关联对象')}</button>{canManage && <button className="quiet-button" type="button" onClick={() => openAction('note')}><MessageCircleMore size={14} />写备注</button>}</div><dl className="risk-facts"><div><dt>当前负责人</dt><dd>{text(incident.assignee_name, '尚未分配')}</dd></div><div><dt>时效状态</dt><dd><span className={`risk-sla ${text(incident.sla_state)}`}>{slaText(incident)}</span></dd></div><div><dt>首次发现</dt><dd>{dateTime(incident.first_seen_at)}</dd></div><div><dt>最近信号</dt><dd>{dateTime(incident.last_detected_at)}</dd></div><div><dt>同类信号</dt><dd>{number(incident.detected_count)} 个来源证据</dd></div></dl>{canManage && <div className="risk-command-actions">{['open', 'acknowledged'].includes(text(incident.status)) && <button className="primary-button" type="button" onClick={() => openAction('claim')}><UserCheck size={15} />我来处理</button>}{text(incident.status) === 'open' && <button className="quiet-button" type="button" onClick={() => openAction('acknowledge')}>确认</button>}{['open', 'acknowledged', 'in_progress'].includes(text(incident.status)) && <><button className="quiet-button" type="button" onClick={() => openAction('assign')}><UserPlus size={15} />指派</button><button className="quiet-button" type="button" onClick={() => openAction('resolve')}><CheckCircle2 size={15} />解决</button><button className="quiet-button" type="button" onClick={() => openAction('suppress')}><Bell size={15} />抑制</button></>}{['resolved', 'dismissed', 'suppressed'].includes(text(incident.status)) && <button className="quiet-button" type="button" onClick={() => openAction('reopen')}><RotateCcw size={15} />重新打开</button>}</div>}<section className="risk-evidence"><h4>来源证据</h4>{evidence.length ? evidence.map((entry, index) => <div key={`${text(entry.label)}-${index}`}><span>{text(entry.label)}</span><strong>{text(entry.value)}</strong></div>) : <p>该事件暂无额外来源证据。</p>}</section><section className="risk-timeline"><h4>处置时间线</h4>{timeline.length ? timeline.map((entry) => <article key={text(entry.id)}><i /><div><strong>{text(entry.content)}</strong><small>{text(entry.actor_name, '系统')} · {dateTime(entry.created_at)}</small></div></article>) : <p>尚未记录人工处置。</p>}</section></> : <EmptySelection text="从左侧选择风险事件，即可查看证据、SLA 和完整处置时间线。" />}</LoadingState></aside>
    </section>
    {actionTarget && <Modal title={actionCopy[actionTarget.action].title} onClose={() => { if (!actionSaving) setActionTarget(null); }}><form className="risk-action-form" onSubmit={submitAction}><div className="risk-action-intro"><Siren size={18} /><span><strong>{text(actionTarget.incident.subject)}</strong>{actionCopy[actionTarget.action].description}</span></div>{actionTarget.action === 'assign' && <label>负责人<select name="assignee_id" defaultValue={text(actionTarget.incident.assignee_id, '')} required><option value="" disabled>选择负责人</option>{assignees.map((admin) => <option value={text(admin.id)} key={text(admin.id)}>{text(admin.display_name)} · {text(admin.email)}</option>)}</select></label>}{actionTarget.action === 'suppress' && <label>抑制时长<select name="suppress_hours" defaultValue={String(number(rules.suppression_default_hours) || 24)}><option value="4">4 小时</option><option value="12">12 小时</option><option value="24">24 小时</option><option value="72">72 小时</option></select></label>}<label>处置说明{actionCopy[actionTarget.action].needsNote ? '（必填）' : '（可选）'}<textarea name="note" minLength={actionCopy[actionTarget.action].needsNote ? 3 : undefined} placeholder={actionTarget.action === 'resolve' ? '说明已完成的处置和验证结果。' : actionTarget.action === 'dismiss' ? '说明为何判定该信号不构成风险。' : '补充本次操作的上下文。'} autoFocus={actionCopy[actionTarget.action].needsNote} /></label>{actionError && <p className="form-error">{actionError}</p>}<footer className="modal-actions"><button className="quiet-button" type="button" disabled={actionSaving} onClick={() => setActionTarget(null)}>取消</button><button className={actionTarget.action === 'dismiss' ? 'danger-button' : 'primary-button'} disabled={actionSaving}>{actionSaving ? '正在保存…' : actionCopy[actionTarget.action].confirm}</button></footer></form></Modal>}
    {rulesOpen && <RiskRulesDialog session={session} rules={rules} saving={rulesSaving} error={rulesError} onClose={() => { if (!rulesSaving) setRulesOpen(false); }} onSave={async (values, reason) => { setRulesSaving(true); setRulesError(''); try { await api('/risk-settings', session, { method: 'PUT', body: JSON.stringify({ value: values, reason }) }); onToast('风险规则已保存，新信号将按新规则检测'); setRulesOpen(false); resource.reload(); } catch (error) { setRulesError(error instanceof Error ? error.message : '风险规则保存失败'); } finally { setRulesSaving(false); } }} />}
  </div>;
}

function RiskRulesDialog({ session, rules, saving, error, onClose, onSave }: { session: AdminSession; rules: Row; saving: boolean; error: string; onClose: () => void; onSave: (values: Row, reason: string) => Promise<void> }) {
  void session;
  const inputValue = (key: string, fallback: number) => String(number(rules[key]) || fallback);
  const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); const numberField = (name: string) => Number(form.get(name)); await onSave({ login_failure_count: numberField('login_failure_count'), login_failure_window_hours: numberField('login_failure_window_hours'), unusual_ip_count: numberField('unusual_ip_count'), unusual_ip_window_hours: numberField('unusual_ip_window_hours'), report_surge_count: numberField('report_surge_count'), report_surge_window_hours: numberField('report_surge_window_hours'), posting_spike_count: numberField('posting_spike_count'), posting_spike_window_hours: numberField('posting_spike_window_hours'), critical_case_sla_hours: numberField('critical_case_sla_hours'), notification_window_minutes: numberField('notification_window_minutes'), suppression_default_hours: numberField('suppression_default_hours'), sla_hours: { critical: numberField('sla_critical'), high: numberField('sla_high'), medium: numberField('sla_medium'), low: numberField('sla_low') } }, String(form.get('reason') ?? '').trim()); };
  const sla = (rules.sla_hours ?? {}) as Row;
  return <Modal title="风险检测与 SLA 规则" onClose={onClose}><form className="risk-rules-form" onSubmit={submit}><p>规则只影响后续检测与事件时效；已生成风险的人工处置记录不会被覆盖。</p><fieldset><legend>异常阈值</legend><label>登录失败次数<input name="login_failure_count" type="number" min="1" max="100" defaultValue={inputValue('login_failure_count', 3)} required /></label><label>登录失败窗口（小时）<input name="login_failure_window_hours" type="number" min="1" max="720" defaultValue={inputValue('login_failure_window_hours', 24)} required /></label><label>异常 IP 数量<input name="unusual_ip_count" type="number" min="1" max="100" defaultValue={inputValue('unusual_ip_count', 3)} required /></label><label>异常 IP 窗口（小时）<input name="unusual_ip_window_hours" type="number" min="1" max="720" defaultValue={inputValue('unusual_ip_window_hours', 24)} required /></label><label>举报激增数量<input name="report_surge_count" type="number" min="1" max="100" defaultValue={inputValue('report_surge_count', 3)} required /></label><label>举报激增窗口（小时）<input name="report_surge_window_hours" type="number" min="1" max="720" defaultValue={inputValue('report_surge_window_hours', 24)} required /></label><label>异常发布数量<input name="posting_spike_count" type="number" min="1" max="100" defaultValue={inputValue('posting_spike_count', 5)} required /></label><label>异常发布窗口（小时）<input name="posting_spike_window_hours" type="number" min="1" max="720" defaultValue={inputValue('posting_spike_window_hours', 1)} required /></label></fieldset><fieldset><legend>提醒与时效</legend><label>紧急病例复核 SLA（小时）<input name="critical_case_sla_hours" type="number" min="1" max="720" defaultValue={inputValue('critical_case_sla_hours', 4)} required /></label><label>提醒聚合窗口（分钟）<input name="notification_window_minutes" type="number" min="1" max="1440" defaultValue={inputValue('notification_window_minutes', 30)} required /></label><label>默认抑制时长（小时）<input name="suppression_default_hours" type="number" min="1" max="720" defaultValue={inputValue('suppression_default_hours', 24)} required /></label><label>紧急 SLA（小时）<input name="sla_critical" type="number" min="1" max="720" defaultValue={String(number(sla.critical) || 4)} required /></label><label>高风险 SLA（小时）<input name="sla_high" type="number" min="1" max="720" defaultValue={String(number(sla.high) || 24)} required /></label><label>需关注 SLA（小时）<input name="sla_medium" type="number" min="1" max="720" defaultValue={String(number(sla.medium) || 72)} required /></label><label>低风险 SLA（小时）<input name="sla_low" type="number" min="1" max="720" defaultValue={String(number(sla.low) || 168)} required /></label></fieldset><label className="risk-rules-reason">保存理由<textarea name="reason" minLength={3} required placeholder="说明本次规则调整的业务或安全依据。" /></label>{error && <p className="form-error">{error}</p>}<footer className="modal-actions"><button className="quiet-button" type="button" disabled={saving} onClick={onClose}>取消</button><button className="primary-button" disabled={saving}>{saving ? '正在保存…' : '保存规则'}</button></footer></form></Modal>;
}

const assetTypeLabels: Record<string, string> = { image: '图片', video: '视频', document: '文档', audio: '音频', other: '其他' };

function formatBytes(value: unknown): string {
  const bytes = number(value);
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toLocaleString('zh-CN', { maximumFractionDigits: index ? 1 : 0 })} ${units[index]}`;
}

type AssetAction = 'preview' | 'quarantine' | 'restore' | 'delete';
type AssetPreview = { url: string; name: string; mimeType: string };

function AssetsPanel({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [query, setQuery] = useState('');
  const [owner, setOwner] = useState('');
  const [fileType, setFileType] = useState('all');
  const [assetStatus, setAssetStatus] = useState('all');
  const [createdFrom, setCreatedFrom] = useState('');
  const [createdTo, setCreatedTo] = useState('');
  const [page, setPage] = useState(1);
  const [assetAction, setAssetAction] = useState<{ item: Row; action: AssetAction } | null>(null);
  const [actionReason, setActionReason] = useState('');
  const [actionError, setActionError] = useState('');
  const [actionSaving, setActionSaving] = useState(false);
  const [preview, setPreview] = useState<AssetPreview | null>(null);
  const canManage = hasPermission(session, 'assets.manage');
  const path = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: '12', file_type: fileType, status: assetStatus });
    if (query.trim()) params.set('q', query.trim());
    if (owner.trim()) params.set('owner', owner.trim());
    if (createdFrom) params.set('created_from', createdFrom);
    if (createdTo) params.set('created_to', createdTo);
    return `/assets?${params.toString()}`;
  }, [assetStatus, createdFrom, createdTo, fileType, owner, page, query]);
  const resource = useResource<Row>(session, path);
  const items = Array.isArray(resource.data?.items) ? resource.data.items as Row[] : [];
  const summary = (resource.data?.summary ?? {}) as Row;
  const types = Array.isArray(resource.data?.types) ? resource.data.types as Row[] : [];
  const total = number(resource.data?.total);
  const pageSize = number(resource.data?.page_size) || 12;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const actionCopy: Record<AssetAction, { title: string; description: string; confirm: string }> = {
    preview: { title: '申请受控预览', description: '说明预览用途。系统将记录本次授权并在 15 分钟后失效。', confirm: '授权并预览' },
    quarantine: { title: '隔离文件', description: '文件会从常规访问中移除，保留记录与原始存储地址，之后可以恢复。', confirm: '确认隔离' },
    restore: { title: '恢复文件', description: '恢复后，文件会重新进入正常资产清单。', confirm: '恢复文件' },
    delete: { title: '删除文件', description: '这是软删除：文件将停止向业务端暴露，并进入待清理资产，之后可以恢复。', confirm: '确认删除' },
  };
  const openAction = (item: Row, action: AssetAction) => { setAssetAction({ item, action }); setActionReason(''); setActionError(''); };
  const closePreview = () => { if (preview) URL.revokeObjectURL(preview.url); setPreview(null); };
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url); }, [preview]);
  const submitAssetAction = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!assetAction || actionReason.trim().length < 3) { setActionError('请填写至少 3 个字的处理理由。'); return; }
    setActionSaving(true); setActionError('');
    try {
      const fileId = text(assetAction.item.id);
      if (assetAction.action === 'preview') {
        const grant = await api<Row>(`/assets/${fileId}/preview`, session, { method: 'POST', body: JSON.stringify({ reason: actionReason.trim() }) });
        const response = await fetch(`${API_BASE}${text(grant.content_path)}`, { headers: { Authorization: `Bearer ${session.access_token}` } });
        if (!response.ok) {
          const payload: unknown = await response.json().catch(() => null);
          throw new Error(responseMessage(payload));
        }
        const blob = await response.blob();
        setPreview({ url: URL.createObjectURL(blob), name: text(grant.file_name), mimeType: text(grant.mime_type, blob.type || 'application/octet-stream') });
        onToast('已授权受控预览；本次访问已写入审计日志');
      } else {
        await api(`/assets/${fileId}/lifecycle`, session, { method: 'PATCH', body: JSON.stringify({ action: assetAction.action, reason: actionReason.trim() }) });
        onToast(assetAction.action === 'quarantine' ? '文件已隔离' : assetAction.action === 'restore' ? '文件已恢复' : '文件已软删除，已进入待清理资产');
        resource.reload();
      }
      setAssetAction(null);
    } catch (error) { setActionError(error instanceof Error ? error.message : '文件处置失败'); } finally { setActionSaving(false); }
  };
  const resetFilters = () => { setQuery(''); setOwner(''); setFileType('all'); setAssetStatus('all'); setCreatedFrom(''); setCreatedTo(''); setPage(1); };
  const setFilter = (setter: (value: string) => void, value: string) => { setter(value); setPage(1); };
  const typeSummary = types.map((item) => `${assetTypeLabels[text(item.type)] ?? text(item.type)} ${number(item.count)}`).join(' · ') || '暂无可用资产';
  return <div className="asset-page">
    <section className="asset-hero"><div><span className="eyebrow">资产治理台</span><h3>文件留在平台，访问必须留下理由。</h3><p>从检索、状态处置到短时授权预览，所有操作以资产元数据为中心，并保留可审计记录。</p></div><div className="asset-hero-note"><PackageSearch size={18} /><span>{typeSummary}</span></div></section>
    <section className="asset-summary-grid"><article><span>管理中文件</span><strong>{number(summary.total_files).toLocaleString('zh-CN')}</strong><small>占用 {formatBytes(summary.total_bytes)}</small></article><article><span>正常可用</span><strong>{number(summary.normal_files).toLocaleString('zh-CN')}</strong><small>上传失败 {number(summary.failed_files)} 个</small></article><article><span>待治理项</span><strong>{(number(summary.orphaned_files) + number(summary.duplicate_files) + number(summary.stale_files)).toLocaleString('zh-CN')}</strong><small>孤立 {number(summary.orphaned_files)} · 重复 {number(summary.duplicate_files)} · 长期未用 {number(summary.stale_files)}</small></article><article><span>可回收空间</span><strong>{formatBytes(summary.reclaimable_bytes)}</strong><small>隔离 {number(summary.quarantined_files)} · 已删除 {number(summary.deleted_files)}</small></article></section>
    <section className="asset-governance-strip"><div><Archive size={16} /><span>大文件 <b>{number(summary.large_files)}</b></span></div><div><FileArchive size={16} /><span>孤立文件 <b>{number(summary.orphaned_files)}</b></span></div><div><AlertTriangle size={16} /><span>待处理上传失败 <b>{number(summary.failed_files)}</b></span></div><p>“已删除”保留为软删除状态，便于核查与恢复；待清理体积用于后续存储清理决策。</p></section>
    <section className="asset-ledger"><header className="asset-ledger-header"><div><span className="eyebrow">资产清单</span><h3>检索与处置</h3></div><button className="quiet-button" onClick={resource.reload}><RefreshCcw size={15} />刷新</button></header><div className="asset-filter-grid"><label className="input-with-icon asset-search"><Search size={15} /><input value={query} onChange={(event) => setFilter(setQuery, event.target.value)} placeholder="搜索文件名或上传者" /></label><label className="input-with-icon asset-owner"><Users size={14} /><input value={owner} onChange={(event) => setFilter(setOwner, event.target.value)} placeholder="筛选上传者" /></label><select value={fileType} onChange={(event) => setFilter(setFileType, event.target.value)}><option value="all">全部类型</option>{Object.entries(assetTypeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select><select value={assetStatus} onChange={(event) => setFilter(setAssetStatus, event.target.value)}><option value="all">全部状态</option><option value="normal">正常</option><option value="quarantined">已隔离</option><option value="deleted">已删除</option><option value="upload_failed">上传失败</option></select><label className="asset-date"><span>上传起始</span><input type="date" value={createdFrom} onChange={(event) => setFilter(setCreatedFrom, event.target.value)} /></label><label className="asset-date"><span>上传结束</span><input type="date" value={createdTo} onChange={(event) => setFilter(setCreatedTo, event.target.value)} /></label><button className="quiet-button asset-reset" type="button" onClick={resetFilters}>重置</button></div><LoadingState loading={resource.loading} error={resource.error}><SimpleTable columns={['文件', '类型 / 大小', '上传者', '生命周期', '治理提示', '操作']} rows={items} render={(item) => { const statusValue = text(item.asset_status); const governance = [number(item.reference_count) === 0 ? '孤立' : '', number(item.duplicate_count) > 0 ? `重复 ${number(item.duplicate_count)}` : '', item.is_large ? '大文件' : '', item.is_stale ? '长期未用' : ''].filter(Boolean); return [<div className="asset-name" key="name"><strong>{text(item.file_name)}</strong><small>{text(item.mime_type)} · {dateTime(item.created_at)}</small></div>, <div className="asset-type" key="type"><strong>{assetTypeLabels[text(item.file_type)] ?? text(item.file_type)}</strong><small>{formatBytes(item.file_size)}</small></div>, text(item.owner_name), <Status key="status" value={statusValue} />, <div className="asset-flags" key="flags">{governance.length ? governance.map((flag) => <span key={flag}>{flag}</span>) : <small>引用正常</small>}</div>, <div className="asset-row-actions" key="actions">{canManage && statusValue === 'normal' && <><button type="button" title="申请预览" aria-label={`申请预览 ${text(item.file_name)}`} onClick={() => openAction(item, 'preview')}><PlayCircle size={15} /></button><button type="button" title="隔离文件" aria-label={`隔离 ${text(item.file_name)}`} onClick={() => openAction(item, 'quarantine')}><Archive size={15} /></button><button className="danger" type="button" title="删除文件" aria-label={`删除 ${text(item.file_name)}`} onClick={() => openAction(item, 'delete')}><X size={15} /></button></>}{canManage && statusValue === 'quarantined' && <><button type="button" title="恢复文件" aria-label={`恢复 ${text(item.file_name)}`} onClick={() => openAction(item, 'restore')}><CheckCircle2 size={15} /></button><button className="danger" type="button" title="删除文件" aria-label={`删除 ${text(item.file_name)}`} onClick={() => openAction(item, 'delete')}><X size={15} /></button></>}{canManage && statusValue === 'deleted' && <button type="button" title="恢复文件" aria-label={`恢复 ${text(item.file_name)}`} onClick={() => openAction(item, 'restore')}><CheckCircle2 size={15} /></button>}{!canManage && <small>仅查看</small>}</div>]; }} empty="没有符合当前条件的文件资产" /></LoadingState><footer className="asset-pagination"><span>共 {total.toLocaleString('zh-CN')} 项，第 {Math.min(page, pages)} / {pages} 页</span><div><button className="quiet-button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button><button className="quiet-button" disabled={page >= pages} onClick={() => setPage((value) => Math.min(pages, value + 1))}>下一页</button></div></footer></section>
    {assetAction && <Modal title={actionCopy[assetAction.action].title} onClose={() => { if (!actionSaving) setAssetAction(null); }}><form className="asset-action-form" onSubmit={submitAssetAction}><div className={`asset-action-note ${assetAction.action}`}><FileText size={17} /><span><strong>{text(assetAction.item.file_name)}</strong>{actionCopy[assetAction.action].description}</span></div><label>处理理由<textarea value={actionReason} onChange={(event) => { setActionReason(event.target.value); setActionError(''); }} placeholder="说明业务原因，内容将写入审计日志。" minLength={3} required autoFocus /></label>{actionError && <p className="form-error">{actionError}</p>}<footer className="modal-actions"><button className="quiet-button" type="button" disabled={actionSaving} onClick={() => setAssetAction(null)}>取消</button><button className={assetAction.action === 'delete' ? 'danger-button' : 'primary-button'} disabled={actionSaving}>{actionSaving ? '正在处理…' : actionCopy[assetAction.action].confirm}</button></footer></form></Modal>}
    {preview && <Modal title={`受控预览 · ${preview.name}`} onClose={closePreview}><div className="asset-preview"><div className="asset-preview-warning"><ShieldCheck size={16} /><span>本次预览已授权并记录审计；请勿将内容用于授权范围外的用途。</span></div>{preview.mimeType.startsWith('image/') ? <img src={preview.url} alt={preview.name} /> : preview.mimeType.startsWith('video/') ? <video controls src={preview.url} /> : preview.mimeType.startsWith('audio/') ? <audio controls src={preview.url} /> : <iframe title={preview.name} src={preview.url} />}</div></Modal>}
  </div>;
}

const analyticsLabels: Record<string, string> = { diagnosis: '智能问诊', video: '视频咨询', general: '普通对话', low: '低风险', medium: '需关注', high: '高风险', critical: '紧急', experience: '经验分享', case: '病例分享', question: '问题求助', reference: '参考资料', announcement: '公告' };

function analyticsValue(value: unknown, unit = ''): string { return value === null || value === undefined ? '—' : `${number(value).toLocaleString('zh-CN', { maximumFractionDigits: 1 })}${unit}`; }

function AnalyticsBreakdown({ title, rows }: { title: string; rows: Row[] }) {
  const total = rows.reduce((sum, row) => sum + number(row.value), 0);
  return <section className="analytics-breakdown"><strong>{title}</strong>{rows.length ? <div>{rows.map((row) => <span key={text(row.label)}><em>{analyticsLabels[text(row.label)] ?? text(row.label)}</em><b>{number(row.value).toLocaleString('zh-CN')}</b><i style={{ width: `${total ? Math.max(8, number(row.value) / total * 100) : 0}%` }} /></span>)}</div> : <small>当天暂无该类数据</small>}</section>;
}

function AnalyticsPanel({ data, session, days, onDaysChange }: { data: Row; session: AdminSession; days: number; onDaysChange: (days: number) => void }) {
  const safeData = data ?? {};
  const series = Array.isArray(safeData.series) ? safeData.series as Row[] : [];
  const period = (safeData.period ?? {}) as Row;
  const summary = (safeData.summary ?? {}) as Row;
  const retention = (safeData.retention ?? {}) as Row;
  const efficiency = (safeData.efficiency ?? {}) as Row;
  const funnel = Array.isArray(safeData.funnel) ? safeData.funnel as Row[] : [];
  const [selectedDay, setSelectedDay] = useState('');
  const latestDay = text(period.to, '');
  const selectedExists = series.some((item) => text(item.day, '') === selectedDay);
  const drillDownDay = selectedExists ? selectedDay : latestDay;
  const drillDown = useResource<Row>(session, `/analytics/days/${drillDownDay}`, Boolean(drillDownDay));
  const drillSummary = (drillDown.data?.summary ?? {}) as Row;
  const breakdown = (drillDown.data?.breakdown ?? {}) as Row;
  const attention = (drillDown.data?.attention ?? {}) as Row;
  const maxTrendValue = Math.max(1, ...series.flatMap((item) => ['users', 'conversations', 'cases', 'posts'].map((key) => number(item[key]))));
  const funnelBase = Math.max(1, number(funnel[0]?.value));
  const dateRange = `${shortDate(period.from)} – ${shortDate(period.to)}`;
  const shouldShowAxisLabel = (index: number) => series.length <= 14 || index === series.length - 1 || index % Math.ceil(series.length / 7) === 0;
  const efficiencyCards = [
    { label: '首次助手响应', value: analyticsValue(efficiency.first_reply_minutes, ' 分钟'), note: '从用户首条已发送消息到首条助手回复' },
    { label: '病例闭环时长', value: analyticsValue(efficiency.case_close_hours, ' 小时'), note: '本周期已关闭病例的平均耗时' },
    { label: '随访逾期率', value: analyticsValue(efficiency.overdue_follow_up_rate, '%'), note: `${number(efficiency.overdue_follow_ups)} / ${number(efficiency.scheduled_follow_ups)} 个排期中批次逾期` },
    { label: '举报审核时长', value: analyticsValue(efficiency.moderation_review_hours, ' 小时'), note: `当前仍有 ${number(efficiency.pending_reports)} 条待处理举报` },
  ];
  return <div className="analytics-page">
    <section className="analytics-hero"><div><span className="eyebrow">运营观察窗口</span><h3>增长不是终点，完成养殖闭环才算有效使用。</h3><p>以脱敏的事件聚合观察用户从注册、问诊到病例随访的路径，并及时发现服务效率中的积压。</p></div><div className="analytics-period-control"><span>{dateRange}</span><div className="segmented" aria-label="统计时间范围">{[7, 14, 30, 90].map((value) => <button type="button" className={days === value ? 'active' : ''} onClick={() => onDaysChange(value)} key={value}>{value} 天</button>)}</div></div></section>
    <section className="analytics-kpi-grid" aria-label="周期关键指标"><article><span>新增用户</span><strong>{analyticsValue(summary.new_users)}</strong><small>统计周期内完成注册</small></article><article><span>活跃用户</span><strong>{analyticsValue(summary.active_users)}</strong><small>完成至少一次有效产品操作</small></article><article><span>7 日留存</span><strong>{analyticsValue(retention.rate, '%')}</strong><small>{number(retention.retained_users)} / {number(retention.eligible_users)} 名已满 7 天用户回访</small></article><article><span>随访逾期</span><strong>{analyticsValue(efficiency.overdue_follow_ups)}</strong><small>{number(efficiency.scheduled_follow_ups)} 个排期中批次</small></article></section>
    <section className="analytics-layout analytics-first-row"><article className="analytics-card analytics-trend-card"><header className="analytics-card-header"><div><span className="eyebrow">每日趋势</span><h3>增长与业务产出</h3><p>点击任意日期，查看当天的脱敏构成。</p></div><div className="analytics-legend"><span className="legend-user">用户</span><span className="legend-consultation">问诊</span><span className="legend-case">病例</span><span className="legend-post">帖子</span></div></header><div className="analytics-trend" role="list" aria-label="每日运营趋势">{series.map((item, index) => { const day = text(item.day, ''); const metrics = [{ key: 'users' }, { key: 'conversations' }, { key: 'cases' }, { key: 'posts' }]; return <button type="button" role="listitem" className={`analytics-day${drillDownDay === day ? ' selected' : ''}`} onClick={() => setSelectedDay(day)} aria-pressed={drillDownDay === day} title={`${shortDate(day)}：新增 ${number(item.users)}，问诊 ${number(item.conversations)}，病例 ${number(item.cases)}，帖子 ${number(item.posts)}`} key={day}><span className="analytics-day-bars">{metrics.map((metric) => <i className={`bar-${metric.key}`} style={{ height: `${Math.max(5, number(item[metric.key]) / maxTrendValue * 100)}%` }} key={metric.key} />)}</span>{shouldShowAxisLabel(index) && <small>{shortDate(day).replace(/^\d{4}\//, '')}</small>}</button>; })}</div></article><article className="analytics-card analytics-funnel-card"><header className="analytics-card-header"><div><span className="eyebrow">新用户路径</span><h3>注册后的关键转化</h3><p>只统计本周期新注册用户在周期内完成的后续动作。</p></div></header><div className="analytics-funnel">{funnel.map((stage, index) => { const value = number(stage.value); const ratio = value / funnelBase * 100; return <article key={text(stage.key)}><span>{String(index + 1).padStart(2, '0')}</span><div><small>{text(stage.label)}</small><strong>{value.toLocaleString('zh-CN')}</strong><em>{index === 0 ? '基准人数' : `${ratio.toFixed(1)}% 转化`}</em></div><i><b style={{ width: `${ratio}%` }} /></i></article>; })}</div></article></section>
    <section className="analytics-card analytics-efficiency-card"><header className="analytics-card-header"><div><span className="eyebrow">业务效率</span><h3>把用户体验变成可处理的时效指标</h3></div><small>只对已有完成时间的数据计算平均值；无样本时显示“—”。</small></header><div className="analytics-efficiency-grid">{efficiencyCards.map((item) => <article key={item.label}><span>{item.label}</span><strong>{item.value}</strong><small>{item.note}</small></article>)}</div></section>
    <section className="analytics-card analytics-drilldown-card" aria-live="polite"><header className="analytics-card-header"><div><span className="eyebrow">按日下钻</span><h3>{shortDate(drillDownDay)} 的业务构成</h3><p>保持聚合口径，不展示用户身份、对话内容或养殖场详情。</p></div>{drillDown.loading && <small>正在更新…</small>}</header>{drillDown.error ? <p className="analytics-drilldown-error">{drillDown.error}</p> : drillDown.data ? <><div className="analytics-day-summary"><span>新增用户 <b>{number(drillSummary.new_users)}</b></span><span>活跃用户 <b>{number(drillSummary.active_users)}</b></span><span>问诊 <b>{number(drillSummary.conversations)}</b></span><span>病例 <b>{number(drillSummary.cases)}</b></span><span>随访 <b>{number(drillSummary.follow_ups)}</b></span><span>帖子 <b>{number(drillSummary.posts)}</b></span></div><div className="analytics-breakdown-grid"><AnalyticsBreakdown title="问诊类型" rows={Array.isArray(breakdown.conversations) ? breakdown.conversations as Row[] : []} /><AnalyticsBreakdown title="病例等级" rows={Array.isArray(breakdown.cases) ? breakdown.cases as Row[] : []} /><AnalyticsBreakdown title="内容类型" rows={Array.isArray(breakdown.posts) ? breakdown.posts as Row[] : []} /></div><div className="analytics-attention"><span>当日需要关注</span><p>高风险新病例 <b>{number(attention.high_risk_cases)}</b><i />新增举报 <b>{number(attention.reports_created)}</b><i />失败任务 <b>{number(attention.failed_jobs)}</b></p></div></> : <div className="empty-selection"><p>选择趋势中的某一天，查看当天的聚合数据构成。</p></div>}</section>
  </div>;
}
const HEALTH_SERVICES: Array<[string, string]> = [['admin_api', '管理 API'], ['database', 'PostgreSQL'], ['user_api', '用户 API'], ['object_storage', '对象存储']];

function healthLocalDateTime(value: unknown): string {
  if (!value) return '';
  const parsed = new Date(String(value));
  if (Number.isNaN(parsed.valueOf())) return '';
  const offset = parsed.getTimezoneOffset() * 60_000;
  return new Date(parsed.valueOf() - offset).toISOString().slice(0, 16);
}

function HealthSettingsDialog({ session, data, loading, onClose, onSaved, onToast }: { session: AdminSession; data: Row | null; loading: boolean; onClose: () => void; onSaved: () => void; onToast: (message: string) => void }) {
  const [saving, setSaving] = useState(false); const [error, setError] = useState('');
  const probes = (data?.probes ?? {}) as Row; const maintenance = (data?.maintenance ?? {}) as Row;
  const maintenanceServices = Array.isArray(maintenance.services) ? maintenance.services.map((item) => text(item)).filter(Boolean) : [];
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); const form = new FormData(event.currentTarget); const maintenanceEnabled = form.get('maintenance_enabled') === 'on'; const endInput = text(form.get('ends_at'), '');
    if (maintenanceEnabled && !endInput) { setError('启用维护窗口时，请设置结束时间。'); return; }
    const endsAt = maintenanceEnabled && endInput ? new Date(endInput).toISOString() : null;
    const value = {
      probes: { user_api_url: text(form.get('user_api_url'), ''), object_storage_url: text(form.get('object_storage_url'), ''), timeout_seconds: Number(form.get('timeout_seconds') || 3) },
      maintenance: { enabled: maintenanceEnabled, services: form.getAll('maintenance_services').map((item) => String(item)), ends_at: endsAt, message: text(form.get('maintenance_message'), '') },
    };
    const reason = text(form.get('reason'), '').trim();
    if (reason.length < 3) { setError('请填写至少 3 个字的修改理由。'); return; }
    setSaving(true); setError('');
    try { await api('/health/settings', session, { method: 'PUT', body: JSON.stringify({ value, reason }) }); onToast('服务健康设置已保存'); onSaved(); onClose(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '服务健康设置保存失败'); }
    finally { setSaving(false); }
  };
  return <Modal title="服务健康设置" onClose={onClose}>{loading ? <div className="loading-state"><RefreshCcw size={17} />正在加载设置…</div> : <form className="health-settings-form" onSubmit={submit}>
    <p>探测地址只供管理端健康检查使用；维护窗口内会保留真实探测结果，同时自动抑制对应的服务风险告警。</p>
    <fieldset><legend>探测连接</legend><label>用户 API 健康检查地址<input name="user_api_url" type="url" defaultValue={text(probes.user_api_url, '')} placeholder="http://127.0.0.1:8010/healthz" /></label><label>对象存储探测地址（可选）<input name="object_storage_url" type="url" defaultValue={text(probes.object_storage_url, '')} placeholder="https://storage.example.com/healthz" /></label><label>超时秒数<input name="timeout_seconds" type="number" min="0.5" max="15" step="0.5" defaultValue={number(probes.timeout_seconds) || 3} /></label></fieldset>
    <fieldset><legend>维护窗口</legend><label className="health-setting-switch"><input name="maintenance_enabled" type="checkbox" defaultChecked={Boolean(maintenance.enabled)} />当前正在维护</label><div className="health-maintenance-services">{HEALTH_SERVICES.map(([key, label]) => <label key={key}><input name="maintenance_services" type="checkbox" value={key} defaultChecked={maintenanceServices.includes(key)} />{label}</label>)}</div><label>结束时间<input name="ends_at" type="datetime-local" defaultValue={healthLocalDateTime(maintenance.ends_at)} /></label><label>维护说明<input name="maintenance_message" maxLength={240} defaultValue={text(maintenance.message, '')} placeholder="例如：存储供应商例行升级，预计 30 分钟恢复。" /></label></fieldset>
    <label className="health-settings-reason">修改理由<textarea name="reason" minLength={3} required placeholder="该说明会写入审计日志。" /></label>{error && <p className="form-error">{error}</p>}<footer className="modal-actions"><button className="quiet-button" type="button" onClick={onClose}>取消</button><button className="primary-button" disabled={saving}>{saving ? '保存中…' : '保存设置'}</button></footer>
  </form>}</Modal>;
}

function HealthPanel({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const resource = useResource<Row>(session, '/health'); const [settingsOpen, setSettingsOpen] = useState(false); const [refreshing, setRefreshing] = useState(false); const settingsResource = useResource<Row>(session, '/health/settings', settingsOpen);
  const data = resource.data ?? {}; const services = Array.isArray(data.services) ? data.services as Row[] : []; const summary = (data.summary ?? {}) as Row; const metrics = (data.metrics ?? {}) as Row; const history = Array.isArray(data.history) ? data.history as Row[] : [];
  const maintenance = (data.maintenance ?? {}) as Row; const isMaintenance = Boolean(maintenance.enabled) && Boolean(maintenance.ends_at) && new Date(text(maintenance.ends_at)).valueOf() > Date.now(); const canManage = hasPermission(session, 'security.manage');
  const refresh = async () => { setRefreshing(true); try { await api('/health/refresh', session, { method: 'POST' }); onToast('已完成一次真实探活'); resource.reload(); } catch (error) { onToast(error instanceof Error ? error.message : '服务探活失败'); } finally { setRefreshing(false); } };
  const maxHistory = Math.max(1, ...history.map((item) => number(item.healthy) + number(item.degraded) + number(item.failed) + number(item.maintenance) + number(item.unknown)));
  return <div className="health-console"><LoadingState loading={resource.loading} error={resource.error}>
    <section className="health-hero"><div className="health-hero-copy"><span className="eyebrow">live dependency check</span><h3>让每个依赖都给出<br />可解释的运行信号。</h3><p>显示实时探活、任务负载与过去 14 天的健康变化。失败会自动进入风险事件；维护窗口不会掩盖真实探测结果。</p></div><div className={`health-hero-orbit ${number(summary.failed) > 0 ? 'has-failure' : ''}`}><span>可用依赖</span><strong>{number(summary.healthy)}<i>/</i>{number(summary.total)}</strong><small>{number(summary.failed) ? `${number(summary.failed)} 项不可用` : number(summary.degraded) ? `${number(summary.degraded)} 项降级` : '当前无不可用依赖'}</small></div></section>
    {isMaintenance && <section className="health-maintenance-notice"><Wrench size={17} /><div><strong>维护窗口进行中</strong><span>{text(maintenance.message, '维护期间自动抑制对应告警')} · 截止 {dateTime(maintenance.ends_at)}</span></div></section>}
    <section className="health-summary-grid" aria-label="服务健康概览"><article><span>运行正常</span><strong>{number(summary.healthy)}</strong><small>探测已成功响应</small></article><article><span>需要关注</span><strong>{number(summary.degraded)}</strong><small>响应异常但仍可访问</small></article><article><span>不可用</span><strong>{number(summary.failed)}</strong><small>已同步为风险事件</small></article><article><span>无法判定</span><strong>{number(summary.unknown)}</strong><small>等待配置或可用样本</small></article></section>
    <section className="health-command-header"><div><span className="eyebrow">当前依赖</span><h3>不是颜色，而是一次可追溯的检查结果。</h3><small>最近检测：{dateTime(data.generated_at)}</small></div><div>{canManage && <button className="quiet-button" onClick={() => setSettingsOpen(true)}><Settings size={14} />设置</button>}<button className="primary-button" disabled={refreshing} onClick={() => void refresh()}><RefreshCcw size={15} className={refreshing ? 'is-spinning' : ''} />{refreshing ? '探测中…' : '立即探活'}</button></div></section>
    <section className="health-service-grid">{services.map((service) => { const serviceStatus = text(service.status); return <article className={`health-service-card ${serviceStatus}`} key={text(service.key)}><header><span className={`service-dot ${serviceStatus}`} /><div><strong>{text(service.label)}</strong><small>{text(service.key)}</small></div><Status value={serviceStatus} /></header><p>{text(service.detail)}</p><footer><span>{service.latency_ms === null || service.latency_ms === undefined ? '延迟 —' : `${number(service.latency_ms)} ms`}</span><span>{service.status_code ? `HTTP ${number(service.status_code)}` : '协议检查'}</span>{service.maintenance_ends_at && <span>维护至 {dateTime(service.maintenance_ends_at)}</span>}</footer></article>; })}</section>
    <section className="health-insight-grid"><article className="health-history-card"><header><div><span className="eyebrow">14 日健康历史</span><h3>每天取每项服务最后一次检查</h3></div><small>用于发现持续性故障</small></header><div className="health-history-bars">{history.map((item, index) => { const total = number(item.healthy) + number(item.degraded) + number(item.failed) + number(item.maintenance) + number(item.unknown); return <div className="health-history-day" title={`${shortDate(item.day)}：正常 ${number(item.healthy)}，降级 ${number(item.degraded)}，失败 ${number(item.failed)}`} key={text(item.day)}><span style={{ height: `${Math.max(4, total / maxHistory * 100)}%` }}><i className="healthy" style={{ height: `${number(item.healthy) / Math.max(1, total) * 100}%` }} /><i className="degraded" style={{ height: `${number(item.degraded) / Math.max(1, total) * 100}%` }} /><i className="failed" style={{ height: `${number(item.failed) / Math.max(1, total) * 100}%` }} /><i className="maintenance" style={{ height: `${number(item.maintenance) / Math.max(1, total) * 100}%` }} /></span>{(index === 0 || index === history.length - 1 || index % 4 === 0) && <small>{shortDate(item.day).replace(/^\d{4}\//, '')}</small>}</div>; })}</div><footer><span><i className="healthy" />正常</span><span><i className="degraded" />降级</span><span><i className="failed" />失败</span><span><i className="maintenance" />维护</span></footer></article><article className="health-runtime-card"><header><div><span className="eyebrow">运行负载</span><h3>服务之外的执行信号</h3></div><Activity size={18} /></header><dl><div><dt>进行中的后台任务</dt><dd>{number(metrics.active_jobs)}</dd></div><div><dt>24 小时失败任务</dt><dd className={number(metrics.failed_jobs_24h) > 0 ? 'attention' : ''}>{number(metrics.failed_jobs_24h)}</dd></div><div><dt>7 天失败任务</dt><dd>{number(metrics.failed_jobs_7d)}</dd></div><div><dt>测试失败的系统模型</dt><dd className={number(metrics.failed_models) > 0 ? 'attention' : ''}>{number(metrics.failed_models)}</dd></div></dl><p><AlertTriangle size={14} />任务与模型失败会留在各自的业务模块，并与风险事件建立关联，避免在此重复堆积待办。</p></article></section>
  </LoadingState>{settingsOpen && <HealthSettingsDialog session={session} data={settingsResource.data} loading={settingsResource.loading} onClose={() => setSettingsOpen(false)} onSaved={() => { resource.reload(); settingsResource.reload(); }} onToast={onToast} />}</div>;
}

function SystemPage({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  useEffect(() => { const requested = hashQuery('tab'); if (requested === 'audit' || requested === 'roles' || requested === 'settings' || requested === 'admins') setTab(requested); }, []);
  const [tab, setTab] = useState<'admins' | 'roles' | 'audit' | 'settings'>('admins'); const [inviteOpen, setInviteOpen] = useState(false); const [roleTarget, setRoleTarget] = useState<Row | null>(null); const [selectedRoleKeys, setSelectedRoleKeys] = useState<string[]>([]); const [roleReason, setRoleReason] = useState(''); const [roleSaving, setRoleSaving] = useState(false); const [roleError, setRoleError] = useState(''); const [statusTarget, setStatusTarget] = useState<Row | null>(null); const [statusAction, setStatusAction] = useState<'disabled' | 'active'>('disabled'); const [statusReason, setStatusReason] = useState(''); const [statusSaving, setStatusSaving] = useState(false); const [statusError, setStatusError] = useState(''); const [roleEditorOpen, setRoleEditorOpen] = useState(false); const [roleEditorMode, setRoleEditorMode] = useState<'create' | 'edit' | 'clone'>('create'); const [roleEditorTarget, setRoleEditorTarget] = useState<Row | null>(null); const [roleDraft, setRoleDraft] = useState({ key: '', label: '', description: '', permissionKeys: [] as string[] }); const [roleEditorReason, setRoleEditorReason] = useState(''); const [roleEditorSaving, setRoleEditorSaving] = useState(false); const [roleEditorError, setRoleEditorError] = useState(''); const [roleImpact, setRoleImpact] = useState<Row | null>(null); const [roleImpactLoading, setRoleImpactLoading] = useState(false); const [roleImpactError, setRoleImpactError] = useState(''); const [deleteRoleTarget, setDeleteRoleTarget] = useState<Row | null>(null); const [deleteRoleReason, setDeleteRoleReason] = useState(''); const [deleteRoleSaving, setDeleteRoleSaving] = useState(false); const [deleteRoleError, setDeleteRoleError] = useState(''); const path = tab === 'roles' ? '/roles' : '/admins'; const resource = useResource<ListResponse>(session, path, tab === 'admins' || tab === 'roles'); const rolesResource = useResource<ListResponse>(session, '/roles', Boolean(roleTarget)); const availablePermissions = Array.isArray((resource.data as Row | null)?.available_permissions) ? ((resource.data as Row).available_permissions as Row[]) : [];
  const invite = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); const roleKeys = String(form.get('role_keys')).split(',').map((value) => value.trim()).filter(Boolean); try { const result = await api<Row>('/admins/invitations', session, { method: 'POST', body: JSON.stringify({ email: form.get('email'), display_name: form.get('display_name'), role_keys: roleKeys, expires_in_hours: 72 }) }); setInviteOpen(false); onToast(`邀请已创建：${text(result.invitation_token)}（请通过安全渠道发送）`); resource.reload(); } catch (error) { onToast(error instanceof Error ? error.message : '创建邀请失败'); } };
  const openStatusDialog = (item: Row, action: 'disabled' | 'active') => { setStatusTarget(item); setStatusAction(action); setStatusReason(''); setStatusError(''); };
  const submitStatusChange = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (!statusTarget) return; if (statusReason.trim().length < 3) { setStatusError('请填写至少 3 个字的操作理由。'); return; } setStatusSaving(true); setStatusError(''); try { await api(`/admins/${text(statusTarget.id)}/status`, session, { method: 'PATCH', body: JSON.stringify({ status: statusAction, reason: statusReason.trim() }) }); onToast(statusAction === 'disabled' ? '管理员已禁用' : '管理员已恢复'); setStatusTarget(null); resource.reload(); } catch (error) { setStatusError(error instanceof Error ? error.message : '账号状态更新失败'); } finally { setStatusSaving(false); } };
  const openRoleDialog = (item: Row) => { setRoleTarget(item); setSelectedRoleKeys(Array.isArray(item.roles) ? (item.roles as unknown[]).map((role) => text(role)).filter(Boolean) : []); setRoleReason(''); setRoleError(''); };
  const toggleRole = (roleKey: string) => setSelectedRoleKeys((current) => current.includes(roleKey) ? current.filter((key) => key !== roleKey) : [...current, roleKey]);
  const submitRoles = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (!roleTarget) return; if (!selectedRoleKeys.length) { setRoleError('请至少选择一个角色。'); return; } if (roleReason.trim().length < 3) { setRoleError('请填写至少 3 个字的调整理由。'); return; } setRoleSaving(true); setRoleError(''); try { await api(`/admins/${text(roleTarget.id)}/roles`, session, { method: 'PATCH', body: JSON.stringify({ role_keys: selectedRoleKeys, reason: roleReason.trim() }) }); onToast('角色已更新，目标管理员需重新登录'); setRoleTarget(null); resource.reload(); } catch (error) { setRoleError(error instanceof Error ? error.message : '角色更新失败'); } finally { setRoleSaving(false); } };
  const loadRoleImpact = async (item: Row) => { setRoleImpact(null); setRoleImpactError(''); setRoleImpactLoading(true); try { setRoleImpact(await api<Row>(`/roles/${text(item.id)}/impact`, session)); } catch (error) { setRoleImpactError(error instanceof Error ? error.message : '无法加载角色影响范围'); } finally { setRoleImpactLoading(false); } };
  const openRoleEditor = (existing?: Row) => { setRoleEditorOpen(true); setRoleEditorMode(existing ? 'edit' : 'create'); setRoleEditorTarget(existing ?? null); setRoleDraft(existing ? { key: text(existing.key), label: text(existing.label), description: text(existing.description), permissionKeys: Array.isArray(existing.permissions) ? (existing.permissions as unknown[]).map((item) => text(item)).filter(Boolean) : [] } : { key: '', label: '', description: '', permissionKeys: [] }); setRoleEditorReason(''); setRoleEditorError(''); if (existing) void loadRoleImpact(existing); else setRoleImpact(null); };
  const toggleDraftPermission = (permissionKey: string) => setRoleDraft((current) => ({ ...current, permissionKeys: current.permissionKeys.includes(permissionKey) ? current.permissionKeys.filter((key) => key !== permissionKey) : [...current.permissionKeys, permissionKey] }));
  const submitRoleEditor = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const key = roleDraft.key.trim(); if (!/^[a-z][a-z0-9_]*$/.test(key)) { setRoleEditorError('角色标识需以小写字母开头，只能使用小写字母、数字和下划线。'); return; } if (roleDraft.label.trim().length < 2 || roleDraft.description.trim().length < 3) { setRoleEditorError('请填写角色名称和至少 3 个字的职责说明。'); return; } if (!roleDraft.permissionKeys.length) { setRoleEditorError('请至少选择一项权限。'); return; } if (roleEditorReason.trim().length < 3) { setRoleEditorError('请填写至少 3 个字的操作理由。'); return; } setRoleEditorSaving(true); setRoleEditorError(''); const body = { key, label: roleDraft.label.trim(), description: roleDraft.description.trim(), permission_keys: roleDraft.permissionKeys, reason: roleEditorReason.trim() }; try { await api(roleEditorTarget ? `/roles/${text(roleEditorTarget.id)}` : '/roles', session, { method: roleEditorTarget ? 'PUT' : 'POST', body: JSON.stringify(body) }); onToast(roleEditorTarget ? '角色已更新，受影响会话已撤销' : '自定义角色已创建'); setRoleEditorOpen(false); setRoleEditorTarget(null); setRoleDraft({ key: '', label: '', description: '', permissionKeys: [] }); setRoleImpact(null); resource.reload(); } catch (error) { setRoleEditorError(error instanceof Error ? error.message : '角色保存失败'); } finally { setRoleEditorSaving(false); } };
  const openRoleDelete = (item: Row) => { setDeleteRoleTarget(item); setDeleteRoleReason(''); setDeleteRoleError(''); void loadRoleImpact(item); };
  const submitRoleDelete = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (!deleteRoleTarget) return; if (number(roleImpact?.assigned_admin_count) > 0) { setDeleteRoleError('该角色仍被管理员使用，先在账号角色分配中移除后再删除。'); return; } if (deleteRoleReason.trim().length < 3) { setDeleteRoleError('请填写至少 3 个字的删除理由。'); return; } setDeleteRoleSaving(true); setDeleteRoleError(''); try { await api(`/roles/${text(deleteRoleTarget.id)}`, session, { method: 'DELETE', body: JSON.stringify({ reason: deleteRoleReason.trim() }) }); onToast('自定义角色已删除'); setDeleteRoleTarget(null); setRoleImpact(null); resource.reload(); } catch (error) { setDeleteRoleError(error instanceof Error ? error.message : '角色删除失败'); } finally { setDeleteRoleSaving(false); } };
  const isStatusDisable = statusAction === 'disabled';
  if (tab === 'audit') return <>
    <PageHeader eyebrow="权限、安全与可追溯性" title="系统管理" description="所有角色变更、敏感查看与高风险操作都在此保留审计证据。" actions={<Tabs current={tab} onChange={setTab} values={[['admins', '管理员'], ['roles', '角色权限'], ['audit', '审计日志'], ['settings', '系统设置']]} />} />
    <AuditLogsPanel session={session} onToast={onToast} />
  </>;
  if (tab === 'settings') return <>
    <PageHeader eyebrow="系统规则与运行边界" title="系统设置" description="用可解释的规则管理待办时效；每次修改都会记录理由、影响范围与可回滚版本。" actions={<Tabs current={tab} onChange={setTab} values={[['admins', '管理员'], ['roles', '角色权限'], ['audit', '审计日志'], ['settings', '系统设置']]} />} />
    <SystemSettingsWorkspace session={session} onToast={onToast} />
  </>;
  return <>
    <PageHeader eyebrow="权限、安全与可追溯性" title="系统管理" description="所有角色变更、敏感查看与高风险操作都在此保留审计证据。" actions={<Tabs current={tab} onChange={setTab} values={[['admins', '管理员'], ['roles', '角色权限'], ['audit', '审计日志'], ['settings', '系统设置']]} />} />
    {tab === 'admins' && <button className="primary-button page-float-action" onClick={() => setInviteOpen(true)}><UserRoundCheck size={16} />邀请管理员</button>}
    {tab === 'roles' && <button className="primary-button page-float-action" onClick={() => openRoleEditor()}><Plus size={16} />新增自定义角色</button>}
    <article className="panel full-panel">
      <LoadingState loading={resource.loading} error={resource.error}>
        {tab === 'admins' && <SimpleTable columns={['管理员', '角色', 'MFA', '最近活跃', '状态', '操作']} rows={asItems(resource.data)} render={(item) => [
          <div key="admin"><strong>{text(item.display_name)}</strong><small>{text(item.email)}</small></div>,
          Array.isArray(item.roles) ? (item.roles as unknown[]).join('、') : '—',
          item.mfa_enrolled ? '已启用' : '待绑定',
          dateTime(item.last_seen_at),
          <Status key="status" value={text(item.status)} />,
          <div className="row-actions" key="action">
            <button onClick={() => openRoleDialog(item)}>角色</button>
            {text(item.status) === 'active' && <button className="danger" onClick={() => openStatusDialog(item, 'disabled')}>禁用</button>}
            {text(item.status) === 'disabled' && <button className="restore-button" onClick={() => openStatusDialog(item, 'active')}>恢复</button>}
          </div>,
        ]} empty="暂无管理员账号" />}
        {tab === 'roles' && <RolesPanel data={resource.data as Row | null} onEdit={openRoleEditor} onDelete={openRoleDelete} />}
      </LoadingState>
    </article>
    {inviteOpen && <Modal title="邀请管理员" onClose={() => setInviteOpen(false)}><form className="form-grid" onSubmit={invite}><label>邮箱<input name="email" type="email" required /></label><label>显示名称<input name="display_name" required /></label><label>角色标识<input name="role_keys" defaultValue="community_moderator" required /><small>多个角色以逗号分隔，如 expert_reviewer,operations</small></label><button className="primary-button">创建邀请</button></form></Modal>}
    {roleTarget && <Modal title="调整管理员角色" onClose={() => { if (!roleSaving) setRoleTarget(null); }}><form className="role-assignment-form" onSubmit={submitRoles}>
      <div className="role-assignment-heading"><div className="role-assignment-avatar">{text(roleTarget.display_name).slice(0, 1) || '管'}</div><div><span>正在调整</span><strong>{text(roleTarget.display_name)}</strong><small>{text(roleTarget.email)}</small></div></div>
      <div className="role-assignment-note"><ShieldCheck size={16} /><span>保存后会撤销该账号当前会话，需重新登录后按新权限生效。</span></div>
      <fieldset className="role-assignment-list"><legend>分配角色</legend>{rolesResource.loading && <p className="role-assignment-loading">正在加载可用角色…</p>}{rolesResource.error && <p className="form-error">{rolesResource.error}</p>}{asItems(rolesResource.data).map((role) => { const key = text(role.key); const checked = selectedRoleKeys.includes(key); const permissionCount = Array.isArray(role.permissions) ? role.permissions.length : 0; return <label className={'role-choice' + (checked ? ' selected' : '')} key={key}><input type="checkbox" checked={checked} onChange={() => toggleRole(key)} /><span><strong>{text(role.label)}</strong><small>{text(role.description)}</small></span><em>{permissionCount} 项权限</em></label>; })}</fieldset>
      <label className="role-reason-field">调整理由<textarea value={roleReason} onChange={(event) => { setRoleReason(event.target.value); setRoleError(''); }} placeholder="例如：负责社区内容审核，授予社区审核员角色。" minLength={3} required /></label>
      {roleError && <p className="form-error">{roleError}</p>}
      <footer className="modal-actions"><button className="quiet-button" type="button" disabled={roleSaving} onClick={() => setRoleTarget(null)}>取消</button><button className="primary-button" disabled={roleSaving || rolesResource.loading}>{roleSaving ? '正在保存…' : '保存角色'}</button></footer>
    </form></Modal>}
    {statusTarget && <Modal title={isStatusDisable ? '禁用管理员' : '恢复管理员'} onClose={() => { if (!statusSaving) setStatusTarget(null); }}><form className="admin-status-form" onSubmit={submitStatusChange}>
      <div className="role-assignment-heading"><div className={'role-assignment-avatar' + (isStatusDisable ? ' danger' : ' success')}>{text(statusTarget.display_name).slice(0, 1) || '管'}</div><div><span>{isStatusDisable ? '即将禁用' : '即将恢复'}</span><strong>{text(statusTarget.display_name)}</strong><small>{text(statusTarget.email)}</small></div></div>
      <div className={'admin-status-note' + (isStatusDisable ? ' danger' : ' success')}>{isStatusDisable ? <ShieldAlert size={16} /> : <ShieldCheck size={16} />}<span>{isStatusDisable ? '确认后，该账号将立即退出所有后台会话，且无法再次登录，直到被恢复。' : '恢复后，该账号可以再次完成密码和 MFA 验证后登录；此前撤销的会话不会自动恢复。'}</span></div>
      <label className="role-reason-field">操作理由<textarea value={statusReason} onChange={(event) => { setStatusReason(event.target.value); setStatusError(''); }} placeholder={isStatusDisable ? '例如：已不再负责后台管理，停用其管理员权限。' : '例如：已完成身份复核，恢复其后台管理权限。'} minLength={3} required /></label>
      {statusError && <p className="form-error">{statusError}</p>}
      <footer className="modal-actions"><button className="quiet-button" type="button" disabled={statusSaving} onClick={() => setStatusTarget(null)}>取消</button><button className={isStatusDisable ? 'danger-confirm-button' : 'primary-button'} disabled={statusSaving}>{statusSaving ? '正在保存…' : isStatusDisable ? '确认禁用' : '确认恢复'}</button></footer>
    </form></Modal>}
    {roleEditorOpen && <Modal title={roleEditorMode === 'edit' ? '编辑自定义角色' : '新增自定义角色'} onClose={() => { if (!roleEditorSaving) { setRoleEditorOpen(false); setRoleImpact(null); } }}><form className="role-editor-form" onSubmit={submitRoleEditor}>
      <div className="role-editor-scroll">
        <div className="role-editor-intro"><ShieldCheck size={17} /><span>{roleEditorMode === 'edit' ? '角色权限变更会撤销使用该角色的后台会话。' : '选择所需能力后，角色可分配给管理员账号。'}</span></div>
        <div className="role-editor-fields"><label>角色标识<input value={roleDraft.key} onChange={(event) => setRoleDraft((current) => ({ ...current, key: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '') }))} placeholder="content_reviewer" required minLength={2} disabled={roleEditorSaving} /></label><label>显示名称<input value={roleDraft.label} onChange={(event) => setRoleDraft((current) => ({ ...current, label: event.target.value }))} placeholder="内容审核员" required minLength={2} disabled={roleEditorSaving} /></label></div>
        <label className="role-reason-field">职责说明<textarea value={roleDraft.description} onChange={(event) => setRoleDraft((current) => ({ ...current, description: event.target.value }))} placeholder="例如：负责处理社区举报、内容隐藏和专业认证。" minLength={3} required disabled={roleEditorSaving} /></label>
        {roleEditorMode === 'edit' && <div className="role-impact-summary">{roleImpactLoading ? <span>正在计算本次变更影响…</span> : roleImpactError ? <span className="form-error">{roleImpactError}</span> : <><strong>影响预览</strong><span>当前分配给 {number(roleImpact?.assigned_admin_count)} 位管理员；保存后会撤销 {number(roleImpact?.active_session_count)} 个活跃会话。</span></>}</div>}
        <fieldset className="role-permission-set"><legend>权限能力 <small>已选择 {roleDraft.permissionKeys.length} 项</small></legend>{Array.from(new Set(availablePermissions.map((permission) => text(permission.group)))).map((group) => { const permissions = availablePermissions.filter((permission) => text(permission.group) === group); return <section className="role-permission-group" key={group}><h3>{{ workbench: '工作台', users: '用户与内容', community: '社区治理', diagnosis: '智能问诊', husbandry: '养殖病例', models: '模型任务', knowledge: '知识能力', security: '运营与安全', analytics: '运营分析', system: '系统管理' }[group] ?? group}</h3><div>{permissions.map((permission) => { const key = text(permission.key); const checked = roleDraft.permissionKeys.includes(key); return <label className={'role-permission-choice' + (checked ? ' selected' : '')} key={key}><input type="checkbox" checked={checked} onChange={() => toggleDraftPermission(key)} disabled={roleEditorSaving} /><span><strong>{text(permission.label)}</strong><small>{key}</small></span></label>; })}</div></section>; })}</fieldset>
        <label className="role-reason-field">操作理由<textarea value={roleEditorReason} onChange={(event) => { setRoleEditorReason(event.target.value); setRoleEditorError(''); }} placeholder={roleEditorMode === 'edit' ? '例如：补充社区审核职责，调整权限范围。' : '例如：新增内容审核岗位，便于职责分工。'} minLength={3} required disabled={roleEditorSaving} /></label>
      </div>
      {roleEditorError && <p className="role-editor-feedback form-error">{roleEditorError}</p>}
      <footer className="modal-actions role-editor-actions"><button className="quiet-button" type="button" disabled={roleEditorSaving} onClick={() => { setRoleEditorOpen(false); setRoleImpact(null); }}>取消</button><button className="primary-button" disabled={roleEditorSaving || !availablePermissions.length}>{roleEditorSaving ? '正在保存…' : roleEditorMode === 'edit' ? '保存角色' : '确定创建'}</button></footer>
    </form></Modal>}
    {deleteRoleTarget && <Modal title="删除自定义角色" onClose={() => { if (!deleteRoleSaving) { setDeleteRoleTarget(null); setRoleImpact(null); } }}><form className="role-delete-form" onSubmit={submitRoleDelete}>
      <div className="role-assignment-heading"><div className="role-assignment-avatar danger">{text(deleteRoleTarget.label).slice(0, 1) || '角'}</div><div><span>即将删除</span><strong>{text(deleteRoleTarget.label)}</strong><small>{text(deleteRoleTarget.key)}</small></div></div>
      <div className="admin-status-note danger"><ShieldAlert size={16} /><span>删除不可恢复。系统预置角色不能删除，仍被管理员使用的自定义角色也不能删除。</span></div>
      <section className="role-delete-impact"><strong>使用情况</strong>{roleImpactLoading ? <p>正在检查影响范围…</p> : roleImpactError ? <p className="form-error">{roleImpactError}</p> : <><p>已分配给 <b>{number(roleImpact?.assigned_admin_count)}</b> 位管理员，存在 <b>{number(roleImpact?.active_session_count)}</b> 个活跃会话。</p>{(Array.isArray(roleImpact?.assigned_admins) ? roleImpact.assigned_admins as Row[] : []).slice(0, 5).map((admin) => <span key={text(admin.id)}>{text(admin.display_name)} · {text(admin.email)}</span>)}{number(roleImpact?.assigned_admin_count) > 5 && <span>其余管理员请在“管理员”中查看和调整。</span>}</>}</section>
      <label className="role-reason-field">删除理由<textarea value={deleteRoleReason} onChange={(event) => { setDeleteRoleReason(event.target.value); setDeleteRoleError(''); }} placeholder="例如：该岗位已取消，且没有管理员继续使用该角色。" minLength={3} required disabled={deleteRoleSaving || roleImpactLoading || number(roleImpact?.assigned_admin_count) > 0} /></label>
      {deleteRoleError && <p className="form-error">{deleteRoleError}</p>}
      <footer className="modal-actions"><button className="quiet-button" type="button" disabled={deleteRoleSaving} onClick={() => { setDeleteRoleTarget(null); setRoleImpact(null); }}>取消</button><button className="danger-confirm-button" disabled={deleteRoleSaving || roleImpactLoading || !!roleImpactError || number(roleImpact?.assigned_admin_count) > 0}>{deleteRoleSaving ? '正在删除…' : '确认删除'}</button></footer>
    </form></Modal>}

  </>;
}

function RolesPanel({ data, onEdit, onDelete }: { data: Row | null; onEdit: (item: Row) => void; onDelete: (item: Row) => void }) { const items = Array.isArray(data?.items) ? data.items as Row[] : []; return <SimpleTable columns={['角色', '说明', '权限数量', '使用情况', '权限', '操作']} rows={items} render={(item) => [<div key="label"><strong>{text(item.label)}</strong><small>{text(item.key)}{item.is_system ? ' · 系统预置' : ' · 自定义角色'}</small></div>, text(item.description), Array.isArray(item.permissions) ? item.permissions.length : 0, <span className="role-usage" key="usage">{number(item.assigned_admin_count)} 位管理员 · {number(item.active_session_count)} 会话</span>, <span className="permission-list" key="permissions">{Array.isArray(item.permissions) ? (item.permissions as unknown[]).slice(0, 4).join(' · ') : '—'}</span>, item.is_system ? <span className="role-usage" key="actions">系统预置</span> : <div className="row-actions" key="actions"><button onClick={() => onEdit(item)}>编辑</button><button className="danger" onClick={() => onDelete(item)}>删除</button></div>]} empty="未配置角色" />; }

const auditActionLabels: Record<string, string> = {
  'auth.login': '管理员登录', 'auth.logout': '管理员退出', 'auth.login_failed': '登录失败', 'admins.invite': '邀请管理员',
  'admins.status_changed': '账号状态变更', 'admins.roles_changed': '管理员角色变更',
  'roles.created': '创建角色', 'roles.updated': '更新角色', 'roles.deleted': '删除角色',
  'community.report_reviewed': '处理社区举报', 'community.verification_reviewed': '审核专业认证', 'community.post_status_changed': '调整帖子状态', 'community.tag_renamed': '重命名话题', 'community.tag_merged': '合并话题',
  'sensitive_access.granted': '授予敏感查看', 'sensitive_access.used': '使用敏感查看',
  'diagnosis.expert_review_published': '发布问诊复核', 'diagnosis.expert_review_drafted': '保存问诊复核草稿', 'husbandry.expert_review_published': '发布病例复核', 'husbandry.expert_review_drafted': '保存病例复核草稿',
  'models.created': '新增系统模型', 'models.updated': '更新系统模型', 'models.tested': '测试系统模型',
  'knowledge.source_created': '新建知识源', 'knowledge.index_queued': '发起知识索引',
  'settings.updated': '更新系统设置', 'risk_rules.updated': '更新风险规则',
};
const auditResourceLabels: Record<string, string> = {
  admin_account: '管理员账号', admin_role: '角色权限', admin_invite: '管理员邀请', admin_session: '后台会话',
  community_report: '社区举报', community_profile: '社区资料', community_post: '社区帖子', community_tag: '社区话题',
  conversation: '问诊会话', expert_review: '专家复核', husbandry_case: '养殖病例', work_item: '待办事项',
  system_setting: '系统设置', system_model: '系统模型', knowledge_source: '知识源', background_job: '后台任务', file: '文件资产', risk_incident: '风险事件',
};

function auditActionLabel(action: string) { return auditActionLabels[action] ?? action.replace('.', ' · '); }
function auditResourceLabel(resourceType: string) { return auditResourceLabels[resourceType] ?? resourceType.replace(/_/g, ' '); }
function auditActionTone(action: string) { if (/(deleted|status_changed|sensitive_access|risk_rules|settings\.updated|roles\.)/.test(action)) return 'risk'; if (/(failed|dismiss|suppress|quarantine)/.test(action)) return 'warning'; if (/(created|published|granted|login)$/.test(action)) return 'positive'; return 'neutral'; }
function auditValue(value: unknown) { if (value === undefined || value === null || value === '') return '—'; if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value); try { return JSON.stringify(value); } catch { return String(value); } }
function auditChangedFields(entry: Row) {
  const before = typeof entry.before_data === 'object' && entry.before_data !== null && !Array.isArray(entry.before_data) ? entry.before_data as Row : {};
  const after = typeof entry.after_data === 'object' && entry.after_data !== null && !Array.isArray(entry.after_data) ? entry.after_data as Row : {};
  return Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).filter((key) => JSON.stringify(before[key]) !== JSON.stringify(after[key])).map((key) => ({ key, before: before[key], after: after[key] }));
}
function auditDestination(entry: Row) {
  const id = encodeURIComponent(text(entry.resource_id));
  const destinations: Record<string, string> = {
    admin_account: '/system?tab=admins', admin_role: '/system?tab=roles', system_setting: '/system?tab=settings',
    community_report: `/community?tab=reports&report_id=${id}`, community_profile: `/community?tab=verifications&user_id=${id}`, community_post: '/community?tab=posts', community_tag: '/community?tab=tags',
    conversation: `/diagnosis?conversation_id=${id}`, husbandry_case: `/husbandry?case_id=${id}`, work_item: '/queue?status=active',
    knowledge_source: '/knowledge', system_model: '/models', background_job: '/diagnosis?tab=jobs', risk_incident: '/operations', file: '/knowledge',
  };
  return destinations[text(entry.resource_type)] ?? '/system?tab=audit';
}

function AuditActionBadge({ action }: { action: string }) { return <span className={`audit-action-badge ${auditActionTone(action)}`} title={action}>{auditActionLabel(action)}</span>; }

function AuditLogsPanel({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const [action, setAction] = useState('');
  const [actor, setActor] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [highRiskOnly, setHighRiskOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Row | null>(null);
  const pageSize = 20;
  const path = useMemo(() => '/audit-logs?' + new URLSearchParams({ page: String(page), page_size: String(pageSize), ...(action ? { action } : {}), ...(actor.trim() ? { actor: actor.trim() } : {}), ...(dateFrom ? { date_from: dateFrom } : {}), ...(dateTo ? { date_to: dateTo } : {}), ...(highRiskOnly ? { high_risk_only: 'true' } : {}) }).toString(), [action, actor, dateFrom, dateTo, highRiskOnly, page]);
  const resource = useResource<ListResponse>(session, path);
  const items = asItems(resource.data);
  const total = number(resource.data?.total);
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const resetFilters = () => { setAction(''); setActor(''); setDateFrom(''); setDateTo(''); setHighRiskOnly(false); setPage(1); };
  const goToObject = (entry: Row) => { window.location.hash = auditDestination(entry); setSelected(null); };
  const exportCurrentPage = () => {
    if (!items.length) { onToast('当前没有可导出的审计记录'); return; }
    const quote = (value: unknown) => `"${auditValue(value).replace(/"/g, '""')}"`;
    const lines = [['时间', '操作者', '邮箱', '操作', '对象类型', '对象 ID', '理由', 'IP', '请求编号'], ...items.map((entry) => [dateTime(entry.created_at), text(entry.actor_name, '系统'), text(entry.actor_email), auditActionLabel(text(entry.action)), auditResourceLabel(text(entry.resource_type)), text(entry.resource_id), text(entry.reason), text(entry.ip_address), text(entry.request_id)])].map((row) => row.map(quote).join(','));
    const url = URL.createObjectURL(new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a'); link.href = url; link.download = `canw-audit-${new Date().toISOString().slice(0, 10)}-page-${page}.csv`; link.click(); URL.revokeObjectURL(url); onToast(`已导出当前第 ${page} 页审计记录`);
  };
  useEffect(() => { setPage(1); }, [action, actor, dateFrom, dateTo, highRiskOnly]);
  useEffect(() => { if (page > totalPages) setPage(totalPages); }, [page, totalPages]);
  return <section className="audit-console">
    <header className="audit-console-header"><div><span className="eyebrow">AUDIT TRAIL</span><h3>查清每一次关键变更</h3><p>按风险、时间与操作者收窄记录；变更字段和来源信息可直接核对。</p></div><div className="audit-console-count"><b>{total.toLocaleString('zh-CN')}</b><span>{highRiskOnly ? '高风险记录' : '匹配记录'}</span></div></header>
    <div className="audit-filter-bar audit-filter-bar-v2">
      <label>动作<select value={action} onChange={(event) => setAction(event.target.value)}><option value="">全部动作</option><option value="admins.status_changed">账号状态变更</option><option value="admins.roles_changed">管理员角色变更</option><option value="roles.created">创建角色</option><option value="roles.updated">更新角色</option><option value="roles.deleted">删除角色</option><option value="sensitive_access.granted">授予敏感查看</option><option value="community.report_reviewed">处理社区举报</option><option value="settings.updated">更新系统设置</option><option value="models.updated">更新系统模型</option></select></label>
      <label>开始日期<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
      <label>结束日期<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} min={dateFrom || undefined} /></label>
      <label>操作者<input value={actor} onChange={(event) => setActor(event.target.value)} placeholder="姓名或邮箱" /></label>
      <label className="audit-risk-toggle"><input type="checkbox" checked={highRiskOnly} onChange={(event) => setHighRiskOnly(event.target.checked)} /><span>仅看高风险</span></label>
      <div className="audit-filter-actions"><button type="button" className="quiet-button" onClick={resetFilters}>重置筛选</button><button type="button" className="primary-button" onClick={exportCurrentPage}>导出当前页 CSV</button></div>
    </div>
    <div className="audit-result-bar"><span>{resource.loading ? '正在更新审计记录…' : `共 ${total.toLocaleString('zh-CN')} 条，第 ${Math.min(page, totalPages)} / ${totalPages} 页`}</span><span>高风险操作以红色标签提示</span></div>
    <article className="panel audit-table-panel"><LoadingState loading={resource.loading} error={resource.error}><SimpleTable columns={['时间', '操作者', '操作', '对象', '理由', '来源', '详情']} rows={items} render={(entry) => [
      dateTime(entry.created_at),
      <div key="actor"><strong>{text(entry.actor_name, '系统')}</strong><small>{text(entry.actor_email, '系统任务')}</small></div>,
      <AuditActionBadge key="action" action={text(entry.action)} />,
      <button key="object" className="audit-object-link" onClick={() => goToObject(entry)}><strong>{auditResourceLabel(text(entry.resource_type))}</strong><small title={text(entry.resource_id)}>{text(entry.resource_id)}</small></button>,
      <span key="reason" className="audit-reason" title={text(entry.reason)}>{text(entry.reason, '未填写理由')}</span>,
      <span key="source" className="audit-source" title={text(entry.user_agent)}>{text(entry.ip_address, '系统任务')}</span>,
      <button key="detail" className="quiet-button" onClick={() => setSelected(entry)}>查看变更</button>,
    ]} empty="没有符合当前筛选条件的审计记录" /></LoadingState></article>
    <footer className="audit-pagination"><span>每页 20 条</span><div><button className="quiet-button" disabled={page <= 1 || resource.loading} onClick={() => setPage((current) => Math.max(1, current - 1))}>上一页</button><button className="quiet-button" disabled={page >= totalPages || resource.loading} onClick={() => setPage((current) => Math.min(totalPages, current + 1))}>下一页</button></div></footer>
    {selected && <AuditDetailModal entry={selected} onClose={() => setSelected(null)} onJump={() => goToObject(selected)} />}
  </section>;
}

function AuditDetailModal({ entry, onClose, onJump }: { entry: Row; onClose: () => void; onJump: () => void }) {
  const changes = auditChangedFields(entry);
  return <Modal title="审计变更详情" onClose={onClose}><section className="audit-detail audit-detail-v2"><div className="audit-detail-meta"><span>{dateTime(entry.created_at)}</span><span>{text(entry.actor_name, '系统')} · {text(entry.actor_email, '系统任务')}</span><span><AuditActionBadge action={text(entry.action)} /></span></div><section className="audit-detail-object"><div><span>对象</span><strong>{auditResourceLabel(text(entry.resource_type))}</strong><small>{text(entry.resource_id)}</small></div><button className="quiet-button" onClick={onJump}>查看对象</button></section><section className="audit-detail-reason"><span>操作理由</span><p>{text(entry.reason, '本次操作未填写理由。')}</p></section><section className="audit-change-panel"><header><div><span>变化字段</span><h3>{changes.length ? `共 ${changes.length} 处变更` : '未记录结构化字段差异'}</h3></div></header>{changes.length ? <div className="audit-change-list">{changes.map((change) => <article key={change.key}><strong>{change.key}</strong><div><span>变更前</span><p>{auditValue(change.before)}</p></div><div><span>变更后</span><p>{auditValue(change.after)}</p></div></article>)}</div> : <p className="audit-empty-diff">该操作没有可比较的前后字段；可通过操作理由和来源信息追溯。</p>}</section><section className="audit-origin-grid"><div><span>来源 IP</span><strong>{text(entry.ip_address, '系统任务')}</strong></div><div><span>请求编号</span><strong>{text(entry.request_id, '未提供')}</strong></div><div><span>设备信息</span><strong title={text(entry.user_agent)}>{text(entry.user_agent, '未提供')}</strong></div></section></section></Modal>;
}

type SlaDraft = { highRisk: number; standard: number };
type SlaPendingChange = { values: SlaDraft; kind: 'save' | 'default' | 'history' };
const DEFAULT_SLA_DRAFT: SlaDraft = { highRisk: 4, standard: 24 };

function readSlaDraft(value: unknown): SlaDraft {
  const source = value && typeof value === 'object' && !Array.isArray(value) ? value as Row : {};
  const highRisk = number(source.high_risk_case_sla_hours);
  const standard = number(source.standard_work_item_sla_hours);
  return {
    highRisk: highRisk >= 1 && highRisk <= 720 ? highRisk : DEFAULT_SLA_DRAFT.highRisk,
    standard: standard >= 1 && standard <= 720 ? standard : DEFAULT_SLA_DRAFT.standard,
  };
}

function slaPayload(values: SlaDraft): Row {
  return {
    high_risk_case_sla_hours: values.highRisk,
    standard_work_item_sla_hours: values.standard,
  };
}

function SystemSettingsWorkspace({ session, onToast }: { session: AdminSession; onToast: (message: string) => void }) {
  const settingsResource = useResource<ListResponse>(session, '/settings');
  const impactResource = useResource<Row>(session, '/settings/review-thresholds/impact');
  const historyResource = useResource<ListResponse>(session, '/settings/review_thresholds/history?page_size=12');
  const [draft, setDraft] = useState<SlaDraft>(DEFAULT_SLA_DRAFT);
  const [pendingChange, setPendingChange] = useState<SlaPendingChange | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const canManage = hasPermission(session, 'settings.manage');
  const reviewSetting = asItems(settingsResource.data).find((item) => text(item.key) === 'review_thresholds');
  const settingUpdatedAt = text(reviewSetting?.updated_at);
  const impact = impactResource.data ?? {};
  const activeWorkItems = (impact.active_work_items ?? {}) as Row;
  const effectiveThresholds = readSlaDraft(impact.effective_thresholds);
  const history = asItems(historyResource.data);

  useEffect(() => {
    setDraft(readSlaDraft(reviewSetting?.value));
  }, [settingUpdatedAt]);

  const validate = (values: SlaDraft): boolean => {
    if (!Number.isInteger(values.highRisk) || !Number.isInteger(values.standard) || values.highRisk < 1 || values.highRisk > 720 || values.standard < 1 || values.standard > 720) {
      setError('两项时效都必须是 1 到 720 之间的整数小时。');
      return false;
    }
    setError('');
    return true;
  };
  const requestSave = (values: SlaDraft, kind: SlaPendingChange['kind']) => {
    if (!canManage) { onToast('当前账号没有修改系统设置的权限'); return; }
    if (!validate(values)) return;
    setPendingChange({ values, kind });
  };
  const confirmSave = async () => {
    if (!pendingChange) return;
    const change = pendingChange;
    setPendingChange(null);
    const label = change.kind === 'default' ? '恢复默认 SLA' : change.kind === 'history' ? '回滚 SLA 历史版本' : '更新待办 SLA';
    const reason = await askReasonInDialog(label, {
      confirmLabel: change.kind === 'default' ? '恢复默认值' : change.kind === 'history' ? '确认回滚' : '确认保存',
      description: '此操作会重算所有进行中待办的截止时间，并在审计日志中保留前后配置与操作理由。',
    });
    if (!reason) return;
    setSaving(true);
    try {
      const result = await api<Row>('/settings/review_thresholds', session, { method: 'PUT', body: JSON.stringify({ value: slaPayload(change.values), reason }) });
      setDraft(change.values);
      onToast(`SLA 已保存，已重算 ${number(result.active_slas_recalculated)} 项进行中待办`);
      settingsResource.reload();
      impactResource.reload();
      historyResource.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '系统设置保存失败');
    } finally {
      setSaving(false);
    }
  };
  const restoreHistory = (entry: Row) => {
    const afterData = (entry.after_data ?? {}) as Row;
    const value = afterData.value;
    if (!value || typeof value !== 'object' || Array.isArray(value)) { onToast('这条历史记录没有可恢复的 SLA 配置'); return; }
    requestSave(readSlaDraft(value), 'history');
  };
  const goTo = (path: string) => { window.location.hash = path; };

  return <section className="settings-console">
    <section className="settings-hero"><div><span className="eyebrow">CONTROL CENTER</span><h3>把平台规则变成<br />可预览、可回滚的操作。</h3><p>当前设置中心只开放已经接入并会真实生效的 SLA 规则。风险规则、模型和服务健康使用各自的专用入口，避免误操作跨域影响。</p></div><div className="settings-hero-status"><span>进行中待办</span><strong>{number(activeWorkItems.total)}</strong><small>保存后将同步重算截止时间</small></div></section>

    <section className="settings-overview-grid" aria-label="设置范围">
      <article className="settings-overview-card active"><span><Clock3 size={16} />待办时效</span><strong>已接入</strong><p>高风险病例和普通待办的 SLA，保存后立即重算。</p></article>
      <article className="settings-overview-card"><span><ShieldAlert size={16} />风险规则</span><strong>专用入口</strong><p>异常阈值、抑制窗口和风险事件 SLA 在风险中心维护。</p><button className="quiet-button" onClick={() => goTo('/operations?tab=risk')}>打开风险规则</button></article>
      <article className="settings-overview-card"><span><Bot size={16} />系统模型</span><strong>专用入口</strong><p>模型密钥、连通性和后台任务在模型与任务中维护。</p><button className="quiet-button" onClick={() => goTo('/models')}>打开模型与任务</button></article>
      <article className="settings-overview-card"><span><Wrench size={16} />服务健康</span><strong>专用入口</strong><p>依赖探测、维护窗口和真实健康趋势在运维中心维护。</p><button className="quiet-button" onClick={() => goTo('/operations?tab=health')}>打开服务健康</button></article>
      <article className="settings-overview-card muted"><span><Bell size={16} />通知渠道</span><strong>待接入</strong><p>站内提醒正在使用；短信和邮件尚未配置外部服务，不会模拟发送。</p></article>
    </section>

    <section className="settings-workspace">
      <article className="panel settings-sla-panel"><header className="settings-panel-heading"><div><span className="eyebrow">SLA POLICY</span><h3>待办时效规则</h3><p>高风险病例优先使用更短的响应时限；普通待办使用标准时限。</p></div><span className="settings-updated">当前生效<br /><b>{effectiveThresholds.highRisk}h / {effectiveThresholds.standard}h</b></span></header>
        <div className="settings-sla-inputs">
          <label>高风险病例 SLA<small>适用于高 / 紧急优先级待办</small><div><input type="number" min="1" max="720" step="1" value={draft.highRisk} disabled={!canManage || saving} onChange={(event) => { setDraft((current) => ({ ...current, highRisk: Number(event.target.value) })); setError(''); }} /><span>小时</span></div></label>
          <label>普通待办 SLA<small>适用于常规审核、跟进与运营待办</small><div><input type="number" min="1" max="720" step="1" value={draft.standard} disabled={!canManage || saving} onChange={(event) => { setDraft((current) => ({ ...current, standard: Number(event.target.value) })); setError(''); }} /><span>小时</span></div></label>
        </div>
        {error && <p className="form-error">{error}</p>}
        {!canManage && <p className="settings-readonly-note"><LockKeyhole size={14} />当前账号仅可查看，需 `settings.manage` 权限才能修改。</p>}
        <footer className="settings-sla-actions"><button className="quiet-button" disabled={!canManage || saving} onClick={() => requestSave(DEFAULT_SLA_DRAFT, 'default')}><RotateCcw size={14} />恢复默认</button><button className="primary-button" disabled={!canManage || saving} onClick={() => requestSave(draft, 'save')}>{saving ? '保存中…' : '预览并保存'}</button></footer>
      </article>
      <aside className="settings-impact-card"><header><span className="eyebrow">IMPACT PREVIEW</span><h3>这次修改会影响什么？</h3></header><div className="settings-impact-counts"><div><strong>{number(activeWorkItems.total)}</strong><span>进行中待办</span></div><div><strong>{number(activeWorkItems.high_risk)}</strong><span>高风险 / 紧急</span></div><div><strong>{number(activeWorkItems.standard)}</strong><span>普通待办</span></div></div><p>保存后，以上待办会按新的规则重新计算截止时间；不会改动已完成、已取消或历史记录。</p><dl><div><dt>当前逾期</dt><dd>{number(activeWorkItems.overdue)} 项</dd></div><div><dt>最早截止</dt><dd>{activeWorkItems.earliest_due_at ? dateTime(activeWorkItems.earliest_due_at) : '暂无'}</dd></div><div><dt>变更记录</dt><dd>理由 + 前后快照</dd></div></dl></aside>
    </section>

    <section className="settings-history-panel"><header className="settings-panel-heading"><div><span className="eyebrow">VERSION HISTORY</span><h3>待办时效历史</h3><p>每次保存都来自审计日志。恢复历史版本同样需要二次确认与操作理由。</p></div><button className="quiet-button" onClick={() => { settingsResource.reload(); impactResource.reload(); historyResource.reload(); }} disabled={historyResource.loading}><RefreshCcw size={14} className={historyResource.loading ? 'is-spinning' : ''} />刷新</button></header>
      <LoadingState loading={historyResource.loading} error={historyResource.error}>{history.length ? <div className="settings-history-list">{history.map((entry) => { const afterData = (entry.after_data ?? {}) as Row; const values = readSlaDraft(afterData.value); return <article key={text(entry.id)}><span className="settings-history-dot" /><div><strong>{values.highRisk}h 高风险 · {values.standard}h 普通待办</strong><p>{text(entry.reason, '未填写操作理由')}</p><small>{dateTime(entry.created_at)} · {text(entry.actor_name, '系统')}</small></div>{canManage && <button className="quiet-button" disabled={saving} onClick={() => restoreHistory(entry)}><RotateCcw size={13} />恢复此版本</button>}</article>; })}</div> : <div className="empty-selection"><Clock3 size={24} /><p>还没有 SLA 变更记录。首次保存后会在这里保留可回滚版本。</p></div>}</LoadingState>
    </section>

    {pendingChange && <Modal title={pendingChange.kind === 'default' ? '恢复默认待办时效？' : pendingChange.kind === 'history' ? '回滚到历史时效？' : '保存待办时效？'} onClose={() => !saving && setPendingChange(null)}><section className="settings-confirm"><div className="settings-confirm-icon"><SlidersHorizontal size={20} /></div><div><h3>{pendingChange.values.highRisk} 小时 / {pendingChange.values.standard} 小时</h3><p>高风险病例与普通待办的截止时间将按新规则重新计算。下一步需要填写操作理由，完整变更会写入审计日志。</p></div><div className="settings-confirm-impact"><span>受影响待办</span><strong>{number(activeWorkItems.total)} 项</strong></div><footer className="modal-actions"><button className="quiet-button" type="button" onClick={() => setPendingChange(null)}>取消</button><button className="primary-button" type="button" onClick={() => void confirmSave()}>继续填写理由</button></footer></section></Modal>}
  </section>;
}

function Tabs<T extends string>({ current, onChange, values }: { current: T; onChange: (value: T) => void; values: Array<[T, string]> }) { return <div className="segmented">{values.map(([key, label]) => <button className={current === key ? 'active' : ''} key={key} onClick={() => onChange(key)}>{label}</button>)}</div>; }
function Status({ value }: { value: string }) { const label: Record<string, string> = { active: '正常', disabled: '已禁用', pending: '待处理', reviewed: '已处置', claimed: '处理中', completed: '已完成', critical: '紧急', high: '高风险', medium: '需关注', low: '低风险', unreviewed: '待复核', draft: '草稿', published: '已发布', hidden: '已隐藏', verified: '已认证', rejected: '已驳回', unverified: '未认证', open: '待响应', acknowledged: '已确认', in_progress: '处理中', needs_more_info: '待补充', suspected: '疑似', processing: '处理中', resolved: '已解决', dismissed: '已忽略', suppressed: '已抑制', due_soon: '即将到期', overdue: '已超时', on_track: '时效正常', closed: '已结案', ready: '可用', failed: '失败', running: '运行中', enabled: '已启用', disabled_model: '已停用', normal: '正常', quarantined: '已隔离', deleted: '已删除', upload_failed: '上传失败', healthy: '正常', degraded: '降级', maintenance: '维护中', unknown: '待配置', user_reports: '社区举报', user_security: '登录异常', user_verification: '认证待审', service_health_failure: '服务不可用', repeated_login_failure: '连续登录失败', unusual_login_ip: '异常登录来源', admin_permission_change: '权限或账号变更', sensitive_admin_action: '敏感管理操作', multimodal_failure: '多模态服务失败', background_job_failure: '后台任务失败', report_surge: '举报激增', posting_spike: '异常发布频率', critical_case_overdue: '紧急病例超时', '已解锁原文': '已解锁原文', '脱敏模式': '脱敏模式' }; return <span className={`status status-${value.replace(/[^a-zA-Z0-9_-]/g, '')}`}>{label[value] ?? value}</span>; }
function PanelTitle({ icon: Icon, title, note }: { icon: LucideIcon; title: string; note: string }) { return <header className="panel-title"><div><Icon size={17} /><h3>{title}</h3></div><small>{note}</small></header>; }
function EmptySelection({ text: message }: { text: string }) { return <div className="empty-selection"><MoreHorizontal size={25} /><p>{message}</p></div>; }
function Timeline({ rows, label }: { rows: Row[]; label: (row: Row) => string }) { return <div className="timeline">{rows.length ? rows.map((row, index) => <div key={`${text(row.id, String(index))}-${index}`}><span /><p>{label(row)}</p></div>) : <p className="empty-note">暂无记录</p>}</div>; }
function SummaryChips({ data }: { data: Row }) { return <div className="summary-chips">{Object.entries(data).map(([key, value]) => <span key={key}><b>{number(value)}</b>{key.replace(/_/g, ' ')}</span>)}</div>; }
function SimpleTable({ columns, rows, render, empty }: { columns: ReactNode[]; rows: Row[]; render: (row: Row) => ReactNode[]; empty: string }) { return <div className="table-wrap"><table><thead><tr>{columns.map((column, index) => <th key={index}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={text(row.id, String(index))}>{render(row).map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table>{!rows.length && <div className="empty-table"><FileText size={20} />{empty}</div>}</div>; }
function Pagination({ total, page, pageSize, onChange }: { total: number; page: number; pageSize: number; onChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
  if (pages <= 1) return null;
  return <footer className="table-pagination"><span>共 {total} 项 · 第 {page}/{pages} 页</span><div><button className="quiet-button" disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</button><button className="quiet-button" disabled={page >= pages} onClick={() => onChange(page + 1)}>下一页</button></div></footer>;
}
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="modal modal-workbench" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}><header><div><span className="modal-kicker">CANW / 操作面板</span><h2>{title}</h2></div><button aria-label="关闭弹窗" onClick={onClose}><X size={18} /></button></header><div className="modal-content">{children}</div></section></div>;
}

function ReasonDialog({ request, onResolve }: { request: ReasonDialogRequest; onResolve: (value: string | null) => void }) {
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = reason.trim();
    if (value.length < 3) { setError('请填写至少 3 个字的处理理由。'); return; }
    onResolve(value);
  };
  return <Modal title={request.label} onClose={() => onResolve(null)}><form className="role-assignment-form reason-dialog-form" onSubmit={submit}><div className="role-assignment-heading"><div className="role-assignment-avatar"><ClipboardCheck size={19} /></div><div><span>操作确认</span><strong>{request.label}</strong><small>理由将写入审计日志</small></div></div><div className="role-assignment-note"><ShieldCheck size={16} /><span>{request.description ?? '请说明本次操作的业务原因，便于后续审计追溯。'}</span></div><label className="role-reason-field">处理理由<textarea autoFocus value={reason} onChange={(event) => { setReason(event.target.value); setError(''); }} placeholder="例如：当前负责人暂时无法继续处理，释放给公共队列。" minLength={3} required /></label>{error && <p className="form-error">{error}</p>}<footer className="modal-actions"><button className="quiet-button" type="button" onClick={() => onResolve(null)}>取消</button><button className={request.tone === 'danger' ? 'danger-button' : 'primary-button'}>{request.confirmLabel ?? '确认操作'}</button></footer></form></Modal>;
}

export default App;

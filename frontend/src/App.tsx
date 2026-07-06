import { useEffect, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import clsx from 'clsx';
import type { LucideIcon } from 'lucide-react';
import {
  Bot,
  Brain,
  Camera,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleUserRound,
  Clock3,
  Database,
  FileSearch,
  FileText,
  Folder,
  FolderOpen,
  GitBranch,
  History,
  ImageUp,
  Leaf,
  LogOut,
  Mail,
  MessageSquarePlus,
  Mic,
  MoreHorizontal,
  PanelLeft,
  PencilLine,
  Phone,
  Plus,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
  Upload,
  UploadCloud,
  UserRound,
  Video,
  Workflow,
  X,
} from 'lucide-react';

type ThreadKey = 'diagnosis' | 'video' | 'history' | 'memory' | 'tools' | 'settings' | 'login';
type AuthMode = 'phone' | 'email';

type AuthUser = {
  id: string;
  display_name: string;
  username: string;
  email: string;
  phone_number: string;
  avatar_url: string | null;
};

type AuthSessionState = {
  accessToken: string;
  refreshToken: string;
  user: AuthUser;
};

type EmailVerificationCodeResponse = {
  status: string;
  email?: string;
  phone_number?: string;
  expires_in: number;
  dev_code?: string | null;
};

type EmailLoginResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
};

type LogoutResponse = {
  status: string;
};

type RefreshTokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
};

class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
  }
}

const AUTH_STORAGE_KEY = 'canw.auth';
const API_BASE_URLS = import.meta.env.VITE_API_BASE_URL
  ? [import.meta.env.VITE_API_BASE_URL]
  : ['http://127.0.0.1:8000/api/v1', 'http://127.0.0.1:8010/api/v1'];

type SidebarAction = {
  key: ThreadKey;
  icon: LucideIcon;
  label: string;
};

const sidebarActions: SidebarAction[] = [
  { key: 'diagnosis', icon: MessageSquarePlus, label: '新问诊' },
  { key: 'video', icon: Video, label: '视频咨询' },
  { key: 'history', icon: Search, label: '搜索' },
  { key: 'memory', icon: Brain, label: '记忆系统' },
  { key: 'tools', icon: Workflow, label: '工具入口' },
];

type ProjectChat = {
  id: string;
  key: ThreadKey;
  title: string;
  time: string;
};

const projectFolders: Array<{ id: string; name: string; chats: ProjectChat[] }> = [
  {
    id: 'silkworm-assistant',
    name: '家蚕疾病智能体',
    chats: [
      { id: 'diagnosis-white-hard', key: 'diagnosis', title: '蚕体发白变硬，帮我判断可能原因', time: '20 分' },
      { id: 'video-fifth-instar', key: 'video', title: '上传一段五龄蚕视频做症状分析', time: '1 天' },
      { id: 'memory-farm-profile', key: 'memory', title: '保存我的养殖地区和常见咨询', time: '3 天' },
      { id: 'tools-graph-source', key: 'tools', title: '查看疾病关系图谱和引用来源', time: '5 天' },
    ],
  },
  {
    id: 'knowledge-graph',
    name: '知识图谱构建',
    chats: [
      { id: 'kg-entity-relation', key: 'tools', title: '家蚕疾病图谱实体与关系整理', time: '1 小时' },
      { id: 'kg-neo4j-path', key: 'tools', title: 'Neo4j 检索路径与问答联动', time: '10 小时' },
    ],
  },
  {
    id: 'case-memory',
    name: '病例与记忆管理',
    chats: [
      { id: 'history-case-summary', key: 'history', title: '历史病例摘要与标签推荐', time: '4 天' },
      { id: 'memory-privacy-control', key: 'memory', title: '长期记忆写入与隐私控制', time: '4 天' },
    ],
  },
];

function getProjectChatId(thread: ThreadKey) {
  for (const folder of projectFolders) {
    const chat = folder.chats.find((item) => item.key === thread);
    if (chat) return chat.id;
  }
  return null;
}

const evidenceRows = [
  { name: '《家蚕病理学》症状片段', type: '文本证据', score: '0.87' },
  { name: '白僵病 -> 症状 -> 蚕体僵硬', type: 'Neo4j 路径', score: '2 跳' },
  { name: '发白、变硬、白色菌丝', type: 'BM25 命中词', score: '12.4' },
];

const memoryFacts = [
  ['memory_type', 'fact'],
  ['content', '该用户养蚕环境湿度较高'],
  ['timestamp', '2026-07-01'],
];

const historyRows = [
  { title: '蚕体发白变硬咨询', tag: '白僵病', summary: '疑似白僵病，建议确认白色菌丝和蚕室湿度。', time: '2026-06-30' },
  { title: '食桑减少与眠起不齐', tag: '信息不足', summary: '建议补充蚕龄、发病比例、桑叶和眠起情况。', time: '2026-06-28' },
  { title: '微粒子病传播方式查询', tag: '微粒子病', summary: '查询了病原、传播路径和防控重点。', time: '2026-06-23' },
];

function readStoredAuth(): AuthSessionState | null {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthSessionState) : null;
  } catch {
    return null;
  }
}

function saveStoredAuth(authState: AuthSessionState) {
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(authState));
}

function clearStoredAuth() {
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
}

function getAvatarLabel(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return '用';
  const compact = trimmed.match(/[A-Za-z0-9]+/g)?.join('') || trimmed;
  return Array.from(compact).slice(0, 2).join('').toUpperCase();
}

function getDefaultUsername(email: string) {
  return email.split('@', 1)[0] || 'user';
}

function getAccountIdentifier(user: AuthUser | null) {
  if (!user) return '';
  return user.email || user.phone_number || '';
}

function isUnauthorizedError(error: unknown) {
  return error instanceof ApiRequestError && error.status === 401;
}

function fileToAvatarDataUrl(file: File): Promise<string> {
  if (!file.type.startsWith('image/')) {
    return Promise.reject(new Error('请选择图片文件'));
  }
  if (file.size > 3 * 1024 * 1024) {
    return Promise.reject(new Error('头像图片不能超过 3MB'));
  }

  return new Promise((resolve, reject) => {
    const image = new Image();
    const objectUrl = URL.createObjectURL(file);

    image.onload = () => {
      const size = 256;
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d');
      if (!context) {
        URL.revokeObjectURL(objectUrl);
        reject(new Error('头像处理失败'));
        return;
      }

      canvas.width = size;
      canvas.height = size;
      const sourceSize = Math.min(image.naturalWidth, image.naturalHeight);
      const sourceX = (image.naturalWidth - sourceSize) / 2;
      const sourceY = (image.naturalHeight - sourceSize) / 2;
      context.drawImage(image, sourceX, sourceY, sourceSize, sourceSize, 0, 0, size, size);
      URL.revokeObjectURL(objectUrl);
      resolve(canvas.toDataURL('image/jpeg', 0.88));
    };

    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error('头像读取失败'));
    };

    image.src = objectUrl;
  });
}

async function requestEmailVerificationCode(email: string): Promise<EmailVerificationCodeResponse> {
  return apiPost<EmailVerificationCodeResponse>('/auth/email/verification-codes', { email });
}

async function requestPhoneVerificationCode(phoneNumber: string): Promise<EmailVerificationCodeResponse> {
  return apiPost<EmailVerificationCodeResponse>('/auth/phone/verification-codes', { phone_number: phoneNumber });
}

async function loginWithEmailCode(email: string, code: string): Promise<EmailLoginResponse> {
  return apiPost<EmailLoginResponse>('/auth/email/login', {
    email,
    code,
    device_name: window.navigator.userAgent,
  });
}

async function loginWithPhoneCode(phoneNumber: string, code: string): Promise<EmailLoginResponse> {
  return apiPost<EmailLoginResponse>('/auth/phone/login', {
    phone_number: phoneNumber,
    code,
    device_name: window.navigator.userAgent,
  });
}

async function refreshAuthToken(refreshToken: string): Promise<RefreshTokenResponse> {
  return apiPost<RefreshTokenResponse>('/auth/refresh', {
    refresh_token: refreshToken,
  });
}

async function logoutWithRefreshToken(refreshToken: string): Promise<LogoutResponse> {
  return apiPost<LogoutResponse>('/auth/logout', {
    refresh_token: refreshToken,
  });
}

async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  return apiRequest<T>(path, {
    method: 'POST',
    payload,
  });
}

async function fetchCurrentUserProfile(accessToken: string): Promise<AuthUser> {
  return apiRequest<AuthUser>('/auth/me', {
    accessToken,
  });
}

async function updateUserProfile(
  accessToken: string,
  profile: { displayName: string; username: string; avatarUrl: string | null },
): Promise<AuthUser> {
  return apiRequest<AuthUser>('/auth/me', {
    method: 'PATCH',
    accessToken,
    payload: {
      display_name: profile.displayName,
      username: profile.username,
      avatar_url: profile.avatarUrl,
    },
  });
}

async function apiRequest<T>(
  path: string,
  options: { method?: string; payload?: unknown; accessToken?: string } = {},
): Promise<T> {
  let lastError = '请求失败';
  let lastApiError: ApiRequestError | null = null;
  const method = options.method ?? 'GET';

  for (const baseUrl of API_BASE_URLS) {
    try {
      const headers: Record<string, string> = {};
      if (options.payload !== undefined) {
        headers['Content-Type'] = 'application/json';
      }
      if (options.accessToken) {
        headers.Authorization = `Bearer ${options.accessToken}`;
      }

      const response = await fetch(`${baseUrl}${path}`, {
        method,
        headers,
        body: options.payload !== undefined ? JSON.stringify(options.payload) : undefined,
      });
      const data = await response.json().catch(() => null);

      if (response.ok) {
        return data as T;
      }

      lastError = data?.detail || `请求失败：${response.status}`;
      lastApiError = new ApiRequestError(lastError, response.status);
      if (response.status !== 404 || import.meta.env.VITE_API_BASE_URL) {
        throw lastApiError;
      }
    } catch (error) {
      if (error instanceof ApiRequestError) {
        lastApiError = error;
        lastError = error.message;
      } else {
        lastError = error instanceof Error ? error.message : '网络连接失败';
      }
      if (import.meta.env.VITE_API_BASE_URL) {
        throw error instanceof ApiRequestError ? error : new Error(lastError);
      }
    }
  }

  if (lastApiError) {
    throw lastApiError;
  }
  throw new Error(lastError);
}

function App() {
  const [activeThread, setActiveThread] = useState<ThreadKey>('diagnosis');
  const [activeProjectChatId, setActiveProjectChatId] = useState<string | null>('diagnosis-white-hard');
  const [authState, setAuthState] = useState<AuthSessionState | null>(() => readStoredAuth());
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const isAuthenticated = Boolean(authState);

  const handleAuthExpired = () => {
    clearStoredAuth();
    setAuthState(null);
    setProfileModalOpen(false);
    setAuthModalOpen(true);
  };

  const handleTokenRefresh = async () => {
    if (!authState?.refreshToken) {
      handleAuthExpired();
      throw new Error('登录状态已失效');
    }

    try {
      const response = await refreshAuthToken(authState.refreshToken);
      const nextAuthState = {
        accessToken: response.access_token,
        refreshToken: authState.refreshToken,
        user: response.user,
      };
      saveStoredAuth(nextAuthState);
      setAuthState(nextAuthState);
      return nextAuthState;
    } catch (error) {
      if (isUnauthorizedError(error)) {
        handleAuthExpired();
      }
      throw error;
    }
  };

  useEffect(() => {
    if (!authState?.accessToken || !authState.refreshToken) return;

    let ignore = false;

    const syncAuthProfile = async () => {
      try {
        const user = await fetchCurrentUserProfile(authState.accessToken);
        if (ignore) return;
        const nextAuthState = { ...authState, user };
        saveStoredAuth(nextAuthState);
        setAuthState(nextAuthState);
      } catch (error) {
        if (ignore || !isUnauthorizedError(error)) return;
        try {
          await handleTokenRefresh();
        } catch {
          if (!ignore) handleAuthExpired();
        }
      }
    };

    void syncAuthProfile();

    return () => {
      ignore = true;
    };
  }, [authState?.refreshToken]);

  const handleSignOut = async () => {
    const refreshToken = authState?.refreshToken;

    clearStoredAuth();
    setAuthState(null);
    setProfileModalOpen(false);

    if (!refreshToken) return;

    try {
      await logoutWithRefreshToken(refreshToken);
    } catch {
      // Local logout should still complete if the network request fails.
    }
  };

  const handleThreadSelect = (thread: ThreadKey) => {
    setActiveThread(thread);
    setActiveProjectChatId(getProjectChatId(thread));
  };

  const handleProjectChatSelect = (thread: ThreadKey, chatId: string) => {
    setActiveThread(thread);
    setActiveProjectChatId(chatId);
  };

  const handleProfileSaved = (user: AuthUser) => {
    setAuthState((currentAuthState) => {
      if (!currentAuthState) return currentAuthState;

      const nextAuthState = {
        ...currentAuthState,
        user,
      };
      saveStoredAuth(nextAuthState);
      return nextAuthState;
    });
  };

  const threadTitle = useMemo(() => {
    if (activeThread === 'video') return '视频咨询：上传短视频后生成症状摘要';
    if (activeThread === 'history') return '历史对话：病例摘要、标签与相似推荐';
    if (activeThread === 'memory') return '记忆系统：短期记忆、长期记忆与 Memory Agent';
    if (activeThread === 'tools') return '工具入口：图谱、RAG、诊断模式和上传能力';
    if (activeThread === 'settings') return '设置系统：模型、知识源、记忆、隐私与 UI';
    if (activeThread === 'login') return '账号与登录：手机号、邮箱和会话状态';
    return '蚕体发白变硬，帮我判断可能原因';
  }, [activeThread]);

  return (
    <main className={clsx('app-frame', sidebarCollapsed && 'sidebar-collapsed')}>
      <Sidebar
        activeThread={activeThread}
        activeProjectChatId={activeProjectChatId}
        collapsed={sidebarCollapsed}
        isAuthenticated={isAuthenticated}
        authUser={authState?.user ?? null}
        onSelect={handleThreadSelect}
        onProjectSelect={handleProjectChatSelect}
        onToggleSidebar={() => setSidebarCollapsed((collapsed) => !collapsed)}
        onOpenAuth={() => setAuthModalOpen(true)}
        onOpenProfile={() => setProfileModalOpen(true)}
        onSignOut={() => {
          void handleSignOut();
        }}
      />
      <section className="thread-area">
        <ThreadHeader title={threadTitle} />
        <div className="thread-scroll">
          {activeThread === 'diagnosis' && <DiagnosisThread />}
          {activeThread === 'video' && <VideoThread />}
          {activeThread === 'history' && <HistoryThread />}
          {activeThread === 'memory' && <MemoryThread />}
          {activeThread === 'tools' && <ToolsThread />}
          {activeThread === 'settings' && <SettingsThread />}
          {activeThread === 'login' && <LoginThread />}
        </div>
        <Composer />
      </section>
      <AuthModal
        open={authModalOpen}
        onClose={() => setAuthModalOpen(false)}
        onSuccess={(nextAuthState) => {
          saveStoredAuth(nextAuthState);
          setAuthState(nextAuthState);
          setAuthModalOpen(false);
        }}
      />
      <ProfileModal
        open={profileModalOpen}
        authState={authState}
        onClose={() => setProfileModalOpen(false)}
        onAuthExpired={handleAuthExpired}
        onSaved={handleProfileSaved}
        onTokenRefresh={handleTokenRefresh}
      />
    </main>
  );
}

function Sidebar({
  activeThread,
  activeProjectChatId,
  collapsed,
  isAuthenticated,
  authUser,
  onSelect,
  onProjectSelect,
  onToggleSidebar,
  onOpenAuth,
  onOpenProfile,
  onSignOut,
}: {
  activeThread: ThreadKey;
  activeProjectChatId: string | null;
  collapsed: boolean;
  isAuthenticated: boolean;
  authUser: AuthUser | null;
  onSelect: (thread: ThreadKey) => void;
  onProjectSelect: (thread: ThreadKey, chatId: string) => void;
  onToggleSidebar: () => void;
  onOpenAuth: () => void;
  onOpenProfile: () => void;
  onSignOut: () => void;
}) {
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);

  const handleAccountClick = () => {
    if (!isAuthenticated) {
      setAccountMenuOpen(false);
      onOpenAuth();
      return;
    }

    setAccountMenuOpen((open) => !open);
  };

  return (
    <aside className="app-sidebar">
      <div className="window-bar">
        <div className="sidebar-brand" aria-label="CanW">
          <strong>CanW</strong>
        </div>
        <button
          type="button"
          aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          aria-pressed={collapsed}
          onClick={() => {
            setAccountMenuOpen(false);
            onToggleSidebar();
          }}
        >
          <PanelLeft className={clsx(collapsed && 'rotated')} size={16} />
        </button>
      </div>

      <nav className="primary-actions" aria-label="用户端主操作">
        {sidebarActions.map((action) => {
          const Icon = action.icon;
          return (
            <button
              className={clsx('sidebar-action', activeThread === action.key && 'active')}
              key={action.key}
              onClick={() => onSelect(action.key)}
              type="button"
            >
              <Icon size={17} />
              <span>{action.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-section">
        <span className="sidebar-label">项目</span>
        {projectFolders.map((folder) => {
          const firstChat = folder.chats[0];
          const isFolderActive = folder.chats.some((chat) => chat.id === activeProjectChatId);

          return (
            <div className="project-folder" key={folder.id}>
              <button
                className={clsx('project-folder-row', isFolderActive && 'active')}
                onClick={() => onProjectSelect(firstChat.key, firstChat.id)}
                type="button"
              >
                {isFolderActive ? <FolderOpen size={16} /> : <Folder size={16} />}
                <span>{folder.name}</span>
                {isFolderActive && (
                  <>
                    <ChevronDown className="project-folder-icon" size={14} />
                    <MoreHorizontal className="project-folder-icon" size={15} />
                    <PencilLine className="project-folder-icon" size={14} />
                  </>
                )}
              </button>
              <div className="project-thread-list">
                {folder.chats.map((chat) => (
                  <button
                    className={clsx('project-thread', activeProjectChatId === chat.id && 'selected')}
                    key={chat.id}
                    onClick={() => onProjectSelect(chat.key, chat.id)}
                    type="button"
                  >
                    <span>{chat.title}</span>
                    <small>{chat.time}</small>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
        <button className="project-more" type="button">
          展开显示
        </button>
      </div>

      <div className="sidebar-section">
        <span className="sidebar-label">对话</span>
        {historyRows.length > 0 ? (
          historyRows.map((row) => (
            <button className="thread-link" type="button" key={row.title} onClick={() => onSelect('history')}>
              <FileText size={15} />
              <span>{row.title}</span>
              <small>{row.tag}</small>
            </button>
          ))
        ) : (
          <div className="empty-chat">暂无聊天</div>
        )}
      </div>

      <div className="account-region">
        {isAuthenticated && accountMenuOpen && !collapsed && (
          <div className="account-menu" role="menu" aria-label="账号菜单">
            <button className="account-menu-muted" type="button" role="menuitem">
              <CircleUserRound size={16} />
              <span>{getAccountIdentifier(authUser)}</span>
            </button>
            <button type="button" role="menuitem" onClick={() => onSelect('login')}>
              <UserRound size={16} />
              <span>个人账户</span>
            </button>
            <div className="account-menu-separator" />
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setAccountMenuOpen(false);
                onOpenProfile();
              }}
            >
              <CircleUserRound size={16} />
              <span>个人资料</span>
            </button>
            <button type="button" role="menuitem" onClick={() => onSelect('settings')}>
              <Settings2 size={16} />
              <span>设置</span>
              <small>Ctrl+,</small>
            </button>
            <button
              className="account-menu-danger"
              type="button"
              role="menuitem"
              onClick={() => {
                setAccountMenuOpen(false);
                onSignOut();
              }}
            >
              <LogOut size={16} />
              <span>退出登录</span>
            </button>
          </div>
        )}
        <button
          className={clsx('account-card', !isAuthenticated && 'unauthenticated')}
          type="button"
          onClick={handleAccountClick}
          aria-expanded={accountMenuOpen}
          aria-haspopup={isAuthenticated ? 'menu' : 'dialog'}
        >
          {isAuthenticated ? (
            <>
              <div className={clsx('avatar-mini', authUser?.avatar_url && 'has-image')}>
                {authUser?.avatar_url ? (
                  <img alt="" src={authUser.avatar_url} />
                ) : (
                  getAvatarLabel(authUser?.display_name || getAccountIdentifier(authUser))
                )}
              </div>
              <div>
                <strong>{authUser?.display_name || 'CanW 用户'}</strong>
              </div>
            </>
          ) : (
            <>
              <div className="avatar-mini auth-avatar">
                <UserRound size={17} />
              </div>
              <div>
                <strong>登录</strong>
              </div>
              <ChevronRight className="account-card-arrow" size={16} />
            </>
          )}
        </button>
      </div>
    </aside>
  );
}

function AuthModal({
  open,
  onClose,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess: (authState: AuthSessionState) => void;
}) {
  const [mode, setMode] = useState<AuthMode>('email');
  const [account, setAccount] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [codeCooldown, setCodeCooldown] = useState(0);
  const isPhoneMode = mode === 'phone';

  useEffect(() => {
    if (!open) return;

    setMode('email');
    setAccount('');
    setVerificationCode('');
    setMessage('');
    setError('');
    setIsSendingCode(false);
    setIsLoggingIn(false);
    setCodeCooldown(0);
  }, [open]);

  useEffect(() => {
    if (!open || codeCooldown <= 0) return;

    const timer = window.setInterval(() => {
      setCodeCooldown((currentCooldown) => Math.max(currentCooldown - 1, 0));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [codeCooldown, open]);

  if (!open) return null;

  const setAuthMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setAccount('');
    setVerificationCode('');
    setMessage('');
    setError('');
    setCodeCooldown(0);
  };

  const handleRequestCode = async () => {
    if (codeCooldown > 0) {
      return;
    }

    setError('');
    setMessage('');
    setIsSendingCode(true);

    try {
      const response = isPhoneMode
        ? await requestPhoneVerificationCode(account)
        : await requestEmailVerificationCode(account);
      if (response.dev_code) {
        setVerificationCode(response.dev_code);
        setMessage(`开发验证码已自动填入：${response.dev_code}`);
      } else {
        setMessage(`验证码已发送至 ${response.email || response.phone_number}`);
      }
      setCodeCooldown(60);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '验证码发送失败');
    } finally {
      setIsSendingCode(false);
    }
  };

  const handleLogin = async () => {
    setError('');
    setMessage('');
    setIsLoggingIn(true);

    try {
      const response = isPhoneMode
        ? await loginWithPhoneCode(account, verificationCode)
        : await loginWithEmailCode(account, verificationCode);
      onSuccess({
        accessToken: response.access_token,
        refreshToken: response.refresh_token,
        user: response.user,
      });
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : '登录失败');
    } finally {
      setIsLoggingIn(false);
    }
  };

  return (
    <div className="auth-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="auth-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="auth-close" type="button" aria-label="关闭登录窗口" onClick={onClose}>
          <X size={18} />
        </button>

        <div className="auth-mark" aria-hidden="true">
          <span>CanW</span>
        </div>

        <header className="auth-header">
          <h2 id="auth-title">欢迎来到CanW</h2>
        </header>

        <div className="auth-tabs" role="tablist" aria-label="登录方式">
          <button
            className={clsx(isPhoneMode && 'active')}
            type="button"
            role="tab"
            aria-selected={isPhoneMode}
            onClick={() => setAuthMode('phone')}
          >
            <Phone size={16} />
            手机号
          </button>
          <button
            className={clsx(!isPhoneMode && 'active')}
            type="button"
            role="tab"
            aria-selected={!isPhoneMode}
            onClick={() => setAuthMode('email')}
          >
            <Mail size={16} />
            邮箱
          </button>
        </div>

        <form
          className="auth-form"
          onSubmit={(event) => {
            event.preventDefault();
            void handleLogin();
          }}
        >
          <label>
            <span>{isPhoneMode ? '手机号' : '邮箱地址'}</span>
            <div className="auth-input-shell">
              {isPhoneMode ? <Phone size={16} /> : <Mail size={16} />}
              <input
                autoFocus
                disabled={isSendingCode || isLoggingIn}
                inputMode={isPhoneMode ? 'tel' : 'email'}
                onChange={(event) => setAccount(event.target.value)}
                placeholder={isPhoneMode ? '请输入手机号' : '请输入 QQ 或网易邮箱'}
                type={isPhoneMode ? 'tel' : 'email'}
                value={account}
              />
            </div>
          </label>

          <label>
            <span>验证码</span>
            <div className="auth-code-row">
              <div className="auth-input-shell">
                <ShieldCheck size={16} />
                <input
                  disabled={isSendingCode || isLoggingIn}
                  inputMode="numeric"
                  maxLength={6}
                  onChange={(event) => setVerificationCode(event.target.value)}
                  placeholder="6 位验证码"
                  value={verificationCode}
                />
              </div>
              <button
                className="auth-code-button"
                disabled={codeCooldown > 0 || isSendingCode || isLoggingIn}
                onClick={() => void handleRequestCode()}
                type="button"
              >
                {isSendingCode ? '发送中' : codeCooldown > 0 ? `${codeCooldown}s` : '获取验证码'}
              </button>
            </div>
          </label>

          {(message || error) && (
            <p className={clsx('auth-message', error && 'error')} role="status">
              {error || message}
            </p>
          )}

          <button className="auth-submit" disabled={isSendingCode || isLoggingIn} type="submit">
            {isLoggingIn ? '登录中' : '登录'}
          </button>
        </form>

        <p className="auth-note">登陆账号，开始使用CanW</p>
      </section>
    </div>
  );
}

function ProfileModal({
  open,
  authState,
  onClose,
  onAuthExpired,
  onSaved,
  onTokenRefresh,
}: {
  open: boolean;
  authState: AuthSessionState | null;
  onClose: () => void;
  onAuthExpired: () => void;
  onSaved: (user: AuthUser) => void;
  onTokenRefresh: () => Promise<AuthSessionState>;
}) {
  const [displayName, setDisplayName] = useState('');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [avatarUrl, setAvatarUrl] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open || !authState) return;

    let ignore = false;
    setDisplayName(authState.user.display_name);
    setUsername(authState.user.username || getDefaultUsername(authState.user.email || authState.user.phone_number));
    setEmail(getAccountIdentifier(authState.user));
    setAvatarUrl(authState.user.avatar_url ?? null);
    setMessage('');
    setError('');
    setIsSaving(false);
    setIsLoading(true);

    const loadProfile = async () => {
      try {
        let user: AuthUser;
        try {
          user = await fetchCurrentUserProfile(authState.accessToken);
        } catch (profileError) {
          if (!isUnauthorizedError(profileError)) throw profileError;
          const refreshedAuthState = await onTokenRefresh();
          user = await fetchCurrentUserProfile(refreshedAuthState.accessToken);
        }

        if (ignore) return;
        setDisplayName(user.display_name);
        setUsername(user.username || getDefaultUsername(user.email || user.phone_number));
        setEmail(getAccountIdentifier(user));
        setAvatarUrl(user.avatar_url ?? null);
      } catch (profileError) {
        if (ignore) return;
        if (isUnauthorizedError(profileError)) {
          onAuthExpired();
          return;
        }
        setError(profileError instanceof Error ? profileError.message : '资料同步失败');
      } finally {
        if (!ignore) setIsLoading(false);
      }
    };

    void loadProfile();

    return () => {
      ignore = true;
    };
  }, [
    open,
    authState?.accessToken,
    authState?.user.avatar_url,
    authState?.user.display_name,
    authState?.user.email,
    authState?.user.phone_number,
    authState?.user.username,
    authState,
    onAuthExpired,
    onTokenRefresh,
  ]);

  if (!open || !authState) return null;

  const handleAvatarChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    setError('');
    setMessage('');

    try {
      const nextAvatarUrl = await fileToAvatarDataUrl(file);
      setAvatarUrl(nextAvatarUrl);
      setMessage('头像已选择，保存后生效');
    } catch (avatarError) {
      setError(avatarError instanceof Error ? avatarError.message : '头像处理失败');
    }
  };

  const handleSaveProfile = async () => {
    const nextDisplayName = displayName.trim();
    if (!nextDisplayName) {
      setError('显示名称不能为空');
      return;
    }

    const nextUsername = username.trim();
    if (!nextUsername) {
      setError('用户名不能为空');
      return;
    }

    setError('');
    setMessage('');
    setIsSaving(true);

    try {
      let user: AuthUser;
      try {
        user = await updateUserProfile(authState.accessToken, {
          displayName: nextDisplayName,
          username: nextUsername,
          avatarUrl,
        });
      } catch (saveError) {
        if (!isUnauthorizedError(saveError)) throw saveError;
        const refreshedAuthState = await onTokenRefresh();
        user = await updateUserProfile(refreshedAuthState.accessToken, {
          displayName: nextDisplayName,
          username: nextUsername,
          avatarUrl,
        });
      }

      onSaved(user);
      setMessage('已保存');
      onClose();
    } catch (saveError) {
      if (isUnauthorizedError(saveError)) {
        onAuthExpired();
        return;
      }
      setError(saveError instanceof Error ? saveError.message : '资料保存失败');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="auth-overlay profile-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="profile-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="profile-header">
          <h2 id="profile-title">编辑个人资料</h2>
        </header>

        <form
          className="profile-form"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSaveProfile();
          }}
        >
          <div className="profile-avatar-editor">
            <button
              className={clsx('profile-avatar-button', avatarUrl && 'has-image')}
              type="button"
              aria-label="编辑头像"
              onClick={() => avatarInputRef.current?.click()}
            >
              {avatarUrl ? <img alt="" src={avatarUrl} /> : <span>{getAvatarLabel(displayName || username || email)}</span>}
            </button>
            <button
              className="profile-camera-button"
              type="button"
              aria-label="选择头像图片"
              onClick={() => avatarInputRef.current?.click()}
            >
              <Camera size={17} />
            </button>
            <input ref={avatarInputRef} hidden accept="image/*" type="file" onChange={handleAvatarChange} />
          </div>

          <label className="profile-field">
            <span>显示名称</span>
            <div>
              <input
                disabled={isSaving}
                maxLength={64}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="请输入显示名称"
                value={displayName}
              />
            </div>
          </label>

          <label className="profile-field">
            <span>用户名</span>
            <div>
              <input
                disabled={isSaving}
                maxLength={32}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="请输入用户名"
                value={username}
              />
            </div>
          </label>

          {(isLoading || message || error) && (
            <p className={clsx('auth-message', error && 'error')} role="status">
              {error || message || '正在同步资料'}
            </p>
          )}

          <p className="profile-help">你的个人资料有助于大家在群聊中认识你。</p>

          <div className="profile-actions">
            <button className="profile-secondary" disabled={isSaving} type="button" onClick={onClose}>
              取消
            </button>
            <button className="auth-submit profile-submit" disabled={isLoading || isSaving} type="submit">
              {isSaving ? '保存中' : '保存'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function ThreadHeader({ title }: { title: string }) {
  return (
    <header className="thread-header">
      <div className="thread-title">
        <div className="doc-icon">
          <Bot size={17} />
        </div>
        <strong>{title}</strong>
      </div>
      <div className="header-actions">
        <button type="button" aria-label="上传资料">
          <Upload size={16} />
        </button>
        <button type="button" aria-label="更多">
          <MoreHorizontal size={18} />
        </button>
      </div>
    </header>
  );
}

function DiagnosisThread() {
  return (
    <article className="conversation-card">
      <AssistantBlock>
        <p>
          你描述的“蚕体发白变硬”更接近白僵病的典型症状，但需要继续确认是否存在白色菌丝、蚕体僵硬程度和蚕室湿度。
        </p>
        <ul>
          <li>当前症状：体表发白、活动减弱、变硬。</li>
          <li>系统会同时调用文本知识库、向量检索和 Neo4j 图谱路径。</li>
          <li>若证据不足，回答会提示“无法可靠判断”，并继续追问。</li>
        </ul>
      </AssistantBlock>

      <div className="result-card diagnosis-result">
        <div className="result-icon">
          <Sparkles size={20} />
        </div>
        <div>
          <strong>初步判断</strong>
          <p>疑似白僵病相关表现，证据充分度 72%。</p>
        </div>
        <button type="button">查看依据</button>
      </div>

      <EvidencePanel />

      <AssistantBlock>
        <p>
          这个页面会作为用户端主问诊线程。后续接入后端后，底部输入框会走 FastAPI，智能体编排由 LangGraph 管理。
        </p>
      </AssistantBlock>

      <FeedbackBar />
    </article>
  );
}

function VideoThread() {
  return (
    <article className="conversation-card">
      <AssistantBlock>
        <p>视频咨询会把短视频转成可确认的症状线索，再进入家蚕疾病问诊。</p>
      </AssistantBlock>
      <section className="upload-card">
        <div className="upload-target">
          <ImageUp size={34} />
          <strong>选择或拖入家蚕症状视频</strong>
          <span>建议包含病蚕近景、蚕座、桑叶和环境画面。</span>
        </div>
        <div className="process-list">
          {['视频上传', '抽取关键帧', '语音转写', '症状结构化', '进入问诊'].map((step, index) => (
            <div className={clsx('process-step', index < 2 && 'done', index === 2 && 'current')} key={step}>
              <Circle size={12} />
              <span>{step}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="inline-panel">
        <div className="panel-title">
          <span>上传能力</span>
          <small>多模态输入</small>
        </div>
        <div className="upload-matrix">
          <CapabilityCard icon={ImageUp} title="图片上传" text="病蚕近景、蚕座、桑叶图片。" />
          <CapabilityCard icon={Video} title="视频上传" text="抽帧、ASR、症状摘要。" />
          <CapabilityCard icon={UploadCloud} title="批量病例上传" text="面向农技人员批量整理病例。" />
        </div>
      </section>
      <FeedbackBar />
    </article>
  );
}

function HistoryThread() {
  return (
    <article className="conversation-card">
      <AssistantBlock>
        <p>历史对话不只是保存聊天记录，还要自动生成病例摘要、标签和相似对话推荐。</p>
      </AssistantBlock>
      <section className="inline-panel">
        <div className="panel-title">
          <span>对话列表</span>
          <small>支持搜索、归档、标签</small>
        </div>
        {historyRows.map((row) => (
          <div className="history-row rich-history-row" key={row.title}>
            <Clock3 size={17} />
            <div>
              <strong>{row.title}</strong>
              <span>{row.summary}</span>
            </div>
            <div className="case-tag">{row.tag}</div>
            <small>{row.time}</small>
            <ChevronRight size={17} />
          </div>
        ))}
      </section>

      <section className="inline-panel">
        <div className="panel-title">
          <span>病例摘要</span>
          <small>自动生成</small>
        </div>
        <div className="case-summary">
          <strong>摘要：五龄期家蚕局部出现体表发白、变硬、活动减弱。</strong>
          <p>系统建议优先排查白僵病，并补充蚕室湿度、消毒记录、死亡比例与关键帧图片。</p>
          <div className="tag-row">
            <span>白僵病</span>
            <span>高湿环境</span>
            <span>需复查</span>
          </div>
        </div>
      </section>

      <section className="inline-panel">
        <div className="panel-title">
          <span>相似对话推荐</span>
          <small>基于历史 embedding</small>
        </div>
        <div className="quote-card">推荐查看“蚕体白色粉状物咨询”和“高湿环境下白僵病防控”。</div>
      </section>
    </article>
  );
}

function MemoryThread() {
  return (
    <article className="conversation-card">
      <AssistantBlock>
        <p>
          你列的记忆系统是这个项目的关键差异点。这里拆成短期记忆、长期记忆和 Memory Agent 三层，用户端要能看见并控制长期记忆。
        </p>
      </AssistantBlock>

      <section className="inline-panel">
        <div className="panel-title">
          <span>短期记忆</span>
          <small>当前会话内</small>
        </div>
        <div className="feature-grid">
          <CapabilityCard icon={MessageSquarePlus} title="最近 N 轮对话" text="保留当前问诊上下文和追问状态。" />
          <CapabilityCard icon={Bot} title="Context Window" text="控制 prompt window，避免无关内容挤占上下文。" />
          <CapabilityCard icon={FileSearch} title="summary memory" text="对长会话自动压缩成会话摘要。" />
        </div>
      </section>

      <section className="inline-panel">
        <div className="panel-title">
          <span>长期记忆</span>
          <small>用户级知识沉淀</small>
        </div>
        <div className="feature-grid">
          <CapabilityCard icon={Leaf} title="养殖习惯" text="地区、饲养阶段、环境偏好。" />
          <CapabilityCard icon={History} title="历史疾病案例" text="保存用户授权的历史诊断结果。" />
          <CapabilityCard icon={Database} title="memory embedding" text="向量化保存，支持相似病例召回。" />
        </div>
        <div className="memory-json">
          <span>{'{'}</span>
          <code>"user_id": "u_25721942",</code>
          {memoryFacts.map(([key, value]) => (
            <code key={key}>
              "{key}": "{value}",
            </code>
          ))}
          <span>{'}'}</span>
        </div>
      </section>

      <section className="inline-panel">
        <div className="panel-title">
          <span>Memory Agent</span>
          <small>写入、更新、合并、清理</small>
        </div>
        <div className="agent-flow">
          <span>识别可记忆事实</span>
          <ChevronRight size={15} />
          <span>冲突检测</span>
          <ChevronRight size={15} />
          <span>用户授权</span>
          <ChevronRight size={15} />
          <span>写入 PostgreSQL + Qdrant</span>
        </div>
        <div className="memory-row">
          <span>短期缓存</span>
          <strong>Redis</strong>
          <button type="button">查看策略</button>
        </div>
        <div className="memory-row">
          <span>结构化记忆</span>
          <strong>PostgreSQL</strong>
          <button type="button">查看表结构</button>
        </div>
        <div className="memory-row">
          <span>语义记忆</span>
          <strong>向量数据库</strong>
          <button type="button">查看 embedding</button>
        </div>
      </section>
    </article>
  );
}

function ToolsThread() {
  return (
    <article className="conversation-card">
      <AssistantBlock>
        <p>工具和知识入口是系统核心能力的用户可见层。用户不需要理解后端技术，但需要能看到图谱、引用和诊断模式。</p>
      </AssistantBlock>

      <section className="inline-panel">
        <div className="panel-title">
          <span>知识入口</span>
          <small>用户可见能力</small>
        </div>
        <div className="tool-grid">
          <CapabilityCard icon={GitBranch} title="疾病关系图谱查看" text="查看疾病、症状、病原、防治措施之间的关系。" />
          <CapabilityCard icon={FileSearch} title="RAG 文档查看" text="展开引用来源、原始片段和资料版本。" />
          <CapabilityCard icon={Sparkles} title="证据融合报告" text="展示 BM25、向量检索、Neo4j 的综合依据。" />
        </div>
      </section>

      <section className="inline-panel">
        <div className="panel-title">
          <span>诊断模式切换</span>
          <small>普通、专家、快速</small>
        </div>
        <div className="mode-bar">
          <button className="active" type="button">普通问答</button>
          <button type="button">专家模式</button>
          <button type="button">快速诊断</button>
        </div>
      </section>

      <section className="inline-panel">
        <div className="panel-title">
          <span>上传入口</span>
          <small>图片、视频、批量病例</small>
        </div>
        <div className="upload-matrix">
          <CapabilityCard icon={ImageUp} title="图片上传" text="单张或多张症状图片。" />
          <CapabilityCard icon={Video} title="视频上传" text="短视频抽帧和语音转写。" />
          <CapabilityCard icon={UploadCloud} title="批量病例上传" text="面向农技员的批量病例录入。" />
        </div>
      </section>
    </article>
  );
}

function SettingsThread() {
  return (
    <article className="conversation-card">
      <AssistantBlock>
        <p>企业级用户端需要设置控制面板，但要分层展示，避免普通养殖户被复杂参数吓到。</p>
      </AssistantBlock>

      <SettingPanel title="模型设置" note="GPT / Qwen / Claude、temperature、推理模式">
        <div className="segmented-control">
          <button className="active" type="button">Qwen</button>
          <button type="button">GPT</button>
          <button type="button">Claude</button>
        </div>
        <SettingRow label="Temperature" value="0.2" />
        <SettingRow label="推理模式" value="证据优先" />
      </SettingPanel>

      <SettingPanel title="知识源设置" note="KG、RAG、数据版本">
        <div className="source-list">
          <ToggleLine label="启用知识图谱 KG" enabled />
          <ToggleLine label="启用 RAG 文档检索" enabled />
          <SettingRow label="数据版本" value="silkworm-kb-2026.07" />
        </div>
      </SettingPanel>

      <SettingPanel title="记忆控制" note="长期记忆、写入授权、清除记忆">
        <ToggleLine label="开启长期记忆" enabled />
        <ToggleLine label="允许 Memory Agent 写入" enabled />
        <div className="danger-row">
          <span>清除全部长期记忆</span>
          <button type="button">清除</button>
        </div>
      </SettingPanel>

      <SettingPanel title="隐私与安全" note="数据删除、导出、审计">
        <SettingRow label="导出用户数据" value="JSON / CSV" />
        <SettingRow label="记录审计" value="已开启" />
        <div className="danger-row">
          <span>删除账号数据</span>
          <button type="button">删除</button>
        </div>
      </SettingPanel>

      <SettingPanel title="UI 设置" note="深色模式、字体、农技简化模式">
        <ToggleLine label="深色模式" />
        <SettingRow label="字体大小" value="标准" />
        <ToggleLine label="农技简化模式" enabled />
      </SettingPanel>
    </article>
  );
}

function LoginThread() {
  return (
    <article className="conversation-card">
      <AssistantBlock>
        <p>当前账号入口先支持手机号验证码和邮箱验证码。输入验证码后即可登录系统。</p>
      </AssistantBlock>
      <section className="login-strip">
        <div className="login-method-card">
          <Phone size={28} />
          <strong>手机号验证码</strong>
          <span>适合农户和农技人员快速进入问诊。</span>
        </div>
        <div className="login-method-card">
          <Mail size={28} />
          <strong>邮箱验证码</strong>
          <span>适合后台管理、资料整理和专家账号。</span>
        </div>
        <div className="sms-box">
          <label>
            <span>账号</span>
            <div>
              <Phone size={15} />
              138 0000 0000 / name@example.com
            </div>
          </label>
          <label>
            <span>验证码</span>
            <div>826491</div>
          </label>
          <button type="button">登录</button>
        </div>
      </section>
    </article>
  );
}

function EvidencePanel() {
  return (
    <section className="inline-panel">
      <div className="panel-title">
        <span>证据来源</span>
        <small>RAG + 图谱融合</small>
      </div>
      <div className="evidence-list">
        {evidenceRows.map((row) => (
          <div className="evidence-row" key={row.name}>
            <div className="file-dot">
              <FileText size={15} />
            </div>
            <div>
              <strong>{row.name}</strong>
              <span>{row.type}</span>
            </div>
            <small>{row.score}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function CapabilityCard({ icon: Icon, title, text }: { icon: LucideIcon; title: string; text: string }) {
  return (
    <div className="capability-card">
      <Icon size={20} />
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}

function SettingPanel({ title, note, children }: { title: string; note: string; children: ReactNode }) {
  return (
    <section className="inline-panel setting-panel">
      <div className="panel-title">
        <span>{title}</span>
        <small>{note}</small>
      </div>
      <div className="setting-body">{children}</div>
    </section>
  );
}

function SettingRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="setting-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ToggleLine({ label, enabled = false }: { label: string; enabled?: boolean }) {
  return (
    <div className="setting-row">
      <span>{label}</span>
      <button className={clsx('mini-switch', enabled && 'on')} type="button" aria-label={label}>
        <i />
      </button>
    </div>
  );
}

function AssistantBlock({ children }: { children: ReactNode }) {
  return (
    <div className="assistant-block">
      <div className="assistant-avatar">
        <Bot size={17} />
      </div>
      <div className="assistant-content">{children}</div>
    </div>
  );
}

function FeedbackBar() {
  return (
    <div className="feedback-bar">
      <button type="button" aria-label="复制">
        <FileText size={15} />
      </button>
      <button type="button" aria-label="赞同">
        <ThumbsUp size={15} />
      </button>
      <button type="button" aria-label="反对">
        <ThumbsDown size={15} />
      </button>
      <button className="retry-action" type="button" aria-label="重试">
        <RotateCcw size={15} />
      </button>
    </div>
  );
}

function Composer() {
  return (
    <form className="composer-card">
      <textarea placeholder="描述症状、上传视频，或继续追问" rows={1} />
      <div className="composer-toolbar">
        <div className="composer-left">
          <button type="button" aria-label="添加">
            <Plus size={19} />
          </button>
          <button type="button" aria-label="上传视频">
            <Video size={17} />
          </button>
          <button type="button" aria-label="语音">
            <Mic size={17} />
          </button>
        </div>
        <button className="send-button" type="button" aria-label="发送">
          <Send size={18} />
        </button>
      </div>
    </form>
  );
}

export default App;

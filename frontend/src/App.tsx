import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import clsx from 'clsx';
import type { LucideIcon } from 'lucide-react';
import type {
  ApiCommunityAuthor,
  ApiCommunityBlockedUserList,
  ApiCommunityBookmarkCollection,
  ApiCommunityBookmarkCollectionDetail,
  ApiCommunityBookmarkCollectionList,
  ApiCommunityCaseUpdate,
  ApiCommunityComment,
  ApiCommunityCommentList,
  ApiCommunityCreatorOverview,
  ApiCommunityDirectMessage,
  ApiCommunityDirectThread,
  ApiCommunityNotifications,
  ApiCommunityPost,
  ApiCommunityPostList,
  ApiCommunityProfileDetail,
  ApiCommunityRelationshipList,
  ApiCommunitySearch,
  ApiCommunityTag,
  ApiCommunityUpload,
  CommunityConfirmAction,
  CommunityFeedTab,
  CommunityPostType,
  CommunityPostVisibility,
  CommunityRealtimeEvent,
  CommunityRelationshipType,
} from './features/community/types';
import { CommunityConfirmDialog } from './features/community/CommunityConfirmDialog';
import { DiagnosisMarkdown } from './features/diagnosis/DiagnosisMarkdown';
import {
  formatCaseUpdateStatus,
  formatCommunityIdentity,
  formatCommunityPostType,
  formatCommunityTime,
  formatNotificationText,
} from './features/community/formatters';
import {
  Archive,
  ArrowDownUp,
  BadgeDollarSign,
  Bell,
  Bot,
  Bookmark,
  Brain,
  BookOpen,
  Braces,
  Briefcase,
  Camera,
  CalendarDays,
  ChartColumn,
  Check,
  ChevronDown,
  ChevronRight,
  CircleUserRound,
  ClipboardList,
  Copy,
  Cross,
  Database,
  Download,
  Dumbbell,
  FileText,
  Flag,
  FlaskConical,
  Flower2,
  Folder,
  FolderOpen,
  FolderPlus,
  FolderX,
  GitBranch,
  Globe,
  GraduationCap,
  Heart,
  History,
  ImageUp,
  Link2,
  Lightbulb,
  LogOut,
  Mail,
  MessageCircle,
  MessageSquarePlus,
  Mic,
  Microscope,
  MoreHorizontal,
  Music,
  PanelLeft,
  Paperclip,
  Palette,
  PencilLine,
  PenLine,
  PenTool,
  Phone,
  Pin,
  PinOff,
  Plane,
  Plus,
  Scale,
  Scissors,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquareTerminal,
  Stethoscope,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  Upload,
  UserPlus,
  UserRound,
  Video,
  Volume2,
  Wrench,
  X,
} from 'lucide-react';

type ThreadKey = 'diagnosis' | 'video' | 'history' | 'memory' | 'tools' | 'settings' | 'projects' | 'admin';
type AuthMode = 'phone' | 'email';
type UiTheme = 'light' | 'dark';
type UiFontSize = 'small' | 'standard' | 'large' | 'extra';
type ActiveConversationSource = 'project' | 'history' | null;
type BrowserSpeechRecognitionMode = 'speech' | 'backend' | null;

type BrowserSpeechRecognitionResult = {
  isFinal: boolean;
  0?: {
    transcript?: string;
  };
};

type BrowserSpeechRecognitionEvent = {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: BrowserSpeechRecognitionResult;
  };
};

type BrowserSpeechRecognitionErrorEvent = {
  error?: string;
  message?: string;
};

type BrowserSpeechRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null;
  onerror: ((event: BrowserSpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

type BrowserSpeechRecognitionWindow = Window & {
  SpeechRecognition?: BrowserSpeechRecognitionConstructor;
  webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
};

type ConfiguredModel = {
  id: string;
  providerName: string;
  modelId: string;
  apiRequestUrl: string;
  hasApiKey: boolean;
  enabled: boolean;
  isDefault: boolean;
  lastTestStatus: 'success' | 'failed' | null;
  lastTestMessage: string | null;
  lastTestAt: string | null;
};

type ModelConfigDraft = {
  providerName: string;
  modelId: string;
  apiKey: string;
  apiRequestUrl: string;
};

type UiPreferences = {
  theme: UiTheme;
  fontSize: UiFontSize;
};

type UserPreferences = {
  knowledge_graph_enabled: boolean;
  rag_enabled: boolean;
  long_term_memory_enabled: boolean;
  memory_agent_write_enabled: boolean;
  in_app_notifications: boolean;
  upload_notifications: boolean;
  model_notifications: boolean;
  husbandry_health_notifications: boolean;
  husbandry_temperature_min: number;
  husbandry_temperature_max: number;
  husbandry_humidity_max: number;
  auto_generate_title: boolean;
  send_shortcut: 'enter' | 'ctrl_enter';
  show_model_status: boolean;
  image_compression: 'balanced' | 'high_quality';
  auto_retry_upload: boolean;
  draft_attachment_retention_hours: 24 | 72 | 168;
  reduced_motion: boolean;
  high_contrast: boolean;
  locale: 'zh-CN' | 'en-US';
  theme: UiTheme;
  font_size: UiFontSize;
};

type ApiUserSettingsResponse = {
  preferences: UserPreferences;
  updated_at: string | null;
};

type ApiUserDeviceSession = {
  id: string;
  device_name: string;
  last_used_at: string | null;
  created_at: string;
  expires_at: string;
  is_current: boolean;
};

type AuthUser = {
  id: string;
  display_name: string;
  username: string;
  role: string;
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

type ApiProjectResponse = {
  id: string;
  name: string;
  description: string | null;
  icon_key: string;
  color: string;
  status: string;
  created_at: string;
  updated_at: string;
  pinned_at: string | null;
};

type ApiFarm = {
  id: string;
  name: string;
  location: string | null;
  notes: string | null;
  status: string;
  created_at: string;
  updated_at: string;
};

type ApiSilkwormBatch = {
  id: string;
  farm_id: string;
  project_id: string | null;
  farm_name: string;
  batch_code: string | null;
  variety: string | null;
  instar: string | null;
  start_date: string | null;
  expected_cocooning_date: string | null;
  population_count: number | null;
  notes: string | null;
  status: 'active' | 'finished' | 'archived';
  created_at: string;
  updated_at: string;
};

type ApiHusbandryDailyRecord = {
  id: string;
  batch_id: string;
  record_date: string;
  temperature_celsius: number | null;
  humidity_percent: number | null;
  feedings: number | null;
  leaf_amount_kg: number | null;
  sick_count: number | null;
  death_count: number | null;
  observations: string | null;
  management_notes: string | null;
  created_at: string;
  updated_at: string;
  assets: ApiHusbandryAsset[];
};

type HusbandryCaseStatus = 'needs_more_info' | 'suspected' | 'processing' | 'closed';
type HusbandryCaseSeverity = 'low' | 'medium' | 'high' | 'critical';

type ApiHusbandryFollowUp = {
  id: string;
  case_id: string;
  observed_on: string;
  action_taken: string | null;
  note: string | null;
  affected_count: number | null;
  death_count: number | null;
  next_follow_up_on: string | null;
  created_at: string;
};

type ApiHusbandryAsset = {
  id: string;
  file_id: string;
  file_name: string;
  file_type: 'image' | 'video';
  mime_type: string;
  storage_url: string | null;
  file_size: number;
  created_at: string;
};

type ApiHusbandryCase = {
  id: string;
  farm_id: string;
  batch_id: string | null;
  project_id: string | null;
  source_conversation_id: string | null;
  farm_name: string;
  batch_code: string | null;
  title: string;
  occurred_on: string;
  symptom_summary: string | null;
  suspected_disease: string | null;
  severity: HusbandryCaseSeverity;
  status: HusbandryCaseStatus;
  diagnosis_summary: string | null;
  recommendation: string | null;
  source_snapshot: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  follow_ups: ApiHusbandryFollowUp[];
  assets: ApiHusbandryAsset[];
  expert_reviews?: ApiDiagnosisExpertReview[];
};

type ApiHusbandryDashboard = {
  active_batch_count: number;
  open_case_count: number;
  due_follow_up_count: number;
  today_record_count: number;
  recent_cases: ApiHusbandryCase[];
};

type DiagnosisMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  status?: 'error' | 'regenerating';
  feedback?: 'like' | 'dislike' | null;
  feedbackReasons?: string[];
  feedbackDetail?: string | null;
  attachments?: DiagnosisMessageAttachment[];
};

type DiagnosisMessageAttachment = {
  id: string;
  fileName: string;
  fileType: 'image' | 'video' | 'document' | 'audio' | 'other';
  mimeType: string;
  storageUrl: string | null;
  fileSize: number;
};

type ApiDiagnosisFileResponse = {
  id: string;
  file_name: string;
  file_type: 'image' | 'video' | 'document' | 'audio' | 'other';
  mime_type: string;
  storage_url: string | null;
  file_size: number;
  metadata?: Record<string, unknown>;
};

type DiagnosisSubmitOptions = {
  attachmentIds?: string[];
  uploadedAttachments?: ApiDiagnosisFileResponse[];
  structuredData?: Record<string, unknown> | null;
};

type ApiDiagnosisVoiceTranscriptionResponse = {
  text: string;
  model: string;
  provider: string;
};

type ApiDiagnosisMessageResponse = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  message_type: string;
  status: string;
  created_at: string;
  displayed_at?: string | null;
  feedback?: 'like' | 'dislike' | null;
  feedback_reasons?: string[];
  feedback_detail?: string | null;
  attachments?: ApiDiagnosisFileResponse[];
};

type ApiDiagnosisConversationResponse = {
  id: string;
  project_id: string | null;
  title: string;
  summary: string | null;
  conversation_type: string;
  status: string;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  pinned_at: string | null;
};

type ApiDiagnosisConversationDetailResponse = ApiDiagnosisConversationResponse & {
  messages: ApiDiagnosisMessageResponse[];
  expert_reviews?: ApiDiagnosisExpertReview[];
};

type ApiDiagnosisExpertReview = {
  id: string;
  reviewer_name: string;
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  conclusion: string;
  recommendation: string;
  evidence: Array<Record<string, unknown>>;
  version: number;
  published_at: string;
};

type ApiDiagnosisConversationTurnResponse = {
  conversation: ApiDiagnosisConversationResponse;
  user_message: ApiDiagnosisMessageResponse;
  assistant_message: ApiDiagnosisMessageResponse;
  model: string;
  provider: string;
};

type ApiDiagnosisMessageMutationResponse = {
  conversation: ApiDiagnosisConversationResponse;
  message: ApiDiagnosisMessageResponse;
};

type ApiDiagnosisConversationShareResponse = {
  id: string;
  conversation_id: string;
  share_token: string;
  share_url: string;
  title: string;
  variant: DiagnosisConversationShareVariant;
  created_at: string;
  expires_at: string | null;
};

type ApiPublicDiagnosisConversationShareResponse = {
  title: string;
  variant: DiagnosisConversationShareVariant;
  content_markdown: string;
  created_at: string;
  updated_at: string;
};

type ApiProjectShareResponse = {
  id: string;
  project_id: string;
  share_token: string;
  share_url: string;
  title: string;
  variant: ProjectShareVariant;
  created_at: string;
  expires_at: string | null;
};

type ApiPublicProjectShareResponse = {
  title: string;
  variant: ProjectShareVariant;
  content_markdown: string;
  created_at: string;
  updated_at: string;
};

type DiagnosisConversationPublicSharePayload = {
  title: string;
  variant: DiagnosisConversationShareVariant;
  contentMarkdown: string;
};

type ProjectPublicSharePayload = {
  title: string;
  variant: ProjectShareVariant;
  contentMarkdown: string;
};

type ToastTone = 'success' | 'error' | 'info';

type AppToastState = {
  id: number;
  message: string;
  tone: ToastTone;
};

type ApiModelConfigResponse = {
  id: string;
  provider_name: string;
  model_id: string;
  api_request_url: string;
  is_enabled: boolean;
  is_default: boolean;
  has_api_key: boolean;
  last_test_status: 'success' | 'failed' | null;
  last_test_message: string | null;
  last_test_at: string | null;
  created_at: string;
  updated_at: string;
};

type ApiModelConfigTestResponse = {
  id: string;
  status: 'success' | 'failed';
  message: string;
  tested_at: string;
};

type DiagnosisConversation = {
  id: string;
  projectId: string | null;
  title: string;
  summary: string;
  status: string;
  time: string;
  updatedAt: string;
  pinnedAt: string | null;
};

type ArchiveBulkDeletePayload = {
  conversationIds: string[];
  projectIds: string[];
};

type HeaderConversationMenuConfig = {
  conversation: DiagnosisConversation | null;
  messages: DiagnosisMessage[];
  projects: CreatedProject[];
  onCreateProjectForMove: (conversationId: string) => void;
  onCreatePublicShare: (
    conversationId: string,
    payload: DiagnosisConversationPublicSharePayload,
  ) => Promise<ApiDiagnosisConversationShareResponse>;
  onCreateCommunityDraft: (conversationId: string, attachmentIds: string[]) => Promise<void>;
  onArchive: (conversationId: string) => void;
  onDelete: (conversation: DiagnosisConversation) => void;
  onMoveProject: (conversationId: string, projectId: string | null) => Promise<DiagnosisConversation>;
  onNotify: (message: string, tone?: ToastTone) => void;
  onRename: (conversationId: string, title: string) => Promise<void>;
  onSaveAsCase: (conversationId: string) => void;
};

class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
  }
}

function getApiErrorMessage(data: unknown, fallback: string) {
  if (!data || typeof data !== 'object') return fallback;

  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== 'object') return '';
        const message = (item as { msg?: unknown; message?: unknown }).msg ?? (item as { msg?: unknown; message?: unknown }).message;
        const location = (item as { loc?: unknown }).loc;
        const locationLabel = Array.isArray(location) ? location.filter((part) => typeof part === 'string').join('.') : '';
        if (typeof message !== 'string' || !message.trim()) return '';
        return locationLabel ? `${locationLabel}: ${message}` : message;
      })
      .filter(Boolean);
    if (messages.length > 0) return messages.join('；');
  }
  if (detail && typeof detail === 'object') {
    const message =
      (detail as { message?: unknown; msg?: unknown; error?: unknown }).message ??
      (detail as { message?: unknown; msg?: unknown; error?: unknown }).msg ??
      (detail as { message?: unknown; msg?: unknown; error?: unknown }).error;
    if (typeof message === 'string' && message.trim()) return message;
  }

  const message = (data as { message?: unknown; error?: unknown }).message ?? (data as { message?: unknown; error?: unknown }).error;
  if (typeof message === 'string' && message.trim()) return message;

  return fallback;
}

function useDebouncedValue<T>(value: T, delay = 300) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedValue(value), delay);
    return () => window.clearTimeout(timer);
  }, [delay, value]);
  return debouncedValue;
}

const AUTH_STORAGE_KEY = 'canw.auth';
const UI_PREFERENCES_STORAGE_KEY = 'canw.ui.preferences';
const SELECTED_MODEL_CONFIG_STORAGE_KEY = 'canw.model.selected';
const SIDEBAR_WIDTH_STORAGE_KEY = 'canw.sidebar.width';
const SIDEBAR_DEFAULT_WIDTH = 280;
const SIDEBAR_MIN_WIDTH = 220;
const SIDEBAR_MAX_WIDTH = 420;
const SIDEBAR_COLLAPSED_WIDTH = 64;
const SIDEBAR_COLLAPSE_THRESHOLD = 188;
const API_BASE_URLS = import.meta.env.VITE_API_BASE_URL
  ? [import.meta.env.VITE_API_BASE_URL]
  : ['http://127.0.0.1:8010/api/v1', 'http://127.0.0.1:8000/api/v1'];

const defaultUiPreferences: UiPreferences = {
  theme: 'light',
  fontSize: 'standard',
};

const defaultUserPreferences: UserPreferences = {
  knowledge_graph_enabled: true,
  rag_enabled: true,
  long_term_memory_enabled: true,
  memory_agent_write_enabled: true,
  in_app_notifications: true,
  upload_notifications: true,
  model_notifications: true,
  husbandry_health_notifications: true,
  husbandry_temperature_min: 20,
  husbandry_temperature_max: 30,
  husbandry_humidity_max: 85,
  auto_generate_title: true,
  send_shortcut: 'enter',
  show_model_status: true,
  image_compression: 'balanced',
  auto_retry_upload: true,
  draft_attachment_retention_hours: 24,
  reduced_motion: false,
  high_contrast: false,
  locale: 'zh-CN',
  theme: 'light',
  font_size: 'standard',
};

const uiFontSizeOptions: Array<{ value: UiFontSize; label: string }> = [
  { value: 'small', label: '小' },
  { value: 'standard', label: '标准' },
  { value: 'large', label: '大' },
  { value: 'extra', label: '超大' },
];

const emptyModelDraft: ModelConfigDraft = {
  providerName: 'OpenAI',
  modelId: '',
  apiKey: '',
  apiRequestUrl: '',
};

const createDiagnosisMessageId = () => `diagnosis-${Date.now()}-${Math.random().toString(16).slice(2)}`;

const getCurrentTimeLabel = () =>
  new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date());

function toSafeMarkdownFileName(value: string) {
  const normalized = value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');
  return normalized || 'CanW-问诊记录';
}

function downloadMarkdownFile(fileName: string, content: string) {
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = fileName.endsWith('.md') ? fileName : `${fileName}.md`;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

async function copyTextToClipboard(text: string) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.top = '0';
  textarea.style.left = '0';
  textarea.style.width = '1px';
  textarea.style.height = '1px';
  textarea.style.opacity = '0';
  textarea.style.pointerEvents = 'none';
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, textarea.value.length);

  try {
    if (document.execCommand('copy')) return;
  } finally {
    document.body.removeChild(textarea);
  }

  if (!navigator.clipboard?.writeText) {
    throw new Error('clipboard unsupported');
  }

  await navigator.clipboard.writeText(text);
}

function formatAttachmentSize(size: number) {
  if (!Number.isFinite(size) || size <= 0) return '待处理';
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / (1024 * 1024)).toFixed(size < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

function downloadJsonFile(fileName: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = fileName.endsWith('.json') ? fileName : `${fileName}.json`;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

function downloadCsvFile(fileName: string, rows: Array<Array<string | number | null | undefined>>) {
  const escapeCell = (value: string | number | null | undefined) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const content = `\uFEFF${rows.map((row) => row.map(escapeCell).join(',')).join('\r\n')}`;
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = fileName.endsWith('.csv') ? fileName : `${fileName}.csv`;
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

const IMAGE_UPLOAD_MAX_EDGE = 1920;
const IMAGE_UPLOAD_COMPRESSION_THRESHOLD = 700 * 1024;
const IMAGE_UPLOAD_WEBP_QUALITY = 0.84;

type ImageUploadPreparation = {
  file: File;
  originalSize: number;
  compressed: boolean;
};

function canCompressUploadImage(file: File) {
  return file.type.startsWith('image/') && file.type !== 'image/gif' && file.type !== 'image/svg+xml';
}

function getCompressedImageFileName(name: string) {
  const baseName = name.replace(/\.[^/.]+$/, '').trim() || 'image';
  return `${baseName}.webp`;
}

function loadImageForUpload(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const objectUrl = URL.createObjectURL(file);
    const release = () => URL.revokeObjectURL(objectUrl);

    image.onload = () => {
      release();
      resolve(image);
    };
    image.onerror = () => {
      release();
      reject(new Error('图片读取失败'));
    };
    image.src = objectUrl;
  });
}

function canvasToBlob(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

async function prepareImageForUpload(
  file: File,
  compression: UserPreferences['image_compression'] = 'balanced',
): Promise<ImageUploadPreparation> {
  const originalSize = file.size;
  if (!canCompressUploadImage(file)) {
    return { file, originalSize, compressed: false };
  }

  const maxEdge = compression === 'high_quality' ? 2560 : IMAGE_UPLOAD_MAX_EDGE;
  const compressionThreshold = compression === 'high_quality' ? 1400 * 1024 : IMAGE_UPLOAD_COMPRESSION_THRESHOLD;
  const quality = compression === 'high_quality' ? 0.92 : IMAGE_UPLOAD_WEBP_QUALITY;

  try {
    const image = await loadImageForUpload(file);
    const sourceWidth = image.naturalWidth;
    const sourceHeight = image.naturalHeight;
    if (!sourceWidth || !sourceHeight) return { file, originalSize, compressed: false };

    const longestEdge = Math.max(sourceWidth, sourceHeight);
    const scale = Math.min(1, maxEdge / longestEdge);
    const targetWidth = Math.max(1, Math.round(sourceWidth * scale));
    const targetHeight = Math.max(1, Math.round(sourceHeight * scale));
    const needsResize = targetWidth !== sourceWidth || targetHeight !== sourceHeight;
    if (!needsResize && originalSize <= compressionThreshold) {
      return { file, originalSize, compressed: false };
    }

    const canvas = document.createElement('canvas');
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const context = canvas.getContext('2d');
    if (!context) return { file, originalSize, compressed: false };

    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = 'high';
    context.drawImage(image, 0, 0, targetWidth, targetHeight);

    const compressedBlob = await canvasToBlob(canvas, 'image/webp', quality);
    if (!compressedBlob || compressedBlob.size >= originalSize) {
      return { file, originalSize, compressed: false };
    }

    return {
      file: new File([compressedBlob], getCompressedImageFileName(file.name), {
        type: 'image/webp',
        lastModified: file.lastModified,
      }),
      originalSize,
      compressed: true,
    };
  } catch {
    // Preserve the source file when a browser cannot decode a particular image format.
    return { file, originalSize, compressed: false };
  }
}

function formatPreparedImageDetail(prepared: ImageUploadPreparation) {
  const detail = formatAttachmentSize(prepared.file.size);
  if (!prepared.compressed || !prepared.originalSize) return detail;
  const reduction = Math.max(1, Math.round((1 - prepared.file.size / prepared.originalSize) * 100));
  return `${detail} · 已压缩 ${reduction}%`;
}

function formatVoiceDuration(seconds: number) {
  const safeSeconds = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safeSeconds / 60);
  const restSeconds = safeSeconds % 60;
  return `${minutes}:${String(restSeconds).padStart(2, '0')}`;
}

function getBrowserSpeechRecognitionConstructor() {
  const speechWindow = window as BrowserSpeechRecognitionWindow;
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

type SidebarAction = {
  key: ThreadKey;
  icon: LucideIcon;
  label: string;
};

const sidebarActions: SidebarAction[] = [
  { key: 'diagnosis', icon: MessageSquarePlus, label: '新问诊' },
  { key: 'video', icon: MessageCircle, label: '社区' },
  { key: 'history', icon: Search, label: '搜索聊天' },
  { key: 'memory', icon: GitBranch, label: '图谱探索' },
  { key: 'tools', icon: ClipboardList, label: '养殖工作台' },
];

const projectColorOptions = [
  { value: '#11110f', label: '墨色' },
  { value: '#ff4338', label: '珊瑚红' },
  { value: '#f47c31', label: '暖橙' },
  { value: '#f5bd3c', label: '麦黄' },
  { value: '#4caf58', label: '草木绿' },
  { value: '#3f7ee8', label: '湖蓝' },
  { value: '#8350e9', label: '紫罗兰' },
  { value: '#df6b62', label: '陶土粉' },
] as const;

const projectIconOptions = [
  { key: 'folder', label: '项目', icon: Folder },
  { key: 'money', label: '费用', icon: BadgeDollarSign },
  { key: 'book', label: '文档', icon: BookOpen },
  { key: 'study', label: '学习', icon: GraduationCap },
  { key: 'pen', label: '书写', icon: PenLine },
  { key: 'draft', label: '草稿', icon: PenTool },
  { key: 'code', label: '代码', icon: Braces },
  { key: 'terminal', label: '终端', icon: SquareTerminal },
  { key: 'music', label: '音频', icon: Music },
  { key: 'archive', label: '清理', icon: Trash2 },
  { key: 'edit', label: '剪裁', icon: Scissors },
  { key: 'palette', label: '设计', icon: Palette },
  { key: 'health', label: '诊断', icon: Stethoscope },
  { key: 'cross', label: '医疗', icon: Cross },
  { key: 'plant', label: '生长', icon: Flower2 },
  { key: 'work', label: '工作', icon: Briefcase },
  { key: 'chart', label: '数据', icon: ChartColumn },
  { key: 'user', label: '个人', icon: CircleUserRound },
  { key: 'training', label: '训练', icon: Dumbbell },
  { key: 'list', label: '清单', icon: ClipboardList },
  { key: 'rule', label: '评估', icon: Scale },
  { key: 'research', label: '研究', icon: Microscope },
  { key: 'travel', label: '出行', icon: Plane },
  { key: 'global', label: '全球', icon: Globe },
  { key: 'tool', label: '工具', icon: Wrench },
  { key: 'lab', label: '实验', icon: FlaskConical },
  { key: 'brain', label: '知识', icon: Brain },
  { key: 'heart', label: '关注', icon: Heart },
  { key: 'spark', label: '灵感', icon: Sparkles },
  { key: 'data', label: '资料', icon: Database },
] as const;

type ProjectIconKey = (typeof projectIconOptions)[number]['key'];

type CreatedProject = {
  id: string;
  name: string;
  description: string;
  updatedAt: string;
  owner: 'me' | 'shared';
  color: string;
  iconKey: ProjectIconKey;
  status: string;
  pinnedAt: string | null;
};

type ProjectSettingsUpdate = Pick<CreatedProject, 'name' | 'description' | 'color' | 'iconKey'>;

type ProjectChat = {
  id: string;
  key: ThreadKey;
  title: string;
  time: string;
};

type ProjectFolder = {
  id: string;
  name: string;
  chats: ProjectChat[];
  color?: string;
  iconKey?: ProjectIconKey;
  pinned?: boolean;
};

const projectFolders: ProjectFolder[] = [];

const defaultProjectRows: CreatedProject[] = [];

function isProjectIconKey(value: string): value is ProjectIconKey {
  return projectIconOptions.some((option) => option.key === value);
}

function getProjectIconOption(iconKey?: ProjectIconKey) {
  return projectIconOptions.find((option) => option.key === iconKey) ?? projectIconOptions[0];
}

function getProjectColor(value?: string): string {
  return projectColorOptions.some((option) => option.value === value) ? value ?? projectColorOptions[0].value : projectColorOptions[0].value;
}

function getProjectIconStyle(color?: string): CSSProperties {
  const normalizedColor = getProjectColor(color);
  return {
    color: normalizedColor,
    borderColor: `${normalizedColor}33`,
    backgroundColor: `${normalizedColor}10`,
  };
}

function formatProjectUpdatedAt(value: string) {
  const updatedAt = new Date(value);
  if (Number.isNaN(updatedAt.getTime())) return '';

  const diffMs = Date.now() - updatedAt.getTime();
  if (diffMs < 60 * 1000) return '刚刚';
  if (diffMs < 60 * 60 * 1000) return `${Math.max(1, Math.floor(diffMs / (60 * 1000)))} 分`;
  if (diffMs < 24 * 60 * 60 * 1000) return `${Math.max(1, Math.floor(diffMs / (60 * 60 * 1000)))} 小时`;

  return `${updatedAt.getMonth() + 1}月${updatedAt.getDate()}日`;
}

function formatMessageTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return getCurrentTimeLabel();

  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function formatArchiveDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';

  const time = new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);

  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日，${time}`;
}

function mapApiProject(project: ApiProjectResponse): CreatedProject {
  return {
    id: project.id,
    name: project.name,
    description: project.description ?? '',
    updatedAt: formatProjectUpdatedAt(project.updated_at),
    owner: 'me',
    color: getProjectColor(project.color),
    iconKey: isProjectIconKey(project.icon_key) ? project.icon_key : 'folder',
    status: project.status,
    pinnedAt: project.pinned_at,
  };
}

function mapApiDiagnosisConversation(conversation: ApiDiagnosisConversationResponse): DiagnosisConversation {
  const updatedAt = conversation.last_message_at ?? conversation.updated_at;

  return {
    id: conversation.id,
    projectId: conversation.project_id ?? null,
    title: conversation.title || '未命名问诊',
    summary: conversation.summary ?? '',
    status: conversation.status,
    time: formatProjectUpdatedAt(updatedAt),
    updatedAt,
    pinnedAt: conversation.pinned_at,
  };
}

function mapApiDiagnosisMessage(message: ApiDiagnosisMessageResponse): DiagnosisMessage {
  return {
    id: message.id,
    role: message.role === 'user' ? 'user' : 'assistant',
    content: message.content,
    createdAt: formatMessageTime(message.displayed_at ?? message.created_at),
    status: message.status === 'failed' ? 'error' : undefined,
    feedback: message.feedback ?? null,
    feedbackReasons: message.feedback_reasons ?? [],
    feedbackDetail: message.feedback_detail ?? null,
    attachments: (message.attachments ?? []).map(mapApiDiagnosisAttachment),
  };
}

function mapApiDiagnosisAttachment(attachment: ApiDiagnosisFileResponse): DiagnosisMessageAttachment {
  return {
    id: attachment.id,
    fileName: attachment.file_name,
    fileType: attachment.file_type,
    mimeType: attachment.mime_type,
    storageUrl: attachment.storage_url,
    fileSize: attachment.file_size,
  };
}

function mapApiModelConfig(modelConfig: ApiModelConfigResponse): ConfiguredModel {
  return {
    id: modelConfig.id,
    providerName: modelConfig.provider_name,
    modelId: modelConfig.model_id,
    apiRequestUrl: modelConfig.api_request_url,
    hasApiKey: modelConfig.has_api_key,
    enabled: modelConfig.is_enabled,
    isDefault: modelConfig.is_default,
    lastTestStatus: modelConfig.last_test_status,
    lastTestMessage: modelConfig.last_test_message,
    lastTestAt: modelConfig.last_test_at,
  };
}

function sortProjectsByPin(projects: CreatedProject[]) {
  return [...projects].sort((firstProject, secondProject) => {
    const firstPinnedAt = firstProject.pinnedAt ? new Date(firstProject.pinnedAt).getTime() : 0;
    const secondPinnedAt = secondProject.pinnedAt ? new Date(secondProject.pinnedAt).getTime() : 0;
    if (firstPinnedAt || secondPinnedAt) return secondPinnedAt - firstPinnedAt;
    return 0;
  });
}

function sortDiagnosisConversationsByPin(conversations: DiagnosisConversation[]) {
  return [...conversations].sort((firstConversation, secondConversation) => {
    const firstPinnedAt = firstConversation.pinnedAt ? new Date(firstConversation.pinnedAt).getTime() : 0;
    const secondPinnedAt = secondConversation.pinnedAt ? new Date(secondConversation.pinnedAt).getTime() : 0;
    if (firstPinnedAt || secondPinnedAt) return secondPinnedAt - firstPinnedAt;
    return 0;
  });
}

function sortConversationsByUpdatedAt(conversations: DiagnosisConversation[]) {
  return [...conversations].sort((firstConversation, secondConversation) => {
    const firstTime = new Date(firstConversation.updatedAt).getTime();
    const secondTime = new Date(secondConversation.updatedAt).getTime();
    return (Number.isNaN(secondTime) ? 0 : secondTime) - (Number.isNaN(firstTime) ? 0 : firstTime);
  });
}

function getConversationGroupLabel(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '更早';

  const today = new Date();
  const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();
  const conversationStart = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const diffDays = Math.floor((todayStart - conversationStart) / (24 * 60 * 60 * 1000));

  if (diffDays <= 0) return '今天';
  if (diffDays === 1) return '昨天';
  if (diffDays <= 7) return '前 7 天';
  return '更早';
}

function getProjectChatId(thread: ThreadKey, folders: ProjectFolder[] = projectFolders) {
  for (const folder of folders) {
    const chat = folder.chats.find((item) => item.key === thread);
    if (chat) return chat.id;
  }
  return null;
}

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

function readSelectedModelConfigId(): string | null {
  try {
    const value = window.localStorage.getItem(SELECTED_MODEL_CONFIG_STORAGE_KEY);
    return value?.trim() || null;
  } catch {
    return null;
  }
}

function saveSelectedModelConfigId(modelConfigId: string | null) {
  if (!modelConfigId) {
    window.localStorage.removeItem(SELECTED_MODEL_CONFIG_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(SELECTED_MODEL_CONFIG_STORAGE_KEY, modelConfigId);
}

function isUiTheme(value: unknown): value is UiTheme {
  return value === 'light' || value === 'dark';
}

function isUiFontSize(value: unknown): value is UiFontSize {
  return uiFontSizeOptions.some((option) => option.value === value);
}

function readStoredUiPreferences(): UiPreferences {
  try {
    const raw = window.localStorage.getItem(UI_PREFERENCES_STORAGE_KEY);
    if (!raw) return defaultUiPreferences;

    const parsed = JSON.parse(raw) as Partial<UiPreferences>;
    return {
      theme: isUiTheme(parsed.theme) ? parsed.theme : defaultUiPreferences.theme,
      fontSize: isUiFontSize(parsed.fontSize) ? parsed.fontSize : defaultUiPreferences.fontSize,
    };
  } catch {
    return defaultUiPreferences;
  }
}

function saveStoredUiPreferences(preferences: UiPreferences) {
  window.localStorage.setItem(UI_PREFERENCES_STORAGE_KEY, JSON.stringify(preferences));
}

function clampSidebarWidth(width: number) {
  if (!Number.isFinite(width)) return SIDEBAR_DEFAULT_WIDTH;
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.round(width)));
}

function readStoredSidebarWidth() {
  try {
    const raw = window.localStorage.getItem(SIDEBAR_WIDTH_STORAGE_KEY);
    const parsedWidth = raw ? Number.parseInt(raw, 10) : SIDEBAR_DEFAULT_WIDTH;
    return clampSidebarWidth(parsedWidth);
  } catch {
    return SIDEBAR_DEFAULT_WIDTH;
  }
}

function saveStoredSidebarWidth(width: number) {
  window.localStorage.setItem(SIDEBAR_WIDTH_STORAGE_KEY, String(clampSidebarWidth(width)));
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

function getAccountRole(user: AuthUser | null) {
  return user?.role || 'farmer';
}

function isUnauthorizedError(error: unknown) {
  return error instanceof ApiRequestError && error.status === 401;
}

function fileToAvatarBlob(file: File): Promise<Blob> {
  const allowedTypes = new Set(['image/jpeg', 'image/png', 'image/webp']);
  if (!allowedTypes.has(file.type)) {
    return Promise.reject(new Error('头像只支持 JPG、PNG 或 WebP 图片'));
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
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            reject(new Error('头像处理失败'));
            return;
          }
          if (blob.size > 2 * 1024 * 1024) {
            reject(new Error('头像图片不能超过 2MB'));
            return;
          }
          resolve(blob);
        },
        'image/jpeg',
        0.88,
      );
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
  profile: { displayName: string; username: string },
): Promise<AuthUser> {
  return apiRequest<AuthUser>('/auth/me', {
    method: 'PATCH',
    accessToken,
    payload: {
      display_name: profile.displayName,
      username: profile.username,
    },
  });
}

async function uploadUserAvatar(accessToken: string, avatar: Blob): Promise<AuthUser> {
  const formData = new FormData();
  formData.append('avatar', avatar, 'avatar.jpg');
  return apiRequest<AuthUser>('/auth/me/avatar', {
    method: 'POST',
    accessToken,
    formData,
  });
}

async function fetchProjects(accessToken: string): Promise<ApiProjectResponse[]> {
  return apiRequest<ApiProjectResponse[]>('/projects', {
    accessToken,
  });
}

async function fetchArchivedProjects(accessToken: string): Promise<ApiProjectResponse[]> {
  return apiRequest<ApiProjectResponse[]>('/projects/archived', {
    accessToken,
  });
}

async function fetchProjectConversations(
  accessToken: string,
  projectId: string,
): Promise<ApiDiagnosisConversationResponse[]> {
  return apiRequest<ApiDiagnosisConversationResponse[]>(`/projects/${projectId}/conversations`, {
    accessToken,
  });
}

async function createProjectShare(
  accessToken: string,
  projectId: string,
  payload: ProjectPublicSharePayload,
): Promise<ApiProjectShareResponse> {
  return apiRequest<ApiProjectShareResponse>(`/projects/${projectId}/shares`, {
    method: 'POST',
    accessToken,
    payload: {
      title: payload.title,
      variant: payload.variant,
      content_markdown: payload.contentMarkdown,
    },
  });
}

async function fetchPublicProjectShare(shareToken: string): Promise<ApiPublicProjectShareResponse> {
  return apiRequest<ApiPublicProjectShareResponse>(`/projects/shares/${encodeURIComponent(shareToken)}`);
}

async function createProject(
  accessToken: string,
  project: Pick<CreatedProject, 'name' | 'color' | 'iconKey'>,
): Promise<ApiProjectResponse> {
  return apiRequest<ApiProjectResponse>('/projects', {
    method: 'POST',
    accessToken,
    payload: {
      name: project.name,
      color: project.color,
      icon_key: project.iconKey,
    },
  });
}

async function updateProject(
  accessToken: string,
  projectId: string,
  project: ProjectSettingsUpdate,
): Promise<ApiProjectResponse> {
  return apiRequest<ApiProjectResponse>(`/projects/${projectId}`, {
    method: 'PATCH',
    accessToken,
    payload: {
      name: project.name,
      description: project.description,
      color: project.color,
      icon_key: project.iconKey,
    },
  });
}

async function setProjectPinned(
  accessToken: string,
  projectId: string,
  pinned: boolean,
): Promise<ApiProjectResponse> {
  return apiRequest<ApiProjectResponse>(`/projects/${projectId}/pin`, {
    method: 'PATCH',
    accessToken,
    payload: { pinned },
  });
}

async function archiveProject(accessToken: string, projectId: string): Promise<ApiProjectResponse> {
  return apiRequest<ApiProjectResponse>(`/projects/${projectId}/archive`, {
    method: 'PATCH',
    accessToken,
  });
}

async function restoreProject(accessToken: string, projectId: string): Promise<ApiProjectResponse> {
  return apiRequest<ApiProjectResponse>(`/projects/${projectId}/restore`, {
    method: 'PATCH',
    accessToken,
  });
}

async function deleteProject(accessToken: string, projectId: string): Promise<void> {
  await apiRequest<null>(`/projects/${projectId}`, {
    method: 'DELETE',
    accessToken,
  });
}

async function fetchHusbandryDashboard(accessToken: string, farmId?: string): Promise<ApiHusbandryDashboard> {
  const query = farmId ? `?farm_id=${encodeURIComponent(farmId)}` : '';
  return apiRequest<ApiHusbandryDashboard>(`/husbandry/dashboard${query}`, { accessToken });
}

async function fetchHusbandryFarms(accessToken: string): Promise<ApiFarm[]> {
  return apiRequest<ApiFarm[]>('/husbandry/farms', { accessToken });
}

async function createHusbandryFarm(
  accessToken: string,
  payload: { name: string; location?: string; notes?: string },
): Promise<ApiFarm> {
  return apiRequest<ApiFarm>('/husbandry/farms', {
    method: 'POST',
    accessToken,
    payload,
  });
}

async function updateHusbandryFarm(accessToken: string, farmId: string, payload: { name?: string; location?: string; notes?: string; status?: 'active' | 'archived' }): Promise<ApiFarm> {
  return apiRequest<ApiFarm>(`/husbandry/farms/${farmId}`, { method: 'PATCH', accessToken, payload });
}

async function fetchSilkwormBatches(accessToken: string): Promise<ApiSilkwormBatch[]> {
  return apiRequest<ApiSilkwormBatch[]>('/husbandry/batches', { accessToken });
}

async function createSilkwormBatch(
  accessToken: string,
  payload: {
    farm_id: string;
    batch_code?: string;
    variety?: string;
    instar?: string;
    start_date?: string;
    expected_cocooning_date?: string;
    population_count?: number;
    notes?: string;
  },
): Promise<ApiSilkwormBatch> {
  return apiRequest<ApiSilkwormBatch>('/husbandry/batches', {
    method: 'POST',
    accessToken,
    payload,
  });
}

async function updateSilkwormBatch(accessToken: string, batchId: string, payload: Record<string, unknown>): Promise<ApiSilkwormBatch> {
  return apiRequest<ApiSilkwormBatch>(`/husbandry/batches/${batchId}`, { method: 'PATCH', accessToken, payload });
}

async function fetchHusbandryDailyRecords(accessToken: string, batchId: string): Promise<ApiHusbandryDailyRecord[]> {
  return apiRequest<ApiHusbandryDailyRecord[]>(`/husbandry/batches/${batchId}/daily-records`, { accessToken });
}

async function upsertHusbandryDailyRecord(
  accessToken: string,
  batchId: string,
  payload: {
    record_date: string;
    temperature_celsius?: number;
    humidity_percent?: number;
    feedings?: number;
    leaf_amount_kg?: number;
    sick_count?: number;
    death_count?: number;
    observations?: string;
    management_notes?: string;
  },
): Promise<ApiHusbandryDailyRecord> {
  return apiRequest<ApiHusbandryDailyRecord>(`/husbandry/batches/${batchId}/daily-records`, {
    method: 'PUT',
    accessToken,
    payload,
  });
}

async function deleteHusbandryDailyRecord(accessToken: string, batchId: string, recordId: string): Promise<void> {
  await apiRequest<null>(`/husbandry/batches/${batchId}/daily-records/${recordId}`, { method: 'DELETE', accessToken });
}

async function fetchHusbandryCases(accessToken: string): Promise<ApiHusbandryCase[]> {
  return apiRequest<ApiHusbandryCase[]>('/husbandry/cases', { accessToken });
}

async function createHusbandryCase(
  accessToken: string,
  payload: {
    farm_id: string;
    batch_id?: string | null;
    source_conversation_id?: string | null;
    title: string;
    occurred_on: string;
    symptom_summary?: string;
    suspected_disease?: string;
    severity: HusbandryCaseSeverity;
    status: HusbandryCaseStatus;
    diagnosis_summary?: string;
    recommendation?: string;
  },
): Promise<ApiHusbandryCase> {
  return apiRequest<ApiHusbandryCase>('/husbandry/cases', {
    method: 'POST',
    accessToken,
    payload,
  });
}

async function updateHusbandryCase(accessToken: string, caseId: string, payload: Record<string, unknown>): Promise<ApiHusbandryCase> {
  return apiRequest<ApiHusbandryCase>(`/husbandry/cases/${caseId}`, { method: 'PATCH', accessToken, payload });
}

async function deleteHusbandryCase(accessToken: string, caseId: string): Promise<void> {
  await apiRequest<null>(`/husbandry/cases/${caseId}`, { method: 'DELETE', accessToken });
}

async function addHusbandryCaseFollowUp(
  accessToken: string,
  caseId: string,
  payload: {
    observed_on: string;
    action_taken?: string;
    note?: string;
    affected_count?: number;
    death_count?: number;
    next_follow_up_on?: string;
  },
): Promise<ApiHusbandryCase> {
  return apiRequest<ApiHusbandryCase>(`/husbandry/cases/${caseId}/follow-ups`, {
    method: 'POST',
    accessToken,
    payload,
  });
}

async function updateHusbandryCaseFollowUp(
  accessToken: string,
  caseId: string,
  followUpId: string,
  payload: Record<string, unknown>,
): Promise<ApiHusbandryCase> {
  return apiRequest<ApiHusbandryCase>(`/husbandry/cases/${caseId}/follow-ups/${followUpId}`, { method: 'PATCH', accessToken, payload });
}

async function deleteHusbandryCaseFollowUp(accessToken: string, caseId: string, followUpId: string): Promise<void> {
  await apiRequest<null>(`/husbandry/cases/${caseId}/follow-ups/${followUpId}`, { method: 'DELETE', accessToken });
}

async function uploadHusbandryAssets(
  accessToken: string,
  endpoint: string,
  files: File[],
): Promise<ApiHusbandryAsset[]> {
  if (!files.length) return [];
  const formData = new FormData();
  files.forEach((file) => formData.append('attachments', file));
  return apiRequest<ApiHusbandryAsset[]>(endpoint, { method: 'POST', accessToken, formData });
}

async function deleteHusbandryAsset(accessToken: string, assetId: string): Promise<void> {
  await apiRequest<null>(`/husbandry/assets/${assetId}`, { method: 'DELETE', accessToken });
}

async function fetchDiagnosisConversations(accessToken: string): Promise<ApiDiagnosisConversationResponse[]> {
  return apiRequest<ApiDiagnosisConversationResponse[]>('/diagnosis/conversations', {
    accessToken,
  });
}

async function searchDiagnosisConversations(accessToken: string, query: string): Promise<ApiDiagnosisConversationResponse[]> {
  return apiRequest<ApiDiagnosisConversationResponse[]>(`/diagnosis/search?q=${encodeURIComponent(query)}`, {
    accessToken,
  });
}

async function fetchArchivedDiagnosisConversations(accessToken: string): Promise<ApiDiagnosisConversationResponse[]> {
  return apiRequest<ApiDiagnosisConversationResponse[]>('/diagnosis/conversations/archived', {
    accessToken,
  });
}

async function fetchDiagnosisConversation(
  accessToken: string,
  conversationId: string,
): Promise<ApiDiagnosisConversationDetailResponse> {
  return apiRequest<ApiDiagnosisConversationDetailResponse>(`/diagnosis/conversations/${conversationId}`, {
    accessToken,
  });
}

async function createDiagnosisConversationShare(
  accessToken: string,
  conversationId: string,
  payload: DiagnosisConversationPublicSharePayload,
): Promise<ApiDiagnosisConversationShareResponse> {
  return apiRequest<ApiDiagnosisConversationShareResponse>(`/diagnosis/conversations/${conversationId}/shares`, {
    method: 'POST',
    accessToken,
    payload: {
      title: payload.title,
      variant: payload.variant,
      content_markdown: payload.contentMarkdown,
    },
  });
}

async function fetchPublicDiagnosisConversationShare(
  shareToken: string,
): Promise<ApiPublicDiagnosisConversationShareResponse> {
  return apiRequest<ApiPublicDiagnosisConversationShareResponse>(`/diagnosis/shares/${encodeURIComponent(shareToken)}`);
}

async function createDiagnosisConversation(
  accessToken: string,
  message: string,
  modelConfigId: string | null,
  projectId: string | null = null,
): Promise<ApiDiagnosisConversationTurnResponse> {
  const payload: { message: string; model_config_id: string | null; project_id?: string } = {
    message,
    model_config_id: modelConfigId,
  };
  if (projectId) {
    payload.project_id = projectId;
  }

  return apiRequest<ApiDiagnosisConversationTurnResponse>('/diagnosis/conversations', {
    method: 'POST',
    accessToken,
    payload,
  });
}

async function createDiagnosisConversationMessage(
  accessToken: string,
  conversationId: string,
  message: string,
  modelConfigId: string | null,
): Promise<ApiDiagnosisConversationTurnResponse> {
  return apiRequest<ApiDiagnosisConversationTurnResponse>(`/diagnosis/conversations/${conversationId}/messages`, {
    method: 'POST',
    accessToken,
    payload: { message, model_config_id: modelConfigId },
  });
}

async function transcribeDiagnosisAudio(accessToken: string, audio: File): Promise<ApiDiagnosisVoiceTranscriptionResponse> {
  const formData = new FormData();
  formData.append('audio', audio, audio.name);
  return apiRequest<ApiDiagnosisVoiceTranscriptionResponse>('/diagnosis/transcribe', {
    method: 'POST',
    accessToken,
    formData,
  });
}

type DiagnosisMultimodalSubmitPayload = {
  message: string;
  modelConfigId: string | null;
  attachmentIds: string[];
  structuredData?: Record<string, unknown> | null;
  projectId?: string | null;
};

function buildDiagnosisMultimodalFormData(payload: DiagnosisMultimodalSubmitPayload) {
  const formData = new FormData();
  formData.append('message', payload.message);
  if (payload.modelConfigId) {
    formData.append('model_config_id', payload.modelConfigId);
  }
  if (payload.projectId) {
    formData.append('project_id', payload.projectId);
  }
  if (payload.structuredData && Object.keys(payload.structuredData).length > 0) {
    formData.append('structured_data', JSON.stringify(payload.structuredData));
  }
  payload.attachmentIds.forEach((attachmentId) => {
    formData.append('attachment_ids', attachmentId);
  });
  return formData;
}

async function createDiagnosisMultimodalConversation(
  accessToken: string,
  payload: DiagnosisMultimodalSubmitPayload,
): Promise<ApiDiagnosisConversationTurnResponse> {
  return apiRequest<ApiDiagnosisConversationTurnResponse>('/diagnosis/conversations/multimodal', {
    method: 'POST',
    accessToken,
    formData: buildDiagnosisMultimodalFormData(payload),
  });
}

async function createDiagnosisMultimodalConversationMessage(
  accessToken: string,
  conversationId: string,
  payload: DiagnosisMultimodalSubmitPayload,
): Promise<ApiDiagnosisConversationTurnResponse> {
  return apiRequest<ApiDiagnosisConversationTurnResponse>(`/diagnosis/conversations/${conversationId}/messages/multimodal`, {
    method: 'POST',
    accessToken,
    formData: buildDiagnosisMultimodalFormData(payload),
  });
}

async function uploadDiagnosisAttachment(accessToken: string, attachment: File): Promise<ApiDiagnosisFileResponse> {
  const formData = new FormData();
  formData.append('attachments', attachment, attachment.name);
  const uploaded = await apiRequest<ApiDiagnosisFileResponse[]>('/diagnosis/uploads', {
    method: 'POST',
    accessToken,
    formData,
  });
  const result = uploaded[0];
  if (!result) throw new Error('附件上传失败，请重试');
  return result;
}

async function deleteDiagnosisAttachment(accessToken: string, fileId: string): Promise<void> {
  await apiRequest<null>(`/diagnosis/uploads/${fileId}`, {
    method: 'DELETE',
    accessToken,
  });
}

async function fetchCommunityFeed(
  accessToken: string,
  options: { tab: CommunityFeedTab; query?: string; tag?: string; postType?: CommunityPostType | ''; questionStatus?: 'open' | 'resolved' | ''; region?: string; offset?: number } = { tab: 'recommended' },
): Promise<ApiCommunityPostList> {
  const searchParams = new URLSearchParams({ tab: options.tab, offset: String(options.offset ?? 0) });
  if (options.query?.trim()) searchParams.set('q', options.query.trim());
  if (options.tag?.trim()) searchParams.set('tag', options.tag.trim());
  if (options.postType) searchParams.set('post_type', options.postType);
  if (options.questionStatus) searchParams.set('question_status', options.questionStatus);
  if (options.region?.trim()) searchParams.set('region', options.region.trim());
  return apiRequest<ApiCommunityPostList>(`/community/feed?${searchParams.toString()}`, { accessToken });
}

async function clearCommunityViewHistory(accessToken: string): Promise<void> {
  await apiRequest<null>('/community/history', { method: 'DELETE', accessToken });
}

async function resetCommunityRecommendations(accessToken: string): Promise<void> {
  await apiRequest<null>('/community/recommendations', { method: 'DELETE', accessToken });
}

async function searchCommunity(accessToken: string, query: string): Promise<ApiCommunitySearch> {
  return apiRequest<ApiCommunitySearch>(`/community/search?q=${encodeURIComponent(query.trim())}`, { accessToken });
}

async function fetchCommunityTags(accessToken: string): Promise<ApiCommunityTag[]> {
  return apiRequest<ApiCommunityTag[]>('/community/tags', { accessToken });
}

async function toggleCommunityTopicFollow(accessToken: string, tagId: string): Promise<ApiCommunityTag> {
  return apiRequest<ApiCommunityTag>(`/community/tags/${tagId}/follow`, { method: 'POST', accessToken });
}

async function fetchCommunityBookmarkCollections(accessToken: string, postId = ''): Promise<ApiCommunityBookmarkCollectionList> {
  const query = postId ? `?post_id=${encodeURIComponent(postId)}` : '';
  return apiRequest<ApiCommunityBookmarkCollectionList>(`/community/collections${query}`, { accessToken });
}

async function createCommunityBookmarkCollection(accessToken: string, name: string, description: string): Promise<ApiCommunityBookmarkCollection> {
  return apiRequest<ApiCommunityBookmarkCollection>('/community/collections', { method: 'POST', accessToken, payload: { name, description: description.trim() || null } });
}

async function updateCommunityBookmarkCollection(accessToken: string, collectionId: string, name: string, description: string): Promise<ApiCommunityBookmarkCollection> {
  return apiRequest<ApiCommunityBookmarkCollection>(`/community/collections/${collectionId}`, { method: 'PATCH', accessToken, payload: { name, description: description.trim() || null } });
}

async function deleteCommunityBookmarkCollection(accessToken: string, collectionId: string): Promise<void> {
  await apiRequest<null>(`/community/collections/${collectionId}`, { method: 'DELETE', accessToken });
}

async function fetchCommunityBookmarkCollectionDetail(accessToken: string, collectionId: string): Promise<ApiCommunityBookmarkCollectionDetail> {
  return apiRequest<ApiCommunityBookmarkCollectionDetail>(`/community/collections/${collectionId}`, { accessToken });
}

async function toggleCommunityBookmarkCollectionPost(accessToken: string, collectionId: string, postId: string): Promise<ApiCommunityBookmarkCollection> {
  return apiRequest<ApiCommunityBookmarkCollection>(`/community/collections/${collectionId}/posts/${postId}`, { method: 'POST', accessToken });
}

async function fetchCommunityPost(accessToken: string, postId: string): Promise<ApiCommunityPost> {
  return apiRequest<ApiCommunityPost>(`/community/posts/${postId}`, { accessToken });
}

async function createCommunityPost(
  accessToken: string,
  payload: {
    title: string;
    contentMarkdown: string;
    postType: CommunityPostType;
    visibility: CommunityPostVisibility;
    tags: string[];
    fileIds: string[];
    coverFileId?: string | null;
    publish: boolean;
    sourceConversationId?: string | null;
    caseData?: Record<string, string | number | null>;
  },
): Promise<ApiCommunityPost> {
  return apiRequest<ApiCommunityPost>('/community/posts', {
    method: 'POST',
    accessToken,
    payload: {
      title: payload.title,
      content_markdown: payload.contentMarkdown,
      post_type: payload.postType,
      visibility: payload.visibility,
      tags: payload.tags,
      file_ids: payload.fileIds,
      cover_file_id: payload.coverFileId ?? null,
      publish: payload.publish,
      source_conversation_id: payload.sourceConversationId ?? null,
      case_data: payload.caseData ?? {},
    },
  });
}

async function updateCommunityPost(
  accessToken: string,
  postId: string,
  payload: Partial<{
    title: string;
    contentMarkdown: string;
    postType: CommunityPostType;
    visibility: CommunityPostVisibility;
    tags: string[];
    fileIds: string[];
    coverFileId: string | null;
    publish: boolean;
    caseData: Record<string, string | number | null>;
  }>,
): Promise<ApiCommunityPost> {
  return apiRequest<ApiCommunityPost>(`/community/posts/${postId}`, {
    method: 'PATCH',
    accessToken,
    payload: {
      ...(payload.title !== undefined ? { title: payload.title } : {}),
      ...(payload.contentMarkdown !== undefined ? { content_markdown: payload.contentMarkdown } : {}),
      ...(payload.postType !== undefined ? { post_type: payload.postType } : {}),
      ...(payload.visibility !== undefined ? { visibility: payload.visibility } : {}),
      ...(payload.tags !== undefined ? { tags: payload.tags } : {}),
      ...(payload.fileIds !== undefined ? { file_ids: payload.fileIds } : {}),
      ...(payload.coverFileId !== undefined ? { cover_file_id: payload.coverFileId } : {}),
      ...(payload.publish !== undefined ? { publish: payload.publish } : {}),
      ...(payload.caseData !== undefined ? { case_data: payload.caseData } : {}),
    },
  });
}

async function deleteCommunityPost(accessToken: string, postId: string): Promise<void> {
  await apiRequest<null>(`/community/posts/${postId}`, { method: 'DELETE', accessToken });
}

async function toggleCommunityPostLike(accessToken: string, postId: string): Promise<ApiCommunityPost> {
  return apiRequest<ApiCommunityPost>(`/community/posts/${postId}/like`, { method: 'POST', accessToken });
}

async function toggleCommunityPostBookmark(accessToken: string, postId: string): Promise<ApiCommunityPost> {
  return apiRequest<ApiCommunityPost>(`/community/posts/${postId}/bookmark`, { method: 'POST', accessToken });
}

async function fetchCommunityComments(accessToken: string, postId: string, sort: 'top' | 'latest' = 'top'): Promise<ApiCommunityCommentList> {
  return apiRequest<ApiCommunityCommentList>(`/community/posts/${postId}/comments?sort=${sort}`, { accessToken });
}

async function createCommunityComment(
  accessToken: string,
  postId: string,
  content: string,
  parentCommentId: string | null = null,
): Promise<ApiCommunityComment> {
  return apiRequest<ApiCommunityComment>(`/community/posts/${postId}/comments`, {
    method: 'POST',
    accessToken,
    payload: { content, parent_comment_id: parentCommentId },
  });
}

async function toggleCommunityCommentLike(accessToken: string, commentId: string): Promise<ApiCommunityComment> {
  return apiRequest<ApiCommunityComment>(`/community/comments/${commentId}/like`, { method: 'POST', accessToken });
}

async function updateCommunityComment(accessToken: string, commentId: string, content: string): Promise<ApiCommunityComment> {
  return apiRequest<ApiCommunityComment>(`/community/comments/${commentId}`, {
    method: 'PATCH',
    accessToken,
    payload: { content },
  });
}

async function deleteCommunityComment(accessToken: string, commentId: string): Promise<void> {
  await apiRequest<null>(`/community/comments/${commentId}`, { method: 'DELETE', accessToken });
}

async function reportCommunityPost(
  accessToken: string,
  postId: string,
  reason: string,
  detail: string,
): Promise<void> {
  await apiRequest<null>(`/community/posts/${postId}/reports`, {
    method: 'POST',
    accessToken,
    payload: { target_type: 'post', reason, detail: detail.trim() || null },
  });
}

async function toggleCommunityFollow(accessToken: string, userId: string): Promise<ApiCommunityAuthor> {
  return apiRequest<ApiCommunityAuthor>(`/community/users/${userId}/follow`, { method: 'POST', accessToken });
}

async function fetchCommunityProfileDetail(accessToken: string, userId: string): Promise<ApiCommunityProfileDetail> {
  return apiRequest<ApiCommunityProfileDetail>(`/community/users/${userId}/posts`, { accessToken });
}

async function fetchCommunityRelationships(
  accessToken: string,
  userId: string,
  relationshipType: CommunityRelationshipType,
  offset = 0,
): Promise<ApiCommunityRelationshipList> {
  const query = new URLSearchParams({ relationship_type: relationshipType, offset: String(offset) });
  return apiRequest<ApiCommunityRelationshipList>(`/community/users/${userId}/relationships?${query.toString()}`, { accessToken });
}

async function fetchCommunityBlockedUsers(accessToken: string): Promise<ApiCommunityBlockedUserList> {
  return apiRequest<ApiCommunityBlockedUserList>('/community/blocked-users', { accessToken });
}

async function fetchCommunityCreatorOverview(accessToken: string): Promise<ApiCommunityCreatorOverview> {
  return apiRequest<ApiCommunityCreatorOverview>('/community/creator/overview', { accessToken });
}

async function updateCommunityProfile(
  accessToken: string,
  payload: {
    identity_type: ApiCommunityAuthor['identity_type'];
    region: string | null;
    organization: string | null;
    expertise_tags: string[];
    years_experience: number | null;
    bio: string | null;
    request_verification: boolean;
  },
): Promise<ApiCommunityAuthor> {
  return apiRequest<ApiCommunityAuthor>('/community/profile', { method: 'PUT', accessToken, payload });
}

async function toggleCommunityUserBlock(accessToken: string, userId: string): Promise<{ blocked: boolean }> {
  return apiRequest<{ blocked: boolean }>(`/community/users/${userId}/block`, { method: 'POST', accessToken });
}

async function hideCommunityPost(accessToken: string, postId: string): Promise<void> {
  await apiRequest(`/community/posts/${postId}/not-interested`, { method: 'POST', accessToken });
}

async function acceptCommunityAnswer(accessToken: string, postId: string, commentId: string): Promise<ApiCommunityPost> {
  return apiRequest<ApiCommunityPost>(`/community/posts/${postId}/answers/${commentId}/accept`, { method: 'POST', accessToken });
}

async function addCommunityCaseUpdate(
  accessToken: string,
  postId: string,
  payload: { occurred_on: string; outcome_status: ApiCommunityCaseUpdate['outcome_status']; content: string },
): Promise<ApiCommunityCaseUpdate> {
  return apiRequest<ApiCommunityCaseUpdate>(`/community/posts/${postId}/case-updates`, { method: 'POST', accessToken, payload: { ...payload, metrics: {} } });
}

async function saveCommunityPostToHusbandry(
  accessToken: string,
  postId: string,
  farmId: string,
  batchId: string | null,
): Promise<{ case_id: string }> {
  return apiRequest<{ case_id: string }>(`/community/posts/${postId}/save-to-husbandry`, {
    method: 'POST', accessToken, payload: { farm_id: farmId, batch_id: batchId },
  });
}

async function fetchCommunityNotifications(accessToken: string): Promise<ApiCommunityNotifications> {
  return apiRequest<ApiCommunityNotifications>('/community/notifications', { accessToken });
}

async function streamCommunityEvents(
  accessToken: string,
  signal: AbortSignal,
  onEvent: (event: CommunityRealtimeEvent) => void,
): Promise<void> {
  let lastError: Error | null = null;
  for (const baseUrl of API_BASE_URLS) {
    try {
      const response = await fetch(`${baseUrl}/community/events`, {
        headers: { Authorization: `Bearer ${accessToken}`, Accept: 'text/event-stream' },
        signal,
      });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new ApiRequestError(getApiErrorMessage(data, `实时连接失败：${response.status}`), response.status);
      }
      if (!response.body) throw new Error('浏览器不支持实时社区连接');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      try {
        while (!signal.aborted) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let boundary = buffer.indexOf('\n\n');
          while (boundary >= 0) {
            const frame = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            const eventName = frame.match(/^event:\s*(.+)$/m)?.[1]?.trim() ?? 'message';
            const data = frame.match(/^data:\s*(.*)$/m)?.[1];
            if (data) {
              try {
                onEvent({ ...(JSON.parse(data) as CommunityRealtimeEvent), type: eventName });
              } catch {
                // Keep the persistent API as source of truth if a transient event is malformed.
              }
            }
            boundary = buffer.indexOf('\n\n');
          }
        }
      } finally {
        reader.releaseLock();
      }
      return;
    } catch (error) {
      if (signal.aborted) return;
      if (error instanceof ApiRequestError) throw error;
      lastError = error instanceof Error ? error : new Error('实时连接失败');
      if (import.meta.env.VITE_API_BASE_URL) throw lastError;
    }
  }
  throw lastError ?? new Error('实时连接失败');
}

async function markCommunityNotificationsRead(accessToken: string): Promise<void> {
  await apiRequest<null>('/community/notifications/read', { method: 'POST', accessToken });
}

async function fetchCommunityDirectThreads(accessToken: string): Promise<{ items: ApiCommunityDirectThread[] }> {
  return apiRequest<{ items: ApiCommunityDirectThread[] }>('/community/direct/threads', { accessToken });
}

async function fetchCommunityDirectMessages(accessToken: string, threadId: string): Promise<{ items: ApiCommunityDirectMessage[]; next_offset: number | null }> {
  return apiRequest<{ items: ApiCommunityDirectMessage[]; next_offset: number | null }>(`/community/direct/threads/${threadId}/messages`, { accessToken });
}

async function sendCommunityDirectMessage(accessToken: string, userId: string, content: string): Promise<ApiCommunityDirectMessage> {
  return apiRequest<ApiCommunityDirectMessage>(`/community/users/${userId}/direct-messages`, {
    method: 'POST',
    accessToken,
    payload: { content },
  });
}

async function uploadCommunityAttachments(accessToken: string, files: File[]): Promise<ApiCommunityUpload[]> {
  const formData = new FormData();
  files.forEach((file) => formData.append('attachments', file, file.name));
  return apiRequest<ApiCommunityUpload[]>('/community/uploads', { method: 'POST', accessToken, formData });
}

async function createCommunityDraftFromConversation(
  accessToken: string,
  conversationId: string,
  attachmentIds: string[],
): Promise<ApiCommunityPost> {
  return apiRequest<ApiCommunityPost>(`/community/posts/from-conversation/${conversationId}/draft`, {
    method: 'POST',
    accessToken,
    payload: { include_attachment_ids: attachmentIds },
  });
}

async function createCommunityDraftFromHusbandryCase(
  accessToken: string,
  caseId: string,
  title?: string,
): Promise<ApiCommunityPost> {
  return apiRequest<ApiCommunityPost>(`/community/posts/from-husbandry-case/${caseId}/draft`, {
    method: 'POST',
    accessToken,
    payload: { title },
  });
}

async function fetchModelConfigs(accessToken: string): Promise<ApiModelConfigResponse[]> {
  return apiRequest<ApiModelConfigResponse[]>('/model-configs', {
    accessToken,
  });
}

async function createModelConfig(accessToken: string, draft: ModelConfigDraft): Promise<ApiModelConfigResponse> {
  return apiRequest<ApiModelConfigResponse>('/model-configs', {
    method: 'POST',
    accessToken,
    payload: {
      provider_name: draft.providerName,
      model_id: draft.modelId,
      api_key: draft.apiKey,
      api_request_url: draft.apiRequestUrl,
      is_enabled: true,
      is_default: false,
    },
  });
}

async function updateModelConfig(
  accessToken: string,
  modelConfigId: string,
  draft: ModelConfigDraft,
): Promise<ApiModelConfigResponse> {
  return apiRequest<ApiModelConfigResponse>(`/model-configs/${modelConfigId}`, {
    method: 'PATCH',
    accessToken,
    payload: {
      provider_name: draft.providerName,
      model_id: draft.modelId,
      api_key: draft.apiKey.trim() || undefined,
      api_request_url: draft.apiRequestUrl,
    },
  });
}

async function deleteModelConfig(accessToken: string, modelConfigId: string): Promise<void> {
  await apiRequest<null>(`/model-configs/${modelConfigId}`, {
    method: 'DELETE',
    accessToken,
  });
}

async function setDefaultModelConfig(accessToken: string, modelConfigId: string): Promise<ApiModelConfigResponse> {
  return apiRequest<ApiModelConfigResponse>(`/model-configs/${modelConfigId}/set-default`, {
    method: 'POST',
    accessToken,
  });
}

async function testModelConfig(accessToken: string, modelConfigId: string): Promise<ApiModelConfigTestResponse> {
  return apiRequest<ApiModelConfigTestResponse>(`/model-configs/${modelConfigId}/test`, {
    method: 'POST',
    accessToken,
  });
}

async function fetchUserSettings(accessToken: string): Promise<ApiUserSettingsResponse> {
  return apiRequest<ApiUserSettingsResponse>('/settings/me', { accessToken });
}

async function updateUserSettings(
  accessToken: string,
  preferences: Partial<UserPreferences>,
): Promise<ApiUserSettingsResponse> {
  return apiRequest<ApiUserSettingsResponse>('/settings/me', {
    method: 'PATCH',
    accessToken,
    payload: { preferences },
  });
}

async function fetchUserDeviceSessions(accessToken: string): Promise<ApiUserDeviceSession[]> {
  return apiRequest<ApiUserDeviceSession[]>('/settings/me/sessions', { accessToken });
}

async function revokeUserDeviceSession(accessToken: string, sessionId: string): Promise<void> {
  await apiRequest<null>(`/settings/me/sessions/${sessionId}`, { method: 'DELETE', accessToken });
}

async function revokeOtherUserDeviceSessions(accessToken: string): Promise<void> {
  await apiRequest<null>('/settings/me/sessions/revoke-others', { method: 'POST', accessToken });
}

async function exportUserSettingsData(accessToken: string): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>('/settings/me/export', { accessToken });
}

async function deleteUserAccount(accessToken: string, confirmation: string): Promise<void> {
  await apiRequest<null>('/settings/me', {
    method: 'DELETE',
    accessToken,
    payload: { confirmation },
  });
}

async function updateDiagnosisConversation(
  accessToken: string,
  conversationId: string,
  title: string,
): Promise<ApiDiagnosisConversationResponse> {
  return apiRequest<ApiDiagnosisConversationResponse>(`/diagnosis/conversations/${conversationId}`, {
    method: 'PATCH',
    accessToken,
    payload: { title },
  });
}

async function moveDiagnosisConversationProject(
  accessToken: string,
  conversationId: string,
  projectId: string | null,
): Promise<ApiDiagnosisConversationResponse> {
  return apiRequest<ApiDiagnosisConversationResponse>(`/diagnosis/conversations/${conversationId}/project`, {
    method: 'PATCH',
    accessToken,
    payload: { project_id: projectId },
  });
}

async function setDiagnosisConversationPinned(
  accessToken: string,
  conversationId: string,
  pinned: boolean,
): Promise<ApiDiagnosisConversationResponse> {
  return apiRequest<ApiDiagnosisConversationResponse>(`/diagnosis/conversations/${conversationId}/pin`, {
    method: 'PATCH',
    accessToken,
    payload: { pinned },
  });
}

async function archiveDiagnosisConversation(
  accessToken: string,
  conversationId: string,
): Promise<ApiDiagnosisConversationResponse> {
  return apiRequest<ApiDiagnosisConversationResponse>(`/diagnosis/conversations/${conversationId}/archive`, {
    method: 'PATCH',
    accessToken,
  });
}

async function restoreDiagnosisConversation(
  accessToken: string,
  conversationId: string,
): Promise<ApiDiagnosisConversationResponse> {
  return apiRequest<ApiDiagnosisConversationResponse>(`/diagnosis/conversations/${conversationId}/restore`, {
    method: 'PATCH',
    accessToken,
  });
}

async function deleteDiagnosisConversation(accessToken: string, conversationId: string): Promise<void> {
  await apiRequest<null>(`/diagnosis/conversations/${conversationId}`, {
    method: 'DELETE',
    accessToken,
  });
}

async function updateDiagnosisMessage(
  accessToken: string,
  conversationId: string,
  messageId: string,
  content: string,
): Promise<ApiDiagnosisMessageMutationResponse> {
  return apiRequest<ApiDiagnosisMessageMutationResponse>(`/diagnosis/conversations/${conversationId}/messages/${messageId}`, {
    method: 'PATCH',
    accessToken,
    payload: { content },
  });
}

async function deleteDiagnosisMessage(
  accessToken: string,
  conversationId: string,
  messageId: string,
): Promise<ApiDiagnosisConversationDetailResponse> {
  return apiRequest<ApiDiagnosisConversationDetailResponse>(`/diagnosis/conversations/${conversationId}/messages/${messageId}`, {
    method: 'DELETE',
    accessToken,
  });
}

async function setDiagnosisMessageFeedback(
  accessToken: string,
  conversationId: string,
  messageId: string,
  feedback: 'like' | 'dislike' | null,
  feedbackReasons: string[] = [],
  feedbackDetail: string | null = null,
): Promise<ApiDiagnosisMessageMutationResponse> {
  return apiRequest<ApiDiagnosisMessageMutationResponse>(
    `/diagnosis/conversations/${conversationId}/messages/${messageId}/feedback`,
    {
      method: 'PATCH',
      accessToken,
      payload: {
        feedback,
        feedback_reasons: feedbackReasons,
        feedback_detail: feedbackDetail,
      },
    },
  );
}

async function regenerateDiagnosisMessage(
  accessToken: string,
  conversationId: string,
  messageId: string,
  modelConfigId: string | null,
): Promise<ApiDiagnosisMessageMutationResponse> {
  return apiRequest<ApiDiagnosisMessageMutationResponse>(
    `/diagnosis/conversations/${conversationId}/messages/${messageId}/regenerate`,
    {
      method: 'POST',
      accessToken,
      payload: { model_config_id: modelConfigId },
    },
  );
}

async function apiRequest<T>(
  path: string,
  options: { method?: string; payload?: unknown; accessToken?: string; formData?: FormData } = {},
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
        body: options.formData ?? (options.payload !== undefined ? JSON.stringify(options.payload) : undefined),
      });
      const data = await response.json().catch(() => null);

      if (response.ok) {
        return data as T;
      }

      lastError = getApiErrorMessage(data, `请求失败：${response.status}`);
      lastApiError = new ApiRequestError(lastError, response.status);
      throw lastApiError;
    } catch (error) {
      if (error instanceof ApiRequestError) {
        throw error;
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

function getPublicShareTokenFromPath() {
  const match = window.location.pathname.match(/^\/share\/([^/?#]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function getPublicProjectShareTokenFromPath() {
  const match = window.location.pathname.match(/^\/project-share\/([^/?#]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function App() {
  const publicShareToken = getPublicShareTokenFromPath();
  if (publicShareToken) {
    return <PublicDiagnosisSharePage shareToken={publicShareToken} />;
  }

  const publicProjectShareToken = getPublicProjectShareTokenFromPath();
  if (publicProjectShareToken) {
    return <PublicProjectSharePage shareToken={publicProjectShareToken} />;
  }

  return <MainApp />;
}

function MainApp() {
  const [activeThread, setActiveThread] = useState<ThreadKey>('diagnosis');
  const [activeProjectChatId, setActiveProjectChatId] = useState<string | null>(null);
  const [authState, setAuthState] = useState<AuthSessionState | null>(() => readStoredAuth());
  const [createdProjects, setCreatedProjects] = useState<CreatedProject[]>([]);
  const [archivedProjects, setArchivedProjects] = useState<CreatedProject[]>([]);
  const [archivedProjectsLoading, setArchivedProjectsLoading] = useState(false);
  const [archivedProjectsError, setArchivedProjectsError] = useState('');
  const [archiveSavingProjectId, setArchiveSavingProjectId] = useState<string | null>(null);
  const [diagnosisMessages, setDiagnosisMessages] = useState<DiagnosisMessage[]>([]);
  const [diagnosisExpertReviews, setDiagnosisExpertReviews] = useState<ApiDiagnosisExpertReview[]>([]);
  const [diagnosisSessionId, setDiagnosisSessionId] = useState(0);
  const [activeDiagnosisConversationId, setActiveDiagnosisConversationId] = useState<string | null>(null);
  const [toolCaseSourceConversationId, setToolCaseSourceConversationId] = useState<string | null>(null);
  const [inlineCaseConversationId, setInlineCaseConversationId] = useState<string | null>(null);
  const [activeConversationSource, setActiveConversationSource] = useState<ActiveConversationSource>(null);
  const [diagnosisConversations, setDiagnosisConversations] = useState<DiagnosisConversation[]>([]);
  const [archivedDiagnosisConversations, setArchivedDiagnosisConversations] = useState<DiagnosisConversation[]>([]);
  const [archivedDiagnosisLoading, setArchivedDiagnosisLoading] = useState(false);
  const [archivedDiagnosisError, setArchivedDiagnosisError] = useState('');
  const [archiveSavingConversationId, setArchiveSavingConversationId] = useState<string | null>(null);
  const [diagnosisSending, setDiagnosisSending] = useState(false);
  const [diagnosisHistoryLoading, setDiagnosisHistoryLoading] = useState(false);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [projectsError, setProjectsError] = useState('');
  const [projectConversationsById, setProjectConversationsById] = useState<Record<string, DiagnosisConversation[]>>({});
  const [projectConversationsLoadingId, setProjectConversationsLoadingId] = useState<string | null>(null);
  const [projectConversationsError, setProjectConversationsError] = useState('');
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [pendingProjectMoveConversationId, setPendingProjectMoveConversationId] = useState<string | null>(null);
  const [chatSearchOpen, setChatSearchOpen] = useState(false);
  const [toast, setToast] = useState<AppToastState | null>(null);
  const [deleteConfirmConversation, setDeleteConfirmConversation] = useState<DiagnosisConversation | null>(null);
  const [deleteSavingConversationId, setDeleteSavingConversationId] = useState<string | null>(null);
  const [deleteErrorConversationId, setDeleteErrorConversationId] = useState<string | null>(null);
  const [conversationShareContext, setConversationShareContext] = useState<{
    conversation: DiagnosisConversation | null;
    messages: DiagnosisMessage[];
    title: string;
  } | null>(null);
  const [projectShareContext, setProjectShareContext] = useState<{
    project: CreatedProject;
    conversations: ProjectShareConversation[];
  } | null>(null);
  const [communityDraftPost, setCommunityDraftPost] = useState<ApiCommunityPost | null>(null);
  const [deleteConfirmProject, setDeleteConfirmProject] = useState<CreatedProject | null>(null);
  const [deleteSavingProjectId, setDeleteSavingProjectId] = useState<string | null>(null);
  const [deleteErrorProjectId, setDeleteErrorProjectId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(() => readStoredSidebarWidth());
  const [sidebarResizing, setSidebarResizing] = useState(false);
  const [uiPreferences, setUiPreferences] = useState<UiPreferences>(() => readStoredUiPreferences());
  const [userPreferences, setUserPreferences] = useState<UserPreferences>(defaultUserPreferences);
  const [userSettingsLoading, setUserSettingsLoading] = useState(false);
  const [userSettingsError, setUserSettingsError] = useState('');
  const [deviceSessions, setDeviceSessions] = useState<ApiUserDeviceSession[]>([]);
  const [deviceSessionsLoading, setDeviceSessionsLoading] = useState(false);
  const [configuredModels, setConfiguredModels] = useState<ConfiguredModel[]>([]);
  const [modelConfigsLoading, setModelConfigsLoading] = useState(false);
  const [modelConfigsError, setModelConfigsError] = useState('');
  const [modelConfigSaving, setModelConfigSaving] = useState(false);
  const [testingModelConfigId, setTestingModelConfigId] = useState<string | null>(null);
  const [selectedModelConfigId, setSelectedModelConfigId] = useState<string | null>(() => readSelectedModelConfigId());
  const toastTimerRef = useRef<number | null>(null);
  const sidebarResizeStateRef = useRef<{ startWidth: number; startX: number } | null>(null);
  const isAuthenticated = Boolean(authState);
  const selectedModel = useMemo(
    () => configuredModels.find((model) => model.id === selectedModelConfigId) ?? configuredModels.find((model) => model.isDefault) ?? configuredModels[0] ?? null,
    [configuredModels, selectedModelConfigId],
  );
  const sortedCreatedProjects = useMemo(
    () => sortProjectsByPin(createdProjects),
    [createdProjects],
  );
  const sortedDiagnosisConversations = useMemo(
    () => sortDiagnosisConversationsByPin(diagnosisConversations),
    [diagnosisConversations],
  );
  const pinnedProjectIds = useMemo(
    () => createdProjects.filter((project) => project.pinnedAt).map((project) => project.id),
    [createdProjects],
  );
  const pinnedDiagnosisConversationIds = useMemo(
    () => diagnosisConversations.filter((conversation) => conversation.pinnedAt).map((conversation) => conversation.id),
    [diagnosisConversations],
  );
  const activeDiagnosisConversation = useMemo(
    () =>
      activeDiagnosisConversationId
        ? diagnosisConversations.find((conversation) => conversation.id === activeDiagnosisConversationId) ?? null
        : null,
    [activeDiagnosisConversationId, diagnosisConversations],
  );
  const showToast = (message: string, tone: ToastTone = 'success') => {
    if (!userPreferences.in_app_notifications && tone !== 'error') return;
    if (toastTimerRef.current) {
      window.clearTimeout(toastTimerRef.current);
    }
    setToast({ id: Date.now(), message, tone });
    toastTimerRef.current = window.setTimeout(() => {
      setToast(null);
      toastTimerRef.current = null;
    }, 2200);
  };

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        window.clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  const sidebarProjectFolders = useMemo<ProjectFolder[]>(
    () => [
      ...sortedCreatedProjects.map((project) => ({
        id: project.id,
        name: project.name,
        chats: [],
        color: project.color,
        iconKey: project.iconKey,
        pinned: pinnedProjectIds.includes(project.id),
      })),
      ...projectFolders,
    ],
    [pinnedProjectIds, sortedCreatedProjects],
  );

  const projectRows = useMemo(() => [...sortedCreatedProjects, ...defaultProjectRows], [sortedCreatedProjects]);
  const activeProject = useMemo(
    () => (activeProjectChatId ? projectRows.find((project) => project.id === activeProjectChatId) ?? null : null),
    [activeProjectChatId, projectRows],
  );

  useEffect(() => {
    try {
      window.localStorage.removeItem('canw.projects.local');
    } catch {
      // Ignore local cleanup failures; the backend project API will become the source of truth.
    }
    setCreatedProjects([]);
  }, []);

  useEffect(() => {
    saveStoredUiPreferences(uiPreferences);
    document.documentElement.style.colorScheme = uiPreferences.theme;
  }, [uiPreferences]);

  useEffect(() => {
    if (!authState?.accessToken) {
      setUserPreferences(defaultUserPreferences);
      setUserSettingsError('');
      setUserSettingsLoading(false);
      setDeviceSessions([]);
      return;
    }

    let ignore = false;
    const syncUserSettings = async (accessToken: string) => {
      const response = await fetchUserSettings(accessToken);
      if (ignore) return;
      const preferences = { ...defaultUserPreferences, ...response.preferences };
      setUserPreferences(preferences);
      setUiPreferences({ theme: preferences.theme, fontSize: preferences.font_size });
      setUserSettingsError('');
    };

    const loadUserSettings = async () => {
      setUserSettingsLoading(true);
      try {
        await syncUserSettings(authState.accessToken);
      } catch (error) {
        if (ignore) return;
        if (isUnauthorizedError(error)) {
          try {
            const refreshedAuthState = await handleTokenRefresh();
            await syncUserSettings(refreshedAuthState.accessToken);
          } catch {
            if (!ignore) handleAuthExpired();
          }
          return;
        }
        setUserSettingsError(error instanceof Error ? error.message : '设置加载失败');
      } finally {
        if (!ignore) setUserSettingsLoading(false);
      }
    };

    void loadUserSettings();
    return () => {
      ignore = true;
    };
  }, [authState?.accessToken]);

  useEffect(() => {
    if (!authState?.accessToken || activeThread !== 'settings') return;
    let ignore = false;

    const loadDeviceSessions = async (accessToken: string) => {
      const sessions = await fetchUserDeviceSessions(accessToken);
      if (!ignore) setDeviceSessions(sessions);
    };

    const run = async () => {
      setDeviceSessionsLoading(true);
      try {
        await loadDeviceSessions(authState.accessToken);
      } catch (error) {
        if (isUnauthorizedError(error)) {
          try {
            const refreshedAuthState = await handleTokenRefresh();
            await loadDeviceSessions(refreshedAuthState.accessToken);
          } catch {
            if (!ignore) handleAuthExpired();
          }
        } else if (!ignore) {
          setUserSettingsError(error instanceof Error ? error.message : '设备列表加载失败');
        }
      } finally {
        if (!ignore) setDeviceSessionsLoading(false);
      }
    };

    void run();
    return () => {
      ignore = true;
    };
  }, [activeThread, authState?.accessToken]);

  useEffect(() => {
    saveSelectedModelConfigId(selectedModelConfigId);
  }, [selectedModelConfigId]);

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

  useEffect(() => {
    if (!authState?.accessToken) {
      setCreatedProjects([]);
      setArchivedProjects([]);
      setArchivedProjectsError('');
      setArchivedProjectsLoading(false);
      setProjectConversationsById({});
      setProjectConversationsError('');
      setProjectConversationsLoadingId(null);
      setProjectsError('');
      setProjectsLoading(false);
      return;
    }

    let ignore = false;

    const syncProjects = async (accessToken: string) => {
      const [projects, archived] = await Promise.all([
        fetchProjects(accessToken),
        fetchArchivedProjects(accessToken),
      ]);
      if (ignore) return;
      setCreatedProjects(projects.map(mapApiProject));
      setArchivedProjects(archived.map(mapApiProject));
      setProjectsError('');
      setArchivedProjectsError('');
    };

    const loadProjects = async () => {
      setProjectsLoading(true);
      setArchivedProjectsLoading(true);
      try {
        await syncProjects(authState.accessToken);
      } catch (error) {
        if (ignore) return;
        if (isUnauthorizedError(error)) {
          try {
            const refreshedAuthState = await handleTokenRefresh();
            await syncProjects(refreshedAuthState.accessToken);
          } catch {
            if (!ignore) handleAuthExpired();
          }
          return;
        }
        setProjectsError(error instanceof Error ? error.message : '项目加载失败');
        setArchivedProjectsError(error instanceof Error ? error.message : '归档项目加载失败');
      } finally {
        if (!ignore) {
          setProjectsLoading(false);
          setArchivedProjectsLoading(false);
        }
      }
    };

    void loadProjects();

    return () => {
      ignore = true;
    };
  }, [authState?.accessToken]);

  useEffect(() => {
    if (!authState?.accessToken) {
      setConfiguredModels([]);
      setModelConfigsError('');
      setModelConfigsLoading(false);
      return;
    }

    let ignore = false;

    const syncModelConfigs = async (accessToken: string) => {
      const modelConfigs = await fetchModelConfigs(accessToken);
      if (ignore) return;
      const nextModels = modelConfigs.map(mapApiModelConfig);
      setConfiguredModels(nextModels);
      setModelConfigsError('');
      setSelectedModelConfigId((currentId) => {
        if (currentId && nextModels.some((model) => model.id === currentId)) return currentId;
        return nextModels.find((model) => model.isDefault)?.id ?? nextModels[0]?.id ?? null;
      });
    };

    const loadModelConfigs = async () => {
      setModelConfigsLoading(true);
      try {
        await syncModelConfigs(authState.accessToken);
      } catch (error) {
        if (ignore) return;
        if (isUnauthorizedError(error)) {
          try {
            const refreshedAuthState = await handleTokenRefresh();
            await syncModelConfigs(refreshedAuthState.accessToken);
          } catch {
            if (!ignore) handleAuthExpired();
          }
          return;
        }
        setModelConfigsError(error instanceof Error ? error.message : '模型配置加载失败');
      } finally {
        if (!ignore) setModelConfigsLoading(false);
      }
    };

    void loadModelConfigs();

    return () => {
      ignore = true;
    };
  }, [authState?.accessToken]);

  useEffect(() => {
    if (!authState?.accessToken) {
      setDiagnosisConversations([]);
      setArchivedDiagnosisConversations([]);
      setArchivedDiagnosisError('');
      setArchivedDiagnosisLoading(false);
      setActiveDiagnosisConversationId(null);
      setDiagnosisMessages([]);
      setDiagnosisHistoryLoading(false);
      return;
    }

    let ignore = false;

    const syncDiagnosisConversations = async (accessToken: string) => {
      const [conversations, archivedConversations] = await Promise.all([
        fetchDiagnosisConversations(accessToken),
        fetchArchivedDiagnosisConversations(accessToken),
      ]);
      if (ignore) return;
      setDiagnosisConversations(conversations.map(mapApiDiagnosisConversation));
      setArchivedDiagnosisConversations(archivedConversations.map(mapApiDiagnosisConversation));
      setArchivedDiagnosisError('');
    };

    const loadDiagnosisConversations = async () => {
      setDiagnosisHistoryLoading(true);
      setArchivedDiagnosisLoading(true);
      try {
        await syncDiagnosisConversations(authState.accessToken);
      } catch (error) {
        if (ignore) return;
        if (isUnauthorizedError(error)) {
          try {
            const refreshedAuthState = await handleTokenRefresh();
            await syncDiagnosisConversations(refreshedAuthState.accessToken);
          } catch {
            if (!ignore) handleAuthExpired();
          }
          return;
        }
        setArchivedDiagnosisError(error instanceof Error ? error.message : '归档对话加载失败');
      } finally {
        if (!ignore) setDiagnosisHistoryLoading(false);
        if (!ignore) setArchivedDiagnosisLoading(false);
      }
    };

    void loadDiagnosisConversations();

    return () => {
      ignore = true;
    };
  }, [authState?.accessToken]);

  useEffect(() => {
    if (!authState?.accessToken || activeThread !== 'projects' || !activeProject?.id) return;

    let ignore = false;
    const projectId = activeProject.id;

    const syncProjectConversations = async (accessToken: string) => {
      const conversations = await fetchProjectConversations(accessToken, projectId);
      if (ignore) return;
      setProjectConversationsById((current) => ({
        ...current,
        [projectId]: conversations.map(mapApiDiagnosisConversation),
      }));
      setProjectConversationsError('');
    };

    const loadProjectConversations = async () => {
      setProjectConversationsLoadingId(projectId);
      setProjectConversationsError('');
      try {
        await syncProjectConversations(authState.accessToken);
      } catch (error) {
        if (ignore) return;
        if (isUnauthorizedError(error)) {
          try {
            const refreshedAuthState = await handleTokenRefresh();
            await syncProjectConversations(refreshedAuthState.accessToken);
          } catch {
            if (!ignore) handleAuthExpired();
          }
          return;
        }
        setProjectConversationsError(error instanceof Error ? error.message : '项目对话加载失败');
      } finally {
        if (!ignore) setProjectConversationsLoadingId(null);
      }
    };

    void loadProjectConversations();

    return () => {
      ignore = true;
    };
  }, [activeProject?.id, activeThread, authState?.accessToken]);

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

  const syncProjectConversationLocally = (conversation: ApiDiagnosisConversationResponse) => {
    const nextConversation = mapApiDiagnosisConversation(conversation);
    setProjectConversationsById((currentLists) => {
      const nextLists: Record<string, DiagnosisConversation[]> = {};

      Object.entries(currentLists).forEach(([projectId, conversations]) => {
        nextLists[projectId] = conversations.filter((currentConversation) => currentConversation.id !== nextConversation.id);
      });

      if (nextConversation.projectId) {
        nextLists[nextConversation.projectId] = sortDiagnosisConversationsByPin(
          sortConversationsByUpdatedAt([
            nextConversation,
            ...(nextLists[nextConversation.projectId] ?? []),
          ]),
        );
      }

      return nextLists;
    });
  };

  const removeProjectConversationLocally = (conversationId: string) => {
    setProjectConversationsById((currentLists) =>
      Object.fromEntries(
        Object.entries(currentLists).map(([projectId, conversations]) => [
          projectId,
          conversations.filter((conversation) => conversation.id !== conversationId),
        ]),
      ),
    );
  };

  const upsertDiagnosisConversation = (conversation: ApiDiagnosisConversationResponse) => {
    const nextConversation = mapApiDiagnosisConversation(conversation);
    setDiagnosisConversations((currentConversations) => [
      nextConversation,
      ...currentConversations.filter((currentConversation) => currentConversation.id !== nextConversation.id),
    ]);
    syncProjectConversationLocally(conversation);
  };

  const updateDiagnosisConversationInPlace = (conversation: ApiDiagnosisConversationResponse) => {
    const nextConversation = mapApiDiagnosisConversation(conversation);
    setDiagnosisConversations((currentConversations) =>
      currentConversations.map((currentConversation) =>
        currentConversation.id === nextConversation.id ? nextConversation : currentConversation,
      ),
    );
    syncProjectConversationLocally(conversation);
  };

  const runAuthenticatedRequest = async <T,>(request: (accessToken: string) => Promise<T>): Promise<T> => {
    if (!authState?.accessToken) {
      setAuthModalOpen(true);
      throw new Error('请先登录');
    }

    try {
      return await request(authState.accessToken);
    } catch (error) {
      if (!isUnauthorizedError(error)) throw error;
      const refreshedAuthState = await handleTokenRefresh();
      return request(refreshedAuthState.accessToken);
    }
  };

  const handleModelConfigSave = async (draft: ModelConfigDraft, editingModelId: string | null) => {
    setModelConfigSaving(true);
    try {
      const modelConfig = await runAuthenticatedRequest((accessToken) =>
        editingModelId ? updateModelConfig(accessToken, editingModelId, draft) : createModelConfig(accessToken, draft),
      );
      const nextModel = mapApiModelConfig(modelConfig);
      setConfiguredModels((currentModels) => {
        const exists = currentModels.some((model) => model.id === nextModel.id);
        if (exists) {
          return currentModels.map((model) =>
            model.id === nextModel.id ? nextModel : nextModel.isDefault ? { ...model, isDefault: false } : model,
          );
        }
        if (nextModel.isDefault) return [nextModel, ...currentModels.map((model) => ({ ...model, isDefault: false }))];
        return [nextModel, ...currentModels];
      });
      setSelectedModelConfigId((currentId) => (nextModel.isDefault ? nextModel.id : currentId ?? nextModel.id));
      setModelConfigsError('');
      return nextModel;
    } catch (error) {
      const message = error instanceof Error ? error.message : '模型配置保存失败';
      setModelConfigsError(message);
      throw error;
    } finally {
      setModelConfigSaving(false);
    }
  };

  const handleModelConfigDelete = async (modelConfigId: string) => {
    await runAuthenticatedRequest((accessToken) => deleteModelConfig(accessToken, modelConfigId));
    setConfiguredModels((currentModels) => {
      const nextModels = currentModels.filter((model) => model.id !== modelConfigId);
      if (selectedModelConfigId === modelConfigId) {
        setSelectedModelConfigId(nextModels.find((model) => model.isDefault)?.id ?? nextModels[0]?.id ?? null);
      }
      return nextModels;
    });
  };

  const handleModelConfigSetDefault = async (modelConfigId: string) => {
    const modelConfig = await runAuthenticatedRequest((accessToken) => setDefaultModelConfig(accessToken, modelConfigId));
    const nextModel = mapApiModelConfig(modelConfig);
    setConfiguredModels((currentModels) =>
      currentModels.map((model) =>
        model.id === nextModel.id ? nextModel : { ...model, isDefault: false },
      ),
    );
    setSelectedModelConfigId(nextModel.id);
  };

  const handleModelConfigTest = async (modelConfigId: string) => {
    setTestingModelConfigId(modelConfigId);
    try {
      const result = await runAuthenticatedRequest((accessToken) => testModelConfig(accessToken, modelConfigId));
      setConfiguredModels((currentModels) =>
        currentModels.map((model) =>
          model.id === modelConfigId
            ? {
                ...model,
                lastTestStatus: result.status,
                lastTestMessage: result.message,
                lastTestAt: result.tested_at,
              }
            : model,
        ),
      );
      return result;
    } finally {
      setTestingModelConfigId(null);
    }
  };

  const handleDiagnosisConversationSelect = async (
    conversationId: string,
    source: ActiveConversationSource = 'history',
  ) => {
    if (!authState?.accessToken) {
      setAuthModalOpen(true);
      return;
    }

    const loadWithToken = (accessToken: string) => fetchDiagnosisConversation(accessToken, conversationId);

    setDiagnosisSending(false);
    setChatSearchOpen(false);
    setDiagnosisExpertReviews([]);
    setActiveThread('history');
    setActiveDiagnosisConversationId(conversationId);
    setActiveConversationSource(source);
    setDiagnosisSessionId((currentSessionId) => currentSessionId + 1);

    try {
      const conversation = await loadWithToken(authState.accessToken);
      setDiagnosisMessages(conversation.messages.map(mapApiDiagnosisMessage));
      setDiagnosisExpertReviews(conversation.expert_reviews ?? []);
      updateDiagnosisConversationInPlace(conversation);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        try {
          const refreshedAuthState = await handleTokenRefresh();
          const conversation = await loadWithToken(refreshedAuthState.accessToken);
          setDiagnosisMessages(conversation.messages.map(mapApiDiagnosisMessage));
          setDiagnosisExpertReviews(conversation.expert_reviews ?? []);
          updateDiagnosisConversationInPlace(conversation);
        } catch {
          handleAuthExpired();
        }
        return;
      }
      setDiagnosisMessages([
        {
          id: createDiagnosisMessageId(),
          role: 'assistant',
          content: error instanceof Error ? `加载对话失败：${error.message}` : '加载对话失败，请稍后重试。',
          createdAt: getCurrentTimeLabel(),
          status: 'error',
        },
      ]);
    }
  };

  const handleDiagnosisSubmit = async (
    question: string,
    projectId: string | null = null,
    options: DiagnosisSubmitOptions = {},
  ) => {
    const trimmedQuestion = question.trim();
    const attachmentIds = options.attachmentIds ?? [];
    const uploadedAttachments = options.uploadedAttachments ?? [];
    const structuredData = options.structuredData ?? null;
    const hasStructuredData = Boolean(structuredData && Object.keys(structuredData).length > 0);
    if ((!trimmedQuestion && attachmentIds.length === 0 && !hasStructuredData) || diagnosisSending) return;

    if (!authState?.accessToken) {
      setAuthModalOpen(true);
      return;
    }

    const targetProjectId = projectId && createdProjects.some((project) => project.id === projectId) ? projectId : null;
    const targetConversationId = targetProjectId ? null : activeDiagnosisConversationId;
    const optimisticUserMessageId = createDiagnosisMessageId();
    const userMessage: DiagnosisMessage = {
      id: optimisticUserMessageId,
      role: 'user',
      content: trimmedQuestion || '已上传问诊材料',
      createdAt: getCurrentTimeLabel(),
      attachments: uploadedAttachments.map(mapApiDiagnosisAttachment),
    };

    if (targetProjectId) {
      setChatSearchOpen(false);
      setActiveThread('diagnosis');
      setActiveProjectChatId(targetProjectId);
      setActiveDiagnosisConversationId(null);
      setActiveConversationSource(null);
      setDiagnosisSessionId((currentSessionId) => currentSessionId + 1);
      setDiagnosisMessages([userMessage]);
    } else {
      setDiagnosisMessages((currentMessages) => [...currentMessages, userMessage]);
    }
    setDiagnosisSending(true);

    const modelConfigId = selectedModel?.id ?? null;
    const newConversationProjectId =
      targetProjectId ??
      (!targetConversationId && activeProjectChatId && createdProjects.some((project) => project.id === activeProjectChatId)
        ? activeProjectChatId
        : null);
    const nextConversationSource: ActiveConversationSource = targetConversationId
      ? activeConversationSource ?? 'history'
      : newConversationProjectId
        ? 'project'
        : 'history';
    const submitWithToken = (accessToken: string) =>
      attachmentIds.length > 0 || hasStructuredData
        ? targetConversationId
          ? createDiagnosisMultimodalConversationMessage(accessToken, targetConversationId, {
              message: trimmedQuestion,
              modelConfigId,
              attachmentIds,
              structuredData,
            })
          : createDiagnosisMultimodalConversation(accessToken, {
              message: trimmedQuestion,
              modelConfigId,
              attachmentIds,
              structuredData,
              projectId: newConversationProjectId,
            })
        : targetConversationId
          ? createDiagnosisConversationMessage(accessToken, targetConversationId, trimmedQuestion, modelConfigId)
          : createDiagnosisConversation(accessToken, trimmedQuestion, modelConfigId, newConversationProjectId);

    try {
      const response = await submitWithToken(authState.accessToken);
      setActiveDiagnosisConversationId(response.conversation.id);
      setActiveConversationSource(nextConversationSource);
      upsertDiagnosisConversation(response.conversation);
      setDiagnosisMessages((currentMessages) => [
        ...currentMessages.filter((message) => message.id !== optimisticUserMessageId),
        mapApiDiagnosisMessage(response.user_message),
        mapApiDiagnosisMessage(response.assistant_message),
      ]);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        try {
          const refreshedAuthState = await handleTokenRefresh();
          const response = await submitWithToken(refreshedAuthState.accessToken);
          setActiveDiagnosisConversationId(response.conversation.id);
          setActiveConversationSource(nextConversationSource);
          upsertDiagnosisConversation(response.conversation);
          setDiagnosisMessages((currentMessages) => [
            ...currentMessages.filter((message) => message.id !== optimisticUserMessageId),
            mapApiDiagnosisMessage(response.user_message),
            mapApiDiagnosisMessage(response.assistant_message),
          ]);
          return;
        } catch {
          handleAuthExpired();
        }
      }
      setDiagnosisMessages((currentMessages) => [
        ...currentMessages,
        {
          id: createDiagnosisMessageId(),
          role: 'assistant',
          content: error instanceof Error ? `模型调用失败：${error.message}` : '模型调用失败，请稍后重试。',
          createdAt: getCurrentTimeLabel(),
          status: 'error',
        },
      ]);
    } finally {
      setDiagnosisSending(false);
    }
  };

  const handleDiagnosisAudioTranscribe = async (audio: File) => {
    const response = await runAuthenticatedRequest((accessToken) => transcribeDiagnosisAudio(accessToken, audio));
    return response.text;
  };

  const updateDiagnosisMessageInPlace = (message: ApiDiagnosisMessageResponse) => {
    const nextMessage = mapApiDiagnosisMessage(message);
    setDiagnosisMessages((currentMessages) =>
      currentMessages.map((currentMessage) => (currentMessage.id === nextMessage.id ? nextMessage : currentMessage)),
    );
  };

  const handleDiagnosisMessageEdit = async (messageId: string, content: string) => {
    if (!activeDiagnosisConversationId) return;
    const messageIndex = diagnosisMessages.findIndex((message) => message.id === messageId);
    const assistantMessageToRegenerate =
      messageIndex >= 0
        ? diagnosisMessages.slice(messageIndex + 1).find((message) => message.role === 'assistant')
        : undefined;
    const modelConfigId = selectedModel?.id ?? null;

    const response = await runAuthenticatedRequest((accessToken) =>
      updateDiagnosisMessage(accessToken, activeDiagnosisConversationId, messageId, content),
    );
    updateDiagnosisConversationInPlace(response.conversation);
    updateDiagnosisMessageInPlace(response.message);

    if (!assistantMessageToRegenerate) return;

    setDiagnosisMessages((currentMessages) =>
      currentMessages.map((message) =>
        message.id === assistantMessageToRegenerate.id
          ? {
              ...message,
              content: '',
              status: 'regenerating',
              feedback: null,
              feedbackReasons: [],
              feedbackDetail: null,
            }
          : message,
      ),
    );

    void (async () => {
      try {
        const regenerateResponse = await runAuthenticatedRequest((accessToken) =>
          regenerateDiagnosisMessage(
            accessToken,
            activeDiagnosisConversationId,
            assistantMessageToRegenerate.id,
            modelConfigId,
          ),
        );
        updateDiagnosisConversationInPlace(regenerateResponse.conversation);
        updateDiagnosisMessageInPlace(regenerateResponse.message);
      } catch (error) {
        setDiagnosisMessages((currentMessages) =>
          currentMessages.map((message) =>
            message.id === assistantMessageToRegenerate.id
              ? {
                  ...message,
                  content: error instanceof Error ? `重新生成失败：${error.message}` : '重新生成失败，请稍后再试。',
                  status: 'error',
                }
              : message,
          ),
        );
      }
    })();
  };

  const handleDiagnosisMessageDelete = async (messageId: string) => {
    if (!activeDiagnosisConversationId) return;
    const detail = await runAuthenticatedRequest((accessToken) =>
      deleteDiagnosisMessage(accessToken, activeDiagnosisConversationId, messageId),
    );
    updateDiagnosisConversationInPlace(detail);
    setDiagnosisMessages(detail.messages.map(mapApiDiagnosisMessage));
  };

  const handleDiagnosisMessageFeedback = async (
    messageId: string,
    feedback: 'like' | 'dislike' | null,
    feedbackReasons: string[] = [],
    feedbackDetail: string | null = null,
  ) => {
    if (!activeDiagnosisConversationId) return;
    const response = await runAuthenticatedRequest((accessToken) =>
      setDiagnosisMessageFeedback(
        accessToken,
        activeDiagnosisConversationId,
        messageId,
        feedback,
        feedbackReasons,
        feedbackDetail,
      ),
    );
    updateDiagnosisConversationInPlace(response.conversation);
    updateDiagnosisMessageInPlace(response.message);
  };

  const handleDiagnosisMessageRegenerate = async (messageId: string) => {
    if (!activeDiagnosisConversationId || diagnosisSending) return;

    setDiagnosisMessages((currentMessages) =>
      currentMessages.map((message) =>
        message.id === messageId && message.role === 'assistant'
          ? {
              ...message,
              content: '',
              status: 'regenerating',
              feedback: null,
              feedbackReasons: [],
              feedbackDetail: null,
            }
          : message,
      ),
    );

    try {
      const response = await runAuthenticatedRequest((accessToken) =>
        regenerateDiagnosisMessage(accessToken, activeDiagnosisConversationId, messageId, selectedModel?.id ?? null),
      );
      updateDiagnosisConversationInPlace(response.conversation);
      updateDiagnosisMessageInPlace(response.message);
    } catch (error) {
      setDiagnosisMessages((currentMessages) =>
        currentMessages.map((message) =>
          message.id === messageId
            ? {
                ...message,
                content: error instanceof Error ? `重试失败：${error.message}` : '重试失败，请稍后再试。',
                status: 'error',
              }
            : message,
        ),
      );
      throw error;
    }
  };

  const handleThreadSelect = (thread: ThreadKey) => {
    if (thread === 'history') {
      setChatSearchOpen(true);
      return;
    }

    setChatSearchOpen(false);

    if (thread === 'diagnosis') {
      setDiagnosisMessages([]);
      setDiagnosisSessionId((currentSessionId) => currentSessionId + 1);
      setActiveDiagnosisConversationId(null);
      setActiveConversationSource(null);
      setDiagnosisSending(false);
    }
    setActiveThread(thread);
    setActiveProjectChatId(getProjectChatId(thread, sidebarProjectFolders));
  };

  const handleProjectFolderSelect = (projectId: string) => {
    setActiveThread('projects');
    setActiveProjectChatId(projectId);
  };

  const handleProjectPinToggle = async (projectId: string) => {
    const currentProject = createdProjects.find((project) => project.id === projectId);
    if (!currentProject) return;

    const nextPinned = !currentProject.pinnedAt;
    try {
      const project = await runAuthenticatedRequest((accessToken) => setProjectPinned(accessToken, projectId, nextPinned));
      const nextProject = mapApiProject(project);
      setCreatedProjects((currentProjects) =>
        currentProjects.map((existingProject) => (existingProject.id === nextProject.id ? nextProject : existingProject)),
      );
      showToast(nextPinned ? '已置顶项目' : '已取消置顶');
    } catch (error) {
      showToast(error instanceof Error ? error.message : '项目置顶失败', 'error');
    }
  };

  const handleProjectArchive = async (projectId: string) => {
    const currentProject = createdProjects.find((project) => project.id === projectId);
    if (!currentProject || archiveSavingProjectId === projectId) return;

    setArchiveSavingProjectId(projectId);
    try {
      const project = await runAuthenticatedRequest((accessToken) => archiveProject(accessToken, projectId));
      const nextProject = mapApiProject(project);
      const archivedAt = new Date().toISOString();
      const conversationsToArchive = Array.from(
        new Map(
          [
            ...diagnosisConversations.filter((conversation) => conversation.projectId === projectId),
            ...(projectConversationsById[projectId] ?? []),
          ].map((conversation) => [conversation.id, conversation]),
        ).values(),
      ).map((conversation) => ({
        ...conversation,
        status: 'archived',
        pinnedAt: null,
        updatedAt: archivedAt,
        time: formatProjectUpdatedAt(archivedAt),
      }));

      setCreatedProjects((currentProjects) => currentProjects.filter((existingProject) => existingProject.id !== projectId));
      setArchivedProjects((currentProjects) => [
        nextProject,
        ...currentProjects.filter((existingProject) => existingProject.id !== projectId),
      ]);
      setDiagnosisConversations((currentConversations) =>
        currentConversations.filter((conversation) => conversation.projectId !== projectId),
      );
      if (conversationsToArchive.length > 0) {
        setArchivedDiagnosisConversations((currentConversations) =>
          sortConversationsByUpdatedAt([
            ...conversationsToArchive,
            ...currentConversations.filter(
              (conversation) => !conversationsToArchive.some((archivedConversation) => archivedConversation.id === conversation.id),
            ),
          ]),
        );
      }
      setProjectConversationsById((currentLists) => {
        const nextLists = { ...currentLists };
        delete nextLists[projectId];
        return nextLists;
      });
      if (activeDiagnosisConversationId && conversationsToArchive.some((conversation) => conversation.id === activeDiagnosisConversationId)) {
        setActiveDiagnosisConversationId(null);
        setActiveConversationSource(null);
        setDiagnosisMessages([]);
        setDiagnosisSending(false);
      }
      if (activeProjectChatId === projectId) {
        setActiveProjectChatId(null);
      }
      setProjectsError('');
      setArchivedProjectsError('');
      showToast('已归档项目');
    } catch (error) {
      showToast(error instanceof Error ? error.message : '项目归档失败', 'error');
    } finally {
      setArchiveSavingProjectId(null);
    }
  };

  const handleProjectRestore = async (projectId: string) => {
    if (archiveSavingProjectId === projectId) return;

    setArchiveSavingProjectId(projectId);
    try {
      const project = await runAuthenticatedRequest((accessToken) => restoreProject(accessToken, projectId));
      const nextProject = mapApiProject(project);
      const restoredAt = new Date().toISOString();
      const conversationsToRestore = archivedDiagnosisConversations
        .filter((conversation) => conversation.projectId === projectId)
        .map((conversation) => ({
          ...conversation,
          status: 'active',
          updatedAt: restoredAt,
          time: formatProjectUpdatedAt(restoredAt),
        }));

      setArchivedProjects((currentProjects) => currentProjects.filter((existingProject) => existingProject.id !== projectId));
      setCreatedProjects((currentProjects) => [
        nextProject,
        ...currentProjects.filter((existingProject) => existingProject.id !== projectId),
      ]);
      if (conversationsToRestore.length > 0) {
        setArchivedDiagnosisConversations((currentConversations) =>
          currentConversations.filter(
            (conversation) => !conversationsToRestore.some((restoredConversation) => restoredConversation.id === conversation.id),
          ),
        );
        setDiagnosisConversations((currentConversations) =>
          sortDiagnosisConversationsByPin(
            sortConversationsByUpdatedAt([
              ...conversationsToRestore,
              ...currentConversations.filter(
                (conversation) => !conversationsToRestore.some((restoredConversation) => restoredConversation.id === conversation.id),
              ),
            ]),
          ),
        );
      }
      setProjectsError('');
      setArchivedProjectsError('');
      showToast('已恢复项目');
    } catch (error) {
      showToast(error instanceof Error ? error.message : '项目恢复失败', 'error');
    } finally {
      setArchiveSavingProjectId(null);
    }
  };

  const handleDiagnosisConversationPinToggle = async (conversationId: string) => {
    const currentConversation = diagnosisConversations.find((conversation) => conversation.id === conversationId);
    if (!currentConversation) return;

    const nextPinned = !currentConversation.pinnedAt;
    try {
      const conversation = await runAuthenticatedRequest((accessToken) =>
        setDiagnosisConversationPinned(accessToken, conversationId, nextPinned),
      );
      updateDiagnosisConversationInPlace(conversation);
      showToast(nextPinned ? '已置顶聊天' : '已取消置顶');
    } catch (error) {
      showToast(error instanceof Error ? error.message : '聊天置顶失败', 'error');
    }
  };

  const addArchivedDiagnosisConversation = (conversation: ApiDiagnosisConversationResponse) => {
    const nextConversation = mapApiDiagnosisConversation(conversation);
    setArchivedDiagnosisConversations((currentConversations) =>
      sortConversationsByUpdatedAt([
        nextConversation,
        ...currentConversations.filter((currentConversation) => currentConversation.id !== nextConversation.id),
      ]),
    );
  };

  const handleDiagnosisConversationArchive = async (conversationId: string) => {
    const currentConversation = diagnosisConversations.find((conversation) => conversation.id === conversationId);
    if (!currentConversation || archiveSavingConversationId === conversationId) return;

    setArchiveSavingConversationId(conversationId);
    try {
      const conversation = await runAuthenticatedRequest((accessToken) => archiveDiagnosisConversation(accessToken, conversationId));
      removeDiagnosisConversationLocally(conversationId);
      addArchivedDiagnosisConversation(conversation);
      showToast('已归档对话');
    } catch (error) {
      showToast(error instanceof Error ? error.message : '对话归档失败', 'error');
    } finally {
      setArchiveSavingConversationId(null);
    }
  };

  const handleDiagnosisConversationRestore = async (conversationId: string) => {
    if (archiveSavingConversationId === conversationId) return;

    setArchiveSavingConversationId(conversationId);
    try {
      const conversation = await runAuthenticatedRequest((accessToken) => restoreDiagnosisConversation(accessToken, conversationId));
      setArchivedDiagnosisConversations((currentConversations) =>
        currentConversations.filter((currentConversation) => currentConversation.id !== conversationId),
      );
      upsertDiagnosisConversation(conversation);
      showToast('已恢复对话');
    } catch (error) {
      showToast(error instanceof Error ? error.message : '对话恢复失败', 'error');
    } finally {
      setArchiveSavingConversationId(null);
    }
  };

  const handleDiagnosisConversationRename = async (conversationId: string, title: string) => {
    const nextTitle = title.trim();
    if (!nextTitle) return;

    if (!authState?.accessToken) {
      setAuthModalOpen(true);
      return;
    }

    const renameWithToken = (accessToken: string) => updateDiagnosisConversation(accessToken, conversationId, nextTitle);

    try {
      const conversation = await renameWithToken(authState.accessToken);
      updateDiagnosisConversationInPlace(conversation);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        try {
          const refreshedAuthState = await handleTokenRefresh();
          const conversation = await renameWithToken(refreshedAuthState.accessToken);
          updateDiagnosisConversationInPlace(conversation);
          return;
        } catch {
          handleAuthExpired();
          return;
        }
      }
      throw error;
    }
  };

  const removeDiagnosisConversationLocally = (conversationId: string) => {
    setDiagnosisConversations((currentConversations) =>
      currentConversations.filter((conversation) => conversation.id !== conversationId),
    );
    setArchivedDiagnosisConversations((currentConversations) =>
      currentConversations.filter((conversation) => conversation.id !== conversationId),
    );
    removeProjectConversationLocally(conversationId);
    if (activeDiagnosisConversationId === conversationId) {
      setActiveDiagnosisConversationId(null);
      setActiveConversationSource(null);
      setDiagnosisMessages([]);
      setDiagnosisSending(false);
      setActiveThread('diagnosis');
      setDiagnosisSessionId((currentSessionId) => currentSessionId + 1);
    }
  };

  const handleDiagnosisConversationDelete = async (conversationId: string) => {
    if (!authState?.accessToken) {
      setAuthModalOpen(true);
      return;
    }

    const deleteWithToken = (accessToken: string) => deleteDiagnosisConversation(accessToken, conversationId);

    try {
      await deleteWithToken(authState.accessToken);
      removeDiagnosisConversationLocally(conversationId);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        try {
          const refreshedAuthState = await handleTokenRefresh();
          await deleteWithToken(refreshedAuthState.accessToken);
          removeDiagnosisConversationLocally(conversationId);
          return;
        } catch {
          handleAuthExpired();
          return;
        }
      }
      throw error;
    }
  };

  const openDiagnosisConversationDeleteConfirm = (conversation: DiagnosisConversation) => {
    setDeleteErrorConversationId(null);
    setDeleteConfirmConversation(conversation);
  };

  const openDiagnosisConversationShareDialog = async (conversation: DiagnosisConversation) => {
    setChatSearchOpen(false);

    try {
      const detail = await runAuthenticatedRequest((accessToken) => fetchDiagnosisConversation(accessToken, conversation.id));
      const nextConversation = mapApiDiagnosisConversation(detail);
      const nextMessages = detail.messages.map(mapApiDiagnosisMessage);
      updateDiagnosisConversationInPlace(detail);

      if (activeDiagnosisConversationId === conversation.id) {
        setDiagnosisMessages(nextMessages);
      }

      setConversationShareContext({
        conversation: nextConversation,
        messages: nextMessages,
        title: nextConversation.title,
      });
    } catch (error) {
      if (error instanceof Error && error.message === '请先登录') return;
      showToast('分享内容加载失败，请稍后再试', 'error');
    }
  };

  const handleDiagnosisConversationPublicShare = (
    conversationId: string,
    payload: DiagnosisConversationPublicSharePayload,
  ) =>
    runAuthenticatedRequest((accessToken) =>
      createDiagnosisConversationShare(accessToken, conversationId, payload),
    );

  const handleDiagnosisConversationCommunityDraft = async (conversationId: string, attachmentIds: string[]) => {
    try {
      const draft = await runAuthenticatedRequest((accessToken) =>
        createCommunityDraftFromConversation(accessToken, conversationId, attachmentIds),
      );
      setCommunityDraftPost(draft);
      setConversationShareContext(null);
      setActiveThread('video');
      showToast('已生成社区草稿，请确认后发布', 'success');
    } catch (error) {
      if (error instanceof Error && error.message === '请先登录') return;
      showToast(error instanceof Error ? `社区草稿生成失败：${error.message}` : '社区草稿生成失败，请稍后再试', 'error');
      throw error;
    }
  };

  const handleDiagnosisAttachmentUpload = async (attachment: File) =>
    runAuthenticatedRequest((accessToken) => uploadDiagnosisAttachment(accessToken, attachment));

  const handleDiagnosisAttachmentDelete = async (fileId: string) =>
    runAuthenticatedRequest((accessToken) => deleteDiagnosisAttachment(accessToken, fileId));

  const handleProjectPublicShare = (projectId: string, payload: ProjectPublicSharePayload) =>
    runAuthenticatedRequest((accessToken) => createProjectShare(accessToken, projectId, payload));

  const openProjectShareDialog = async (project: CreatedProject) => {
    setChatSearchOpen(false);

    try {
      const sharedConversations = await runAuthenticatedRequest(async (accessToken) => {
        const conversations = await fetchProjectConversations(accessToken, project.id);
        const details = await Promise.all(conversations.map((conversation) => fetchDiagnosisConversation(accessToken, conversation.id)));
        return details.map((detail) => ({
          ...mapApiDiagnosisConversation(detail),
          messages: detail.messages.map(mapApiDiagnosisMessage),
        }));
      });

      setProjectShareContext({
        project,
        conversations: sharedConversations,
      });
    } catch (error) {
      if (error instanceof Error && error.message === '请先登录') return;
      showToast(error instanceof Error ? `项目分享内容加载失败：${error.message}` : '项目分享内容加载失败，请稍后再试', 'error');
    }
  };

  const deleteConfirmSaving = deleteConfirmConversation
    ? deleteSavingConversationId === deleteConfirmConversation.id
    : false;
  const deleteConfirmErrored = deleteConfirmConversation
    ? deleteErrorConversationId === deleteConfirmConversation.id
    : false;

  const closeDiagnosisConversationDeleteConfirm = () => {
    if (deleteConfirmSaving) return;
    setDeleteConfirmConversation(null);
    setDeleteErrorConversationId(null);
  };

  const confirmDiagnosisConversationDelete = async () => {
    if (!deleteConfirmConversation || deleteConfirmSaving) return;

    setDeleteSavingConversationId(deleteConfirmConversation.id);
    setDeleteErrorConversationId(null);
    try {
      await handleDiagnosisConversationDelete(deleteConfirmConversation.id);
      setDeleteConfirmConversation(null);
    } catch {
      setDeleteErrorConversationId(deleteConfirmConversation.id);
    } finally {
      setDeleteSavingConversationId(null);
    }
  };

  const handleOpenProjectCreate = () => {
    if (!authState?.accessToken) {
      setAuthModalOpen(true);
      return;
    }

    setPendingProjectMoveConversationId(null);
    setProjectModalOpen(true);
  };

  const handleOpenProjectCreateForMove = (conversationId: string) => {
    if (!authState?.accessToken) {
      setAuthModalOpen(true);
      return;
    }

    setPendingProjectMoveConversationId(conversationId);
    setProjectModalOpen(true);
  };

  const closeProjectCreateModal = () => {
    setProjectModalOpen(false);
    setPendingProjectMoveConversationId(null);
  };

  const handleProjectCreate = async ({ name, color, iconKey }: Pick<CreatedProject, 'name' | 'color' | 'iconKey'>) => {
    if (!authState?.accessToken) {
      setAuthModalOpen(true);
      throw new Error('请先登录后创建项目');
    }

    const createWithToken = (accessToken: string) =>
      createProject(accessToken, {
        name: name.trim(),
        color,
        iconKey,
      });

    let createdProject: ApiProjectResponse;
    let activeAccessToken = authState.accessToken;
    try {
      createdProject = await createWithToken(activeAccessToken);
    } catch (error) {
      if (!isUnauthorizedError(error)) {
        throw error;
      }
      const refreshedAuthState = await handleTokenRefresh();
      activeAccessToken = refreshedAuthState.accessToken;
      createdProject = await createWithToken(activeAccessToken);
    }

    const nextProject = mapApiProject(createdProject);
    const moveConversationId = pendingProjectMoveConversationId;
    setCreatedProjects((currentProjects) => [nextProject, ...currentProjects.filter((project) => project.id !== nextProject.id)]);
    setProjectsError('');
    setActiveProjectChatId(nextProject.id);
    if (!moveConversationId) {
      setActiveThread('projects');
    }

    if (moveConversationId) {
      try {
        const movedConversation = await moveDiagnosisConversationProject(activeAccessToken, moveConversationId, nextProject.id);
        updateDiagnosisConversationInPlace(movedConversation);
        showToast(`已移至 ${nextProject.name}`);
      } catch {
        showToast('项目已创建，但移动对话失败', 'error');
      }
    }

    setPendingProjectMoveConversationId(null);
    setProjectModalOpen(false);
  };

  const handleProjectUpdate = async (projectId: string, project: ProjectSettingsUpdate) => {
    if (!authState?.accessToken) {
      setAuthModalOpen(true);
      throw new Error('请先登录后修改项目');
    }

    const updateWithToken = (accessToken: string) => updateProject(accessToken, projectId, project);

    let updatedProject: ApiProjectResponse;
    try {
      updatedProject = await updateWithToken(authState.accessToken);
    } catch (error) {
      if (!isUnauthorizedError(error)) {
        throw error;
      }
      const refreshedAuthState = await handleTokenRefresh();
      updatedProject = await updateWithToken(refreshedAuthState.accessToken);
    }

    const nextProject = mapApiProject(updatedProject);
    setCreatedProjects((currentProjects) =>
      currentProjects.map((currentProject) => (currentProject.id === nextProject.id ? nextProject : currentProject)),
    );
    setProjectsError('');
    return nextProject;
  };

  const handleProjectDelete = async (projectId: string, _options: { silent?: boolean } = {}) => {
    await runAuthenticatedRequest((accessToken) => deleteProject(accessToken, projectId));
    const releasedConversationIds = new Set((projectConversationsById[projectId] ?? []).map((conversation) => conversation.id));

    setCreatedProjects((currentProjects) => currentProjects.filter((project) => project.id !== projectId));
    setArchivedProjects((currentProjects) => currentProjects.filter((project) => project.id !== projectId));
    setProjectConversationsById((currentLists) => {
      const remainingLists = { ...currentLists };
      delete remainingLists[projectId];
      return remainingLists;
    });
    setDiagnosisConversations((currentConversations) =>
      currentConversations.map((conversation) =>
        releasedConversationIds.has(conversation.id) || conversation.projectId === projectId
          ? { ...conversation, projectId: null }
          : conversation,
      ),
    );
    setArchivedDiagnosisConversations((currentConversations) =>
      currentConversations.map((conversation) =>
        releasedConversationIds.has(conversation.id) || conversation.projectId === projectId
          ? { ...conversation, projectId: null }
          : conversation,
      ),
    );
    if (activeProjectChatId === projectId) {
      setActiveProjectChatId(null);
    }
    setProjectsError('');
    if (!_options.silent) {
      showToast('项目已删除');
    }
  };

  const handleArchiveBulkDelete = async ({ conversationIds, projectIds }: ArchiveBulkDeletePayload) => {
    const uniqueConversationIds = Array.from(new Set(conversationIds));
    const uniqueProjectIds = Array.from(new Set(projectIds));
    if (uniqueConversationIds.length === 0 && uniqueProjectIds.length === 0) return;

    try {
      for (const conversationId of uniqueConversationIds) {
        await handleDiagnosisConversationDelete(conversationId);
      }
      for (const projectId of uniqueProjectIds) {
        await handleProjectDelete(projectId, { silent: true });
      }
      showToast('已删除归档内容');
    } catch (error) {
      showToast(error instanceof Error ? error.message : '归档内容删除失败', 'error');
    }
  };

  const openProjectDeleteConfirm = (project: CreatedProject) => {
    setDeleteConfirmProject(project);
    setDeleteErrorProjectId(null);
  };

  const closeProjectDeleteConfirm = () => {
    if (deleteSavingProjectId) return;
    setDeleteConfirmProject(null);
    setDeleteErrorProjectId(null);
  };

  const confirmProjectDelete = async () => {
    if (!deleteConfirmProject || deleteSavingProjectId) return;

    setDeleteSavingProjectId(deleteConfirmProject.id);
    setDeleteErrorProjectId(null);
    try {
      await handleProjectDelete(deleteConfirmProject.id);
      setDeleteConfirmProject(null);
    } catch {
      setDeleteErrorProjectId(deleteConfirmProject.id);
    } finally {
      setDeleteSavingProjectId(null);
    }
  };

  const handleProjectConversationOpen = (conversationId: string, projectId: string) => {
    setActiveProjectChatId(projectId);
    void handleDiagnosisConversationSelect(conversationId, 'project');
  };

  const handleProjectConversationMove = async (conversationId: string, projectId: string | null) => {
    const conversation = await runAuthenticatedRequest((accessToken) =>
      moveDiagnosisConversationProject(accessToken, conversationId, projectId),
    );
    updateDiagnosisConversationInPlace(conversation);
    return mapApiDiagnosisConversation(conversation);
  };

  const handleDiagnosisConversationMoveToProject = async (conversationId: string, projectId: string | null) => {
    const currentConversation =
      diagnosisConversations.find((conversation) => conversation.id === conversationId) ??
      archivedDiagnosisConversations.find((conversation) => conversation.id === conversationId);
    const previousProjectName = currentConversation?.projectId
      ? projectRows.find((project) => project.id === currentConversation.projectId)?.name
      : null;

    try {
      const movedConversation = await handleProjectConversationMove(conversationId, projectId);
      if (projectId) {
        const targetProject = projectRows.find((project) => project.id === projectId);
        showToast(`已移至 ${targetProject?.name ?? '项目'}`);
      } else {
        showToast(previousProjectName ? `已从 ${previousProjectName} 移除` : '已移出项目');
      }
      return movedConversation;
    } catch {
      showToast(projectId ? '移动到项目失败，请稍后再试' : '从项目移除失败，请稍后再试', 'error');
      throw new Error(projectId ? '移动到项目失败' : '从项目移除失败');
    }
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

  const handleUserSettingsChange = async (patch: Partial<UserPreferences>) => {
    const previousPreferences = userPreferences;
    const optimisticPreferences = { ...previousPreferences, ...patch };
    setUserPreferences(optimisticPreferences);
    setUserSettingsError('');

    if (!authState?.accessToken) return optimisticPreferences;

    const persist = async (accessToken: string) => updateUserSettings(accessToken, patch);
    try {
      const response = await persist(authState.accessToken);
      const nextPreferences = { ...defaultUserPreferences, ...response.preferences };
      setUserPreferences(nextPreferences);
      return nextPreferences;
    } catch (error) {
      if (isUnauthorizedError(error)) {
        try {
          const refreshedAuthState = await handleTokenRefresh();
          const response = await persist(refreshedAuthState.accessToken);
          const nextPreferences = { ...defaultUserPreferences, ...response.preferences };
          setUserPreferences(nextPreferences);
          return nextPreferences;
        } catch (refreshError) {
          setUserPreferences(previousPreferences);
          handleAuthExpired();
          throw refreshError;
        }
      }
      setUserPreferences(previousPreferences);
      const message = error instanceof Error ? error.message : '设置保存失败';
      setUserSettingsError(message);
      throw new Error(message);
    }
  };

  const handleUserDataExport = async () => {
    if (!authState?.accessToken) throw new Error('请先登录');
    const data = await exportUserSettingsData(authState.accessToken);
    downloadJsonFile(`CanW-数据导出-${new Date().toISOString().slice(0, 10)}.json`, data);
    showToast('数据已导出');
  };

  const handleRevokeDeviceSession = async (sessionId: string) => {
    if (!authState?.accessToken) throw new Error('请先登录');
    await revokeUserDeviceSession(authState.accessToken, sessionId);
    setDeviceSessions((currentSessions) => currentSessions.filter((session) => session.id !== sessionId));
    showToast('设备已退出登录');
  };

  const handleRevokeOtherDeviceSessions = async () => {
    if (!authState?.accessToken) throw new Error('请先登录');
    await revokeOtherUserDeviceSessions(authState.accessToken);
    setDeviceSessions((currentSessions) => currentSessions.filter((session) => session.is_current));
    showToast('其他设备已退出登录');
  };

  const handleAccountDelete = async (confirmation: string) => {
    if (!authState?.accessToken) throw new Error('请先登录');
    await deleteUserAccount(authState.accessToken, confirmation);
    clearStoredAuth();
    setAuthState(null);
    setActiveThread('diagnosis');
    setDeviceSessions([]);
    showToast('账户已删除');
  };

  const handleUiThemeChange = (theme: UiTheme) => {
    setUiPreferences((currentPreferences) => ({
      ...currentPreferences,
      theme,
    }));
    void handleUserSettingsChange({ theme }).catch(() => {
      setUiPreferences((currentPreferences) => ({ ...currentPreferences, theme: userPreferences.theme }));
    });
  };

  const handleUiFontSizeChange = (fontSize: UiFontSize) => {
    setUiPreferences((currentPreferences) => ({
      ...currentPreferences,
      fontSize,
    }));
    void handleUserSettingsChange({ font_size: fontSize }).catch(() => {
      setUiPreferences((currentPreferences) => ({ ...currentPreferences, fontSize: userPreferences.font_size }));
    });
  };

  const handleConversationSaveAsCase = (conversationId: string) => {
    setInlineCaseConversationId(conversationId);
  };

  const visibleThread: ThreadKey = activeThread === 'history' ? 'diagnosis' : activeThread;

  const threadTitle = useMemo(() => {
    if (visibleThread === 'video') return '社区：家蚕疾病经验、求助与案例分享';
    if (visibleThread === 'memory') return '图谱探索：家蚕疾病知识图谱';
    if (visibleThread === 'tools') return '养殖管理：记录、病例与随访';
    if (visibleThread === 'settings') return '设置系统：模型、知识源、记忆、隐私与 UI';
    return '新问诊';
  }, [visibleThread]);

  const isProjectsView = visibleThread === 'projects';
  const isDiagnosisStartView = visibleThread === 'diagnosis';
  const activeNavThread: ThreadKey | null = activeThread === 'history' ? null : activeThread;

  const handleSidebarToggle = () => {
    setSidebarCollapsed((collapsed) => !collapsed);
  };

  const handleSidebarResizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;

    event.preventDefault();
    const startWidth = sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : sidebarWidth;
    sidebarResizeStateRef.current = {
      startWidth,
      startX: event.clientX,
    };
    setSidebarResizing(true);

    const getNextRawWidth = (clientX: number) => {
      const resizeState = sidebarResizeStateRef.current;
      if (!resizeState) return startWidth;
      return resizeState.startWidth + clientX - resizeState.startX;
    };

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const nextRawWidth = getNextRawWidth(moveEvent.clientX);
      if (nextRawWidth <= SIDEBAR_COLLAPSE_THRESHOLD) {
        setSidebarCollapsed(true);
        return;
      }

      setSidebarCollapsed(false);
      setSidebarWidth(clampSidebarWidth(nextRawWidth));
    };

    let handlePointerEnd: (endEvent: PointerEvent) => void;
    const cleanup = () => {
      sidebarResizeStateRef.current = null;
      setSidebarResizing(false);
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerEnd);
      window.removeEventListener('pointercancel', handlePointerEnd);
    };

    handlePointerEnd = (endEvent: PointerEvent) => {
      const finalRawWidth = getNextRawWidth(endEvent.clientX);
      if (finalRawWidth <= SIDEBAR_COLLAPSE_THRESHOLD) {
        setSidebarCollapsed(true);
      } else {
        const nextWidth = clampSidebarWidth(finalRawWidth);
        setSidebarCollapsed(false);
        setSidebarWidth(nextWidth);
        saveStoredSidebarWidth(nextWidth);
      }
      cleanup();
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerEnd);
    window.addEventListener('pointercancel', handlePointerEnd);
  };

  void [
    userSettingsLoading,
    userSettingsError,
    deviceSessions,
    deviceSessionsLoading,
    handleUserDataExport,
    handleRevokeDeviceSession,
    handleRevokeOtherDeviceSessions,
    handleAccountDelete,
  ];

  return (
    <main
      className={clsx(
        'app-frame',
        sidebarCollapsed && 'sidebar-collapsed',
        sidebarResizing && 'sidebar-resizing',
        uiPreferences.theme === 'dark' && 'theme-dark',
        userPreferences.reduced_motion && 'reduced-motion',
        userPreferences.high_contrast && 'high-contrast',
        `font-size-${uiPreferences.fontSize}`,
      )}
      style={{ '--sidebar-width': `${sidebarWidth}px` } as CSSProperties}
    >
      <Sidebar
        activeThread={visibleThread}
        activeNavThread={activeNavThread}
        activeConversationSource={activeConversationSource}
        activeDiagnosisConversationId={activeDiagnosisConversationId}
        activeProjectChatId={activeProjectChatId}
        collapsed={sidebarCollapsed}
        diagnosisConversations={sortedDiagnosisConversations}
        diagnosisHistoryLoading={diagnosisHistoryLoading}
        pinnedDiagnosisConversationIds={pinnedDiagnosisConversationIds}
        isAuthenticated={isAuthenticated}
        authUser={authState?.user ?? null}
        projectFolders={sidebarProjectFolders}
        projects={projectRows}
        onDiagnosisConversationSelect={handleDiagnosisConversationSelect}
        onDiagnosisConversationPinToggle={handleDiagnosisConversationPinToggle}
        onDiagnosisConversationArchive={handleDiagnosisConversationArchive}
        onDiagnosisConversationRename={handleDiagnosisConversationRename}
        onDiagnosisConversationDelete={openDiagnosisConversationDeleteConfirm}
        onDiagnosisConversationShare={openDiagnosisConversationShareDialog}
        onDiagnosisConversationMoveToProject={handleDiagnosisConversationMoveToProject}
        onSelect={handleThreadSelect}
        onProjectConversationOpen={handleProjectConversationOpen}
        onProjectFolderSelect={handleProjectFolderSelect}
        onProjectArchive={handleProjectArchive}
        onProjectDelete={handleProjectDelete}
        onProjectPinToggle={handleProjectPinToggle}
        onProjectShare={openProjectShareDialog}
        onProjectUpdate={handleProjectUpdate}
        resizing={sidebarResizing}
        onToggleSidebar={handleSidebarToggle}
        onSidebarResizeStart={handleSidebarResizeStart}
        onOpenAuth={() => setAuthModalOpen(true)}
        onOpenProfile={() => setProfileModalOpen(true)}
        onOpenProjectCreate={handleOpenProjectCreate}
        onOpenProjectCreateForMove={handleOpenProjectCreateForMove}
        onSignOut={() => {
          void handleSignOut();
        }}
      />
      <section
        className={clsx(
          'thread-area',
          isProjectsView && 'projects-thread-area',
          isDiagnosisStartView && 'diagnosis-start-thread-area',
          visibleThread === 'video' && 'community-thread-area',
          (visibleThread === 'settings' || visibleThread === 'memory' || visibleThread === 'tools') && 'headerless-thread-area',
        )}
      >
        {isProjectsView ? (
          <ProjectsPage
            activeProjectId={activeProjectChatId}
            configuredModels={configuredModels}
            conversations={sortedDiagnosisConversations}
            error={projectsError}
            isConversationSending={diagnosisSending}
            isLoading={projectsLoading}
            pinnedProjectIds={pinnedProjectIds}
            projectConversations={activeProjectChatId ? projectConversationsById[activeProjectChatId] ?? [] : []}
            projectConversationsError={projectConversationsError}
            projectConversationsLoading={Boolean(activeProjectChatId && projectConversationsLoadingId === activeProjectChatId)}
            projects={projectRows}
            selectedModelConfigId={selectedModel?.id ?? null}
            userPreferences={userPreferences}
            onProjectConversationMove={handleProjectConversationMove}
            onProjectConversationOpen={handleProjectConversationOpen}
            onProjectConversationSubmit={(projectId, question, options) => handleDiagnosisSubmit(question, projectId, options)}
            onProjectArchive={handleProjectArchive}
            onProjectDelete={handleProjectDelete}
            onAudioTranscribe={handleDiagnosisAudioTranscribe}
            onAttachmentUpload={handleDiagnosisAttachmentUpload}
            onAttachmentDelete={handleDiagnosisAttachmentDelete}
            onOpenCreate={handleOpenProjectCreate}
            onModelSelect={setSelectedModelConfigId}
            onProjectPinToggle={handleProjectPinToggle}
            onProjectOpen={handleProjectFolderSelect}
            onProjectShare={openProjectShareDialog}
            onProjectUpdate={handleProjectUpdate}
          />
        ) : isDiagnosisStartView ? (
          <DiagnosisThread
            activeConversation={activeDiagnosisConversation}
            configuredModels={configuredModels}
            key={activeDiagnosisConversationId ?? `new-${diagnosisSessionId}`}
            isSending={diagnosisSending}
            messages={diagnosisMessages}
            expertReviews={diagnosisExpertReviews}
            projects={projectRows}
            selectedModelConfigId={selectedModel?.id ?? null}
            userPreferences={userPreferences}
            onConversationArchive={handleDiagnosisConversationArchive}
            onConversationDelete={openDiagnosisConversationDeleteConfirm}
            onConversationMoveToProject={handleDiagnosisConversationMoveToProject}
            onConversationPublicShare={handleDiagnosisConversationPublicShare}
            onConversationCommunityDraft={handleDiagnosisConversationCommunityDraft}
            onConversationRename={handleDiagnosisConversationRename}
            onConversationSaveAsCase={handleConversationSaveAsCase}
            onMessageDelete={handleDiagnosisMessageDelete}
            onMessageEdit={handleDiagnosisMessageEdit}
            onMessageFeedback={handleDiagnosisMessageFeedback}
            onMessageRegenerate={handleDiagnosisMessageRegenerate}
            onModelSelect={setSelectedModelConfigId}
            onNotify={showToast}
            onOpenProjectCreateForMove={handleOpenProjectCreateForMove}
            onAudioTranscribe={handleDiagnosisAudioTranscribe}
            onAttachmentUpload={handleDiagnosisAttachmentUpload}
            onAttachmentDelete={handleDiagnosisAttachmentDelete}
            onSubmit={handleDiagnosisSubmit}
          />
        ) : visibleThread === 'video' ? (
          <CommunityPage
            accessToken={authState?.accessToken ?? ''}
            currentUser={authState?.user ?? null}
            draftPost={communityDraftPost}
            onAuthExpired={handleAuthExpired}
            onDraftConsumed={() => setCommunityDraftPost(null)}
            onNotify={showToast}
            onRequireAuth={() => setAuthModalOpen(true)}
            onTokenRefresh={handleTokenRefresh}
          />
        ) : (
          <>
            {visibleThread !== 'settings' && visibleThread !== 'memory' && visibleThread !== 'tools' && <ThreadHeader title={threadTitle} />}
            <div className="thread-scroll">
              {visibleThread === 'memory' && <MemoryThread />}
              {visibleThread === 'tools' && (
                <HusbandryThread
                  accessToken={authState?.accessToken ?? ''}
                  conversations={sortedDiagnosisConversations}
                  sourceConversationId={toolCaseSourceConversationId}
                  onAuthExpired={handleAuthExpired}
                  onCommunityDraft={(draft) => {
                    setCommunityDraftPost(draft);
                    setActiveThread('video');
                  }}
                  onNotify={showToast}
                  onRequireAuth={() => setAuthModalOpen(true)}
                  onSourceConversationConsumed={() => setToolCaseSourceConversationId(null)}
                  userPreferences={userPreferences}
                />
              )}
              {visibleThread === 'settings' && (
                <SettingsThread
                  archivedConversations={archivedDiagnosisConversations}
                  archiveError={archivedDiagnosisError}
                  archivedProjects={archivedProjects}
                  archivedProjectsError={archivedProjectsError}
                  archivedProjectsLoading={archivedProjectsLoading}
                  archiveSavingConversationId={archiveSavingConversationId}
                  archiveSavingProjectId={archiveSavingProjectId}
                  archivesLoading={archivedDiagnosisLoading}
                  configuredModels={configuredModels}
                  deviceSessions={deviceSessions}
                  deviceSessionsLoading={deviceSessionsLoading}
                  fontSize={uiPreferences.fontSize}
                  isModelConfigSaving={modelConfigSaving}
                  modelConfigError={modelConfigsError}
                  modelConfigsLoading={modelConfigsLoading}
                  selectedModelConfigId={selectedModel?.id ?? null}
                  testingModelConfigId={testingModelConfigId}
                  theme={uiPreferences.theme}
                  userPreferences={userPreferences}
                  userSettingsError={userSettingsError}
                  userSettingsLoading={userSettingsLoading}
                  projects={projectRows}
                  onFontSizeChange={handleUiFontSizeChange}
                  onArchiveBulkDelete={handleArchiveBulkDelete}
                  onConversationDelete={openDiagnosisConversationDeleteConfirm}
                  onConversationRestore={handleDiagnosisConversationRestore}
                  onProjectDelete={openProjectDeleteConfirm}
                  onProjectRestore={handleProjectRestore}
                  onModelDelete={handleModelConfigDelete}
                  onModelSave={handleModelConfigSave}
                  onModelSelect={setSelectedModelConfigId}
                  onModelSetDefault={handleModelConfigSetDefault}
                  onModelTest={handleModelConfigTest}
                  onAccountDelete={handleAccountDelete}
                  onDeviceSessionRevoke={handleRevokeDeviceSession}
                  onOtherDeviceSessionsRevoke={handleRevokeOtherDeviceSessions}
                  onThemeChange={handleUiThemeChange}
                  onUserDataExport={handleUserDataExport}
                  onUserSettingsChange={handleUserSettingsChange}
                />
              )}
            </div>
            {visibleThread !== 'memory' && visibleThread !== 'tools' && <Composer />}
          </>
        )}
      </section>
      <ChatSearchDialog
        accessToken={authState?.accessToken ?? ''}
        conversations={sortedDiagnosisConversations}
        isLoading={diagnosisHistoryLoading}
        open={chatSearchOpen}
        onClose={() => setChatSearchOpen(false)}
        onNewChat={() => {
          setChatSearchOpen(false);
          handleThreadSelect('diagnosis');
        }}
        onOpenConversation={(conversationId) => {
          setChatSearchOpen(false);
          void handleDiagnosisConversationSelect(conversationId);
        }}
      />
      {deleteConfirmConversation && (
        <DeleteConversationDialog
          conversation={deleteConfirmConversation}
          saving={deleteConfirmSaving}
          error={deleteConfirmErrored}
          onCancel={closeDiagnosisConversationDeleteConfirm}
          onConfirm={confirmDiagnosisConversationDelete}
        />
      )}
      {deleteConfirmProject && (
        <DeleteProjectDialog
          project={deleteConfirmProject}
          saving={deleteSavingProjectId === deleteConfirmProject.id}
          error={deleteErrorProjectId === deleteConfirmProject.id ? '项目删除失败' : ''}
          onCancel={closeProjectDeleteConfirm}
          onConfirm={() => {
            void confirmProjectDelete();
          }}
        />
      )}
      {conversationShareContext && (
        <DiagnosisConversationShareDialog
          conversation={conversationShareContext.conversation}
          messages={conversationShareContext.messages}
          title={conversationShareContext.title}
          onCancel={() => setConversationShareContext(null)}
          onCreateCommunityDraft={handleDiagnosisConversationCommunityDraft}
          onCreatePublicShare={handleDiagnosisConversationPublicShare}
          onNotify={showToast}
        />
      )}
      {inlineCaseConversationId && (() => {
        const conversation = diagnosisConversations.find((item) => item.id === inlineCaseConversationId) ?? activeDiagnosisConversation;
        return conversation ? <DiagnosisSaveAsCaseDialog conversation={conversation} accessToken={authState?.accessToken ?? ''} onClose={() => setInlineCaseConversationId(null)} onNotify={showToast} /> : null;
      })()}
      {projectShareContext && (
        <ProjectShareDialog
          conversations={projectShareContext.conversations}
          project={projectShareContext.project}
          onCancel={() => setProjectShareContext(null)}
          onCreatePublicShare={handleProjectPublicShare}
          onNotify={showToast}
        />
      )}
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
      <ProjectCreateModal open={projectModalOpen} onClose={closeProjectCreateModal} onCreate={handleProjectCreate} />
      {toast && <AppToast key={toast.id} toast={toast} />}
    </main>
  );
}

function PublicDiagnosisSharePage({ shareToken }: { shareToken: string }) {
  const [share, setShare] = useState<ApiPublicDiagnosisConversationShareResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [exported, setExported] = useState(false);
  const copyTimerRef = useRef<number | null>(null);
  const exportTimerRef = useRef<number | null>(null);

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError('');

    fetchPublicDiagnosisConversationShare(shareToken)
      .then((response) => {
        if (!ignore) setShare(response);
      })
      .catch((shareError) => {
        if (!ignore) {
          setError(shareError instanceof Error ? shareError.message : '分享内容加载失败');
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [shareToken]);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
      if (exportTimerRef.current !== null) window.clearTimeout(exportTimerRef.current);
    };
  }, []);

  const markCopied = () => {
    setCopied(true);
    if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
    copyTimerRef.current = window.setTimeout(() => {
      setCopied(false);
      copyTimerRef.current = null;
    }, 1800);
  };

  const markExported = () => {
    setExported(true);
    if (exportTimerRef.current !== null) window.clearTimeout(exportTimerRef.current);
    exportTimerRef.current = window.setTimeout(() => {
      setExported(false);
      exportTimerRef.current = null;
    }, 1800);
  };

  const handleCopy = async () => {
    if (!share) return;
    try {
      await copyTextToClipboard(share.content_markdown);
      markCopied();
    } catch {
      setCopied(false);
    }
  };

  const handleExport = () => {
    if (!share) return;
    downloadMarkdownFile(toSafeMarkdownFileName(`CanW-${share.title || '问诊分享'}`), share.content_markdown);
    markExported();
  };

  const variantLabel =
    diagnosisConversationShareOptions.find((option) => option.value === share?.variant)?.label ?? '会话分享';
  const createdLabel = share?.created_at ? new Date(share.created_at).toLocaleString('zh-CN') : '';

  return (
    <main className="public-share-page">
      <section className="public-share-card" aria-live="polite">
        <header className="public-share-header">
          <div className="public-share-brand">
            <span className="public-share-logo">
              <Bot size={18} />
            </span>
            <span>CanW</span>
          </div>
          {share && (
            <div className="public-share-actions">
              <button type="button" onClick={() => void handleCopy()}>
                {copied ? <Check size={16} /> : <Copy size={16} />}
                <span>{copied ? '已复制' : '复制 Markdown'}</span>
              </button>
              <button className="primary" type="button" onClick={handleExport}>
                {exported ? <Check size={16} /> : <Download size={16} />}
                <span>{exported ? '已导出' : '导出 Markdown'}</span>
              </button>
            </div>
          )}
        </header>

        {loading ? (
          <div className="public-share-state">
            <Sparkles size={22} />
            <strong>正在加载分享内容</strong>
          </div>
        ) : error ? (
          <div className="public-share-state error">
            <ShieldCheck size={22} />
            <strong>分享不可访问</strong>
            <span>{error}</span>
          </div>
        ) : share ? (
          <>
            <div className="public-share-title-block">
              <p>{variantLabel}</p>
              <h1>{share.title}</h1>
              <span>{createdLabel ? `创建于 ${createdLabel}` : '公开会话快照'}</span>
            </div>
            <article className="public-share-markdown" aria-label="Markdown 分享内容">
              <pre>{share.content_markdown}</pre>
            </article>
          </>
        ) : null}
      </section>
    </main>
  );
}

function PublicProjectSharePage({ shareToken }: { shareToken: string }) {
  const [share, setShare] = useState<ApiPublicProjectShareResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [exported, setExported] = useState(false);
  const copyTimerRef = useRef<number | null>(null);
  const exportTimerRef = useRef<number | null>(null);

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError('');

    fetchPublicProjectShare(shareToken)
      .then((response) => {
        if (!ignore) setShare(response);
      })
      .catch((shareError) => {
        if (!ignore) {
          setError(shareError instanceof Error ? shareError.message : '项目分享内容加载失败');
        }
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [shareToken]);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
      if (exportTimerRef.current !== null) window.clearTimeout(exportTimerRef.current);
    };
  }, []);

  const markCopied = () => {
    setCopied(true);
    if (copyTimerRef.current !== null) window.clearTimeout(copyTimerRef.current);
    copyTimerRef.current = window.setTimeout(() => {
      setCopied(false);
      copyTimerRef.current = null;
    }, 1800);
  };

  const markExported = () => {
    setExported(true);
    if (exportTimerRef.current !== null) window.clearTimeout(exportTimerRef.current);
    exportTimerRef.current = window.setTimeout(() => {
      setExported(false);
      exportTimerRef.current = null;
    }, 1800);
  };

  const handleCopy = async () => {
    if (!share) return;
    try {
      await copyTextToClipboard(share.content_markdown);
      markCopied();
    } catch {
      setCopied(false);
    }
  };

  const handleExport = () => {
    if (!share) return;
    downloadMarkdownFile(toSafeMarkdownFileName(`CanW-${share.title || '项目分享'}`), share.content_markdown);
    markExported();
  };

  const variantLabel = projectShareOptions.find((option) => option.value === share?.variant)?.label ?? '项目分享';
  const createdLabel = share?.created_at ? new Date(share.created_at).toLocaleString('zh-CN') : '';

  return (
    <main className="public-share-page">
      <section className="public-share-card" aria-live="polite">
        <header className="public-share-header">
          <div className="public-share-brand">
            <span className="public-share-logo">
              <Folder size={18} />
            </span>
            <span>CanW</span>
          </div>
          {share && (
            <div className="public-share-actions">
              <button type="button" onClick={() => void handleCopy()}>
                {copied ? <Check size={16} /> : <Copy size={16} />}
                <span>{copied ? '已复制' : '复制 Markdown'}</span>
              </button>
              <button className="primary" type="button" onClick={handleExport}>
                {exported ? <Check size={16} /> : <Download size={16} />}
                <span>{exported ? '已导出' : '导出 Markdown'}</span>
              </button>
            </div>
          )}
        </header>

        {loading ? (
          <div className="public-share-state">
            <Sparkles size={22} />
            <strong>正在加载项目分享</strong>
          </div>
        ) : error ? (
          <div className="public-share-state error">
            <ShieldCheck size={22} />
            <strong>项目分享不可访问</strong>
            <span>{error}</span>
          </div>
        ) : share ? (
          <>
            <div className="public-share-title-block">
              <p>{variantLabel}</p>
              <h1>{share.title}</h1>
              <span>{createdLabel ? `创建于 ${createdLabel}` : '公开项目快照'}</span>
            </div>
            <article className="public-share-markdown" aria-label="Markdown 项目分享内容">
              <pre>{share.content_markdown}</pre>
            </article>
          </>
        ) : null}
      </section>
    </main>
  );
}

function AppToast({ toast }: { toast: AppToastState }) {
  return (
    <div className="app-toast-region" aria-live="polite" aria-atomic="true">
      <div className={clsx('app-toast', `tone-${toast.tone}`)} role="status">
        {toast.message}
      </div>
    </div>
  );
}

function ChatSearchDialog({
  accessToken,
  conversations,
  isLoading,
  open,
  onClose,
  onNewChat,
  onOpenConversation,
}: {
  accessToken: string;
  conversations: DiagnosisConversation[];
  isLoading: boolean;
  open: boolean;
  onClose: () => void;
  onNewChat: () => void;
  onOpenConversation: (conversationId: string) => void;
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [remoteResults, setRemoteResults] = useState<DiagnosisConversation[] | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) return;

    setSearchQuery('');
    setRemoteResults(null);
    window.setTimeout(() => inputRef.current?.focus(), 0);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose, open]);

  useEffect(() => {
    const query = searchQuery.trim();
    if (!open || query.length < 2 || !accessToken) {
      setRemoteResults(null);
      setSearchLoading(false);
      return undefined;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      setSearchLoading(true);
      void searchDiagnosisConversations(accessToken, query)
        .then((items) => {
          if (!cancelled) setRemoteResults(items.map(mapApiDiagnosisConversation));
        })
        .catch(() => {
          // 网络异常时仍保留已加载内容的本地筛选，避免搜索入口失效。
          if (!cancelled) setRemoteResults(null);
        })
        .finally(() => {
          if (!cancelled) setSearchLoading(false);
        });
    }, 220);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [accessToken, open, searchQuery]);

  const filteredConversations = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return conversations;
    if (remoteResults !== null) return remoteResults;

    return conversations.filter((conversation) =>
      `${conversation.title} ${conversation.summary}`.toLowerCase().includes(query),
    );
  }, [conversations, remoteResults, searchQuery]);

  const groupedConversations = useMemo(() => {
    const groupOrder = ['今天', '昨天', '前 7 天', '更早'];
    const groups = new Map<string, DiagnosisConversation[]>();

    filteredConversations.forEach((conversation) => {
      const label = getConversationGroupLabel(conversation.updatedAt);
      groups.set(label, [...(groups.get(label) ?? []), conversation]);
    });

    return groupOrder
      .map((label) => ({ label, conversations: groups.get(label) ?? [] }))
      .filter((group) => group.conversations.length > 0);
  }, [filteredConversations]);

  if (!open) return null;

  return (
    <div className="chat-search-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="chat-search-dialog"
        role="dialog"
        aria-label="搜索聊天"
        aria-modal="true"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="chat-search-header">
          <input
            ref={inputRef}
            aria-label="搜索聊天"
            placeholder="搜索聊天..."
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
          />
          <button type="button" aria-label="关闭搜索聊天" onClick={onClose}>
            <X size={19} />
          </button>
        </div>
        <div className="chat-search-body">
          <button className="chat-search-new" type="button" onClick={onNewChat}>
            <PencilLine size={17} />
            <span>新聊天</span>
          </button>
          {isLoading || searchLoading ? (
            <div className="chat-search-empty" role="status">
              正在加载对话记录...
            </div>
          ) : groupedConversations.length > 0 ? (
            groupedConversations.map((group) => (
              <div className="chat-search-group" key={group.label}>
                <span className="chat-search-group-label">{group.label}</span>
                {group.conversations.map((conversation) => (
                  <button
                    className="chat-search-row"
                    key={conversation.id}
                    type="button"
                    onClick={() => onOpenConversation(conversation.id)}
                  >
                    <MessageCircle size={18} />
                    <span>{conversation.title}</span>
                  </button>
                ))}
              </div>
            ))
          ) : (
            <div className="chat-search-empty" role="status">
              {searchQuery.trim() ? '没有匹配的聊天' : '暂无对话记录'}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function ProjectMoveSubmenu({
  currentProjectId,
  moving,
  projects,
  onCreateProject,
  onMoveProject,
}: {
  currentProjectId: string | null;
  moving?: boolean;
  projects: CreatedProject[];
  onCreateProject: () => void;
  onMoveProject: (projectId: string) => void;
}) {
  return (
    <div className="project-move-submenu" role="menu" aria-label="选择项目">
      <button className="project-move-item new-project" type="button" role="menuitem" disabled={moving} onClick={onCreateProject}>
        <FolderPlus size={16} />
        <span>新项目</span>
      </button>
      {projects.length > 0 ? (
        projects.map((project) => (
          <button
            className="project-move-item"
            key={project.id}
            type="button"
            role="menuitem"
            aria-current={project.id === currentProjectId ? 'true' : undefined}
            disabled={moving}
            onClick={() => onMoveProject(project.id)}
          >
            <Folder size={16} />
            <span>{project.name}</span>
          </button>
        ))
      ) : (
        <div className="project-move-empty" role="menuitem" aria-disabled="true">
          暂无项目
        </div>
      )}
    </div>
  );
}

function Sidebar({
  activeThread,
  activeNavThread,
  activeConversationSource,
  activeDiagnosisConversationId,
  activeProjectChatId,
  collapsed,
  diagnosisConversations,
  diagnosisHistoryLoading,
  pinnedDiagnosisConversationIds,
  isAuthenticated,
  authUser,
  projectFolders,
  projects,
  resizing,
  onDiagnosisConversationSelect,
  onDiagnosisConversationPinToggle,
  onDiagnosisConversationArchive,
  onDiagnosisConversationRename,
  onDiagnosisConversationDelete,
  onDiagnosisConversationShare,
  onDiagnosisConversationMoveToProject,
  onSelect,
  onProjectConversationOpen,
  onProjectFolderSelect,
  onProjectArchive,
  onProjectDelete,
  onProjectPinToggle,
  onProjectShare,
  onProjectUpdate,
  onToggleSidebar,
  onSidebarResizeStart,
  onOpenAuth,
  onOpenProfile,
  onOpenProjectCreate,
  onOpenProjectCreateForMove,
  onSignOut,
}: {
  activeThread: ThreadKey;
  activeNavThread: ThreadKey | null;
  activeConversationSource: ActiveConversationSource;
  activeDiagnosisConversationId: string | null;
  activeProjectChatId: string | null;
  collapsed: boolean;
  diagnosisConversations: DiagnosisConversation[];
  diagnosisHistoryLoading: boolean;
  pinnedDiagnosisConversationIds: string[];
  isAuthenticated: boolean;
  authUser: AuthUser | null;
  projectFolders: ProjectFolder[];
  projects: CreatedProject[];
  resizing: boolean;
  onDiagnosisConversationSelect: (conversationId: string) => void;
  onDiagnosisConversationPinToggle: (conversationId: string) => void;
  onDiagnosisConversationArchive: (conversationId: string) => void;
  onDiagnosisConversationRename: (conversationId: string, title: string) => Promise<void>;
  onDiagnosisConversationDelete: (conversation: DiagnosisConversation) => void;
  onDiagnosisConversationShare: (conversation: DiagnosisConversation) => void;
  onDiagnosisConversationMoveToProject: (conversationId: string, projectId: string | null) => Promise<DiagnosisConversation>;
  onSelect: (thread: ThreadKey) => void;
  onProjectConversationOpen: (conversationId: string, projectId: string) => void;
  onProjectFolderSelect: (projectId: string) => void;
  onProjectArchive: (projectId: string) => void;
  onProjectDelete: (projectId: string) => Promise<void>;
  onProjectPinToggle: (projectId: string) => void;
  onProjectShare: (project: CreatedProject) => void;
  onProjectUpdate: (projectId: string, project: ProjectSettingsUpdate) => Promise<CreatedProject>;
  onToggleSidebar: () => void;
  onSidebarResizeStart: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onOpenAuth: () => void;
  onOpenProfile: () => void;
  onOpenProjectCreate: () => void;
  onOpenProjectCreateForMove: (conversationId: string) => void;
  onSignOut: () => void;
}) {
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [openConversationMenuId, setOpenConversationMenuId] = useState<string | null>(null);
  const [renamingConversationId, setRenamingConversationId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [renameSavingConversationId, setRenameSavingConversationId] = useState<string | null>(null);
  const [renameErrorConversationId, setRenameErrorConversationId] = useState<string | null>(null);
  const [accountMenuClosing, setAccountMenuClosing] = useState(false);
  const [projectsExpanded, setProjectsExpanded] = useState(true);
  const [expandedProjectIds, setExpandedProjectIds] = useState<string[]>([]);
  const [fullyExpandedProjectIds, setFullyExpandedProjectIds] = useState<string[]>([]);
  const [movingConversationId, setMovingConversationId] = useState<string | null>(null);
  const [openProjectMenuId, setOpenProjectMenuId] = useState<string | null>(null);
  const [settingsProjectId, setSettingsProjectId] = useState<string | null>(null);
  const [deleteProjectCandidate, setDeleteProjectCandidate] = useState<CreatedProject | null>(null);
  const [deleteProjectSaving, setDeleteProjectSaving] = useState(false);
  const [deleteProjectError, setDeleteProjectError] = useState('');
  const accountRegionRef = useRef<HTMLDivElement | null>(null);
  const accountMenuCloseTimerRef = useRef<number | null>(null);
  const renameInputRef = useRef<HTMLInputElement | null>(null);
  const projectNameById = useMemo(() => new Map(projects.map((project) => [project.id, project.name])), [projects]);
  const settingsProject = settingsProjectId ? projects.find((project) => project.id === settingsProjectId) ?? null : null;
  const projectConversationLimit = 5;

  const clearAccountMenuCloseTimer = () => {
    if (accountMenuCloseTimerRef.current) {
      window.clearTimeout(accountMenuCloseTimerRef.current);
      accountMenuCloseTimerRef.current = null;
    }
  };

  const closeAccountMenu = () => {
    clearAccountMenuCloseTimer();
    if (!accountMenuOpen && !accountMenuClosing) return;

    setAccountMenuOpen(false);
    setAccountMenuClosing(true);
    accountMenuCloseTimerRef.current = window.setTimeout(() => {
      setAccountMenuClosing(false);
      accountMenuCloseTimerRef.current = null;
    }, 150);
  };

  useEffect(() => {
    if (!openConversationMenuId) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!(event.target instanceof Element)) return;
      if (!event.target.closest('.thread-link')) {
        setOpenConversationMenuId(null);
      }
    };

    window.addEventListener('pointerdown', handlePointerDown);
    return () => window.removeEventListener('pointerdown', handlePointerDown);
  }, [openConversationMenuId]);

  useEffect(() => {
    if (!openProjectMenuId) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!(event.target instanceof Element)) return;
      if (!event.target.closest('.project-folder') && !event.target.closest('.project-folder-context-menu')) {
        setOpenProjectMenuId(null);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpenProjectMenuId(null);
      }
    };

    window.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [openProjectMenuId]);

  useEffect(() => {
    return () => clearAccountMenuCloseTimer();
  }, []);

  useEffect(() => {
    if (!accountMenuOpen) return undefined;

    const handlePointerDown = (event: PointerEvent) => {
      if (!(event.target instanceof Node)) return;
      if (!accountRegionRef.current?.contains(event.target)) {
        closeAccountMenu();
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        closeAccountMenu();
      }
    };

    window.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [accountMenuOpen, accountMenuClosing]);

  useEffect(() => {
    if (!renamingConversationId) return;
    renameInputRef.current?.focus();
    renameInputRef.current?.select();
  }, [renamingConversationId]);

  useEffect(() => {
    const projectIds = new Set(projectFolders.map((folder) => folder.id));
    setExpandedProjectIds((currentProjectIds) => currentProjectIds.filter((projectId) => projectIds.has(projectId)));
    setFullyExpandedProjectIds((currentProjectIds) => currentProjectIds.filter((projectId) => projectIds.has(projectId)));
    setOpenProjectMenuId((currentProjectId) => currentProjectId && projectIds.has(currentProjectId) ? currentProjectId : null);
  }, [projectFolders]);

  const handleAccountClick = () => {
    if (!isAuthenticated) {
      setAccountMenuOpen(false);
      setAccountMenuClosing(false);
      setOpenConversationMenuId(null);
      onOpenAuth();
      return;
    }

    setOpenConversationMenuId(null);
    if (accountMenuOpen) {
      closeAccountMenu();
      return;
    }

    clearAccountMenuCloseTimer();
    setAccountMenuClosing(false);
    setAccountMenuOpen(true);
  };

  const toggleProjectExpansion = (projectId: string) => {
    setExpandedProjectIds((currentProjectIds) => {
      if (currentProjectIds.includes(projectId)) {
        return currentProjectIds.filter((currentProjectId) => currentProjectId !== projectId);
      }
      return [...currentProjectIds, projectId];
    });
    setFullyExpandedProjectIds((currentProjectIds) => currentProjectIds.filter((currentProjectId) => currentProjectId !== projectId));
  };

  const toggleProjectConversationList = (projectId: string, expanded: boolean) => {
    setFullyExpandedProjectIds((currentProjectIds) => {
      if (expanded) {
        return currentProjectIds.includes(projectId) ? currentProjectIds : [...currentProjectIds, projectId];
      }
      return currentProjectIds.filter((currentProjectId) => currentProjectId !== projectId);
    });
  };

  const closeProjectMenu = () => {
    setOpenProjectMenuId(null);
  };

  const openProjectSettings = (project: CreatedProject) => {
    closeProjectMenu();
    setSettingsProjectId(project.id);
  };

  const requestProjectDelete = (project: CreatedProject) => {
    closeProjectMenu();
    setSettingsProjectId(null);
    setDeleteProjectCandidate(project);
    setDeleteProjectError('');
  };

  const confirmProjectDelete = async () => {
    if (!deleteProjectCandidate || deleteProjectSaving) return;
    setDeleteProjectSaving(true);
    setDeleteProjectError('');
    try {
      await onProjectDelete(deleteProjectCandidate.id);
      setDeleteProjectCandidate(null);
    } catch (deleteError) {
      setDeleteProjectError(deleteError instanceof Error ? deleteError.message : '项目删除失败');
    } finally {
      setDeleteProjectSaving(false);
    }
  };

  return (
    <aside className="app-sidebar">
      <div
        className={clsx('sidebar-resize-handle', resizing && 'dragging')}
        role="separator"
        aria-label="拖拽调整侧边栏宽度"
        aria-orientation="vertical"
        onPointerDown={onSidebarResizeStart}
      />
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
            setAccountMenuClosing(false);
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
              className={clsx('sidebar-action', activeNavThread === action.key && 'active')}
              key={action.key}
              onClick={() => onSelect(action.key)}
              type="button"
            >
              <Icon size={17} />
              <span>{action.label}</span>
            </button>
          );
        })}
        <div
          className={clsx('sidebar-action project-entry-action', activeNavThread === 'projects' && 'active')}
          role="group"
          aria-label="项目"
          onClick={() => onSelect('projects')}
        >
          <button
            className="project-entry-main"
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onSelect('projects');
            }}
          >
            <Folder size={17} />
            <span>项目</span>
          </button>
          <button
            className="project-entry-toggle"
            type="button"
            aria-label={projectsExpanded ? '收起项目列表' : '展开项目列表'}
            aria-expanded={projectsExpanded}
            aria-controls="sidebar-project-list"
            onClick={(event) => {
              event.stopPropagation();
              setProjectsExpanded((expanded) => !expanded);
            }}
          >
            <ChevronDown className="project-entry-chevron" size={14} />
          </button>
          <button
            className="project-entry-add"
            type="button"
            aria-label="新建项目"
            onClick={(event) => {
              event.stopPropagation();
              onOpenProjectCreate();
            }}
          >
            <Plus size={16} />
          </button>
        </div>
      </nav>

      <div
        id="sidebar-project-list"
        className={clsx('sidebar-section project-list-section', !projectsExpanded && 'collapsed')}
        aria-hidden={!projectsExpanded}
      >
        <div className="project-list-inner">
          {projectFolders.length > 0 ? (
            <>
              {projectFolders.map((folder) => {
                const project = projects.find((currentProject) => currentProject.id === folder.id) ?? null;
                const folderConversations = diagnosisConversations.filter((conversation) => conversation.projectId === folder.id);
                const projectExpanded = expandedProjectIds.includes(folder.id);
                const projectFullyExpanded = fullyExpandedProjectIds.includes(folder.id);
                const projectMenuOpen = openProjectMenuId === folder.id && project !== null;
                const hasConversationOverflow = folderConversations.length > projectConversationLimit;
                const visibleConversations = projectFullyExpanded
                  ? folderConversations
                  : folderConversations.slice(0, projectConversationLimit);

                return (
                  <div className={clsx('project-folder', projectExpanded && 'expanded')} key={folder.id}>
                    <div
                      className={clsx('project-folder-row', activeThread === 'projects' && activeProjectChatId === folder.id && 'active')}
                      aria-expanded={projectExpanded}
                    >
                      <button
                        className="project-folder-toggle"
                        type="button"
                        onClick={() => {
                          toggleProjectExpansion(folder.id);
                        }}
                      >
                        <ProjectIconBadge color={folder.color} iconKey={folder.iconKey} size="sidebar" />
                        <span className="project-folder-name">{folder.name}</span>
                        {folder.pinned && <Pin className="project-pinned-icon project-pinned-icon-sidebar" size={13} aria-label="已置顶" />}
                        <ChevronDown className="project-folder-chevron" size={14} />
                      </button>
                      <span className="project-folder-actions">
                        <button
                          type="button"
                          aria-label={`${folder.name}更多操作`}
                          aria-haspopup="menu"
                          aria-expanded={projectMenuOpen}
                          disabled={!project}
                          onClick={() => {
                            setOpenConversationMenuId(null);
                            setOpenProjectMenuId((currentProjectId) => {
                              return currentProjectId === folder.id ? null : folder.id;
                            });
                          }}
                        >
                          <MoreHorizontal className="project-folder-icon" size={15} />
                        </button>
                        <button type="button" aria-label={`打开${folder.name}`} onClick={() => onProjectFolderSelect(folder.id)}>
                          <PencilLine className="project-folder-icon" size={14} />
                        </button>
                      </span>
                    </div>
                    <div className={clsx('project-thread-region', projectExpanded && 'expanded')} aria-hidden={!projectExpanded}>
                      <div className="project-thread-list">
                        {visibleConversations.length === 0 && (
                          <div className="project-thread-empty">暂无对话</div>
                        )}
                        {visibleConversations.map((conversation) => (
                          <button
                            className={clsx(
                              'project-thread',
                              activeDiagnosisConversationId === conversation.id &&
                                activeThread === 'diagnosis' &&
                                activeConversationSource === 'project' &&
                                activeProjectChatId === folder.id &&
                                'selected',
                            )}
                            key={conversation.id}
                            onClick={() => onProjectConversationOpen(conversation.id, folder.id)}
                            tabIndex={projectExpanded ? undefined : -1}
                            type="button"
                          >
                            <span>{conversation.title}</span>
                            <small>{conversation.time}</small>
                          </button>
                        ))}
                        {hasConversationOverflow && (
                          <button
                            className="project-more"
                            type="button"
                            onClick={() => toggleProjectConversationList(folder.id, !projectFullyExpanded)}
                            tabIndex={projectExpanded ? undefined : -1}
                          >
                            {projectFullyExpanded ? '折叠对话' : '展开显示'}
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </>
          ) : (
            <div className="empty-chat project-list-empty">暂无项目</div>
          )}
        </div>
      </div>

      <div className="sidebar-section">
        <span className="sidebar-label">对话</span>
        {diagnosisHistoryLoading ? (
          <div className="empty-chat">加载中...</div>
        ) : diagnosisConversations.length > 0 ? (
          diagnosisConversations.map((conversation) => {
            const conversationPinned = pinnedDiagnosisConversationIds.includes(conversation.id);
            const conversationMenuOpen = openConversationMenuId === conversation.id;
            const conversationRenaming = renamingConversationId === conversation.id;
            const conversationRenameSaving = renameSavingConversationId === conversation.id;
            const conversationRenameErrored = renameErrorConversationId === conversation.id;
            const conversationProjectName = conversation.projectId ? projectNameById.get(conversation.projectId) ?? null : null;

            const cancelConversationRename = () => {
              setRenamingConversationId(null);
              setRenameDraft('');
              setRenameErrorConversationId(null);
              setRenameSavingConversationId(null);
            };

            const commitConversationRename = async () => {
              if (conversationRenameSaving) return;

              const nextTitle = renameDraft.trim();
              if (!nextTitle || nextTitle === conversation.title.trim()) {
                cancelConversationRename();
                return;
              }

              setRenameSavingConversationId(conversation.id);
              setRenameErrorConversationId(null);
              try {
                await onDiagnosisConversationRename(conversation.id, nextTitle);
                cancelConversationRename();
              } catch {
                setRenameErrorConversationId(conversation.id);
              } finally {
                setRenameSavingConversationId(null);
              }
            };

            const handleConversationRenameSubmit = async (event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              await commitConversationRename();
            };

            const handleConversationMenuAction = (action: 'pin' | 'rename' | 'archive') => {
              if (action === 'pin') {
                onDiagnosisConversationPinToggle(conversation.id);
              }
              if (action === 'rename') {
                setRenameDraft(conversation.title);
                setRenamingConversationId(conversation.id);
                setRenameErrorConversationId(null);
              }
              if (action === 'archive') {
                onDiagnosisConversationArchive(conversation.id);
              }
              setOpenConversationMenuId(null);
            };

            const handleConversationShare = () => {
              setOpenConversationMenuId(null);
              onDiagnosisConversationShare(conversation);
            };

            const handleConversationDelete = () => {
              setOpenConversationMenuId(null);
              onDiagnosisConversationDelete(conversation);
            };

            const handleConversationMoveToProject = async (projectId: string | null) => {
              if (movingConversationId === conversation.id) return;

              setMovingConversationId(conversation.id);
              try {
                await onDiagnosisConversationMoveToProject(conversation.id, projectId);
                setOpenConversationMenuId(null);
              } catch {
                // The parent move handler already shows the failure toast.
              } finally {
                setMovingConversationId(null);
              }
            };

            const handleConversationCreateProjectForMove = () => {
              setOpenConversationMenuId(null);
              onOpenProjectCreateForMove(conversation.id);
            };

            return (
              <div className={clsx('thread-link', conversationMenuOpen && 'menu-open')} key={conversation.id}>
                <div
                  className={clsx(
                    'thread-link-row',
                    activeDiagnosisConversationId === conversation.id &&
                      activeThread === 'diagnosis' &&
                      activeConversationSource === 'history' &&
                      'selected',
                    conversationPinned && 'pinned',
                  )}
                >
                  {conversationRenaming ? (
                    <form
                      className={clsx('thread-link-main', 'thread-rename-form', conversationRenameErrored && 'error')}
                      onBlur={(event) => {
                        if (event.relatedTarget instanceof Node && event.currentTarget.contains(event.relatedTarget)) {
                          return;
                        }
                        void commitConversationRename();
                      }}
                      onSubmit={handleConversationRenameSubmit}
                    >
                      <FileText size={15} />
                      <input
                        ref={renameInputRef}
                        aria-label="重命名聊天"
                        value={renameDraft}
                        maxLength={80}
                        disabled={conversationRenameSaving}
                        onChange={(event) => {
                          setRenameDraft(event.target.value);
                          setRenameErrorConversationId(null);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === 'Escape') {
                            event.preventDefault();
                            cancelConversationRename();
                          }
                        }}
                      />
                    </form>
                  ) : (
                    <button
                      className={clsx('thread-link-main', conversationProjectName && 'has-project-source')}
                      type="button"
                      onClick={() => {
                        setOpenConversationMenuId(null);
                        setRenamingConversationId(null);
                        onDiagnosisConversationSelect(conversation.id);
                      }}
                    >
                      <FileText size={15} />
                      <span className="thread-link-copy">
                        <span className="thread-link-title">{conversation.title}</span>
                        {conversationProjectName && (
                          <small className="thread-link-project">{conversationProjectName}</small>
                        )}
                      </span>
                    </button>
                  )}
                  <span className="thread-link-meta">
                    <small className="thread-link-time">{conversation.time}</small>
                    <span className="thread-link-actions">
                      <button
                        className="thread-link-action thread-pin-button"
                        type="button"
                        aria-label={conversationPinned ? '取消置顶聊天' : '置顶聊天'}
                        aria-pressed={conversationPinned}
                        onClick={() => {
                          onDiagnosisConversationPinToggle(conversation.id);
                          setOpenConversationMenuId(null);
                        }}
                      >
                        {conversationPinned ? <PinOff size={14} strokeWidth={1.8} /> : <Pin size={14} strokeWidth={2} />}
                      </button>
                      <button
                        className="thread-link-action"
                        type="button"
                        aria-label="更多聊天操作"
                        aria-expanded={conversationMenuOpen}
                        aria-haspopup="menu"
                        onClick={() => setOpenConversationMenuId(conversationMenuOpen ? null : conversation.id)}
                      >
                        <MoreHorizontal size={16} />
                      </button>
                    </span>
                  </span>
                </div>
                {conversationMenuOpen && (
                  <div
                    className={clsx('thread-context-menu', conversation.projectId && 'has-project-remove')}
                    role="menu"
                    aria-label="聊天操作"
                  >
                    <button type="button" role="menuitem" onClick={handleConversationShare}>
                      <Upload size={16} />
                      <span>分享</span>
                    </button>
                    <button type="button" role="menuitem" onClick={() => handleConversationMenuAction('rename')}>
                      <PencilLine size={16} />
                      <span>重命名</span>
                    </button>
                    <div className="thread-menu-submenu-wrap">
                      <button
                        className="thread-menu-submenu-trigger"
                        type="button"
                        role="menuitem"
                        aria-haspopup="menu"
                        aria-expanded="true"
                      >
                        <Folder size={16} />
                        <span>移至项目</span>
                        <ChevronRight className="thread-menu-chevron" size={15} />
                      </button>
                      <ProjectMoveSubmenu
                        currentProjectId={conversation.projectId}
                        moving={movingConversationId === conversation.id}
                        projects={projects}
                        onCreateProject={handleConversationCreateProjectForMove}
                        onMoveProject={(projectId) => {
                          void handleConversationMoveToProject(projectId);
                        }}
                      />
                    </div>
                    {conversation.projectId && (
                      <button
                        type="button"
                        role="menuitem"
                        disabled={movingConversationId === conversation.id}
                        onClick={() => {
                          void handleConversationMoveToProject(null);
                        }}
                      >
                        <FolderX size={16} />
                        <span>从「{conversationProjectName ?? '当前项目'}」移除</span>
                      </button>
                    )}
                    <div className="thread-menu-separator" />
                    <button type="button" role="menuitem" onClick={() => handleConversationMenuAction('pin')}>
                      <Pin size={16} />
                      <span>{conversationPinned ? '取消置顶' : '置顶聊天'}</span>
                    </button>
                    <button type="button" role="menuitem" onClick={() => handleConversationMenuAction('archive')}>
                      <Archive size={16} />
                      <span>归档</span>
                    </button>
                    <button
                      className="danger"
                      type="button"
                      role="menuitem"
                      onClick={handleConversationDelete}
                    >
                      <Trash2 size={16} />
                      <span>删除</span>
                    </button>
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <div className="empty-chat">暂无聊天</div>
        )}
      </div>

      <div className="account-region" ref={accountRegionRef}>
        {isAuthenticated && (accountMenuOpen || accountMenuClosing) && !collapsed && (
          <div className={clsx('account-menu', accountMenuClosing && !accountMenuOpen && 'closing')} role="menu" aria-label="账号菜单">
            <div className="account-menu-readonly account-menu-muted" role="menuitem" aria-disabled="true">
              <CircleUserRound size={16} />
              <span>{getAccountIdentifier(authUser)}</span>
            </div>
            <div className="account-menu-readonly account-menu-muted" role="menuitem" aria-disabled="true">
              <UserRound size={16} />
              <span>{getAccountRole(authUser)}</span>
            </div>
            <div className="account-menu-separator" />
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                closeAccountMenu();
                onOpenProfile();
              }}
            >
              <CircleUserRound size={16} />
              <span>个人资料</span>
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                closeAccountMenu();
                onSelect('settings');
              }}
            >
              <Settings2 size={16} />
              <span>设置</span>
              <small>Ctrl+,</small>
            </button>
            <button
              className="account-menu-danger"
              type="button"
              role="menuitem"
              onClick={() => {
                closeAccountMenu();
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

      <ProjectSettingsModal
        project={settingsProject}
        onClose={() => setSettingsProjectId(null)}
        onDeleteRequest={requestProjectDelete}
        onUpdate={onProjectUpdate}
      />
      {openProjectMenuId && (() => {
        const project = projects.find((currentProject) => currentProject.id === openProjectMenuId);
        if (!project) return null;
        const folder = projectFolders.find((currentFolder) => currentFolder.id === project.id);
        const pinned = Boolean(folder?.pinned);
        return (
          <div className="project-action-overlay" role="presentation" onMouseDown={closeProjectMenu}>
          <section
            className="project-folder-context-menu project-action-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="project-action-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="project-action-header">
              <span id="project-action-title">{project.name}</span>
              <button type="button" aria-label="关闭项目操作" onClick={closeProjectMenu}><X size={17} /></button>
            </header>
            <button
              type="button"
              onClick={() => {
                closeProjectMenu();
                onProjectShare(project);
              }}
            >
              <Upload size={16} />
              <span>分享项目</span>
            </button>
            <button type="button" onClick={() => openProjectSettings(project)}>
              <PencilLine size={16} />
              <span>重命名项目</span>
            </button>
            <button type="button" onClick={() => openProjectSettings(project)}>
              <Settings2 size={16} />
              <span>项目设置</span>
            </button>
            <div className="project-folder-context-separator" role="separator" />
            <button
              type="button"
              onClick={() => {
                closeProjectMenu();
                onProjectPinToggle(project.id);
              }}
            >
              {pinned ? <PinOff size={16} /> : <Pin size={16} />}
              <span>{pinned ? '取消置顶项目' : '置顶项目'}</span>
            </button>
            <button
              type="button"
              onClick={() => {
                closeProjectMenu();
                onProjectArchive(project.id);
              }}
            >
              <Archive size={16} />
              <span>归档项目</span>
            </button>
            <button className="danger" type="button" onClick={() => requestProjectDelete(project)}>
              <Trash2 size={16} />
              <span>删除项目</span>
            </button>
          </section>
          </div>
        );
      })()}
      <DeleteProjectDialog
        error={deleteProjectError}
        project={deleteProjectCandidate}
        saving={deleteProjectSaving}
        onCancel={() => {
          if (deleteProjectSaving) return;
          setDeleteProjectCandidate(null);
        }}
        onConfirm={() => {
          void confirmProjectDelete();
        }}
      />
    </aside>
  );
}

function RenameConversationDialog({
  conversation,
  saving,
  error,
  onCancel,
  onConfirm,
}: {
  conversation: DiagnosisConversation;
  saving: boolean;
  error: string;
  onCancel: () => void;
  onConfirm: (title: string) => Promise<void>;
}) {
  const [draft, setDraft] = useState(conversation.title);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const normalizedDraft = draft.trim();
  const canSubmit = Boolean(normalizedDraft) && normalizedDraft !== conversation.title.trim() && !saving;

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !saving) {
        onCancel();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onCancel, saving]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;
    void onConfirm(normalizedDraft);
  };

  return (
    <div
      className="delete-conversation-overlay rename-conversation-overlay"
      role="presentation"
      onMouseDown={(event: ReactMouseEvent<HTMLDivElement>) => {
        if (event.target === event.currentTarget && !saving) {
          onCancel();
        }
      }}
    >
      <section
        className="delete-conversation-dialog rename-conversation-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rename-conversation-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 id="rename-conversation-title">重命名聊天</h2>
        <form onSubmit={handleSubmit}>
          <input
            ref={inputRef}
            aria-label="聊天名称"
            disabled={saving}
            maxLength={80}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          {error && (
            <p className="delete-conversation-error" role="alert">
              {error}
            </p>
          )}
          <div className="delete-conversation-actions">
            <button className="delete-conversation-cancel" type="button" disabled={saving} onClick={onCancel}>
              取消
            </button>
            <button className="delete-conversation-confirm" type="submit" disabled={!canSubmit}>
              {saving ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function DeleteConversationDialog({
  conversation,
  saving,
  error,
  onCancel,
  onConfirm,
}: {
  conversation: DiagnosisConversation;
  saving: boolean;
  error: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !saving) {
        onCancel();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onCancel, saving]);

  return (
    <div
      className="delete-conversation-overlay"
      role="presentation"
      onMouseDown={(event: ReactMouseEvent<HTMLDivElement>) => {
        if (event.target === event.currentTarget) {
          onCancel();
        }
      }}
    >
      <section
        className="delete-conversation-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-conversation-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 id="delete-conversation-title">删除聊天？</h2>
        <p className="delete-conversation-lead">
          这会删除“<strong>{conversation.title}</strong>”。
        </p>
        {error && (
          <p className="delete-conversation-error" role="alert">
            删除失败，请稍后重试。
          </p>
        )}
        <div className="delete-conversation-actions">
          <button className="delete-conversation-cancel" type="button" disabled={saving} onClick={onCancel}>
            取消
          </button>
          <button className="delete-conversation-confirm" type="button" disabled={saving} onClick={onConfirm}>
            {saving ? '删除中...' : '删除'}
          </button>
        </div>
      </section>
    </div>
  );
}

function DeleteMessageTurnDialog({
  saving,
  onCancel,
  onConfirm,
}: {
  saving: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !saving) {
        onCancel();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onCancel, saving]);

  return (
    <div
      className="delete-conversation-overlay delete-message-turn-overlay"
      role="presentation"
      onMouseDown={(event: ReactMouseEvent<HTMLDivElement>) => {
        if (event.target === event.currentTarget && !saving) {
          onCancel();
        }
      }}
    >
      <section
        className="delete-conversation-dialog delete-message-turn-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-message-turn-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <p id="delete-message-turn-title" className="delete-conversation-lead delete-message-turn-lead">
          确定删除这轮对话？这条回复和对应的用户问题都会删除
        </p>
        <div className="delete-conversation-actions">
          <button className="delete-conversation-cancel" type="button" disabled={saving} onClick={onCancel}>
            取消
          </button>
          <button className="delete-conversation-confirm" type="button" disabled={saving} onClick={onConfirm}>
            {saving ? '删除中...' : '确定'}
          </button>
        </div>
      </section>
    </div>
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
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
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
    setIsUploadingAvatar(false);
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
      setIsUploadingAvatar(true);
      const avatarBlob = await fileToAvatarBlob(file);
      let user: AuthUser;
      try {
        user = await uploadUserAvatar(authState.accessToken, avatarBlob);
      } catch (uploadError) {
        if (!isUnauthorizedError(uploadError)) throw uploadError;
        const refreshedAuthState = await onTokenRefresh();
        user = await uploadUserAvatar(refreshedAuthState.accessToken, avatarBlob);
      }

      setAvatarUrl(user.avatar_url ?? null);
      onSaved(user);
      setMessage('头像已更新');
    } catch (avatarError) {
      if (isUnauthorizedError(avatarError)) {
        onAuthExpired();
        return;
      }
      setError(avatarError instanceof Error ? avatarError.message : '头像处理失败');
    } finally {
      setIsUploadingAvatar(false);
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
        });
      } catch (saveError) {
        if (!isUnauthorizedError(saveError)) throw saveError;
        const refreshedAuthState = await onTokenRefresh();
        user = await updateUserProfile(refreshedAuthState.accessToken, {
          displayName: nextDisplayName,
          username: nextUsername,
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
              disabled={isSaving || isUploadingAvatar}
              type="button"
              aria-label="编辑头像"
              onClick={() => avatarInputRef.current?.click()}
            >
              {avatarUrl ? <img alt="" src={avatarUrl} /> : <span>{getAvatarLabel(displayName || username || email)}</span>}
            </button>
            <button
              className="profile-camera-button"
              disabled={isSaving || isUploadingAvatar}
              type="button"
              aria-label="选择头像图片"
              onClick={() => avatarInputRef.current?.click()}
            >
              <Camera size={17} />
            </button>
            <input
              ref={avatarInputRef}
              hidden
              accept="image/jpeg,image/png,image/webp"
              disabled={isSaving || isUploadingAvatar}
              type="file"
              onChange={handleAvatarChange}
            />
          </div>

          <label className="profile-field">
            <span>显示名称</span>
            <div>
              <input
                disabled={isSaving || isUploadingAvatar}
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
                disabled={isSaving || isUploadingAvatar}
                maxLength={32}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="请输入用户名"
                value={username}
              />
            </div>
          </label>

          {(isLoading || isUploadingAvatar || message || error) && (
            <p className={clsx('auth-message', error && 'error')} role="status">
              {error || message || (isUploadingAvatar ? '正在上传头像...' : '正在同步资料')}
            </p>
          )}

          <p className="profile-help">你的个人资料有助于大家在群聊中认识你。</p>

          <div className="profile-actions">
            <button className="profile-secondary" disabled={isSaving || isUploadingAvatar} type="button" onClick={onClose}>
              取消
            </button>
            <button className="auth-submit profile-submit" disabled={isLoading || isSaving || isUploadingAvatar} type="submit">
              {isSaving ? '保存中' : '保存'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

type ProjectFilter = 'all' | 'owned' | 'shared';

function ProjectsPage({
  activeProjectId,
  configuredModels,
  conversations,
  error,
  isConversationSending,
  isLoading,
  pinnedProjectIds,
  projectConversations,
  projectConversationsError,
  projectConversationsLoading,
  projects,
  selectedModelConfigId,
  userPreferences,
  onProjectConversationMove,
  onProjectConversationOpen,
  onProjectConversationSubmit,
  onProjectArchive,
  onProjectDelete,
  onAudioTranscribe,
  onAttachmentUpload,
  onAttachmentDelete,
  onOpenCreate,
  onModelSelect,
  onProjectPinToggle,
  onProjectOpen,
  onProjectShare,
  onProjectUpdate,
}: {
  activeProjectId: string | null;
  configuredModels: ConfiguredModel[];
  conversations: DiagnosisConversation[];
  error: string;
  isConversationSending: boolean;
  isLoading: boolean;
  pinnedProjectIds: string[];
  projectConversations: DiagnosisConversation[];
  projectConversationsError: string;
  projectConversationsLoading: boolean;
  projects: CreatedProject[];
  selectedModelConfigId: string | null;
  userPreferences: UserPreferences;
  onProjectConversationMove: (conversationId: string, projectId: string | null) => Promise<DiagnosisConversation>;
  onProjectConversationOpen: (conversationId: string, projectId: string) => void;
  onProjectConversationSubmit: (
    projectId: string,
    question: string,
    options?: DiagnosisSubmitOptions,
  ) => Promise<void>;
  onProjectArchive: (projectId: string) => void;
  onProjectDelete: (projectId: string) => Promise<void>;
  onAudioTranscribe: (audio: File) => Promise<string>;
  onAttachmentUpload: (attachment: File) => Promise<ApiDiagnosisFileResponse>;
  onAttachmentDelete: (fileId: string) => Promise<void>;
  onOpenCreate: () => void;
  onModelSelect: (modelConfigId: string | null) => void;
  onProjectPinToggle: (projectId: string) => void;
  onProjectOpen: (projectId: string) => void;
  onProjectShare: (project: CreatedProject) => void;
  onProjectUpdate: (projectId: string, project: ProjectSettingsUpdate) => Promise<CreatedProject>;
}) {
  const [query, setQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<ProjectFilter>('all');
  const [openProjectMenuId, setOpenProjectMenuId] = useState<string | null>(null);
  const [settingsProjectId, setSettingsProjectId] = useState<string | null>(null);
  const [deleteProjectCandidate, setDeleteProjectCandidate] = useState<CreatedProject | null>(null);
  const [deleteProjectSaving, setDeleteProjectSaving] = useState(false);
  const [deleteProjectError, setDeleteProjectError] = useState('');
  const activeProject = activeProjectId ? projects.find((project) => project.id === activeProjectId) ?? null : null;
  const settingsProject = settingsProjectId ? projects.find((project) => project.id === settingsProjectId) ?? null : null;

  const filteredProjects = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return projects.filter((project) => {
      const matchesQuery = !normalizedQuery || project.name.toLowerCase().includes(normalizedQuery);
      const matchesFilter =
        activeFilter === 'all' ||
        (activeFilter === 'owned' && project.owner === 'me') ||
        (activeFilter === 'shared' && project.owner === 'shared');

      return matchesQuery && matchesFilter;
    });
  }, [activeFilter, projects, query]);

  useEffect(() => {
    if (!openProjectMenuId) return;
    if (filteredProjects.some((project) => project.id === openProjectMenuId)) return;
    setOpenProjectMenuId(null);
  }, [filteredProjects, openProjectMenuId]);

  useEffect(() => {
    if (!settingsProjectId) return;
    if (projects.some((project) => project.id === settingsProjectId)) return;
    setSettingsProjectId(null);
  }, [projects, settingsProjectId]);

  useEffect(() => {
    if (!openProjectMenuId) return;

    const closeMenu = () => setOpenProjectMenuId(null);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu();
    };

    window.addEventListener('click', closeMenu);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('click', closeMenu);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [openProjectMenuId]);

  const handleProjectRowKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>, projectId: string) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onProjectOpen(projectId);
  };

  const requestProjectDelete = (project: CreatedProject) => {
    setOpenProjectMenuId(null);
    setSettingsProjectId(null);
    setDeleteProjectCandidate(project);
    setDeleteProjectError('');
  };

  const confirmProjectDelete = async () => {
    if (!deleteProjectCandidate || deleteProjectSaving) return;
    setDeleteProjectSaving(true);
    setDeleteProjectError('');
    try {
      await onProjectDelete(deleteProjectCandidate.id);
      setDeleteProjectCandidate(null);
    } catch (deleteError) {
      setDeleteProjectError(deleteError instanceof Error ? deleteError.message : '项目删除失败');
    } finally {
      setDeleteProjectSaving(false);
    }
  };

  if (activeProject) {
    return (
      <section className="projects-page projects-apple project-detail-page">
        <div className="projects-page-inner">
          <ProjectDetailView
            configuredModels={configuredModels}
            conversations={projectConversations}
            error={projectConversationsError}
            isConversationSending={isConversationSending}
            isLoading={projectConversationsLoading}
            isPinned={pinnedProjectIds.includes(activeProject.id)}
            project={activeProject}
            selectedModelConfigId={selectedModelConfigId}
            sourceConversations={conversations}
            userPreferences={userPreferences}
            onConversationMove={onProjectConversationMove}
            onConversationOpen={onProjectConversationOpen}
            onConversationSubmit={onProjectConversationSubmit}
            onAudioTranscribe={onAudioTranscribe}
            onAttachmentUpload={onAttachmentUpload}
            onAttachmentDelete={onAttachmentDelete}
            onModelSelect={onModelSelect}
            onRequestArchive={() => onProjectArchive(activeProject.id)}
            onOpenSettings={() => setSettingsProjectId(activeProject.id)}
            onRequestDelete={() => requestProjectDelete(activeProject)}
            onShareProject={() => onProjectShare(activeProject)}
            onTogglePin={() => onProjectPinToggle(activeProject.id)}
          />
        </div>
        <ProjectSettingsModal
          project={settingsProject}
          onClose={() => setSettingsProjectId(null)}
          onDeleteRequest={requestProjectDelete}
          onUpdate={onProjectUpdate}
        />
        <DeleteProjectDialog
          error={deleteProjectError}
          project={deleteProjectCandidate}
          saving={deleteProjectSaving}
          onCancel={() => {
            if (deleteProjectSaving) return;
            setDeleteProjectCandidate(null);
          }}
          onConfirm={() => {
            void confirmProjectDelete();
          }}
        />
      </section>
    );
  }

  return (
    <section className="projects-page projects-apple">
      <div className="projects-page-inner">
        <header className="projects-page-header">
          <h1>项目</h1>
          <div className="projects-toolbar">
            <label className="projects-search">
              <Search size={15} />
              <input aria-label="搜索项目" onChange={(event) => setQuery(event.target.value)} placeholder="搜索项目" value={query} />
            </label>
            <button className="projects-create-button" type="button" onClick={onOpenCreate}>
              <Plus size={16} />
              <span>新建</span>
            </button>
          </div>
        </header>

        <div className="projects-tabs" role="tablist" aria-label="项目筛选">
          <button
            className={clsx(activeFilter === 'all' && 'active')}
            type="button"
            role="tab"
            aria-selected={activeFilter === 'all'}
            onClick={() => setActiveFilter('all')}
          >
            全部
          </button>
          <button
            className={clsx(activeFilter === 'owned' && 'active')}
            type="button"
            role="tab"
            aria-selected={activeFilter === 'owned'}
            onClick={() => setActiveFilter('owned')}
          >
            由你创建
          </button>
          <button
            className={clsx(activeFilter === 'shared' && 'active')}
            type="button"
            role="tab"
            aria-selected={activeFilter === 'shared'}
            onClick={() => setActiveFilter('shared')}
          >
            与你共享
          </button>
        </div>

        {error && (
          <p className="projects-error" role="alert">
            {error}
          </p>
        )}

        <div className="projects-table" role="table" aria-label="项目列表">
          <div className="projects-table-head" role="row">
            <span role="columnheader">名称</span>
            <span role="columnheader">修改时间</span>
            <span role="columnheader" aria-label="项目操作" />
          </div>
          {filteredProjects.map((project) => (
            <ProjectRow
              active={activeProjectId === project.id}
              isMenuOpen={openProjectMenuId === project.id}
              isPinned={pinnedProjectIds.includes(project.id)}
              key={project.id}
              project={project}
              onOpen={() => onProjectOpen(project.id)}
              onOpenMenu={() => setOpenProjectMenuId((currentProjectId) => (currentProjectId === project.id ? null : project.id))}
              onOpenSettings={() => {
                setSettingsProjectId(project.id);
                setOpenProjectMenuId(null);
              }}
              onRequestArchive={() => {
                onProjectArchive(project.id);
                setOpenProjectMenuId(null);
              }}
              onRequestDelete={() => requestProjectDelete(project)}
              onRowKeyDown={(event) => handleProjectRowKeyDown(event, project.id)}
              onTogglePin={() => {
                onProjectPinToggle(project.id);
                setOpenProjectMenuId(null);
              }}
            />
          ))}
          {filteredProjects.length === 0 && (
            <div className="projects-empty" role="status">
              {isLoading ? '正在加载项目...' : projects.length === 0 ? '暂无项目' : '没有找到项目'}
            </div>
          )}
        </div>
      </div>
      <ProjectSettingsModal
        project={settingsProject}
        onClose={() => setSettingsProjectId(null)}
        onDeleteRequest={requestProjectDelete}
        onUpdate={onProjectUpdate}
      />
      <DeleteProjectDialog
        error={deleteProjectError}
        project={deleteProjectCandidate}
        saving={deleteProjectSaving}
        onCancel={() => {
          if (deleteProjectSaving) return;
          setDeleteProjectCandidate(null);
        }}
        onConfirm={() => {
          void confirmProjectDelete();
        }}
      />
    </section>
  );
}

function formatProjectConversationDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

function ProjectDetailView({
  configuredModels,
  conversations,
  error,
  isConversationSending,
  isLoading,
  isPinned,
  project,
  selectedModelConfigId,
  sourceConversations,
  userPreferences,
  onConversationMove,
  onConversationOpen,
  onConversationSubmit,
  onAudioTranscribe,
  onAttachmentUpload,
  onAttachmentDelete,
  onModelSelect,
  onOpenSettings,
  onRequestArchive,
  onRequestDelete,
  onShareProject,
  onTogglePin,
}: {
  configuredModels: ConfiguredModel[];
  conversations: DiagnosisConversation[];
  error: string;
  isConversationSending: boolean;
  isLoading: boolean;
  isPinned: boolean;
  project: CreatedProject;
  selectedModelConfigId: string | null;
  sourceConversations: DiagnosisConversation[];
  userPreferences: UserPreferences;
  onConversationMove: (conversationId: string, projectId: string | null) => Promise<DiagnosisConversation>;
  onConversationOpen: (conversationId: string, projectId: string) => void;
  onConversationSubmit: (
    projectId: string,
    question: string,
    options?: DiagnosisSubmitOptions,
  ) => Promise<void>;
  onAudioTranscribe: (audio: File) => Promise<string>;
  onAttachmentUpload: (attachment: File) => Promise<ApiDiagnosisFileResponse>;
  onAttachmentDelete: (fileId: string) => Promise<void>;
  onModelSelect: (modelConfigId: string | null) => void;
  onOpenSettings: () => void;
  onRequestArchive: () => void;
  onRequestDelete: () => void;
  onShareProject: () => void;
  onTogglePin: () => void;
}) {
  const [draft, setDraft] = useState('');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [actionMenuOpen, setActionMenuOpen] = useState(false);
  const [activeSection, setActiveSection] = useState<'chat' | 'sources'>('chat');
  const [movingConversationId, setMovingConversationId] = useState<string | null>(null);
  const availableConversations = sourceConversations.filter((conversation) => conversation.projectId !== project.id);
  useEffect(() => {
    if (!actionMenuOpen) return;

    const closeMenu = () => setActionMenuOpen(false);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu();
    };

    window.addEventListener('click', closeMenu);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('click', closeMenu);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [actionMenuOpen]);

  const moveConversation = async (conversationId: string, projectId: string | null) => {
    setMovingConversationId(conversationId);
    try {
      await onConversationMove(conversationId, projectId);
      if (projectId) setPickerOpen(false);
    } finally {
      setMovingConversationId(null);
    }
  };

  const submitProjectDraft = (options: DiagnosisSubmitOptions = {}) => {
    const question = draft.trim();
    const attachmentIds = options.attachmentIds ?? [];
    const structuredData = options.structuredData ?? null;
    const hasStructuredData = Boolean(structuredData && Object.keys(structuredData).length > 0);
    if ((!question && attachmentIds.length === 0 && !hasStructuredData) || isConversationSending) return;

    setDraft('');
    void onConversationSubmit(project.id, question, options);
  };

  return (
    <section className="project-detail project-detail-minimal">
      <header className="project-detail-minimal-header">
        <div className="project-detail-title">
          <Folder size={31} />
          <h1>{project.name}</h1>
        </div>
        <div className="project-detail-top-actions">
          <button className="project-share-button" type="button" onClick={onShareProject}>
            <Upload size={15} />
            <span>分享</span>
          </button>
          <div className="project-more-wrap">
            <button
              className={clsx('project-more-button', actionMenuOpen && 'open')}
              type="button"
              aria-haspopup="menu"
              aria-expanded={actionMenuOpen}
              aria-label="项目操作"
              onClick={(event) => {
                event.stopPropagation();
                setActionMenuOpen((current) => !current);
              }}
            >
              <MoreHorizontal size={18} />
            </button>
            {actionMenuOpen && (
              <div className="project-detail-menu" role="menu" onClick={(event) => event.stopPropagation()}>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setActionMenuOpen(false);
                    setPickerOpen(true);
                  }}
                >
                  <Link2 size={16} />
                  <span>添加已有对话</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setActionMenuOpen(false);
                    onTogglePin();
                  }}
                >
                  {isPinned ? <PinOff size={16} /> : <Pin size={16} />}
                  <span>{isPinned ? '取消置顶' : '置顶项目'}</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setActionMenuOpen(false);
                    onOpenSettings();
                  }}
                >
                  <Settings2 size={16} />
                  <span>项目设置</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setActionMenuOpen(false);
                    onRequestArchive();
                  }}
                >
                  <Archive size={16} />
                  <span>归档项目</span>
                </button>
                <div className="project-detail-menu-separator" role="separator" />
                <button
                  className="danger"
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setActionMenuOpen(false);
                    onRequestDelete();
                  }}
                >
                  <Trash2 size={16} />
                  <span>删除项目</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <DiagnosisComposer
        className="project-new-chat-composer"
        configuredModels={configuredModels}
        draft={draft}
        isSending={isConversationSending}
        onChange={setDraft}
        onAudioTranscribe={onAudioTranscribe}
        onAttachmentUpload={onAttachmentUpload}
        onAttachmentDelete={onAttachmentDelete}
        onModelSelect={onModelSelect}
        panelPlacement="down"
        onSubmit={submitProjectDraft}
        placeholder={`${project.name}中的新聊天`}
        selectedModelConfigId={selectedModelConfigId}
        sendDisabled={isConversationSending}
        uploadPreferences={userPreferences}
      />

      <div className="project-detail-tabs" role="tablist" aria-label="项目内容">
        <button
          className={clsx(activeSection === 'chat' && 'active')}
          type="button"
          role="tab"
          aria-selected={activeSection === 'chat'}
          onClick={() => setActiveSection('chat')}
        >
          聊天
        </button>
        <button
          className={clsx(activeSection === 'sources' && 'active')}
          type="button"
          role="tab"
          aria-selected={activeSection === 'sources'}
          onClick={() => setActiveSection('sources')}
        >
          来源
        </button>
      </div>

      {activeSection === 'chat' ? (
        <section className="project-chat-list" aria-label="项目内对话">
          {error && (
            <p className="project-detail-error" role="alert">
              {error}
            </p>
          )}
          {isLoading && conversations.length === 0 ? (
            <div className="project-chat-empty" role="status">
              正在加载项目内对话...
            </div>
          ) : conversations.length === 0 ? (
            <div className="project-chat-empty" role="status">
              还没有项目内对话
            </div>
          ) : (
            conversations.map((conversation) => (
              <div className="project-chat-row" key={conversation.id}>
                <button className="project-chat-main" type="button" onClick={() => onConversationOpen(conversation.id, project.id)}>
                  <span>
                    <strong>{conversation.title}</strong>
                    <small>{conversation.summary || '暂无摘要'}</small>
                  </span>
                </button>
                <div className="project-chat-row-meta">
                  <time>{formatProjectConversationDate(conversation.updatedAt)}</time>
                  <button
                    disabled={movingConversationId === conversation.id}
                    type="button"
                    onClick={() => {
                      void moveConversation(conversation.id, null);
                    }}
                  >
                    {movingConversationId === conversation.id ? '移出中' : '移出'}
                  </button>
                </div>
              </div>
            ))
          )}
        </section>
      ) : (
        <section className="project-source-empty" aria-label="项目来源">
          <FileText size={20} />
          <span>来源会用于保存项目文件和资料。</span>
        </section>
      )}

      <ProjectConversationPicker
        conversations={availableConversations}
        movingConversationId={movingConversationId}
        open={pickerOpen}
        project={project}
        onClose={() => setPickerOpen(false)}
        onMove={(conversationId) => {
          void moveConversation(conversationId, project.id);
        }}
      />
    </section>
  );
}

function ProjectConversationPicker({
  conversations,
  movingConversationId,
  open,
  project,
  onClose,
  onMove,
}: {
  conversations: DiagnosisConversation[];
  movingConversationId: string | null;
  open: boolean;
  project: CreatedProject;
  onClose: () => void;
  onMove: (conversationId: string) => void;
}) {
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (!open) return;
    setQuery('');
  }, [open]);

  if (!open) return null;

  const normalizedQuery = query.trim().toLowerCase();
  const filteredConversations = conversations.filter((conversation) =>
    `${conversation.title} ${conversation.summary}`.toLowerCase().includes(normalizedQuery),
  );

  return (
    <div className="project-modal-overlay projects-apple-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="project-conversation-picker projects-apple-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={`添加对话到 ${project.name}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="project-picker-header">
          <div>
            <h2>添加对话</h2>
            <p>{project.name}</p>
          </div>
          <button type="button" aria-label="关闭添加对话" onClick={onClose}>
            <X size={18} />
          </button>
        </header>
        <label className="project-picker-search">
          <Search size={15} />
          <input
            autoFocus
            aria-label="搜索可添加的对话"
            placeholder="搜索对话"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="project-picker-list">
          {filteredConversations.length === 0 ? (
            <div className="project-picker-empty">没有可添加的对话</div>
          ) : (
            filteredConversations.map((conversation) => (
              <div className="project-picker-row" key={conversation.id}>
                <MessageCircle size={17} />
                <span>
                  <strong>{conversation.title}</strong>
                  <small>{conversation.summary || conversation.time}</small>
                </span>
                <button disabled={movingConversationId === conversation.id} type="button" onClick={() => onMove(conversation.id)}>
                  {movingConversationId === conversation.id ? '添加中' : '添加'}
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  );
}

function DeleteProjectDialog({
  error,
  project,
  saving,
  onCancel,
  onConfirm,
}: {
  error: string;
  project: CreatedProject | null;
  saving: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  if (!project) return null;

  return createPortal(
    <div className="project-modal-overlay projects-apple-overlay" role="presentation" onMouseDown={onCancel}>
      <section
        className="delete-project-dialog projects-apple-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-project-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <h2 id="delete-project-title">删除项目</h2>
        <p>项目“{project.name}”会被删除，项目内对话会保留并移出项目。</p>
        {error && (
          <p className="delete-project-error" role="alert">
            {error}
          </p>
        )}
        <div className="delete-project-actions">
          <button disabled={saving} type="button" onClick={onCancel}>
            取消
          </button>
          <button className="danger" disabled={saving} type="button" onClick={onConfirm}>
            {saving ? '删除中' : '删除'}
          </button>
        </div>
      </section>
    </div>,
    document.body,
  );
}

function ProjectRow({
  active,
  isMenuOpen,
  isPinned,
  project,
  onOpen,
  onOpenMenu,
  onOpenSettings,
  onRequestArchive,
  onRequestDelete,
  onRowKeyDown,
  onTogglePin,
}: {
  active: boolean;
  isMenuOpen: boolean;
  isPinned: boolean;
  project: CreatedProject;
  onOpen: () => void;
  onOpenMenu: () => void;
  onOpenSettings: () => void;
  onRequestArchive: () => void;
  onRequestDelete: () => void;
  onRowKeyDown: (event: ReactKeyboardEvent<HTMLDivElement>) => void;
  onTogglePin: () => void;
}) {
  return (
    <div
      className={clsx('projects-row', active && 'selected', isPinned && 'pinned')}
      role="row"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={onRowKeyDown}
    >
      <span className="projects-name-cell" role="cell">
        <ProjectIconBadge color={project.color} iconKey={project.iconKey} size="table" />
        <span className="project-name-text">{project.name}</span>
      </span>
      <span className="projects-date-cell" role="cell">
        {project.updatedAt}
      </span>
      <span className={clsx('project-row-actions', isMenuOpen && 'menu-open')} role="cell">
        {isPinned && <Pin className="project-pinned-icon project-pinned-icon-table" size={15} aria-label="已置顶" />}
        <button
          className={clsx('project-row-more', isMenuOpen && 'open')}
          type="button"
          aria-label={`${project.name} 项目操作`}
          aria-haspopup="menu"
          aria-expanded={isMenuOpen}
          onClick={(event) => {
            event.stopPropagation();
            onOpenMenu();
          }}
        >
          <MoreHorizontal size={18} />
        </button>

        {isMenuOpen && (
          <div className="project-row-menu" role="menu" aria-label={`${project.name} 操作`} onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              role="menuitem"
              onClick={(event) => {
                event.stopPropagation();
                onTogglePin();
              }}
            >
              <Pin size={17} />
              <span>{isPinned ? '取消置顶' : '置顶项目'}</span>
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={(event) => {
                event.stopPropagation();
                onOpenSettings();
              }}
            >
              <Settings2 size={17} />
              <span>项目设置</span>
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={(event) => {
                event.stopPropagation();
                onRequestArchive();
              }}
            >
              <Archive size={17} />
              <span>归档项目</span>
            </button>
            <div className="project-row-menu-separator" role="separator" />
            <button
              className="danger"
              type="button"
              role="menuitem"
              onClick={(event) => {
                event.stopPropagation();
                onRequestDelete();
              }}
            >
              <Trash2 size={17} />
              <span>删除项目</span>
            </button>
          </div>
        )}
      </span>
    </div>
  );
}

function ProjectSettingsModal({
  project,
  onClose,
  onDeleteRequest,
  onUpdate,
}: {
  project: CreatedProject | null;
  onClose: () => void;
  onDeleteRequest: (project: CreatedProject) => void;
  onUpdate: (projectId: string, project: ProjectSettingsUpdate) => Promise<CreatedProject>;
}) {
  const [projectName, setProjectName] = useState('');
  const [projectDescription, setProjectDescription] = useState('');
  const [selectedColor, setSelectedColor] = useState<string>(projectColorOptions[0].value);
  const [selectedIconKey, setSelectedIconKey] = useState<ProjectIconKey>('folder');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!project) return;
    setProjectName(project.name);
    setProjectDescription(project.description);
    setSelectedColor(project.color);
    setSelectedIconKey(project.iconKey);
    setPickerOpen(false);
    setStatusMessage('');
    setError('');
  }, [project]);

  if (!project) return null;

  const SelectedIcon = getProjectIconOption(selectedIconKey).icon;
  const buildSettings = (overrides: Partial<ProjectSettingsUpdate> = {}): ProjectSettingsUpdate => ({
    name: overrides.name ?? projectName,
    description: overrides.description ?? projectDescription,
    color: overrides.color ?? selectedColor,
    iconKey: overrides.iconKey ?? selectedIconKey,
  });

  const saveSettings = async (overrides: Partial<ProjectSettingsUpdate> = {}) => {
    const nextSettings = buildSettings(overrides);
    const normalizedName = nextSettings.name.trim();
    if (!normalizedName) {
      setError('项目名称不能为空');
      throw new Error('项目名称不能为空');
    }

    const normalizedSettings = {
      ...nextSettings,
      name: normalizedName,
      description: nextSettings.description.trim(),
    };

    const hasChanges =
      normalizedSettings.name !== project.name ||
      normalizedSettings.description !== project.description ||
      normalizedSettings.color !== project.color ||
      normalizedSettings.iconKey !== project.iconKey;

    if (!hasChanges) return;

    setIsSaving(true);
    setStatusMessage('正在保存...');
    setError('');
    try {
      const savedProject = await onUpdate(project.id, normalizedSettings);
      setProjectName(savedProject.name);
      setProjectDescription(savedProject.description);
      setSelectedColor(savedProject.color);
      setSelectedIconKey(savedProject.iconKey);
      setStatusMessage('已保存');
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : '项目保存失败';
      setError(message);
      setStatusMessage('');
      throw saveError;
    } finally {
      setIsSaving(false);
    }
  };

  const handleClose = async () => {
    try {
      await saveSettings();
      onClose();
    } catch {
      // Keep the dialog open so the user can correct the field.
    }
  };

  const handleColorSelect = (color: string) => {
    setSelectedColor(color);
    void saveSettings({ color });
  };

  const handleIconSelect = (iconKey: ProjectIconKey) => {
    setSelectedIconKey(iconKey);
    void saveSettings({ iconKey });
  };

  return createPortal(
    <div
      className="project-modal-overlay project-settings-overlay projects-apple-overlay"
      role="presentation"
      onMouseDown={() => {
        void handleClose();
      }}
    >
      <section
        className="project-settings-dialog projects-apple-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-settings-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="project-settings-header">
          <h2 id="project-settings-title">项目设置</h2>
          <button
            type="button"
            aria-label="关闭项目设置"
            onClick={() => {
              void handleClose();
            }}
          >
            <X size={18} />
          </button>
        </header>

        <div className="project-settings-body">
          <label className="project-settings-field">
            <span>项目名称</span>
            <div className="project-settings-name-input">
              <button
                className="project-settings-icon-trigger"
                type="button"
                aria-expanded={pickerOpen}
                aria-label="选择项目图标和颜色"
                onClick={() => setPickerOpen((current) => !current)}
                style={getProjectIconStyle(selectedColor)}
              >
                <SelectedIcon size={18} />
              </button>
              <input
                maxLength={64}
                onBlur={() => {
                  void saveSettings();
                }}
                onChange={(event) => {
                  setProjectName(event.target.value);
                  setStatusMessage('');
                  setError('');
                }}
                value={projectName}
              />
              {pickerOpen && (
                <ProjectAppearancePicker
                  selectedColor={selectedColor}
                  selectedIconKey={selectedIconKey}
                  onColorSelect={handleColorSelect}
                  onDone={() => setPickerOpen(false)}
                  onIconSelect={handleIconSelect}
                />
              )}
            </div>
          </label>

          <label className="project-settings-field">
            <span>项目描述</span>
            <small>设置此项目的背景信息和回答方式。</small>
            <textarea
              maxLength={500}
              onBlur={() => {
                void saveSettings();
              }}
              onChange={(event) => {
                setProjectDescription(event.target.value);
                setStatusMessage('');
                setError('');
              }}
              placeholder="例如“用西班牙语回答。参考最新的 JavaScript 文档。回答要简短且突出重点。”"
              value={projectDescription}
            />
          </label>
          {(statusMessage || error) && (
            <p className={clsx('project-settings-message', error && 'error')} role={error ? 'alert' : 'status'}>
              {error || statusMessage}
            </p>
          )}
        </div>

        <button
          className="project-settings-delete"
          disabled={isSaving}
          type="button"
          onClick={() => onDeleteRequest(project)}
        >
          删除项目
        </button>
      </section>
    </div>,
    document.body,
  );
}

function ProjectCreateModal({
  open,
  onClose,
  onCreate,
}: {
  open: boolean;
  onClose: () => void;
  onCreate: (project: Pick<CreatedProject, 'name' | 'color' | 'iconKey'>) => Promise<void> | void;
}) {
  const [projectName, setProjectName] = useState('');
  const [selectedColor, setSelectedColor] = useState<string>(projectColorOptions[0].value);
  const [selectedIconKey, setSelectedIconKey] = useState<ProjectIconKey>('folder');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState('');
  const canCreate = projectName.trim().length > 0 && !isCreating;
  const SelectedIcon = getProjectIconOption(selectedIconKey).icon;

  useEffect(() => {
    if (!open) return;
    setProjectName('');
    setSelectedColor(projectColorOptions[0].value);
    setSelectedIconKey('folder');
    setPickerOpen(false);
    setIsCreating(false);
    setError('');
  }, [open]);

  useEffect(() => {
    if (!open || !pickerOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPickerOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, pickerOpen]);

  if (!open) return null;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canCreate) return;

    setError('');
    setIsCreating(true);
    try {
      await onCreate({
        name: projectName,
        color: selectedColor,
        iconKey: selectedIconKey,
      });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '创建项目失败');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="project-modal-overlay projects-apple-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="project-create-dialog projects-apple-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-create-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="project-create-header">
          <h2 id="project-create-title">创建项目</h2>
          <div className="project-create-tools">
            <button type="button" aria-label="关闭创建项目" onClick={onClose}>
              <X size={18} />
            </button>
          </div>
        </header>

        <form className="project-create-form" onSubmit={handleSubmit}>
          <div className="project-name-field">
            <label htmlFor="project-name-input">项目名称</label>
            <div className="project-name-input">
              <button
                className="project-icon-trigger"
                type="button"
                aria-expanded={pickerOpen}
                aria-label="选择项目图标和颜色"
                onClick={() => setPickerOpen((current) => !current)}
                style={getProjectIconStyle(selectedColor)}
              >
                <SelectedIcon size={18} />
              </button>
              <input
                id="project-name-input"
                autoFocus
                maxLength={64}
                onChange={(event) => setProjectName(event.target.value)}
                placeholder="周末怡恨之旅"
                value={projectName}
              />
              {pickerOpen && (
                <ProjectAppearancePicker
                  selectedColor={selectedColor}
                  selectedIconKey={selectedIconKey}
                  onColorSelect={setSelectedColor}
                  onDone={() => setPickerOpen(false)}
                  onIconSelect={setSelectedIconKey}
                />
              )}
            </div>
          </div>

          <div className="project-create-note">
            <Lightbulb size={18} />
            <p>项目功能可将聊天、文件和自定义指令集中保存，以便用于持续进行的工作，或者单纯用于整理内容，让一切更井然有序。</p>
          </div>

          {error && (
            <p className="project-create-error" role="alert">
              {error}
            </p>
          )}

          <div className="project-create-actions">
            <button className="project-create-submit" disabled={!canCreate} type="submit">
              {isCreating ? '创建中' : '创建项目'}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function ProjectAppearancePicker({
  selectedColor,
  selectedIconKey,
  onColorSelect,
  onDone,
  onIconSelect,
}: {
  selectedColor: string;
  selectedIconKey: ProjectIconKey;
  onColorSelect: (color: string) => void;
  onDone: () => void;
  onIconSelect: (iconKey: ProjectIconKey) => void;
}) {
  return (
    <div className="project-appearance-popover" role="dialog" aria-label="项目外观" onMouseDown={(event) => event.stopPropagation()}>
      <div className="project-color-grid" role="radiogroup" aria-label="项目颜色">
        {projectColorOptions.map((color) => (
          <button
            className={clsx('project-color-option', selectedColor === color.value && 'selected')}
            key={color.value}
            type="button"
            role="radio"
            aria-checked={selectedColor === color.value}
            aria-label={color.label}
            onClick={() => onColorSelect(color.value)}
            style={{ backgroundColor: color.value }}
          />
        ))}
      </div>

      <div className="project-icon-grid" role="radiogroup" aria-label="项目图标">
        {projectIconOptions.map((option) => {
          const Icon = option.icon;
          return (
            <button
              className={clsx('project-icon-option', selectedIconKey === option.key && 'selected')}
              key={option.key}
              type="button"
              role="radio"
              aria-checked={selectedIconKey === option.key}
              aria-label={option.label}
              onClick={() => onIconSelect(option.key)}
            >
              <Icon size={20} />
            </button>
          );
        })}
      </div>

      <div className="project-picker-footer">
        <button type="button" onClick={onDone}>
          完成
        </button>
      </div>
    </div>
  );
}

function ProjectIconBadge({
  color,
  iconKey = 'folder',
  open = false,
  size,
}: {
  color?: string;
  iconKey?: ProjectIconKey;
  open?: boolean;
  size: 'sidebar' | 'table';
}) {
  const option = getProjectIconOption(iconKey);
  const Icon = iconKey === 'folder' && open ? FolderOpen : option.icon;

  return (
    <span className={clsx('project-icon-badge', `project-icon-badge-${size}`)} style={getProjectIconStyle(color)}>
      <Icon size={size === 'table' ? 20 : 16} />
    </span>
  );
}

type DiagnosisConversationShareVariant = 'summary' | 'full-record' | 'expert-review';
type ProjectShareVariant = 'summary' | 'full-record' | 'expert-review';

const diagnosisConversationShareOptions: Array<{
  value: DiagnosisConversationShareVariant;
  label: string;
  note: string;
  actionLabel: string;
  icon: LucideIcon;
}> = [
  {
    value: 'summary',
    label: '会话摘要',
    note: '快速交接当前问诊',
    actionLabel: '导出会话摘要',
    icon: ClipboardList,
  },
  {
    value: 'full-record',
    label: '完整记录',
    note: '保留全部问答过程',
    actionLabel: '导出完整记录',
    icon: FileText,
  },
  {
    value: 'expert-review',
    label: '专家复核',
    note: '给农技专家继续判断',
    actionLabel: '导出复核材料',
    icon: Stethoscope,
  },
];

type ProjectShareConversation = DiagnosisConversation & {
  messages: DiagnosisMessage[];
};

const projectShareOptions: Array<{
  value: ProjectShareVariant;
  label: string;
  note: string;
  actionLabel: string;
  icon: LucideIcon;
}> = [
  {
    value: 'summary',
    label: '项目摘要',
    note: '交接项目概况',
    actionLabel: '导出项目摘要',
    icon: ClipboardList,
  },
  {
    value: 'full-record',
    label: '完整记录',
    note: '保留项目全部问答',
    actionLabel: '导出完整记录',
    icon: FileText,
  },
  {
    value: 'expert-review',
    label: '专家复核',
    note: '给农技专家继续判断',
    actionLabel: '导出复核材料',
    icon: Stethoscope,
  },
];

function formatDiagnosisConversationTranscript(messages: DiagnosisMessage[]) {
  return messages
    .map((message) => {
      const speaker = message.role === 'user' ? '养殖户' : 'CanW 助手';
      return `## ${speaker} · ${message.createdAt}\n\n${message.content.trim()}`;
    })
    .join('\n\n');
}

function buildDiagnosisConversationShareText({
  conversation,
  messages,
  title,
  variant,
}: {
  conversation: DiagnosisConversation | null;
  messages: DiagnosisMessage[];
  title: string;
  variant: DiagnosisConversationShareVariant;
}) {
  const conversationTitle = conversation?.title?.trim() || title || '新问诊';
  const transcript = formatDiagnosisConversationTranscript(messages);
  const userMessages = messages.filter((message) => message.role === 'user');
  const assistantMessages = messages.filter((message) => message.role === 'assistant');
  const latestQuestion = userMessages.at(-1)?.content.trim() || '暂无用户问题';
  const latestAnswer = assistantMessages.at(-1)?.content.trim() || '暂无 AI 回复';
  const latestTime = messages.at(-1)?.createdAt || getCurrentTimeLabel();

  if (variant === 'full-record') {
    return [
      '# CanW 家蚕问诊完整记录',
      '',
      `- 会话：${conversationTitle}`,
      `- 导出时间：${getCurrentTimeLabel()}`,
      `- 对话轮次：${assistantMessages.length}`,
      '',
      '## 对话记录',
      '',
      transcript || '暂无对话内容',
    ].join('\n');
  }

  if (variant === 'expert-review') {
    return [
      '# CanW 家蚕问诊专家复核材料',
      '',
      `- 会话：${conversationTitle}`,
      `- 最近更新时间：${latestTime}`,
      `- 对话轮次：${assistantMessages.length}`,
      '',
      '## 最近一次用户问题',
      '',
      latestQuestion,
      '',
      '## 最近一次 AI 初步回复',
      '',
      latestAnswer,
      '',
      '## 完整上下文',
      '',
      transcript || '暂无对话内容',
      '',
      '## 请专家重点复核',
      '',
      '1. AI 初步判断是否准确；',
      '2. 是否需要补充现场图片、视频、蚕龄、温湿度、发病比例等信息；',
      '3. 临时处置建议是否存在风险或遗漏。',
    ].join('\n');
  }

  return [
    '# CanW 家蚕问诊会话摘要',
    '',
    `- 会话：${conversationTitle}`,
    `- 最近更新时间：${latestTime}`,
    `- 对话轮次：${assistantMessages.length}`,
    '',
    '## 最近问题',
    '',
    compactDiagnosisText(latestQuestion, 160),
    '',
    '## AI 建议摘要',
    '',
    compactDiagnosisText(latestAnswer, 360),
    '',
    '## 交接提醒',
    '',
    '请结合现场情况复核，持续记录发病数量、死亡数量、蚕龄、温湿度、消毒处理和关键图片。',
    ].join('\n');
}

function formatProjectConversationBlock(conversation: ProjectShareConversation, includeTranscript: boolean) {
  const userMessages = conversation.messages.filter((message) => message.role === 'user');
  const assistantMessages = conversation.messages.filter((message) => message.role === 'assistant');
  const latestQuestion = userMessages.at(-1)?.content.trim() || '暂无用户问题';
  const latestAnswer = assistantMessages.at(-1)?.content.trim() || conversation.summary || '暂无 AI 回复';
  const lines = [
    `## ${conversation.title}`,
    '',
    `- 更新时间：${conversation.time || '暂无'}`,
    `- 对话轮次：${assistantMessages.length}`,
    '',
    '### 最近问题',
    '',
    compactDiagnosisText(latestQuestion, 220),
    '',
    '### 最近回复摘要',
    '',
    compactDiagnosisText(latestAnswer, 420),
  ];

  if (includeTranscript) {
    lines.push('', '### 完整问答', '', formatDiagnosisConversationTranscript(conversation.messages) || '暂无对话内容');
  }

  return lines.join('\n');
}

function buildProjectShareText({
  conversations,
  project,
  title,
  variant,
}: {
  conversations: ProjectShareConversation[];
  project: CreatedProject;
  title: string;
  variant: ProjectShareVariant;
}) {
  const projectTitle = project.name?.trim() || title || '未命名项目';
  const conversationCount = conversations.length;
  const totalRounds = conversations.reduce(
    (sum, conversation) => sum + conversation.messages.filter((message) => message.role === 'assistant').length,
    0,
  );
  const latestConversation = conversations[0] ?? null;
  const latestQuestion =
    latestConversation?.messages
      .filter((message) => message.role === 'user')
      .at(-1)
      ?.content.trim() || '暂无最近问题';
  const latestAnswer =
    latestConversation?.messages
      .filter((message) => message.role === 'assistant')
      .at(-1)
      ?.content.trim() || '暂无最近回复';
  const conversationList = conversations.length
    ? conversations
        .map((conversation, index) => {
          const assistantCount = conversation.messages.filter((message) => message.role === 'assistant').length;
          return `${index + 1}. ${conversation.title}（${conversation.time || '暂无时间'}，${assistantCount} 轮）`;
        })
        .join('\n')
    : '暂无项目内对话';

  if (variant === 'full-record') {
    return [
      '# CanW 家蚕问诊项目完整记录',
      '',
      `- 项目：${projectTitle}`,
      `- 导出时间：${getCurrentTimeLabel()}`,
      `- 对话数量：${conversationCount}`,
      `- 对话轮次：${totalRounds}`,
      '',
      '## 项目说明',
      '',
      project.description?.trim() || '暂无项目说明',
      '',
      '## 对话目录',
      '',
      conversationList,
      '',
      '## 完整记录',
      '',
      conversations.map((conversation) => formatProjectConversationBlock(conversation, true)).join('\n\n---\n\n') || '暂无对话内容',
    ].join('\n');
  }

  if (variant === 'expert-review') {
    return [
      '# CanW 家蚕问诊项目专家复核材料',
      '',
      `- 项目：${projectTitle}`,
      `- 最近更新时间：${latestConversation?.time || '暂无'}`,
      `- 对话数量：${conversationCount}`,
      `- 对话轮次：${totalRounds}`,
      '',
      '## 项目说明',
      '',
      project.description?.trim() || '暂无项目说明',
      '',
      '## 最近一次问题',
      '',
      latestQuestion,
      '',
      '## 最近一次 AI 初步回复',
      '',
      latestAnswer,
      '',
      '## 项目内对话概览',
      '',
      conversations.map((conversation) => formatProjectConversationBlock(conversation, false)).join('\n\n---\n\n') || '暂无对话内容',
      '',
      '## 请专家重点复核',
      '',
      '1. 项目内多个问诊之间是否存在共同病因或传播风险；',
      '2. AI 初步判断和临时处置建议是否需要修正；',
      '3. 是否需要补充现场图片、视频、蚕龄、温湿度、发病比例等信息。',
    ].join('\n');
  }

  return [
    '# CanW 家蚕问诊项目摘要',
    '',
    `- 项目：${projectTitle}`,
    `- 导出时间：${getCurrentTimeLabel()}`,
    `- 对话数量：${conversationCount}`,
    `- 对话轮次：${totalRounds}`,
    '',
    '## 项目说明',
    '',
    project.description?.trim() || '暂无项目说明',
    '',
    '## 对话列表',
    '',
    conversationList,
    '',
    '## 最近问题',
    '',
    compactDiagnosisText(latestQuestion, 180),
    '',
    '## 最近回复摘要',
    '',
    compactDiagnosisText(latestAnswer, 420),
    '',
    '## 交接提醒',
    '',
    '请结合项目内所有会话复核，持续记录发病数量、死亡数量、蚕龄、温湿度、消毒处理和关键图片。',
  ].join('\n');
}

function DiagnosisConversationShareDialog({
  conversation,
  messages,
  onCancel,
  onCreateCommunityDraft,
  onCreatePublicShare,
  onNotify,
  title,
}: {
  conversation: DiagnosisConversation | null;
  messages: DiagnosisMessage[];
  title: string;
  onCancel: () => void;
  onCreateCommunityDraft: (conversationId: string, attachmentIds: string[]) => Promise<void>;
  onCreatePublicShare: (
    conversationId: string,
    payload: DiagnosisConversationPublicSharePayload,
  ) => Promise<ApiDiagnosisConversationShareResponse>;
  onNotify: (message: string, tone?: ToastTone) => void;
}) {
  const [selectedVariant, setSelectedVariant] = useState<DiagnosisConversationShareVariant>('summary');
  const [exportedVariant, setExportedVariant] = useState<DiagnosisConversationShareVariant | null>(null);
  const [linkedVariant, setLinkedVariant] = useState<DiagnosisConversationShareVariant | null>(null);
  const [publicShareUrl, setPublicShareUrl] = useState('');
  const [exporting, setExporting] = useState(false);
  const [linkCreating, setLinkCreating] = useState(false);
  const [communityDrafting, setCommunityDrafting] = useState(false);
  const exportTimerRef = useRef<number | null>(null);
  const linkTimerRef = useRef<number | null>(null);
  const busy = exporting || linkCreating || communityDrafting;
  const selectedOption =
    diagnosisConversationShareOptions.find((option) => option.value === selectedVariant) ?? diagnosisConversationShareOptions[0];
  const shareText = buildDiagnosisConversationShareText({
    conversation,
    messages,
    title,
    variant: selectedVariant,
  });
  const exportBaseName = toSafeMarkdownFileName(
    `CanW-${conversation?.title?.trim() || title || '问诊记录'}-${selectedOption.label}`,
  );

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCancel();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (exportTimerRef.current !== null) {
        window.clearTimeout(exportTimerRef.current);
      }
      if (linkTimerRef.current !== null) {
        window.clearTimeout(linkTimerRef.current);
      }
    };
  }, [busy, onCancel]);

  const exportMarkdown = () => {
    if (busy) return;

    setExporting(true);
    try {
      downloadMarkdownFile(exportBaseName, shareText);
      setExportedVariant(selectedVariant);
      if (exportTimerRef.current !== null) {
        window.clearTimeout(exportTimerRef.current);
      }
      exportTimerRef.current = window.setTimeout(() => {
        setExportedVariant(null);
        exportTimerRef.current = null;
      }, 1800);
    } catch {
      onNotify('Markdown 导出失败，请稍后再试', 'error');
    } finally {
      setExporting(false);
    }
  };

  const schedulePublicLinkReset = (delayMs = 1800) => {
    if (linkTimerRef.current !== null) {
      window.clearTimeout(linkTimerRef.current);
    }
    linkTimerRef.current = window.setTimeout(() => {
      setLinkedVariant(null);
      setPublicShareUrl('');
      linkTimerRef.current = null;
    }, delayMs);
  };

  const createPublicLink = async () => {
    if (busy || !conversation) return;

    setLinkCreating(true);
    try {
      const response = await onCreatePublicShare(conversation.id, {
        title: conversation.title?.trim() || title || 'CanW 问诊分享',
        variant: selectedVariant,
        contentMarkdown: shareText,
      });
      setPublicShareUrl(response.share_url);
      try {
        await copyTextToClipboard(response.share_url);
        setLinkedVariant(selectedVariant);
        onNotify('分享链接已复制', 'success');
        schedulePublicLinkReset();
      } catch {
        onNotify('链接已生成，请手动复制', 'info');
        schedulePublicLinkReset(5000);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '请稍后再试';
      onNotify(`分享链接生成失败：${message}`, 'error');
    } finally {
      setLinkCreating(false);
    }
  };

  const createCommunityDraft = async () => {
    if (busy || !conversation) return;
    setCommunityDrafting(true);
    try {
      const attachmentIds = Array.from(
        new Set(messages.flatMap((message) => message.attachments?.map((attachment) => attachment.id) ?? [])),
      );
      await onCreateCommunityDraft(conversation.id, attachmentIds);
    } finally {
      setCommunityDrafting(false);
    }
  };

  return createPortal(
    <div
      className="message-feedback-overlay diagnosis-share-overlay"
      role="presentation"
      onMouseDown={() => {
        if (!busy) onCancel();
      }}
    >
      <section
        className="diagnosis-share-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="diagnosis-conversation-share-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="diagnosis-share-header">
          <div>
            <h2 id="diagnosis-conversation-share-title">分享聊天</h2>
            <p>导出 Markdown 文件，或生成一份可公开访问的会话快照链接。</p>
          </div>
          <button type="button" aria-label="关闭分享" disabled={busy} onClick={onCancel}>
            <X size={19} />
          </button>
        </div>

        <div className="diagnosis-share-options" role="tablist" aria-label="分享聊天用途">
          {diagnosisConversationShareOptions.map((option) => {
            const OptionIcon = option.icon;
            const selected = selectedVariant === option.value;
            return (
              <button
                className={clsx(selected && 'selected')}
                key={option.value}
                type="button"
                role="tab"
                aria-selected={selected}
                disabled={busy}
                onClick={() => setSelectedVariant(option.value)}
              >
                <OptionIcon size={17} />
                <span>{option.label}</span>
                <small>{option.note}</small>
              </button>
            );
          })}
        </div>

        <div className="diagnosis-share-preview" aria-label="分享聊天内容预览">
          <pre>{shareText}</pre>
        </div>

        {publicShareUrl && (
          <button
            className="diagnosis-share-url"
            type="button"
            disabled={busy}
            title={publicShareUrl}
            onClick={() => {
              void copyTextToClipboard(publicShareUrl)
                .then(() => onNotify('分享链接已复制', 'success'))
                .catch(() => onNotify('复制链接失败，请手动复制', 'error'));
            }}
          >
            <Link2 size={15} />
            <span>{publicShareUrl}</span>
          </button>
        )}

        <div className="diagnosis-share-actions">
          <button className="diagnosis-share-secondary" type="button" disabled={busy} onClick={onCancel}>
            取消
          </button>
          <button
            className="diagnosis-share-link"
            type="button"
            disabled={busy || !conversation}
            onClick={() => void createPublicLink()}
          >
            {linkedVariant === selectedVariant ? <Check size={16} /> : <Link2 size={16} />}
            <span>{linkedVariant === selectedVariant ? '链接已复制' : linkCreating ? '生成中' : '生成链接'}</span>
          </button>
          <button
            className="diagnosis-share-community"
            type="button"
            disabled={busy || !conversation}
            onClick={() => void createCommunityDraft()}
          >
            <Globe size={16} />
            <span>{communityDrafting ? '正在生成草稿' : '发布到社区'}</span>
          </button>
          <button className="diagnosis-share-primary" type="button" disabled={busy} onClick={exportMarkdown}>
            {exportedVariant === selectedVariant ? <Check size={16} /> : <Download size={16} />}
            <span>{exportedVariant === selectedVariant ? '已导出' : selectedOption.actionLabel}</span>
          </button>
        </div>
      </section>
    </div>,
    document.body,
  );
}

function ProjectShareDialog({
  conversations,
  onCancel,
  onCreatePublicShare,
  onNotify,
  project,
}: {
  conversations: ProjectShareConversation[];
  project: CreatedProject;
  onCancel: () => void;
  onCreatePublicShare: (projectId: string, payload: ProjectPublicSharePayload) => Promise<ApiProjectShareResponse>;
  onNotify: (message: string, tone?: ToastTone) => void;
}) {
  const [selectedVariant, setSelectedVariant] = useState<ProjectShareVariant>('summary');
  const [exportedVariant, setExportedVariant] = useState<ProjectShareVariant | null>(null);
  const [linkedVariant, setLinkedVariant] = useState<ProjectShareVariant | null>(null);
  const [publicShareUrl, setPublicShareUrl] = useState('');
  const [exporting, setExporting] = useState(false);
  const [linkCreating, setLinkCreating] = useState(false);
  const exportTimerRef = useRef<number | null>(null);
  const linkTimerRef = useRef<number | null>(null);
  const busy = exporting || linkCreating;
  const selectedOption = projectShareOptions.find((option) => option.value === selectedVariant) ?? projectShareOptions[0];
  const shareText = buildProjectShareText({
    conversations,
    project,
    title: project.name,
    variant: selectedVariant,
  });
  const exportBaseName = toSafeMarkdownFileName(`CanW-${project.name || '项目'}-${selectedOption.label}`);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCancel();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (exportTimerRef.current !== null) {
        window.clearTimeout(exportTimerRef.current);
      }
      if (linkTimerRef.current !== null) {
        window.clearTimeout(linkTimerRef.current);
      }
    };
  }, [busy, onCancel]);

  const exportMarkdown = () => {
    if (busy) return;

    setExporting(true);
    try {
      downloadMarkdownFile(exportBaseName, shareText);
      setExportedVariant(selectedVariant);
      if (exportTimerRef.current !== null) {
        window.clearTimeout(exportTimerRef.current);
      }
      exportTimerRef.current = window.setTimeout(() => {
        setExportedVariant(null);
        exportTimerRef.current = null;
      }, 1800);
    } catch {
      onNotify('Markdown 导出失败，请稍后再试', 'error');
    } finally {
      setExporting(false);
    }
  };

  const schedulePublicLinkReset = (delayMs = 1800) => {
    if (linkTimerRef.current !== null) {
      window.clearTimeout(linkTimerRef.current);
    }
    linkTimerRef.current = window.setTimeout(() => {
      setLinkedVariant(null);
      setPublicShareUrl('');
      linkTimerRef.current = null;
    }, delayMs);
  };

  const createPublicLink = async () => {
    if (busy) return;

    setLinkCreating(true);
    try {
      const response = await onCreatePublicShare(project.id, {
        title: project.name?.trim() || 'CanW 项目分享',
        variant: selectedVariant,
        contentMarkdown: shareText,
      });
      setPublicShareUrl(response.share_url);
      try {
        await copyTextToClipboard(response.share_url);
        setLinkedVariant(selectedVariant);
        onNotify('项目分享链接已复制', 'success');
        schedulePublicLinkReset();
      } catch {
        onNotify('链接已生成，请手动复制', 'info');
        schedulePublicLinkReset(5000);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '请稍后再试';
      onNotify(`项目分享链接生成失败：${message}`, 'error');
    } finally {
      setLinkCreating(false);
    }
  };

  return (
    <div
      className="message-feedback-overlay diagnosis-share-overlay"
      role="presentation"
      onMouseDown={() => {
        if (!busy) onCancel();
      }}
    >
      <section
        className="diagnosis-share-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-share-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="diagnosis-share-header">
          <div>
            <h2 id="project-share-title">分享项目</h2>
            <p>把项目内问诊整理成可交接、可复核、可归档的 Markdown 快照。</p>
          </div>
          <button type="button" aria-label="关闭项目分享" disabled={busy} onClick={onCancel}>
            <X size={19} />
          </button>
        </div>

        <div className="diagnosis-share-options" role="tablist" aria-label="分享项目用途">
          {projectShareOptions.map((option) => {
            const OptionIcon = option.icon;
            const selected = selectedVariant === option.value;
            return (
              <button
                className={clsx(selected && 'selected')}
                key={option.value}
                type="button"
                role="tab"
                aria-selected={selected}
                disabled={busy}
                onClick={() => setSelectedVariant(option.value)}
              >
                <OptionIcon size={17} />
                <span>{option.label}</span>
                <small>{option.note}</small>
              </button>
            );
          })}
        </div>

        <div className="diagnosis-share-preview" aria-label="分享项目内容预览">
          <pre>{shareText}</pre>
        </div>

        {publicShareUrl && (
          <button
            className="diagnosis-share-url"
            type="button"
            disabled={busy}
            title={publicShareUrl}
            onClick={() => {
              void copyTextToClipboard(publicShareUrl)
                .then(() => onNotify('项目分享链接已复制', 'success'))
                .catch(() => onNotify('复制链接失败，请手动复制', 'error'));
            }}
          >
            <Link2 size={15} />
            <span>{publicShareUrl}</span>
          </button>
        )}

        <div className="diagnosis-share-actions">
          <button className="diagnosis-share-secondary" type="button" disabled={busy} onClick={onCancel}>
            取消
          </button>
          <button className="diagnosis-share-link" type="button" disabled={busy} onClick={() => void createPublicLink()}>
            {linkedVariant === selectedVariant ? <Check size={16} /> : <Link2 size={16} />}
            <span>{linkedVariant === selectedVariant ? '链接已复制' : linkCreating ? '生成中' : '生成链接'}</span>
          </button>
          <button className="diagnosis-share-primary" type="button" disabled={busy} onClick={exportMarkdown}>
            {exportedVariant === selectedVariant ? <Check size={16} /> : <Download size={16} />}
            <span>{exportedVariant === selectedVariant ? '已导出' : selectedOption.actionLabel}</span>
          </button>
        </div>
      </section>
    </div>
  );
}

function ThreadHeader({
  title,
  conversationMenu,
  icon: HeaderIcon = Bot,
}: {
  title: string;
  conversationMenu?: HeaderConversationMenuConfig;
  icon?: LucideIcon;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [renameSaving, setRenameSaving] = useState(false);
  const [renameError, setRenameError] = useState('');
  const [moveSaving, setMoveSaving] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const conversation = conversationMenu?.conversation ?? null;
  const headerMenuAvailable = Boolean(conversationMenu);
  const conversationActionsEnabled = Boolean(conversation && conversationMenu);
  const conversationProjectName =
    conversation?.projectId && conversationMenu
      ? conversationMenu.projects.find((project) => project.id === conversation.projectId)?.name ?? '当前项目'
      : null;

  useEffect(() => {
    if (!menuOpen) return undefined;

    const handlePointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMenuOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [menuOpen]);

  const closeMenu = () => setMenuOpen(false);

  const handleConversationShareOpen = () => {
    closeMenu();
    if (!conversationMenu) return;
    setShareDialogOpen(true);
  };

  const handleSaveAsCase = () => {
    if (!conversation || !conversationMenu) return;
    closeMenu();
    conversationMenu.onSaveAsCase(conversation.id);
  };

  const handleRenameOpen = () => {
    if (!conversation) return;
    setRenameError('');
    setRenameDialogOpen(true);
    closeMenu();
  };

  const handleRenameConfirm = async (nextTitle: string) => {
    if (!conversation || !conversationMenu || renameSaving) return;

    setRenameSaving(true);
    setRenameError('');
    try {
      await conversationMenu.onRename(conversation.id, nextTitle);
      setRenameDialogOpen(false);
    } catch {
      setRenameError('重命名失败，请稍后再试。');
    } finally {
      setRenameSaving(false);
    }
  };

  const handleDelete = () => {
    if (!conversation || !conversationMenu) return;
    closeMenu();
    conversationMenu.onDelete(conversation);
  };

  const handleArchive = () => {
    if (!conversation || !conversationMenu) return;
    closeMenu();
    conversationMenu.onArchive(conversation.id);
  };

  const handleMoveProject = async (projectId: string | null) => {
    if (!conversation || !conversationMenu || moveSaving) return;

    setMoveSaving(true);
    try {
      await conversationMenu.onMoveProject(conversation.id, projectId);
      closeMenu();
    } catch {
      // The parent move handler already shows the failure toast.
    } finally {
      setMoveSaving(false);
    }
  };

  const handleCreateProjectForMove = () => {
    if (!conversation || !conversationMenu) return;
    closeMenu();
    conversationMenu.onCreateProjectForMove(conversation.id);
  };

  return (
    <header className="thread-header">
        <div className="thread-title">
          <div className="doc-icon">
          <HeaderIcon size={17} />
        </div>
        <strong>{title}</strong>
      </div>
      <div className="header-actions">
        {conversationMenu && conversation && (
          <button className="header-share-button" type="button" aria-label="存为病例" onClick={handleSaveAsCase}>
            <ClipboardList size={16} />
            <span>存为病例</span>
          </button>
        )}
        {conversationMenu ? (
          <button className="header-share-button" type="button" aria-label="分享" onClick={handleConversationShareOpen}>
            <Upload size={16} />
            <span>分享</span>
          </button>
        ) : (
          <button type="button" aria-label="上传资料">
            <Upload size={16} />
          </button>
        )}
        <div className={clsx('header-more-menu-wrap', menuOpen && 'open')} ref={menuRef}>
          <button
            type="button"
            aria-label="更多"
            aria-expanded={menuOpen}
            aria-haspopup="menu"
            onClick={() => {
              if (!headerMenuAvailable) return;
              setMenuOpen((open) => !open);
            }}
          >
            <MoreHorizontal size={18} />
          </button>
          {menuOpen && conversationMenu && (
            <div
              className={clsx('thread-context-menu header-context-menu', conversationProjectName && 'has-project-remove')}
              role="menu"
              aria-label="聊天操作"
            >
              <button type="button" role="menuitem" onClick={handleConversationShareOpen}>
                <Upload size={16} />
                <span>分享</span>
              </button>
              <button type="button" role="menuitem" disabled={!conversationActionsEnabled} onClick={handleSaveAsCase}>
                <ClipboardList size={16} />
                <span>存为病例</span>
              </button>
              <button type="button" role="menuitem" disabled={!conversationActionsEnabled} onClick={handleRenameOpen}>
                <PencilLine size={16} />
                <span>重命名</span>
              </button>
              <div className="thread-menu-submenu-wrap">
                <button
                  className="thread-menu-submenu-trigger"
                  type="button"
                  role="menuitem"
                  aria-haspopup="menu"
                  aria-expanded="true"
                  disabled={!conversationActionsEnabled}
                >
                  <Folder size={16} />
                  <span>移至项目</span>
                  <ChevronRight className="thread-menu-chevron" size={15} />
                </button>
                {conversationActionsEnabled && (
                  <ProjectMoveSubmenu
                    currentProjectId={conversation?.projectId ?? null}
                    moving={moveSaving}
                    projects={conversationMenu.projects}
                    onCreateProject={handleCreateProjectForMove}
                    onMoveProject={(projectId) => {
                      void handleMoveProject(projectId);
                    }}
                  />
                )}
              </div>
              {conversationProjectName && (
                <button
                  type="button"
                  role="menuitem"
                  disabled={!conversationActionsEnabled || moveSaving}
                  onClick={() => {
                    void handleMoveProject(null);
                  }}
                >
                  <FolderX size={16} />
                  <span>从「{conversationProjectName}」移除</span>
                </button>
              )}
              <div className="thread-menu-separator" />
              <button type="button" role="menuitem" disabled={!conversationActionsEnabled} onClick={handleArchive}>
                <Archive size={16} />
                <span>归档</span>
              </button>
              <button className="danger" type="button" role="menuitem" disabled={!conversationActionsEnabled} onClick={handleDelete}>
                <Trash2 size={16} />
                <span>删除</span>
              </button>
            </div>
          )}
        </div>
      </div>
      {renameDialogOpen && conversation && (
        <RenameConversationDialog
          conversation={conversation}
          error={renameError}
          saving={renameSaving}
          onCancel={() => {
            if (!renameSaving) setRenameDialogOpen(false);
          }}
          onConfirm={handleRenameConfirm}
        />
      )}
      {shareDialogOpen && conversationMenu && (
        <DiagnosisConversationShareDialog
          conversation={conversation}
          messages={conversationMenu.messages}
          title={title}
          onCancel={() => setShareDialogOpen(false)}
          onCreateCommunityDraft={conversationMenu.onCreateCommunityDraft}
          onCreatePublicShare={conversationMenu.onCreatePublicShare}
          onNotify={conversationMenu.onNotify}
        />
      )}
    </header>
  );
}

function DiagnosisThread({
  activeConversation,
  configuredModels,
  expertReviews,
  isSending,
  messages,
  projects,
  selectedModelConfigId,
  userPreferences,
  onConversationArchive,
  onConversationDelete,
  onConversationMoveToProject,
  onConversationCommunityDraft,
  onConversationPublicShare,
  onConversationRename,
  onConversationSaveAsCase,
  onMessageDelete,
  onMessageEdit,
  onMessageFeedback,
  onMessageRegenerate,
  onModelSelect,
  onNotify,
  onOpenProjectCreateForMove,
  onAudioTranscribe,
  onAttachmentUpload,
  onAttachmentDelete,
  onSubmit,
}: {
  activeConversation: DiagnosisConversation | null;
  configuredModels: ConfiguredModel[];
  expertReviews: ApiDiagnosisExpertReview[];
  isSending: boolean;
  messages: DiagnosisMessage[];
  projects: CreatedProject[];
  selectedModelConfigId: string | null;
  userPreferences: UserPreferences;
  onConversationArchive: (conversationId: string) => void;
  onConversationDelete: (conversation: DiagnosisConversation) => void;
  onConversationMoveToProject: (conversationId: string, projectId: string | null) => Promise<DiagnosisConversation>;
  onConversationCommunityDraft: (conversationId: string, attachmentIds: string[]) => Promise<void>;
  onConversationPublicShare: (
    conversationId: string,
    payload: DiagnosisConversationPublicSharePayload,
  ) => Promise<ApiDiagnosisConversationShareResponse>;
  onConversationRename: (conversationId: string, title: string) => Promise<void>;
  onConversationSaveAsCase: (conversationId: string) => void;
  onMessageDelete: (messageId: string) => Promise<void>;
  onMessageEdit: (messageId: string, content: string) => Promise<void>;
  onMessageFeedback: (
    messageId: string,
    feedback: 'like' | 'dislike' | null,
    feedbackReasons?: string[],
    feedbackDetail?: string | null,
  ) => Promise<void>;
  onMessageRegenerate: (messageId: string) => Promise<void>;
  onModelSelect: (modelConfigId: string | null) => void;
  onNotify: (message: string, tone?: ToastTone) => void;
  onOpenProjectCreateForMove: (conversationId: string) => void;
  onAudioTranscribe: (audio: File) => Promise<string>;
  onAttachmentUpload: (attachment: File) => Promise<ApiDiagnosisFileResponse>;
  onAttachmentDelete: (fileId: string) => Promise<void>;
  onSubmit: (
    question: string,
    projectId?: string | null,
    options?: DiagnosisSubmitOptions,
  ) => Promise<void>;
}) {
  const [draft, setDraft] = useState('');
  const chatScrollRef = useRef<HTMLDivElement>(null);
  const canSend = !isSending;

  const submitDraft = (options: DiagnosisSubmitOptions = {}) => {
    const question = draft.trim();
    const attachmentIds = options.attachmentIds ?? [];
    const structuredData = options.structuredData ?? null;
    const hasStructuredData = Boolean(structuredData && Object.keys(structuredData).length > 0);
    if ((!question && attachmentIds.length === 0 && !hasStructuredData) || isSending) return;

    setDraft('');
    void onSubmit(question, null, options);
  };

  useEffect(() => {
    if (!messages.length && !isSending) return;
    chatScrollRef.current?.scrollTo({
      top: chatScrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [isSending, messages.length]);

  if (messages.length > 0) {
    return (
      <section className="diagnosis-chat-page" aria-label="新问诊对话">
        <ThreadHeader
          title={activeConversation?.title?.trim() || '新对话'}
          icon={MessageCircle}
          conversationMenu={{
            conversation: activeConversation,
            messages,
            projects,
            onCreateProjectForMove: onOpenProjectCreateForMove,
            onCreateCommunityDraft: onConversationCommunityDraft,
            onCreatePublicShare: onConversationPublicShare,
            onArchive: onConversationArchive,
            onDelete: onConversationDelete,
            onMoveProject: onConversationMoveToProject,
            onNotify,
            onRename: onConversationRename,
            onSaveAsCase: onConversationSaveAsCase,
          }}
        />
        <div className="diagnosis-chat-scroll" ref={chatScrollRef}>
          <article className="diagnosis-conversation">
            {userPreferences.show_model_status && <div className="diagnosis-simulated-banner" role="status">
              <Sparkles size={17} />
              <div>
                <strong>大模型问诊中</strong>
                <span>当前由后端调用模型回答；后续 RAG + KG 会接入同一个问诊入口。</span>
              </div>
            </div>}
            {expertReviews.length > 0 && <DiagnosisExpertReviewPanel reviews={expertReviews} />}
            {messages.map((message, messageIndex) => {
              const sourceQuestion =
                message.role === 'assistant'
                  ? messages
                      .slice(0, messageIndex)
                      .reverse()
                      .find((previousMessage) => previousMessage.role === 'user')?.content ?? null
                  : null;

              return (
                <DiagnosisMessageBubble
                  key={message.id}
                  message={message}
                  sourceQuestion={sourceQuestion}
                  onDelete={onMessageDelete}
                  onEdit={onMessageEdit}
                  onFeedback={onMessageFeedback}
                  onNotify={onNotify}
                  onRegenerate={onMessageRegenerate}
                />
              );
            })}
            {isSending && (
              <div className="diagnosis-thinking" role="status">
                <div className="diagnosis-message-avatar">
                  <Bot size={17} />
                </div>
                <div className="diagnosis-thinking-body">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
          </article>
        </div>
        <DiagnosisComposer
          className="diagnosis-chat-composer"
          configuredModels={configuredModels}
          draft={draft}
          isSending={isSending}
          onChange={setDraft}
          onAudioTranscribe={onAudioTranscribe}
          onAttachmentUpload={onAttachmentUpload}
          onAttachmentDelete={onAttachmentDelete}
          onModelSelect={onModelSelect}
          panelPlacement="up"
          onSubmit={submitDraft}
          selectedModelConfigId={selectedModelConfigId}
          sendDisabled={!canSend || isSending}
          uploadPreferences={userPreferences}
        />
      </section>
    );
  }

  return (
    <section className="diagnosis-start-page" aria-label="新问诊">
      <button className="diagnosis-corner-action" type="button" aria-label="展开新问诊页面">
        <span />
      </button>

      <div className="diagnosis-start-center">
        <h1>我们先从哪里开始呢?</h1>
        <DiagnosisComposer
          className="diagnosis-start-composer"
          configuredModels={configuredModels}
          draft={draft}
          isSending={isSending}
          onChange={setDraft}
          onAudioTranscribe={onAudioTranscribe}
          onAttachmentUpload={onAttachmentUpload}
          onAttachmentDelete={onAttachmentDelete}
          onModelSelect={onModelSelect}
          panelPlacement="down"
          onSubmit={submitDraft}
          selectedModelConfigId={selectedModelConfigId}
          sendDisabled={!canSend || isSending}
          uploadPreferences={userPreferences}
        />
      </div>
    </section>
  );
}

type ComposerAttachmentKind = 'image' | 'video' | 'audio' | 'document' | 'data';
type ComposerFileAttachmentKind = Extract<ComposerAttachmentKind, 'image' | 'video' | 'document'>;
type ComposerPanelPlacement = 'up' | 'down';

type ComposerAttachmentDraft = {
  id: string;
  kind: ComposerAttachmentKind;
  name: string;
  detail: string;
  structuredData?: Record<string, unknown>;
  file?: File;
  previewUrl?: string;
  uploadStatus?: 'preparing' | 'uploading' | 'ready' | 'error';
  uploadedAttachment?: ApiDiagnosisFileResponse;
  uploadError?: string;
};

type VoiceCaptureState = 'idle' | 'recording' | 'transcribing';

const composerAttachmentMeta: Record<ComposerAttachmentKind, { label: string; icon: LucideIcon }> = {
  image: { label: '图片', icon: ImageUp },
  video: { label: '视频', icon: Video },
  audio: { label: '语音', icon: Mic },
  document: { label: '资料', icon: FileText },
  data: { label: '养殖数据', icon: Database },
};

const multimodalComposerTools: Array<{
  key: 'files';
  label: string;
  note: string;
  icon: LucideIcon;
}> = [
  { key: 'files', label: '添加照片和文件', note: '自动识别图片、视频、文档', icon: Paperclip },
];

const documentAttachmentExtensions = [
  '.pdf',
  '.doc',
  '.docx',
  '.ppt',
  '.pptx',
  '.xls',
  '.xlsx',
  '.csv',
  '.txt',
  '.md',
  '.markdown',
  '.json',
  '.xml',
  '.html',
  '.htm',
  '.rtf',
  '.log',
];
const documentAttachmentAccept = [
  ...documentAttachmentExtensions,
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.ms-powerpoint',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/json',
  'application/rtf',
  'application/xml',
  'text/*',
].join(',');
const multimodalAttachmentAccept = ['image/*', 'video/*', documentAttachmentAccept].join(',');

function DiagnosisExpertReviewPanel({ reviews }: { reviews: ApiDiagnosisExpertReview[] }) {
  const latest = reviews[0];
  const riskLabels: Record<ApiDiagnosisExpertReview['risk_level'], string> = {
    low: '低风险',
    medium: '需关注',
    high: '高风险',
    critical: '紧急',
  };

  return (
    <section className={`diagnosis-expert-review risk-${latest.risk_level}`} aria-label="专家复核意见">
      <header>
        <div><ShieldCheck size={17} /><span>专家复核意见</span></div>
        <strong>{riskLabels[latest.risk_level]}</strong>
      </header>
      <div className="diagnosis-expert-review-body">
        <p><b>复核结论：</b>{latest.conclusion}</p>
        <p><b>后续建议：</b>{latest.recommendation}</p>
        {latest.evidence.length > 0 && <small>已附 {latest.evidence.length} 条复核依据</small>}
      </div>
      <footer><span>{latest.reviewer_name}</span><span>{formatSettingsDateTime(latest.published_at)}</span>{reviews.length > 1 && <span>历史版本 {reviews.length}</span>}</footer>
    </section>
  );
}

function DiagnosisComposer({
  className,
  configuredModels,
  draft,
  isSending,
  onChange,
  onAudioTranscribe,
  onAttachmentUpload,
  onAttachmentDelete,
  onModelSelect,
  panelPlacement = 'up',
  onSubmit,
  placeholder = '描述症状、上传视频，或继续追问',
  selectedModelConfigId,
  sendDisabled,
  uploadPreferences = defaultUserPreferences,
}: {
  className: string;
  configuredModels: ConfiguredModel[];
  draft: string;
  isSending: boolean;
  onChange: (value: string) => void;
  onAudioTranscribe: (audio: File) => Promise<string>;
  onAttachmentUpload: (attachment: File) => Promise<ApiDiagnosisFileResponse>;
  onAttachmentDelete: (fileId: string) => Promise<void>;
  onModelSelect: (modelConfigId: string | null) => void;
  panelPlacement?: ComposerPanelPlacement;
  onSubmit: (options?: DiagnosisSubmitOptions) => void;
  placeholder?: string;
  selectedModelConfigId: string | null;
  sendDisabled: boolean;
  uploadPreferences?: UserPreferences;
}) {
  const [multimodalOpen, setMultimodalOpen] = useState(false);
  const [farmingDataOpen, setFarmingDataOpen] = useState(false);
  const [attachmentDrafts, setAttachmentDrafts] = useState<ComposerAttachmentDraft[]>([]);
  const [attachmentUploadCount, setAttachmentUploadCount] = useState(0);
  const [voiceState, setVoiceState] = useState<VoiceCaptureState>('idle');
  const [voiceSeconds, setVoiceSeconds] = useState(0);
  const [voiceError, setVoiceError] = useState('');
  const composerRef = useRef<HTMLFormElement | null>(null);
  const materialInputRef = useRef<HTMLInputElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  const videoInputRef = useRef<HTMLInputElement | null>(null);
  const documentInputRef = useRef<HTMLInputElement | null>(null);
  const attachmentDraftsRef = useRef<ComposerAttachmentDraft[]>([]);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const voiceStreamRef = useRef<MediaStream | null>(null);
  const voiceChunksRef = useRef<Blob[]>([]);
  const voiceTimerRef = useRef<number | null>(null);
  const draftRef = useRef(draft);
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const speechTranscriptRef = useRef('');
  const voiceModeRef = useRef<BrowserSpeechRecognitionMode>(null);
  const removedAttachmentDraftIdsRef = useRef(new Set<string>());
  const isUploadingAttachments = attachmentUploadCount > 0;

  useEffect(() => {
    attachmentDraftsRef.current = attachmentDrafts;
  }, [attachmentDrafts]);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    return () => {
      attachmentDraftsRef.current.forEach((attachment) => {
        if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
      });
      if (voiceTimerRef.current !== null) {
        window.clearInterval(voiceTimerRef.current);
      }
      speechRecognitionRef.current?.abort();
      voiceStreamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  useEffect(() => {
    if (!multimodalOpen) return undefined;

    const handlePointerDown = (event: PointerEvent) => {
      if (!composerRef.current?.contains(event.target as Node)) {
        setMultimodalOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMultimodalOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [multimodalOpen]);

  const removeAttachmentDraft = (attachmentId: string) => {
    const removedAttachment = attachmentDraftsRef.current.find((attachment) => attachment.id === attachmentId);
    removedAttachmentDraftIdsRef.current.add(attachmentId);
    setAttachmentDrafts((currentDrafts) => {
      const currentAttachment = currentDrafts.find((attachment) => attachment.id === attachmentId);
      if (currentAttachment?.previewUrl) URL.revokeObjectURL(currentAttachment.previewUrl);
      return currentDrafts.filter((attachment) => attachment.id !== attachmentId);
    });
    if (removedAttachment?.uploadedAttachment) {
      void onAttachmentDelete(removedAttachment.uploadedAttachment.id).catch(() => undefined);
    }
  };

  const clearAttachmentDrafts = () => {
    setAttachmentDrafts((currentDrafts) => {
      currentDrafts.forEach((attachment) => {
        if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
      });
      return [];
    });
  };

  const appendAttachmentDrafts = (nextDrafts: ComposerAttachmentDraft[]) => {
    setAttachmentDrafts((currentDrafts) => {
      return [...currentDrafts, ...nextDrafts];
    });
  };

  const resetVoiceCapture = () => {
    if (voiceTimerRef.current !== null) {
      window.clearInterval(voiceTimerRef.current);
      voiceTimerRef.current = null;
    }
    speechRecognitionRef.current = null;
    speechTranscriptRef.current = '';
    voiceModeRef.current = null;
    voiceStreamRef.current?.getTracks().forEach((track) => track.stop());
    voiceStreamRef.current = null;
    mediaRecorderRef.current = null;
    voiceChunksRef.current = [];
    setVoiceSeconds(0);
  };

  const appendVoiceTextToDraft = (text: string) => {
    const normalizedText = text.trim();
    if (!normalizedText) return false;
    const currentDraft = draftRef.current.trim();
    onChange(currentDraft ? `${currentDraft}\n${normalizedText}` : normalizedText);
    return true;
  };

  const cancelVoiceRecording = () => {
    const recognition = speechRecognitionRef.current;
    if (recognition && voiceModeRef.current === 'speech') {
      recognition.onend = null;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.abort();
    }

    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = null;
      recorder.stop();
    }
    resetVoiceCapture();
    setVoiceState('idle');
    setVoiceError('');
  };

  const transcribeVoiceBlob = async (blob: Blob, mimeType: string) => {
    if (!blob.size) {
      setVoiceError('没有录到语音');
      setVoiceState('idle');
      return;
    }

    setVoiceState('transcribing');
    setVoiceError('');
    const extension = mimeType.includes('mp4') || mimeType.includes('mpeg') ? 'mp4' : 'webm';
    const audioFile = new File([blob], `voice-${Date.now()}.${extension}`, {
      type: mimeType || 'audio/webm',
    });

    try {
      const text = await onAudioTranscribe(audioFile);
      const normalizedText = text.trim();
      if (!normalizedText) {
        setVoiceError('没有识别到有效文字');
        return;
      }
      appendVoiceTextToDraft(normalizedText);
    } catch (error) {
      setVoiceError(error instanceof Error ? error.message : '语音转文字失败');
    } finally {
      resetVoiceCapture();
      setVoiceState('idle');
    }
  };

  const stopVoiceRecording = () => {
    if (voiceModeRef.current === 'speech') {
      speechRecognitionRef.current?.stop();
      return;
    }

    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === 'inactive') return;
    recorder.stop();
  };

  const startBrowserSpeechRecognition = () => {
    const SpeechRecognitionConstructor = getBrowserSpeechRecognitionConstructor();
    if (!SpeechRecognitionConstructor) return false;

    try {
      const recognition = new SpeechRecognitionConstructor();
      recognition.lang = 'zh-CN';
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      speechTranscriptRef.current = '';
      voiceModeRef.current = 'speech';
      speechRecognitionRef.current = recognition;

      recognition.onresult = (event) => {
        let finalText = '';
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const result = event.results[index];
          const transcript = result?.[0]?.transcript?.trim() ?? '';
          if (result?.isFinal && transcript) {
            finalText = `${finalText} ${transcript}`.trim();
          }
        }
        if (finalText) {
          speechTranscriptRef.current = `${speechTranscriptRef.current} ${finalText}`.trim();
        }
      };

      recognition.onerror = (event) => {
        const message =
          event.error === 'not-allowed'
            ? '浏览器没有麦克风权限'
            : event.error === 'no-speech'
              ? '没有识别到语音'
              : event.message || '语音识别失败';
        setVoiceError(message);
        resetVoiceCapture();
        setVoiceState('idle');
      };

      recognition.onend = () => {
        if (voiceModeRef.current !== 'speech') return;
        const appended = appendVoiceTextToDraft(speechTranscriptRef.current);
        if (!appended) {
          setVoiceError('没有识别到有效文字');
        }
        resetVoiceCapture();
        setVoiceState('idle');
      };

      recognition.start();
      setVoiceSeconds(0);
      setVoiceState('recording');
      setVoiceError('');
      setMultimodalOpen(false);
      voiceTimerRef.current = window.setInterval(() => {
        setVoiceSeconds((seconds) => seconds + 1);
      }, 1000);
      return true;
    } catch {
      resetVoiceCapture();
      return false;
    }
  };

  const startBackendVoiceRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      setVoiceError('当前浏览器不支持录音');
      return;
    }

    try {
      setVoiceError('');
      voiceModeRef.current = 'backend';
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const preferredMimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : '';
      const recorder = preferredMimeType ? new MediaRecorder(stream, { mimeType: preferredMimeType }) : new MediaRecorder(stream);
      voiceStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      voiceChunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          voiceChunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        const mimeType = recorder.mimeType || preferredMimeType || 'audio/webm';
        const blob = new Blob(voiceChunksRef.current, { type: mimeType });
        void transcribeVoiceBlob(blob, mimeType);
      };
      recorder.start();
      setVoiceSeconds(0);
      setVoiceState('recording');
      setMultimodalOpen(false);
      voiceTimerRef.current = window.setInterval(() => {
        setVoiceSeconds((seconds) => seconds + 1);
      }, 1000);
    } catch (error) {
      resetVoiceCapture();
      setVoiceState('idle');
      setVoiceError(error instanceof Error ? error.message : '无法访问麦克风');
    }
  };

  const startVoiceRecording = async () => {
    if (isSending || voiceState !== 'idle') return;
    if (startBrowserSpeechRecognition()) return;
    await startBackendVoiceRecording();
  };

  const detectAttachmentKind = (file: File): ComposerFileAttachmentKind => {
    if (file.type.startsWith('image/')) return 'image';
    if (file.type.startsWith('video/')) return 'video';
    const lowerName = file.name.toLowerCase();
    if (documentAttachmentExtensions.some((extension) => lowerName.endsWith(extension))) return 'document';
    return 'document';
  };

  const updateAttachmentDraft = (attachmentId: string, update: Partial<ComposerAttachmentDraft>) => {
    setAttachmentDrafts((currentDrafts) =>
      currentDrafts.map((attachment) => (attachment.id === attachmentId ? { ...attachment, ...update } : attachment)),
    );
  };

  const uploadAttachmentDraft = async (attachmentId: string, sourceFile: File, kind: ComposerFileAttachmentKind) => {
    setAttachmentUploadCount((count) => count + 1);
    try {
      const prepared = kind === 'image'
        ? await prepareImageForUpload(sourceFile, uploadPreferences.image_compression)
        : { file: sourceFile, originalSize: sourceFile.size, compressed: false };
      if (removedAttachmentDraftIdsRef.current.has(attachmentId)) return;

      updateAttachmentDraft(attachmentId, {
        file: prepared.file,
        detail: kind === 'image' ? formatPreparedImageDetail(prepared) : formatAttachmentSize(prepared.file.size),
        uploadStatus: 'uploading',
        uploadError: undefined,
      });
      let uploadedAttachment: ApiDiagnosisFileResponse;
      try {
        uploadedAttachment = await onAttachmentUpload(prepared.file);
      } catch (uploadError) {
        if (!uploadPreferences.auto_retry_upload) throw uploadError;
        uploadedAttachment = await onAttachmentUpload(prepared.file);
      }
      if (removedAttachmentDraftIdsRef.current.has(attachmentId)) {
        await onAttachmentDelete(uploadedAttachment.id).catch(() => undefined);
        return;
      }
      updateAttachmentDraft(attachmentId, {
        uploadedAttachment,
        uploadStatus: 'ready',
        uploadError: undefined,
      });
    } catch (error) {
      if (!removedAttachmentDraftIdsRef.current.has(attachmentId)) {
        updateAttachmentDraft(attachmentId, {
          uploadStatus: 'error',
          uploadError: error instanceof Error ? error.message : '附件上传失败，请重试',
        });
      }
    } finally {
      setAttachmentUploadCount((count) => Math.max(0, count - 1));
    }
  };

  const retryAttachmentUpload = (attachment: ComposerAttachmentDraft) => {
    if (
      !attachment.file ||
      (attachment.kind !== 'image' && attachment.kind !== 'video' && attachment.kind !== 'document')
    ) {
      return;
    }
    removedAttachmentDraftIdsRef.current.delete(attachment.id);
    updateAttachmentDraft(attachment.id, {
      uploadStatus: attachment.kind === 'image' ? 'preparing' : 'uploading',
      uploadError: undefined,
    });
    void uploadAttachmentDraft(attachment.id, attachment.file, attachment.kind);
  };

  const handleFileAttachmentChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (!files.length) return;

    const remainingSlots = Math.max(0, 6 - attachmentDraftsRef.current.length);
    const selectedFiles = files.slice(0, Math.min(4, remainingSlots));
    if (!selectedFiles.length) return;

    const nextDrafts: ComposerAttachmentDraft[] = selectedFiles.map((file, index) => {
      const kind = detectAttachmentKind(file);
      const attachmentId = `attachment-${Date.now()}-${index}-${file.name}`;
      return {
        id: attachmentId,
        kind,
        name: file.name,
        detail: formatAttachmentSize(file.size),
        file,
        previewUrl: kind === 'document' ? undefined : URL.createObjectURL(file),
        uploadStatus: kind === 'image' ? 'preparing' : 'uploading',
      };
    });

    appendAttachmentDrafts(nextDrafts);
    setMultimodalOpen(false);
    nextDrafts.forEach((attachment) => {
      if (
        attachment.file &&
        (attachment.kind === 'image' || attachment.kind === 'video' || attachment.kind === 'document')
      ) {
        void uploadAttachmentDraft(attachment.id, attachment.file, attachment.kind);
      }
    });
  };

  const openMaterialPicker = () => {
    if (isSending) return;
    materialInputRef.current?.click();
  };

  const addFarmingDataDraft = (structuredData: Record<string, unknown>, detail: string) => {
    const dataDraft: ComposerAttachmentDraft = {
      id: `attachment-data-${Date.now()}`,
      kind: 'data',
      name: '养殖数据',
      detail,
      structuredData,
    };
    setAttachmentDrafts((currentDrafts) => [
      ...currentDrafts.filter((attachment) => attachment.kind !== 'data'),
      dataDraft,
    ]);
    setMultimodalOpen(false);
    setFarmingDataOpen(false);
  };

  const triggerAttachmentTool = (kind: ComposerAttachmentKind) => {
    if (isSending) return;

    if (kind === 'image') {
      imageInputRef.current?.click();
      return;
    }
    if (kind === 'video') {
      videoInputRef.current?.click();
      return;
    }
    if (kind === 'document') {
      documentInputRef.current?.click();
      return;
    }
    if (kind === 'audio') {
      void startVoiceRecording();
      return;
    }

    setMultimodalOpen(false);
    setFarmingDataOpen(true);
  };

  const buildStructuredData = () => {
    return attachmentDrafts.find((attachment) => attachment.kind === 'data')?.structuredData ?? null;
  };

  const submitComposer = () => {
    const uploadedAttachments = attachmentDrafts.flatMap((attachment) =>
      attachment.uploadStatus === 'ready' && attachment.uploadedAttachment ? [attachment.uploadedAttachment] : [],
    );
    const structuredData = buildStructuredData();
    const hasPendingAttachment = attachmentDrafts.some(
      (attachment) => attachment.file && attachment.uploadStatus !== 'ready',
    );
    const hasPayload = draft.trim().length > 0 || uploadedAttachments.length > 0 || Boolean(structuredData);
    if (sendDisabled || isSending || isUploadingAttachments || hasPendingAttachment || !hasPayload) return;

    onSubmit({
      attachmentIds: uploadedAttachments.map((attachment) => attachment.id),
      uploadedAttachments,
      structuredData,
    });
    setMultimodalOpen(false);
    clearAttachmentDrafts();
  };

  const handleComposerSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitComposer();
  };

  const handleComposerKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    submitComposer();
  };

  const finalSendDisabled =
    sendDisabled ||
    isSending ||
    isUploadingAttachments ||
    attachmentDrafts.some((attachment) => attachment.file && attachment.uploadStatus !== 'ready') ||
    (draft.trim().length === 0 &&
      !attachmentDrafts.some((attachment) => attachment.uploadStatus === 'ready' || attachment.kind === 'data'));
  const mediaAttachmentDrafts = attachmentDrafts.filter(
    (attachment) => attachment.kind === 'image' || attachment.kind === 'video',
  );
  const fileAttachmentDrafts = attachmentDrafts.filter(
    (attachment) => attachment.kind !== 'image' && attachment.kind !== 'video',
  );

  return (
    <form className={className} ref={composerRef} onSubmit={handleComposerSubmit}>
      {multimodalOpen && (
        <div
          className={clsx('diagnosis-multimodal-panel', `placement-${panelPlacement}`)}
          role="menu"
          aria-label="添加问诊材料"
        >
          <div className="diagnosis-multimodal-list">
            {multimodalComposerTools.map((tool) => {
              const ToolIcon = tool.icon;
              return (
                <button
                  key={tool.key}
                  type="button"
                  role="menuitem"
                  disabled={isSending}
                  onClick={openMaterialPicker}
                >
                  <span className="diagnosis-multimodal-mark kind-upload">
                    <ToolIcon size={17} />
                  </span>
                  <span>
                    <strong>{tool.label}</strong>
                    <small>{tool.note}</small>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
      {mediaAttachmentDrafts.length > 0 && (
        <div className="diagnosis-attachment-media-strip" aria-label="待发送图片和视频">
          {mediaAttachmentDrafts.map((attachment) => {
            const AttachmentIcon = composerAttachmentMeta[attachment.kind].icon;
            return (
              <div
                className={clsx(
                  'diagnosis-attachment-media-card',
                  `kind-${attachment.kind}`,
                  attachment.uploadStatus && `is-${attachment.uploadStatus}`,
                )}
                key={attachment.id}
              >
                <div className="diagnosis-attachment-media-preview" aria-hidden="true">
                  {attachment.previewUrl && attachment.kind === 'image' ? (
                    <img alt="" src={attachment.previewUrl} />
                  ) : attachment.previewUrl && attachment.kind === 'video' ? (
                    <video muted playsInline src={attachment.previewUrl} />
                  ) : (
                    <AttachmentIcon size={17} />
                  )}
                </div>
                {attachment.uploadStatus !== 'ready' && attachment.uploadStatus !== 'error' && (
                  <span className="diagnosis-attachment-upload-spinner" aria-label="附件上传中" />
                )}
                {attachment.uploadStatus === 'error' && (
                  <button
                    className="diagnosis-attachment-retry"
                    type="button"
                    aria-label={`重新上传${attachment.name}`}
                    title={attachment.uploadError || '重新上传'}
                    onClick={() => retryAttachmentUpload(attachment)}
                  >
                    <RotateCcw size={15} />
                  </button>
                )}
                <button type="button" aria-label={`移除${composerAttachmentMeta[attachment.kind].label}`} onClick={() => removeAttachmentDraft(attachment.id)}>
                  <X size={14} />
                </button>
              </div>
            );
          })}
        </div>
      )}
      {fileAttachmentDrafts.length > 0 && (
        <div className="diagnosis-attachment-strip document-strip" aria-label="待发送文档资料">
          {fileAttachmentDrafts.map((attachment) => {
            const AttachmentIcon = composerAttachmentMeta[attachment.kind].icon;
            return (
              <div className={clsx('diagnosis-attachment-chip', `kind-${attachment.kind}`)} key={attachment.id}>
                <div className="diagnosis-attachment-preview" aria-hidden="true">
                  <AttachmentIcon size={17} />
                </div>
                <div className="diagnosis-attachment-copy">
                  <strong>{attachment.name}</strong>
                  <span>{attachment.uploadStatus === 'error' ? attachment.uploadError || '上传失败' : attachment.detail}</span>
                </div>
                {attachment.uploadStatus !== 'ready' && attachment.uploadStatus !== 'error' && <span className="diagnosis-file-upload-spinner" aria-label="附件上传中" />}
                {attachment.uploadStatus === 'error' && (
                  <button
                    className="diagnosis-file-attachment-retry"
                    type="button"
                    aria-label={`重新上传${attachment.name}`}
                    title={attachment.uploadError || '重新上传'}
                    onClick={() => retryAttachmentUpload(attachment)}
                  >
                    <RotateCcw size={14} />
                  </button>
                )}
                <button type="button" aria-label={`移除${composerAttachmentMeta[attachment.kind].label}`} onClick={() => removeAttachmentDraft(attachment.id)}>
                  <X size={14} />
                </button>
              </div>
            );
          })}
        </div>
      )}
      {isUploadingAttachments && <div className="diagnosis-image-preparing" role="status">正在上传附件到安全存储</div>}
      {(voiceState !== 'idle' || voiceError) && (
        <div className={clsx('diagnosis-voice-capture', voiceState)} role="status">
          <span className="diagnosis-voice-dot" aria-hidden="true" />
          <div className="diagnosis-voice-copy">
            <strong>
              {voiceState === 'recording'
                ? '正在听'
                : voiceState === 'transcribing'
                  ? '正在转文字'
                  : '语音未识别'}
            </strong>
            <span>{voiceError || (voiceState === 'recording' ? formatVoiceDuration(voiceSeconds) : '请稍等')}</span>
          </div>
          {voiceState === 'recording' ? (
            <div className="diagnosis-voice-actions">
              <button type="button" onClick={cancelVoiceRecording}>
                取消
              </button>
              <button className="primary" type="button" onClick={stopVoiceRecording}>
                完成
              </button>
            </div>
          ) : (
            voiceError && (
              <button className="diagnosis-voice-dismiss" type="button" aria-label="关闭语音提示" onClick={() => setVoiceError('')}>
                <X size={14} />
              </button>
            )
          )}
        </div>
      )}
      <textarea
        aria-label="输入问诊问题"
        aria-busy={isSending}
        disabled={isSending}
        enterKeyHint="send"
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleComposerKeyDown}
        placeholder={isSending ? '正在等待模型回复...' : placeholder}
        rows={1}
        title="Enter 发送，Shift + Enter 换行"
        value={draft}
      />
      <div className="diagnosis-start-toolbar">
        <div className="diagnosis-start-tools">
          <button
            className={clsx(multimodalOpen && 'active')}
            type="button"
            aria-label="添加内容"
            aria-expanded={multimodalOpen}
            aria-haspopup="menu"
            disabled={isSending}
            onClick={() => setMultimodalOpen((open) => !open)}
          >
            <Plus size={20} />
          </button>
          <button type="button" aria-label="上传视频" disabled={isSending} onClick={() => triggerAttachmentTool('video')}>
            <Video size={17} />
          </button>
          <button type="button" aria-label="语音输入" disabled={isSending} onClick={() => triggerAttachmentTool('audio')}>
            <Mic size={17} />
          </button>
        </div>
        <div className="diagnosis-toolbar-right">
          <ModelSwitchControl
            disabled={isSending}
            models={configuredModels}
            selectedModelConfigId={selectedModelConfigId}
            onModelSelect={onModelSelect}
          />
          <button className="diagnosis-send-button" disabled={finalSendDisabled} type="submit" aria-label="发送">
            <Send size={20} />
          </button>
        </div>
      </div>
      <input
        ref={materialInputRef}
        className="diagnosis-hidden-file-input"
        type="file"
        accept={multimodalAttachmentAccept}
        multiple
        onChange={handleFileAttachmentChange}
      />
      <input
        ref={imageInputRef}
        className="diagnosis-hidden-file-input"
        type="file"
        accept="image/*"
        multiple
        onChange={handleFileAttachmentChange}
      />
      <input
        ref={videoInputRef}
        className="diagnosis-hidden-file-input"
        type="file"
        accept="video/*"
        multiple
        onChange={handleFileAttachmentChange}
      />
      <input
        ref={documentInputRef}
        className="diagnosis-hidden-file-input"
        type="file"
        accept={documentAttachmentAccept}
        multiple
        onChange={handleFileAttachmentChange}
      />
      {farmingDataOpen && (
        <ComposerFarmingDataDialog
          onCancel={() => setFarmingDataOpen(false)}
          onSave={addFarmingDataDraft}
        />
      )}
    </form>
  );
}

function ComposerFarmingDataDialog({
  onCancel,
  onSave,
}: {
  onCancel: () => void;
  onSave: (structuredData: Record<string, unknown>, detail: string) => void;
}) {
  const [form, setForm] = useState({
    record_date: todayInputValue(),
    instar: '',
    temperature_celsius: '',
    humidity_percent: '',
    feedings: '',
    leaf_amount_kg: '',
    sick_count: '',
    death_count: '',
    observations: '',
  });
  const update = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const toNumber = (value: string) => (value.trim() === '' ? null : Number(value));
  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const structuredData = {
      source: 'composer_farming_record',
      record_date: form.record_date,
      husbandry: {
        instar: form.instar || null,
        temperature_celsius: toNumber(form.temperature_celsius),
        humidity_percent: toNumber(form.humidity_percent),
        feedings: toNumber(form.feedings),
        leaf_amount_kg: toNumber(form.leaf_amount_kg),
        sick_count: toNumber(form.sick_count),
        death_count: toNumber(form.death_count),
        observations: form.observations.trim() || null,
      },
    };
    const detail = [
      form.instar && `${form.instar}`,
      form.temperature_celsius && `${form.temperature_celsius}℃`,
      form.humidity_percent && `${form.humidity_percent}%湿度`,
      form.sick_count && `${form.sick_count}头异常`,
    ].filter(Boolean).join(' · ') || '已填写现场养殖数据';
    onSave(structuredData, detail);
  };

  return (
    <HusbandryModal eyebrow="问诊补充" title="记录现场养殖数据" onCancel={onCancel}>
      <form className="husbandry-form" onSubmit={save}>
        <p className="diagnosis-case-dialog-note">这些数据会随本次问诊一同发送，帮助模型结合现场情况给出建议。</p>
        <div className="husbandry-form-grid">
          <label>记录日期<input required type="date" value={form.record_date} onChange={(event) => update('record_date', event.target.value)} /></label>
          <label>蚕龄<select value={form.instar} onChange={(event) => update('instar', event.target.value)}><option value="">未填写</option><option value="一龄">一龄</option><option value="二龄">二龄</option><option value="三龄">三龄</option><option value="四龄">四龄</option><option value="五龄">五龄</option><option value="上蔟">上蔟</option></select></label>
          <label>温度（℃）<input inputMode="decimal" min="0" max="50" placeholder="如 25" type="number" value={form.temperature_celsius} onChange={(event) => update('temperature_celsius', event.target.value)} /></label>
          <label>湿度（%）<input inputMode="decimal" min="0" max="100" placeholder="如 78" type="number" value={form.humidity_percent} onChange={(event) => update('humidity_percent', event.target.value)} /></label>
          <label>喂食次数<input inputMode="numeric" min="0" max="20" placeholder="如 3" type="number" value={form.feedings} onChange={(event) => update('feedings', event.target.value)} /></label>
          <label>用叶量（kg）<input inputMode="decimal" min="0" placeholder="如 12.5" step="0.1" type="number" value={form.leaf_amount_kg} onChange={(event) => update('leaf_amount_kg', event.target.value)} /></label>
          <label>异常数量<input inputMode="numeric" min="0" placeholder="如 2" type="number" value={form.sick_count} onChange={(event) => update('sick_count', event.target.value)} /></label>
          <label>死亡数量<input inputMode="numeric" min="0" placeholder="如 0" type="number" value={form.death_count} onChange={(event) => update('death_count', event.target.value)} /></label>
        </div>
        <label>现场补充<textarea maxLength={1200} placeholder="例如：食欲下降、眠起不齐、通风情况或已采取的措施。" value={form.observations} onChange={(event) => update('observations', event.target.value)} /></label>
        <footer className="husbandry-form-actions"><button type="button" onClick={onCancel}>取消</button><button className="husbandry-primary-action" type="submit">附加到本次问诊</button></footer>
      </form>
    </HusbandryModal>
  );
}

function ModelSwitchControl({
  disabled,
  models,
  selectedModelConfigId,
  onModelSelect,
}: {
  disabled: boolean;
  models: ConfiguredModel[];
  selectedModelConfigId: string | null;
  onModelSelect: (modelConfigId: string | null) => void;
}) {
  const pickerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const selectableModels = models.filter((model) => model.enabled);

  useEffect(() => {
    if (!open) return undefined;

    const handlePointerDown = (event: PointerEvent) => {
      if (!pickerRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };

    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  if (selectableModels.length === 0) {
    return (
      <span className="diagnosis-model-empty" title="请先在设置中配置模型">
        未配置模型
      </span>
    );
  }

  const selectedValue = selectableModels.some((model) => model.id === selectedModelConfigId)
    ? selectedModelConfigId ?? ''
    : selectableModels.find((model) => model.isDefault)?.id ?? selectableModels[0].id;
  const selectedModel = selectableModels.find((model) => model.id === selectedValue) ?? selectableModels[0];
  const selectedLabel = selectedModel.modelId || selectedModel.providerName;

  const handleModelChoose = (modelConfigId: string) => {
    onModelSelect(modelConfigId);
    setOpen(false);
  };

  return (
    <div className={clsx('diagnosis-model-picker', open && 'open')} ref={pickerRef}>
      <button
        className="diagnosis-model-trigger"
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`当前模型：${selectedLabel}`}
        disabled={disabled}
        onClick={() => setOpen((currentOpen) => !currentOpen)}
      >
        <span>{selectedLabel}</span>
        <ChevronDown size={13} aria-hidden="true" />
      </button>
      {open && (
        <div className="diagnosis-model-menu" role="listbox" aria-label="选择对话模型">
          {selectableModels.map((model) => {
            const modelLabel = model.modelId || model.providerName;
            const selected = model.id === selectedValue;

            return (
              <button
                className={clsx('diagnosis-model-option', selected && 'selected')}
                key={model.id}
                type="button"
                role="option"
                aria-selected={selected}
                onClick={() => handleModelChoose(model.id)}
              >
                <span>{modelLabel}</span>
                {selected && <Check size={14} aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DiagnosisMessageBubble({
  message,
  sourceQuestion,
  onDelete,
  onEdit,
  onFeedback,
  onNotify,
  onRegenerate,
}: {
  message: DiagnosisMessage;
  sourceQuestion: string | null;
  onDelete: (messageId: string) => Promise<void>;
  onEdit: (messageId: string, content: string) => Promise<void>;
  onFeedback: (
    messageId: string,
    feedback: 'like' | 'dislike' | null,
    feedbackReasons?: string[],
    feedbackDetail?: string | null,
  ) => Promise<void>;
  onNotify: (message: string, tone?: ToastTone) => void;
  onRegenerate: (messageId: string) => Promise<void>;
}) {
  const isUser = message.role === 'user';
  const isError = message.status === 'error';
  const isRegenerating = message.status === 'regenerating';
  const AvatarIcon = isUser ? UserRound : Bot;
  const messageAttachments = message.attachments ?? [];
  const mediaAttachments = messageAttachments.filter(
    (attachment) => (attachment.fileType === 'image' || attachment.fileType === 'video') && attachment.storageUrl,
  );
  const fileAttachments = messageAttachments.filter(
    (attachment) => !((attachment.fileType === 'image' || attachment.fileType === 'video') && attachment.storageUrl),
  );
  const hasTextContent = message.content.trim().length > 0;
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState(message.content);
  const [editSaving, setEditSaving] = useState(false);

  const startEditing = () => {
    setEditDraft(message.content);
    setEditing(true);
  };

  const cancelEditing = () => {
    setEditDraft(message.content);
    setEditing(false);
    setEditSaving(false);
  };

  const handleEditSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextContent = editDraft.trim();
    if (!nextContent || nextContent === message.content.trim()) {
      cancelEditing();
      return;
    }

    setEditSaving(true);
    try {
      await onEdit(message.id, nextContent);
      setEditing(false);
    } catch {
      onNotify('消息更新失败', 'error');
    } finally {
      setEditSaving(false);
    }
  };

  return (
    <div className={clsx('diagnosis-message', isUser ? 'user' : 'assistant', editing && 'editing', isError && 'error')}>
      {!isUser && (
        <div className="diagnosis-message-avatar">
          <AvatarIcon size={17} />
        </div>
      )}
      <div className="diagnosis-message-content">
        {isRegenerating ? (
          <div className="diagnosis-thinking-body diagnosis-message-regenerating-body" role="status" aria-label="正在重新生成回复">
            <span />
            <span />
            <span />
          </div>
        ) : editing ? (
          <form className="diagnosis-message-edit-form" onSubmit={handleEditSubmit}>
            <textarea
              aria-label="编辑消息"
              disabled={editSaving}
              maxLength={4000}
              rows={3}
              value={editDraft}
              onChange={(event) => setEditDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Escape') {
                  event.preventDefault();
                  cancelEditing();
                }
              }}
            />
            <div className="diagnosis-message-edit-actions">
              <button type="button" disabled={editSaving} onClick={cancelEditing}>
                取消
              </button>
              <button type="submit" disabled={editSaving || !editDraft.trim()}>
                {editSaving ? '发送中...' : '发送'}
              </button>
            </div>
          </form>
        ) : (
          <>
            {mediaAttachments.length > 0 && (
              <DiagnosisMessageAttachments attachments={mediaAttachments} variant="media" />
            )}
            {fileAttachments.length > 0 && (
              <DiagnosisMessageAttachments attachments={fileAttachments} variant="files" />
            )}
            {hasTextContent ? (
              <div className="diagnosis-message-body">
                <span>{isUser ? '你' : 'CanW 助手'} · {message.createdAt}</span>
                {isUser ? <p>{message.content}</p> : <DiagnosisMarkdown content={message.content} />}
              </div>
            ) : (
              <span className="diagnosis-message-meta-only">{isUser ? '你' : 'CanW 助手'} · {message.createdAt}</span>
            )}
            <DiagnosisMessageActions
              isUser={isUser}
              content={message.content}
              createdAt={message.createdAt}
              feedback={message.feedback ?? null}
              sourceQuestion={sourceQuestion}
              onDelete={() => onDelete(message.id)}
              onEdit={startEditing}
              onFeedback={(
                nextFeedback: DiagnosisMessageFeedback,
                feedbackReasons?: string[],
                feedbackDetail?: string | null,
              ) => onFeedback(message.id, nextFeedback, feedbackReasons, feedbackDetail)}
              onNotify={onNotify}
              onRegenerate={() => onRegenerate(message.id)}
            />
          </>
        )}
      </div>
      {isUser && (
        <div className="diagnosis-message-avatar">
          <AvatarIcon size={17} />
        </div>
      )}
    </div>
  );
}

function DiagnosisMessageAttachments({
  attachments,
  variant = 'files',
}: {
  attachments: DiagnosisMessageAttachment[];
  variant?: 'files' | 'media';
}) {
  if (variant === 'media') {
    return (
      <div className="diagnosis-message-media-grid" aria-label="图片和视频附件">
        {attachments.map((attachment) => {
          if (attachment.fileType === 'video') {
            return (
              <div className="diagnosis-message-media kind-video" key={attachment.id} title={attachment.fileName}>
                <video controls playsInline preload="metadata" src={attachment.storageUrl ?? ''} />
              </div>
            );
          }

          return (
            <a
              className="diagnosis-message-media kind-image"
              href={attachment.storageUrl ?? undefined}
              key={attachment.id}
              target="_blank"
              rel="noreferrer"
              title={attachment.fileName}
            >
              <img alt={attachment.fileName} src={attachment.storageUrl ?? ''} />
            </a>
          );
        })}
      </div>
    );
  }

  return (
    <div className="diagnosis-message-attachments" aria-label="消息附件">
      {attachments.map((attachment) => {
        const normalizedType = attachment.fileType === 'other' ? 'document' : attachment.fileType;
        const AttachmentIcon = composerAttachmentMeta[normalizedType].icon;
        const content = (
          <>
            <span className={clsx('diagnosis-message-attachment-preview', `kind-${normalizedType}`)}>
              {attachment.fileType === 'image' && attachment.storageUrl ? (
                <img alt="" src={attachment.storageUrl} />
              ) : (
                <AttachmentIcon size={17} />
              )}
            </span>
            <span className="diagnosis-message-attachment-copy">
              <strong>{attachment.fileName}</strong>
              <small>{composerAttachmentMeta[normalizedType].label} · {formatAttachmentSize(attachment.fileSize)}</small>
            </span>
          </>
        );

        return attachment.storageUrl ? (
          <a
            className={clsx('diagnosis-message-attachment', `kind-${normalizedType}`)}
            href={attachment.storageUrl}
            key={attachment.id}
            target="_blank"
            rel="noreferrer"
          >
            {content}
          </a>
        ) : (
          <div className={clsx('diagnosis-message-attachment', `kind-${normalizedType}`)} key={attachment.id}>
            {content}
          </div>
        );
      })}
    </div>
  );
}

type DiagnosisMessageFeedback = 'like' | 'dislike' | null;

const dislikeFeedbackReasonOptions = [
  '不正确或不完整',
  '与期望不符',
  '速度慢或存在问题',
  '风格或语气',
  '安全或法律疑虑',
  '其他',
];

type DiagnosisMessageActionsProps = {
  isUser: boolean;
  content: string;
  createdAt: string;
  feedback: DiagnosisMessageFeedback;
  sourceQuestion: string | null;
  onDelete: () => Promise<void>;
  onEdit: () => void;
  onFeedback: (
    feedback: DiagnosisMessageFeedback,
    feedbackReasons?: string[],
    feedbackDetail?: string | null,
  ) => Promise<void>;
  onNotify: (message: string, tone?: ToastTone) => void;
  onRegenerate: () => Promise<void>;
};

function DislikeFeedbackDialog({
  onCancel,
  onSubmit,
}: {
  onCancel: () => void;
  onSubmit: (feedbackReasons: string[], feedbackDetail: string | null) => Promise<void>;
}) {
  const [selectedReasons, setSelectedReasons] = useState<string[]>([]);
  const [detail, setDetail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const canSubmit = selectedReasons.length > 0 || detail.trim().length > 0;

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onCancel]);

  const toggleReason = (reason: string) => {
    setSelectedReasons((currentReasons) =>
      currentReasons.includes(reason)
        ? currentReasons.filter((currentReason) => currentReason !== reason)
        : [...currentReasons, reason],
    );
  };

  const handleSubmit = async () => {
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    try {
      await onSubmit(selectedReasons, detail.trim() || null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="message-feedback-overlay" role="presentation" onMouseDown={onCancel}>
      <section
        className="message-feedback-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="message-feedback-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="message-feedback-header">
          <h2 id="message-feedback-title">分享反馈</h2>
          <button type="button" aria-label="关闭反馈" disabled={submitting} onClick={onCancel}>
            <X size={19} />
          </button>
        </div>
        <div className="message-feedback-reasons" aria-label="反馈原因">
          {dislikeFeedbackReasonOptions.map((reason) => (
            <button
              className={clsx(selectedReasons.includes(reason) && 'selected')}
              key={reason}
              type="button"
              aria-pressed={selectedReasons.includes(reason)}
              disabled={submitting}
              onClick={() => toggleReason(reason)}
            >
              {reason}
            </button>
          ))}
        </div>
        <textarea
          value={detail}
          disabled={submitting}
          maxLength={1000}
          placeholder="分享详细信息（可选）"
          onChange={(event) => setDetail(event.target.value)}
        />
        <div className="message-feedback-actions">
          <button type="button" disabled={!canSubmit || submitting} onClick={() => void handleSubmit()}>
            {submitting ? '提交中' : '提交'}
          </button>
        </div>
      </section>
    </div>
  );
}

type DiagnosisShareVariant = 'care-card' | 'expert-review' | 'case-summary';

const diagnosisShareOptions: Array<{
  value: DiagnosisShareVariant;
  label: string;
  note: string;
  actionLabel: string;
  icon: LucideIcon;
}> = [
  {
    value: 'care-card',
    label: '问诊卡片',
    note: '给养殖户或同伴执行',
    actionLabel: '复制问诊卡片',
    icon: ClipboardList,
  },
  {
    value: 'expert-review',
    label: '专家复核',
    note: '给农技专家继续判断',
    actionLabel: '复制复核单',
    icon: Stethoscope,
  },
  {
    value: 'case-summary',
    label: '病例摘要',
    note: '用于归档和后续追踪',
    actionLabel: '复制病例摘要',
    icon: FileText,
  },
];

function compactDiagnosisText(value: string, maxLength = 180) {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength)}...`;
}

function buildDiagnosisShareText({
  answer,
  createdAt,
  question,
  variant,
}: {
  answer: string;
  createdAt: string;
  question: string | null;
  variant: DiagnosisShareVariant;
}) {
  const questionText = question?.trim() || '未记录对应问题';
  const answerText = answer.trim();

  if (variant === 'expert-review') {
    return [
      '【CanW 家蚕问诊专家复核单】',
      `时间：${createdAt}`,
      '',
      '养殖户问题：',
      questionText,
      '',
      'AI 初步问诊回复：',
      answerText,
      '',
      '请专家重点复核：',
      '1. 初步判断是否需要修正；',
      '2. 还需要补充哪些现场信息或图片；',
      '3. 临时处置建议是否存在风险或遗漏。',
      '',
      '说明：以上内容为 AI 初步问诊结果，需结合现场情况复核。',
    ].join('\n');
  }

  if (variant === 'case-summary') {
    return [
      '【CanW 家蚕病例摘要】',
      `记录时间：${createdAt}`,
      '',
      `主诉：${compactDiagnosisText(questionText, 120)}`,
      '',
      `问诊摘要：${compactDiagnosisText(answerText, 260)}`,
      '',
      '后续追踪建议：',
      '持续记录发病数量、死亡数量、蚕龄、温湿度、消毒处理和关键图片，便于复诊对比。',
    ].join('\n');
  }

  return [
    '【CanW 家蚕问诊卡片】',
    `时间：${createdAt}`,
    '',
    '问题：',
    questionText,
    '',
    'AI 初步建议：',
    answerText,
    '',
    '执行提醒：',
    '请优先落实隔离、清理、消毒、通风和记录；如出现快速扩散或死亡增加，请联系农技人员复核。',
  ].join('\n');
}

function DiagnosisShareDialog({
  answer,
  createdAt,
  onCancel,
  onCopy,
  question,
}: {
  answer: string;
  createdAt: string;
  question: string | null;
  onCancel: () => void;
  onCopy: (text: string) => Promise<void>;
}) {
  const [selectedVariant, setSelectedVariant] = useState<DiagnosisShareVariant>('care-card');
  const [copiedVariant, setCopiedVariant] = useState<DiagnosisShareVariant | null>(null);
  const [copying, setCopying] = useState(false);
  const copyTimerRef = useRef<number | null>(null);
  const selectedOption = diagnosisShareOptions.find((option) => option.value === selectedVariant) ?? diagnosisShareOptions[0];
  const shareText = buildDiagnosisShareText({
    answer,
    createdAt,
    question,
    variant: selectedVariant,
  });

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !copying) onCancel();
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
    };
  }, [copying, onCancel]);

  const handleCopy = async () => {
    if (copying) return;

    setCopying(true);
    try {
      await onCopy(shareText);
      setCopiedVariant(selectedVariant);
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
      copyTimerRef.current = window.setTimeout(() => {
        setCopiedVariant(null);
        copyTimerRef.current = null;
      }, 1800);
    } catch {
      // The parent already shows the copy failure message.
    } finally {
      setCopying(false);
    }
  };

  return (
    <div
      className="message-feedback-overlay diagnosis-share-overlay"
      role="presentation"
      onMouseDown={() => {
        if (!copying) onCancel();
      }}
    >
      <section
        className="diagnosis-share-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="diagnosis-share-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="diagnosis-share-header">
          <div>
            <h2 id="diagnosis-share-title">分享问诊卡片</h2>
            <p>把这轮问诊整理成可转发、可复核、可归档的文本。</p>
          </div>
          <button type="button" aria-label="关闭分享" disabled={copying} onClick={onCancel}>
            <X size={19} />
          </button>
        </div>

        <div className="diagnosis-share-options" role="tablist" aria-label="分享用途">
          {diagnosisShareOptions.map((option) => {
            const OptionIcon = option.icon;
            const selected = selectedVariant === option.value;
            return (
              <button
                className={clsx(selected && 'selected')}
                key={option.value}
                type="button"
                role="tab"
                aria-selected={selected}
                disabled={copying}
                onClick={() => setSelectedVariant(option.value)}
              >
                <OptionIcon size={17} />
                <span>{option.label}</span>
                <small>{option.note}</small>
              </button>
            );
          })}
        </div>

        <div className="diagnosis-share-preview" aria-label="分享内容预览">
          <pre>{shareText}</pre>
        </div>

        <div className="diagnosis-share-actions">
          <button className="diagnosis-share-secondary" type="button" disabled={copying} onClick={onCancel}>
            取消
          </button>
          <button className="diagnosis-share-primary" type="button" disabled={copying} onClick={() => void handleCopy()}>
            {copiedVariant === selectedVariant ? <Check size={16} /> : <Copy size={16} />}
            <span>{copiedVariant === selectedVariant ? '已复制' : selectedOption.actionLabel}</span>
          </button>
        </div>
      </section>
    </div>
  );
}

function DiagnosisMessageActions({
  isUser,
  content,
  createdAt,
  feedback,
  sourceQuestion,
  onDelete,
  onEdit,
  onFeedback,
  onNotify,
  onRegenerate,
}: DiagnosisMessageActionsProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [dislikeDialogOpen, setDislikeDialogOpen] = useState(false);
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const copyTimerRef = useRef<number | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!(event.target instanceof Element)) return;
      if (!menuRef.current?.contains(event.target)) {
        setMenuOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMenuOpen(false);
      }
    };

    window.addEventListener('pointerdown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [menuOpen]);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current !== null) {
        window.clearTimeout(copyTimerRef.current);
      }
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const markCopied = () => {
    setCopied(true);
    if (copyTimerRef.current !== null) {
      window.clearTimeout(copyTimerRef.current);
    }
    copyTimerRef.current = window.setTimeout(() => {
      setCopied(false);
      copyTimerRef.current = null;
    }, 2400);
  };

  const copyWithFallback = (text: string) => {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.top = '0';
    textarea.style.left = '0';
    textarea.style.width = '1px';
    textarea.style.height = '1px';
    textarea.style.opacity = '0';
    textarea.style.pointerEvents = 'none';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);

    try {
      return document.execCommand('copy');
    } catch {
      return false;
    } finally {
      document.body.removeChild(textarea);
    }
  };

  const handleCopy = () => {
    if (copyWithFallback(content)) {
      markCopied();
      return;
    }

    if (!navigator.clipboard?.writeText) {
      onNotify('当前浏览器不支持自动复制', 'error');
      return;
    }

    void navigator.clipboard
      .writeText(content)
      .then(markCopied)
      .catch(() => onNotify('复制失败，请手动选择文本复制', 'error'));
  };

  const copyShareText = async (text: string) => {
    if (copyWithFallback(text)) return;

    if (!navigator.clipboard?.writeText) {
      throw new Error('clipboard unsupported');
    }

    await navigator.clipboard.writeText(text);
  };

  const handleReadAloud = () => {
    if (!('speechSynthesis' in window)) {
      onNotify('当前浏览器不支持朗读', 'error');
      return;
    }

    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      onNotify('已停止朗读', 'info');
      return;
    }

    const utterance = new SpeechSynthesisUtterance(content);
    utterance.lang = 'zh-CN';
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.cancel();
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
    onNotify('开始朗读', 'info');
  };

  const handleFeedback = (
    nextFeedback: DiagnosisMessageFeedback,
    feedbackReasons: string[] = [],
    feedbackDetail: string | null = null,
  ) => {
    void onFeedback(nextFeedback, feedbackReasons, feedbackDetail)
      .catch(() => onNotify('反馈保存失败', 'error'));
  };

  const submitDislikeFeedback = async (feedbackReasons: string[], feedbackDetail: string | null) => {
    try {
      await onFeedback('dislike', feedbackReasons, feedbackDetail);
      setDislikeDialogOpen(false);
    } catch {
      onNotify('反馈提交失败', 'error');
    }
  };

  const handleRegenerate = () => {
    void onRegenerate()
      .catch(() => onNotify('重试失败，请稍后再试', 'error'));
  };

  const handleDelete = () => {
    void onDelete()
      .then(() => onNotify('消息已删除'))
      .catch(() => onNotify('删除失败，请稍后再试', 'error'));
  };

  const confirmDelete = async () => {
    void handleDelete;
    if (deleteSubmitting) return;
    setDeleteSubmitting(true);
    try {
      await onDelete();
      setDeleteDialogOpen(false);
      setMenuOpen(false);
      onNotify(isUser ? '消息已删除' : '这轮对话已删除');
    } catch {
      onNotify('删除失败，请稍后再试', 'error');
    } finally {
      setDeleteSubmitting(false);
    }
  };

  let actions: Array<{
    label: string;
    tooltip: string;
    icon: LucideIcon;
    onClick?: () => void;
    active?: boolean;
    feedbackKind?: 'like' | 'dislike';
    copied?: boolean;
    menu?: boolean;
  }>;

  const likeAction = {
    label: '赞同',
    tooltip: '喜欢',
    icon: ThumbsUp,
    active: feedback === 'like',
    feedbackKind: 'like' as const,
    onClick: () => handleFeedback(feedback === 'like' ? null : 'like'),
  };

  const dislikeAction = {
    label: '不赞同',
    tooltip: '不喜欢',
    icon: ThumbsDown,
    active: feedback === 'dislike',
    feedbackKind: 'dislike' as const,
    onClick: () => {
      if (feedback === 'dislike') {
        handleFeedback(null);
        return;
      }
      setDislikeDialogOpen(true);
    },
  };

  const feedbackActions = feedback === 'like' ? [likeAction] : feedback === 'dislike' ? [dislikeAction] : [likeAction, dislikeAction];

  actions = isUser
    ? [
        {
          label: '复制',
          tooltip: copied ? '消息已复制' : '复制消息',
          icon: copied ? Check : Copy,
          copied,
          onClick: handleCopy,
        },
        { label: '编辑', tooltip: '编辑消息', icon: PencilLine, onClick: onEdit },
      ]
    : [
        {
          label: '复制',
          tooltip: copied ? '回复已复制' : '复制回复',
          icon: copied ? Check : Copy,
          copied,
          onClick: handleCopy,
        },
        ...feedbackActions,
        { label: '分享', tooltip: '分享问诊卡片', icon: Upload, onClick: () => setShareDialogOpen(true) },
        { label: '重新生成', tooltip: '重试', icon: RotateCcw, onClick: handleRegenerate },
        { label: '更多', tooltip: '更多', icon: MoreHorizontal, menu: true },
      ];
  const menuTimeLabel = `今天，${createdAt}`;

  return (
    <>
      <div
        className={clsx('diagnosis-message-actions', isUser ? 'user-actions' : 'assistant-actions')}
        role="group"
        aria-label="消息操作"
        ref={menuRef}
      >
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <span className="diagnosis-message-action-shell" key={action.label}>
              <button
                className={clsx(
                  action.active && 'active',
                  action.active && action.feedbackKind && `feedback-${action.feedbackKind}-active`,
                  action.copied && 'copied',
                )}
                type="button"
                aria-label={action.label}
                aria-pressed={action.feedbackKind ? action.active : undefined}
                aria-expanded={action.menu ? menuOpen : undefined}
                aria-haspopup={action.menu ? 'menu' : undefined}
                data-tooltip={action.tooltip}
                onClick={
                  action.menu
                    ? () => setMenuOpen((open) => !open)
                    : action.onClick
                }
              >
                <Icon size={16} strokeWidth={1.8} />
              </button>
              {action.menu && menuOpen && (
                <div className="diagnosis-message-more-menu" role="menu" aria-label="更多消息操作">
                  <div className="diagnosis-message-more-time">{menuTimeLabel}</div>
                  <button
                    className="danger"
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      setDeleteDialogOpen(true);
                    }}
                  >
                    <Trash2 size={16} />
                    <span>删除</span>
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      handleReadAloud();
                    }}
                  >
                    <Volume2 size={16} />
                    <span>{speaking ? '停止朗读' : '朗读'}</span>
                  </button>
                </div>
              )}
            </span>
          );
        })}
      </div>
      {dislikeDialogOpen && (
        <DislikeFeedbackDialog onCancel={() => setDislikeDialogOpen(false)} onSubmit={submitDislikeFeedback} />
      )}
      {shareDialogOpen && (
        <DiagnosisShareDialog
          answer={content}
          createdAt={createdAt}
          question={sourceQuestion}
          onCancel={() => setShareDialogOpen(false)}
          onCopy={async (text) => {
            try {
              await copyShareText(text);
            } catch {
              onNotify('分享内容复制失败，请手动选择文本复制', 'error');
              throw new Error('copy failed');
            }
          }}
        />
      )}
      {deleteDialogOpen && (
        <DeleteMessageTurnDialog
          saving={deleteSubmitting}
          onCancel={() => {
            if (!deleteSubmitting) setDeleteDialogOpen(false);
          }}
          onConfirm={confirmDelete}
        />
      )}
    </>
  );
}

function CommunityPage({
  accessToken,
  currentUser,
  draftPost,
  onAuthExpired,
  onDraftConsumed,
  onNotify,
  onRequireAuth,
  onTokenRefresh,
}: {
  accessToken: string;
  currentUser: AuthUser | null;
  draftPost: ApiCommunityPost | null;
  onAuthExpired: () => void;
  onDraftConsumed: () => void;
  onNotify: (message: string, tone?: ToastTone) => void;
  onRequireAuth: () => void;
  onTokenRefresh: () => Promise<AuthSessionState>;
}) {
  const [feedTab, setFeedTab] = useState<CommunityFeedTab>('recommended');
  const [posts, setPosts] = useState<ApiCommunityPost[]>([]);
  const [tags, setTags] = useState<ApiCommunityTag[]>([]);
  const [selectedTag, setSelectedTag] = useState('');
  const [contentFilter, setContentFilter] = useState<CommunityPostType | ''>('');
  const [questionFilter, setQuestionFilter] = useState<'open' | 'resolved' | ''>('');
  const [regionFilter, setRegionFilter] = useState('');
  const debouncedRegionFilter = useDebouncedValue(regionFilter, 350);
  const [searchDraft, setSearchDraft] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [communitySearchResults, setCommunitySearchResults] = useState<ApiCommunitySearch | null>(null);
  const [communitySearching, setCommunitySearching] = useState(false);
  const [communitySearchOpen, setCommunitySearchOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [pendingPostActions, setPendingPostActions] = useState<Set<string>>(() => new Set());
  const [pendingFollowIds, setPendingFollowIds] = useState<Set<string>>(() => new Set());
  const [error, setError] = useState('');
  const [composerOpen, setComposerOpen] = useState(false);
  const [editingPost, setEditingPost] = useState<ApiCommunityPost | null>(null);
  const [postTitle, setPostTitle] = useState('');
  const [postContent, setPostContent] = useState('');
  const [postType, setPostType] = useState<CommunityPostType>('experience');
  const [postVisibility, setPostVisibility] = useState<CommunityPostVisibility>('public');
  const [postTags, setPostTags] = useState('');
  const [postCaseData, setPostCaseData] = useState<Record<string, string | number | null>>({});
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [communityImagePreparationCount, setCommunityImagePreparationCount] = useState(0);
  const [existingAssets, setExistingAssets] = useState<ApiCommunityUpload[]>([]);
  const [posting, setPosting] = useState(false);
  const [selectedPost, setSelectedPost] = useState<ApiCommunityPost | null>(null);
  const [comments, setComments] = useState<ApiCommunityComment[]>([]);
  const [commentSort, setCommentSort] = useState<'top' | 'latest'>('top');
  const [commentsLoading, setCommentsLoading] = useState(false);
  const [commentDraft, setCommentDraft] = useState('');
  const [replyTo, setReplyTo] = useState<ApiCommunityComment | null>(null);
  const [editingComment, setEditingComment] = useState<ApiCommunityComment | null>(null);
  const [commentSending, setCommentSending] = useState(false);
  const [pendingCommentLikeIds, setPendingCommentLikeIds] = useState<Set<string>>(() => new Set());
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<ApiCommunityNotifications | null>(null);
  const [communityRealtimeStatus, setCommunityRealtimeStatus] = useState<'connecting' | 'live' | 'offline'>('connecting');
  const [deletePost, setDeletePost] = useState<ApiCommunityPost | null>(null);
  const [deleteComment, setDeleteComment] = useState<ApiCommunityComment | null>(null);
  const [communityConfirmAction, setCommunityConfirmAction] = useState<CommunityConfirmAction | null>(null);
  const [communityConfirmSubmitting, setCommunityConfirmSubmitting] = useState(false);
  const [reportPost, setReportPost] = useState<ApiCommunityPost | null>(null);
  const [profileAuthor, setProfileAuthor] = useState<ApiCommunityAuthor | null>(null);
  const [profilePosts, setProfilePosts] = useState<ApiCommunityPost[]>([]);
  const [profilePublicMode, setProfilePublicMode] = useState(false);
  const [relationshipDialog, setRelationshipDialog] = useState<{ author: ApiCommunityAuthor; type: CommunityRelationshipType } | null>(null);
  const [relationshipResult, setRelationshipResult] = useState<ApiCommunityRelationshipList | null>(null);
  const [relationshipLoading, setRelationshipLoading] = useState(false);
  const [relationshipLoadingMore, setRelationshipLoadingMore] = useState(false);
  const [blockedUsersOpen, setBlockedUsersOpen] = useState(false);
  const [blockedUsers, setBlockedUsers] = useState<ApiCommunityAuthor[]>([]);
  const [blockedUsersLoading, setBlockedUsersLoading] = useState(false);
  const [pendingUnblockIds, setPendingUnblockIds] = useState<Set<string>>(() => new Set());
  const [creatorOverview, setCreatorOverview] = useState<ApiCommunityCreatorOverview | null>(null);
  const [directMessagesOpen, setDirectMessagesOpen] = useState(false);
  const [directThreads, setDirectThreads] = useState<ApiCommunityDirectThread[]>([]);
  const [activeDirectThread, setActiveDirectThread] = useState<ApiCommunityDirectThread | null>(null);
  const [directRecipient, setDirectRecipient] = useState<ApiCommunityAuthor | null>(null);
  const [directMessages, setDirectMessages] = useState<ApiCommunityDirectMessage[]>([]);
  const [directMessageDraft, setDirectMessageDraft] = useState('');
  const [directMessagesLoading, setDirectMessagesLoading] = useState(false);
  const [directMessageSending, setDirectMessageSending] = useState(false);
  const [collectionsOpen, setCollectionsOpen] = useState(false);
  const [collectionTargetPost, setCollectionTargetPost] = useState<ApiCommunityPost | null>(null);
  const [bookmarkCollections, setBookmarkCollections] = useState<ApiCommunityBookmarkCollection[]>([]);
  const [selectedBookmarkCollection, setSelectedBookmarkCollection] = useState<ApiCommunityBookmarkCollectionDetail | null>(null);
  const [collectionsLoading, setCollectionsLoading] = useState(false);
  const [collectionSaving, setCollectionSaving] = useState(false);
  const [caseUpdatePost, setCaseUpdatePost] = useState<ApiCommunityPost | null>(null);
  const [saveCasePost, setSaveCasePost] = useState<ApiCommunityPost | null>(null);
  const [farms, setFarms] = useState<ApiFarm[]>([]);
  const [batches, setBatches] = useState<ApiSilkwormBatch[]>([]);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const preparingCommunityImages = communityImagePreparationCount > 0;

  const withCommunityAuth = async <T,>(operation: (token: string) => Promise<T>): Promise<T> => {
    if (!accessToken) {
      onRequireAuth();
      throw new Error('请先登录');
    }
    try {
      return await operation(accessToken);
    } catch (requestError) {
      if (!isUnauthorizedError(requestError)) throw requestError;
      try {
        const refreshed = await onTokenRefresh();
        return await operation(refreshed.accessToken);
      } catch {
        onAuthExpired();
        throw new Error('登录状态已失效');
      }
    }
  };

  const replacePost = (nextPost: ApiCommunityPost) => {
    setPosts((currentPosts) => currentPosts.map((post) => (post.id === nextPost.id ? nextPost : post)));
    setSelectedPost((currentPost) => (currentPost?.id === nextPost.id ? nextPost : currentPost));
  };

  const replaceCommunityAuthor = (nextAuthor: ApiCommunityAuthor) => {
    setPosts((currentPosts) => currentPosts.map((post) => (post.author.id === nextAuthor.id ? { ...post, author: nextAuthor } : post)));
    setSelectedPost((currentPost) => (currentPost?.author.id === nextAuthor.id ? { ...currentPost, author: nextAuthor } : currentPost));
    setProfileAuthor((currentAuthor) => (currentAuthor?.id === nextAuthor.id ? nextAuthor : currentAuthor));
    setCommunitySearchResults((current) => current ? { ...current, authors: current.authors.map((author) => (author.id === nextAuthor.id ? nextAuthor : author)) } : current);
    setRelationshipResult((current) => current ? {
      ...current,
      author: current.author.id === nextAuthor.id ? nextAuthor : current.author,
      items: current.items.map((author) => (author.id === nextAuthor.id ? nextAuthor : author)),
    } : current);
  };

  const loadFeed = async (offset = 0, append = false) => {
    if (!accessToken) return;
    append ? setLoadingMore(true) : setLoading(true);
    try {
      const response = await withCommunityAuth((token) =>
        fetchCommunityFeed(token, {
          tab: feedTab,
          query: searchQuery,
          tag: selectedTag,
          postType: contentFilter,
          questionStatus: contentFilter === 'question' ? questionFilter : '',
          region: debouncedRegionFilter,
          offset,
        }),
      );
      setPosts((currentPosts) => (append ? [...currentPosts, ...response.items] : response.items));
      setNextOffset(response.next_offset);
      setError('');
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '社区内容加载失败');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  const clearHistory = async () => {
    try {
      await withCommunityAuth(clearCommunityViewHistory);
      setPosts([]);
      setNextOffset(null);
      onNotify('浏览记录已清空', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '清空浏览记录失败', 'error');
    }
  };

  const resetRecommendationPreferences = async () => {
    try {
      await withCommunityAuth(resetCommunityRecommendations);
      setFeedTab('recommended');
      setSelectedTag('');
      setSearchQuery('');
      setSearchDraft('');
      setCommunitySearchResults(null);
      onNotify('推荐偏好已重置', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '推荐偏好重置失败', 'error');
    }
  };

  const confirmCommunityAction = async () => {
    if (!communityConfirmAction || communityConfirmSubmitting) return;
    setCommunityConfirmSubmitting(true);
    try {
      if (communityConfirmAction === 'clear_history') await clearHistory();
      else await resetRecommendationPreferences();
      setCommunityConfirmAction(null);
    } finally {
      setCommunityConfirmSubmitting(false);
    }
  };

  const runCommunitySearch = async (query: string) => {
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      setCommunitySearchResults(null);
      setCommunitySearchOpen(false);
      return;
    }
    setCommunitySearchOpen(true);
    setCommunitySearching(true);
    try {
      const results = await withCommunityAuth((token) => searchCommunity(token, normalizedQuery));
      setCommunitySearchResults(results);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '社区搜索失败', 'error');
    } finally {
      setCommunitySearching(false);
    }
  };

  useEffect(() => {
    if (!accessToken) return;
    void loadFeed();
  }, [accessToken, feedTab, searchQuery, selectedTag, contentFilter, questionFilter, debouncedRegionFilter]);

  useEffect(() => {
    if (!accessToken) return;
    void withCommunityAuth(fetchCommunityTags)
      .then((nextTags) => setTags(nextTags))
      .catch(() => undefined);
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) {
      setCommunityRealtimeStatus('offline');
      return;
    }
    const controller = new AbortController();
    let retryTimer: number | undefined;
    let reconciliationTimer: number | undefined;

    const refreshThreads = () => void withCommunityAuth(fetchCommunityDirectThreads)
      .then((response) => setDirectThreads(response.items))
      .catch(() => undefined);
    const refreshActiveThreadMessages = (threadId: string) => {
      if (!directMessagesOpen || activeDirectThread?.id !== threadId) return;
      void withCommunityAuth((token) => fetchCommunityDirectMessages(token, threadId))
        .then((response) => {
          setDirectMessages(response.items);
          setDirectThreads((items) => items.map((item) => (
            item.id === threadId ? { ...item, unread_count: 0 } : item
          )));
        })
        .catch(() => undefined);
    };
    const refreshNotifications = () => void withCommunityAuth(fetchCommunityNotifications)
      .then(setNotifications)
      .catch(() => undefined);
    const scheduleReconnect = (token: string) => {
      if (controller.signal.aborted) return;
      retryTimer = window.setTimeout(() => void connect(token), 1_500);
    };
    const connect = async (token: string) => {
      setCommunityRealtimeStatus('connecting');
      try {
        await streamCommunityEvents(token, controller.signal, (event) => {
          if (event.type === 'ready') {
            setCommunityRealtimeStatus('live');
            return;
          }
          if (event.type !== 'notification') return;
          refreshNotifications();
          if (event.notification_type === 'direct_message') {
            refreshThreads();
            const threadId = typeof event.payload?.thread_id === 'string' ? event.payload.thread_id : '';
            if (threadId) refreshActiveThreadMessages(threadId);
          }
        });
        if (!controller.signal.aborted) {
          setCommunityRealtimeStatus('offline');
          scheduleReconnect(token);
        }
      } catch (streamError) {
        if (controller.signal.aborted) return;
        if (isUnauthorizedError(streamError)) {
          try {
            const refreshed = await onTokenRefresh();
            scheduleReconnect(refreshed.accessToken);
            return;
          } catch {
            onAuthExpired();
            return;
          }
        }
        setCommunityRealtimeStatus('offline');
        scheduleReconnect(token);
      }
    };

    refreshThreads();
    refreshNotifications();
    void connect(accessToken);
    // A slow reconciliation handles background-tab reconnects without
    // reintroducing the old high-frequency polling behavior.
    reconciliationTimer = window.setInterval(() => {
      refreshThreads();
      refreshNotifications();
    }, 300_000);
    return () => {
      controller.abort();
      if (retryTimer) window.clearTimeout(retryTimer);
      if (reconciliationTimer) window.clearInterval(reconciliationTimer);
    };
  }, [accessToken, activeDirectThread?.id, directMessagesOpen]);

  useEffect(() => {
    if (!accessToken || !currentUser) return;
    void withCommunityAuth(fetchCommunityCreatorOverview)
      .then(setCreatorOverview)
      .catch(() => undefined);
  }, [accessToken, currentUser?.id]);

  useEffect(() => {
    if (!draftPost) return;
    setEditingPost(draftPost);
    setPostTitle(draftPost.title);
    setPostContent(draftPost.content_markdown);
    setPostType(draftPost.post_type);
    setPostVisibility(draftPost.visibility);
    setPostTags(draftPost.tags.map((tag) => tag.name).join(' '));
    setPostCaseData(draftPost.case_data ?? {});
    setExistingAssets(
      draftPost.assets.map((asset) => ({
        file_id: asset.file_id,
        file_name: asset.file_name,
        file_type: asset.file_type,
        mime_type: asset.mime_type,
        storage_url: asset.storage_url,
        file_size: asset.file_size,
      })),
    );
    setPendingFiles([]);
    setComposerOpen(true);
    onDraftConsumed();
  }, [draftPost, onDraftConsumed]);

  const openComposer = (post: ApiCommunityPost | null = null) => {
    setEditingPost(post);
    setPostTitle(post?.title ?? '');
    setPostContent(post?.content_markdown ?? '');
    setPostType(post?.post_type ?? 'experience');
    setPostVisibility(post?.visibility ?? 'public');
    setPostTags(post?.tags.map((tag) => tag.name).join(' ') ?? '');
    setPostCaseData(post?.case_data ?? {});
    setExistingAssets(
      post?.assets.map((asset) => ({
        file_id: asset.file_id,
        file_name: asset.file_name,
        file_type: asset.file_type,
        mime_type: asset.mime_type,
        storage_url: asset.storage_url,
        file_size: asset.file_size,
      })) ?? [],
    );
    setPendingFiles([]);
    setComposerOpen(true);
  };

  const closeComposer = () => {
    if (posting || preparingCommunityImages) return;
    setComposerOpen(false);
    setEditingPost(null);
    setPendingFiles([]);
  };

  const handleCommunityFilesSelected = async (files: File[]) => {
    const selectedFiles = files.slice(0, 9);
    if (!selectedFiles.length) return;

    const hasImages = selectedFiles.some((file) => file.type.startsWith('image/'));
    if (hasImages) setCommunityImagePreparationCount((count) => count + 1);
    try {
      const preparedFiles = await Promise.all(selectedFiles.map((file) => prepareImageForUpload(file)));
      setPendingFiles((currentFiles) => [...currentFiles, ...preparedFiles.map((prepared) => prepared.file)].slice(0, 9));
    } finally {
      if (hasImages) setCommunityImagePreparationCount((count) => Math.max(0, count - 1));
    }
  };

  const submitPost = async (publish: boolean) => {
    if (preparingCommunityImages) return;
    const normalizedTitle = postTitle.trim();
    if (!normalizedTitle) {
      onNotify('请填写帖子标题', 'error');
      return;
    }
    setPosting(true);
    try {
      const uploaded = pendingFiles.length > 0 ? await withCommunityAuth((token) => uploadCommunityAttachments(token, pendingFiles)) : [];
      const files = [...existingAssets, ...uploaded];
      const tagsValue = Array.from(
        new Set(
          postTags
            .split(/[\s,#，、]+/)
            .map((tag) => tag.trim())
            .filter(Boolean),
        ),
      );
      const nextPost = editingPost
        ? await withCommunityAuth((token) =>
            updateCommunityPost(token, editingPost.id, {
              title: normalizedTitle,
              contentMarkdown: postContent,
              postType,
              visibility: postVisibility,
              tags: tagsValue,
              fileIds: files.map((file) => file.file_id),
              coverFileId: files[0]?.file_id ?? null,
              publish,
              caseData: postType === 'case' ? postCaseData : {},
            }),
          )
        : await withCommunityAuth((token) =>
            createCommunityPost(token, {
              title: normalizedTitle,
              contentMarkdown: postContent,
              postType,
              visibility: postVisibility,
              tags: tagsValue,
              fileIds: files.map((file) => file.file_id),
              coverFileId: files[0]?.file_id ?? null,
              publish,
              caseData: postType === 'case' ? postCaseData : {},
            }),
          );
      setComposerOpen(false);
      setEditingPost(null);
      setPendingFiles([]);
      setExistingAssets([]);
      if (nextPost.status === 'published') {
        setPosts((currentPosts) => [nextPost, ...currentPosts.filter((post) => post.id !== nextPost.id)]);
        setSelectedPost(nextPost);
        onNotify('帖子已发布到社区，已显示在当前信息流顶部', 'success');
      } else {
        onNotify('已保存到草稿箱，请在“草稿”中继续编辑或发布', 'success');
        if (feedTab === 'drafts') {
          setPosts((currentPosts) => [nextPost, ...currentPosts.filter((post) => post.id !== nextPost.id)]);
        }
      }
      void withCommunityAuth(fetchCommunityTags).then(setTags).catch(() => undefined);
      if (currentUser) void withCommunityAuth(fetchCommunityCreatorOverview).then(setCreatorOverview).catch(() => undefined);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '帖子保存失败', 'error');
    } finally {
      setPosting(false);
    }
  };

  const openPost = async (postId: string) => {
    try {
      setCommentsLoading(true);
      const [post, commentResult] = await Promise.all([
        withCommunityAuth((token) => fetchCommunityPost(token, postId)),
        withCommunityAuth((token) => fetchCommunityComments(token, postId, 'top')),
      ]);
      setSelectedPost(post);
      setComments(commentResult.items);
      setCommentSort('top');
      setCommentDraft('');
      setReplyTo(null);
      setEditingComment(null);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '帖子打开失败', 'error');
    } finally {
      setCommentsLoading(false);
    }
  };

  const changeCommentSort = async (sort: 'top' | 'latest') => {
    if (!selectedPost || sort === commentSort) return;
    setCommentSort(sort);
    setCommentsLoading(true);
    try {
      const result = await withCommunityAuth((token) => fetchCommunityComments(token, selectedPost.id, sort));
      setComments(result.items);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '评论排序加载失败', 'error');
    } finally {
      setCommentsLoading(false);
    }
  };

  useEffect(() => {
    if (!accessToken) return;
    const postId = new URLSearchParams(window.location.search).get('community_post');
    if (postId) void openPost(postId);
  }, [accessToken]);

  const handlePostReaction = async (postId: string, action: 'like' | 'bookmark') => {
    const actionKey = `${postId}:${action}`;
    if (pendingPostActions.has(actionKey)) return;
    const currentPost = selectedPost?.id === postId ? selectedPost : posts.find((post) => post.id === postId);
    const optimisticPost = currentPost ? {
      ...currentPost,
      ...(action === 'like'
        ? { is_liked: !currentPost.is_liked, like_count: Math.max(0, currentPost.like_count + (currentPost.is_liked ? -1 : 1)) }
        : { is_bookmarked: !currentPost.is_bookmarked, bookmark_count: Math.max(0, currentPost.bookmark_count + (currentPost.is_bookmarked ? -1 : 1)) }),
    } : null;
    if (optimisticPost) replacePost(optimisticPost);
    setPendingPostActions((current) => new Set(current).add(actionKey));
    try {
      const nextPost = await withCommunityAuth((token) =>
        action === 'like' ? toggleCommunityPostLike(token, postId) : toggleCommunityPostBookmark(token, postId),
      );
      replacePost(nextPost);
    } catch (requestError) {
      if (currentPost) replacePost(currentPost);
      onNotify(requestError instanceof Error ? requestError.message : '互动失败', 'error');
    } finally {
      setPendingPostActions((current) => {
        const next = new Set(current);
        next.delete(actionKey);
        return next;
      });
    }
  };

  const shareCommunityPost = async (post: ApiCommunityPost) => {
    const shareUrl = new URL(window.location.href);
    shareUrl.searchParams.set('community_post', post.id);
    const sharePayload = {
      title: post.title,
      text: post.excerpt || post.content_markdown.slice(0, 120),
      url: shareUrl.toString(),
    };
    try {
      if (navigator.share) {
        await navigator.share(sharePayload);
      } else {
        await copyTextToClipboard(sharePayload.url);
        onNotify('帖子链接已复制，可发送给社区同行', 'success');
      }
    } catch (shareError) {
      if (shareError instanceof DOMException && shareError.name === 'AbortError') return;
      try {
        await copyTextToClipboard(sharePayload.url);
        onNotify('分享面板不可用，已复制帖子链接', 'success');
      } catch {
        onNotify('帖子链接复制失败，请稍后重试', 'error');
      }
    }
  };

  const handleFollow = async (authorId: string) => {
    if (pendingFollowIds.has(authorId)) return;
    const currentAuthor = profileAuthor?.id === authorId
      ? profileAuthor
      : selectedPost?.author.id === authorId
        ? selectedPost.author
        : posts.find((post) => post.author.id === authorId)?.author
          ?? communitySearchResults?.authors.find((author) => author.id === authorId)
          ?? relationshipResult?.items.find((author) => author.id === authorId);
    const optimisticAuthor = currentAuthor ? {
      ...currentAuthor,
      is_followed: !currentAuthor.is_followed,
      follower_count: Math.max(0, currentAuthor.follower_count + (currentAuthor.is_followed ? -1 : 1)),
    } : null;
    if (optimisticAuthor) replaceCommunityAuthor(optimisticAuthor);
    setPendingFollowIds((current) => new Set(current).add(authorId));
    try {
      const updatedAuthor = await withCommunityAuth((token) => toggleCommunityFollow(token, authorId));
      replaceCommunityAuthor(updatedAuthor);
      if (currentUser) void withCommunityAuth(fetchCommunityCreatorOverview).then(setCreatorOverview).catch(() => undefined);
    } catch (requestError) {
      if (currentAuthor) replaceCommunityAuthor(currentAuthor);
      onNotify(requestError instanceof Error ? requestError.message : '关注失败', 'error');
    } finally {
      setPendingFollowIds((current) => {
        const next = new Set(current);
        next.delete(authorId);
        return next;
      });
    }
  };

  const openProfile = async (authorId: string, publicMode = false) => {
    try {
      const [detail, overview] = await Promise.all([
        withCommunityAuth((token) => fetchCommunityProfileDetail(token, authorId)),
        authorId === currentUser?.id ? withCommunityAuth(fetchCommunityCreatorOverview) : Promise.resolve(null),
      ]);
      setProfileAuthor(detail.author);
      setProfilePosts(detail.posts);
      setProfilePublicMode(publicMode);
      if (overview) setCreatorOverview(overview);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '资料加载失败', 'error');
    }
  };

  const openRelationships = async (author: ApiCommunityAuthor, relationshipType: CommunityRelationshipType, offset = 0, append = false) => {
    append ? setRelationshipLoadingMore(true) : setRelationshipLoading(true);
    if (!append) {
      setRelationshipDialog({ author, type: relationshipType });
      setRelationshipResult(null);
    }
    try {
      const response = await withCommunityAuth((token) => fetchCommunityRelationships(token, author.id, relationshipType, offset));
      setRelationshipDialog({ author: response.author, type: response.relationship_type });
      setRelationshipResult((current) => append && current ? { ...response, items: [...current.items, ...response.items] } : response);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '关注列表加载失败', 'error');
      if (!append) setRelationshipDialog(null);
    } finally {
      setRelationshipLoading(false);
      setRelationshipLoadingMore(false);
    }
  };

  const openCurrentUserRelationships = async (relationshipType: CommunityRelationshipType) => {
    if (!currentUser) return;
    try {
      const detail = await withCommunityAuth((token) => fetchCommunityProfileDetail(token, currentUser.id));
      void openRelationships(detail.author, relationshipType);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '个人主页加载失败', 'error');
    }
  };

  const openBlockedUsers = async () => {
    setBlockedUsersOpen(true);
    setBlockedUsersLoading(true);
    try {
      const response = await withCommunityAuth(fetchCommunityBlockedUsers);
      setBlockedUsers(response.items);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '已屏蔽用户加载失败', 'error');
    } finally {
      setBlockedUsersLoading(false);
    }
  };

  const handleUnblockUser = async (author: ApiCommunityAuthor) => {
    if (pendingUnblockIds.has(author.id)) return;
    setPendingUnblockIds((current) => new Set(current).add(author.id));
    try {
      const result = await withCommunityAuth((token) => toggleCommunityUserBlock(token, author.id));
      if (!result.blocked) {
        setBlockedUsers((items) => items.filter((item) => item.id !== author.id));
        onNotify(`已解除屏蔽 ${author.display_name}`, 'success');
      }
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '解除屏蔽失败', 'error');
    } finally {
      setPendingUnblockIds((current) => {
        const next = new Set(current);
        next.delete(author.id);
        return next;
      });
    }
  };

  const handleTopicFollow = async (tag: ApiCommunityTag) => {
    const optimisticTag = { ...tag, is_followed: !tag.is_followed };
    setTags((items) => items.map((item) => (item.id === tag.id ? optimisticTag : item)));
    setCommunitySearchResults((current) => current ? { ...current, tags: current.tags.map((item) => (item.id === tag.id ? optimisticTag : item)) } : current);
    try {
      const nextTag = await withCommunityAuth((token) => toggleCommunityTopicFollow(token, tag.id));
      setTags((items) => items.map((item) => (item.id === nextTag.id ? nextTag : item)));
      setCommunitySearchResults((current) => current ? { ...current, tags: current.tags.map((item) => (item.id === nextTag.id ? nextTag : item)) } : current);
      onNotify(nextTag.is_followed ? `已关注话题 #${nextTag.name}` : `已取消关注话题 #${nextTag.name}`, 'success');
    } catch (requestError) {
      setTags((items) => items.map((item) => (item.id === tag.id ? tag : item)));
      setCommunitySearchResults((current) => current ? { ...current, tags: current.tags.map((item) => (item.id === tag.id ? tag : item)) } : current);
      onNotify(requestError instanceof Error ? requestError.message : '话题设置失败', 'error');
    }
  };

  const openBookmarkCollections = async (post: ApiCommunityPost | null = null) => {
    setCollectionsOpen(true);
    setCollectionTargetPost(post);
    setSelectedBookmarkCollection(null);
    setCollectionsLoading(true);
    try {
      const response = await withCommunityAuth((token) => fetchCommunityBookmarkCollections(token, post?.id ?? ''));
      setBookmarkCollections(response.items);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '收藏夹加载失败', 'error');
    } finally {
      setCollectionsLoading(false);
    }
  };

  const openBookmarkCollectionDetail = async (collectionId: string) => {
    try {
      const detail = await withCommunityAuth((token) => fetchCommunityBookmarkCollectionDetail(token, collectionId));
      setSelectedBookmarkCollection(detail);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '收藏内容加载失败', 'error');
    }
  };

  const saveBookmarkCollection = async (collectionId: string | null, name: string, description: string) => {
    setCollectionSaving(true);
    try {
      const collection = collectionId
        ? await withCommunityAuth((token) => updateCommunityBookmarkCollection(token, collectionId, name, description))
        : await withCommunityAuth((token) => createCommunityBookmarkCollection(token, name, description));
      setBookmarkCollections((items) => collectionId ? items.map((item) => (item.id === collection.id ? { ...item, ...collection } : item)) : [collection, ...items]);
      if (collectionId && selectedBookmarkCollection?.collection.id === collection.id) {
        setSelectedBookmarkCollection((detail) => detail ? { ...detail, collection: { ...detail.collection, ...collection } } : detail);
      }
      onNotify(collectionId ? '收藏夹已更新' : '已新建收藏夹', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '收藏夹保存失败', 'error');
      throw requestError;
    } finally {
      setCollectionSaving(false);
    }
  };

  const removeBookmarkCollection = async (collectionId: string) => {
    try {
      await withCommunityAuth((token) => deleteCommunityBookmarkCollection(token, collectionId));
      setBookmarkCollections((items) => items.filter((item) => item.id !== collectionId));
      setSelectedBookmarkCollection((detail) => detail?.collection.id === collectionId ? null : detail);
      onNotify('收藏夹已删除，原收藏内容不会受影响', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '删除收藏夹失败', 'error');
    }
  };

  const togglePostInBookmarkCollection = async (collectionId: string) => {
    if (!collectionTargetPost) return;
    try {
      const collection = await withCommunityAuth((token) => toggleCommunityBookmarkCollectionPost(token, collectionId, collectionTargetPost.id));
      setBookmarkCollections((items) => items.map((item) => (item.id === collection.id ? { ...item, ...collection } : item)));
      const refreshedPost = await withCommunityAuth((token) => fetchCommunityPost(token, collectionTargetPost.id));
      setCollectionTargetPost(refreshedPost);
      replacePost(refreshedPost);
      onNotify(collection.contains_post ? `已归入“${collection.name}”` : `已从“${collection.name}”移除`, 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '收藏夹操作失败', 'error');
    }
  };

  const submitComment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedPost || !commentDraft.trim() || commentSending) return;
    setCommentSending(true);
    try {
      if (editingComment) {
        const comment = await withCommunityAuth((token) => updateCommunityComment(token, editingComment.id, commentDraft.trim()));
        setComments((currentComments) => currentComments.map((item) => (item.id === comment.id ? comment : item)));
        setCommentDraft('');
        setEditingComment(null);
        onNotify('评论已更新', 'success');
        return;
      }
      const comment = await withCommunityAuth((token) =>
        createCommunityComment(token, selectedPost.id, commentDraft.trim(), replyTo?.id ?? null),
      );
      setComments((currentComments) => [...currentComments, comment]);
      setSelectedPost((currentPost) =>
        currentPost ? { ...currentPost, comment_count: currentPost.comment_count + 1 } : currentPost,
      );
      setPosts((currentPosts) =>
        currentPosts.map((post) => (post.id === selectedPost.id ? { ...post, comment_count: post.comment_count + 1 } : post)),
      );
      setCommentDraft('');
      setReplyTo(null);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '评论发布失败', 'error');
    } finally {
      setCommentSending(false);
    }
  };

  const handleCommentLike = async (commentId: string) => {
    if (pendingCommentLikeIds.has(commentId)) return;
    const currentComment = comments.find((comment) => comment.id === commentId);
    const optimisticComment = currentComment ? {
      ...currentComment,
      is_liked: !currentComment.is_liked,
      like_count: Math.max(0, currentComment.like_count + (currentComment.is_liked ? -1 : 1)),
    } : null;
    if (optimisticComment) setComments((currentComments) => currentComments.map((comment) => (comment.id === commentId ? optimisticComment : comment)));
    setPendingCommentLikeIds((current) => new Set(current).add(commentId));
    try {
      const nextComment = await withCommunityAuth((token) => toggleCommunityCommentLike(token, commentId));
      setComments((currentComments) => currentComments.map((comment) => (comment.id === commentId ? nextComment : comment)));
    } catch (requestError) {
      if (currentComment) setComments((currentComments) => currentComments.map((comment) => (comment.id === commentId ? currentComment : comment)));
      onNotify(requestError instanceof Error ? requestError.message : '评论互动失败', 'error');
    } finally {
      setPendingCommentLikeIds((current) => {
        const next = new Set(current);
        next.delete(commentId);
        return next;
      });
    }
  };

  const beginCommentEdit = (comment: ApiCommunityComment) => {
    if (!comment.is_author || comment.status !== 'active') return;
    setReplyTo(null);
    setEditingComment(comment);
    setCommentDraft(comment.content);
  };

  const cancelCommentAction = () => {
    setReplyTo(null);
    setEditingComment(null);
    setCommentDraft('');
  };

  const requestCommentDelete = (commentId: string) => {
    const comment = comments.find((item) => item.id === commentId);
    if (comment) setDeleteComment(comment);
  };

  const confirmDeleteComment = async () => {
    const comment = deleteComment;
    if (!comment) return;
    const commentId = comment.id;
    try {
      await withCommunityAuth((token) => deleteCommunityComment(token, commentId));
      setComments((items) => items.map((item) => (
        item.id === commentId
          ? { ...item, content: '该评论已删除', status: 'deleted', is_accepted: false }
          : item
      )));
      setSelectedPost((currentPost) => currentPost ? {
        ...currentPost,
        comment_count: Math.max(0, currentPost.comment_count - 1),
        ...(comment.is_accepted ? { question_status: 'open' } : {}),
      } : currentPost);
      setPosts((items) => items.map((post) => (
        post.id === selectedPost?.id
          ? {
              ...post,
              comment_count: Math.max(0, post.comment_count - 1),
              ...(comment.is_accepted ? { question_status: 'open' } : {}),
            }
          : post
      )));
      if (editingComment?.id === commentId) cancelCommentAction();
      setDeleteComment(null);
      onNotify('评论已删除', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '删除评论失败', 'error');
    }
  };

  const handleAcceptAnswer = async (commentId: string) => {
    if (!selectedPost) return;
    try {
      const nextPost = await withCommunityAuth((token) => acceptCommunityAnswer(token, selectedPost.id, commentId));
      replacePost(nextPost);
      setComments((items) => items.map((item) => ({ ...item, is_accepted: item.id === commentId })));
      onNotify('已采纳回答，问题已标记为解决', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '采纳回答失败', 'error');
    }
  };

  const handleCaseUpdate = async (payload: { occurred_on: string; outcome_status: ApiCommunityCaseUpdate['outcome_status']; content: string }) => {
    if (!caseUpdatePost) return;
    try {
      await withCommunityAuth((token) => addCommunityCaseUpdate(token, caseUpdatePost.id, payload));
      const nextPost = await withCommunityAuth((token) => fetchCommunityPost(token, caseUpdatePost.id));
      replacePost(nextPost);
      setCaseUpdatePost(null);
      onNotify('病例随访已加入时间线', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '随访保存失败', 'error');
    }
  };

  const handleProfileSave = async (payload: Parameters<typeof updateCommunityProfile>[1]) => {
    try {
      const nextAuthor = await withCommunityAuth((token) => updateCommunityProfile(token, payload));
      setPosts((items) => items.map((post) => (post.author.id === nextAuthor.id ? { ...post, author: nextAuthor } : post)));
      setSelectedPost((post) => (post?.author.id === nextAuthor.id ? { ...post, author: nextAuthor } : post));
      setProfileAuthor(nextAuthor);
      onNotify(payload.request_verification ? '资料已保存，认证申请已提交' : '社区资料已保存', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '资料保存失败', 'error');
    }
  };

  const handleNotInterested = async (post: ApiCommunityPost) => {
    try {
      await withCommunityAuth((token) => hideCommunityPost(token, post.id));
      setPosts((items) => items.filter((item) => item.id !== post.id));
      setSelectedPost(null);
      onNotify('已减少此类内容推荐', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '设置失败', 'error');
    }
  };

  const handleBlockAuthor = async (author: ApiCommunityAuthor) => {
    try {
      const result = await withCommunityAuth((token) => toggleCommunityUserBlock(token, author.id));
      if (result.blocked) {
        setPosts((items) => items.filter((post) => post.author.id !== author.id));
        setSelectedPost(null);
      }
      setProfileAuthor(null);
      onNotify(result.blocked ? `已屏蔽 ${author.display_name}` : `已取消屏蔽 ${author.display_name}`, 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '屏蔽设置失败', 'error');
    }
  };

  const openSaveToHusbandry = async (post: ApiCommunityPost) => {
    try {
      const [nextFarms, nextBatches] = await Promise.all([
        withCommunityAuth(fetchHusbandryFarms),
        withCommunityAuth(fetchSilkwormBatches),
      ]);
      setFarms(nextFarms);
      setBatches(nextBatches);
      setSaveCasePost(post);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '养殖台账加载失败', 'error');
    }
  };

  const handleSaveToHusbandry = async (farmId: string, batchId: string | null) => {
    if (!saveCasePost) return;
    try {
      await withCommunityAuth((token) => saveCommunityPostToHusbandry(token, saveCasePost.id, farmId, batchId));
      setSaveCasePost(null);
      onNotify('病例已保存到养殖台账，可继续记录处置和随访', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '保存到台账失败', 'error');
    }
  };

  const openDirectThread = async (thread: ApiCommunityDirectThread) => {
    setActiveDirectThread(thread);
    setDirectRecipient(thread.counterpart);
    setDirectMessagesLoading(true);
    try {
      const response = await withCommunityAuth((token) => fetchCommunityDirectMessages(token, thread.id));
      setDirectMessages(response.items);
      setDirectThreads((items) => items.map((item) => (item.id === thread.id ? { ...item, unread_count: 0 } : item)));
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '私信加载失败', 'error');
    } finally {
      setDirectMessagesLoading(false);
    }
  };

  const openDirectMessages = async (recipient: ApiCommunityAuthor | null = null, threadId = '') => {
    setDirectMessagesOpen(true);
    setDirectRecipient(recipient);
    setDirectMessages([]);
    setDirectMessageDraft('');
    try {
      const response = await withCommunityAuth(fetchCommunityDirectThreads);
      setDirectThreads(response.items);
      const thread = threadId ? response.items.find((item) => item.id === threadId) : recipient ? response.items.find((item) => item.counterpart.id === recipient.id) : response.items[0];
      if (thread) {
        await openDirectThread(thread);
      } else {
        setActiveDirectThread(null);
      }
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '私信列表加载失败', 'error');
    }
  };

  const sendDirectMessage = async () => {
    const recipient = activeDirectThread?.counterpart ?? directRecipient;
    const content = directMessageDraft.trim();
    if (!recipient || !content || directMessageSending) return;
    setDirectMessageSending(true);
    try {
      const message = await withCommunityAuth((token) => sendCommunityDirectMessage(token, recipient.id, content));
      setDirectMessages((items) => [...items, message]);
      setDirectMessageDraft('');
      const nextThreads = await withCommunityAuth(fetchCommunityDirectThreads);
      setDirectThreads(nextThreads.items);
      const thread = nextThreads.items.find((item) => item.id === message.thread_id);
      if (thread) setActiveDirectThread(thread);
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '私信发送失败', 'error');
    } finally {
      setDirectMessageSending(false);
    }
  };

  const openNotifications = async () => {
    setNotificationsOpen(true);
    try {
      const nextNotifications = await withCommunityAuth(fetchCommunityNotifications);
      setNotifications(nextNotifications);
      if (nextNotifications.unread_count > 0) {
        await withCommunityAuth(markCommunityNotificationsRead);
        setNotifications((current) => (current ? { ...current, unread_count: 0 } : current));
      }
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '通知加载失败', 'error');
    }
  };

  const confirmDeletePost = async () => {
    if (!deletePost) return;
    try {
      await withCommunityAuth((token) => deleteCommunityPost(token, deletePost.id));
      setPosts((currentPosts) => currentPosts.filter((post) => post.id !== deletePost.id));
      setSelectedPost((currentPost) => (currentPost?.id === deletePost.id ? null : currentPost));
      setDeletePost(null);
      onNotify('帖子已删除', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '删除失败', 'error');
    }
  };

  const submitReport = async (reason: string, detail: string) => {
    if (!reportPost) return;
    try {
      await withCommunityAuth((token) => reportCommunityPost(token, reportPost.id, reason, detail));
      setReportPost(null);
      onNotify('举报已提交，社区会尽快处理', 'success');
    } catch (requestError) {
      onNotify(requestError instanceof Error ? requestError.message : '举报提交失败', 'error');
    }
  };

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (saveCasePost) { setSaveCasePost(null); return; }
      if (caseUpdatePost) { setCaseUpdatePost(null); return; }
      if (relationshipDialog) { setRelationshipDialog(null); return; }
      if (communitySearchOpen) { setCommunitySearchOpen(false); return; }
      if (collectionsOpen) {
        setCollectionsOpen(false);
        setCollectionTargetPost(null);
        setSelectedBookmarkCollection(null);
        return;
      }
      if (blockedUsersOpen) { setBlockedUsersOpen(false); return; }
      if (directMessagesOpen) { setDirectMessagesOpen(false); return; }
      if (profileAuthor) {
        setProfileAuthor(null);
        setProfilePublicMode(false);
        return;
      }
      if (reportPost) { setReportPost(null); return; }
      if (communityConfirmAction && !communityConfirmSubmitting) { setCommunityConfirmAction(null); return; }
      if (deleteComment) { setDeleteComment(null); return; }
      if (deletePost) { setDeletePost(null); return; }
      if (notificationsOpen) { setNotificationsOpen(false); return; }
      if (selectedPost) { setSelectedPost(null); return; }
      if (composerOpen && !posting && !preparingCommunityImages) closeComposer();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [
    caseUpdatePost,
    blockedUsersOpen,
    collectionsOpen,
    communitySearchOpen,
    communityConfirmAction,
    communityConfirmSubmitting,
    composerOpen,
    deleteComment,
    deletePost,
    directMessagesOpen,
    notificationsOpen,
    posting,
    preparingCommunityImages,
    profileAuthor,
    relationshipDialog,
    reportPost,
    saveCasePost,
    selectedPost,
  ]);

  const communityTabs: Array<{ key: CommunityFeedTab; label: string }> = [
    { key: 'recommended', label: '推荐' },
    { key: 'following', label: '关注' },
    { key: 'topics', label: '话题关注' },
    { key: 'latest', label: '最新' },
    { key: 'bookmarked', label: '收藏' },
    { key: 'liked', label: '赞过' },
    { key: 'history', label: '浏览记录' },
    { key: 'mine', label: '我的发布' },
    { key: 'drafts', label: '草稿' },
  ];

  return (
    <article className="community-workspace">
      <header className="community-topbar">
        <div>
          <span className="community-eyebrow">CanW Community</span>
          <h1>家蚕交流社区</h1>
          <p>交流观察、记录处理过程，沉淀可复核的养殖经验。</p>
        </div>
        <div className="community-top-actions">
          {currentUser && <button type="button" className="community-profile-button" onClick={() => void openProfile(currentUser.id, true)}><UserRound size={17} /><span>我的主页</span></button>}
          {currentUser && <button type="button" className="community-profile-button" onClick={() => void openBookmarkCollections()}><Bookmark size={17} /><span>收藏夹</span></button>}
          <span className={clsx('community-realtime-status', communityRealtimeStatus)} role="status" aria-live="polite" title={communityRealtimeStatus === 'live' ? '社区消息实时同步中' : communityRealtimeStatus === 'connecting' ? '正在连接社区实时服务' : '实时服务暂不可用，正在使用低频同步'}><i aria-hidden="true" /><span>{communityRealtimeStatus === 'live' ? '实时' : communityRealtimeStatus === 'connecting' ? '连接中' : '稍后同步'}</span></span>
          <button type="button" className="community-icon-button" aria-label="社区私信" title="社区私信" onClick={() => void openDirectMessages()}>
            <MessageSquarePlus size={18} />
            {directThreads.reduce((total, thread) => total + thread.unread_count, 0) > 0 ? <i>{directThreads.reduce((total, thread) => total + thread.unread_count, 0) > 9 ? '9+' : directThreads.reduce((total, thread) => total + thread.unread_count, 0)}</i> : null}
          </button>
          <button type="button" className="community-icon-button" aria-label="社区通知" title="社区通知" onClick={() => void openNotifications()}>
            <Bell size={18} />
            {notifications?.unread_count ? <i>{notifications.unread_count > 9 ? '9+' : notifications.unread_count}</i> : null}
          </button>
          <button type="button" className="community-publish-button" onClick={() => openComposer()}>
            <Plus size={17} />
            <span>发布帖子</span>
          </button>
        </div>
      </header>

      <section className="community-toolbar" aria-label="社区内容筛选">
        <div className="community-tabs" role="tablist">
          {communityTabs.map((tab) => (
            <button
              type="button"
              key={tab.key}
              role="tab"
              aria-selected={feedTab === tab.key}
              className={clsx(feedTab === tab.key && 'active')}
              onClick={() => {
                setFeedTab(tab.key);
                setSelectedTag('');
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {feedTab === 'history' && posts.length > 0 && <button type="button" className="community-history-clear" onClick={() => setCommunityConfirmAction('clear_history')}><Trash2 size={14} />清空记录</button>}
        <form
          className="community-search"
          onSubmit={(event) => {
            event.preventDefault();
            const nextQuery = searchDraft.trim();
            setSearchQuery(nextQuery);
            void runCommunitySearch(nextQuery);
          }}
        >
          <Search size={16} />
          <input value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} placeholder="搜索帖子、经验或症状" />
          {searchDraft && (
            <button type="button" aria-label="清除搜索" title="清除搜索" onClick={() => {
              setSearchDraft('');
              setSearchQuery('');
              setCommunitySearchResults(null);
              setCommunitySearchOpen(false);
            }}>
              <X size={14} />
            </button>
          )}
        </form>
      </section>

      <section className="community-discovery-filters" aria-label="内容类型筛选">
        <div>
          {([
            ['', '全部内容'],
            ['case', '病例'],
            ['question', '问答'],
            ['experience', '经验'],
            ['reference', '资料'],
          ] as Array<[CommunityPostType | '', string]>).map(([value, label]) => (
            <button type="button" key={value || 'all'} className={clsx(contentFilter === value && 'active')} onClick={() => {
              setContentFilter(value);
              if (value !== 'question') setQuestionFilter('');
            }}>{label}</button>
          ))}
        </div>
        {contentFilter === 'question' && <select aria-label="问题状态" value={questionFilter} onChange={(event) => setQuestionFilter(event.target.value as 'open' | 'resolved' | '')}><option value="">全部问题</option><option value="open">待解答</option><option value="resolved">已解决</option></select>}
        <label><Globe size={15} /><input value={regionFilter} onChange={(event) => setRegionFilter(event.target.value)} placeholder="按地区筛选" /></label>
      </section>

      <div className="community-shell">
        <section className="community-feed-column" aria-busy={loading || loadingMore}>
          {error && (
            <div className="community-inline-error">
              <span>{error}</span>
              <button type="button" onClick={() => void loadFeed()}>重新加载</button>
            </div>
          )}
          {loading ? (
            <div className="community-loading-list" aria-label="正在加载社区内容">
              <span /><span /><span />
            </div>
          ) : posts.length > 0 ? (
            <div className="community-post-list">
              {posts.map((post) => (
                <CommunityPostCard
                  key={post.id}
                  post={post}
                  reactionPending={pendingPostActions.has(`${post.id}:like`) || pendingPostActions.has(`${post.id}:bookmark`)}
                  onBookmark={() => void handlePostReaction(post.id, 'bookmark')}
                  onLike={() => void handlePostReaction(post.id, 'like')}
                  onOpen={() => void openPost(post.id)}
                />
              ))}
            </div>
          ) : (
            <section className="community-empty-state">
              <MessageCircle size={24} />
              <strong>{feedTab === 'history' ? '暂无浏览记录' : feedTab === 'drafts' ? '还没有社区草稿' : '这里还没有内容'}</strong>
              <span>{feedTab === 'history' ? '打开一篇社区内容后，它会自动保存在这里。' : feedTab === 'drafts' ? '从问诊分享中生成草稿，或新建一篇帖子。' : '分享一次观察或处理过程，帮助更多养殖者。'}</span>
              <button type="button" onClick={() => feedTab === 'history' ? setFeedTab('recommended') : openComposer()}><Plus size={16} />{feedTab === 'history' ? '去逛逛' : '发布帖子'}</button>
            </section>
          )}
          {nextOffset !== null && (
            <button className="community-load-more" type="button" disabled={loadingMore} onClick={() => void loadFeed(nextOffset, true)}>
              {loadingMore ? '正在加载' : '加载更多'}
            </button>
          )}
        </section>

        <aside className="community-aside">
          <section>
            <div className="community-aside-title"><span>热门话题</span><small>持续更新</small></div>
            <div className="community-tag-list">
              {tags.length > 0 ? tags.map((tag) => (
                <div className="community-topic-row" key={tag.id}>
                  <button
                    className={clsx(selectedTag === tag.name && 'selected')}
                    type="button"
                    onClick={() => {
                      setSelectedTag((currentTag) => (currentTag === tag.name ? '' : tag.name));
                      setFeedTab('latest');
                    }}
                  >
                    <span>#{tag.name}</span><small>{tag.post_count}</small>
                  </button>
                  <button className={clsx('community-topic-follow', tag.is_followed && 'following')} type="button" onClick={() => void handleTopicFollow(tag)}>{tag.is_followed ? '已关注' : '关注'}</button>
                </div>
              )) : <span className="community-muted">发布内容后会出现话题</span>}
            </div>
          </section>
          {searchQuery && <section className="community-search-discovery">
            <div className="community-aside-title"><span>搜索发现</span><small>{communitySearching ? '正在搜索' : `“${searchQuery}”`}</small></div>
            <button className="community-search-open-results" type="button" onClick={() => setCommunitySearchOpen(true)}>查看完整结果</button>
            {communitySearchResults ? <div>
              {communitySearchResults.authors.length > 0 && <div className="community-search-author-list"><small>用户</small>{communitySearchResults.authors.map((author) => <button type="button" key={author.id} onClick={() => void openProfile(author.id)}><span>{author.avatar_url ? <img src={author.avatar_url} alt="" /> : getAvatarLabel(author.display_name)}</span><strong>{author.display_name}</strong><em>{author.verification_status === 'verified' ? '已认证' : formatCommunityIdentity(author.identity_type)}</em></button>)}</div>}
              {communitySearchResults.tags.length > 0 && <div className="community-search-topic-list"><small>话题</small>{communitySearchResults.tags.map((tag) => <button type="button" key={tag.id} onClick={() => { setSelectedTag(tag.name); setFeedTab('latest'); }}><span>#{tag.name}</span><em>{tag.post_count}</em></button>)}</div>}
              {communitySearchResults.authors.length === 0 && communitySearchResults.tags.length === 0 && <p>没有匹配的用户或话题，已在中间列表展示相关帖子。</p>}
            </div> : <p>正在检索帖子、用户和话题。</p>}
          </section>}
          {creatorOverview && <section className="community-creator-glance">
            <div className="community-aside-title"><span>我的社区</span><small>近 7 天发布 {creatorOverview.published_this_week} 条</small></div>
            <div>
              <button type="button" onClick={() => void openCurrentUserRelationships('followers')}><strong>{creatorOverview.follower_count}</strong>粉丝</button>
              <button type="button" onClick={() => void openCurrentUserRelationships('following')}><strong>{creatorOverview.following_count}</strong>关注</button>
              <span><strong>{creatorOverview.received_like_count}</strong>获赞</span>
              <span><strong>{creatorOverview.view_count}</strong>浏览</span>
            </div>
          </section>}
          <section className="community-safety-note">
            <ShieldCheck size={17} />
            <div><strong>经验交流</strong><span>发布前请移除联系方式、地址与其他敏感信息。</span></div>
            {feedTab === 'recommended' && <button type="button" onClick={() => setCommunityConfirmAction('reset_recommendations')}>重置推荐</button>}
          </section>
        </aside>
      </div>

      {composerOpen && (
        <CommunityComposerDialog
          existingAssets={existingAssets}
          isDraft={editingPost?.status === 'draft'}
          openFilePicker={() => uploadInputRef.current?.click()}
          pendingFiles={pendingFiles}
          preparingFiles={preparingCommunityImages}
          postContent={postContent}
          postCaseData={postCaseData}
          postTags={postTags}
          postTitle={postTitle}
          postType={postType}
          posting={posting}
          postVisibility={postVisibility}
          onCancel={closeComposer}
          onContentChange={setPostContent}
          onCaseDataChange={setPostCaseData}
          onFilesSelected={handleCommunityFilesSelected}
          onRemoveExistingAsset={(fileId) => setExistingAssets((assets) => assets.filter((asset) => asset.file_id !== fileId))}
          onRemovePendingFile={(fileName, index) => setPendingFiles((files) => files.filter((file, currentIndex) => !(file.name === fileName && currentIndex === index)))}
          onMoveExistingAsset={(index, direction) => setExistingAssets((assets) => {
            const nextIndex = index + direction;
            if (nextIndex < 0 || nextIndex >= assets.length) return assets;
            const next = [...assets];
            [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
            return next;
          })}
          onMovePendingFile={(index, direction) => setPendingFiles((files) => {
            const nextIndex = index + direction;
            if (nextIndex < 0 || nextIndex >= files.length) return files;
            const next = [...files];
            [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
            return next;
          })}
          onSaveDraft={() => void submitPost(false)}
          onSubmit={() => void submitPost(true)}
          onTagsChange={setPostTags}
          onTitleChange={setPostTitle}
          onTypeChange={setPostType}
          onVisibilityChange={setPostVisibility}
        />
      )}
      <input
        ref={uploadInputRef}
        className="community-file-input"
        type="file"
        multiple
        accept="image/*,video/*,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.txt,.md,.markdown,.json,.xml,.html,.htm,.rtf,.log"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          if (files.length > 0) void handleCommunityFilesSelected(files);
          event.currentTarget.value = '';
        }}
      />
      {selectedPost && (
        <CommunityPostDialog
          comments={comments}
          commentsLoading={commentsLoading}
          commentSort={commentSort}
          commentDraft={commentDraft}
          commentSending={commentSending}
          editingComment={editingComment}
          post={selectedPost}
          replyTo={replyTo}
          onBookmark={() => void handlePostReaction(selectedPost.id, 'bookmark')}
          onAcceptAnswer={(commentId) => void handleAcceptAnswer(commentId)}
          onAddCaseUpdate={() => setCaseUpdatePost(selectedPost)}
          onClose={() => setSelectedPost(null)}
          onCommentChange={setCommentDraft}
          onCommentDelete={requestCommentDelete}
          onCommentEdit={beginCommentEdit}
          onCommentLike={(commentId) => void handleCommentLike(commentId)}
          onCommentSortChange={(sort) => void changeCommentSort(sort)}
          onCommentSubmit={submitComment}
          onDelete={() => setDeletePost(selectedPost)}
          onEdit={() => {
            setSelectedPost(null);
            openComposer(selectedPost);
          }}
          onFollow={() => void handleFollow(selectedPost.author.id)}
          onLike={() => void handlePostReaction(selectedPost.id, 'like')}
          onManageCollections={() => void openBookmarkCollections(selectedPost)}
          onNotInterested={() => void handleNotInterested(selectedPost)}
          onOpenProfile={() => void openProfile(selectedPost.author.id)}
          onReport={() => setReportPost(selectedPost)}
          onShare={() => void shareCommunityPost(selectedPost)}
          onSaveToHusbandry={() => void openSaveToHusbandry(selectedPost)}
          onReply={(comment) => { setEditingComment(null); setReplyTo(comment); setCommentDraft(''); }}
          onCancelReply={cancelCommentAction}
        />
      )}
      {notificationsOpen && (
        <CommunityNotificationsDialog notifications={notifications} onClose={() => setNotificationsOpen(false)} onOpenPost={(postId) => {
          setNotificationsOpen(false);
          void openPost(postId);
        }} onOpenDirectMessages={(threadId) => {
          setNotificationsOpen(false);
          void openDirectMessages(null, threadId);
        }} />
      )}
      {deletePost && (
        <CommunityDeletePostDialog post={deletePost} onCancel={() => setDeletePost(null)} onConfirm={() => void confirmDeletePost()} />
      )}
      {deleteComment && (
        <CommunityDeleteCommentDialog comment={deleteComment} onCancel={() => setDeleteComment(null)} onConfirm={() => void confirmDeleteComment()} />
      )}
      {communityConfirmAction && (
        <CommunityConfirmDialog
          title={communityConfirmAction === 'clear_history' ? '清空浏览记录？' : '重置推荐偏好？'}
          titleId={`community-${communityConfirmAction}-title`}
          description={communityConfirmAction === 'clear_history'
            ? '这不会影响你的点赞、收藏和评论。'
            : '会恢复“不感兴趣”的内容并清除浏览偏好；点赞、收藏和关注不会受到影响。'}
          confirmLabel={communityConfirmAction === 'clear_history' ? '清空' : '重置'}
          pendingLabel={communityConfirmAction === 'clear_history' ? '正在清空' : '正在重置'}
          tone={communityConfirmAction === 'clear_history' ? 'danger' : 'primary'}
          submitting={communityConfirmSubmitting}
          onCancel={() => setCommunityConfirmAction(null)}
          onConfirm={() => void confirmCommunityAction()}
        />
      )}
      {reportPost && <CommunityReportDialog post={reportPost} onCancel={() => setReportPost(null)} onSubmit={submitReport} />}
      {profileAuthor && (profileAuthor.id === currentUser?.id && !profilePublicMode
        ? <CommunityProfileDialog author={profileAuthor} isCurrentUser onBlock={() => void handleBlockAuthor(profileAuthor)} onClose={() => { setProfileAuthor(null); setProfilePublicMode(false); }} onFollow={() => void handleFollow(profileAuthor.id)} onSave={handleProfileSave} />
        : <CommunityPublicProfileDialog author={profileAuthor} posts={profilePosts} isCurrentUser={profileAuthor.id === currentUser?.id} onBlock={() => void handleBlockAuthor(profileAuthor)} onClose={() => { setProfileAuthor(null); setProfilePublicMode(false); }} onDirectMessage={() => { setProfileAuthor(null); setProfilePublicMode(false); void openDirectMessages(profileAuthor); }} onEditProfile={() => setProfilePublicMode(false)} onFollow={() => void handleFollow(profileAuthor.id)} onManageBlockedUsers={() => { setProfileAuthor(null); setProfilePublicMode(false); void openBlockedUsers(); }} onOpenPost={(postId) => { setProfileAuthor(null); setProfilePublicMode(false); void openPost(postId); }} onOpenRelationships={(type) => void openRelationships(profileAuthor, type)} />)}
      {directMessagesOpen && <CommunityDirectMessagesDialog activeThread={activeDirectThread} directMessages={directMessages} draft={directMessageDraft} loading={directMessagesLoading} recipient={directRecipient} sending={directMessageSending} threads={directThreads} onClose={() => setDirectMessagesOpen(false)} onDraftChange={setDirectMessageDraft} onOpenThread={(thread) => void openDirectThread(thread)} onSend={() => void sendDirectMessage()} />}
      {collectionsOpen && <CommunityCollectionsDialog collections={bookmarkCollections} detail={selectedBookmarkCollection} loading={collectionsLoading} saving={collectionSaving} targetPost={collectionTargetPost} onClose={() => { setCollectionsOpen(false); setCollectionTargetPost(null); setSelectedBookmarkCollection(null); }} onDelete={(collectionId) => void removeBookmarkCollection(collectionId)} onOpenCollection={(collectionId) => void openBookmarkCollectionDetail(collectionId)} onOpenPost={(postId) => { setCollectionsOpen(false); setCollectionTargetPost(null); setSelectedBookmarkCollection(null); void openPost(postId); }} onSave={(collectionId, name, description) => saveBookmarkCollection(collectionId, name, description)} onTogglePost={(collectionId) => void togglePostInBookmarkCollection(collectionId)} />}
      {communitySearchOpen && <CommunitySearchDialog query={searchQuery} results={communitySearchResults} loading={communitySearching} onClose={() => setCommunitySearchOpen(false)} onFollow={(authorId) => void handleFollow(authorId)} onOpenPost={(postId) => { setCommunitySearchOpen(false); void openPost(postId); }} onOpenProfile={(authorId) => { setCommunitySearchOpen(false); void openProfile(authorId); }} onOpenTopic={(tag) => { setCommunitySearchOpen(false); setSelectedTag(tag.name); setFeedTab('latest'); }} onTopicFollow={(tag) => void handleTopicFollow(tag)} />}
      {relationshipDialog && <CommunityRelationshipDialog author={relationshipDialog.author} relationshipType={relationshipDialog.type} result={relationshipResult} loading={relationshipLoading} loadingMore={relationshipLoadingMore} onClose={() => setRelationshipDialog(null)} onFollow={(authorId) => void handleFollow(authorId)} onLoadMore={() => { const nextOffset = relationshipResult?.next_offset; if (nextOffset != null) void openRelationships(relationshipDialog.author, relationshipDialog.type, nextOffset, true); }} onOpenProfile={(authorId) => { setRelationshipDialog(null); void openProfile(authorId); }} onTypeChange={(type) => void openRelationships(relationshipDialog.author, type)} />}
      {blockedUsersOpen && <CommunityBlockedUsersDialog users={blockedUsers} loading={blockedUsersLoading} pendingUserIds={pendingUnblockIds} onClose={() => setBlockedUsersOpen(false)} onUnblock={(author) => void handleUnblockUser(author)} />}
      {caseUpdatePost && <CommunityCaseUpdateDialog post={caseUpdatePost} onCancel={() => setCaseUpdatePost(null)} onSubmit={handleCaseUpdate} />}
      {saveCasePost && <CommunitySaveCaseDialog post={saveCasePost} farms={farms} batches={batches} onCancel={() => setSaveCasePost(null)} onSubmit={handleSaveToHusbandry} />}
    </article>
  );
}

function CommunityPostCard({
  post,
  reactionPending,
  onBookmark,
  onLike,
  onOpen,
}: {
  post: ApiCommunityPost;
  reactionPending: boolean;
  onBookmark: () => void;
  onLike: () => void;
  onOpen: () => void;
}) {
  const images = post.assets.filter((asset) => asset.file_type === 'image' && asset.storage_url).slice(0, 3);
  const fileAssets = post.assets.filter((asset) => asset.file_type !== 'image');
  return (
    <article className="community-post-card" role="button" aria-label={`打开帖子：${post.title}`} tabIndex={0} onClick={onOpen} onKeyDown={(event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        onOpen();
      }
    }}>
      <header>
        <div className="community-author">
          {post.author.avatar_url ? <img src={post.author.avatar_url} alt="" /> : <span>{getAvatarLabel(post.author.display_name)}</span>}
          <div><strong>{post.author.display_name}{post.author.verification_status === 'verified' && <ShieldCheck size={13} />}</strong><small>{post.author.region ? `${post.author.region} · ` : ''}{formatCommunityTime(post.published_at ?? post.created_at)} · {formatCommunityPostType(post.post_type)}</small></div>
        </div>
        <div className="community-card-status">{post.status === 'draft' && <span className="community-draft-pill">草稿</span>}{post.post_type === 'question' && <span className={clsx('community-question-pill', post.question_status === 'resolved' && 'resolved')}>{post.question_status === 'resolved' ? '已解决' : '待解答'}</span>}{post.post_type === 'case' && (post.case_updates?.length ?? 0) > 0 && <span className="community-followup-pill">{post.case_updates.length} 次随访</span>}</div>
      </header>
      <div className="community-post-copy"><h2>{post.title}</h2>{post.excerpt && <p>{post.excerpt}</p>}</div>
      {post.recommendation_reason && <div className="community-recommendation-reason"><Sparkles size={14} /><span>{post.recommendation_reason}</span></div>}
      {images.length > 0 && (
        <div className={clsx('community-media-grid', `count-${images.length}`)}>
          {images.map((asset) => <img src={asset.storage_url ?? ''} alt={asset.file_name} key={asset.id} loading="lazy" decoding="async" />)}
        </div>
      )}
      {fileAssets.length > 0 && (
        <div className="community-file-summary"><FileText size={15} /><span>{fileAssets.length} 个附件</span></div>
      )}
      {post.tags.length > 0 && <div className="community-post-tags">{post.tags.map((tag) => <span key={tag.id}>#{tag.name}</span>)}</div>}
      <footer onClick={(event) => event.stopPropagation()}>
        <button className={clsx(post.is_liked && 'active')} type="button" disabled={reactionPending} aria-pressed={post.is_liked} title={post.is_liked ? '取消点赞' : '点赞'} onClick={onLike}><Heart size={17} fill={post.is_liked ? 'currentColor' : 'none'} /><span>{post.like_count}</span></button>
        <button type="button" title="查看评论" onClick={onOpen}><MessageCircle size={17} /><span>{post.comment_count}</span></button>
        <button className={clsx(post.is_bookmarked && 'active')} type="button" disabled={reactionPending} aria-pressed={post.is_bookmarked} title={post.is_bookmarked ? '取消收藏' : '收藏'} onClick={onBookmark}><Bookmark size={17} fill={post.is_bookmarked ? 'currentColor' : 'none'} /><span>{post.bookmark_count}</span></button>
      </footer>
    </article>
  );
}

function CommunityComposerDialog({
  existingAssets,
  isDraft,
  openFilePicker,
  pendingFiles,
  preparingFiles,
  postContent,
  postCaseData,
  postTags,
  postTitle,
  postType,
  posting,
  postVisibility,
  onCancel,
  onContentChange,
  onCaseDataChange,
  onFilesSelected,
  onMoveExistingAsset,
  onMovePendingFile,
  onRemoveExistingAsset,
  onRemovePendingFile,
  onSaveDraft,
  onSubmit,
  onTagsChange,
  onTitleChange,
  onTypeChange,
  onVisibilityChange,
}: {
  existingAssets: ApiCommunityUpload[];
  isDraft: boolean;
  openFilePicker: () => void;
  pendingFiles: File[];
  preparingFiles: boolean;
  postContent: string;
  postCaseData: Record<string, string | number | null>;
  postTags: string;
  postTitle: string;
  postType: CommunityPostType;
  posting: boolean;
  postVisibility: CommunityPostVisibility;
  onCancel: () => void;
  onContentChange: (value: string) => void;
  onCaseDataChange: (value: Record<string, string | number | null>) => void;
  onFilesSelected: (files: File[]) => void | Promise<void>;
  onMoveExistingAsset: (index: number, direction: -1 | 1) => void;
  onMovePendingFile: (index: number, direction: -1 | 1) => void;
  onRemoveExistingAsset: (fileId: string) => void;
  onRemovePendingFile: (fileName: string, index: number) => void;
  onSaveDraft: () => void;
  onSubmit: () => void;
  onTagsChange: (value: string) => void;
  onTitleChange: (value: string) => void;
  onTypeChange: (value: CommunityPostType) => void;
  onVisibilityChange: (value: CommunityPostVisibility) => void;
}) {
  return (
    <div className="community-overlay" role="presentation" onMouseDown={onCancel}>
      <section className="community-composer-dialog" role="dialog" aria-modal="true" aria-labelledby="community-composer-title" onMouseDown={(event) => event.stopPropagation()}>
        <header><div><span>社区发布</span><h2 id="community-composer-title">{isDraft ? '完善社区草稿' : '发布新帖子'}</h2></div><button type="button" aria-label="关闭发布窗口" title="关闭" disabled={posting || preparingFiles} onClick={onCancel}><X size={19} /></button></header>
        <label className="community-title-input"><span>标题</span><input value={postTitle} maxLength={120} disabled={posting || preparingFiles} onChange={(event) => onTitleChange(event.target.value)} placeholder="用一句话说清楚你的观察或问题" /></label>
        <textarea className="community-content-input" value={postContent} maxLength={60000} disabled={posting || preparingFiles} onChange={(event) => onContentChange(event.target.value)} placeholder="补充症状、养殖环境、已采取的措施和结果。" />
        {postType === 'case' && <section className="community-case-builder">
          <div><span>结构化病例</span><small>填写后会在帖子中形成便于对照的病例卡片</small></div>
          <div className="community-case-fields">
            <label><span>发生日期</span><input type="date" value={String(postCaseData.occurred_on ?? '')} onChange={(event) => onCaseDataChange({ ...postCaseData, occurred_on: event.target.value })} /></label>
            <label><span>地区</span><input value={String(postCaseData.region ?? '')} placeholder="如 浙江湖州" onChange={(event) => onCaseDataChange({ ...postCaseData, region: event.target.value })} /></label>
            <label><span>品种</span><input value={String(postCaseData.variety ?? '')} placeholder="蚕品种" onChange={(event) => onCaseDataChange({ ...postCaseData, variety: event.target.value })} /></label>
            <label><span>龄期</span><input value={String(postCaseData.instar ?? '')} placeholder="如 五龄第 3 天" onChange={(event) => onCaseDataChange({ ...postCaseData, instar: event.target.value })} /></label>
            <label className="wide"><span>主要症状</span><input value={String(postCaseData.symptoms ?? '')} placeholder="体色、食桑、活动、排泄等变化" onChange={(event) => onCaseDataChange({ ...postCaseData, symptoms: event.target.value })} /></label>
            <label className="wide"><span>环境</span><input value={String(postCaseData.environment ?? '')} placeholder="温湿度、通风、消毒等" onChange={(event) => onCaseDataChange({ ...postCaseData, environment: event.target.value })} /></label>
            <label className="wide"><span>已采取措施</span><input value={String(postCaseData.measure ?? '')} placeholder="隔离、消毒、调温等" onChange={(event) => onCaseDataChange({ ...postCaseData, measure: event.target.value })} /></label>
            <label className="wide"><span>当前结果</span><input value={String(postCaseData.outcome ?? '')} placeholder="改善、稳定或仍在观察" onChange={(event) => onCaseDataChange({ ...postCaseData, outcome: event.target.value })} /></label>
          </div>
        </section>}
        <div className="community-composer-row">
          <label><span>内容类型</span><select value={postType} disabled={posting} onChange={(event) => onTypeChange(event.target.value as CommunityPostType)}><option value="experience">经验分享</option><option value="case">病例交流</option><option value="question">提问求助</option><option value="reference">资料解读</option></select></label>
          <label><span>可见范围</span><select value={postVisibility} disabled={posting} onChange={(event) => onVisibilityChange(event.target.value as CommunityPostVisibility)}><option value="public">公开社区</option><option value="followers">仅关注者</option></select></label>
          <label className="community-tag-input"><span>话题</span><input value={postTags} disabled={posting} onChange={(event) => onTagsChange(event.target.value)} placeholder="如 白僵病 湿度" /></label>
        </div>
        <section className="community-attachment-area">
          <button className="community-add-asset" type="button" disabled={posting || preparingFiles} onClick={openFilePicker}><Paperclip size={18} /><span>添加图片、视频或文档</span></button>
          <input className="community-hidden-inline-file" type="file" disabled={posting || preparingFiles} multiple accept="image/*,video/*,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.txt,.md,.markdown,.json,.xml,.html,.htm,.rtf,.log" onChange={(event) => {
            void onFilesSelected(Array.from(event.target.files ?? []));
            event.currentTarget.value = '';
          }} />
          {preparingFiles && <div className="community-attachment-preparing" role="status">正在优化图片，稍后即可发布</div>}
          {(existingAssets.length > 0 || pendingFiles.length > 0) && <div className="community-asset-chips">
            <p className="community-asset-order-hint">可调整素材顺序；第一张图片将作为帖子封面。</p>
            {existingAssets.map((asset, index) => <CommunityAssetChip key={asset.file_id} asset={asset} canMoveNext={index < existingAssets.length - 1} canMovePrevious={index > 0} onMoveNext={() => onMoveExistingAsset(index, 1)} onMovePrevious={() => onMoveExistingAsset(index, -1)} onRemove={() => onRemoveExistingAsset(asset.file_id)} />)}
            {pendingFiles.map((file, index) => <CommunityPendingFileChip key={`${file.name}-${index}`} file={file} canMoveNext={index < pendingFiles.length - 1} canMovePrevious={index > 0} onMoveNext={() => onMovePendingFile(index, 1)} onMovePrevious={() => onMovePendingFile(index, -1)} onRemove={() => onRemovePendingFile(file.name, index)} />)}
          </div>}
        </section>
        <footer><button type="button" disabled={posting || preparingFiles} onClick={onCancel}>取消</button><button type="button" disabled={posting || preparingFiles} onClick={onSaveDraft}>{posting ? '正在保存' : '保存草稿'}</button><button className="community-submit-post" type="button" disabled={posting || preparingFiles} onClick={onSubmit}>{posting ? '正在发布' : '发布帖子'}</button></footer>
      </section>
    </div>
  );
}

function CommunityAssetChip({ asset, canMoveNext, canMovePrevious, onMoveNext, onMovePrevious, onRemove }: { asset: ApiCommunityUpload; canMoveNext: boolean; canMovePrevious: boolean; onMoveNext: () => void; onMovePrevious: () => void; onRemove: () => void }) {
  return <div className="community-asset-chip">{asset.file_type === 'image' && asset.storage_url ? <img src={asset.storage_url} alt="" /> : asset.file_type === 'video' ? <Video size={16} /> : <FileText size={16} />}<span>{asset.file_name}</span><div className="community-asset-order"><button type="button" aria-label={`将 ${asset.file_name} 前移`} title="前移" disabled={!canMovePrevious} onClick={onMovePrevious}><ChevronRight className="community-asset-previous" size={14} /></button><button type="button" aria-label={`将 ${asset.file_name} 后移`} title="后移" disabled={!canMoveNext} onClick={onMoveNext}><ChevronRight size={14} /></button><button type="button" aria-label={`移除 ${asset.file_name}`} title="移除" onClick={onRemove}><X size={14} /></button></div></div>;
}

function CommunityPendingFileChip({ file, canMoveNext, canMovePrevious, onMoveNext, onMovePrevious, onRemove }: { file: File; canMoveNext: boolean; canMovePrevious: boolean; onMoveNext: () => void; onMovePrevious: () => void; onRemove: () => void }) {
  const previewUrl = useMemo(() => (file.type.startsWith('image/') ? URL.createObjectURL(file) : ''), [file]);
  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);
  return <div className="community-asset-chip pending">{previewUrl ? <img src={previewUrl} alt="" /> : file.type.startsWith('video/') ? <Video size={16} /> : <FileText size={16} />}<span>{file.name}</span><small>{formatAttachmentSize(file.size)}</small><div className="community-asset-order"><button type="button" aria-label={`将 ${file.name} 前移`} title="前移" disabled={!canMovePrevious} onClick={onMovePrevious}><ChevronRight className="community-asset-previous" size={14} /></button><button type="button" aria-label={`将 ${file.name} 后移`} title="后移" disabled={!canMoveNext} onClick={onMoveNext}><ChevronRight size={14} /></button><button type="button" aria-label={`移除 ${file.name}`} title="移除" onClick={onRemove}><X size={14} /></button></div></div>;
}

function CommunityPostDialog({
  comments, commentsLoading, commentSort, commentDraft, commentSending, editingComment, post, replyTo, onAcceptAnswer, onAddCaseUpdate, onBookmark, onCancelReply, onClose, onCommentChange, onCommentDelete, onCommentEdit, onCommentLike, onCommentSortChange, onCommentSubmit, onDelete, onEdit, onFollow, onLike, onManageCollections, onNotInterested, onOpenProfile, onReport, onReply, onSaveToHusbandry, onShare,
}: {
  comments: ApiCommunityComment[];
  commentsLoading: boolean;
  commentSort: 'top' | 'latest';
  commentDraft: string;
  commentSending: boolean;
  editingComment: ApiCommunityComment | null;
  post: ApiCommunityPost;
  replyTo: ApiCommunityComment | null;
  onAcceptAnswer: (commentId: string) => void;
  onAddCaseUpdate: () => void;
  onBookmark: () => void;
  onCancelReply: () => void;
  onClose: () => void;
  onCommentChange: (value: string) => void;
  onCommentDelete: (commentId: string) => void;
  onCommentEdit: (comment: ApiCommunityComment) => void;
  onCommentLike: (commentId: string) => void;
  onCommentSortChange: (sort: 'top' | 'latest') => void;
  onCommentSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onDelete: () => void;
  onEdit: () => void;
  onFollow: () => void;
  onLike: () => void;
  onManageCollections: () => void;
  onNotInterested: () => void;
  onOpenProfile: () => void;
  onReport: () => void;
  onReply: (comment: ApiCommunityComment) => void;
  onSaveToHusbandry: () => void;
  onShare: () => void;
}) {
  const rootComments = comments.filter((comment) => !comment.parent_comment_id);
  const replyMap = useMemo(() => {
    const map = new Map<string, ApiCommunityComment[]>();
    comments.forEach((comment) => {
      if (!comment.parent_comment_id) return;
      map.set(comment.parent_comment_id, [...(map.get(comment.parent_comment_id) ?? []), comment]);
    });
    return map;
  }, [comments]);
  return <div className="community-overlay community-detail-overlay" role="presentation" onMouseDown={onClose}>
    <section className="community-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="community-post-title" onMouseDown={(event) => event.stopPropagation()}>
      <header className="community-detail-header"><span>社区帖子</span><button type="button" aria-label="关闭帖子" title="关闭" onClick={onClose}><X size={19} /></button></header>
      <div className="community-detail-scroll">
        <article className="community-detail-post">
          <div className="community-detail-author"><button type="button" className="community-author community-author-button" onClick={onOpenProfile}>{post.author.avatar_url ? <img src={post.author.avatar_url} alt="" /> : <span>{getAvatarLabel(post.author.display_name)}</span>}<div><strong>{post.author.display_name}{post.author.verification_status === 'verified' && <ShieldCheck size={14} />}</strong><small>{post.author.region ? `${post.author.region} · ` : ''}{formatCommunityTime(post.published_at ?? post.created_at)} · {formatCommunityPostType(post.post_type)}</small></div></button>{!post.is_author && <button type="button" className={clsx('community-follow-button', post.author.is_followed && 'following')} onClick={onFollow}><UserPlus size={15} />{post.author.is_followed ? '已关注' : '关注'}</button>}</div>
          <h1 id="community-post-title">{post.title}</h1>
          {post.post_type === 'question' && <div className={clsx('community-question-state', post.question_status === 'resolved' && 'resolved')}><MessageCircle size={16} /><strong>{post.question_status === 'resolved' ? '问题已解决' : '等待社区回答'}</strong><span>{post.question_status === 'resolved' ? '发帖人已采纳一条回答' : '有帮助的回答可由发帖人采纳'}</span></div>}
          <CommunityPostContent post={post} />
          <div className="community-detail-actions"><button className={clsx(post.is_liked && 'active')} type="button" onClick={onLike}><Heart size={18} fill={post.is_liked ? 'currentColor' : 'none'} />{post.like_count}</button><button className={clsx(post.is_bookmarked && 'active')} type="button" onClick={onBookmark}><Bookmark size={18} fill={post.is_bookmarked ? 'currentColor' : 'none'} />{post.bookmark_count}</button><button type="button" onClick={onManageCollections}><FolderPlus size={17} />归入收藏夹</button><button type="button" onClick={onShare}><Link2 size={17} />分享</button>{post.post_type === 'case' && !post.is_author && <button type="button" onClick={onSaveToHusbandry}><ClipboardList size={17} />存入台账</button>}{post.post_type === 'case' && post.is_author && <button type="button" onClick={onAddCaseUpdate}><History size={17} />添加随访</button>}{post.is_author ? <><button type="button" onClick={onEdit}><PencilLine size={17} />编辑</button><button className="danger" type="button" onClick={onDelete}><Trash2 size={17} />删除</button></> : <><button type="button" onClick={onNotInterested}><ThumbsDown size={16} />不感兴趣</button><button type="button" onClick={onReport}><Flag size={16} />举报</button></>}</div>
        </article>
        <section className="community-comments"><header><h2>{post.post_type === 'question' ? '回答' : '评论'} {post.comment_count}</h2><div className="community-comment-sort" role="tablist" aria-label="评论排序"><button type="button" role="tab" aria-selected={commentSort === 'top'} className={clsx(commentSort === 'top' && 'active')} onClick={() => onCommentSortChange('top')}>最热</button><button type="button" role="tab" aria-selected={commentSort === 'latest'} className={clsx(commentSort === 'latest' && 'active')} onClick={() => onCommentSortChange('latest')}>最新</button></div></header>{commentsLoading ? <div className="community-comments-loading">正在加载评论</div> : rootComments.length > 0 ? rootComments.map((comment) => <CommunityCommentThread key={comment.id} comment={comment} replyMap={replyMap} canAccept={post.is_author && post.post_type === 'question' && post.question_status === 'open'} onAccept={onAcceptAnswer} onDelete={onCommentDelete} onEdit={onCommentEdit} onLike={onCommentLike} onReply={onReply} />) : <div className="community-comments-empty">{post.post_type === 'question' ? '还没有回答，分享你的判断依据和建议。' : '还没有评论，说说你的经验或问题。'}</div>}</section>
      </div>
      <form className="community-comment-form" onSubmit={onCommentSubmit}>{editingComment ? <div className="community-replying community-comment-editing"><span>编辑评论</span><button type="button" aria-label="取消编辑" title="取消编辑" onClick={onCancelReply}><X size={14} /></button></div> : replyTo && <div className="community-replying"><span>回复 @{replyTo.author.display_name}</span><button type="button" aria-label="取消回复" title="取消回复" onClick={onCancelReply}><X size={14} /></button></div>}<textarea value={commentDraft} maxLength={2000} disabled={commentSending} onChange={(event) => onCommentChange(event.target.value)} placeholder={editingComment ? '修改这条评论' : '写下你的评论'} /><button type="submit" disabled={commentSending || !commentDraft.trim()} aria-label={editingComment ? '保存评论' : '发布评论'} title={editingComment ? '保存评论' : '发布评论'}>{editingComment ? <Check size={17} /> : <Send size={17} />}</button></form>
    </section>
  </div>;
}

function CommunityPostContent({ post }: { post: ApiCommunityPost }) {
  const images = post.assets.filter((asset) => asset.file_type === 'image' && asset.storage_url);
  const videos = post.assets.filter((asset) => asset.file_type === 'video' && asset.storage_url);
  const files = post.assets.filter((asset) => asset.file_type === 'document' || asset.file_type === 'other');
  const caseData = post.case_data ?? {};
  const caseUpdates = post.case_updates ?? [];
  const caseLabels: Array<[string, string]> = [['occurred_on', '发生日期'], ['region', '地区'], ['variety', '品种'], ['instar', '龄期'], ['symptoms', '主要症状'], ['environment', '养殖环境'], ['measure', '已采取措施'], ['outcome', '当前结果'], ['suspected_disease', '疑似问题'], ['diagnosis', '初步判断']];
  return <>{post.post_type === 'case' && Object.keys(caseData).length > 0 && <section className="community-case-summary"><header><ClipboardList size={17} /><strong>病例摘要</strong><span>结构化记录</span></header><div>{caseLabels.filter(([key]) => caseData[key]).map(([key, label]) => <dl key={key}><dt>{label}</dt><dd>{String(caseData[key])}</dd></dl>)}</div></section>}<div className="community-detail-content">{post.content_markdown.split('\n').filter(Boolean).map((paragraph, index) => <p key={`${index}-${paragraph.slice(0, 12)}`}>{paragraph.replace(/^#{1,6}\s*/, '')}</p>)}</div>{images.length > 0 && <div className={clsx('community-detail-media', `count-${Math.min(images.length, 4)}`)}>{images.map((asset) => <a href={asset.storage_url ?? undefined} target="_blank" rel="noreferrer" key={asset.id}><img src={asset.storage_url ?? ''} alt={asset.file_name} /></a>)}</div>}{videos.map((asset) => <video className="community-video" controls key={asset.id} src={asset.storage_url ?? undefined} />)}{files.length > 0 && <div className="community-detail-files">{files.map((asset) => <a href={asset.storage_url ?? undefined} target="_blank" rel="noreferrer" key={asset.id}><FileText size={17} /><span>{asset.file_name}</span><small>{formatAttachmentSize(asset.file_size)}</small></a>)}</div>}{caseUpdates.length > 0 && <section className="community-case-timeline"><header><History size={17} /><strong>病例随访</strong><span>{caseUpdates.length} 次更新</span></header>{caseUpdates.map((update) => <article key={update.id}><i /><div><header><strong>{formatCaseUpdateStatus(update.outcome_status)}</strong><time>{update.occurred_on}</time></header><p>{update.content}</p></div></article>)}</section>}{post.tags.length > 0 && <div className="community-post-tags detail">{post.tags.map((tag) => <span key={tag.id}>#{tag.name}</span>)}</div>}</>;
}

function CommunityCommentThread({ comment, replyMap, canAccept, onAccept, onDelete, onEdit, onLike, onReply, depth = 0 }: { comment: ApiCommunityComment; replyMap: Map<string, ApiCommunityComment[]>; canAccept: boolean; onAccept: (id: string) => void; onDelete: (id: string) => void; onEdit: (comment: ApiCommunityComment) => void; onLike: (id: string) => void; onReply: (comment: ApiCommunityComment) => void; depth?: number }) {
  return <div className={clsx('community-comment-thread', depth > 0 && 'nested-thread')}><CommunityCommentRow comment={comment} nested={depth > 0} canAccept={canAccept && depth === 0} onAccept={onAccept} onDelete={onDelete} onEdit={onEdit} onLike={onLike} onReply={onReply} />{(replyMap.get(comment.id) ?? []).map((reply) => <CommunityCommentThread key={reply.id} comment={reply} replyMap={replyMap} canAccept={false} depth={depth + 1} onAccept={onAccept} onDelete={onDelete} onEdit={onEdit} onLike={onLike} onReply={onReply} />)}</div>;
}

function CommunityCommentRow({ comment, nested = false, canAccept = false, onAccept, onDelete, onEdit, onLike, onReply }: { comment: ApiCommunityComment; nested?: boolean; canAccept?: boolean; onAccept: (id: string) => void; onDelete: (id: string) => void; onEdit: (comment: ApiCommunityComment) => void; onLike: (id: string) => void; onReply: (comment: ApiCommunityComment) => void }) {
  const isActive = comment.status === 'active';
  return <article className={clsx('community-comment-row', nested && 'nested', comment.is_accepted && 'accepted', !isActive && 'deleted')}><div className="community-comment-avatar">{comment.author.avatar_url ? <img src={comment.author.avatar_url} alt="" /> : getAvatarLabel(comment.author.display_name)}</div><div><header><strong>{comment.author.display_name}{comment.author.verification_status === 'verified' && <ShieldCheck size={12} />}</strong><small>{formatCommunityTime(comment.created_at)}</small>{comment.is_accepted && <span className="community-accepted-pill"><Check size={12} />已采纳</span>}</header><p>{comment.content}</p>{isActive && <footer><button className={clsx(comment.is_liked && 'active')} type="button" onClick={() => onLike(comment.id)}><Heart size={14} fill={comment.is_liked ? 'currentColor' : 'none'} />{comment.like_count || ''}</button><button type="button" onClick={() => onReply(comment)}><ReplyIcon />回复</button>{comment.is_author && <><button type="button" onClick={() => onEdit(comment)}><PencilLine size={13} />编辑</button><button className="danger" type="button" onClick={() => onDelete(comment.id)}><Trash2 size={13} />删除</button></>}{canAccept && <button className="community-accept-answer" type="button" onClick={() => onAccept(comment.id)}><Check size={14} />采纳回答</button>}</footer>}</div></article>;
}

function ReplyIcon() { return <ChevronRight className="community-reply-icon" size={14} />; }

function CommunityProfileDialog({ author, isCurrentUser, onBlock, onClose, onFollow, onSave }: { author: ApiCommunityAuthor; isCurrentUser: boolean; onBlock: () => void; onClose: () => void; onFollow: () => void; onSave: (payload: Parameters<typeof updateCommunityProfile>[1]) => void }) {
  const [identityType, setIdentityType] = useState(author.identity_type ?? (author.role === 'agritech' ? 'technician' : author.role === 'expert' ? 'researcher' : 'farmer'));
  const [region, setRegion] = useState(author.region ?? '');
  const [organization, setOrganization] = useState(author.organization ?? '');
  const [expertise, setExpertise] = useState((author.expertise_tags ?? []).join(' '));
  const [years, setYears] = useState(author.years_experience?.toString() ?? '');
  const [bio, setBio] = useState(author.bio ?? '');
  return <div className="community-overlay community-profile-overlay" role="presentation" onMouseDown={onClose}><section className="community-profile-dialog" role="dialog" aria-modal="true" aria-label="社区专业资料" onMouseDown={(event) => event.stopPropagation()}><header><div className="community-profile-hero"><div className="community-profile-avatar">{author.avatar_url ? <img src={author.avatar_url} alt="" /> : getAvatarLabel(author.display_name)}</div><div><span>社区专业资料</span><h2>{author.display_name}{author.verification_status === 'verified' && <ShieldCheck size={18} />}</h2><p>{author.organization || author.region || formatCommunityIdentity(author.identity_type)}</p></div></div><button type="button" aria-label="关闭" onClick={onClose}><X size={18} /></button></header>{isCurrentUser ? <div className="community-profile-form"><div className="community-composer-row"><label><span>身份</span><select value={identityType} onChange={(event) => setIdentityType(event.target.value as ApiCommunityAuthor['identity_type'])}><option value="farmer">养殖户</option><option value="technician">农技人员</option><option value="researcher">科研人员</option><option value="other">其他从业者</option></select></label><label><span>地区</span><input value={region} onChange={(event) => setRegion(event.target.value)} placeholder="省 / 市" /></label><label><span>从业年限</span><input type="number" min="0" max="80" value={years} onChange={(event) => setYears(event.target.value)} placeholder="年" /></label></div><label><span>单位或养殖场</span><input value={organization} onChange={(event) => setOrganization(event.target.value)} /></label><label><span>擅长方向</span><input value={expertise} onChange={(event) => setExpertise(event.target.value)} placeholder="用空格分隔，如 病害防控 小蚕共育" /></label><label><span>个人介绍</span><textarea value={bio} maxLength={500} onChange={(event) => setBio(event.target.value)} placeholder="介绍你的养殖经验或专业背景" /></label></div> : <div className="community-profile-readonly"><div className="community-profile-facts"><span>{formatCommunityIdentity(author.identity_type)}</span>{author.region && <span>{author.region}</span>}{author.years_experience !== null && <span>{author.years_experience} 年经验</span>}{author.verification_status === 'verified' && <span className="verified">已认证</span>}</div>{author.bio && <p>{author.bio}</p>}{author.expertise_tags.length > 0 && <div className="community-post-tags detail">{author.expertise_tags.map((tag) => <span key={tag}>#{tag}</span>)}</div>}</div>}<footer>{isCurrentUser ? <><button type="button" onClick={onClose}>取消</button><button type="button" onClick={() => onSave({ identity_type: identityType, region: region.trim() || null, organization: organization.trim() || null, expertise_tags: expertise.split(/[\s,，]+/).filter(Boolean), years_experience: years ? Number(years) : null, bio: bio.trim() || null, request_verification: false })}>保存资料</button>{author.verification_status === 'unverified' || author.verification_status === 'rejected' ? <button className="community-submit-post" type="button" onClick={() => onSave({ identity_type: identityType, region: region.trim() || null, organization: organization.trim() || null, expertise_tags: expertise.split(/[\s,，]+/).filter(Boolean), years_experience: years ? Number(years) : null, bio: bio.trim() || null, request_verification: true })}>申请认证</button> : <span className="community-verification-state">{author.verification_status === 'pending' ? '认证审核中' : '已完成认证'}</span>}</> : <><button className="danger" type="button" onClick={onBlock}>屏蔽用户</button><button type="button" className="community-submit-post" onClick={onFollow}>{author.is_followed ? '取消关注' : '关注'}</button></>}</footer></section></div>;
}

function CommunityPublicProfileDialog({
  author,
  posts,
  isCurrentUser,
  onBlock,
  onClose,
  onDirectMessage,
  onEditProfile,
  onFollow,
  onManageBlockedUsers,
  onOpenPost,
  onOpenRelationships,
}: {
  author: ApiCommunityAuthor;
  posts: ApiCommunityPost[];
  isCurrentUser: boolean;
  onBlock: () => void;
  onClose: () => void;
  onDirectMessage: () => void;
  onEditProfile: () => void;
  onFollow: () => void;
  onManageBlockedUsers: () => void;
  onOpenPost: (postId: string) => void;
  onOpenRelationships: (type: CommunityRelationshipType) => void;
}) {
  return (
    <div className="community-overlay community-profile-overlay" role="presentation" onMouseDown={onClose}>
      <section className="community-public-profile-dialog" role="dialog" aria-modal="true" aria-label="社区用户主页" onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div className="community-profile-hero">
            <div className="community-profile-avatar">{author.avatar_url ? <img src={author.avatar_url} alt="" /> : getAvatarLabel(author.display_name)}</div>
            <div>
              <span>社区用户</span>
              <h2>{author.display_name}{author.verification_status === 'verified' && <ShieldCheck size={18} />}</h2>
              <p>{author.organization || author.region || formatCommunityIdentity(author.identity_type)}</p>
            </div>
          </div>
          <button type="button" aria-label="关闭" onClick={onClose}><X size={18} /></button>
        </header>
        <div className="community-profile-stat-grid" aria-label="用户社区数据">
          <span><strong>{author.post_count}</strong><small>发布</small></span>
          <button type="button" onClick={() => onOpenRelationships('followers')}><strong>{author.follower_count}</strong><small>粉丝</small></button>
          <button type="button" onClick={() => onOpenRelationships('following')}><strong>{author.following_count}</strong><small>关注</small></button>
          <span><strong>{author.received_like_count}</strong><small>获赞</small></span>
        </div>
        <div className="community-profile-readonly community-public-profile-body">
          <div className="community-profile-facts"><span>{formatCommunityIdentity(author.identity_type)}</span>{author.region && <span>{author.region}</span>}{author.years_experience !== null && <span>{author.years_experience} 年经验</span>}{author.verification_status === 'verified' && <span className="verified">已认证</span>}</div>
          {author.bio && <p>{author.bio}</p>}
          {author.expertise_tags.length > 0 && <div className="community-post-tags detail">{author.expertise_tags.map((tag) => <span key={tag}>#{tag}</span>)}</div>}
        </div>
        <section className="community-profile-posts">
          <header><strong>公开发布</strong><span>{posts.length > 0 ? `最近 ${posts.length} 条` : '暂未发布内容'}</span></header>
          {posts.length > 0 ? <div>{posts.map((post) => <button key={post.id} type="button" onClick={() => onOpenPost(post.id)}><span>{formatCommunityPostType(post.post_type)}</span><strong>{post.title}</strong><small>{post.like_count} 赞 · {post.comment_count} 评论</small></button>)}</div> : <p>这个用户还没有公开发布内容。</p>}
        </section>
        <footer>
          {isCurrentUser ? <><button type="button" onClick={onManageBlockedUsers}><UserRound size={15} />屏蔽管理</button><button type="button" className="community-submit-post" onClick={onEditProfile}><PencilLine size={15} />编辑资料</button></> : <><button className="danger" type="button" onClick={onBlock}>屏蔽用户</button><button type="button" onClick={onDirectMessage}><MessageSquarePlus size={15} />私信</button><button type="button" className="community-submit-post" onClick={onFollow}>{author.is_followed ? '取消关注' : '关注'}</button></>}
        </footer>
      </section>
    </div>
  );
}

function CommunitySearchDialog({
  query,
  results,
  loading,
  onClose,
  onFollow,
  onOpenPost,
  onOpenProfile,
  onOpenTopic,
  onTopicFollow,
}: {
  query: string;
  results: ApiCommunitySearch | null;
  loading: boolean;
  onClose: () => void;
  onFollow: (authorId: string) => void;
  onOpenPost: (postId: string) => void;
  onOpenProfile: (authorId: string) => void;
  onOpenTopic: (tag: ApiCommunityTag) => void;
  onTopicFollow: (tag: ApiCommunityTag) => void;
}) {
  const hasResults = Boolean(results && (results.posts.length || results.authors.length || results.tags.length));
  return (
    <div className="community-overlay" role="presentation" onMouseDown={onClose}>
      <section className="community-search-dialog" role="dialog" aria-modal="true" aria-label="社区搜索结果" onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div><span>社区搜索</span><h2>“{query}”</h2><p>帖子、用户和话题会分别展示，方便直接进入下一步。</p></div>
          <button type="button" aria-label="关闭搜索结果" title="关闭" onClick={onClose}><X size={18} /></button>
        </header>
        {loading && !results ? <div className="community-search-state">正在搜索社区内容…</div> : hasResults && results ? <div className="community-search-result-grid">
          <section className="community-search-result-posts">
            <header><strong>相关内容</strong><small>{results.posts.length} 条</small></header>
            {results.posts.length > 0 ? results.posts.map((post) => <button className="community-search-post-row" type="button" key={post.id} onClick={() => onOpenPost(post.id)}>
              <span>{formatCommunityPostType(post.post_type)}</span><strong>{post.title}</strong><p>{post.excerpt || post.content_markdown}</p><small>{post.author.display_name} · {post.like_count} 赞 · {post.comment_count} 评论</small>
            </button>) : <p className="community-search-empty">没有匹配的帖子，试试更具体的症状、品种或地区。</p>}
          </section>
          <aside>
            <section className="community-search-result-users">
              <header><strong>相关用户</strong><small>{results.authors.length} 位</small></header>
              {results.authors.length > 0 ? results.authors.map((author) => <article key={author.id}>
                <button type="button" className="community-search-person" onClick={() => onOpenProfile(author.id)}><span>{author.avatar_url ? <img src={author.avatar_url} alt="" /> : getAvatarLabel(author.display_name)}</span><div><strong>{author.display_name}{author.verification_status === 'verified' && <ShieldCheck size={13} />}</strong><small>{author.organization || author.region || formatCommunityIdentity(author.identity_type)}</small></div></button>
                <button className={clsx('community-topic-follow', author.is_followed && 'following')} type="button" onClick={() => onFollow(author.id)}>{author.is_followed ? '已关注' : '关注'}</button>
              </article>) : <p className="community-search-empty">没有找到匹配用户。</p>}
            </section>
            <section className="community-search-result-topics">
              <header><strong>相关话题</strong><small>{results.tags.length} 个</small></header>
              {results.tags.length > 0 ? results.tags.map((tag) => <article key={tag.id}><button type="button" onClick={() => onOpenTopic(tag)}><strong>#{tag.name}</strong><small>{tag.post_count} 条内容</small></button><button className={clsx('community-topic-follow', tag.is_followed && 'following')} type="button" onClick={() => onTopicFollow(tag)}>{tag.is_followed ? '已关注' : '关注'}</button></article>) : <p className="community-search-empty">没有找到匹配话题。</p>}
            </section>
          </aside>
        </div> : <div className="community-search-state"><Search size={22} /><strong>没有找到匹配结果</strong><span>可以换一个关键词，或直接从热门话题开始浏览。</span></div>}
      </section>
    </div>
  );
}

function CommunityRelationshipDialog({
  author,
  relationshipType,
  result,
  loading,
  loadingMore,
  onClose,
  onFollow,
  onLoadMore,
  onOpenProfile,
  onTypeChange,
}: {
  author: ApiCommunityAuthor;
  relationshipType: CommunityRelationshipType;
  result: ApiCommunityRelationshipList | null;
  loading: boolean;
  loadingMore: boolean;
  onClose: () => void;
  onFollow: (authorId: string) => void;
  onLoadMore: () => void;
  onOpenProfile: (authorId: string) => void;
  onTypeChange: (type: CommunityRelationshipType) => void;
}) {
  const label = relationshipType === 'followers' ? '粉丝' : '关注';
  return (
    <div className="community-overlay community-relationship-overlay" role="presentation" onMouseDown={onClose}>
      <section className="community-relationship-dialog" role="dialog" aria-modal="true" aria-label={`${author.display_name}的${label}`} onMouseDown={(event) => event.stopPropagation()}>
        <header><div><span>社区关系</span><h2>{author.display_name}</h2></div><button type="button" aria-label="关闭关系列表" title="关闭" onClick={onClose}><X size={18} /></button></header>
        <div className="community-relationship-tabs" role="tablist"><button type="button" role="tab" aria-selected={relationshipType === 'followers'} className={clsx(relationshipType === 'followers' && 'active')} onClick={() => onTypeChange('followers')}>粉丝 {author.follower_count}</button><button type="button" role="tab" aria-selected={relationshipType === 'following'} className={clsx(relationshipType === 'following' && 'active')} onClick={() => onTypeChange('following')}>关注 {author.following_count}</button></div>
        <div className="community-relationship-list">
          {loading ? <div className="community-search-state">正在加载{label}…</div> : result?.items.length ? result.items.map((member) => <article key={member.id}>
            <button type="button" className="community-relationship-person" onClick={() => onOpenProfile(member.id)}><span>{member.avatar_url ? <img src={member.avatar_url} alt="" /> : getAvatarLabel(member.display_name)}</span><div><strong>{member.display_name}{member.verification_status === 'verified' && <ShieldCheck size={13} />}</strong><small>{member.organization || member.region || formatCommunityIdentity(member.identity_type)}</small><em>{member.post_count} 篇发布 · {member.follower_count} 粉丝</em></div></button>
            <button className={clsx('community-topic-follow', member.is_followed && 'following')} type="button" onClick={() => onFollow(member.id)}>{member.is_followed ? '已关注' : '关注'}</button>
          </article>) : <div className="community-search-state"><UserRound size={22} /><strong>还没有{label}</strong><span>{relationshipType === 'followers' ? '继续分享有价值的养殖记录，新的交流会慢慢聚集。' : '关注农技人员、养殖同行和感兴趣的话题，推荐内容会更贴近你。'}</span></div>}
        </div>
        {result?.next_offset != null && <footer><button type="button" disabled={loadingMore} onClick={onLoadMore}>{loadingMore ? '正在加载' : '加载更多'}</button></footer>}
      </section>
    </div>
  );
}

function CommunityBlockedUsersDialog({
  users,
  loading,
  pendingUserIds,
  onClose,
  onUnblock,
}: {
  users: ApiCommunityAuthor[];
  loading: boolean;
  pendingUserIds: Set<string>;
  onClose: () => void;
  onUnblock: (author: ApiCommunityAuthor) => void;
}) {
  return (
    <div className="community-overlay" role="presentation" onMouseDown={onClose}>
      <section className="community-relationship-dialog" role="dialog" aria-modal="true" aria-label="已屏蔽用户" onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div><span>社区隐私</span><h2>已屏蔽用户</h2></div>
          <button type="button" aria-label="关闭已屏蔽用户" title="关闭" onClick={onClose}><X size={18} /></button>
        </header>
        <div className="community-relationship-list">
          {loading ? <div className="community-search-state">正在加载已屏蔽用户…</div> : users.length > 0 ? users.map((author) => (
            <article key={author.id}>
              <div className="community-relationship-person">
                <span>{author.avatar_url ? <img src={author.avatar_url} alt="" /> : getAvatarLabel(author.display_name)}</span>
                <div><strong>{author.display_name}{author.verification_status === 'verified' && <ShieldCheck size={13} />}</strong><small>{author.organization || author.region || formatCommunityIdentity(author.identity_type)}</small><em>{author.post_count} 篇发布 · {author.follower_count} 粉丝</em></div>
              </div>
              <button className="community-topic-follow" type="button" disabled={pendingUserIds.has(author.id)} onClick={() => onUnblock(author)}>{pendingUserIds.has(author.id) ? '正在解除' : '解除屏蔽'}</button>
            </article>
          )) : <div className="community-search-state"><UserRound size={22} /><strong>没有已屏蔽用户</strong><span>你屏蔽的用户会显示在这里，并可随时恢复互动权限。</span></div>}
        </div>
      </section>
    </div>
  );
}

function CommunityCollectionsDialog({
  collections,
  detail,
  loading,
  saving,
  targetPost,
  onClose,
  onDelete,
  onOpenCollection,
  onOpenPost,
  onSave,
  onTogglePost,
}: {
  collections: ApiCommunityBookmarkCollection[];
  detail: ApiCommunityBookmarkCollectionDetail | null;
  loading: boolean;
  saving: boolean;
  targetPost: ApiCommunityPost | null;
  onClose: () => void;
  onDelete: (collectionId: string) => void;
  onOpenCollection: (collectionId: string) => void;
  onOpenPost: (postId: string) => void;
  onSave: (collectionId: string | null, name: string, description: string) => Promise<void>;
  onTogglePost: (collectionId: string) => void;
}) {
  const [editor, setEditor] = useState<{ id: string | null; name: string; description: string } | null>(null);
  const startCreate = () => setEditor({ id: null, name: '', description: '' });
  const startEdit = () => detail && setEditor({ id: detail.collection.id, name: detail.collection.name, description: detail.collection.description ?? '' });
  const saveEditor = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editor?.name.trim() || saving) return;
    try {
      await onSave(editor.id, editor.name.trim(), editor.description);
      setEditor(null);
    } catch {
      // Parent already presents the API failure in the shared toast.
    }
  };
  return (
    <div className="community-overlay community-collections-overlay" role="presentation" onMouseDown={onClose}>
      <section className="community-collections-dialog" role="dialog" aria-modal="true" aria-label="我的收藏夹" onMouseDown={(event) => event.stopPropagation()}>
        <header><div><span>我的收藏</span><h2>{targetPost ? '归入收藏夹' : '收藏夹'}</h2><p>{targetPost ? `将“${targetPost.title}”整理进专题，之后可在这里快速回看。` : '把有价值的病例、经验和资料整理成自己的养殖专题。'}</p></div><button type="button" aria-label="关闭收藏夹" title="关闭" onClick={onClose}><X size={18} /></button></header>
        <div className="community-collections-layout">
          <aside>
            <div className="community-collections-aside-title"><strong>我的专题</strong><button type="button" onClick={startCreate}><Plus size={14} />新建</button></div>
            <div className="community-collection-list">{loading ? <p>正在加载收藏夹…</p> : collections.length > 0 ? collections.map((collection) => <article key={collection.id} className={clsx(detail?.collection.id === collection.id && 'selected')}><button type="button" className="community-collection-summary" onClick={() => targetPost ? undefined : onOpenCollection(collection.id)}><span><Folder size={16} /></span><div><strong>{collection.name}</strong><small>{collection.item_count} 篇内容</small></div></button>{targetPost ? <button type="button" className={clsx('community-topic-follow', collection.contains_post && 'following')} onClick={() => onTogglePost(collection.id)}>{collection.contains_post ? '已收录' : '收录'}</button> : <button className="community-collection-open" type="button" aria-label={`查看 ${collection.name}`} title="查看专题" onClick={() => onOpenCollection(collection.id)}><ChevronRight size={15} /></button>}</article>) : <div className="community-collections-empty"><FolderPlus size={20} /><strong>还没有收藏专题</strong><span>新建一个专题，把重要内容沉淀下来。</span></div>}</div>
          </aside>
          <main>{editor ? <form className="community-collection-editor" onSubmit={(event) => void saveEditor(event)}><header><strong>{editor.id ? '编辑收藏专题' : '新建收藏专题'}</strong><button type="button" onClick={() => setEditor(null)}><X size={15} /></button></header><label><span>专题名称</span><input autoFocus value={editor.name} maxLength={40} onChange={(event) => setEditor({ ...editor, name: event.target.value })} placeholder="例如：五龄管理资料" /></label><label><span>说明（可选）</span><textarea value={editor.description} maxLength={180} onChange={(event) => setEditor({ ...editor, description: event.target.value })} placeholder="记录这个专题适合解决什么问题" /></label><footer><button type="button" onClick={() => setEditor(null)}>取消</button><button className="community-submit-post" type="submit" disabled={saving || !editor.name.trim()}>{saving ? '正在保存' : '保存专题'}</button></footer></form> : targetPost ? <div className="community-collection-target-state"><Bookmark size={24} /><strong>选择一个专题</strong><span>收录会同时保存这篇帖子；取消收录不会影响其他收藏夹。</span></div> : detail ? <section className="community-collection-detail"><header><div><span>收藏专题</span><h3>{detail.collection.name}</h3><p>{detail.collection.description || '暂未填写专题说明'}</p></div><div><button type="button" onClick={startEdit}><PencilLine size={15} />编辑</button><button className="danger" type="button" onClick={() => onDelete(detail.collection.id)}><Trash2 size={15} />删除</button></div></header>{detail.posts.length > 0 ? <div className="community-collection-post-list">{detail.posts.map((post) => <button type="button" key={post.id} onClick={() => onOpenPost(post.id)}><span>{formatCommunityPostType(post.post_type)}</span><strong>{post.title}</strong><small>{post.author.display_name} · {post.like_count} 赞 · {post.comment_count} 评论</small></button>)}</div> : <div className="community-collection-target-state"><Folder size={23} /><strong>这个专题还是空的</strong><span>打开帖子后选择“归入收藏夹”，即可把内容整理到这里。</span></div>}</section> : <div className="community-collection-target-state"><Folder size={24} /><strong>选择一个收藏专题</strong><span>在左侧打开专题，就能查看已保存的养殖经验和病例资料。</span></div>}</main>
        </div>
      </section>
    </div>
  );
}

function CommunityDirectMessagesDialog({
  activeThread,
  directMessages,
  draft,
  loading,
  recipient,
  sending,
  threads,
  onClose,
  onDraftChange,
  onOpenThread,
  onSend,
}: {
  activeThread: ApiCommunityDirectThread | null;
  directMessages: ApiCommunityDirectMessage[];
  draft: string;
  loading: boolean;
  recipient: ApiCommunityAuthor | null;
  sending: boolean;
  threads: ApiCommunityDirectThread[];
  onClose: () => void;
  onDraftChange: (value: string) => void;
  onOpenThread: (thread: ApiCommunityDirectThread) => void;
  onSend: () => void;
}) {
  const activeRecipient = activeThread?.counterpart ?? recipient;
  return (
    <div className="community-overlay" role="presentation" onMouseDown={onClose}>
      <section className="community-direct-dialog" role="dialog" aria-modal="true" aria-label="社区私信" onMouseDown={(event) => event.stopPropagation()}>
        <aside>
          <header><div><span>社区交流</span><h2>私信</h2></div><button type="button" aria-label="关闭" onClick={onClose}><X size={18} /></button></header>
          <div className="community-direct-thread-list">
            {threads.length > 0 ? threads.map((thread) => <button className={clsx(activeThread?.id === thread.id && 'active')} type="button" key={thread.id} onClick={() => onOpenThread(thread)}><div className="community-comment-avatar">{thread.counterpart.avatar_url ? <img src={thread.counterpart.avatar_url} alt="" /> : getAvatarLabel(thread.counterpart.display_name)}</div><span><strong>{thread.counterpart.display_name}</strong><small>{thread.last_message_preview || '开始交流'}</small></span>{thread.unread_count > 0 && <i>{thread.unread_count > 9 ? '9+' : thread.unread_count}</i>}</button>) : <p>还没有私信会话。</p>}
          </div>
        </aside>
        <main>
          {activeRecipient ? <><header><div className="community-author"><div className="community-comment-avatar">{activeRecipient.avatar_url ? <img src={activeRecipient.avatar_url} alt="" /> : getAvatarLabel(activeRecipient.display_name)}</div><div><strong>{activeRecipient.display_name}</strong><small>{activeRecipient.organization || activeRecipient.region || formatCommunityIdentity(activeRecipient.identity_type)}</small></div></div></header><div className="community-direct-message-list">{loading ? <span>正在加载消息</span> : directMessages.length > 0 ? directMessages.map((message) => <article className={clsx(message.is_mine && 'mine')} key={message.id}><p>{message.content}</p><small>{formatCommunityTime(message.created_at)}</small></article>) : <div className="community-direct-empty"><MessageCircle size={22} /><strong>开始一次专业交流</strong><span>请勿发送联系方式、住址等敏感信息。</span></div>}</div><footer><textarea value={draft} maxLength={2000} disabled={sending} onChange={(event) => onDraftChange(event.target.value)} placeholder={`向 ${activeRecipient.display_name} 发送消息`} /><button type="button" disabled={sending || !draft.trim()} onClick={onSend}><Send size={17} />发送</button></footer></> : <div className="community-direct-empty"><MessageCircle size={24} /><strong>选择一个会话</strong><span>从左侧查看已有私信，或从用户主页发起交流。</span></div>}
        </main>
      </section>
    </div>
  );
}

function CommunityCaseUpdateDialog({ post, onCancel, onSubmit }: { post: ApiCommunityPost; onCancel: () => void; onSubmit: (payload: { occurred_on: string; outcome_status: ApiCommunityCaseUpdate['outcome_status']; content: string }) => void }) {
  const [occurredOn, setOccurredOn] = useState(new Date().toISOString().slice(0, 10));
  const [outcomeStatus, setOutcomeStatus] = useState<ApiCommunityCaseUpdate['outcome_status']>('observing');
  const [content, setContent] = useState('');
  return <div className="community-overlay" role="presentation" onMouseDown={onCancel}><section className="community-case-update-dialog" role="dialog" aria-modal="true" aria-label="添加病例随访" onMouseDown={(event) => event.stopPropagation()}><header><div><span>病例随访</span><h2>{post.title}</h2></div><button type="button" aria-label="关闭" onClick={onCancel}><X size={18} /></button></header><div className="community-composer-row"><label><span>观察日期</span><input type="date" value={occurredOn} onChange={(event) => setOccurredOn(event.target.value)} /></label><label><span>当前状态</span><select value={outcomeStatus} onChange={(event) => setOutcomeStatus(event.target.value as ApiCommunityCaseUpdate['outcome_status'])}><option value="observing">继续观察</option><option value="improved">已有改善</option><option value="stable">情况稳定</option><option value="worsened">有所加重</option><option value="resolved">问题解决</option></select></label></div><label><span>随访记录</span><textarea value={content} maxLength={3000} onChange={(event) => setContent(event.target.value)} placeholder="记录新的症状变化、采取的措施和结果" /></label><footer><button type="button" onClick={onCancel}>取消</button><button className="community-submit-post" type="button" disabled={!content.trim()} onClick={() => onSubmit({ occurred_on: occurredOn, outcome_status: outcomeStatus, content: content.trim() })}>加入时间线</button></footer></section></div>;
}

function CommunitySaveCaseDialog({ post, farms, batches, onCancel, onSubmit }: { post: ApiCommunityPost; farms: ApiFarm[]; batches: ApiSilkwormBatch[]; onCancel: () => void; onSubmit: (farmId: string, batchId: string | null) => void }) {
  const [farmId, setFarmId] = useState(farms[0]?.id ?? '');
  const [batchId, setBatchId] = useState('');
  const matchingBatches = batches.filter((batch) => batch.farm_id === farmId);
  return <div className="community-overlay" role="presentation" onMouseDown={onCancel}><section className="community-save-case-dialog" role="dialog" aria-modal="true" aria-label="保存病例到养殖台账" onMouseDown={(event) => event.stopPropagation()}><header><div><span>社区 → 养殖台账</span><h2>保存病例</h2></div><button type="button" aria-label="关闭" onClick={onCancel}><X size={18} /></button></header><p>“{post.title}” 会复制为你的私人病例，社区原帖不会被修改。</p>{farms.length > 0 ? <div className="community-composer-row"><label><span>养殖场</span><select value={farmId} onChange={(event) => { setFarmId(event.target.value); setBatchId(''); }}>{farms.map((farm) => <option value={farm.id} key={farm.id}>{farm.name}</option>)}</select></label><label><span>关联批次（可选）</span><select value={batchId} onChange={(event) => setBatchId(event.target.value)}><option value="">暂不关联</option>{matchingBatches.map((batch) => <option value={batch.id} key={batch.id}>{batch.batch_code || batch.variety || '未命名批次'}</option>)}</select></label></div> : <div className="community-inline-error"><span>请先在养殖工作台中创建一个养殖场。</span></div>}<footer><button type="button" onClick={onCancel}>取消</button><button className="community-submit-post" type="button" disabled={!farmId} onClick={() => onSubmit(farmId, batchId || null)}>保存到台账</button></footer></section></div>;
}

function CommunityNotificationsDialog({ notifications, onClose, onOpenDirectMessages, onOpenPost }: { notifications: ApiCommunityNotifications | null; onClose: () => void; onOpenDirectMessages: (threadId: string) => void; onOpenPost: (postId: string) => void }) {
  const [filter, setFilter] = useState<'all' | 'interaction' | 'social' | 'system'>('all');
  const visibleItems = (notifications?.items ?? []).filter((item) => {
    if (filter === 'all') return true;
    if (filter === 'interaction') return ['post_like', 'post_comment', 'comment_reply', 'comment_like', 'answer_accepted', 'case_update', 'mention'].includes(item.notification_type);
    if (filter === 'social') return ['follow', 'direct_message'].includes(item.notification_type);
    return item.notification_type === 'moderation';
  });
  return <div className="community-overlay community-notification-overlay" role="presentation" onMouseDown={onClose}><section className="community-notifications-dialog" role="dialog" aria-modal="true" aria-labelledby="community-notifications-title" onMouseDown={(event) => event.stopPropagation()}><header><div><span>社区动态</span><h2 id="community-notifications-title">通知</h2></div><button type="button" aria-label="关闭通知" title="关闭" onClick={onClose}><X size={18} /></button></header><div className="community-notification-filters" role="tablist"><button type="button" role="tab" className={clsx(filter === 'all' && 'active')} aria-selected={filter === 'all'} onClick={() => setFilter('all')}>全部</button><button type="button" role="tab" className={clsx(filter === 'interaction' && 'active')} aria-selected={filter === 'interaction'} onClick={() => setFilter('interaction')}>互动</button><button type="button" role="tab" className={clsx(filter === 'social' && 'active')} aria-selected={filter === 'social'} onClick={() => setFilter('social')}>关系</button><button type="button" role="tab" className={clsx(filter === 'system' && 'active')} aria-selected={filter === 'system'} onClick={() => setFilter('system')}>系统</button></div><div>{notifications ? visibleItems.length > 0 ? visibleItems.map((item) => <button type="button" key={item.id} onClick={() => {
    if (item.notification_type === 'direct_message') {
      onOpenDirectMessages(typeof item.payload.thread_id === 'string' ? item.payload.thread_id : '');
    } else if (item.post_id) {
      onOpenPost(item.post_id);
    }
  }}><div className="community-notification-avatar">{item.actor?.avatar_url ? <img src={item.actor.avatar_url} alt="" /> : getAvatarLabel(item.actor?.display_name ?? 'C')}</div><span><strong>{item.actor?.display_name ?? 'CanW'}</strong>{formatNotificationText(item.notification_type, item.payload)}<small>{formatCommunityTime(item.created_at)}</small></span></button>) : <p className="community-muted">这个分类暂时没有通知</p> : <p className="community-muted">正在加载通知</p>}</div></section></div>;
}

function CommunityDeletePostDialog({ post, onCancel, onConfirm }: { post: ApiCommunityPost; onCancel: () => void; onConfirm: () => void }) {
  return <CommunityConfirmDialog title="删除帖子？" titleId="community-delete-post-title" description={<>“{post.title}” 将从社区中移除，相关互动也不再公开显示。</>} onCancel={onCancel} onConfirm={onConfirm} />;
}

function CommunityDeleteCommentDialog({ comment, onCancel, onConfirm }: { comment: ApiCommunityComment; onCancel: () => void; onConfirm: () => void }) {
  return <CommunityConfirmDialog title="删除评论？" titleId="community-delete-comment-title" description={<>“{comment.content}” 将不再公开显示；其下回复会保留。</>} onCancel={onCancel} onConfirm={onConfirm} />;
}

function CommunityReportDialog({ post, onCancel, onSubmit }: { post: ApiCommunityPost; onCancel: () => void; onSubmit: (reason: string, detail: string) => void }) {
  const [reason, setReason] = useState('不准确或不完整');
  const [detail, setDetail] = useState('');
  return <div className="community-overlay community-confirm-overlay" role="presentation" onMouseDown={onCancel}><section className="community-report-dialog" role="dialog" aria-modal="true" aria-labelledby="community-report-title" onMouseDown={(event) => event.stopPropagation()}><header><div><span>社区治理</span><h2 id="community-report-title">举报帖子</h2></div><button type="button" aria-label="关闭举报窗口" title="关闭" onClick={onCancel}><X size={18} /></button></header><p>“{post.title}” 将提交给社区审核。</p><label><span>举报原因</span><select value={reason} onChange={(event) => setReason(event.target.value)}><option>不准确或不完整</option><option>不当医疗建议</option><option>虚假或误导信息</option><option>隐私或敏感信息</option><option>广告或无关内容</option><option>其他</option></select></label><textarea value={detail} maxLength={1000} onChange={(event) => setDetail(event.target.value)} placeholder="补充说明（可选）" /><footer><button type="button" onClick={onCancel}>取消</button><button className="community-submit-post" type="button" onClick={() => onSubmit(reason, detail)}>提交举报</button></footer></section></div>;
}

function MemoryThread() {
  const graphNodes = [
    { name: '白僵病', type: '疾病', active: true },
    { name: '体表白粉', type: '症状', active: false },
    { name: '高湿环境', type: '诱因', active: false },
    { name: '隔离病蚕', type: '措施', active: false },
    { name: '蚕座消毒', type: '措施', active: false },
  ];
  const relationRows = [
    ['白僵病', '表现为', '体表白粉'],
    ['高湿环境', '增加风险', '白僵病'],
    ['白僵病', '建议处理', '隔离病蚕'],
    ['蚕座消毒', '用于控制', '病原扩散'],
  ];

  return (
    <article className="conversation-card feature-page graph-page">
      <section className="feature-hero graph-hero">
        <div>
          <span className="feature-kicker">Knowledge Graph</span>
          <h1>家蚕疾病知识图谱</h1>
          <p>围绕疾病、症状、病原、环境和防治措施建立关系网络，后续可接 Neo4j / RAG 证据来源。</p>
        </div>
        <label className="graph-search">
          <Search size={16} />
          <input placeholder="搜索疾病、症状或处理措施" />
        </label>
      </section>

      <section className="graph-explorer">
        <div className="graph-canvas" aria-label="知识图谱预览">
          {graphNodes.map((node, index) => (
            <button
              className={clsx('graph-node', node.active && 'active', `node-${index + 1}`)}
              type="button"
              key={node.name}
            >
              <strong>{node.name}</strong>
              <span>{node.type}</span>
            </button>
          ))}
          <i className="graph-edge edge-1" />
          <i className="graph-edge edge-2" />
          <i className="graph-edge edge-3" />
          <i className="graph-edge edge-4" />
        </div>
        <div className="graph-inspector">
          <span>当前节点</span>
          <strong>白僵病</strong>
          <p>真菌性疾病，常与高湿、通风不足、病原污染有关。可从症状、诱因、处理措施三个方向继续展开。</p>
          <div className="graph-stats">
            <div><strong>42</strong><span>关联节点</span></div>
            <div><strong>16</strong><span>证据片段</span></div>
            <div><strong>5</strong><span>防治路径</span></div>
          </div>
        </div>
      </section>

      <section className="inline-panel graph-relation-panel">
        <div className="panel-title">
          <span>关系路径</span>
          <small>疾病、症状、诱因、防治措施</small>
        </div>
        <div className="graph-relation-list">
          {relationRows.map(([from, relation, to]) => (
            <div className="graph-relation-row" key={`${from}-${relation}-${to}`}>
              <span>{from}</span>
              <small>{relation}</small>
              <strong>{to}</strong>
            </div>
          ))}
        </div>
      </section>
    </article>
  );
}

type HusbandryFormKind = 'farm' | 'batch' | 'daily' | 'case' | 'follow-up' | null;
type HusbandryDeleteTarget =
  | { kind: 'farm'; farm: ApiFarm }
  | { kind: 'batch'; batch: ApiSilkwormBatch }
  | { kind: 'daily'; batchId: string; record: ApiHusbandryDailyRecord }
  | { kind: 'case'; caseItem: ApiHusbandryCase }
  | { kind: 'follow-up'; caseItem: ApiHusbandryCase; followUp: ApiHusbandryFollowUp }
  | { kind: 'asset'; asset: ApiHusbandryAsset };

function HusbandryThread({
  accessToken,
  conversations,
  sourceConversationId,
  onAuthExpired,
  onCommunityDraft,
  onNotify,
  onRequireAuth,
  onSourceConversationConsumed,
  userPreferences,
}: {
  accessToken: string;
  conversations: DiagnosisConversation[];
  sourceConversationId: string | null;
  onAuthExpired: () => void;
  onCommunityDraft: (draft: ApiCommunityPost) => void;
  onNotify: (message: string, tone?: ToastTone) => void;
  onRequireAuth: () => void;
  onSourceConversationConsumed: () => void;
  userPreferences: UserPreferences;
}) {
  const [dashboard, setDashboard] = useState<ApiHusbandryDashboard | null>(null);
  const [farms, setFarms] = useState<ApiFarm[]>([]);
  const [batches, setBatches] = useState<ApiSilkwormBatch[]>([]);
  const [cases, setCases] = useState<ApiHusbandryCase[]>([]);
  const [dailyRecords, setDailyRecords] = useState<ApiHusbandryDailyRecord[]>([]);
  const [selectedFarmId, setSelectedFarmId] = useState('');
  const [selectedBatchId, setSelectedBatchId] = useState('');
  const [activeForm, setActiveForm] = useState<HusbandryFormKind>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [farmSwitcherOpen, setFarmSwitcherOpen] = useState(false);
  const [batchSwitcherOpen, setBatchSwitcherOpen] = useState(false);
  const [toolPanel, setToolPanel] = useState<'insights' | 'calculator'>('insights');
  const [caseFilter, setCaseFilter] = useState<'all' | 'open' | 'closed'>('all');
  const [caseQuery, setCaseQuery] = useState('');
  const [caseScope, setCaseScope] = useState<'batch' | 'farm'>('batch');
  const [expandedCaseId, setExpandedCaseId] = useState<string | null>(null);
  const [dailyListExpanded, setDailyListExpanded] = useState(false);
  const [caseListExpanded, setCaseListExpanded] = useState(false);
  const [dailyDateFilter, setDailyDateFilter] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<HusbandryDeleteTarget | null>(null);
  const [deleteSaving, setDeleteSaving] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [batchStatusSaving, setBatchStatusSaving] = useState(false);
  const [caseActionSavingId, setCaseActionSavingId] = useState<string | null>(null);
  const [pendingAttachments, setPendingAttachments] = useState<File[]>([]);
  const attachmentPickerRef = useRef<HTMLInputElement | null>(null);
  const [farmExporting, setFarmExporting] = useState(false);

  const selectedBatch = batches.find((batch) => batch.id === selectedBatchId) ?? null;
  const selectedFarm = farms.find((farm) => farm.id === selectedFarmId) ?? null;
  const isReadOnlySelection = selectedFarm?.status === 'archived' || selectedBatch?.status !== 'active';
  const visibleBatches = batches.filter((batch) => batch.farm_id === selectedFarmId);
  const batchCases = useMemo(() => selectedBatchId ? cases.filter((caseItem) => caseItem.batch_id === selectedBatchId) : [], [cases, selectedBatchId]);
  const farmCases = useMemo(() => selectedFarmId ? cases.filter((caseItem) => caseItem.farm_id === selectedFarmId) : [], [cases, selectedFarmId]);
  const scopedCases = caseScope === 'farm' ? farmCases : batchCases;
  const visibleCases = useMemo(() => {
    const query = caseQuery.trim().toLowerCase();
    return scopedCases.filter((caseItem) => {
      const matchesStatus = caseFilter === 'all' || (caseFilter === 'closed' ? caseItem.status === 'closed' : caseItem.status !== 'closed');
      const matchesQuery = !query || [caseItem.title, caseItem.suspected_disease, caseItem.symptom_summary, caseItem.batch_code].filter(Boolean).join(' ').toLowerCase().includes(query);
      return matchesStatus && matchesQuery;
    });
  }, [scopedCases, caseFilter, caseQuery]);
  const filteredDailyRecords = useMemo(() => dailyDateFilter ? dailyRecords.filter((record) => record.record_date === dailyDateFilter) : dailyRecords, [dailyRecords, dailyDateFilter]);
  const displayedDailyRecords = dailyListExpanded ? filteredDailyRecords : filteredDailyRecords.slice(0, 5);
  const displayedCases = caseListExpanded ? visibleCases : visibleCases.slice(0, 5);
  const selectFarm = (farmId: string) => {
    setSelectedFarmId(farmId);
    setSelectedBatchId(batches.find((batch) => batch.farm_id === farmId)?.id ?? '');
    setDailyListExpanded(false);
    setCaseListExpanded(false);
    setDailyDateFilter('');
    setCaseScope('batch');
    setFarmSwitcherOpen(false);
  };
  const selectBatch = (batchId: string) => {
    const nextBatch = batches.find((batch) => batch.id === batchId);
    if (!nextBatch) return;
    setDailyRecords([]);
    setSelectedBatchId(batchId);
    setCaseFilter('all');
    setCaseScope('batch');
    setCaseQuery('');
    setExpandedCaseId(null);
    setDailyListExpanded(false);
    setCaseListExpanded(false);
    setDailyDateFilter('');
    setBatchSwitcherOpen(false);
    onNotify(`已切换至批次：${formatBatchName(nextBatch)}`, 'success');
  };
  const selectedCase = cases.find((caseItem) => caseItem.id === draft.case_id) ?? null;
  const today = todayInputValue();

  const showRequestError = (error: unknown, fallback: string) => {
    if (error instanceof ApiRequestError && error.status === 401) {
      onAuthExpired();
      return;
    }
    onNotify(error instanceof Error ? error.message : fallback, 'error');
  };

  const loadWorkspace = async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const [nextDashboard, nextFarms, nextBatches, nextCases] = await Promise.all([
        fetchHusbandryDashboard(accessToken, selectedFarmId || undefined),
        fetchHusbandryFarms(accessToken),
        fetchSilkwormBatches(accessToken),
        fetchHusbandryCases(accessToken),
      ]);
      setDashboard(nextDashboard);
      setFarms(nextFarms);
      setBatches(nextBatches);
      setCases(nextCases);
      setSelectedFarmId((current) => current || nextBatches[0]?.farm_id || nextFarms[0]?.id || '');
      setSelectedBatchId((current) => current || nextBatches[0]?.id || '');
    } catch (error) {
      showRequestError(error, '养殖台账加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadWorkspace();
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken || !selectedBatchId) {
      setDailyRecords([]);
      return;
    }
    let cancelled = false;
    setRecordsLoading(true);
    void fetchHusbandryDailyRecords(accessToken, selectedBatchId)
      .then((items) => {
        if (!cancelled) setDailyRecords(items);
      })
      .catch((error) => {
        if (!cancelled) showRequestError(error, '每日记录加载失败');
      })
      .finally(() => {
        if (!cancelled) setRecordsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, selectedBatchId]);

  useEffect(() => {
    if (!accessToken || !selectedFarmId) return;
    void fetchHusbandryDashboard(accessToken, selectedFarmId)
      .then(setDashboard)
      .catch((error) => showRequestError(error, '养殖概览加载失败'));
  }, [accessToken, selectedFarmId]);

  const openForm = (kind: Exclude<HusbandryFormKind, null>, extra: Record<string, string> = {}) => {
    const base: Record<string, string> = {
      record_date: today,
      occurred_on: today,
      observed_on: today,
      severity: 'medium',
      status: 'needs_more_info',
      ...extra,
    };
    if (kind !== 'farm' && !base.farm_id) base.farm_id = selectedBatch?.farm_id || selectedFarmId || farms[0]?.id || '';
    if (kind === 'case' && !base.batch_id) base.batch_id = selectedBatch?.id ?? '';
    setPendingAttachments([]);
    setDraft(base);
    setActiveForm(kind);
  };

  const editDailyRecord = (record: ApiHusbandryDailyRecord) => openForm('daily', {
    record_date: record.record_date,
    temperature_celsius: record.temperature_celsius?.toString() ?? '', humidity_percent: record.humidity_percent?.toString() ?? '',
    feedings: record.feedings?.toString() ?? '', leaf_amount_kg: record.leaf_amount_kg?.toString() ?? '',
    sick_count: record.sick_count?.toString() ?? '', death_count: record.death_count?.toString() ?? '',
    observations: record.observations ?? '', management_notes: record.management_notes ?? '',
  });
  const editFollowUp = (caseItem: ApiHusbandryCase, followUp: ApiHusbandryFollowUp) => openForm('follow-up', {
    case_id: caseItem.id,
    follow_up_id: followUp.id,
    observed_on: followUp.observed_on,
    action_taken: followUp.action_taken ?? '',
    note: followUp.note ?? '',
    affected_count: followUp.affected_count?.toString() ?? '',
    death_count: followUp.death_count?.toString() ?? '',
    next_follow_up_on: followUp.next_follow_up_on ?? '',
  });
  const addPendingAttachments = (event: ChangeEvent<HTMLInputElement>) => {
    const next = Array.from(event.target.files ?? []).filter((file) => file.type.startsWith('image/') || file.type.startsWith('video/'));
    if (!next.length) return;
    setPendingAttachments((items) => [...items, ...next].slice(0, 6));
    event.target.value = '';
  };
  const removePendingAttachment = (index: number) => setPendingAttachments((items) => items.filter((_, itemIndex) => itemIndex !== index));
  const requestDelete = (target: HusbandryDeleteTarget) => {
    setDeleteError('');
    setDeleteTarget(target);
  };
  const deleteFollowUp = async (caseItem: ApiHusbandryCase, followUp: ApiHusbandryFollowUp) => {
    setDeleteSaving(true);
    setDeleteError('');
    try {
      await deleteHusbandryCaseFollowUp(accessToken, caseItem.id, followUp.id);
      setCases((items) => items.map((item) => item.id === caseItem.id ? { ...item, follow_ups: item.follow_ups.filter((itemFollowUp) => itemFollowUp.id !== followUp.id) } : item));
      setDeleteTarget(null);
      onNotify('随访记录已删除', 'success');
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : '删除随访失败，请稍后重试。');
    } finally {
      setDeleteSaving(false);
    }
  };
  const deleteAsset = async (asset: ApiHusbandryAsset) => {
    setDeleteSaving(true);
    setDeleteError('');
    try {
      await deleteHusbandryAsset(accessToken, asset.id);
      setDailyRecords((items) => items.map((record) => ({ ...record, assets: record.assets.filter((item) => item.id !== asset.id) })));
      setCases((items) => items.map((caseItem) => ({ ...caseItem, assets: caseItem.assets.filter((item) => item.id !== asset.id) })));
      setDeleteTarget(null);
      onNotify('现场附件已删除', 'success');
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : '删除附件失败，请稍后重试。');
    } finally {
      setDeleteSaving(false);
    }
  };
  const deleteDailyRecord = async (batchId: string, record: ApiHusbandryDailyRecord) => {
    setDeleteSaving(true);
    setDeleteError('');
    try {
      await deleteHusbandryDailyRecord(accessToken, batchId, record.id);
      setDailyRecords((items) => items.filter((item) => item.id !== record.id));
      onNotify('每日记录已删除', 'success');
      await loadWorkspace();
      setDeleteTarget(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : '删除记录失败，请稍后重试。';
      setDeleteError(message);
    } finally {
      setDeleteSaving(false);
    }
  };
  const createCaseCommunityDraft = async (caseItem: ApiHusbandryCase) => {
    try {
      const communityDraft = await createCommunityDraftFromHusbandryCase(accessToken, caseItem.id);
      onCommunityDraft(communityDraft);
      onNotify('已生成社区草稿，请确认脱敏内容后发布', 'success');
    } catch (error) {
      showRequestError(error, '生成社区草稿失败');
    }
  };
  const archiveFarm = async (farm: ApiFarm) => {
    setDeleteSaving(true);
    setDeleteError('');
    try {
      await updateHusbandryFarm(accessToken, farm.id, { status: 'archived' });
      const remainingFarms = farms.filter((item) => item.id !== farm.id);
      const nextFarm = remainingFarms[0] ?? null;
      const remainingBatches = batches.filter((batch) => batch.farm_id !== farm.id);
      setFarms(remainingFarms);
      setBatches(remainingBatches);
      setCases((items) => items.filter((caseItem) => caseItem.farm_id !== farm.id));
      setSelectedFarmId(nextFarm?.id ?? '');
      setSelectedBatchId(remainingBatches.find((batch) => batch.farm_id === nextFarm?.id)?.id ?? '');
      setDailyRecords([]);
      setDashboard(null);
      onNotify(nextFarm ? '养殖场已删除，已切换至下一个养殖场' : '养殖场已删除，可新建养殖场继续记录', 'success');
      setDeleteTarget(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : '删除养殖场失败，请稍后重试。';
      setDeleteError(message);
    } finally {
      setDeleteSaving(false);
    }
  };
  const archiveBatch = async (batch: ApiSilkwormBatch) => {
    setDeleteSaving(true);
    setDeleteError('');
    try {
      await updateSilkwormBatch(accessToken, batch.id, { status: 'archived' });
      const remainingBatches = batches.filter((item) => item.id !== batch.id);
      const nextBatch = remainingBatches.find((item) => item.farm_id === batch.farm_id) ?? null;
      setBatches(remainingBatches);
      setSelectedBatchId(nextBatch?.id ?? '');
      setDailyRecords([]);
      onNotify(nextBatch ? '批次已删除，已切换至同场下一批次' : '批次已删除，可新建批次继续记录', 'success');
      setDeleteTarget(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : '删除批次失败，请稍后重试。';
      setDeleteError(message);
    } finally {
      setDeleteSaving(false);
    }
  };
  const deleteCase = async (caseItem: ApiHusbandryCase) => {
    setDeleteSaving(true);
    setDeleteError('');
    try {
      await deleteHusbandryCase(accessToken, caseItem.id);
      setCases((items) => items.filter((item) => item.id !== caseItem.id));
      setExpandedCaseId((current) => current === caseItem.id ? null : current);
      onNotify('病例已删除', 'success');
      await loadWorkspace();
      setDeleteTarget(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : '删除病例失败，请稍后重试。';
      setDeleteError(message);
    } finally {
      setDeleteSaving(false);
    }
  };
  const updateBatchLifecycle = async (nextStatus: 'active' | 'finished') => {
    if (!selectedBatch || batchStatusSaving) return;
    setBatchStatusSaving(true);
    try {
      const updated = await updateSilkwormBatch(accessToken, selectedBatch.id, { status: nextStatus });
      setBatches((items) => items.map((item) => item.id === updated.id ? updated : item));
      onNotify(nextStatus === 'finished' ? '批次已完成，后续内容将以只读方式保留' : '批次已恢复为在养状态', 'success');
      await loadWorkspace();
    } catch (error) {
      showRequestError(error, '更新批次状态失败');
    } finally {
      setBatchStatusSaving(false);
    }
  };
  const closeCase = async (caseItem: ApiHusbandryCase) => {
    if (caseActionSavingId) return;
    setCaseActionSavingId(caseItem.id);
    try {
      const updated = await updateHusbandryCase(accessToken, caseItem.id, { status: 'closed' });
      setCases((items) => items.map((item) => item.id === updated.id ? updated : item));
      onNotify('病例已关闭', 'success');
      await loadWorkspace();
    } catch (error) {
      showRequestError(error, '关闭病例失败');
    } finally {
      setCaseActionSavingId(null);
    }
  };
  const canCloseHusbandryCase = (caseItem: ApiHusbandryCase) => {
    if (caseItem.status !== 'processing') return false;
    const publishedAt = caseItem.expert_reviews?.[0]?.published_at;
    if (!publishedAt) return false;
    const reviewedAt = new Date(publishedAt).getTime();
    return Number.isFinite(reviewedAt) && caseItem.follow_ups.some((followUp) => new Date(followUp.created_at).getTime() >= reviewedAt);
  };
  const exportCurrentBatch = () => {
    if (!selectedBatch) return;
    const rows: Array<Array<string | number | null | undefined>> = [
      ['养殖台账导出'],
      ['养殖场', selectedFarm?.name ?? selectedBatch.farm_name],
      ['批次', formatBatchName(selectedBatch)],
      ['导出日期', todayInputValue()],
      [],
      ['每日记录'],
      ['日期', '温度（℃）', '湿度（%）', '给桑次数', '桑叶（kg）', '发病数', '死亡数', '观察记录', '管理措施'],
      ...[...dailyRecords].reverse().map((record) => [record.record_date, record.temperature_celsius, record.humidity_percent, record.feedings, record.leaf_amount_kg, record.sick_count, record.death_count, record.observations, record.management_notes]),
      [],
      ['病例台账'],
      ['发生日期', '标题', '状态', '严重程度', '疑似疾病', '症状记录', '处置建议', '随访次数'],
      ...batchCases.map((caseItem) => [caseItem.occurred_on, caseItem.title, formatCaseStatus(caseItem.status), formatCaseSeverity(caseItem.severity), caseItem.suspected_disease, caseItem.symptom_summary, caseItem.recommendation, caseItem.follow_ups.length]),
    ];
    downloadCsvFile(toSafeMarkdownFileName(`CanW-${selectedFarm?.name ?? selectedBatch.farm_name}-${formatBatchName(selectedBatch)}-养殖台账-${todayInputValue()}`), rows);
    onNotify('当前批次台账已导出', 'success');
  };
  const exportCurrentFarm = async () => {
    if (!selectedFarm || farmExporting) return;
    setFarmExporting(true);
    try {
      const farmBatches = batches.filter((batch) => batch.farm_id === selectedFarm.id);
      const recordGroups = await Promise.all(farmBatches.map(async (batch) => ({ batch, records: await fetchHusbandryDailyRecords(accessToken, batch.id) })));
      const rows: Array<Array<string | number | null | undefined>> = [
        ['养殖工作台 · 养殖场台账'],
        ['养殖场', selectedFarm.name],
        ['位置', selectedFarm.location],
        ['导出日期', todayInputValue()],
        [],
        ['批次概览'],
        ['批次', '状态', '品种', '龄期', '起养日期', '预计上蔟', '起养数量'],
        ...farmBatches.map((batch) => [formatBatchName(batch), formatBatchLifecycle(batch.status), batch.variety, batch.instar, batch.start_date, batch.expected_cocooning_date, batch.population_count]),
        [],
        ['每日记录'],
        ['批次', '日期', '温度（℃）', '湿度（%）', '给桑次数', '桑叶（kg）', '发病', '死亡', '观察', '管理措施'],
        ...recordGroups.flatMap(({ batch, records }) => records.map((record) => [formatBatchName(batch), record.record_date, record.temperature_celsius, record.humidity_percent, record.feedings, record.leaf_amount_kg, record.sick_count, record.death_count, record.observations, record.management_notes])),
        [],
        ['病例与随访'],
        ['批次', '发生日期', '标题', '状态', '严重程度', '疑似疾病', '随访次数'],
        ...farmCases.map((caseItem) => [caseItem.batch_code ?? '未关联批次', caseItem.occurred_on, caseItem.title, formatCaseStatus(caseItem.status), formatCaseSeverity(caseItem.severity), caseItem.suspected_disease, caseItem.follow_ups.length]),
      ];
      downloadCsvFile(toSafeMarkdownFileName(`CanW-${selectedFarm.name}-全场养殖台账-${todayInputValue()}`), rows);
      onNotify('养殖场台账已导出', 'success');
    } catch (error) {
      showRequestError(error, '导出养殖场台账失败');
    } finally {
      setFarmExporting(false);
    }
  };
  const confirmDelete = async () => {
    if (!deleteTarget || deleteSaving) return;
    if (deleteTarget.kind === 'farm') await archiveFarm(deleteTarget.farm);
    if (deleteTarget.kind === 'batch') await archiveBatch(deleteTarget.batch);
    if (deleteTarget.kind === 'daily') await deleteDailyRecord(deleteTarget.batchId, deleteTarget.record);
    if (deleteTarget.kind === 'case') await deleteCase(deleteTarget.caseItem);
    if (deleteTarget.kind === 'follow-up') await deleteFollowUp(deleteTarget.caseItem, deleteTarget.followUp);
    if (deleteTarget.kind === 'asset') await deleteAsset(deleteTarget.asset);
  };

  useEffect(() => {
    if (!sourceConversationId) return;
    const conversation = conversations.find((item) => item.id === sourceConversationId);
    openForm('case', {
      source_conversation_id: sourceConversationId,
      title: conversation?.title ?? '',
      status: 'suspected',
    });
    onSourceConversationConsumed();
  }, [sourceConversationId]);

  const saveForm = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!accessToken || saving || !activeForm) return;
    setSaving(true);
    try {
      if (activeForm === 'farm') {
        const farmPayload = {
          name: draft.name ?? '',
          ...compactPayload({ location: draft.location, notes: draft.notes }),
        };
        const farm = draft.farm_id
          ? await updateHusbandryFarm(accessToken, draft.farm_id, farmPayload)
          : await createHusbandryFarm(accessToken, farmPayload);
        setFarms((items) => draft.farm_id ? items.map((item) => item.id === farm.id ? farm : item) : [farm, ...items]);
        if (!draft.farm_id) setSelectedFarmId(farm.id);
        setActiveForm(null);
        onNotify(draft.farm_id ? '养殖场信息已更新' : '养殖场已保存，现在可以建立养殖批次', 'success');
        return;
      }
      if (activeForm === 'batch') {
        const batchPayload = {
          farm_id: draft.farm_id,
          ...compactPayload({
            batch_code: draft.batch_code,
            variety: draft.variety,
            instar: draft.instar,
            start_date: draft.start_date,
            expected_cocooning_date: draft.expected_cocooning_date,
            population_count: optionalNumber(draft.population_count),
          notes: draft.notes,
          }),
        };
        const batch = draft.batch_id
          ? await updateSilkwormBatch(accessToken, draft.batch_id, compactPayload({ batch_code: draft.batch_code, variety: draft.variety, instar: draft.instar, start_date: draft.start_date, expected_cocooning_date: draft.expected_cocooning_date, population_count: optionalNumber(draft.population_count), notes: draft.notes }))
          : await createSilkwormBatch(accessToken, batchPayload);
        setSelectedBatchId(batch.id);
        setActiveForm(null);
        onNotify(draft.batch_id ? '养殖批次已更新' : '养殖批次已建立', 'success');
        await loadWorkspace();
        return;
      }
      if (activeForm === 'daily' && selectedBatch) {
        const savedRecord = await upsertHusbandryDailyRecord(accessToken, selectedBatch.id, {
          record_date: draft.record_date,
          ...compactPayload({
            temperature_celsius: optionalNumber(draft.temperature_celsius),
            humidity_percent: optionalNumber(draft.humidity_percent),
            feedings: optionalNumber(draft.feedings),
            leaf_amount_kg: optionalNumber(draft.leaf_amount_kg),
            sick_count: optionalNumber(draft.sick_count),
            death_count: optionalNumber(draft.death_count),
            observations: draft.observations,
            management_notes: draft.management_notes,
          }),
        });
        const uploadedAssets = await uploadHusbandryAssets(accessToken, `/husbandry/batches/${selectedBatch.id}/daily-records/${savedRecord.id}/assets`, pendingAttachments);
        const record = { ...savedRecord, assets: [...(savedRecord.assets ?? []), ...uploadedAssets] };
        setDailyRecords((items) => [record, ...items.filter((item) => item.record_date !== record.record_date)]);
        setActiveForm(null);
        const risks = userPreferences.husbandry_health_notifications ? getDailyRecordRiskMessages(record, userPreferences) : [];
        onNotify(risks.length ? `每日记录已保存；请关注：${risks.slice(0, 2).join('、')}` : '每日养殖记录已保存', risks.length ? 'error' : 'success');
        await loadWorkspace();
        return;
      }
      if (activeForm === 'case') {
        const casePayload = {
          farm_id: draft.farm_id,
          batch_id: draft.batch_id || null,
          source_conversation_id: draft.source_conversation_id || null,
          title: draft.title,
          occurred_on: draft.occurred_on,
          severity: (draft.severity || 'medium') as HusbandryCaseSeverity,
          status: (draft.status || 'needs_more_info') as HusbandryCaseStatus,
          ...compactPayload({
            symptom_summary: draft.symptom_summary,
            suspected_disease: draft.suspected_disease,
            diagnosis_summary: draft.diagnosis_summary,
            recommendation: draft.recommendation,
          }),
        };
        const savedCase = draft.case_id
          ? await updateHusbandryCase(accessToken, draft.case_id, compactPayload({ title: draft.title, symptom_summary: draft.symptom_summary, suspected_disease: draft.suspected_disease }))
          : await createHusbandryCase(accessToken, casePayload);
        const uploadedAssets = await uploadHusbandryAssets(accessToken, `/husbandry/cases/${savedCase.id}/assets`, pendingAttachments);
        const createdCase = { ...savedCase, assets: [...(savedCase.assets ?? []), ...uploadedAssets] };
        setCases((items) => draft.case_id ? items.map((item) => item.id === createdCase.id ? createdCase : item) : [createdCase, ...items]);
        setActiveForm(null);
        onNotify(draft.case_id ? '病例已更新' : draft.source_conversation_id ? '问诊已存为病例，可继续随访' : '病例已保存', 'success');
        await loadWorkspace();
        return;
      }
      if (activeForm === 'follow-up' && selectedCase) {
        const followUpPayload = {
          observed_on: draft.observed_on,
          ...compactPayload({
            action_taken: draft.action_taken,
            note: draft.note,
            affected_count: optionalNumber(draft.affected_count),
            death_count: optionalNumber(draft.death_count),
            next_follow_up_on: draft.next_follow_up_on,
          }),
        };
        const updatedCase = draft.follow_up_id
          ? await updateHusbandryCaseFollowUp(accessToken, selectedCase.id, draft.follow_up_id, followUpPayload)
          : await addHusbandryCaseFollowUp(accessToken, selectedCase.id, followUpPayload);
        setCases((items) => items.map((item) => item.id === updatedCase.id ? updatedCase : item));
        setActiveForm(null);
        onNotify('随访记录已保存', 'success');
        await loadWorkspace();
      }
    } catch (error) {
      showRequestError(error, '保存失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  if (!accessToken) {
    return <article className="conversation-card feature-page husbandry-page husbandry-login-empty"><Flower2 size={30} /><h1>登录后，建立你的养殖台账</h1><p>保存养殖批次、每日数据、异常病例和随访结果。</p><button type="button" onClick={onRequireAuth}>登录后开始记录</button></article>;
  }

  const sourceConversation = conversations.find((item) => item.id === draft.source_conversation_id) ?? null;
  const editingDailyRecord = activeForm === 'daily' ? dailyRecords.find((record) => record.record_date === draft.record_date) ?? null : null;
  const editingCase = activeForm === 'case' && draft.case_id ? cases.find((caseItem) => caseItem.id === draft.case_id) ?? null : null;

  return (
    <article className="conversation-card feature-page husbandry-page">
      <section className="husbandry-hero">
        <div><span className="feature-kicker">Farming Workbench</span><h1>把养殖过程变得可追溯</h1><p>日常环境、饲养与健康情况统一记录在批次下；发现异常后，问诊可以直接沉淀为病例和随访。</p></div>
        <div className="husbandry-hero-actions"><button type="button" onClick={() => openForm('farm')}><FolderPlus size={16} />新建养殖场</button><button className="husbandry-primary-action" type="button" disabled={farms.length === 0} onClick={() => setFarmSwitcherOpen(true)}><ArrowDownUp size={16} />切换养殖场</button></div>
      </section>

      <section className="husbandry-metrics" aria-label="养殖概览">
        <HusbandryMetric icon={Flower2} label="在养批次" value={dashboard?.active_batch_count ?? 0} tone="leaf" />
        <HusbandryMetric icon={ClipboardList} label="处理中病例" value={dashboard?.open_case_count ?? 0} tone="clay" />
        <HusbandryMetric icon={Bell} label="待随访" value={dashboard?.due_follow_up_count ?? 0} tone="sun" />
        <HusbandryMetric icon={Check} label="今日已记录" value={dashboard?.today_record_count ?? 0} tone="ink" />
      </section>

      <section className="husbandry-farm-shell" aria-label="当前养殖场工作区">
        <header className="husbandry-farm-shell-header"><div><span>当前养殖场</span><h2>{selectedFarm?.name || '选择养殖场'}</h2><p>{selectedFarm ? [selectedFarm.status === 'archived' ? '历史归档 · 只读' : null, selectedFarm.location, selectedFarm.notes].filter(Boolean).join(' · ') || '记录本场的批次、日常养殖与健康情况。' : '先新建一个养殖场，再开始建立批次。'}</p></div><div>{selectedFarm && <button className="husbandry-export-action" type="button" disabled={farmExporting} onClick={() => void exportCurrentFarm()}><Download size={14} />{farmExporting ? '正在导出' : '导出全场'}</button>}{selectedFarm?.status === 'active' && <button type="button" onClick={() => openForm('farm', { farm_id: selectedFarm.id, name: selectedFarm.name, location: selectedFarm.location ?? '', notes: selectedFarm.notes ?? '' })}>编辑场地</button>}{selectedFarm?.status === 'active' && <button className="husbandry-danger-action" type="button" onClick={() => requestDelete({ kind: 'farm', farm: selectedFarm })}>删除养殖场</button>}</div></header>
        <section className="husbandry-batch-switcher" aria-label="切换当前批次"><label><span>切换批次</span><button className="husbandry-batch-switch-trigger" disabled={visibleBatches.length === 0} type="button" onClick={() => setBatchSwitcherOpen(true)}><strong>{selectedBatch ? formatBatchName(selectedBatch) : '还没有批次'}</strong><ChevronDown size={16} /></button></label><button type="button" disabled={selectedFarm?.status !== 'active'} onClick={() => openForm('batch', { farm_id: selectedFarmId })}><Plus size={15} />新建批次</button></section>
        <section className="husbandry-batch-well" aria-label="当前批次信息">
          <header>
            <div><span>当前批次 · {selectedBatch ? formatBatchLifecycle(selectedBatch.status) : '等待选择'}</span><h3>{selectedBatch ? formatBatchName(selectedBatch) : '尚未选择批次'}</h3></div>
            <div className="husbandry-batch-actions">
              {selectedBatch && <button className="husbandry-export-action" type="button" onClick={exportCurrentBatch}><Download size={14} />导出台账</button>}
              {selectedBatch?.status === 'active' && selectedFarm?.status === 'active' && <button className="husbandry-complete-action" type="button" disabled={batchStatusSaving} onClick={() => void updateBatchLifecycle('finished')}><Check size={14} />完成批次</button>}
              {selectedBatch?.status === 'finished' && selectedFarm?.status === 'active' && <button type="button" disabled={batchStatusSaving} onClick={() => void updateBatchLifecycle('active')}><RotateCcw size={14} />恢复在养</button>}
              {selectedBatch && selectedBatch.status !== 'archived' && selectedFarm?.status === 'active' && <button type="button" onClick={() => openForm('batch', { batch_id: selectedBatch.id, farm_id: selectedBatch.farm_id, batch_code: selectedBatch.batch_code ?? '', variety: selectedBatch.variety ?? '', instar: selectedBatch.instar ?? '', start_date: selectedBatch.start_date ?? '', expected_cocooning_date: selectedBatch.expected_cocooning_date ?? '', population_count: selectedBatch.population_count?.toString() ?? '', notes: selectedBatch.notes ?? '' })}>编辑批次</button>}
              {selectedBatch && selectedBatch.status !== 'archived' && selectedFarm?.status === 'active' && <button className="husbandry-danger-action" type="button" onClick={() => requestDelete({ kind: 'batch', batch: selectedBatch })}>删除批次</button>}
            </div>
          </header>
          {selectedBatch ? <HusbandryBatchRuler batch={selectedBatch} /> : <p>建立批次后，可记录龄期、每日养殖情况和异常病例。</p>}
        </section>
      </section>

      {loading ? <div className="husbandry-loading" role="status">正在整理养殖台账…</div> : <div className="husbandry-workspace-grid">
        <section className="husbandry-panel"><header><div><span>每日记录</span><h2>{selectedBatch ? formatBatchName(selectedBatch) : '先建立一个批次'}</h2></div><div className="husbandry-daily-header-actions"><label className={clsx('husbandry-date-picker', dailyDateFilter && 'active')} data-tooltip="选择日期"><CalendarDays size={16} /><input aria-label="选择日期" type="date" value={dailyDateFilter} onChange={(event) => { setDailyDateFilter(event.target.value); setDailyListExpanded(false); }} /></label><button type="button" disabled={!selectedBatch || isReadOnlySelection} onClick={() => openForm('daily')}><Plus size={15} />记录今天</button></div></header>{recordsLoading ? <p className="husbandry-placeholder">正在读取记录…</p> : filteredDailyRecords.length > 0 ? <><div className={clsx('husbandry-daily-list husbandry-scroll-list', dailyListExpanded && 'is-expanded')}>{displayedDailyRecords.map((record) => <DailyRecordRow key={record.id} record={record} preferences={userPreferences} readOnly={isReadOnlySelection} onEdit={() => editDailyRecord(record)} onDelete={() => { if (selectedBatch) requestDelete({ kind: 'daily', batchId: selectedBatch.id, record }); }} />)}</div>{filteredDailyRecords.length > 5 && <footer className="husbandry-list-footer"><button type="button" onClick={() => setDailyListExpanded((current) => !current)}>{dailyListExpanded ? '收起记录' : `展开更多（${filteredDailyRecords.length - 5}）`}</button></footer>}</> : <HusbandryEmpty text={dailyDateFilter ? `${formatDateLabel(dailyDateFilter)}还没有养殖记录。` : selectedBatch ? isReadOnlySelection ? selectedBatch.status === 'finished' ? '该批次已完成，当前仅供查看。' : '这是历史归档批次，当前仅供查看。' : '还没有日记录，先记下今天的环境与健康情况。' : '请先在上方新建养殖场和批次，再开始记录每日数据。'} action={dailyDateFilter ? '查看最近记录' : undefined} onAction={dailyDateFilter ? () => setDailyDateFilter('') : undefined} />}</section>
        <section className="husbandry-panel">
          <header>
            <div><span>病例台账 · 当前批次</span><h2>{selectedBatch ? '发现异常，持续跟进' : '请先选择一个批次'}</h2></div>
            <button type="button" disabled={!selectedBatch || isReadOnlySelection} onClick={() => openForm('case')}><Plus size={15} />新增病例</button>
          </header>
          <div className="husbandry-case-scope" role="tablist" aria-label="病例查看范围">
            <button className={clsx(caseScope === 'batch' && 'active')} type="button" role="tab" aria-selected={caseScope === 'batch'} onClick={() => { setCaseScope('batch'); setCaseListExpanded(false); }}>当前批次 {batchCases.length}</button>
            <button className={clsx(caseScope === 'farm' && 'active')} type="button" role="tab" aria-selected={caseScope === 'farm'} disabled={!selectedFarm} onClick={() => { setCaseScope('farm'); setCaseListExpanded(false); }}>本养殖场 {farmCases.length}</button>
          </div>
          <div className="husbandry-case-controls">
            <div role="group" aria-label="病例状态筛选">
              <button className={clsx(caseFilter === 'all' && 'active')} type="button" onClick={() => setCaseFilter('all')}>全部 {scopedCases.length}</button>
              <button className={clsx(caseFilter === 'open' && 'active')} type="button" onClick={() => setCaseFilter('open')}>处理中 {scopedCases.filter((item) => item.status !== 'closed').length}</button>
              <button className={clsx(caseFilter === 'closed' && 'active')} type="button" onClick={() => setCaseFilter('closed')}>已关闭</button>
            </div>
            <label><Search size={13} /><input value={caseQuery} onChange={(event) => { setCaseQuery(event.target.value); setCaseListExpanded(false); }} placeholder="搜索当前批次病例" /></label>
          </div>
          {visibleCases.length > 0 ? <>
            <div className={clsx('husbandry-case-list husbandry-scroll-list', caseListExpanded && 'is-expanded')}>
              {displayedCases.map((caseItem) => <div className="husbandry-case-item" key={caseItem.id}>
                <article className="husbandry-case-row">
                  <i className={`severity-${caseItem.severity}`} />
                  <div className="husbandry-case-copy"><strong>{caseItem.title}</strong><span>{caseItem.farm_name}{caseItem.batch_code ? ` · ${caseItem.batch_code}` : ''} · {formatDateLabel(caseItem.occurred_on)}</span></div>
                  <em className={`case-status-${caseItem.status}`}>{formatCaseStatus(caseItem.status)}</em>
                  <div className="husbandry-case-actions" aria-label={`${caseItem.title} 操作`}>
                    <button className={clsx(expandedCaseId === caseItem.id && 'active')} type="button" aria-label="查看随访" data-tooltip="查看随访" onClick={() => setExpandedCaseId((current) => current === caseItem.id ? null : caseItem.id)}><History size={14} /><span>{caseItem.follow_ups.length || ''}</span></button>
                    {!isReadOnlySelection && <button type="button" aria-label="生成社区草稿" data-tooltip="生成社区草稿" onClick={() => void createCaseCommunityDraft(caseItem)}><Globe size={14} /></button>}
                    {!isReadOnlySelection && <button type="button" aria-label="编辑病例" data-tooltip="编辑病例" onClick={() => openForm('case', { case_id: caseItem.id, farm_id: caseItem.farm_id, batch_id: caseItem.batch_id ?? '', title: caseItem.title, occurred_on: caseItem.occurred_on, symptom_summary: caseItem.symptom_summary ?? '', suspected_disease: caseItem.suspected_disease ?? '', severity: caseItem.severity, status: caseItem.status, diagnosis_summary: caseItem.diagnosis_summary ?? '', recommendation: caseItem.recommendation ?? '' })}><PencilLine size={14} /></button>}
                    {!isReadOnlySelection && caseItem.status !== 'closed' && <button type="button" aria-label="记录随访" data-tooltip="记录随访" onClick={() => openForm('follow-up', { case_id: caseItem.id })}><Plus size={15} /></button>}
                    {!isReadOnlySelection && caseItem.status !== 'closed' && <button className="complete" type="button" disabled={caseActionSavingId === caseItem.id || !canCloseHusbandryCase(caseItem)} aria-label="关闭病例" data-tooltip={canCloseHusbandryCase(caseItem) ? '关闭病例' : '需在专家发布意见后补充一次随访，才可结案'} onClick={() => void closeCase(caseItem)}><Check size={14} /></button>}
                    {!isReadOnlySelection && caseItem.status !== 'closed' && (caseItem.expert_reviews?.length ?? 0) === 0 && <button className="danger" type="button" aria-label="删除病例" data-tooltip="删除病例" onClick={() => requestDelete({ kind: 'case', caseItem })}><Trash2 size={14} /></button>}
                  </div>
                </article>
                {expandedCaseId === caseItem.id && <><HusbandryFollowUpTimeline caseItem={caseItem} readOnly={isReadOnlySelection} onEdit={(followUp) => editFollowUp(caseItem, followUp)} onDelete={(followUp) => requestDelete({ kind: 'follow-up', caseItem, followUp })} />{caseItem.expert_reviews?.length ? <DiagnosisExpertReviewPanel reviews={caseItem.expert_reviews} /> : null}</>}
              </div>)}
            </div>
            {visibleCases.length > 5 && <footer className="husbandry-list-footer"><button type="button" onClick={() => setCaseListExpanded((current) => !current)}>{caseListExpanded ? '收起记录' : `展开更多（${visibleCases.length - 5}）`}</button></footer>}
          </> : <HusbandryEmpty text={scopedCases.length ? '没有匹配的病例，调整筛选条件或搜索词试试。' : caseScope === 'farm' ? '本养殖场尚无病例。先选择一个批次后即可新增病例。' : selectedBatch ? isReadOnlySelection ? selectedBatch.status === 'finished' ? '该批次已完成，病例仅供回顾。' : '这是历史归档批次，当前仅供查看。' : '当前批次尚无病例。可从问诊导入或新增病例。' : '请先在上方选择或新建批次，再查看病例台账。'} action={scopedCases.length ? '清除筛选' : undefined} onAction={scopedCases.length ? () => { setCaseFilter('all'); setCaseQuery(''); setCaseListExpanded(false); } : undefined} />}
        </section>
      </div>}

      <section className="husbandry-tools"><header><div><span>养殖工作台 · 当前批次</span><h2>{toolPanel === 'insights' ? '把每日数据变成现场提醒' : '快速估算，不用离开记录台'}</h2></div><div><button className={clsx(toolPanel === 'insights' && 'active')} type="button" onClick={() => setToolPanel('insights')}>健康洞察</button><button className={clsx(toolPanel === 'calculator' && 'active')} type="button" onClick={() => setToolPanel('calculator')}>实用计算</button></div></header>{toolPanel === 'insights' ? <HusbandryInsights records={dailyRecords} batch={selectedBatch} cases={batchCases} preferences={userPreferences} /> : <HusbandryCalculator batch={selectedBatch} />}</section>

      {activeForm && <HusbandryModal title={activeForm === 'farm' ? '新建养殖场' : activeForm === 'batch' ? '新建养殖批次' : activeForm === 'daily' ? `记录 ${selectedBatch ? formatBatchName(selectedBatch) : '每日养殖'}` : activeForm === 'case' ? sourceConversation ? '将问诊存为病例' : '新建病例' : `病例随访：${selectedCase?.title || ''}`} eyebrow={activeForm === 'case' ? '病例台账' : '养殖档案'} onCancel={() => setActiveForm(null)}><form className="husbandry-form" onSubmit={saveForm}>
        {activeForm === 'farm' && <><label>养殖场名称<input autoFocus maxLength={80} required value={draft.name ?? ''} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="如：湖州家庭蚕室" /></label><label>所在位置（可选）<input maxLength={160} value={draft.location ?? ''} onChange={(event) => setDraft({ ...draft, location: event.target.value })} placeholder="如：吴兴区八里店镇" /></label><label>备注（可选）<textarea maxLength={2000} value={draft.notes ?? ''} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} placeholder="记录蚕室、桑园或管理特点" /></label></>}
        {activeForm === 'batch' && <><label>所属养殖场<select required value={draft.farm_id} onChange={(event) => setDraft({ ...draft, farm_id: event.target.value })}>{farms.map((farm) => <option key={farm.id} value={farm.id}>{farm.name}</option>)}</select></label><div className="husbandry-form-grid"><label>批次编号<input maxLength={80} value={draft.batch_code ?? ''} onChange={(event) => setDraft({ ...draft, batch_code: event.target.value })} placeholder="如：2026 夏蚕 A-01" /></label><label>蚕品种<input maxLength={80} value={draft.variety ?? ''} onChange={(event) => setDraft({ ...draft, variety: event.target.value })} placeholder="如：菁松×皓月" /></label><label>当前龄期<select value={draft.instar ?? ''} onChange={(event) => setDraft({ ...draft, instar: event.target.value })}><option value="">未填写</option>{['一龄', '二龄', '三龄', '四龄', '五龄', '上蔟'].map((item) => <option key={item}>{item}</option>)}</select></label><label>起养日期<input type="date" value={draft.start_date ?? today} onChange={(event) => setDraft({ ...draft, start_date: event.target.value })} /></label><label>预计上蔟日期<input type="date" value={draft.expected_cocooning_date ?? ''} onChange={(event) => setDraft({ ...draft, expected_cocooning_date: event.target.value })} /></label><label>起养数量<input type="number" min="0" value={draft.population_count ?? ''} onChange={(event) => setDraft({ ...draft, population_count: event.target.value })} /></label></div></>}
        {activeForm === 'daily' && <><div className="husbandry-form-grid"><label>记录日期<input type="date" required value={draft.record_date} onChange={(event) => setDraft({ ...draft, record_date: event.target.value })} /></label><label>温度（℃）<input type="number" step="0.1" value={draft.temperature_celsius ?? ''} onChange={(event) => setDraft({ ...draft, temperature_celsius: event.target.value })} /></label><label>湿度（%）<input type="number" step="0.1" value={draft.humidity_percent ?? ''} onChange={(event) => setDraft({ ...draft, humidity_percent: event.target.value })} /></label><label>给桑次数<input type="number" min="0" value={draft.feedings ?? ''} onChange={(event) => setDraft({ ...draft, feedings: event.target.value })} /></label><label>桑叶用量（kg）<input type="number" min="0" step="0.1" value={draft.leaf_amount_kg ?? ''} onChange={(event) => setDraft({ ...draft, leaf_amount_kg: event.target.value })} /></label><label>发病数量<input type="number" min="0" value={draft.sick_count ?? ''} onChange={(event) => setDraft({ ...draft, sick_count: event.target.value })} /></label><label>死亡数量<input type="number" min="0" value={draft.death_count ?? ''} onChange={(event) => setDraft({ ...draft, death_count: event.target.value })} /></label></div><label>观察到的情况<textarea maxLength={3000} value={draft.observations ?? ''} onChange={(event) => setDraft({ ...draft, observations: event.target.value })} placeholder="如：食桑正常，但湿度较高；发现少量体色异常。" /></label><label>管理措施（可选）<textarea maxLength={3000} value={draft.management_notes ?? ''} onChange={(event) => setDraft({ ...draft, management_notes: event.target.value })} placeholder="如：加强通风、蚕座消毒、隔离异常蚕。" /></label></>}
        {activeForm === 'case' && <><label>关联问诊（可选）<select disabled={Boolean(draft.case_id)} value={draft.source_conversation_id ?? ''} onChange={(event) => { const conversation = conversations.find((item) => item.id === event.target.value); setDraft({ ...draft, source_conversation_id: event.target.value, title: conversation?.title || draft.title, status: conversation ? 'suspected' : draft.status }); }}><option value="">手动录入</option>{conversations.map((conversation) => <option key={conversation.id} value={conversation.id}>{conversation.title}</option>)}</select></label>{sourceConversation && <div className="husbandry-source-note"><Sparkles size={15} />会话记录将随病例保存，便于继续复核。</div>}<div className="husbandry-form-grid"><label>养殖场<input readOnly value={selectedFarm?.name ?? '未选择养殖场'} /></label><label>关联批次<input readOnly value={selectedBatch ? formatBatchName(selectedBatch) : '未选择批次'} /></label><label>发生日期<input disabled={Boolean(draft.case_id)} type="date" required value={draft.occurred_on} onChange={(event) => setDraft({ ...draft, occurred_on: event.target.value })} /></label><label>严重程度<select value={draft.severity} onChange={(event) => setDraft({ ...draft, severity: event.target.value })}><option value="low">轻微</option><option value="medium">一般</option><option value="high">较重</option><option value="critical">紧急</option></select></label><label>当前状态<select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value })}><option value="needs_more_info">待补充</option><option value="suspected">疑似</option><option value="processing">处理中</option><option value="closed">已关闭</option></select></label></div><label>病例标题<input autoFocus maxLength={120} required value={draft.title ?? ''} onChange={(event) => setDraft({ ...draft, title: event.target.value })} placeholder="如：五龄蚕体色发白异常" /></label><label>症状记录<textarea maxLength={4000} value={draft.symptom_summary ?? ''} onChange={(event) => setDraft({ ...draft, symptom_summary: event.target.value })} placeholder="记录症状、数量、环境变化和已采取措施。" /></label><label>疑似疾病（可选）<input maxLength={160} value={draft.suspected_disease ?? ''} onChange={(event) => setDraft({ ...draft, suspected_disease: event.target.value })} placeholder="如：白僵病" /></label><label>初步判断（可选）<textarea maxLength={6000} value={draft.diagnosis_summary ?? ''} onChange={(event) => setDraft({ ...draft, diagnosis_summary: event.target.value })} placeholder="记录专家或问诊给出的初步判断。" /></label><label>处置建议（可选）<textarea maxLength={6000} value={draft.recommendation ?? ''} onChange={(event) => setDraft({ ...draft, recommendation: event.target.value })} placeholder="记录隔离、消毒、通风或送检等后续安排。" /></label></>}
        {activeForm === 'case' && Boolean(draft.case_id) && <p className="husbandry-form-lock-note">风险等级、病例状态、专家判断和处置建议由专家复核流程维护；此处仅可补充病例标题、症状和疑似疾病。</p>}
        {(activeForm === 'daily' || activeForm === 'case') && <HusbandryAttachmentPicker
          inputRef={attachmentPickerRef}
          pendingAttachments={pendingAttachments}
          existingAssets={activeForm === 'daily' ? editingDailyRecord?.assets ?? [] : editingCase?.assets ?? []}
          onPick={addPendingAttachments}
          onRemovePending={removePendingAttachment}
          onRemoveExisting={(asset) => requestDelete({ kind: 'asset', asset })}
        />}
        {activeForm === 'follow-up' && selectedCase && <><label>随访日期<input type="date" required value={draft.observed_on} onChange={(event) => setDraft({ ...draft, observed_on: event.target.value })} /></label><label>已采取的措施<textarea maxLength={3000} value={draft.action_taken ?? ''} onChange={(event) => setDraft({ ...draft, action_taken: event.target.value })} placeholder="如：隔离异常蚕、加强通风、清理蚕座。" /></label><label>观察结果<textarea maxLength={4000} value={draft.note ?? ''} onChange={(event) => setDraft({ ...draft, note: event.target.value })} placeholder="记录症状是否减轻、扩散或恢复。" /></label><div className="husbandry-form-grid"><label>当前发病数<input type="number" min="0" value={draft.affected_count ?? ''} onChange={(event) => setDraft({ ...draft, affected_count: event.target.value })} /></label><label>新增死亡数<input type="number" min="0" value={draft.death_count ?? ''} onChange={(event) => setDraft({ ...draft, death_count: event.target.value })} /></label><label>下次随访<input type="date" value={draft.next_follow_up_on ?? ''} onChange={(event) => setDraft({ ...draft, next_follow_up_on: event.target.value })} /></label></div></>}
        <footer className="husbandry-form-actions"><button type="button" disabled={saving} onClick={() => setActiveForm(null)}>取消</button><button className="husbandry-primary-action" disabled={saving || (activeForm === 'farm' && !draft.name?.trim()) || (activeForm === 'batch' && !draft.farm_id) || (activeForm === 'case' && (!draft.farm_id || !draft.title?.trim()))} type="submit">{saving ? '正在保存' : activeForm === 'case' && sourceConversation ? '保存为病例' : '保存'}</button></footer>
      </form></HusbandryModal>}
      {farmSwitcherOpen && <HusbandryModal eyebrow="养殖场" title="切换养殖场" onCancel={() => setFarmSwitcherOpen(false)}><div className="husbandry-farm-switcher-list">{farms.map((farm) => <button className={clsx(farm.id === selectedFarmId && 'active')} type="button" key={farm.id} onClick={() => selectFarm(farm.id)}><span><strong>{farm.name}</strong><small>{[farm.status === 'archived' ? '历史归档' : '在用', farm.location, farm.notes].filter(Boolean).join(' · ') || '未填写场地说明'}</small></span>{farm.id === selectedFarmId && <Check size={17} />}</button>)}</div></HusbandryModal>}
      {batchSwitcherOpen && <HusbandryModal eyebrow="养殖批次" title="切换批次" onCancel={() => setBatchSwitcherOpen(false)}><div className="husbandry-farm-switcher-list">{visibleBatches.map((batch) => <button className={clsx(batch.id === selectedBatchId && 'active')} type="button" key={batch.id} onClick={() => selectBatch(batch.id)}><span><strong>{formatBatchName(batch)}</strong><small>{[batch.status === 'archived' ? '历史归档' : batch.status === 'finished' ? '已完成' : '在养', batch.variety, batch.instar, batch.population_count ? `${batch.population_count.toLocaleString()} 头` : null].filter(Boolean).join(' · ')}</small></span>{batch.id === selectedBatchId && <Check size={17} />}</button>)}</div></HusbandryModal>}
      {deleteTarget && <HusbandryDeleteDialog
        title={deleteTarget.kind === 'farm' ? '删除养殖场？' : deleteTarget.kind === 'batch' ? '删除养殖批次？' : deleteTarget.kind === 'case' ? '删除病例？' : deleteTarget.kind === 'follow-up' ? '删除随访？' : deleteTarget.kind === 'asset' ? '删除现场附件？' : '删除养殖记录？'}
        description={deleteTarget.kind === 'farm'
          ? <>这会删除“<strong>{deleteTarget.farm.name}</strong>”。已有台账会保留。</>
          : deleteTarget.kind === 'batch'
            ? <>这会删除“<strong>{formatBatchName(deleteTarget.batch)}</strong>”。已有记录与病例会保留。</>
            : deleteTarget.kind === 'case'
              ? <>这会删除“<strong>{deleteTarget.caseItem.title}</strong>”及其随访记录。</>
              : deleteTarget.kind === 'follow-up'
                ? <>这会删除 <strong>{formatDateLabel(deleteTarget.followUp.observed_on)}</strong> 的随访记录。</>
                : deleteTarget.kind === 'asset'
                  ? <>这会删除附件“<strong>{deleteTarget.asset.file_name}</strong>”。</>
                  : <>这会删除 <strong>{formatDateLabel(deleteTarget.record.record_date)}</strong> 的养殖记录。</>}
        saving={deleteSaving}
        error={deleteError}
        onCancel={() => { if (!deleteSaving) setDeleteTarget(null); }}
        onConfirm={() => void confirmDelete()}
      />}
    </article>
  );
}

function HusbandryMetric({ icon: Icon, label, value, tone }: { icon: LucideIcon; label: string; value: number; tone: string }) {
  return <div className={`husbandry-metric tone-${tone}`}><span><Icon size={16} /></span><strong>{value}</strong><small>{label}</small></div>;
}

function HusbandryBatchRuler({ batch }: { batch: ApiSilkwormBatch }) {
  const labels = ['一龄', '二龄', '三龄', '四龄', '五龄', '上蔟'];
  const current = Math.max(0, labels.indexOf(batch.instar ?? ''));
  const facts = [
    { label: '蚕品种', value: batch.variety || '未填写' },
    { label: '起养数量', value: batch.population_count ? `${batch.population_count.toLocaleString()} 头` : '未填写' },
    { label: '预计上蔟', value: batch.expected_cocooning_date ? formatDateLabel(batch.expected_cocooning_date) : '未填写' },
  ];
  return <div className="husbandry-batch-status"><div className="husbandry-batch-stage"><span>{formatBatchLifecycle(batch.status)} · 养殖进度</span><strong className={clsx(`status-${batch.status}`)}>当前：{batch.instar || '未填写'}</strong></div><div className="husbandry-stage-track"><div className="husbandry-ruler" aria-label={`当前龄期：${batch.instar || '未填写'}`}>{labels.map((label, index) => <span className={clsx(index <= current && 'reached', index === current && 'current')} key={label}>{label}</span>)}</div></div><dl className="husbandry-batch-facts">{facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}</dl></div>;
}

function getDailyRecordRiskMessages(record: ApiHusbandryDailyRecord, preferences: Pick<UserPreferences, 'husbandry_temperature_min' | 'husbandry_temperature_max' | 'husbandry_humidity_max'> = defaultUserPreferences) {
  const messages: string[] = [];
  if (record.humidity_percent != null && record.humidity_percent >= preferences.husbandry_humidity_max) messages.push('湿度偏高');
  if (record.temperature_celsius != null && (record.temperature_celsius < preferences.husbandry_temperature_min || record.temperature_celsius > preferences.husbandry_temperature_max)) messages.push('温度需关注');
  if ((record.death_count ?? 0) > 0) messages.push('出现死亡');
  else if ((record.sick_count ?? 0) > 0) messages.push('发现发病');
  return messages;
}

function DailyRecordRow({ record, preferences, readOnly, onEdit, onDelete }: { record: ApiHusbandryDailyRecord; preferences: UserPreferences; readOnly: boolean; onEdit: () => void; onDelete: () => void }) {
  const metrics = [record.temperature_celsius !== null ? `${record.temperature_celsius}℃` : null, record.humidity_percent !== null ? `湿度 ${record.humidity_percent}%` : null, record.feedings !== null ? `${record.feedings} 次给桑` : null, record.leaf_amount_kg !== null ? `${record.leaf_amount_kg}kg 桑叶` : null, record.sick_count !== null ? `${record.sick_count} 发病` : null, record.death_count !== null ? `${record.death_count} 死亡` : null].filter(Boolean);
  const risks = getDailyRecordRiskMessages(record, preferences);
  return <article className={clsx('daily-record-row', risks.length > 0 && 'has-risk')}><time>{formatDateLabel(record.record_date)}</time><div className="daily-record-main"><div className="daily-record-metrics">{metrics.length ? metrics.map((metric) => <span key={metric}>{metric}</span>) : <span className="saved">已保存养殖记录</span>}{risks.length > 0 && <span className="daily-record-risk">{risks.join(' · ')}</span>}</div>{record.observations && <p>{record.observations}</p>}</div>{!readOnly && <div className="daily-record-actions"><button type="button" aria-label="编辑记录" data-tooltip="编辑记录" onClick={onEdit}><PencilLine size={14} /></button><button className="danger" type="button" aria-label="删除记录" data-tooltip="删除记录" onClick={onDelete}><Trash2 size={14} /></button></div>}</article>;
}

function HusbandryFollowUpTimeline({ caseItem, readOnly, onEdit, onDelete }: { caseItem: ApiHusbandryCase; readOnly: boolean; onEdit: (followUp: ApiHusbandryFollowUp) => void; onDelete: (followUp: ApiHusbandryFollowUp) => void }) {
  if (caseItem.follow_ups.length === 0) return <section className="husbandry-follow-up-timeline empty"><header><History size={15} /><strong>随访记录</strong></header><p>尚未添加随访。完成处置后，点击“随访”记录观察结果。</p></section>;
  return <section className="husbandry-follow-up-timeline"><header><History size={15} /><strong>随访记录</strong><span>{caseItem.follow_ups.length} 次</span></header><div>{caseItem.follow_ups.map((followUp) => { const facts = [followUp.affected_count !== null ? `发病 ${followUp.affected_count}` : null, followUp.death_count !== null ? `新增死亡 ${followUp.death_count}` : null, followUp.next_follow_up_on ? `下次 ${formatDateLabel(followUp.next_follow_up_on)}` : null].filter(Boolean); return <article key={followUp.id}><i /><div><header><strong>{formatDateLabel(followUp.observed_on)}</strong>{!readOnly && <span className="husbandry-follow-up-actions"><button type="button" aria-label="编辑随访" data-tooltip="编辑随访" onClick={() => onEdit(followUp)}><PencilLine size={13} /></button><button className="danger" type="button" aria-label="删除随访" data-tooltip="删除随访" onClick={() => onDelete(followUp)}><Trash2 size={13} /></button></span>}</header>{followUp.action_taken && <p><b>处置：</b>{followUp.action_taken}</p>}{followUp.note && <p><b>观察：</b>{followUp.note}</p>}{facts.length > 0 && <footer>{facts.map((fact) => <span key={fact}>{fact}</span>)}</footer>}</div></article>; })}</div></section>;
}

function HusbandryAttachmentPicker({
  inputRef,
  pendingAttachments,
  existingAssets,
  onPick,
  onRemovePending,
  onRemoveExisting,
}: {
  inputRef: RefObject<HTMLInputElement | null>;
  pendingAttachments: File[];
  existingAssets: ApiHusbandryAsset[];
  onPick: (event: ChangeEvent<HTMLInputElement>) => void;
  onRemovePending: (index: number) => void;
  onRemoveExisting: (asset: ApiHusbandryAsset) => void;
}) {
  return <section className="husbandry-attachment-picker"><header><div><ImageUp size={15} /><span>现场图片或视频</span></div><button type="button" onClick={() => inputRef.current?.click()}><Plus size={14} />添加附件</button></header><p>保存后会固定关联到当前记录或病例，便于回看与复核。</p><input ref={inputRef} className="sr-only" type="file" accept="image/*,video/*" multiple onChange={onPick} />{(existingAssets.length > 0 || pendingAttachments.length > 0) && <div className="husbandry-asset-list">{existingAssets.map((asset) => <article key={asset.id}>{asset.file_type === 'image' && asset.storage_url ? <img src={asset.storage_url} alt={asset.file_name} /> : <Video size={17} />}<span><strong>{asset.file_name}</strong><small>{formatAttachmentSize(asset.file_size)} · 已保存</small></span><button className="danger" type="button" aria-label={`删除 ${asset.file_name}`} data-tooltip="删除附件" onClick={() => onRemoveExisting(asset)}><Trash2 size={14} /></button></article>)}{pendingAttachments.map((file, index) => <article className="pending" key={`${file.name}-${file.lastModified}-${index}`}>{file.type.startsWith('image/') ? <ImageUp size={17} /> : <Video size={17} />}<span><strong>{file.name}</strong><small>{formatAttachmentSize(file.size)} · 保存时上传</small></span><button type="button" aria-label={`移除 ${file.name}`} data-tooltip="移除附件" onClick={() => onRemovePending(index)}><X size={14} /></button></article>)}</div>}</section>;
}

function HusbandryInsights({ records, batch, cases, preferences }: { records: ApiHusbandryDailyRecord[]; batch: ApiSilkwormBatch | null; cases: ApiHusbandryCase[]; preferences: UserPreferences }) {
  const alerts = useMemo(() => {
    const newest = records[0];
    const items: Array<{ tone: string; title: string; detail: string }> = [];
    if (!batch) items.push({ tone: 'quiet', title: '先选择一个养殖批次', detail: '建立批次后，系统会根据每日记录生成现场提醒。' });
    if (preferences.husbandry_health_notifications && newest?.humidity_percent != null && newest.humidity_percent >= preferences.husbandry_humidity_max) items.push({ tone: 'risk', title: '湿度偏高', detail: `最新湿度 ${newest.humidity_percent}%，已超过你设置的 ${preferences.husbandry_humidity_max}% 提醒阈值；建议加强通风、保持蚕座干燥。` });
    if (preferences.husbandry_health_notifications && newest?.temperature_celsius != null && (newest.temperature_celsius < preferences.husbandry_temperature_min || newest.temperature_celsius > preferences.husbandry_temperature_max)) items.push({ tone: 'risk', title: '温度超出提醒区间', detail: `最新温度 ${newest.temperature_celsius}℃，当前提醒范围是 ${preferences.husbandry_temperature_min}–${preferences.husbandry_temperature_max}℃。` });
    if (preferences.husbandry_health_notifications && newest && ((newest.sick_count ?? 0) > 0 || (newest.death_count ?? 0) > 0)) items.push({ tone: 'risk', title: '发现健康异常', detail: `最新记录有 ${newest.sick_count ?? 0} 条发病、${newest.death_count ?? 0} 条死亡数据，建议隔离、记录并按需发起问诊。` });
    const due = cases.filter((item) => item.status !== 'closed' && item.follow_ups.some((followUp) => followUp.next_follow_up_on && followUp.next_follow_up_on <= todayInputValue()));
    if (due.length) items.push({ tone: 'sun', title: `${due.length} 个病例需要随访`, detail: `优先更新：${due.slice(0, 2).map((item) => item.title).join('、')}。` });
    if (!items.length) items.push({ tone: preferences.husbandry_health_notifications ? 'good' : 'quiet', title: preferences.husbandry_health_notifications ? '记录状态良好' : '健康提醒已关闭', detail: preferences.husbandry_health_notifications ? records.length ? '近一条记录未发现明显预警项，建议持续记录环境与健康变化。' : '今天还没有记录，先补充温湿度和健康情况。' : '可在设置中的“养殖提醒”重新开启自动预警。' });
    return items;
  }, [records, batch, cases, preferences]);
  const chartRecords = [...records].slice(0, 7).reverse();
  return <div className="husbandry-insights"><div className="husbandry-alert-list">{alerts.map((item) => <article key={item.title} className={`husbandry-alert tone-${item.tone}`}><Bell size={16} /><div><strong>{item.title}</strong><p>{item.detail}</p></div></article>)}</div><div className="husbandry-mini-chart"><header><span>近 7 次记录</span><small>温度 / 湿度</small></header>{chartRecords.length ? <div className="mini-chart-bars">{chartRecords.map((item) => <div key={item.id}><i style={{ height: `${Math.min(100, Math.max(8, (item.humidity_percent ?? 0)))}%` }} title={`${item.humidity_percent ?? '—'}% 湿度`} /><b style={{ height: `${Math.min(100, Math.max(8, ((item.temperature_celsius ?? 0) / 40) * 100))}%` }} title={`${item.temperature_celsius ?? '—'}℃ 温度`} /><span>{formatDateLabel(item.record_date)}</span></div>)}</div> : <p>保存每日记录后，可在这里查看环境趋势。</p>}</div></div>;
}

function HusbandryCalculator({ batch }: { batch: ApiSilkwormBatch | null }) {
  const [population, setPopulation] = useState('1000');
  const [perThousand, setPerThousand] = useState('12');
  const [powder, setPowder] = useState('');
  const [ratio, setRatio] = useState('500');
  const leaves = Number(population) && Number(perThousand) ? ((Number(population) / 1000) * Number(perThousand)).toFixed(1) : '—';
  const solution = Number(powder) && Number(ratio) ? (Number(powder) * Number(ratio)).toFixed(0) : '—';
  return <div className="husbandry-calculator"><article><header><Scale size={17} /><strong>桑叶用量估算</strong></header><p>{batch ? `正在为“${formatBatchName(batch)}”估算，可按该批次实际数量调整。` : '先选择批次后再进行估算。'}</p><div><label>蚕数量<input type="number" min="0" value={population} onChange={(event) => setPopulation(event.target.value)} /></label><label>每千头桑叶（kg）<input type="number" min="0" step="0.1" value={perThousand} onChange={(event) => setPerThousand(event.target.value)} /></label></div><output>预计桑叶：<strong>{leaves} kg</strong></output></article><article><header><FlaskConical size={17} /><strong>消毒液配比换算</strong></header><p>{batch ? `配比结果将作为“${formatBatchName(batch)}”的现场参考。` : '选择批次后，可将结果用于当前批次的现场参考。'}</p><div><label>药粉（g）<input type="number" min="0" value={powder} onChange={(event) => setPowder(event.target.value)} /></label><label>稀释倍数<input type="number" min="1" value={ratio} onChange={(event) => setRatio(event.target.value)} /></label></div><output>可配溶液：<strong>{solution === '—' ? '—' : `${solution} mL`}</strong></output></article></div>;
}

function HusbandryEmpty({ text, action, onAction }: { text: string; action?: string; onAction?: () => void }) {
  return <div className="husbandry-empty"><p>{text}</p>{action && onAction && <button type="button" onClick={onAction}>{action}</button>}</div>;
}

function HusbandryModal({ eyebrow, title, children, onCancel }: { eyebrow: string; title: string; children: ReactNode; onCancel: () => void }) {
  return <div className="husbandry-modal-overlay" role="presentation" onMouseDown={onCancel}><section className="husbandry-modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}><header><div><span>{eyebrow}</span><h2>{title}</h2></div><button aria-label="关闭" type="button" onClick={onCancel}><X size={18} /></button></header>{children}</section></div>;
}

function HusbandryDeleteDialog({ title, description, saving, error, onCancel, onConfirm }: { title: string; description: ReactNode; saving: boolean; error: string; onCancel: () => void; onConfirm: () => void }) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !saving) onCancel();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onCancel, saving]);

  return <div className="delete-conversation-overlay" role="presentation" onMouseDown={(event: ReactMouseEvent<HTMLDivElement>) => { if (event.target === event.currentTarget && !saving) onCancel(); }}>
    <section className="delete-conversation-dialog husbandry-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="husbandry-delete-title" onMouseDown={(event) => event.stopPropagation()}>
      <h2 id="husbandry-delete-title">{title}</h2>
      <p className="delete-conversation-lead">{description}</p>
      {error && <p className="delete-conversation-error" role="alert">{error}</p>}
      <div className="delete-conversation-actions">
        <button className="delete-conversation-cancel" type="button" disabled={saving} onClick={onCancel}>取消</button>
        <button className="delete-conversation-confirm" type="button" disabled={saving} onClick={onConfirm}>{saving ? '删除中…' : '删除'}</button>
      </div>
    </section>
  </div>;
}

function DiagnosisSaveAsCaseDialog({ conversation, accessToken, onClose, onNotify }: { conversation: DiagnosisConversation; accessToken: string; onClose: () => void; onNotify: (message: string, tone?: ToastTone) => void }) {
  const [farms, setFarms] = useState<ApiFarm[]>([]);
  const [batches, setBatches] = useState<ApiSilkwormBatch[]>([]);
  const [farmId, setFarmId] = useState('');
  const [batchId, setBatchId] = useState('');
  const [title, setTitle] = useState(conversation.title);
  const [occurredOn, setOccurredOn] = useState(todayInputValue());
  const [severity, setSeverity] = useState<HusbandryCaseSeverity>('medium');
  const [status, setStatus] = useState<HusbandryCaseStatus>('suspected');
  const [symptomSummary, setSymptomSummary] = useState('');
  const [suspectedDisease, setSuspectedDisease] = useState('');
  const [diagnosisSummary, setDiagnosisSummary] = useState('');
  const [recommendation, setRecommendation] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    void Promise.all([fetchHusbandryFarms(accessToken), fetchSilkwormBatches(accessToken)])
      .then(([nextFarms, nextBatches]) => {
        setFarms(nextFarms);
        setBatches(nextBatches);
        const firstFarm = nextFarms[0];
        setFarmId(firstFarm?.id ?? '');
        setBatchId(nextBatches.find((batch) => batch.farm_id === firstFarm?.id)?.id ?? '');
      })
      .catch((error) => onNotify(error instanceof Error ? error.message : '养殖场数据加载失败', 'error'));
  }, [accessToken]);

  const matchingBatches = batches.filter((batch) => batch.farm_id === farmId);
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!accessToken || !farmId || !batchId || !title.trim() || saving) return;
    setSaving(true);
    try {
      await createHusbandryCase(accessToken, { farm_id: farmId, batch_id: batchId, source_conversation_id: conversation.id, title: title.trim(), occurred_on: occurredOn, severity, status, ...compactPayload({ symptom_summary: symptomSummary, suspected_disease: suspectedDisease, diagnosis_summary: diagnosisSummary, recommendation }) });
      onNotify('问诊已存为病例，可在养殖工作台继续随访', 'success');
      onClose();
    } catch (error) {
      onNotify(error instanceof Error ? error.message : '病例保存失败', 'error');
    } finally { setSaving(false); }
  };

  return <HusbandryModal eyebrow="问诊 → 病例" title="存为病例" onCancel={onClose}><form className="husbandry-form" onSubmit={save}><p className="diagnosis-case-dialog-note">可在此补充病例信息；保存后仍会停留在当前问诊页面。</p><div className="husbandry-form-grid"><label>养殖场<select required value={farmId} onChange={(event) => { const nextFarmId = event.target.value; setFarmId(nextFarmId); setBatchId(batches.find((batch) => batch.farm_id === nextFarmId)?.id ?? ''); }}><option value="">请选择养殖场</option>{farms.map((farm) => <option key={farm.id} value={farm.id}>{farm.name}</option>)}</select></label><label>关联批次<select required value={batchId} onChange={(event) => setBatchId(event.target.value)} disabled={!farmId}><option value="">请选择批次</option>{matchingBatches.map((batch) => <option key={batch.id} value={batch.id}>{formatBatchName(batch)}</option>)}</select></label><label>发生日期<input required type="date" value={occurredOn} onChange={(event) => setOccurredOn(event.target.value)} /></label><label>严重程度<select value={severity} onChange={(event) => setSeverity(event.target.value as HusbandryCaseSeverity)}><option value="low">轻微</option><option value="medium">一般</option><option value="high">较重</option><option value="critical">紧急</option></select></label><label>当前状态<select value={status} onChange={(event) => setStatus(event.target.value as HusbandryCaseStatus)}><option value="needs_more_info">待补充</option><option value="suspected">疑似</option><option value="processing">处理中</option><option value="closed">已关闭</option></select></label></div><label>病例标题<input autoFocus required maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>症状记录<textarea maxLength={4000} value={symptomSummary} onChange={(event) => setSymptomSummary(event.target.value)} placeholder="记录症状、数量、环境变化和已采取措施。" /></label><label>疑似疾病（可选）<input maxLength={160} value={suspectedDisease} onChange={(event) => setSuspectedDisease(event.target.value)} placeholder="如：白僵病" /></label><label>初步判断（可选）<textarea maxLength={6000} value={diagnosisSummary} onChange={(event) => setDiagnosisSummary(event.target.value)} placeholder="记录问诊或专家给出的初步判断。" /></label><label>处置建议（可选）<textarea maxLength={6000} value={recommendation} onChange={(event) => setRecommendation(event.target.value)} placeholder="记录隔离、消毒、通风或送检等后续安排。" /></label><footer className="husbandry-form-actions"><button type="button" disabled={saving} onClick={onClose}>取消</button><button className="husbandry-primary-action" type="submit" disabled={saving || !farmId || !batchId || !title.trim()}>{saving ? '正在保存' : '保存病例'}</button></footer></form></HusbandryModal>;
}

function formatBatchName(batch: ApiSilkwormBatch) {
  return batch.batch_code || [batch.variety, batch.instar].filter(Boolean).join(' · ') || '未命名批次';
}

function formatCaseStatus(status: HusbandryCaseStatus) {
  return { needs_more_info: '待补充', suspected: '疑似', processing: '处理中', closed: '已关闭' }[status];
}

function formatCaseSeverity(severity: HusbandryCaseSeverity) {
  return { low: '轻微', medium: '一般', high: '较重', critical: '紧急' }[severity];
}

function formatBatchLifecycle(status: ApiSilkwormBatch['status']) {
  return { active: '在养中', finished: '已完成', archived: '已归档' }[status];
}

function formatDateLabel(value: string) {
  const parsed = new Date(`${value}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric' }).format(parsed);
}

function todayInputValue() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

function optionalNumber(value: string | undefined) {
  if (!value?.trim()) return undefined;
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function compactPayload<T extends Record<string, unknown>>(payload: T): Partial<T> {
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== undefined && value !== null && value !== '')) as Partial<T>;
}

function SettingsThread({
  archivedConversations,
  archiveError,
  archivedProjects,
  archivedProjectsError,
  archivedProjectsLoading,
  archiveSavingConversationId,
  archiveSavingProjectId,
  archivesLoading,
  configuredModels,
  deviceSessions,
  deviceSessionsLoading,
  fontSize,
  isModelConfigSaving,
  modelConfigError,
  modelConfigsLoading,
  projects,
  selectedModelConfigId,
  testingModelConfigId,
  theme,
  userPreferences,
  userSettingsError,
  userSettingsLoading,
  onAccountDelete,
  onConversationDelete,
  onConversationRestore,
  onFontSizeChange,
  onArchiveBulkDelete,
  onProjectDelete,
  onProjectRestore,
  onModelDelete,
  onModelSave,
  onModelSelect,
  onModelSetDefault,
  onModelTest,
  onDeviceSessionRevoke,
  onOtherDeviceSessionsRevoke,
  onThemeChange,
  onUserDataExport,
  onUserSettingsChange,
}: {
  archivedConversations: DiagnosisConversation[];
  archiveError: string;
  archivedProjects: CreatedProject[];
  archivedProjectsError: string;
  archivedProjectsLoading: boolean;
  archiveSavingConversationId: string | null;
  archiveSavingProjectId: string | null;
  archivesLoading: boolean;
  configuredModels: ConfiguredModel[];
  deviceSessions: ApiUserDeviceSession[];
  deviceSessionsLoading: boolean;
  fontSize: UiFontSize;
  isModelConfigSaving: boolean;
  modelConfigError: string;
  modelConfigsLoading: boolean;
  projects: CreatedProject[];
  selectedModelConfigId: string | null;
  testingModelConfigId: string | null;
  theme: UiTheme;
  userPreferences: UserPreferences;
  userSettingsError: string;
  userSettingsLoading: boolean;
  onAccountDelete: (confirmation: string) => Promise<void>;
  onConversationDelete: (conversation: DiagnosisConversation) => void;
  onConversationRestore: (conversationId: string) => Promise<void> | void;
  onFontSizeChange: (fontSize: UiFontSize) => void;
  onArchiveBulkDelete: (payload: ArchiveBulkDeletePayload) => Promise<void> | void;
  onProjectDelete: (project: CreatedProject) => void;
  onProjectRestore: (projectId: string) => Promise<void> | void;
  onModelDelete: (modelConfigId: string) => Promise<void>;
  onModelSave: (draft: ModelConfigDraft, editingModelId: string | null) => Promise<ConfiguredModel>;
  onModelSelect: (modelConfigId: string | null) => void;
  onModelSetDefault: (modelConfigId: string) => Promise<void>;
  onModelTest: (modelConfigId: string) => Promise<ApiModelConfigTestResponse>;
  onDeviceSessionRevoke: (sessionId: string) => Promise<void>;
  onOtherDeviceSessionsRevoke: () => Promise<void>;
  onThemeChange: (theme: UiTheme) => void;
  onUserDataExport: () => Promise<void>;
  onUserSettingsChange: (patch: Partial<UserPreferences>) => Promise<UserPreferences>;
}) {
  const darkModeEnabled = theme === 'dark';
  const [modelFormOpen, setModelFormOpen] = useState(false);
  const [editingModelId, setEditingModelId] = useState<string | null>(null);
  const [modelDraft, setModelDraft] = useState<ModelConfigDraft>(emptyModelDraft);
  const [formError, setFormError] = useState('');
  const [preferenceSavingKey, setPreferenceSavingKey] = useState<keyof UserPreferences | null>(null);
  const [preferenceError, setPreferenceError] = useState('');
  const [exportingData, setExportingData] = useState(false);
  const [revokeSavingId, setRevokeSavingId] = useState<string | null>(null);
  const [deleteAccountOpen, setDeleteAccountOpen] = useState(false);
  const [deleteAccountConfirmation, setDeleteAccountConfirmation] = useState('');
  const [deletingAccount, setDeletingAccount] = useState(false);
  const handleCreateModel = () => {
    setEditingModelId(null);
    setModelDraft(emptyModelDraft);
    setFormError('');
    setModelFormOpen(true);
  };

  const handleEditModel = (model: ConfiguredModel) => {
    setEditingModelId(model.id);
    setModelDraft({
      providerName: model.providerName,
      modelId: model.modelId,
      apiKey: '',
      apiRequestUrl: model.apiRequestUrl,
    });
    setFormError('');
    setModelFormOpen(true);
  };

  const handleModelDraftChange = (field: keyof ModelConfigDraft, value: string) => {
    setModelDraft((currentDraft) => ({
      ...currentDraft,
      [field]: value,
    }));
  };

  const handleModelSave = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const normalizedDraft = {
      providerName: modelDraft.providerName.trim() || '未命名供应商',
      modelId: modelDraft.modelId.trim(),
      apiKey: modelDraft.apiKey.trim(),
      apiRequestUrl: modelDraft.apiRequestUrl.trim(),
    };

    if (!normalizedDraft.modelId || !normalizedDraft.apiRequestUrl) {
      setFormError('请填写模型 ID 和 API 请求地址');
      return;
    }
    if (!editingModelId && !normalizedDraft.apiKey) {
      setFormError('新增模型配置需要填写 API Key');
      return;
    }

    setFormError('');
    try {
      await onModelSave(normalizedDraft, editingModelId);
      setModelFormOpen(false);
      setEditingModelId(null);
      setModelDraft(emptyModelDraft);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : '模型配置保存失败');
    }
  };

  const updatePreference = async <K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) => {
    if (preferenceSavingKey) return;
    setPreferenceSavingKey(key);
    setPreferenceError('');
    try {
      await onUserSettingsChange({ [key]: value } as Partial<UserPreferences>);
    } catch (error) {
      setPreferenceError(error instanceof Error ? error.message : '设置保存失败');
    } finally {
      setPreferenceSavingKey(null);
    }
  };

  const exportData = async () => {
    setExportingData(true);
    setPreferenceError('');
    try {
      await onUserDataExport();
    } catch (error) {
      setPreferenceError(error instanceof Error ? error.message : '数据导出失败');
    } finally {
      setExportingData(false);
    }
  };

  const revokeSession = async (sessionId: string) => {
    setRevokeSavingId(sessionId);
    setPreferenceError('');
    try {
      await onDeviceSessionRevoke(sessionId);
    } catch (error) {
      setPreferenceError(error instanceof Error ? error.message : '设备退出失败');
    } finally {
      setRevokeSavingId(null);
    }
  };

  const revokeOtherSessions = async () => {
    setRevokeSavingId('others');
    setPreferenceError('');
    try {
      await onOtherDeviceSessionsRevoke();
    } catch (error) {
      setPreferenceError(error instanceof Error ? error.message : '设备退出失败');
    } finally {
      setRevokeSavingId(null);
    }
  };

  const confirmAccountDelete = async () => {
    if (deleteAccountConfirmation.trim().toUpperCase() !== 'DELETE' || deletingAccount) return;
    setDeletingAccount(true);
    setPreferenceError('');
    try {
      await onAccountDelete(deleteAccountConfirmation);
      setDeleteAccountOpen(false);
    } catch (error) {
      setPreferenceError(error instanceof Error ? error.message : '账户删除失败');
    } finally {
      setDeletingAccount(false);
    }
  };

  return (
    <article className="conversation-card settings-card">
      <SettingPanel title="模型配置" note="供应商、模型、连通性">
        <div className="model-config-toolbar">
          <div>
            <strong>已配置模型</strong>
            <span>{modelConfigsLoading ? '同步中...' : `${configuredModels.length} 个配置`}</span>
          </div>
          <button type="button" aria-label="新增模型配置" disabled={isModelConfigSaving} onClick={handleCreateModel}>
            <Plus size={17} />
          </button>
        </div>
        {modelConfigError && (
          <p className="model-config-message error" role="alert">
            {modelConfigError}
          </p>
        )}
        {modelFormOpen && (
          <form className="model-config-form" onSubmit={handleModelSave}>
            <label>
              <span>供应商名称</span>
              <input
                disabled={isModelConfigSaving}
                value={modelDraft.providerName}
                onChange={(event) => handleModelDraftChange('providerName', event.target.value)}
                placeholder="例如 OpenAI"
              />
            </label>
            <label>
              <span>模型 ID</span>
              <input
                disabled={isModelConfigSaving}
                value={modelDraft.modelId}
                onChange={(event) => handleModelDraftChange('modelId', event.target.value)}
                placeholder="例如 gpt-4o"
              />
            </label>
            <label>
              <span>API Key</span>
              <input
                autoComplete="off"
                disabled={isModelConfigSaving}
                type="password"
                value={modelDraft.apiKey}
                onChange={(event) => handleModelDraftChange('apiKey', event.target.value)}
                placeholder={editingModelId ? '留空则保持原 API Key' : '请输入 API Key'}
              />
            </label>
            <label>
              <span>API 请求地址</span>
              <input
                disabled={isModelConfigSaving}
                value={modelDraft.apiRequestUrl}
                onChange={(event) => handleModelDraftChange('apiRequestUrl', event.target.value)}
                placeholder="https://api.example.com/v1"
              />
            </label>
            {formError && (
              <p className="model-config-message error" role="alert">
                {formError}
              </p>
            )}
            <div className="model-config-form-actions">
              <button type="button" disabled={isModelConfigSaving} onClick={() => setModelFormOpen(false)}>
                取消
              </button>
              <button type="submit" disabled={isModelConfigSaving}>
                {isModelConfigSaving ? '保存中...' : editingModelId ? '保存' : '添加'}
              </button>
            </div>
          </form>
        )}
        <div className="model-config-list">
          {configuredModels.length === 0 && !modelConfigsLoading && (
            <div className="model-config-empty">还没有模型配置，点击右上角加号添加一个。</div>
          )}
          {configuredModels.map((model) => (
            <ModelConfigCard
              key={model.id}
              model={model}
              current={selectedModelConfigId === model.id}
              testing={testingModelConfigId === model.id}
              onDelete={() => void onModelDelete(model.id)}
              onEdit={() => handleEditModel(model)}
              onSelect={() => onModelSelect(model.id)}
              onSetDefault={() => void onModelSetDefault(model.id)}
              onTest={() => void onModelTest(model.id)}
            />
          ))}
        </div>
      </SettingPanel>

      {(preferenceError || userSettingsError) && <p className="settings-feedback error" role="alert">{preferenceError || userSettingsError}</p>}

      <SettingPanel title="知识源设置" note="KG、RAG、数据版本">
        <div className="source-list">
          <ToggleLine
            label="启用知识图谱 KG"
            enabled={userPreferences.knowledge_graph_enabled}
            disabled={Boolean(preferenceSavingKey)}
            onToggle={() => void updatePreference('knowledge_graph_enabled', !userPreferences.knowledge_graph_enabled)}
          />
          <ToggleLine
            label="启用 RAG 文档检索"
            enabled={userPreferences.rag_enabled}
            disabled={Boolean(preferenceSavingKey)}
            onToggle={() => void updatePreference('rag_enabled', !userPreferences.rag_enabled)}
          />
          <SettingRow label="数据版本" value="silkworm-kb-2026.07" />
        </div>
      </SettingPanel>

      <SettingPanel title="记忆控制" note="长期记忆、写入授权、清除记忆">
        <ToggleLine
          label="开启长期记忆"
          enabled={userPreferences.long_term_memory_enabled}
          disabled={Boolean(preferenceSavingKey)}
          onToggle={() => void updatePreference('long_term_memory_enabled', !userPreferences.long_term_memory_enabled)}
        />
        <ToggleLine
          label="允许 Memory Agent 写入"
          enabled={userPreferences.memory_agent_write_enabled}
          disabled={Boolean(preferenceSavingKey) || !userPreferences.long_term_memory_enabled}
          onToggle={() => void updatePreference('memory_agent_write_enabled', !userPreferences.memory_agent_write_enabled)}
        />
        <SettingRow label="已写入的长期记忆" value="当前没有可清除内容" />
      </SettingPanel>

      <SettingPanel title="通知" note="站内提醒、上传、模型状态">
        <ToggleLine
          label="站内通知"
          enabled={userPreferences.in_app_notifications}
          disabled={Boolean(preferenceSavingKey)}
          onToggle={() => void updatePreference('in_app_notifications', !userPreferences.in_app_notifications)}
        />
        <ToggleLine
          label="附件上传完成提醒"
          enabled={userPreferences.upload_notifications}
          disabled={Boolean(preferenceSavingKey)}
          onToggle={() => void updatePreference('upload_notifications', !userPreferences.upload_notifications)}
        />
        <ToggleLine
          label="模型连通性与异常提醒"
          enabled={userPreferences.model_notifications}
          disabled={Boolean(preferenceSavingKey)}
          onToggle={() => void updatePreference('model_notifications', !userPreferences.model_notifications)}
        />
      </SettingPanel>

      <SettingPanel title="养殖提醒" note="用于养殖工作台的现场预警">
        <ToggleLine
          label="开启养殖健康提醒"
          enabled={userPreferences.husbandry_health_notifications}
          disabled={Boolean(preferenceSavingKey)}
          onToggle={() => void updatePreference('husbandry_health_notifications', !userPreferences.husbandry_health_notifications)}
        />
        <SettingsSelectRow
          label="温度下限"
          value={String(userPreferences.husbandry_temperature_min)}
          disabled={Boolean(preferenceSavingKey)}
          options={[18, 20, 22].map((value) => ({ value: String(value), label: `${value} ℃` }))}
          onChange={(value) => void updatePreference('husbandry_temperature_min', Number(value))}
        />
        <SettingsSelectRow
          label="温度上限"
          value={String(userPreferences.husbandry_temperature_max)}
          disabled={Boolean(preferenceSavingKey)}
          options={[28, 30, 32, 35].map((value) => ({ value: String(value), label: `${value} ℃` }))}
          onChange={(value) => void updatePreference('husbandry_temperature_max', Number(value))}
        />
        <SettingsSelectRow
          label="湿度提醒阈值"
          value={String(userPreferences.husbandry_humidity_max)}
          disabled={Boolean(preferenceSavingKey)}
          options={[80, 85, 90].map((value) => ({ value: String(value), label: `${value} %` }))}
          onChange={(value) => void updatePreference('husbandry_humidity_max', Number(value))}
        />
      </SettingPanel>

      <SettingPanel title="对话偏好" note="发送方式、标题与状态提示">
        <ToggleLine
          label="自动生成对话标题"
          enabled={userPreferences.auto_generate_title}
          disabled={Boolean(preferenceSavingKey)}
          onToggle={() => void updatePreference('auto_generate_title', !userPreferences.auto_generate_title)}
        />
        <SettingsSelectRow
          label="发送快捷键"
          value={userPreferences.send_shortcut}
          disabled={Boolean(preferenceSavingKey)}
          options={[{ value: 'enter', label: 'Enter 发送' }, { value: 'ctrl_enter', label: 'Ctrl / Cmd + Enter 发送' }]}
          onChange={(value) => void updatePreference('send_shortcut', value as UserPreferences['send_shortcut'])}
        />
        <ToggleLine
          label="显示模型问诊状态"
          enabled={userPreferences.show_model_status}
          disabled={Boolean(preferenceSavingKey)}
          onToggle={() => void updatePreference('show_model_status', !userPreferences.show_model_status)}
        />
      </SettingPanel>

      <SettingPanel title="附件与存储" note="图片压缩、上传重试、草稿保留">
        <SettingsSelectRow
          label="图片上传质量"
          value={userPreferences.image_compression}
          disabled={Boolean(preferenceSavingKey)}
          options={[{ value: 'balanced', label: '平衡（推荐）' }, { value: 'high_quality', label: '高质量' }]}
          onChange={(value) => void updatePreference('image_compression', value as UserPreferences['image_compression'])}
        />
        <ToggleLine
          label="上传失败后自动重试一次"
          enabled={userPreferences.auto_retry_upload}
          disabled={Boolean(preferenceSavingKey)}
          onToggle={() => void updatePreference('auto_retry_upload', !userPreferences.auto_retry_upload)}
        />
        <SettingsSelectRow
          label="未发送附件保留"
          value={String(userPreferences.draft_attachment_retention_hours)}
          disabled={Boolean(preferenceSavingKey)}
          options={[{ value: '24', label: '24 小时' }, { value: '72', label: '3 天' }, { value: '168', label: '7 天' }]}
          onChange={(value) => void updatePreference('draft_attachment_retention_hours', Number(value) as UserPreferences['draft_attachment_retention_hours'])}
        />
      </SettingPanel>

      <SettingPanel title="已归档" note="项目、对话、恢复、删除">
        <ArchiveCenterPanel
          conversations={archivedConversations}
          conversationError={archiveError}
          conversationsLoading={archivesLoading}
          archivedProjects={archivedProjects}
          projectError={archivedProjectsError}
          projectsLoading={archivedProjectsLoading}
          projects={projects}
          savingConversationId={archiveSavingConversationId}
          savingProjectId={archiveSavingProjectId}
          onBulkDelete={onArchiveBulkDelete}
          onConversationDelete={onConversationDelete}
          onConversationRestore={onConversationRestore}
          onProjectDelete={onProjectDelete}
          onProjectRestore={onProjectRestore}
        />
      </SettingPanel>

      <SettingPanel title="隐私与安全" note="数据删除、导出、审计">
        <div className="setting-action-row">
          <div><span>导出用户数据</span><small>下载账户资料、项目、对话与消息</small></div>
          <button type="button" disabled={exportingData} onClick={() => void exportData()}>{exportingData ? '正在导出' : '导出 JSON'}</button>
        </div>
        <SettingRow label="记录审计" value="已开启" />
        <div className="device-sessions-header">
          <div><span>已登录设备</span><small>{deviceSessionsLoading ? '正在读取设备…' : `${deviceSessions.length} 台设备`}</small></div>
          {deviceSessions.some((session) => !session.is_current) && <button type="button" disabled={revokeSavingId === 'others'} onClick={() => void revokeOtherSessions()}>{revokeSavingId === 'others' ? '正在退出' : '退出其他设备'}</button>}
        </div>
        <div className="device-session-list">
          {deviceSessions.map((session) => (
            <div className="device-session-row" key={session.id}>
              <div><strong>{session.device_name}</strong><small>{session.is_current ? '当前设备' : `最近使用 ${formatSettingsDateTime(session.last_used_at ?? session.created_at)}`}</small></div>
              {!session.is_current && <button type="button" disabled={revokeSavingId === session.id} onClick={() => void revokeSession(session.id)}>{revokeSavingId === session.id ? '正在退出' : '退出'}</button>}
            </div>
          ))}
          {!deviceSessionsLoading && deviceSessions.length === 0 && <p className="settings-empty-note">暂无可用设备会话</p>}
        </div>
        <div className="danger-row">
          <span>删除账号数据</span>
          <button type="button" onClick={() => { setDeleteAccountConfirmation(''); setDeleteAccountOpen(true); }}>删除</button>
        </div>
      </SettingPanel>

      <SettingPanel title="辅助功能" note="动效与对比度">
        <ToggleLine
          label="减少界面动效"
          enabled={userPreferences.reduced_motion}
          disabled={Boolean(preferenceSavingKey)}
          onToggle={() => void updatePreference('reduced_motion', !userPreferences.reduced_motion)}
        />
        <ToggleLine
          label="提高文字与控件对比度"
          enabled={userPreferences.high_contrast}
          disabled={Boolean(preferenceSavingKey)}
          onToggle={() => void updatePreference('high_contrast', !userPreferences.high_contrast)}
        />
      </SettingPanel>

      <SettingPanel title="UI 设置" note="深色模式、字体">
        <ToggleLine
          label="深色模式"
          enabled={darkModeEnabled}
          onToggle={() => onThemeChange(darkModeEnabled ? 'light' : 'dark')}
        />
        <FontSizeSelector value={fontSize} onChange={onFontSizeChange} />
      </SettingPanel>
      {userSettingsLoading && <p className="settings-sync-note">正在同步你的设置…</p>}
      {deleteAccountOpen && (
        <div className="settings-confirm-overlay" role="presentation" onMouseDown={() => !deletingAccount && setDeleteAccountOpen(false)}>
          <section className="settings-confirm-dialog" role="dialog" aria-modal="true" aria-label="删除账户" onMouseDown={(event) => event.stopPropagation()}>
            <header><div><span>不可撤销</span><h2>删除账户与数据</h2></div><button type="button" aria-label="关闭" disabled={deletingAccount} onClick={() => setDeleteAccountOpen(false)}><X size={18} /></button></header>
            <p>此操作会删除账户、项目、对话与上传记录，并立即退出所有设备。请输入 <strong>DELETE</strong> 确认。</p>
            <input autoFocus value={deleteAccountConfirmation} disabled={deletingAccount} onChange={(event) => setDeleteAccountConfirmation(event.target.value)} placeholder="DELETE" />
            <footer><button type="button" disabled={deletingAccount} onClick={() => setDeleteAccountOpen(false)}>取消</button><button className="danger" type="button" disabled={deleteAccountConfirmation.trim().toUpperCase() !== 'DELETE' || deletingAccount} onClick={() => void confirmAccountDelete()}>{deletingAccount ? '正在删除' : '删除账户'}</button></footer>
          </section>
        </div>
      )}
    </article>
  );
}

type ArchiveSortMode = 'updated' | 'name';

type ArchiveDropdownOption = {
  icon?: LucideIcon;
  label: string;
  value: string;
};

type ArchiveDropdownSection = {
  label?: string;
  options: ArchiveDropdownOption[];
};

type ArchiveGroup = {
  conversations: DiagnosisConversation[];
  id: string;
  name: string;
  project: CreatedProject | null;
};

function ArchiveCenterPanel({
  archivedProjects,
  conversationError,
  conversations,
  conversationsLoading,
  projectError,
  projects,
  projectsLoading,
  savingConversationId,
  savingProjectId,
  onBulkDelete,
  onConversationDelete,
  onConversationRestore,
  onProjectDelete,
  onProjectRestore,
}: {
  archivedProjects: CreatedProject[];
  conversationError: string;
  conversations: DiagnosisConversation[];
  conversationsLoading: boolean;
  projectError: string;
  projects: CreatedProject[];
  projectsLoading: boolean;
  savingConversationId: string | null;
  savingProjectId: string | null;
  onBulkDelete: (payload: ArchiveBulkDeletePayload) => Promise<void> | void;
  onConversationDelete: (conversation: DiagnosisConversation) => void;
  onConversationRestore: (conversationId: string) => Promise<void> | void;
  onProjectDelete: (project: CreatedProject) => void;
  onProjectRestore: (projectId: string) => Promise<void> | void;
}) {
  const [query, setQuery] = useState('');
  const [projectFilter, setProjectFilter] = useState('all');
  const [sortMode, setSortMode] = useState<ArchiveSortMode>('updated');
  const [bulkConfirmOpen, setBulkConfirmOpen] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const loading = conversationsLoading || projectsLoading;
  const normalizedQuery = query.trim().toLowerCase();

  const projectById = useMemo(() => {
    const nextProjectById = new Map<string, CreatedProject>();
    [...projects, ...archivedProjects].forEach((project) => {
      nextProjectById.set(project.id, project);
    });
    return nextProjectById;
  }, [archivedProjects, projects]);

  const archivedProjectIds = useMemo(() => new Set(archivedProjects.map((project) => project.id)), [archivedProjects]);
  const hasUnfiledConversations = conversations.some((conversation) => !conversation.projectId);

  const projectOptions = useMemo(() => {
    const optionIds = new Set<string>();
    archivedProjects.forEach((project) => optionIds.add(project.id));
    conversations.forEach((conversation) => {
      if (conversation.projectId) optionIds.add(conversation.projectId);
    });

    return Array.from(optionIds)
      .map((projectId) => ({
        id: projectId,
        name: projectById.get(projectId)?.name ?? '未命名项目',
      }))
      .sort((left, right) => left.name.localeCompare(right.name, 'zh-CN'));
  }, [archivedProjects, conversations, projectById]);

  const conversationMatchesQuery = (conversation: DiagnosisConversation) => {
    if (!normalizedQuery) return true;
    const projectName = conversation.projectId ? projectById.get(conversation.projectId)?.name ?? '' : '';
    return (
      conversation.title.toLowerCase().includes(normalizedQuery) ||
      conversation.summary.toLowerCase().includes(normalizedQuery) ||
      projectName.toLowerCase().includes(normalizedQuery)
    );
  };

  const projectMatchesQuery = (project: CreatedProject | null) => {
    if (!normalizedQuery) return true;
    if (!project) return '聊天'.includes(normalizedQuery);
    return project.name.toLowerCase().includes(normalizedQuery) || project.description.toLowerCase().includes(normalizedQuery);
  };

  const archiveGroups = useMemo(() => {
    const groups = new Map<string, ArchiveGroup>();

    archivedProjects.forEach((project) => {
      if (projectFilter !== 'all' && projectFilter !== project.id) return;
      if (!projectMatchesQuery(project)) return;

      groups.set(project.id, {
        conversations: [],
        id: project.id,
        name: project.name,
        project,
      });
    });

    conversations.forEach((conversation) => {
      const groupId = conversation.projectId ?? 'none';
      if (projectFilter !== 'all' && (projectFilter === 'none' ? conversation.projectId : conversation.projectId !== projectFilter)) {
        return;
      }
      if (!conversationMatchesQuery(conversation)) return;

      const project = conversation.projectId ? projectById.get(conversation.projectId) ?? null : null;
      const currentGroup =
        groups.get(groupId) ??
        ({
          conversations: [],
          id: groupId,
          name: project?.name ?? '聊天',
          project,
        } satisfies ArchiveGroup);
      currentGroup.conversations.push(conversation);
      groups.set(groupId, currentGroup);
    });

    const nextGroups = Array.from(groups.values())
      .map((group) => ({
        ...group,
        conversations: [...group.conversations].sort((left, right) => {
          if (sortMode === 'name') return left.title.localeCompare(right.title, 'zh-CN');
          return new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime();
        }),
      }))
      .filter((group) => {
        return Boolean(group.project && archivedProjectIds.has(group.project.id)) || group.conversations.length > 0;
      });

    return nextGroups.sort((left, right) => {
      if (sortMode === 'name') return left.name.localeCompare(right.name, 'zh-CN');
      const leftTime = Math.max(0, ...left.conversations.map((conversation) => new Date(conversation.updatedAt).getTime()));
      const rightTime = Math.max(0, ...right.conversations.map((conversation) => new Date(conversation.updatedAt).getTime()));
      return rightTime - leftTime;
    });
  }, [
    archivedProjectIds,
    archivedProjects,
    conversations,
    normalizedQuery,
    projectById,
    projectFilter,
    sortMode,
  ]);

  const visibleConversationIds = useMemo(
    () => Array.from(new Set(archiveGroups.flatMap((group) => group.conversations.map((conversation) => conversation.id)))),
    [archiveGroups],
  );
  const visibleProjectIds = useMemo(
    () =>
      Array.from(
        new Set(
          archiveGroups.flatMap((group) => (group.project && archivedProjectIds.has(group.project.id) ? [group.project.id] : [])),
        ),
      ),
    [archiveGroups, archivedProjectIds],
  );
  const visibleDeleteCount = visibleConversationIds.length + visibleProjectIds.length;
  const totalArchiveCount = conversations.length + archivedProjects.length;
  const filtered = visibleDeleteCount !== totalArchiveCount;

  const sortSections: ArchiveDropdownSection[] = [
    {
      options: [
        { icon: History, label: '更新时间', value: 'sort:updated' },
        { icon: ArrowDownUp, label: '名称顺序', value: 'sort:name' },
      ],
    },
  ];
  const projectSections: ArchiveDropdownSection[] = [
    {
      options: [
        { icon: Folder, label: '所有项目', value: 'all' },
        ...projectOptions.map((project) => ({
          icon: Folder,
          label: project.name,
          value: project.id,
        })),
        ...(hasUnfiledConversations ? [{ icon: MessageCircle, label: '聊天', value: 'none' }] : []),
      ],
    },
  ];

  const handleSortSelect = (value: string) => {
    if (value === 'sort:updated' || value === 'sort:name') {
      setSortMode(value === 'sort:updated' ? 'updated' : 'name');
    }
  };

  const handleBulkDelete = async () => {
    if (bulkDeleting || visibleDeleteCount === 0) return;

    setBulkDeleting(true);
    try {
      await onBulkDelete({ conversationIds: visibleConversationIds, projectIds: visibleProjectIds });
      setBulkConfirmOpen(false);
    } finally {
      setBulkDeleting(false);
    }
  };

  return (
    <div className="archive-panel archive-center-panel">
      <div className="archive-center-head">
        <div>
          <strong>已归档对话</strong>
          <span>
            {archivedProjects.length} 个项目 · {conversations.length} 个对话
          </span>
        </div>
        <button
          className="archive-danger-button"
          type="button"
          disabled={loading || bulkDeleting || visibleDeleteCount === 0}
          onClick={() => setBulkConfirmOpen(true)}
        >
          <Trash2 size={15} />
          <span>全部删除</span>
        </button>
      </div>

      <div className="archive-panel-toolbar archive-center-toolbar">
        <label className="archive-search">
          <Search size={15} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索已归档聊天" />
        </label>
        <ArchiveDropdown
          ariaLabel="排列方式"
          icon={ArrowDownUp}
          label="排列方式"
          sections={sortSections}
          value={`sort:${sortMode}`}
          onSelect={handleSortSelect}
        />
        <ArchiveDropdown
          ariaLabel="按项目筛选"
          icon={Folder}
          label={projectFilter === 'all' ? '所有项目' : projectFilter === 'none' ? '聊天' : projectById.get(projectFilter)?.name ?? '未命名项目'}
          sections={projectSections}
          value={projectFilter}
          onSelect={setProjectFilter}
        />
      </div>

      <div className="archive-panel-meta">
        <span>{filtered ? `当前筛选 ${visibleDeleteCount} 项` : `${totalArchiveCount} 项归档内容`}</span>
        <small>{sortMode === 'updated' ? '按更新时间排序' : '按名称排序'}</small>
      </div>

      {bulkConfirmOpen && (
        <div className="archive-bulk-confirm" role="alertdialog" aria-label="确认删除归档内容">
          <span>删除当前筛选范围内的 {visibleDeleteCount} 项归档内容？此操作不可恢复。</span>
          <div>
            <button type="button" disabled={bulkDeleting} onClick={() => setBulkConfirmOpen(false)}>
              取消
            </button>
            <button className="danger" type="button" disabled={bulkDeleting} onClick={() => void handleBulkDelete()}>
              {bulkDeleting ? '删除中' : '确认删除'}
            </button>
          </div>
        </div>
      )}

      {(conversationError || projectError) && (
        <p className="archive-panel-message error" role="alert">
          {[conversationError, projectError].filter(Boolean).join('；')}
        </p>
      )}

      <div className="archive-list" aria-live="polite">
        {loading ? (
          <div className="archive-empty">正在载入归档内容...</div>
        ) : archiveGroups.length === 0 ? (
          <div className="archive-empty">{query || projectFilter !== 'all' ? '没有匹配的归档内容' : '暂无归档内容'}</div>
        ) : (
          archiveGroups.map((group) => {
            const project = group.project;
            const archivedProject = Boolean(project && archivedProjectIds.has(project.id));
            const projectSaving = project ? savingProjectId === project.id : false;
            const GroupIcon = project ? Folder : MessageCircle;

            return (
              <section className="archive-group" key={group.id}>
                <div className="archive-group-header">
                  <span>
                    <GroupIcon size={14} />
                    {group.name}
                  </span>
                  <div className="archive-group-meta">
                    <small>{group.conversations.length > 0 ? `${group.conversations.length} 个聊天` : '暂无对话'}</small>
                    {archivedProject && project && (
                      <ArchiveItemActions
                        disabled={projectSaving}
                        label={`管理 ${project.name}`}
                        actions={[
                          {
                            icon: RotateCcw,
                            label: projectSaving ? '恢复中' : '恢复项目',
                            onClick: () => void onProjectRestore(project.id),
                          },
                          {
                            danger: true,
                            icon: Trash2,
                            label: '删除项目',
                            onClick: () => onProjectDelete(project),
                          },
                        ]}
                      />
                    )}
                  </div>
                </div>
                {group.conversations.length === 0 ? (
                  <div className="archive-project-empty">暂无对话</div>
                ) : (
                  group.conversations.map((conversation) => {
                    const saving = savingConversationId === conversation.id;

                    return (
                      <article className="archive-row" key={conversation.id}>
                        <div className="archive-row-main">
                          <strong>{conversation.title}</strong>
                          {conversation.summary && <span>{conversation.summary}</span>}
                          <time dateTime={conversation.updatedAt}>{formatArchiveDateTime(conversation.updatedAt)}</time>
                        </div>
                        <ArchiveItemActions
                          disabled={saving}
                          label={`管理 ${conversation.title}`}
                          actions={[
                            {
                              icon: RotateCcw,
                              label: saving ? '恢复中' : '恢复',
                              onClick: () => void onConversationRestore(conversation.id),
                            },
                            {
                              danger: true,
                              icon: Trash2,
                              label: '删除',
                              onClick: () => onConversationDelete(conversation),
                            },
                          ]}
                        />
                      </article>
                    );
                  })
                )}
              </section>
            );
          })
        )}
      </div>
    </div>
  );
}

function ArchiveDropdown({
  ariaLabel,
  extraSelectedValue,
  icon: Icon,
  label,
  sections,
  value,
  onSelect,
}: {
  ariaLabel: string;
  extraSelectedValue?: string;
  icon: LucideIcon;
  label: string;
  sections: ArchiveDropdownSection[];
  value: string;
  onSelect: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;

    const closeDropdown = (event: PointerEvent) => {
      if (!dropdownRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('pointerdown', closeDropdown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', closeDropdown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  return (
    <div className={clsx('archive-filter', open && 'open')} ref={dropdownRef}>
      <button type="button" aria-label={ariaLabel} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
        <Icon size={15} />
        <span>{label}</span>
        <ChevronDown size={14} />
      </button>
      {open && (
        <div className="archive-filter-menu" role="menu">
          {sections.map((section, sectionIndex) => (
            <div className="archive-filter-section" key={section.label ?? sectionIndex}>
              {section.label && <small>{section.label}</small>}
              {section.options.map((option) => {
                const OptionIcon = option.icon;
                const selected = option.value === value || option.value === extraSelectedValue;

                return (
                  <button
                    type="button"
                    role="menuitemradio"
                    aria-checked={selected}
                    className={clsx(selected && 'selected')}
                    key={option.value}
                    onClick={() => {
                      onSelect(option.value);
                      setOpen(false);
                    }}
                  >
                    {OptionIcon && <OptionIcon size={15} />}
                    <span>{option.label}</span>
                    {selected && <Check size={15} />}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ArchiveItemActions({
  actions,
  disabled,
  label,
}: {
  actions: Array<{
    danger?: boolean;
    icon: LucideIcon;
    label: string;
    onClick: () => void;
  }>;
  disabled?: boolean;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({ left: -9999, top: -9999 });
  const menuRef = useRef<HTMLDivElement>(null);
  const menuPanelRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const updateMenuPosition = () => {
    const trigger = triggerRef.current;
    if (!trigger) return;

    const triggerRect = trigger.getBoundingClientRect();
    const menuRect = menuPanelRef.current?.getBoundingClientRect();
    const menuWidth = menuRect?.width || 136;
    const viewportPadding = 10;
    const gap = 6;
    const left = Math.min(
      Math.max(viewportPadding, triggerRect.right - menuWidth),
      Math.max(viewportPadding, window.innerWidth - menuWidth - viewportPadding),
    );

    setMenuStyle({
      left,
      top: triggerRect.bottom + gap,
    });
  };

  useEffect(() => {
    if (!open) return undefined;

    const frameId = window.requestAnimationFrame(updateMenuPosition);
    const closeMenu = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !menuPanelRef.current?.contains(target)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('pointerdown', closeMenu);
    document.addEventListener('keydown', handleKeyDown);
    window.addEventListener('resize', updateMenuPosition);
    window.addEventListener('scroll', updateMenuPosition, true);
    return () => {
      window.cancelAnimationFrame(frameId);
      document.removeEventListener('pointerdown', closeMenu);
      document.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('resize', updateMenuPosition);
      window.removeEventListener('scroll', updateMenuPosition, true);
    };
  }, [open]);

  const actionMenu = (
    <div className="archive-action-menu" role="menu" ref={menuPanelRef} style={menuStyle}>
      {actions.map((action) => {
        const ActionIcon = action.icon;

        return (
          <button
            className={clsx(action.danger && 'danger')}
            key={action.label}
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              action.onClick();
            }}
          >
            <ActionIcon size={15} />
            <span>{action.label}</span>
          </button>
        );
      })}
    </div>
  );

  return (
    <div className={clsx('archive-action-wrap', open && 'open')} ref={menuRef}>
      <button
        className="archive-action-trigger"
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        ref={triggerRef}
        onClick={() => setOpen((current) => !current)}
      >
        <MoreHorizontal size={17} />
      </button>
      {open && createPortal(actionMenu, document.body)}
    </div>
  );
}

function ModelConfigCard({
  current,
  model,
  onDelete,
  onEdit,
  onSelect,
  onSetDefault,
  onTest,
  testing,
}: {
  current: boolean;
  model: ConfiguredModel;
  onDelete: () => void;
  onEdit: () => void;
  onSelect: () => void;
  onSetDefault: () => void;
  onTest: () => void;
  testing: boolean;
}) {
  const modelName = model.modelId || model.providerName;
  const modelInitial = Array.from(modelName.trim() || 'M')[0]?.toUpperCase() ?? 'M';
  const statusClass = model.lastTestStatus ?? 'unknown';
  const statusText =
    testing ? '正在测试连接...' : model.lastTestStatus === 'success' ? '联通正常' : model.lastTestStatus === 'failed' ? '联通失败' : '未测试';
  const showTestMessage = model.lastTestStatus === 'failed' && Boolean(model.lastTestMessage);

  return (
    <article className={clsx('model-config-card', model.enabled && 'enabled', current && 'current')}>
      <div className="model-card-mark" aria-hidden="true">
        {model.providerName.toLowerCase().includes('openai') ? <Bot size={20} /> : <span>{modelInitial}</span>}
      </div>
      <div className="model-card-main">
        <div className="model-card-title">
          <strong>{modelName}</strong>
          {model.isDefault && <span>默认</span>}
        </div>
        <small className="model-provider-name">{model.providerName}</small>
        <div className={clsx('model-card-status', statusClass)}>
          <span aria-hidden="true" />
          <small>{statusText}</small>
        </div>
        {showTestMessage && <small className={clsx('model-test-status', model.lastTestStatus)}>{model.lastTestMessage}</small>}
      </div>
      <div className="model-card-actions">
        <button
          className={clsx('model-enable-button', current && 'active')}
          type="button"
          title={current ? '正在使用' : '在对话中使用'}
          onClick={onSelect}
        >
          <Send size={15} />
          <span>{current ? '使用中' : '使用'}</span>
        </button>
        <button type="button" title="设为默认" aria-label={`设为默认 ${modelName}`} onClick={onSetDefault}>
          <ShieldCheck size={16} />
        </button>
        <button type="button" title="测试联通性" aria-label={`测试 ${modelName} 联通性`} disabled={testing} onClick={onTest}>
          <RotateCcw size={16} />
        </button>
        <button type="button" title="编辑" aria-label={`编辑 ${modelName}`} onClick={onEdit}>
          <PencilLine size={16} />
        </button>
        <button type="button" title="删除" aria-label={`删除 ${modelName}`} onClick={onDelete}>
          <Trash2 size={16} />
        </button>
      </div>
    </article>
  );
}

function FontSizeSelector({ value, onChange }: { value: UiFontSize; onChange: (fontSize: UiFontSize) => void }) {
  return (
    <div className="setting-row font-size-setting">
      <span>字体大小</span>
      <div className="font-size-control" role="group" aria-label="字体大小">
        {uiFontSizeOptions.map((option) => (
          <button
            className={clsx(value === option.value && 'active')}
            key={option.value}
            type="button"
            aria-pressed={value === option.value}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
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

function SettingsSelectRow({
  label,
  value,
  options,
  disabled = false,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="setting-row settings-select-row">
      <span>{label}</span>
      <select disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  );
}

function ToggleLine({ label, enabled = false, disabled = false, onToggle }: { label: string; enabled?: boolean; disabled?: boolean; onToggle?: () => void }) {
  return (
    <div className="setting-row">
      <span>{label}</span>
      <button
        className={clsx('mini-switch', enabled && 'on')}
        type="button"
        disabled={disabled}
        aria-label={label}
        aria-pressed={enabled}
        onClick={onToggle}
      >
        <i />
      </button>
    </div>
  );
}

function formatSettingsDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未知时间';
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date);
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

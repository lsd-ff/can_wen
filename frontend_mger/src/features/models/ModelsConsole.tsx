import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
  Activity,
  AlertTriangle,
  Bot,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Database,
  ExternalLink,
  Gauge,
  KeyRound,
  Network,
  Pencil,
  Plus,
  RefreshCcw,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  X,
  Zap,
} from 'lucide-react';
import './models.css';

type JsonObject = Record<string, unknown>;
type RequestJson = (path: string, options?: RequestInit) => Promise<unknown>;
type LoadState = { data: JsonObject | null; loading: boolean; error: string };
type Props = { request: RequestJson; onToast: (message: string) => void; canManage: boolean };
type ModelAction = { kind: 'test' | 'toggle'; item: JsonObject };
type JobAction = { kind: 'retry' | 'cancel'; item: JsonObject };

const CAPABILITY_LABELS: Record<string, string> = {
  chat: '对话生成', vision: '视觉理解', embedding: '向量嵌入', rerank: '结果重排', speech: '语音能力',
};
const JOB_LABELS: Record<string, string> = {
  knowledge_build: '知识构建', knowledge_publish: '知识发布',
};
const STATUS_LABELS: Record<string, string> = {
  queued: '排队中', running: '运行中', succeeded: '已完成', failed: '失败', cancelled: '已取消',
  passed: '连接正常', enabled: '已启用', disabled: '已停用', untested: '待测试',
};

export function ModelsConsole({ request, onToast, canManage }: Props) {
  const [tab, setTab] = useState<'models' | 'jobs'>(() => hashTab());
  const [revision, setRevision] = useState(0);
  const [editor, setEditor] = useState<JsonObject | 'create' | null>(null);
  const [modelAction, setModelAction] = useState<ModelAction | null>(null);
  const [jobAction, setJobAction] = useState<JobAction | null>(null);
  const models = useRemote(request, '/models', revision);
  const jobs = useRemote(request, '/jobs', revision);
  const modelRows = items(models.data);
  const jobRows = items(jobs.data);
  const activeJobs = jobRows.some((item) => ['queued', 'running'].includes(text(item.status)));

  useEffect(() => {
    if (!activeJobs) return;
    const timer = window.setInterval(() => setRevision((value) => value + 1), 5000);
    return () => window.clearInterval(timer);
  }, [activeJobs]);

  const refresh = () => setRevision((value) => value + 1);
  const switchTab = (next: 'models' | 'jobs') => {
    setTab(next);
    const params = new URLSearchParams(window.location.hash.split('?')[1] ?? '');
    params.set('tab', next);
    window.history.replaceState(null, '', `${window.location.hash.split('?')[0]}?${params.toString()}`);
  };

  const saveModel = async (values: JsonObject, current?: JsonObject) => {
    await request(current ? `/models/${text(current.id)}` : '/models', {
      method: current ? 'PATCH' : 'POST',
      body: JSON.stringify(values),
    });
    onToast(current ? '模型配置已保存' : '系统模型已添加');
    setEditor(null);
    refresh();
  };

  const submitModelAction = async (reason: string) => {
    if (!modelAction) return;
    const item = modelAction.item;
    if (modelAction.kind === 'test') {
      const result = await request(`/models/${text(item.id)}/test`, {
        method: 'POST', body: JSON.stringify({ reason }),
      }) as JsonObject;
      const passed = text(result.last_test_status) === 'passed';
      onToast(passed ? `${text(item.label)}连接正常` : `${text(item.label)}测试失败：${text(result.last_test_message)}`);
    } else {
      await request(`/models/${text(item.id)}`, {
        method: 'PATCH',
        body: JSON.stringify({
          key: item.key,
          label: item.label,
          model_id: item.model_id,
          api_base_url: item.api_base_url,
          api_key: null,
          clear_api_key: false,
          capability: item.capability,
          enabled: !Boolean(item.enabled),
          reason,
        }),
      });
      onToast(Boolean(item.enabled) ? '模型已停用' : '模型已恢复');
    }
    setModelAction(null);
    refresh();
  };

  const submitJobAction = async (reason: string) => {
    if (!jobAction) return;
    await request(`/jobs/${text(jobAction.item.id)}`, {
      method: 'PATCH', body: JSON.stringify({ action: jobAction.kind, reason }),
    });
    onToast(jobAction.kind === 'retry' ? '任务已重新进入队列' : '任务已取消');
    setJobAction(null);
    refresh();
  };

  return <section className="models-console">
    <header className="models-page-header">
      <div>
        <span className="eyebrow">MODEL CONTROL PLANE</span>
        <h2>模型与任务</h2>
        <p>统一管理知识智能体依赖的模型能力，并追踪每一次构建和发布任务。</p>
      </div>
      <div className="models-header-actions">
        <div className="models-segmented" role="tablist" aria-label="模型与任务工作区">
          <button role="tab" aria-selected={tab === 'models'} className={tab === 'models' ? 'active' : ''} onClick={() => switchTab('models')}>系统模型</button>
          <button role="tab" aria-selected={tab === 'jobs'} className={tab === 'jobs' ? 'active' : ''} onClick={() => switchTab('jobs')}>后台任务</button>
        </div>
        <button className="models-quiet-button" type="button" disabled={models.loading || jobs.loading} onClick={refresh}>
          <RefreshCcw size={14} className={models.loading || jobs.loading ? 'is-spinning' : ''} />刷新
        </button>
      </div>
    </header>

    <ModelsSummary models={modelRows} jobs={jobRows} />
    {(models.error || jobs.error) && <InlineError message={models.error || jobs.error} />}

    {tab === 'models'
      ? <ModelsWorkspace rows={modelRows} loading={models.loading} canManage={canManage} onCreate={() => setEditor('create')} onEdit={setEditor} onAction={setModelAction} />
      : <JobsWorkspace rows={jobRows} loading={jobs.loading} canManage={canManage} onAction={setJobAction} />}

    {editor && <ModelEditorDialog model={editor === 'create' ? undefined : editor} onClose={() => setEditor(null)} onSave={saveModel} />}
    {modelAction && <ReasonDialog {...modelActionCopy(modelAction)} onClose={() => setModelAction(null)} onSubmit={submitModelAction} />}
    {jobAction && <ReasonDialog {...jobActionCopy(jobAction)} onClose={() => setJobAction(null)} onSubmit={submitJobAction} />}
  </section>;
}

function ModelsSummary({ models, jobs }: { models: JsonObject[]; jobs: JsonObject[] }) {
  const enabled = models.filter((item) => Boolean(item.enabled)).length;
  const passed = models.filter((item) => text(item.last_test_status) === 'passed').length;
  const active = jobs.filter((item) => ['queued', 'running'].includes(text(item.status))).length;
  const failed = jobs.filter((item) => text(item.status) === 'failed').length;
  const cards = [
    ['已启用模型', enabled, `共 ${models.length} 个配置`, Bot],
    ['连接正常', passed, `${Math.max(0, enabled - passed)} 个待验证`, CheckCircle2],
    ['运行中任务', active, '自动每 5 秒刷新', Activity],
    ['失败任务', failed, failed ? '可进入任务页重试' : '当前无失败任务', AlertTriangle],
  ] as const;
  return <section className="models-summary-grid" aria-label="模型与任务概览">
    {cards.map(([label, count, note, Icon]) => <article className={label === '失败任务' && count ? 'attention' : ''} key={label}>
      <Icon size={17} /><span>{label}</span><strong>{count}</strong><small>{note}</small>
    </article>)}
  </section>;
}

function ModelsWorkspace({ rows, loading, canManage, onCreate, onEdit, onAction }: { rows: JsonObject[]; loading: boolean; canManage: boolean; onCreate: () => void; onEdit: (item: JsonObject) => void; onAction: (action: ModelAction) => void }) {
  const [query, setQuery] = useState('');
  const [capability, setCapability] = useState('all');
  const filtered = useMemo(() => rows.filter((item) => {
    const needle = query.trim().toLowerCase();
    const matchesText = !needle || [item.label, item.key, item.model_id].some((value) => text(value).toLowerCase().includes(needle));
    return matchesText && (capability === 'all' || text(item.capability) === capability);
  }), [rows, query, capability]);

  return <>
    <CapabilityRail rows={rows} />
    <section className="models-panel">
      <div className="models-toolbar">
        <label className="models-search"><Search size={15} /><input aria-label="搜索系统模型" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索名称、标识或模型 ID" /></label>
        <select aria-label="模型能力" value={capability} onChange={(event) => setCapability(event.target.value)}>
          <option value="all">全部能力</option>{Object.entries(CAPABILITY_LABELS).map(([key, label]) => <option value={key} key={key}>{label}</option>)}
        </select>
        {canManage && <button className="models-primary-button" type="button" onClick={onCreate}><Plus size={15} />添加模型</button>}
      </div>
      {loading ? <Loading message="正在读取模型配置…" /> : filtered.length ? <div className="model-card-grid">
        {filtered.map((item) => <ModelCard item={item} canManage={canManage} onEdit={() => onEdit(item)} onAction={onAction} key={text(item.id)} />)}
      </div> : <Empty icon={<Bot size={25} />} title="没有符合条件的模型" description="调整筛选条件，或添加一个 OpenAI-compatible 模型配置。" />}
    </section>
  </>;
}

function CapabilityRail({ rows }: { rows: JsonObject[] }) {
  const stages = [
    { label: '抽取生成', note: 'QA / KG', keys: ['qa-extract', 'kg-extract'], icon: BrainCircuit },
    { label: '专家评审', note: '质量控制', keys: ['expert-review'], icon: ShieldCheck },
    { label: '向量化', note: '1024 维', keys: ['embedding-primary'], icon: Database },
    { label: '结果重排', note: 'Rerank', keys: ['rerank-primary'], icon: Zap },
  ];
  return <section className="capability-rail" aria-label="知识智能体模型能力链">
    <header><div><span>KNOWLEDGE AGENT ROUTE</span><h3>知识智能体能力链</h3></div><small>配置、启用且连通测试通过才视为就绪</small></header>
    <div>{stages.map(({ label, note, keys, icon: Icon }) => {
      const assigned = keys.map((key) => rows.find((item) => text(item.key) === key)).filter(Boolean) as JsonObject[];
      const ready = assigned.length === keys.length && assigned.every((item) => Boolean(item.enabled) && text(item.last_test_status) === 'passed');
      return <article data-state={ready ? 'ready' : 'attention'} key={label}>
        <span className="capability-icon"><Icon size={18} /></span>
        <div><small>{note}</small><strong>{label}</strong><p>{assigned.length ? assigned.map((item) => text(item.model_id)).join(' · ') : '尚未配置'}</p></div>
        <b>{ready ? '就绪' : `${assigned.filter((item) => text(item.last_test_status) === 'passed').length}/${keys.length}`}</b>
      </article>;
    })}</div>
  </section>;
}

function ModelCard({ item, canManage, onEdit, onAction }: { item: JsonObject; canManage: boolean; onEdit: () => void; onAction: (action: ModelAction) => void }) {
  const enabled = Boolean(item.enabled);
  const testStatus = text(item.last_test_status, 'untested');
  return <article className={`model-card ${enabled ? '' : 'is-disabled'}`}>
    <header>
      <span className="model-capability-icon"><Bot size={18} /></span>
      <div><strong>{text(item.label)}</strong><small>{text(item.key)}</small></div>
      <Status value={enabled ? 'enabled' : 'disabled'} />
    </header>
    <div className="model-identity"><span>{CAPABILITY_LABELS[text(item.capability)] ?? text(item.capability)}</span><code>{text(item.model_id)}</code></div>
    <dl>
      <div><dt>接口</dt><dd>{endpointLabel(text(item.api_base_url))}</dd></div>
      <div><dt>凭据</dt><dd><KeyRound size={12} />{credentialLabel(text(item.credential_source))}</dd></div>
      <div><dt>最近测试</dt><dd>{item.last_test_at ? dateTime(item.last_test_at) : '尚未测试'}</dd></div>
    </dl>
    <div className={`model-test-state ${testStatus}`}><span /><div><strong>{STATUS_LABELS[testStatus] ?? testStatus}</strong><small>{text(item.last_test_message, '保存配置后请执行连通性测试')}</small></div></div>
    {canManage && <footer>
      <button type="button" className="models-quiet-button" onClick={() => onAction({ kind: 'test', item })}><Sparkles size={13} />测试连接</button>
      <button type="button" className="models-quiet-button" onClick={onEdit}><Pencil size={13} />编辑</button>
      <button type="button" className={enabled ? 'models-danger-button' : 'models-quiet-button'} onClick={() => onAction({ kind: 'toggle', item })}>{enabled ? <ToggleRight size={14} /> : <ToggleLeft size={14} />}{enabled ? '停用' : '恢复'}</button>
    </footer>}
  </article>;
}

function JobsWorkspace({ rows, loading, canManage, onAction }: { rows: JsonObject[]; loading: boolean; canManage: boolean; onAction: (action: JobAction) => void }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [selected, setSelected] = useState('');
  const filtered = useMemo(() => rows.filter((item) => {
    const needle = query.trim().toLowerCase();
    const matches = !needle || [item.id, JOB_LABELS[text(item.job_type)] ?? item.job_type, item.error_message].some((value) => text(value).toLowerCase().includes(needle));
    return matches && (status === 'all' || text(item.status) === status);
  }), [rows, query, status]);
  const rowIds = filtered.map((item) => text(item.id)).join('|');
  useEffect(() => {
    if (!filtered.some((item) => text(item.id) === selected)) setSelected(filtered.length ? text(filtered[0].id) : '');
  }, [rowIds, selected]);
  const detail = filtered.find((item) => text(item.id) === selected);

  return <section className="jobs-workspace">
    <article className="jobs-list-panel">
      <header><div><span>BACKGROUND JOBS</span><h3>异步任务队列</h3></div><b>{filtered.length}</b></header>
      <div className="jobs-toolbar">
        <label className="models-search"><Search size={14} /><input aria-label="搜索后台任务" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索任务类型、ID 或错误" /></label>
        <select aria-label="任务状态" value={status} onChange={(event) => setStatus(event.target.value)}><option value="all">全部状态</option><option value="queued">排队中</option><option value="running">运行中</option><option value="succeeded">已完成</option><option value="failed">失败</option><option value="cancelled">已取消</option></select>
      </div>
      {loading ? <Loading message="正在读取后台任务…" /> : filtered.length ? <div className="jobs-list">{filtered.map((item) => <button type="button" className={selected === text(item.id) ? 'selected' : ''} onClick={() => setSelected(text(item.id))} key={text(item.id)}>
        <div><strong>{JOB_LABELS[text(item.job_type)] ?? text(item.job_type)}</strong><Status value={text(item.status)} /></div>
        <div className="job-progress"><span style={{ width: `${Math.min(100, number(item.progress))}%` }} /></div>
        <p>{number(item.progress)}% · 更新于 {dateTime(item.updated_at)}</p>
        {text(item.error_message) !== '—' && <small>{text(item.error_message)}</small>}
      </button>)}</div> : <Empty icon={<Gauge size={25} />} title="当前没有后台任务" description="从知识中心启动构建或发布后，任务会在这里持续更新。" />}
    </article>
    <aside className="job-detail-panel">
      {detail ? <JobDetail item={detail} canManage={canManage} onAction={onAction} /> : <Empty icon={<Activity size={25} />} title="选择一个任务" description="查看进度、执行时间、结果和失败原因。" />}
    </aside>
  </section>;
}

function JobDetail({ item, canManage, onAction }: { item: JsonObject; canManage: boolean; onAction: (action: JobAction) => void }) {
  const payload = (item.payload ?? {}) as JsonObject;
  const result = (item.result ?? {}) as JsonObject;
  const currentStatus = text(item.status);
  return <div className="job-detail">
    <header><div><span>JOB TRACE</span><h3>{JOB_LABELS[text(item.job_type)] ?? text(item.job_type)}</h3><p>{text(item.id)}</p></div><Status value={currentStatus} /></header>
    <section className="job-progress-large"><div><span>执行进度</span><b>{number(item.progress)}%</b></div><i><span style={{ width: `${Math.min(100, number(item.progress))}%` }} /></i></section>
    <dl className="job-facts">
      <div><dt>创建时间</dt><dd>{dateTime(item.created_at)}</dd></div>
      <div><dt>开始时间</dt><dd>{item.started_at ? dateTime(item.started_at) : '尚未开始'}</dd></div>
      <div><dt>完成时间</dt><dd>{item.completed_at ? dateTime(item.completed_at) : '尚未完成'}</dd></div>
      <div><dt>关联对象</dt><dd>{text(payload.build_run_id ?? payload.publication_id ?? payload.source_id)}</dd></div>
    </dl>
    {text(item.error_message) !== '—' && <InlineError message={text(item.error_message)} />}
    {Object.keys(result).length > 0 && <section className="job-result"><span>任务结果</span><pre>{JSON.stringify(result, null, 2)}</pre></section>}
    <button type="button" className="models-link-button" onClick={() => { window.location.hash = '/knowledge'; }}><ExternalLink size={13} />打开知识中心</button>
    {canManage && <footer>
      {currentStatus === 'failed' && <button type="button" className="models-primary-button" onClick={() => onAction({ kind: 'retry', item })}><RotateCcw size={14} />重试任务</button>}
      {['queued', 'running'].includes(currentStatus) && <button type="button" className="models-danger-button" onClick={() => onAction({ kind: 'cancel', item })}>取消任务</button>}
    </footer>}
  </div>;
}

function ModelEditorDialog({ model, onClose, onSave }: { model?: JsonObject; onClose: () => void; onSave: (values: JsonObject, current?: JsonObject) => Promise<void> }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [clearCredential, setClearCredential] = useState(false);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true); setError('');
    try {
      await onSave({
        key: form.get('key'), label: form.get('label'), model_id: form.get('model_id'), api_base_url: form.get('api_base_url'),
        capability: form.get('capability'), api_key: clearCredential ? null : form.get('api_key') || null,
        clear_api_key: clearCredential, enabled: form.get('enabled') === 'on', reason: form.get('reason'),
      }, model);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '模型配置保存失败'); }
    finally { setSaving(false); }
  };
  return <Dialog title={model ? `编辑 · ${text(model.label)}` : '添加系统模型'} onClose={onClose}>
    <form className="model-editor-form" onSubmit={submit}>
      <div className="model-form-intro"><BrainCircuit size={18} /><p>模型配置只作用于平台知识智能体。API Key 加密保存且不会回显。</p></div>
      <div className="model-form-grid">
        <label>内部标识<input name="key" required minLength={2} maxLength={80} defaultValue={text(model?.key, '')} placeholder="qa-extract" /></label>
        <label>显示名称<input name="label" required minLength={2} maxLength={120} defaultValue={text(model?.label, '')} placeholder="QA 抽取模型" /></label>
        <label>模型 ID<input name="model_id" required minLength={2} maxLength={200} defaultValue={text(model?.model_id, '')} placeholder="qwen3.7-plus" /></label>
        <label>能力<select name="capability" defaultValue={text(model?.capability, 'chat')}><option value="chat">对话生成</option><option value="vision">视觉理解</option><option value="embedding">向量嵌入</option><option value="rerank">结果重排</option><option value="speech">语音能力</option></select></label>
        <label className="wide">OpenAI-compatible 地址<input name="api_base_url" required type="url" minLength={8} maxLength={500} defaultValue={text(model?.api_base_url, '')} placeholder="https://example.com/compatible-mode/v1" /></label>
        <label className="wide">API Key（留空则{model ? '保持当前配置' : '使用系统密钥'}）<input name="api_key" type="password" minLength={8} maxLength={1000} disabled={clearCredential} autoComplete="new-password" /></label>
      </div>
      {model?.has_api_key && <label className="model-checkbox"><input type="checkbox" checked={clearCredential} onChange={(event) => setClearCredential(event.target.checked)} />移除独立密钥，改用系统级密钥</label>}
      <label className="model-checkbox"><input name="enabled" type="checkbox" defaultChecked={model ? Boolean(model.enabled) : true} />保存后启用该模型</label>
      <label className="model-reason">保存理由<textarea name="reason" required minLength={3} maxLength={500} placeholder="说明新增或调整模型的原因" /></label>
      {error && <InlineError message={error} />}
      <footer><button type="button" className="models-quiet-button" disabled={saving} onClick={onClose}>取消</button><button className="models-primary-button" disabled={saving}>{saving ? '正在保存…' : '保存模型'}</button></footer>
    </form>
  </Dialog>;
}

function ReasonDialog({ title, description, actionLabel, defaultReason, danger = false, onClose, onSubmit }: { title: string; description: string; actionLabel: string; defaultReason: string; danger?: boolean; onClose: () => void; onSubmit: (reason: string) => Promise<void> }) {
  const [reason, setReason] = useState(defaultReason);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (reason.trim().length < 3) { setError('请填写至少 3 个字的操作理由'); return; }
    setSaving(true); setError('');
    try { await onSubmit(reason.trim()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '操作失败'); }
    finally { setSaving(false); }
  };
  return <Dialog title={title} onClose={onClose}><form className="model-action-form" onSubmit={submit}>
    <div className="model-action-copy"><Sparkles size={18} /><div><strong>{actionLabel}</strong><p>{description}</p></div></div>
    <label>操作理由<textarea value={reason} onChange={(event) => { setReason(event.target.value); if (error) setError(''); }} minLength={3} maxLength={500} autoFocus /></label>
    {error && <InlineError message={error} />}
    <footer><button type="button" className="models-quiet-button" disabled={saving} onClick={onClose}>取消</button><button className={danger ? 'models-danger-button' : 'models-primary-button'} disabled={saving}>{saving ? '正在处理…' : actionLabel}</button></footer>
  </form></Dialog>;
}

function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return <div className="modal-backdrop models-modal-backdrop" onMouseDown={onClose}><section className="models-modal" role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}><header><div><span>MODEL CONTROL PLANE</span><h2>{title}</h2></div><button type="button" aria-label="关闭" onClick={onClose}><X size={18} /></button></header><div className="models-modal-content">{children}</div></section></div>;
}

function Status({ value }: { value: string }) { return <span className={`models-status status-${value}`}>{STATUS_LABELS[value] ?? value}</span>; }
function InlineError({ message }: { message: string }) { return <div className="models-inline-error" role="alert"><AlertTriangle size={16} /><span>{message}</span></div>; }
function Loading({ message }: { message: string }) { return <div className="models-loading"><RefreshCcw size={19} className="is-spinning" /><p>{message}</p></div>; }
function Empty({ icon, title, description }: { icon: ReactNode; title: string; description: string }) { return <div className="models-empty">{icon}<strong>{title}</strong><p>{description}</p></div>; }

function modelActionCopy(action: ModelAction) {
  const enabled = Boolean(action.item.enabled);
  if (action.kind === 'test') return { title: `测试 · ${text(action.item.label)}`, description: '将按模型能力发送最小测试请求，并记录 HTTP 状态和测试时间。', actionLabel: '开始测试', defaultReason: '验证模型配置与接口连通性' };
  return { title: `${enabled ? '停用' : '恢复'} · ${text(action.item.label)}`, description: enabled ? '停用后，新的知识构建不会再选择该模型配置。' : '恢复后，模型可重新参与知识智能体构建。', actionLabel: enabled ? '确认停用' : '确认恢复', defaultReason: enabled ? '暂时停用该模型配置' : '恢复该模型配置', danger: enabled };
}
function jobActionCopy(action: JobAction) {
  if (action.kind === 'cancel') {
    const jobType = text(action.item.job_type);
    const jobLabel = JOB_LABELS[jobType] ?? jobType;
    const isPublish = jobType === 'knowledge_publish';
    return {
      title: `取消 · ${jobLabel}`,
      description: isPublish
        ? '系统将停止后续写入并回滚本次发布状态；已经完成的构建成果会保留，可重新发布。'
        : '系统将停止后续节点，将构建标记为已取消，并让知识源恢复为可再次操作的状态。',
      actionLabel: '确认取消',
      defaultReason: '停止当前后台任务',
      danger: true,
    };
  }
  return action.kind === 'retry'
    ? { title: `重试 · ${JOB_LABELS[text(action.item.job_type)] ?? text(action.item.job_type)}`, description: '任务会从队列重新执行，原失败信息仍保留在审计记录中。', actionLabel: '确认重试', defaultReason: '修复依赖后重新执行任务' }
    : { title: `取消 · ${JOB_LABELS[text(action.item.job_type)] ?? text(action.item.job_type)}`, description: '系统将停止后续节点并把关联构建或发布状态标记为已取消。', actionLabel: '确认取消', defaultReason: '停止当前后台任务', danger: true };
}
function useRemote(request: RequestJson, path: string, revision: number): LoadState {
  const [state, setState] = useState<LoadState>({ data: null, loading: true, error: '' });
  useEffect(() => {
    let active = true;
    setState((current) => ({ ...current, loading: true, error: '' }));
    void request(path).then((data) => { if (active) setState({ data: data as JsonObject, loading: false, error: '' }); }).catch((cause) => { if (active) setState((current) => ({ ...current, loading: false, error: cause instanceof Error ? cause.message : '请求失败' })); });
    return () => { active = false; };
  }, [path, request, revision]);
  return state;
}
function items(data: JsonObject | null): JsonObject[] { return Array.isArray(data?.items) ? data.items as JsonObject[] : []; }
function text(value: unknown, fallback = '—'): string { if (value === null || value === undefined || value === '') return fallback; return String(value); }
function number(value: unknown): number { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0; }
function dateTime(value: unknown): string { if (!value) return '—'; const date = new Date(String(value)); return Number.isNaN(date.getTime()) ? text(value) : date.toLocaleString('zh-CN', { hour12: false }); }
function endpointLabel(value: string): string { try { const url = new URL(value); return `${url.hostname}${url.pathname === '/' ? '' : url.pathname}`; } catch { return value; } }
function credentialLabel(value: string): string { return value === 'model' ? '独立密钥' : value === 'system' ? '系统密钥' : '缺少密钥'; }
function hashTab(): 'models' | 'jobs' { const params = new URLSearchParams(window.location.hash.split('?')[1] ?? ''); return params.get('tab') === 'jobs' ? 'jobs' : 'models'; }

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent, type ReactNode, type RefObject } from 'react';
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from 'react-force-graph-2d';
import { AlertTriangle, BookOpenCheck, Bot, BrainCircuit, CheckCircle2, Database, FileText, GitBranch, ListTree, Maximize2, Minimize2, Network, PlayCircle, RefreshCcw, RotateCcw, Route, Search, ShieldCheck, Sparkles, Table2, Trash2, Upload, Wrench, X, ZoomIn, ZoomOut } from 'lucide-react';
import './knowledge.css';

type JsonObject = Record<string, unknown>;
type RequestJson = (path: string, options?: RequestInit) => Promise<unknown>;
type Props = { request: RequestJson; onToast: (message: string) => void; canManage: boolean };
type LoadState<T> = { data: T | null; loading: boolean; error: string };
type PanelProps = { request: RequestJson; revision: number; onRefresh: () => void; onToast: (message: string) => void; canManage: boolean };

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿', processing: '处理中', ready: '可用', failed: '失败', disabled: '已停用', uploaded: '待解析', parsed: '已解析', parsing: '解析中', queued: '排队中', running: '运行中', awaiting_review: '待人工审核', publishing: '发布中', succeeded: '构建完成', cancelled: '已取消', pending: '待质检', needs_review: '需人工审核', open: '待审核', claimed: '审核中', approved: '已通过', rejected: '已驳回', published: '已发布', staging: '准备发布', rolled_back: '已回滚', high: '高', medium: '中', low: '低', critical: '紧急', qa: 'QA', triple: '三元组', chunk: 'Chunk',
};

const KG_LABEL_COLORS: Record<string, string> = {
  Disease: '#ff6b6b', DiseaseCategory: '#845ef7', Cause: '#ff922b', Symptom: '#f06595', Lesion: '#e8590c', Part: '#15aabf', Route: '#12b886', Condition: '#40c057', Stage: '#228be6', Diagnosis: '#5f3dc4', Measure: '#2f9e44',
};

type GraphSchemaItem = { key: string; label: string; count: number };
type GraphNodeDatum = {
  id: string;
  name: string;
  type: string;
  typeLabel: string;
  degree: number;
  properties: JsonObject;
};
type GraphLinkDatum = {
  id: string;
  source: string | NodeObject<GraphNodeDatum>;
  target: string | NodeObject<GraphNodeDatum>;
  relation: string;
  relationKey: string;
  evidence: string;
  properties: JsonObject;
};

export function KnowledgeConsole({ request, onToast, canManage }: Props) {
  const [tab, setTab] = useState<'sources' | 'builds' | 'extractions' | 'reviews' | 'graph'>('sources');
  const [revision, setRevision] = useState(0);
  const refresh = () => setRevision((value) => value + 1);
  const overview = useRemote<JsonObject>(request, '/knowledge/overview', revision);
  useEffect(() => { if (tab !== 'builds') return; const timer = window.setInterval(refresh, 5000); return () => window.clearInterval(timer); }, [tab]);
  return <>
    <header className="page-header knowledge-page-header"><div><span className="eyebrow">DOMAIN KNOWLEDGE FACTORY</span><h2>养蚕知识中心</h2><p>将真实文献构建为可审核、可追溯、可版本化的 RAG 问答库与疾病知识图谱。</p></div><div className="knowledge-header-actions"><div className="segmented">{([['sources', '文档库'], ['builds', '构建任务'], ['extractions', '抽取结果'], ['reviews', '人工审核'], ['graph', '图谱预览']] as const).map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}</div><button className="quiet-button" onClick={refresh}><RefreshCcw size={14} />刷新</button></div></header>
    <KnowledgeSummary data={overview.data ?? {}} loading={overview.loading} />
    {overview.error && <InlineError message={overview.error} />}
    {tab === 'sources' && <SourcesPanel request={request} revision={revision} onRefresh={refresh} onToast={onToast} canManage={canManage} />}
    {tab === 'builds' && <BuildsPanel request={request} revision={revision} onRefresh={refresh} onToast={onToast} canManage={canManage} />}
    {tab === 'extractions' && <ExtractionResultsPanel request={request} revision={revision} />}
    {tab === 'reviews' && <ReviewsPanel request={request} revision={revision} onRefresh={refresh} onToast={onToast} canManage={canManage} />}
    {tab === 'graph' && <GraphPanel request={request} revision={revision} />}
  </>;
}

function KnowledgeSummary({ data, loading }: { data: JsonObject; loading: boolean }) {
  const cards = [['文档来源', value(data.sources), '已登记知识源', BookOpenCheck], ['可用知识源', value(data.ready_sources), '已完成构建或发布', CheckCircle2], ['运行任务', value(data.active_builds), '构建与发布任务', Sparkles], ['待人工审核', value(data.open_reviews), '规则或专家模型拦截', ShieldCheck], ['QA 数据', value(data.qa_items), '当前全部问答候选', Database], ['KG 三元组', value(data.triples), '当前全部关系候选', Network]] as const;
  return <section className="knowledge-summary-grid">{cards.map(([label, count, note, Icon]) => <article key={label} className={label === '待人工审核' && count > 0 ? 'attention' : ''}><Icon size={17} /><span>{label}</span><strong>{loading ? '…' : count.toLocaleString('zh-CN')}</strong><small>{note}</small></article>)}</section>;
}

function SourcesPanel({ request, revision, onRefresh, onToast, canManage }: PanelProps) {
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(1);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [buildTarget, setBuildTarget] = useState<JsonObject | null>(null);
  const [statusTarget, setStatusTarget] = useState<JsonObject | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<JsonObject | null>(null);
  const statusQuery = statusFilter === 'all' ? '' : `&status=${statusFilter}`;
  const resource = useRemote<JsonObject>(request, `/knowledge/sources?query=${encodeURIComponent(query)}${statusQuery}&page=${page}&page_size=20`, revision);
  const rows = items(resource.data);
  return <section className="knowledge-panel">
    <div className="knowledge-panel-toolbar">
      <label className="input-with-icon"><Search size={15} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="搜索文档名称或文件名" /></label>
      <label className="knowledge-filter-field"><span>状态</span><select value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}><option value="all">全部状态</option><option value="draft">草稿</option><option value="processing">处理中</option><option value="ready">可用</option><option value="failed">失败</option><option value="disabled">已停用</option></select></label>
      {canManage && <button className="primary-button" onClick={() => setUploadOpen(true)}><Upload size={15} />上传文档</button>}
    </div>
    <LoadBlock state={resource}>{rows.length ? <div className="knowledge-source-list">{rows.map((source) => {
      const sourceStatus = text(source.status);
      const processing = sourceStatus === 'processing';
      const disabled = sourceStatus === 'disabled';
      return <article key={text(source.id)} className={disabled ? 'is-disabled' : ''}>
        <div className="knowledge-source-icon"><FileText size={20} /></div>
        <div className="knowledge-source-main"><div><strong>{text(source.title)}</strong><Status value={sourceStatus} /></div><p>{text(source.original_filename, 'Markdown 文档')} · {text(source.version)} · SHA {text(source.content_sha256).slice(0, 12)}</p><small>{value(source.version_count)} 个版本 · 更新于 {dateTime(source.updated_at)}</small></div>
        <div className="knowledge-source-actions">
          {canManage && !disabled && <button className="primary-button compact" disabled={processing} onClick={() => setBuildTarget(source)}><PlayCircle size={14} />{processing ? '构建中' : '构建'}</button>}
          {canManage && <button className="quiet-button compact" disabled={processing} onClick={() => setStatusTarget(source)}>{disabled ? '恢复' : '停用'}</button>}
          {canManage && <button className="danger-button compact" disabled={processing} onClick={() => setDeleteTarget(source)}><Trash2 size={13} />删除</button>}
        </div>
      </article>;
    })}</div> : <Empty message="当前筛选下没有知识文档。可调整条件，或上传 Markdown、PDF、Word 等原始文献。" />}</LoadBlock>
    <Pager total={value(resource.data?.total)} page={page} pageSize={value(resource.data?.page_size) || 20} onChange={setPage} />
    {uploadOpen && <UploadDialog request={request} onClose={() => setUploadOpen(false)} onDone={() => { setUploadOpen(false); onRefresh(); }} onToast={onToast} />}
    {buildTarget && <BuildDialog source={buildTarget} request={request} onClose={() => setBuildTarget(null)} onDone={() => { setBuildTarget(null); onRefresh(); }} onToast={onToast} />}
    {statusTarget && <ReasonActionDialog
      title={`${text(statusTarget.status) === 'disabled' ? '恢复' : '停用'} · ${text(statusTarget.title)}`}
      description={text(statusTarget.status) === 'disabled' ? '恢复后可再次发起构建；已有文件、抽取结果和已发布数据不会改变。' : '停用后不能发起新构建，但不会删除原始文件、抽取结果或已经发布到检索库和图数据库的数据。'}
      actionLabel={text(statusTarget.status) === 'disabled' ? '确认恢复' : '确认停用'}
      defaultReason={text(statusTarget.status) === 'disabled' ? '恢复知识源以便重新构建' : '暂时停用该知识源'}
      danger={text(statusTarget.status) !== 'disabled'}
      onClose={() => setStatusTarget(null)}
      onSubmit={async (reason) => {
        const nextStatus = text(statusTarget.status) === 'disabled' ? 'draft' : 'disabled';
        await request(`/knowledge/sources/${text(statusTarget.id)}/status`, { method: 'PATCH', body: JSON.stringify({ status: nextStatus, reason }) });
        onToast(nextStatus === 'disabled' ? '知识源已停用，已有知识数据保持不变' : '知识源已恢复，可重新发起构建');
        setStatusTarget(null); onRefresh();
      }}
    />}
    {deleteTarget && <DeleteSourceDialog source={deleteTarget} request={request} onClose={() => setDeleteTarget(null)} onDone={() => { setDeleteTarget(null); onRefresh(); }} onToast={onToast} />}
  </section>;
}

function BuildsPanel({ request, revision, onRefresh, onToast, canManage }: PanelProps) {
  const [selected, setSelected] = useState('');
  const [publishTarget, setPublishTarget] = useState<JsonObject | null>(null);
  const resource = useRemote<JsonObject>(request, '/knowledge/builds?page=1&page_size=100', revision);
  const rows = items(resource.data);
  const buildIds = rows.map((row) => text(row.id)).join('|');
  useEffect(() => { if (!rows.some((row) => text(row.id) === selected)) setSelected(rows.length ? text(rows[0].id) : ''); }, [buildIds, selected]);
  const detail = useRemote<JsonObject>(request, selected ? `/knowledge/builds/${selected}` : '', revision, Boolean(selected));
  const selectedBuild = (detail.data?.build ?? null) as JsonObject | null;
  const publication = (selectedBuild?.publication ?? null) as JsonObject | null;
  const events = Array.isArray(detail.data?.events) ? detail.data.events as JsonObject[] : [];
  const runtime = (detail.data?.agent_runtime ?? {}) as JsonObject;
  const chunkDecisions = Array.isArray(detail.data?.chunk_decisions) ? detail.data.chunk_decisions as JsonObject[] : [];
  return <section className="knowledge-split-panel">
    <article className="knowledge-queue-panel">
      <header><div><span>BUILD RUNS</span><h3>RAG / KG 构建任务</h3></div><b>{rows.length}</b></header>
      <LoadBlock state={resource}>{rows.length ? <div className="knowledge-build-list">{rows.map((build) => <button key={text(build.id)} className={selected === text(build.id) ? 'selected' : ''} onClick={() => setSelected(text(build.id))}><div><strong>{text(build.source_title)}</strong><Status value={text(build.status)} /></div><p>{(Array.isArray(build.targets) ? build.targets : []).map(String).join(' + ').toUpperCase()} · {nodeLabel(text(build.current_node, 'queued'))}</p><div className="knowledge-progress"><span style={{ width: `${Math.min(100, value(build.progress))}%` }} /></div><small>{value(build.progress)}% · 待审核 {value(build.open_review_count)} · {dateTime(build.updated_at)}</small></button>)}</div> : <Empty message="还没有构建任务。请先从文档库选择文档并启动 RAG/KG 构建。" />}</LoadBlock>
    </article>
    <aside className="knowledge-detail-panel knowledge-agent-detail">
      <LoadBlock state={detail}>{selectedBuild ? <>
        <div className="knowledge-detail-heading"><div><span>AGENT RUN</span><h3>{text(selectedBuild.source_title)}</h3><p>{text(selectedBuild.version)} · {text(selectedBuild.id)}</p></div><Status value={text(selectedBuild.status)} /></div>
        <AgentRuntimePanel runtime={runtime} build={selectedBuild} />
        <section className="knowledge-metric-row"><span><b>{value((selectedBuild.metrics as JsonObject | undefined)?.chunk_count)}</b>Chunk</span><span><b>{value((selectedBuild.metrics as JsonObject | undefined)?.qa_count)}</b>QA</span><span><b>{value((selectedBuild.metrics as JsonObject | undefined)?.triple_count)}</b>三元组</span></section>
        {text(selectedBuild.error_message) !== '—' && <InlineError message={text(selectedBuild.error_message)} />}
        {publication && <PublicationPanel publication={publication} />}
        <ChunkDecisionPanel rows={chunkDecisions} total={value(detail.data?.chunk_decision_total)} />
        <AgentTimeline events={events} />
        {canManage && text(selectedBuild.status) === 'succeeded' && !publication && <button className="primary-button wide" onClick={() => setPublishTarget(selectedBuild)}><Database size={15} />发布到 Qdrant、OpenSearch 与 Neo4j Aura</button>}
      </> : <Empty message="从左侧选择一个构建任务查看智能体规划、决策和工具轨迹。" />}</LoadBlock>
    </aside>
    {publishTarget && <ReasonActionDialog title="发布知识版本" description="仅发布已通过质量控制的数据；QA 将同步写入 Qdrant 与 OpenSearch，三元组将写入 Neo4j Aura。重复提交会返回已有发布版本，不会重复写入。" actionLabel="确认发布" defaultReason="发布已通过审核的知识版本" onClose={() => setPublishTarget(null)} onSubmit={async (reason) => { const result = await request(`/knowledge/builds/${text(publishTarget.id)}/publish`, { method: 'POST', body: JSON.stringify({ reason }) }) as JsonObject; onToast(result.created === false ? '该知识版本已经发布，无需重复操作' : '发布任务已进入队列'); setPublishTarget(null); onRefresh(); }} />}
  </section>;
}

function PublicationPanel({ publication }: { publication: JsonObject }) {
  const publicationStatus = text(publication.status);
  const counts = (publication.counts ?? {}) as JsonObject;
  const failed = publicationStatus === 'failed';
  const staging = publicationStatus === 'staging';
  return <section className={`knowledge-publication-card status-${publicationStatus}`}>
    <header><div><span>PUBLISH SNAPSHOT</span><strong>{publicationStatus === 'published' ? '知识版本已发布' : publicationStatus === 'staging' ? '正在同步检索存储' : '知识版本发布失败'}</strong></div><Status value={publicationStatus} /></header>
    <div className="knowledge-publication-stores">
      <span><Database size={14} /><small>Qdrant</small><b>{text(publication.qdrant_collection, staging ? '等待创建写入事件' : value(counts.qa) ? '等待写入' : '本版本无 QA')}</b></span>
      <span><Search size={14} /><small>OpenSearch</small><b>{text(publication.opensearch_index, staging ? '等待创建写入事件' : value(counts.qa) ? '等待写入' : '本版本无 QA')}</b></span>
      <span><Network size={14} /><small>Neo4j Aura</small><b>{text(publication.neo4j_database, staging ? '等待创建写入事件' : value(counts.triples) ? '等待写入' : '本版本无三元组')}</b></span>
    </div>
    <p>{staging ? '正在计算待写入数量并生成跨存储幂等事件。' : <>QA {value(counts.qa).toLocaleString('zh-CN')} 条 · 三元组 {value(counts.triples).toLocaleString('zh-CN')} 条{publication.published_at ? ` · 发布于 ${dateTime(publication.published_at)}` : ''}</>}</p>
    {failed && <div className="knowledge-publication-failure"><AlertTriangle size={15} /><span>{text(publication.error_message, '发布任务执行失败，请查看后台任务日志。')}</span><a href="#/models?tab=jobs">到后台任务重试</a></div>}
  </section>;
}

function AgentRuntimePanel({ runtime, build }: { runtime: JsonObject; build: JsonObject }) {
  const plan = (runtime.plan ?? {}) as JsonObject;
  const profile = (plan.document_profile ?? {}) as JsonObject;
  const reflections = (runtime.reflection_rounds ?? {}) as JsonObject;
  const tools = Array.isArray(runtime.tools_invoked) ? runtime.tools_invoked.map(String) : [];
  const reasons = Array.isArray(plan.reasons) ? plan.reasons.map(String) : [];
  const activeAgent = text(runtime.active_agent, 'orchestrator');
  const running = ['queued', 'running', 'publishing'].includes(text(build.status));
  return <section className="knowledge-agent-runtime">
    <div className="knowledge-agent-live">
      <span className={`agent-orb ${running ? 'running' : ''}`}><Bot size={20} /></span>
      <div><small>当前智能体</small><strong>{agentLabel(activeAgent)}</strong><p>{nodeLabel(text(runtime.current_node, 'queued'))}</p></div>
      <span className="agent-route"><Route size={13} />{routeLabel(text(runtime.last_route, 'waiting'))}</span>
    </div>
    <div className="knowledge-agent-stat-grid">
      <span><Wrench size={14} /><b>{tools.length}</b><small>已调用工具</small></span>
      <span><RotateCcw size={14} /><b>{value(reflections.rag) + value(reflections.kg)}</b><small>反思轮次</small></span>
      <span className={value(runtime.human_handoff_count) ? 'attention' : ''}><ShieldCheck size={14} /><b>{value(runtime.human_handoff_count)}</b><small>转人工</small></span>
    </div>
    {Object.keys(plan).length > 0 && <details className="knowledge-agent-plan" open>
      <summary><BrainCircuit size={15} /><span>总控规划</span><small>{value(plan.base_heading_level) ? `H${value(plan.base_heading_level)}` : '全文'} · {value(plan.chunk_target_tokens)} tokens</small></summary>
      <div className="agent-plan-facts"><span>文档约 {value(profile.estimated_tokens).toLocaleString('zh-CN')} tokens</span><span>{splitStrategyLabel(text(plan.semantic_split_strategy))}</span><span>最多反思 {value(plan.max_reflection_rounds)} 轮</span></div>
      {reasons.length > 0 && <ul>{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
    </details>}
    {tools.length > 0 && <div className="knowledge-agent-tools"><span>工具链</span>{tools.map((tool) => <b key={tool}>{toolLabel(tool)}</b>)}</div>}
  </section>;
}

function ChunkDecisionPanel({ rows, total }: { rows: JsonObject[]; total: number }) {
  if (!rows.length) return null;
  return <details className="knowledge-chunk-decisions">
    <summary><ListTree size={15} /><span>Chunk 决策</span><small>展示 {rows.length}/{total || rows.length}</small></summary>
    <div>{rows.map((row) => {
      const rag = (row.rag ?? {}) as JsonObject;
      const kg = (row.kg ?? {}) as JsonObject;
      const ragRisks = Object.keys((rag.risk_flags ?? {}) as JsonObject);
      const kgRisks = Object.keys((kg.risk_flags ?? {}) as JsonObject);
      const handoff = Array.isArray(row.human_handoff_reasons) ? row.human_handoff_reasons.map(String) : [];
      return <article key={text(row.chunk_id)}>
        <header><div><b>#{value(row.ordinal) + 1}</b><strong>{Array.isArray(row.heading_path) ? row.heading_path.map(String).join(' / ') : '无标题 Chunk'}</strong></div><span className={`agent-route route-${text(row.final_route)}`}>{routeLabel(text(row.final_route))}</span></header>
        <p>{value(row.token_count)} tokens · {splitStrategyLabel(text(row.split_strategy))} · 质量 {Math.round(value(row.quality_score) * 100)}%</p>
        <div className="chunk-agent-counts"><span>RAG <b>{value(rag.candidate_count)}</b> 条 · 修正 {value(rag.revision_count)} 轮</span><span>KG <b>{value(kg.candidate_count)}</b> 条 · 修正 {value(kg.revision_count)} 轮</span></div>
        {(ragRisks.length > 0 || kgRisks.length > 0 || handoff.length > 0) && <div className="chunk-risk-list">{[...new Set([...ragRisks, ...kgRisks, ...handoff])].map((risk) => <span key={risk}>{risk}</span>)}</div>}
      </article>;
    })}</div>
  </details>;
}

function AgentTimeline({ events }: { events: JsonObject[] }) {
  return <section className="knowledge-timeline agent-timeline"><header><span>智能体运行轨迹</span><small>{events.length} 条事件</small></header>{events.length ? events.map((event) => {
    const payload = (event.payload ?? {}) as JsonObject;
    const risks = (payload.risk_summary ?? {}) as JsonObject;
    return <article key={text(event.id)}><i className={`level-${text(event.level)}`} /><div><div className="agent-event-heading"><strong>{text(event.message)}</strong>{text(payload.agent) !== '—' && <b>{agentLabel(text(payload.agent))}</b>}</div><p>{nodeLabel(text(event.node))}{text(payload.tool) !== '—' ? ` · ${toolLabel(text(payload.tool))}` : ''}{text(payload.route) !== '—' ? ` · ${routeLabel(text(payload.route))}` : ''}</p>{Object.keys(risks).length > 0 && <div className="agent-event-risks">{Object.entries(risks).map(([risk, count]) => <span key={risk}>{risk} × {value(count)}</span>)}</div>}<small>{dateTime(event.created_at)}</small></div></article>;
  }) : <Empty message="任务尚未产生执行事件。" />}</section>;
}

function ExtractionResultsPanel({ request, revision }: { request: RequestJson; revision: number }) {
  const [typeFilter, setTypeFilter] = useState<'all' | 'qa' | 'triple'>('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState('');
  const params = new URLSearchParams({ item_type: typeFilter, status: statusFilter, query, page: String(page), page_size: '30' });
  const resource = useRemote<JsonObject>(request, `/knowledge/extractions?${params.toString()}`, revision);
  const rows = items(resource.data);
  const counts = (resource.data?.counts ?? {}) as JsonObject;
  const rowKeys = rows.map(extractionKey).join('|');
  useEffect(() => {
    if (!rows.some((row) => extractionKey(row) === selected)) setSelected(rows.length ? extractionKey(rows[0]) : '');
  }, [rowKeys, selected]);
  const [selectedType, selectedId] = selected.split(':');
  const detail = useRemote<JsonObject>(request, selectedId ? `/knowledge/extractions/${selectedType}/${selectedId}` : '', revision, Boolean(selectedId));
  const typeTabs = [['all', '全部', value(counts.all)], ['qa', 'QA', value(counts.qa)], ['triple', '三元组', value(counts.triple)]] as const;
  return <section className="knowledge-review-console knowledge-extraction-console">
    <article className="knowledge-queue-panel">
      <header><div><span>ALL EXTRACTIONS</span><h3>全部抽取结果</h3></div><b>{value(resource.data?.total)}</b></header>
      <p className="knowledge-extraction-note">这里展示智能体抽取出的全部 QA 和三元组，包括自动通过、待审核、已驳回与已发布数据。</p>
      <div className="knowledge-extraction-search">
        <label className="input-with-icon"><Search size={14} /><input value={query} onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="搜索问题、答案、实体或关系" /></label>
        <select aria-label="抽取状态" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
          <option value="all">全部状态</option><option value="pending">待质检</option><option value="needs_review">需人工审核</option><option value="approved">已通过</option><option value="rejected">已驳回</option><option value="published">已发布</option>
        </select>
      </div>
      <div className="knowledge-filter-tabs">{typeTabs.map(([key, label, count]) => <button className={typeFilter === key ? 'active' : ''} key={key} onClick={() => { setTypeFilter(key); setPage(1); }}>{label}<small>{count}</small></button>)}</div>
      <LoadBlock state={resource}>{rows.length ? <div className="knowledge-review-list knowledge-extraction-list">{rows.map((row) => <button key={extractionKey(row)} className={selected === extractionKey(row) ? 'selected' : ''} onClick={() => setSelected(extractionKey(row))}><div><Status value={text(row.item_type)} /><Status value={text(row.status)} /></div><strong>{text(row.display_title)}</strong><p>{text(row.display_summary)}</p><small>{text((row.source as JsonObject | undefined)?.title)} · {dateTime(row.created_at)}</small></button>)}</div> : <Empty message="当前筛选条件下没有抽取结果。" />}</LoadBlock>
      <Pager total={value(resource.data?.total)} page={page} pageSize={value(resource.data?.page_size) || 30} onChange={setPage} />
    </article>
    <aside className="knowledge-detail-panel knowledge-extraction-detail"><LoadBlock state={detail}>{detail.data ? <ExtractionDetail extraction={detail.data} /> : <Empty message="选择一条 QA 或三元组，可查看完整答案、证据和来源 Chunk。" />}</LoadBlock></aside>
  </section>;
}

function ExtractionDetail({ extraction }: { extraction: JsonObject }) {
  const candidate = (extraction.candidate ?? {}) as JsonObject;
  const chunk = (extraction.chunk ?? {}) as JsonObject;
  const source = (extraction.source ?? {}) as JsonObject;
  const build = (extraction.build ?? {}) as JsonObject;
  const manualReview = extraction.manual_review as JsonObject | null | undefined;
  const risks = Array.isArray(candidate.risk_flags) ? candidate.risk_flags.map(String) : [];
  const keywords = Array.isArray(candidate.keywords) ? candidate.keywords.map(String) : [];
  const knowledgeTypes = Array.isArray(candidate.knowledge_types) ? candidate.knowledge_types.map(String) : [];
  const headingPath = Array.isArray(chunk.heading_path) ? chunk.heading_path.map(String).join(' / ') : '无标题路径';
  const expertAssessment = (candidate.expert_assessment ?? {}) as JsonObject;
  const resolution = (candidate.resolution_metadata ?? {}) as JsonObject;
  const isQa = text(extraction.item_type) === 'qa';
  return <div className="knowledge-extraction-record">
    <div className="knowledge-detail-heading"><div><span>{isQa ? 'RAG QA EXTRACTION' : 'KG TRIPLE EXTRACTION'}</span><h3>{text(extraction.display_title)}</h3><p>{text(source.title)} · {text(source.version)} · {headingPath}</p></div><Status value={text(extraction.status)} /></div>
    <section className="knowledge-score-strip"><span><small>抽取置信度</small><b>{scoreText(candidate.extraction_confidence)}</b></span><span><small>规则评分</small><b>{scoreText(candidate.rule_score)}</b></span><span><small>专家评分</small><b>{scoreText(candidate.expert_score)}</b></span></section>
    {risks.length > 0 && <div className="knowledge-risk-flags">{risks.map((flag) => <span key={flag}>{flag}</span>)}</div>}
    {isQa ? <section className="knowledge-extraction-content"><article><span>问题</span><p>{text(candidate.question)}</p></article><article><span>答案</span><p>{text(candidate.answer)}</p></article>{(keywords.length > 0 || knowledgeTypes.length > 0) && <div className="knowledge-extraction-tags">{knowledgeTypes.map((item) => <b key={`type-${item}`}>{item}</b>)}{keywords.map((item) => <i key={`keyword-${item}`}>{item}</i>)}</div>}</section> : <section className="knowledge-triple-card"><div><span>{text(candidate.subject_type)}</span><strong>{text(candidate.subject_canonical_name)}</strong></div><b>{text(candidate.relation)}</b><div><span>{text(candidate.object_type)}</span><strong>{text(candidate.object_canonical_name)}</strong></div></section>}
    <section className={`knowledge-review-link ${manualReview ? 'attention' : 'clear'}`}><ShieldCheck size={17} /><div><strong>{manualReview ? '关联人工审核记录' : '未进入人工审核队列'}</strong><p>{manualReview ? `${STATUS_LABELS[text(manualReview.status)] ?? text(manualReview.status)} · ${(Array.isArray(manualReview.reason_codes) ? manualReview.reason_codes : []).map(String).join(' · ') || '无风险代码'}` : '这条数据仍会完整保留在抽取结果中，不因自动通过而隐藏。'}</p></div>{manualReview && <Status value={text(manualReview.priority)} />}</section>
    <section className="knowledge-evidence"><header><span>原文证据</span><small>第 {text(chunk.start_line)}–{text(chunk.end_line)} 行</small></header><pre>{text(candidate.evidence)}</pre></section>
    <dl className="knowledge-extraction-meta"><div><dt>来源文档</dt><dd>{text(source.title)} · {text(source.version)}</dd></div><div><dt>章节路径</dt><dd>{headingPath}</dd></div><div><dt>构建任务</dt><dd>{text(build.id)} · {STATUS_LABELS[text(build.status)] ?? text(build.status)}</dd></div><div><dt>抽取时间</dt><dd>{dateTime(extraction.created_at)}</dd></div></dl>
    {Object.keys(expertAssessment).length > 0 && <details className="knowledge-json-detail"><summary>专家模型评审详情</summary><pre>{JSON.stringify(expertAssessment, null, 2)}</pre></details>}
    {!isQa && Object.keys(resolution).length > 0 && <details className="knowledge-json-detail"><summary>实体消歧与融合详情</summary><pre>{JSON.stringify(resolution, null, 2)}</pre></details>}
    <section className="knowledge-evidence"><header><span>完整来源 Chunk</span><small>{value(chunk.token_count)} tokens · {text(chunk.split_strategy)}</small></header><pre>{text(chunk.content)}</pre></section>
  </div>;
}

function ReviewsPanel({ request, revision, onRefresh, onToast, canManage }: PanelProps) {
  const [typeFilter, setTypeFilter] = useState<'all' | 'qa' | 'triple' | 'chunk'>('all'); const [selected, setSelected] = useState(''); const query = typeFilter === 'all' ? '' : `&item_type=${typeFilter}`; const resource = useRemote<JsonObject>(request, `/knowledge/reviews?status=active&page=1&page_size=100${query}`, revision); const rows = items(resource.data);
  const reviewIds = rows.map((row) => text(row.id)).join('|'); useEffect(() => { if (!rows.some((row) => text(row.id) === selected)) setSelected(rows.length ? text(rows[0].id) : ''); }, [reviewIds, selected]); const detail = useRemote<JsonObject>(request, selected ? `/knowledge/reviews/${selected}` : '', revision, Boolean(selected));
  return <section className="knowledge-review-console"><article className="knowledge-queue-panel"><header><div><span>HUMAN REVIEW</span><h3>风险审核队列</h3></div><b>{value(resource.data?.total)}</b></header><div className="knowledge-filter-tabs">{([['all', '全部'], ['qa', 'QA'], ['triple', '三元组'], ['chunk', 'Chunk']] as const).map(([key, label]) => <button className={typeFilter === key ? 'active' : ''} key={key} onClick={() => setTypeFilter(key)}>{label}</button>)}</div><LoadBlock state={resource}>{rows.length ? <div className="knowledge-review-list">{rows.map((review) => <button key={text(review.id)} className={selected === text(review.id) ? 'selected' : ''} onClick={() => setSelected(text(review.id))}><div><Status value={text(review.priority)} /><Status value={text(review.item_type)} /></div><strong>{reviewTitle(review)}</strong><p>{(Array.isArray(review.reason_codes) ? review.reason_codes : []).map(String).join(' · ')}</p><small>{text((review.source as JsonObject | undefined)?.title)} · {dateTime(review.created_at)}</small></button>)}</div> : <Empty message="当前没有待人工审核的数据。" />}</LoadBlock></article><aside className="knowledge-detail-panel"><LoadBlock state={detail}>{detail.data ? <ReviewEditor review={detail.data} request={request} canManage={canManage} onDone={() => { onToast('审核结论已保存'); onRefresh(); }} /> : <Empty message="选择一条记录后，可对照原文证据进行审核。" />}</LoadBlock></aside></section>;
}

function ReviewEditor({ review, request, canManage, onDone }: { review: JsonObject; request: RequestJson; canManage: boolean; onDone: () => void }) {
  const candidate = (review.candidate ?? {}) as JsonObject;
  const chunk = (review.chunk ?? {}) as JsonObject;
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState<JsonObject>({});
  useEffect(() => { setDraft({ ...candidate }); setNote(''); setError(''); }, [review.id]);
  const submit = async (action: 'approve' | 'reject') => {
    if (note.trim().length < 3) { setError('请先填写至少 3 个字的审核意见'); return; }
    setSaving(true); setError('');
    try {
      await request(`/knowledge/reviews/${text(review.id)}`, {
        method: 'PATCH',
        body: JSON.stringify({
          action,
          version: value(review.version),
          note: note.trim(),
          corrections: action === 'approve' ? correctionPayload(text(review.item_type), draft) : {},
        }),
      });
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '保存审核结论失败');
    } finally { setSaving(false); }
  };
  return <div className="knowledge-review-editor"><div className="knowledge-detail-heading"><div><span>{text(review.item_type).toUpperCase()} REVIEW</span><h3>{reviewTitle(review)}</h3><p>{text((review.source as JsonObject | undefined)?.title)} · 第 {text(chunk.start_line)}–{text(chunk.end_line)} 行</p></div><Status value={text(review.priority)} /></div><div className="knowledge-risk-flags">{(Array.isArray(review.reason_codes) ? review.reason_codes : []).map((flag) => <span key={String(flag)}>{String(flag)}</span>)}</div>{text(review.item_type) === 'qa' && <div className="knowledge-edit-grid"><label>问题<input value={text(draft.question, '')} onChange={(event) => setDraft({ ...draft, question: event.target.value })} /></label><label>答案<textarea value={text(draft.answer, '')} onChange={(event) => setDraft({ ...draft, answer: event.target.value })} /></label><label>原文证据<textarea value={text(draft.evidence, '')} onChange={(event) => setDraft({ ...draft, evidence: event.target.value })} /></label><label>关键词<input value={(Array.isArray(draft.keywords) ? draft.keywords : []).join('、')} onChange={(event) => setDraft({ ...draft, keywords: event.target.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) })} /></label></div>}{text(review.item_type) === 'triple' && <div className="knowledge-edit-grid triple"><label>主语标准名<input value={text(draft.subject_canonical_name, '')} onChange={(event) => setDraft({ ...draft, subject_canonical_name: event.target.value })} /></label><label>主语类型<input value={text(draft.subject_type, '')} readOnly /></label><label>关系<input value={text(draft.relation, '')} readOnly /></label><label>宾语标准名<input value={text(draft.object_canonical_name, '')} onChange={(event) => setDraft({ ...draft, object_canonical_name: event.target.value })} /></label><label>宾语类型<input value={text(draft.object_type, '')} readOnly /></label><label className="wide">原文证据<textarea value={text(draft.evidence, '')} onChange={(event) => setDraft({ ...draft, evidence: event.target.value })} /></label></div>}<section className="knowledge-evidence"><header><span>来源 Chunk</span><small>{value(chunk.token_count)} tokens</small></header><pre>{text(chunk.content)}</pre></section>{canManage ? <div className="knowledge-review-actions"><label>审核意见<textarea value={note} onChange={(event) => { setNote(event.target.value); if (error) setError(''); }} placeholder="说明通过或驳回依据，至少 3 个字" /></label><small>通过会校验修订内容与原文证据；驳回不会再强制要求错误数据通过证据校验。</small>{error && <InlineError message={error} />}<div><button type="button" className="quiet-button danger" disabled={saving} onClick={() => void submit('reject')}>驳回</button><button type="button" className="primary-button" disabled={saving} onClick={() => void submit('approve')}>{saving ? '保存中…' : '通过并保存修订'}</button></div></div> : <p className="knowledge-readonly">当前账号只有查看权限。</p>}</div>;
}

function GraphPanel({ request, revision }: { request: RequestJson; revision: number }) {
  const [query, setQuery] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [nodeType, setNodeType] = useState('');
  const [relationType, setRelationType] = useState('');
  const [viewMode, setViewMode] = useState<'graph' | 'table'>('graph');
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [selectedLinkId, setSelectedLinkId] = useState('');
  const [hoveredNodeId, setHoveredNodeId] = useState('');
  const [expanded, setExpanded] = useState(false);
  const graphRef = useRef<ForceGraphMethods<GraphNodeDatum, GraphLinkDatum>>(undefined);
  const viewportRef = useRef<HTMLDivElement>(null);
  const fittedRef = useRef(false);
  const viewport = useElementSize(viewportRef, 780, 610);
  const reducedMotion = useReducedMotion();
  const resource = useRemote<JsonObject>(request, `/knowledge/graph/explore?query=${encodeURIComponent(submitted)}&limit=5000`, revision);
  const rawNodes = Array.isArray(resource.data?.nodes) ? resource.data.nodes as JsonObject[] : [];
  const rawEdges = Array.isArray(resource.data?.edges) ? resource.data.edges as JsonObject[] : [];
  const schema = (resource.data?.schema ?? {}) as JsonObject;
  const result = (resource.data?.result ?? {}) as JsonObject;
  const schemaNodeTypes = graphSchemaItems(schema.node_types);
  const schemaRelationTypes = graphSchemaItems(schema.relationship_types);
  const propertyKeys = Array.isArray(schema.property_keys) ? schema.property_keys.map(String) : [];

  const allNodes = useMemo<GraphNodeDatum[]>(() => rawNodes.map((node) => ({
    id: text(node.id),
    name: text(node.name),
    type: text(node.type),
    typeLabel: text(node.type_label, text(node.type)),
    degree: value(node.degree),
    properties: ((node.properties ?? {}) as JsonObject),
  })), [rawNodes]);
  const nodeById = useMemo(() => new Map(allNodes.map((node) => [node.id, node])), [allNodes]);
  const allLinks = useMemo<GraphLinkDatum[]>(() => rawEdges.map((edge) => ({
    id: text(edge.id),
    source: text(edge.source),
    target: text(edge.target),
    relation: text(edge.relation),
    relationKey: text(edge.relation_key, text(edge.relation)),
    evidence: text(edge.evidence, ''),
    properties: ((edge.properties ?? {}) as JsonObject),
  })), [rawEdges]);

  const filtered = useMemo(() => {
    let links = allLinks;
    if (relationType) links = links.filter((link) => link.relationKey === relationType);
    if (nodeType) links = links.filter((link) => nodeById.get(graphEndpointId(link.source))?.type === nodeType || nodeById.get(graphEndpointId(link.target))?.type === nodeType);
    if (!nodeType && !relationType) return { nodes: allNodes, links };
    const visibleIds = new Set<string>();
    links.forEach((link) => { visibleIds.add(graphEndpointId(link.source)); visibleIds.add(graphEndpointId(link.target)); });
    if (nodeType) allNodes.filter((node) => node.type === nodeType).forEach((node) => visibleIds.add(node.id));
    return { nodes: allNodes.filter((node) => visibleIds.has(node.id)), links };
  }, [allLinks, allNodes, nodeById, nodeType, relationType]);

  const graphData = useMemo(() => ({
    nodes: filtered.nodes.map((node) => ({ ...node })),
    links: filtered.links.map((link) => ({ ...link, source: graphEndpointId(link.source), target: graphEndpointId(link.target) })),
  }), [filtered]);
  const adjacency = useMemo(() => {
    const map = new Map<string, Set<string>>();
    filtered.links.forEach((link) => {
      const source = graphEndpointId(link.source); const target = graphEndpointId(link.target);
      if (!map.has(source)) map.set(source, new Set());
      if (!map.has(target)) map.set(target, new Set());
      map.get(source)?.add(target); map.get(target)?.add(source);
    });
    return map;
  }, [filtered.links]);
  const focusedNodeId = hoveredNodeId || selectedNodeId;
  const selectedNode = selectedNodeId ? nodeById.get(selectedNodeId) ?? null : null;
  const selectedLink = selectedLinkId ? allLinks.find((link) => link.id === selectedLinkId) ?? null : null;
  const detailPath = selectedNodeId
    ? `/knowledge/graph/detail?kind=node&element_id=${encodeURIComponent(selectedNodeId)}`
    : selectedLinkId
      ? `/knowledge/graph/detail?kind=relationship&element_id=${encodeURIComponent(selectedLinkId)}`
      : '';
  const detailResource = useRemote<JsonObject>(request, detailPath, revision, Boolean(detailPath));
  const nodeDetail = (detailResource.data?.node ?? {}) as JsonObject;
  const relationshipDetail = (detailResource.data?.relationship ?? {}) as JsonObject;
  const detailedNode = selectedNode && Object.keys(nodeDetail).length ? {
    ...selectedNode,
    degree: value(nodeDetail.degree) || selectedNode.degree,
    properties: ((nodeDetail.properties ?? {}) as JsonObject),
  } : selectedNode;
  const detailedLink = selectedLink && Object.keys(relationshipDetail).length ? {
    ...selectedLink,
    source: text(relationshipDetail.source, graphEndpointId(selectedLink.source)),
    target: text(relationshipDetail.target, graphEndpointId(selectedLink.target)),
    relation: text(relationshipDetail.relation, selectedLink.relation),
    relationKey: text(relationshipDetail.relation_key, selectedLink.relationKey),
    evidence: text(relationshipDetail.evidence, ''),
    properties: ((relationshipDetail.properties ?? {}) as JsonObject),
  } : selectedLink;
  const visibleNodeCounts = useMemo(() => countGraphValues(filtered.nodes.map((node) => node.type)), [filtered.nodes]);
  const visibleRelationCounts = useMemo(() => countGraphValues(filtered.links.map((link) => link.relationKey)), [filtered.links]);

  useEffect(() => {
    fittedRef.current = false;
    setSelectedNodeId((current) => current && filtered.nodes.some((node) => node.id === current) ? current : '');
    setSelectedLinkId((current) => current && filtered.links.some((link) => link.id === current) ? current : '');
  }, [filtered]);
  useEffect(() => {
    if (!expanded) return;
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setExpanded(false); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [expanded]);
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const linkForce = graphRef.current?.d3Force('link') as { distance?: (distance: number) => unknown } | undefined;
      const chargeForce = graphRef.current?.d3Force('charge') as { strength?: (strength: number) => unknown } | undefined;
      linkForce?.distance?.(34);
      chargeForce?.strength?.(-58);
      graphRef.current?.d3ReheatSimulation();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [graphData]);

  const paintNode = useCallback((node: NodeObject<GraphNodeDatum>, context: CanvasRenderingContext2D, globalScale: number) => {
    const nodeId = String(node.id);
    const radius = graphNodeRadius(node.degree ?? 0);
    const related = !focusedNodeId || nodeId === focusedNodeId || adjacency.get(focusedNodeId)?.has(nodeId);
    const selected = nodeId === selectedNodeId;
    const hovered = nodeId === hoveredNodeId;
    context.save();
    context.globalAlpha = related ? 1 : 0.13;
    if (selected || hovered) {
      context.beginPath();
      context.arc(node.x ?? 0, node.y ?? 0, radius + 3.5 / globalScale, 0, Math.PI * 2);
      context.fillStyle = selected ? 'rgba(23,100,82,.22)' : 'rgba(255,255,255,.9)';
      context.fill();
    }
    context.beginPath();
    context.arc(node.x ?? 0, node.y ?? 0, radius, 0, Math.PI * 2);
    context.fillStyle = KG_LABEL_COLORS[node.type] ?? '#8e99a5';
    context.fill();
    context.lineWidth = (selected ? 2.4 : 1.1) / globalScale;
    context.strokeStyle = selected ? '#163f35' : 'rgba(255,255,255,.94)';
    context.stroke();
    if (globalScale >= 2.35 || selected || hovered) drawGraphNodeLabel(context, node, radius, globalScale);
    context.restore();
  }, [adjacency, focusedNodeId, hoveredNodeId, selectedNodeId]);

  const paintPointerArea = useCallback((node: NodeObject<GraphNodeDatum>, color: string, context: CanvasRenderingContext2D) => {
    context.beginPath();
    context.arc(node.x ?? 0, node.y ?? 0, graphNodeRadius(node.degree ?? 0) + 3, 0, Math.PI * 2);
    context.fillStyle = color;
    context.fill();
  }, []);
  const focusNode = (node: NodeObject<GraphNodeDatum>) => {
    setSelectedNodeId(String(node.id)); setSelectedLinkId('');
    if (typeof node.x === 'number' && typeof node.y === 'number') {
      graphRef.current?.centerAt(node.x, node.y, reducedMotion ? 0 : 600);
      graphRef.current?.zoom(3.4, reducedMotion ? 0 : 600);
    }
  };
  const clearSelection = () => { setSelectedNodeId(''); setSelectedLinkId(''); };
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setSubmitted(query.trim()); setNodeType(''); setRelationType(''); clearSelection();
  };
  const cypherSummary = submitted ? `MATCH (n)-[r]-(m) WHERE n.name CONTAINS "${submitted}" RETURN n, r, m` : 'MATCH (n)-[r]->(m) RETURN n, r, m';
  const auraState = resource.loading ? 'connecting' : resource.error ? 'unavailable' : 'connected';
  const auraLabel = auraState === 'connecting' ? 'CONNECTING' : auraState === 'unavailable' ? 'UNAVAILABLE' : 'CONNECTED';

  return <section className={`knowledge-panel graph neo4j-workbench ${expanded ? 'is-expanded' : ''}`}>
    <header className="graph-workbench-header">
      <div><span className={`aura-status ${auraState}`}><i />NEO4J AURA · {auraLabel}</span><h3>家蚕疾病知识图谱</h3></div>
      <form className="graph-search" onSubmit={submitSearch}><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索疾病、症状、病原或防治措施" /><button type="submit">查询</button>{submitted && <button type="button" className="graph-clear-search" onClick={() => { setQuery(''); setSubmitted(''); }}><X size={14} />清除</button>}</form>
    </header>
    <LoadBlock state={resource}>{allNodes.length ? <div className="graph-studio-shell">
      <aside className="graph-schema-panel">
        <div className="graph-side-heading"><div><span>DATABASE INFORMATION</span><strong>数据库结构</strong></div><Database size={18} /></div>
        <GraphFilterGroup title="节点" total={value(schema.total_nodes)} items={schemaNodeTypes} active={nodeType} colorized onSelect={(key) => { setNodeType((current) => current === key ? '' : key); clearSelection(); }} />
        <GraphFilterGroup title="关系" total={value(schema.total_relationships)} items={schemaRelationTypes} active={relationType} onSelect={(key) => { setRelationType((current) => current === key ? '' : key); clearSelection(); }} />
        <section className="graph-property-keys"><h4>属性键 <small>{propertyKeys.length}</small></h4><div>{propertyKeys.slice(0, 18).map((key) => <span key={key}>{key}</span>)}</div>{propertyKeys.length > 18 && <details><summary>显示其余 {propertyKeys.length - 18} 项</summary><div>{propertyKeys.slice(18).map((key) => <span key={key}>{key}</span>)}</div></details>}</section>
      </aside>
      <main className="graph-result-panel">
        <div className="graph-query-row"><code><b>$</b> {cypherSummary}</code><div className="graph-view-tabs"><button className={viewMode === 'graph' ? 'active' : ''} onClick={() => setViewMode('graph')}><Network size={13} />图谱</button><button className={viewMode === 'table' ? 'active' : ''} onClick={() => setViewMode('table')}><Table2 size={13} />表格</button></div></div>
        {Boolean(result.truncated) && <div className="graph-limit-warning"><AlertTriangle size={14} />匹配到 {value(result.matching_relationships).toLocaleString('zh-CN')} 条关系，本次显示前 {value(result.relationship_count).toLocaleString('zh-CN')} 条。</div>}
        {viewMode === 'graph' ? <div className="knowledge-graph-canvas" ref={viewportRef}>
          <ForceGraph2D<GraphNodeDatum, GraphLinkDatum>
            ref={graphRef}
            graphData={graphData}
            width={viewport.width}
            height={viewport.height}
            backgroundColor="#f5f7f7"
            nodeId="id"
            nodeVal={(node) => Math.max(1, Math.log2((node.degree ?? 0) + 2))}
            nodeLabel={(node) => `<div class="graph-tooltip"><b>${escapeHtml(node.name)}</b><span>${escapeHtml(node.typeLabel)} · ${node.degree ?? 0} 条连接</span></div>`}
            nodeCanvasObjectMode={() => 'replace'}
            nodeCanvasObject={paintNode}
            nodePointerAreaPaint={paintPointerArea}
            linkSource="source"
            linkTarget="target"
            linkColor={(link) => graphLinkColor(link, focusedNodeId, selectedLinkId)}
            linkWidth={(link) => link.id === selectedLinkId ? 2.2 : focusedNodeId && graphLinkTouches(link, focusedNodeId) ? 1.25 : 0.55}
            linkDirectionalArrowLength={(link) => link.id === selectedLinkId ? 5 : 3}
            linkDirectionalArrowRelPos={0.82}
            linkDirectionalArrowColor={(link) => graphLinkColor(link, focusedNodeId, selectedLinkId)}
            linkLabel={(link) => `<div class="graph-tooltip"><b>${escapeHtml(link.relation)}</b><span>${escapeHtml(graphNodeName(link.source, nodeById))} → ${escapeHtml(graphNodeName(link.target, nodeById))}</span></div>`}
            onNodeClick={focusNode}
            onNodeHover={(node) => setHoveredNodeId(node ? String(node.id) : '')}
            onLinkClick={(link) => { setSelectedLinkId(String(link.id)); setSelectedNodeId(''); }}
            onBackgroundClick={clearSelection}
            minZoom={0.08}
            maxZoom={12}
            warmupTicks={reducedMotion ? 1 : 70}
            cooldownTicks={reducedMotion ? 1 : 180}
            cooldownTime={reducedMotion ? 20 : 4000}
            d3VelocityDecay={0.28}
            onEngineStop={() => { if (!fittedRef.current) { fittedRef.current = true; graphRef.current?.zoomToFit(reducedMotion ? 0 : 650, 42); } }}
          />
          <div className="graph-canvas-stats"><b>{filtered.nodes.length.toLocaleString('zh-CN')}</b> 节点 <i /> <b>{filtered.links.length.toLocaleString('zh-CN')}</b> 关系</div>
          <div className="graph-canvas-controls"><button title="放大" onClick={() => graphRef.current?.zoom(graphRef.current.zoom() * 1.35, 220)}><ZoomIn size={16} /></button><button title="缩小" onClick={() => graphRef.current?.zoom(graphRef.current.zoom() / 1.35, 220)}><ZoomOut size={16} /></button><button title="适应画布" onClick={() => graphRef.current?.zoomToFit(500, 38)}><Network size={16} /></button><button title="重新布局" onClick={() => { fittedRef.current = false; graphRef.current?.d3ReheatSimulation(); }}><RotateCcw size={16} /></button><button title={expanded ? '退出全屏' : '全屏查看'} onClick={() => setExpanded((current) => !current)}>{expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button></div>
        </div> : <GraphRelationshipTable links={filtered.links} nodes={nodeById} />}
      </main>
      <aside className="graph-overview-panel">
        <div className="graph-side-heading"><div><span>RESULTS OVERVIEW</span><strong>{selectedNode || selectedLink ? '所选内容' : '结果概览'}</strong></div>{(selectedNode || selectedLink) && <button title="关闭详情" onClick={clearSelection}><X size={15} /></button>}</div>
        {selectedNode || selectedLink ? <LoadBlock state={detailResource}>{detailedNode ? <GraphNodeDetail node={detailedNode} /> : detailedLink ? <GraphLinkDetail link={detailedLink} nodes={nodeById} /> : null}</LoadBlock> : <>
          <GraphResultCounts title="节点" total={filtered.nodes.length} items={schemaNodeTypes} counts={visibleNodeCounts} colorized active={nodeType} onSelect={setNodeType} />
          <GraphResultCounts title="关系" total={filtered.links.length} items={schemaRelationTypes} counts={visibleRelationCounts} active={relationType} onSelect={setRelationType} />
          <div className="graph-overview-hint"><span>交互提示</span><p>滚轮缩放，拖动画布，点击节点查看属性；选择左侧标签可观察类型之间的连接。</p></div>
        </>}
      </aside>
    </div> : <Empty message={submitted ? `没有找到与“${submitted}”关联的实体或关系，请调整关键词后重试。` : "Neo4j Aura 中还没有可展示的关系。发布通过审核的 KG 三元组后即可形成全图。"} />}</LoadBlock>
  </section>;
}

function GraphFilterGroup({ title, total, items, active, colorized = false, onSelect }: { title: string; total: number; items: GraphSchemaItem[]; active: string; colorized?: boolean; onSelect: (key: string) => void }) {
  return <section className="graph-filter-group"><h4>{title} <small>({total.toLocaleString('zh-CN')})</small></h4><div>{items.map((item) => <button key={item.key} className={active === item.key ? 'active' : ''} style={colorized ? { '--chip-color': KG_LABEL_COLORS[item.key] ?? '#82909a' } as CSSProperties : undefined} onClick={() => onSelect(item.key)}>{colorized && <i />}{item.label}<b>{item.count}</b></button>)}</div></section>;
}

function GraphResultCounts({ title, total, items, counts, active, colorized = false, onSelect }: { title: string; total: number; items: GraphSchemaItem[]; counts: Map<string, number>; active: string; colorized?: boolean; onSelect: (key: string) => void }) {
  return <section className="graph-result-counts"><h4>{title} <b>{total.toLocaleString('zh-CN')}</b></h4><div>{items.filter((item) => counts.has(item.key)).map((item) => <button key={item.key} className={active === item.key ? 'active' : ''} style={colorized ? { '--chip-color': KG_LABEL_COLORS[item.key] ?? '#82909a' } as CSSProperties : undefined} onClick={() => onSelect(active === item.key ? '' : item.key)}>{colorized && <i />}{item.label} <b>{counts.get(item.key)}</b></button>)}</div></section>;
}

function GraphNodeDetail({ node }: { node: GraphNodeDatum }) {
  return <div className="graph-selection-detail"><span className="graph-detail-type" style={{ '--detail-color': KG_LABEL_COLORS[node.type] ?? '#82909a' } as CSSProperties}><i />{node.typeLabel}</span><h4>{node.name}</h4><p>{node.degree} 条图谱连接</p><GraphPropertyList properties={node.properties} /></div>;
}

function GraphLinkDetail({ link, nodes }: { link: GraphLinkDatum; nodes: Map<string, GraphNodeDatum> }) {
  return <div className="graph-selection-detail relation"><span className="graph-detail-type"><Network size={13} />{link.relation}</span><h4>{graphNodeName(link.source, nodes)}</h4><div className="graph-relation-arrow"><span>{link.relation}</span>→</div><h4>{graphNodeName(link.target, nodes)}</h4>{link.evidence && <blockquote>{link.evidence}</blockquote>}<GraphPropertyList properties={link.properties} /></div>;
}

function GraphPropertyList({ properties }: { properties: JsonObject }) {
  const entries = Object.entries(properties).filter(([, entry]) => entry !== null && entry !== '' && entry !== undefined);
  if (!entries.length) return <p className="graph-no-properties">没有附加属性</p>;
  return <dl className="graph-property-list">{entries.map(([key, entry]) => <div key={key}><dt>{key}</dt><dd>{formatGraphProperty(entry)}</dd></div>)}</dl>;
}

function GraphRelationshipTable({ links, nodes }: { links: GraphLinkDatum[]; nodes: Map<string, GraphNodeDatum> }) {
  const visible = links.slice(0, 1000);
  return <div className="graph-table-view"><header>关系结果 <b>{links.length.toLocaleString('zh-CN')}</b>{links.length > visible.length && <span>为保证页面性能，表格显示前 {visible.length.toLocaleString('zh-CN')} 条；图谱仍展示全部结果。</span>}</header><div><table><thead><tr><th>起点</th><th>关系</th><th>终点</th><th>证据</th></tr></thead><tbody>{visible.map((link) => <tr key={link.id}><td><i style={{ background: KG_LABEL_COLORS[nodes.get(graphEndpointId(link.source))?.type ?? ''] ?? '#82909a' }} />{graphNodeName(link.source, nodes)}</td><td><span>{link.relation}</span></td><td><i style={{ background: KG_LABEL_COLORS[nodes.get(graphEndpointId(link.target))?.type ?? ''] ?? '#82909a' }} />{graphNodeName(link.target, nodes)}</td><td>{link.evidence || '—'}</td></tr>)}</tbody></table></div></div>;
}

function useElementSize<T extends HTMLElement>(ref: RefObject<T | null>, fallbackWidth: number, fallbackHeight: number) {
  const [size, setSize] = useState({ width: fallbackWidth, height: fallbackHeight });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => setSize({ width: Math.max(320, element.clientWidth), height: Math.max(420, element.clientHeight) });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [fallbackHeight, fallbackWidth, ref]);
  return size;
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(media.matches);
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);
  return reduced;
}

function graphSchemaItems(input: unknown): GraphSchemaItem[] {
  if (!Array.isArray(input)) return [];
  return input.map((entry) => {
    const item = (entry ?? {}) as JsonObject;
    return { key: text(item.key), label: text(item.label, text(item.key)), count: value(item.count) };
  });
}

function graphEndpointId(endpoint: string | NodeObject<GraphNodeDatum>): string {
  return typeof endpoint === 'object' && endpoint !== null ? String(endpoint.id) : String(endpoint);
}

function graphNodeName(endpoint: string | NodeObject<GraphNodeDatum>, nodes: Map<string, GraphNodeDatum>): string {
  if (typeof endpoint === 'object' && endpoint !== null && endpoint.name) return endpoint.name;
  return nodes.get(graphEndpointId(endpoint))?.name ?? graphEndpointId(endpoint);
}

function countGraphValues(values: string[]): Map<string, number> {
  const counts = new Map<string, number>();
  values.forEach((entry) => counts.set(entry, (counts.get(entry) ?? 0) + 1));
  return counts;
}

function graphNodeRadius(degree: number): number {
  return 3.8 + Math.min(5.2, Math.log2(Math.max(1, degree) + 1) * 0.92);
}

function drawGraphNodeLabel(context: CanvasRenderingContext2D, node: NodeObject<GraphNodeDatum>, radius: number, globalScale: number) {
  const name = node.name.length > 22 ? `${node.name.slice(0, 21)}…` : node.name;
  const fontSize = 11 / globalScale;
  const paddingX = 4.5 / globalScale;
  const paddingY = 2.5 / globalScale;
  const x = node.x ?? 0;
  const y = (node.y ?? 0) + radius + 8 / globalScale;
  context.font = `600 ${fontSize}px "Microsoft YaHei", sans-serif`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  const width = context.measureText(name).width + paddingX * 2;
  context.fillStyle = 'rgba(26,38,35,.88)';
  context.fillRect(x - width / 2, y - fontSize / 2 - paddingY, width, fontSize + paddingY * 2);
  context.fillStyle = '#fff';
  context.fillText(name, x, y);
}

function graphLinkTouches(link: LinkObject<GraphNodeDatum, GraphLinkDatum> | GraphLinkDatum, nodeId: string): boolean {
  return graphEndpointId(link.source as string | NodeObject<GraphNodeDatum>) === nodeId || graphEndpointId(link.target as string | NodeObject<GraphNodeDatum>) === nodeId;
}

function graphLinkColor(link: LinkObject<GraphNodeDatum, GraphLinkDatum> | GraphLinkDatum, focusedNodeId: string, selectedLinkId: string): string {
  if (String(link.id) === selectedLinkId) return 'rgba(23,100,82,.95)';
  if (focusedNodeId) return graphLinkTouches(link, focusedNodeId) ? 'rgba(78,103,96,.82)' : 'rgba(129,145,151,.055)';
  return 'rgba(116,133,139,.28)';
}

function escapeHtml(input: string): string {
  return input.replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character] ?? character);
}

function formatGraphProperty(input: unknown): string {
  if (Array.isArray(input)) return input.map((entry) => typeof entry === 'object' ? JSON.stringify(entry) : String(entry)).join('、');
  if (input && typeof input === 'object') return JSON.stringify(input, null, 2);
  return String(input);
}

function UploadDialog({ request, onClose, onDone, onToast }: { request: RequestJson; onClose: () => void; onDone: () => void; onToast: (message: string) => void }) {
  const [saving, setSaving] = useState(false); const [error, setError] = useState(''); const submit = async (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); setSaving(true); setError(''); const form = new FormData(event.currentTarget); try { await request('/knowledge/sources/upload', { method: 'POST', body: form }); onToast('文档已上传并登记版本'); onDone(); } catch (reason) { setError(reason instanceof Error ? reason.message : '上传失败'); } finally { setSaving(false); } };
  return <Dialog title="上传知识文档" onClose={onClose}><form className="knowledge-dialog-form" onSubmit={submit}><label>选择文件<input name="file" type="file" accept=".md,.markdown,.pdf,.doc,.docx,.ppt,.pptx,.png,.jpg,.jpeg" required /><small className="knowledge-form-hint">支持 Markdown、PDF、Word、PPT 和常见图片；非 Markdown 文件将交由 MinerU 异步转写，并保留标题、段落与表格结构。</small></label><label>知识源名称<input name="title" minLength={2} required placeholder="例如：家蚕病理学" /></label><label>版本号<input name="version" defaultValue="v1" required /></label><label>授权与用途说明<textarea name="license_note" placeholder="记录资料来源或内部使用约束" /></label><label>上传理由<input name="reason" minLength={3} required defaultValue="新增养蚕领域知识文献" /></label>{error && <InlineError message={error} />}<footer><button type="button" className="quiet-button" onClick={onClose}>取消</button><button className="primary-button" disabled={saving}>{saving ? '上传并登记中…' : '上传文档'}</button></footer></form></Dialog>;
}

function DeleteSourceDialog({ source, request, onClose, onDone, onToast }: { source: JsonObject; request: RequestJson; onClose: () => void; onDone: () => void; onToast: (message: string) => void }) {
  const sourceTitle = text(source.title, '');
  const [confirmation, setConfirmation] = useState('');
  const [reason, setReason] = useState('删除该文档及其全部派生知识数据');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (confirmation.trim() !== sourceTitle) { setError('请输入完整文档名称进行确认'); return; }
    setSaving(true); setError('');
    try {
      const result = await request(`/knowledge/sources/${text(source.id)}`, { method: 'DELETE', body: JSON.stringify({ confirmation_title: confirmation.trim(), reason: reason.trim() }) }) as JsonObject;
      const deleted = (result.deleted ?? {}) as JsonObject;
      onToast(`文档已删除：QA ${value(deleted.qa_items)} 条，三元组 ${value(deleted.triples)} 条`);
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '删除文档失败');
    } finally { setSaving(false); }
  };
  return <Dialog title={`删除文档 · ${sourceTitle}`} onClose={onClose}><form className="knowledge-dialog-form knowledge-delete-form" onSubmit={submit}><div className="knowledge-delete-warning"><AlertTriangle size={19} /><div><strong>此操作不可撤销</strong><p>将同时删除文档文件、所有版本、构建任务、Chunk、QA、三元组、人工审核记录和发布记录，并清理 Qdrant、OpenSearch 与 Neo4j Aura 中由该文档写入的数据。</p></div></div><label>输入文档名称确认删除<input value={confirmation} onChange={(event) => setConfirmation(event.target.value)} placeholder={sourceTitle} autoFocus /></label><label>删除原因<textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} required /></label>{error && <InlineError message={error} />}<footer><button type="button" className="quiet-button" onClick={onClose}>取消</button><button className="danger-confirm-button" disabled={saving || confirmation.trim() !== sourceTitle || reason.trim().length < 3}>{saving ? '正在级联清理…' : '永久删除全部数据'}</button></footer></form></Dialog>;
}

function BuildDialog({ source, request, onClose, onDone, onToast }: { source: JsonObject; request: RequestJson; onClose: () => void; onDone: () => void; onToast: (message: string) => void }) {
  const [rag, setRag] = useState(true); const [kg, setKg] = useState(true); const [reason, setReason] = useState('构建首版养蚕专业知识库'); const [saving, setSaving] = useState(false); const [error, setError] = useState(''); const submit = async (event: FormEvent) => { event.preventDefault(); const targets = [rag ? 'rag' : '', kg ? 'kg' : ''].filter(Boolean); if (!targets.length) { setError('至少选择一个构建目标'); return; } setSaving(true); try { await request(`/knowledge/sources/${text(source.id)}/build`, { method: 'POST', body: JSON.stringify({ targets, reason }) }); onToast('RAG/KG 构建任务已进入队列'); onDone(); } catch (cause) { setError(cause instanceof Error ? cause.message : '创建任务失败'); } finally { setSaving(false); } };
  return <Dialog title={`构建 · ${text(source.title)}`} onClose={onClose}><form className="knowledge-dialog-form" onSubmit={submit}><div className="knowledge-target-grid"><label className={rag ? 'selected' : ''}><input type="checkbox" checked={rag} onChange={(event) => setRag(event.target.checked)} /><Database size={18} /><span><strong>RAG 文档智能体</strong><small>QA 抽取、质检、Qdrant 与 BM25</small></span></label><label className={kg ? 'selected' : ''}><input type="checkbox" checked={kg} onChange={(event) => setKg(event.target.checked)} /><GitBranch size={18} /><span><strong>KG 构建智能体</strong><small>Schema 抽取、消歧、融合与 Neo4j Aura</small></span></label></div><label>构建理由<input value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} required /></label>{error && <InlineError message={error} />}<footer><button type="button" className="quiet-button" onClick={onClose}>取消</button><button className="primary-button" disabled={saving}>{saving ? '创建中…' : '开始构建'}</button></footer></form></Dialog>;
}

function ReasonActionDialog({ title, description, actionLabel, defaultReason = '', danger = false, onClose, onSubmit }: { title: string; description: string; actionLabel: string; defaultReason?: string; danger?: boolean; onClose: () => void; onSubmit: (reason: string) => Promise<void> }) { const [reason, setReason] = useState(defaultReason); const [saving, setSaving] = useState(false); const [error, setError] = useState(''); return <Dialog title={title} onClose={onClose}><form className="knowledge-dialog-form" onSubmit={(event) => { event.preventDefault(); setError(''); setSaving(true); void onSubmit(reason.trim()).catch((cause) => setError(cause instanceof Error ? cause.message : '操作失败')).finally(() => setSaving(false)); }}><p>{description}</p><label>操作理由<input value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} required /></label>{error && <InlineError message={error} />}<footer><button type="button" className="quiet-button" onClick={onClose}>取消</button><button className={danger ? 'danger-confirm-button' : 'primary-button'} disabled={saving || reason.trim().length < 3}>{saving ? '提交中…' : actionLabel}</button></footer></form></Dialog>; }
function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) { return <div className="modal-backdrop" onMouseDown={onClose}><section className="modal modal-workbench knowledge-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}><header><div><span className="modal-kicker">KNOWLEDGE FACTORY</span><h2>{title}</h2></div><button aria-label="关闭" onClick={onClose}><X size={18} /></button></header><div className="modal-content">{children}</div></section></div>; }

function useRemote<T>(request: RequestJson, path: string, revision: number, enabled = true): LoadState<T> { const [state, setState] = useState<LoadState<T>>({ data: null, loading: enabled, error: '' }); useEffect(() => { let cancelled = false; if (!enabled || !path) { setState({ data: null, loading: false, error: '' }); return () => { cancelled = true; }; } setState((current) => ({ ...current, loading: true, error: '' })); void request(path).then((data) => { if (!cancelled) setState({ data: data as T, loading: false, error: '' }); }).catch((error) => { if (!cancelled) setState({ data: null, loading: false, error: error instanceof Error ? error.message : '加载失败' }); }); return () => { cancelled = true; }; }, [enabled, path, request, revision]); return state; }
function LoadBlock<T>({ state, children }: { state: LoadState<T>; children: ReactNode }) { if (state.loading) return <div className="loading-state"><RefreshCcw size={17} />正在读取知识数据…</div>; if (state.error) return <InlineError message={state.error} />; return <>{children}</>; }
function InlineError({ message }: { message: string }) { return <div className="error-state"><AlertTriangle size={18} /><div><strong>暂时无法完成</strong><span>{message}</span></div></div>; }
function Empty({ message }: { message: string }) { return <div className="knowledge-empty"><BookOpenCheck size={24} /><p>{message}</p></div>; }
function Status({ value: status }: { value: string }) { return <span className={`status status-${status.replace(/[^a-zA-Z0-9_-]/g, '')}`}>{STATUS_LABELS[status] ?? status}</span>; }
function Pager({ total, page, pageSize, onChange }: { total: number; page: number; pageSize: number; onChange: (page: number) => void }) { const pages = Math.max(1, Math.ceil(total / Math.max(1, pageSize))); if (pages <= 1) return null; return <footer className="table-pagination"><span>共 {total} 项 · 第 {page}/{pages} 页</span><div><button className="quiet-button" disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</button><button className="quiet-button" disabled={page >= pages} onClick={() => onChange(page + 1)}>下一页</button></div></footer>; }
function items(data: JsonObject | null): JsonObject[] { return Array.isArray(data?.items) ? data.items as JsonObject[] : []; }
function text(input: unknown, fallback = '—'): string { return input === null || input === undefined || input === '' ? fallback : String(input); }
function value(input: unknown): number { const parsed = Number(input); return Number.isFinite(parsed) ? parsed : 0; }
function dateTime(input: unknown): string { if (!input) return '—'; const parsed = new Date(String(input)); return Number.isNaN(parsed.valueOf()) ? String(input) : parsed.toLocaleString('zh-CN', { hour12: false }); }
function extractionKey(item: JsonObject): string { return `${text(item.item_type, '')}:${text(item.id, '')}`; }
function scoreText(input: unknown): string { if (input === null || input === undefined || input === '') return '—'; const score = Number(input); if (!Number.isFinite(score)) return '—'; return `${Math.round((score <= 1 ? score * 100 : score) * 10) / 10}%`; }
function agentLabel(agent: string): string { return ({ orchestrator: '总控规划智能体', rag: 'RAG 文档智能体', kg: 'KG 图谱智能体', publisher: '知识发布智能体' } as Record<string, string>)[agent] ?? agent; }
function routeLabel(route: string): string { return ({ waiting: '等待决策', execute: '执行计划', revise: '反思修正', reevaluate: '重新质检', expert: '专家评审', persist: '质量通过', human_review: '转人工审核', approved: '自动通过', skipped: '无需抽取', ready_to_publish: '等待发布', rag: '进入 RAG', kg: '进入 KG', finalize: '汇总结果' } as Record<string, string>)[route] ?? route; }
function toolLabel(tool: string): string { return ({ knowledge_storage: 'Markdown 存储', mineru: 'MinerU', adaptive_markdown_chunker: '自适应切分器', qa_model: 'QA 模型', kg_model: 'KG 模型', expert_model: '专家模型', silkworm_glossary: '养蚕领域词表', postgresql: 'PostgreSQL', qdrant: 'Qdrant', opensearch: 'OpenSearch', neo4j: 'Neo4j Aura' } as Record<string, string>)[tool] ?? tool; }
function splitStrategyLabel(strategy: string): string { return ({ llm_then_deterministic_fallback: '大模型语义复切，失败时规则兜底', h3_complete: 'H3 完整知识章', h2_complete: 'H2 完整知识章', h1_complete: 'H1 完整知识章', semantic_pending: '等待语义复切', semantic_llm: '大模型语义复切', semantic_fallback: '规则语义兜底' } as Record<string, string>)[strategy] ?? strategy; }
function nodeLabel(node: string): string { return ({ queued: '等待 Worker 接管', load_document: '读取并解析文档', plan_document: '分析文档并制定计划', adaptive_chunk: '自适应切分', persist_chunks: '保存追溯 Chunk', rag_extract: 'RAG 首轮抽取', rag_evaluate: 'RAG 质量判断', rag_revise: 'RAG 反思修正', rag_expert_review: 'RAG 专家评审', rag_quality: 'RAG 结果入库', kg_extract: 'KG 首轮抽取', kg_evaluate: 'KG 质量判断', kg_resolve: 'KG 消歧修正', kg_expert_review: 'KG 专家评审', kg_quality: 'KG 结果入库', finalize: '汇总并决定下一步', awaiting_review: '等待人工审核', ready_to_publish: '等待发布', publish_queued: '发布任务排队', published: '发布完成' } as Record<string, string>)[node] ?? node; }
function reviewTitle(review: JsonObject): string { const candidate = (review.candidate ?? {}) as JsonObject; if (text(review.item_type) === 'qa') return text(candidate.question, '待审核问答'); if (text(review.item_type) === 'triple') return `${text(candidate.subject_canonical_name)} —${text(candidate.relation)}→ ${text(candidate.object_canonical_name)}`; return 'Chunk 抽取异常'; }
function correctionPayload(type: string, draft: JsonObject): JsonObject { if (type === 'qa') return { question: draft.question, answer: draft.answer, evidence: draft.evidence, keywords: draft.keywords, knowledge_types: draft.knowledge_types }; if (type === 'triple') return { subject_name: draft.subject_name, subject_type: draft.subject_type, subject_canonical_name: draft.subject_canonical_name, relation: draft.relation, object_name: draft.object_name, object_type: draft.object_type, object_canonical_name: draft.object_canonical_name, evidence: draft.evidence }; return {}; }

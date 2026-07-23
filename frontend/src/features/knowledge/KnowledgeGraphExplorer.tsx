import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
  type RefObject,
} from 'react';
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from 'react-force-graph-2d';
import {
  AlertTriangle,
  BookOpen,
  ExternalLink,
  GitBranch,
  LoaderCircle,
  Maximize2,
  MousePointer2,
  Minimize2,
  Network,
  RefreshCcw,
  RotateCcw,
  Search,
  ShieldCheck,
  Table2,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';


type KnowledgeGraphRequest = (path: string) => Promise<unknown>;

type Props = {
  authenticated: boolean;
  darkMode: boolean;
  reducedMotion: boolean;
  request: KnowledgeGraphRequest;
  onRequireAuth: () => void;
};

type GraphSchemaItem = {
  key: string;
  label: string;
  count: number;
};

type ApiKnowledgeGraphNode = {
  id: string;
  name: string;
  type: string;
  type_label: string;
  degree: number;
};

type ApiKnowledgeGraphEdge = {
  id: string;
  source: string;
  target: string;
  relation: string;
  relation_key: string;
  has_evidence: boolean;
};

type KnowledgeGraphSource = {
  title: string;
  version: string | null;
  url: string | null;
  published_at: string | null;
};

type KnowledgeGraphResponse = {
  available: boolean;
  reason: string | null;
  nodes: ApiKnowledgeGraphNode[];
  edges: ApiKnowledgeGraphEdge[];
  schema: {
    total_nodes: number;
    total_relationships: number;
    node_types: GraphSchemaItem[];
    relationship_types: GraphSchemaItem[];
  };
  result: {
    node_count: number;
    relationship_count: number;
    matching_relationships: number;
    limit: number;
    truncated: boolean;
    query: string;
  };
  snapshot: {
    scope: 'curated' | 'curated_and_published';
    scope_label: string;
    source_count: number;
    sources: KnowledgeGraphSource[];
  };
};

type KnowledgeGraphNodeDetail = {
  id: string;
  name: string;
  type: string;
  type_label: string;
  degree: number;
  description: string | null;
  aliases: string[];
  english_label: string | null;
  evidence: string | null;
  source_documents: string[];
  confidence: string | number | null;
  review_status: string | null;
};

type KnowledgeGraphRelationshipDetail = {
  id: string;
  source: string;
  source_name: string;
  target: string;
  target_name: string;
  relation: string;
  relation_key: string;
  evidence: string | null;
  source_documents: string[];
  confidence: string | number | null;
  review_status: string | null;
  source_record: KnowledgeGraphSource | null;
};

type KnowledgeGraphDetailResponse = {
  kind: 'node' | 'relationship';
  node: KnowledgeGraphNodeDetail | null;
  relationship: KnowledgeGraphRelationshipDetail | null;
};

type GraphNodeDatum = ApiKnowledgeGraphNode;
type GraphLinkDatum = Omit<ApiKnowledgeGraphEdge, 'source' | 'target'> & {
  source: string | NodeObject<GraphNodeDatum>;
  target: string | NodeObject<GraphNodeDatum>;
  curvature?: number;
};

const NODE_COLORS: Record<string, string> = {
  Disease: '#ff5b57',
  DiseaseCategory: '#7165e3',
  Cause: '#ff9238',
  Symptom: '#e85d9b',
  Lesion: '#d9642c',
  Part: '#1aa6b7',
  Route: '#17a985',
  Condition: '#47a84a',
  Stage: '#3887d6',
  Diagnosis: '#6652bd',
  Measure: '#2f9954',
};

const EMPTY_GRAPH: KnowledgeGraphResponse = {
  available: false,
  reason: null,
  nodes: [],
  edges: [],
  schema: { total_nodes: 0, total_relationships: 0, node_types: [], relationship_types: [] },
  result: { node_count: 0, relationship_count: 0, matching_relationships: 0, limit: 5000, truncated: false, query: '' },
  snapshot: { scope: 'curated', scope_label: 'Neo4j 受控图谱', source_count: 0, sources: [] },
};


export function KnowledgeGraphExplorer({ authenticated, darkMode, reducedMotion, request, onRequireAuth }: Props) {
  const requestRef = useRef(request);
  const graphRef = useRef<ForceGraphMethods<GraphNodeDatum, GraphLinkDatum>>(undefined);
  const viewportRef = useRef<HTMLDivElement>(null);
  const fittedRef = useRef(false);
  const [query, setQuery] = useState('');
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<KnowledgeGraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [nodeType, setNodeType] = useState('');
  const [relationshipType, setRelationshipType] = useState('');
  const [viewMode, setViewMode] = useState<'graph' | 'table'>('graph');
  const [selectedNodeId, setSelectedNodeId] = useState('');
  const [selectedEdgeId, setSelectedEdgeId] = useState('');
  const [hoveredNodeId, setHoveredNodeId] = useState('');
  const [visibleNodeIds, setVisibleNodeIds] = useState<Set<string>>(new Set());
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<KnowledgeGraphDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [expanded, setExpanded] = useState(false);
  const viewport = useElementSize(viewportRef, 760, 610, Boolean(data && viewMode === 'graph'));

  useEffect(() => {
    requestRef.current = request;
  }, [request]);

  useEffect(() => {
    if (!authenticated) {
      setData(null);
      setLoading(false);
      setError('');
      return;
    }
    let ignored = false;
    setLoading(true);
    setError('');
    const path = `/knowledge/graph?query=${encodeURIComponent(submittedQuery)}&limit=5000`;
    void requestRef.current(path)
      .then((payload) => {
        if (ignored) return;
        setData(payload as KnowledgeGraphResponse);
      })
      .catch((reason) => {
        if (ignored) return;
        setError(reason instanceof Error ? reason.message : '图谱加载失败，请稍后重试');
      })
      .finally(() => {
        if (!ignored) setLoading(false);
      });
    return () => {
      ignored = true;
    };
  }, [authenticated, revision, submittedQuery]);

  const graph = data ?? EMPTY_GRAPH;
  const allNodes = useMemo<GraphNodeDatum[]>(() => graph.nodes.map((node) => ({ ...node })), [graph.nodes]);
  const nodeById = useMemo(() => new Map(allNodes.map((node) => [node.id, node])), [allNodes]);
  const allLinks = useMemo<GraphLinkDatum[]>(
    () => graph.edges.map((edge) => ({ ...edge, source: edge.source, target: edge.target })),
    [graph.edges],
  );

  const filtered = useMemo(() => {
    let links = allLinks;
    if (relationshipType) links = links.filter((link) => link.relation_key === relationshipType);
    if (nodeType) {
      links = links.filter((link) => {
        const source = nodeById.get(graphEndpointId(link.source));
        const target = nodeById.get(graphEndpointId(link.target));
        return source?.type === nodeType || target?.type === nodeType;
      });
    }
    if (!nodeType && !relationshipType) return { nodes: allNodes, links };
    // A type filter is a complete catalogue view: even an isolated entity of
    // that type must remain visible, otherwise the number in the left rail
    // would not agree with what the user can inspect on the canvas.
    const visibleNodeIds = new Set<string>(
      nodeType
        ? allNodes.filter((node) => node.type === nodeType).map((node) => node.id)
        : [],
    );
    links.forEach((link) => {
      visibleNodeIds.add(graphEndpointId(link.source));
      visibleNodeIds.add(graphEndpointId(link.target));
    });
    return { nodes: allNodes.filter((node) => visibleNodeIds.has(node.id)), links };
  }, [allLinks, allNodes, nodeById, nodeType, relationshipType]);

  const overviewMode = !submittedQuery && !nodeType && !relationshipType;
  const completeFilterMode = Boolean(nodeType || relationshipType);

  const initialVisibleNodeIds = useMemo(
    () => overviewMode || completeFilterMode ? new Set<string>() : buildInitialVisibleNodeIds(filtered.nodes, filtered.links, submittedQuery),
    [completeFilterMode, filtered.links, filtered.nodes, overviewMode, submittedQuery],
  );

  useEffect(() => {
    setVisibleNodeIds(new Set(initialVisibleNodeIds));
    setExpandedNodeIds(new Set());
    setSelectedNodeId('');
    setSelectedEdgeId('');
    fittedRef.current = false;
  }, [initialVisibleNodeIds]);

  const scene = useMemo(() => {
    // The left "knowledge thread" filters are explicit requests for the
    // complete matching subgraph. Search remains a compact exploration view.
    if (overviewMode || completeFilterMode) return { nodes: filtered.nodes, links: filtered.links };
    const activeNodeIds = visibleNodeIds.size > 0 ? visibleNodeIds : initialVisibleNodeIds;
    const nodes = filtered.nodes.filter((node) => activeNodeIds.has(node.id));
    const candidateLinks = filtered.links.filter((link) => (
      activeNodeIds.has(graphEndpointId(link.source)) && activeNodeIds.has(graphEndpointId(link.target))
    ));
    const links = selectReadableSceneLinks(nodes, candidateLinks, submittedQuery);
    return { nodes, links };
  }, [completeFilterMode, filtered.links, filtered.nodes, initialVisibleNodeIds, overviewMode, submittedQuery, visibleNodeIds]);

  const graphData = useMemo(
    () => ({
      nodes: scene.nodes.map((node) => ({ ...node })),
      links: applyLinkCurvature(scene.links.map((link) => ({
        ...link,
        source: graphEndpointId(link.source),
        target: graphEndpointId(link.target),
      }))),
    }),
    [scene],
  );

  const adjacency = useMemo(() => {
    const connections = new Map<string, Set<string>>();
    scene.links.forEach((link) => {
      const source = graphEndpointId(link.source);
      const target = graphEndpointId(link.target);
      if (!connections.has(source)) connections.set(source, new Set());
      if (!connections.has(target)) connections.set(target, new Set());
      connections.get(source)?.add(target);
      connections.get(target)?.add(source);
    });
    return connections;
  }, [scene.links]);

  const availableAdjacency = useMemo(() => buildGraphAdjacency(filtered.links), [filtered.links]);
  const sceneNodeIds = useMemo(() => new Set(scene.nodes.map((node) => node.id)), [scene.nodes]);
  const hiddenNeighborCounts = useMemo(() => {
    const counts = new Map<string, number>();
    availableAdjacency.forEach((neighbors, nodeId) => {
      counts.set(nodeId, [...neighbors].filter((neighborId) => !sceneNodeIds.has(neighborId)).length);
    });
    return counts;
  }, [availableAdjacency, sceneNodeIds]);

  const selectedNode = selectedNodeId ? nodeById.get(selectedNodeId) ?? null : null;
  const selectedEdge = selectedEdgeId ? allLinks.find((link) => link.id === selectedEdgeId) ?? null : null;
  const focusedNodeId = hoveredNodeId || selectedNodeId;
  const activeFilterLabel = nodeType
    ? graph.schema.node_types.find((item) => item.key === nodeType)?.label ?? ''
    : relationshipType
      ? graph.schema.relationship_types.find((item) => item.key === relationshipType)?.label ?? ''
      : '';
  const selectedNodeTypeTotal = nodeType
    ? graph.schema.node_types.find((item) => item.key === nodeType)?.count ?? 0
    : 0;
  const selectedNodeTypeVisibleCount = nodeType
    ? scene.nodes.filter((node) => node.type === nodeType).length
    : 0;
  const denseSubgraph = scene.nodes.length > 180 || scene.links.length > 360;
  const sceneTitle = submittedQuery
    ? `“${submittedQuery}”的关联结果`
    : activeFilterLabel
      ? `“${activeFilterLabel}”知识子图`
      : '家蚕疾病知识全景';

  useEffect(() => {
    setSelectedNodeId((current) => (current && scene.nodes.some((node) => node.id === current) ? current : ''));
    setSelectedEdgeId((current) => (current && scene.links.some((link) => link.id === current) ? current : ''));
  }, [scene]);

  useEffect(() => {
    const kind = selectedNodeId ? 'node' : selectedEdgeId ? 'relationship' : '';
    const elementId = selectedNodeId || selectedEdgeId;
    if (!authenticated || !kind || !elementId) {
      setDetail(null);
      setDetailLoading(false);
      setDetailError('');
      return;
    }
    let ignored = false;
    setDetail(null);
    setDetailLoading(true);
    setDetailError('');
    const path = `/knowledge/graph/detail?kind=${kind}&element_id=${encodeURIComponent(elementId)}`;
    void requestRef.current(path)
      .then((payload) => {
        if (!ignored) setDetail(payload as KnowledgeGraphDetailResponse);
      })
      .catch((reason) => {
        if (!ignored) setDetailError(reason instanceof Error ? reason.message : '详情加载失败');
      })
      .finally(() => {
        if (!ignored) setDetailLoading(false);
      });
    return () => {
      ignored = true;
    };
  }, [authenticated, revision, selectedEdgeId, selectedNodeId]);

  useEffect(() => {
    if (!expanded) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setExpanded(false);
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [expanded]);

  useEffect(() => {
    if (!graphData.nodes.length || viewMode !== 'graph') return;
    const frame = window.requestAnimationFrame(() => {
      const linkForce = graphRef.current?.d3Force('link') as { distance?: (distance: number) => unknown } | undefined;
      const chargeForce = graphRef.current?.d3Force('charge') as {
        strength?: (strength: number) => unknown;
        distanceMax?: (distance: number) => unknown;
      } | undefined;
      const fullOverview = graphData.nodes.length > 300;
      const compact = graphData.nodes.length > 80;
      linkForce?.distance?.(fullOverview ? 38 : compact ? 82 : 112);
      chargeForce?.strength?.(fullOverview ? -46 : compact ? -150 : -285);
      chargeForce?.distanceMax?.(fullOverview ? 380 : compact ? 520 : 760);
      graphRef.current?.d3ReheatSimulation();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [graphData, viewMode]);

  const paintNode = useCallback(
    (node: NodeObject<GraphNodeDatum>, context: CanvasRenderingContext2D, globalScale: number) => {
      const nodeId = String(node.id);
      const radius = graphNodeRadius(node.degree ?? 0);
      const related = !focusedNodeId || nodeId === focusedNodeId || adjacency.get(focusedNodeId)?.has(nodeId);
      const selected = nodeId === selectedNodeId;
      const hovered = nodeId === hoveredNodeId;
      const wasExpanded = expandedNodeIds.has(nodeId);
      const denseOverview = graphData.nodes.length > 180;
      context.save();
      context.globalAlpha = related ? 1 : 0.1;
      if (selected || hovered) {
        context.beginPath();
        context.arc(node.x ?? 0, node.y ?? 0, radius + 7 / globalScale, 0, Math.PI * 2);
        context.fillStyle = selected ? 'rgba(0,122,255,.2)' : darkMode ? 'rgba(255,255,255,.15)' : 'rgba(255,255,255,.94)';
        context.fill();
      }
      if (!denseOverview || selected || hovered) {
        context.shadowColor = darkMode ? 'rgba(0,0,0,.48)' : 'rgba(44,67,61,.2)';
        context.shadowBlur = (selected || hovered ? 16 : 7) / globalScale;
        context.shadowOffsetY = 2 / globalScale;
      }
      context.beginPath();
      context.arc(node.x ?? 0, node.y ?? 0, radius, 0, Math.PI * 2);
      context.fillStyle = NODE_COLORS[node.type] ?? '#82909a';
      context.fill();
      context.shadowColor = 'transparent';
      context.lineWidth = (selected ? 3 : 1.6) / globalScale;
      context.strokeStyle = selected ? (darkMode ? '#8dc7ff' : '#006fd6') : darkMode ? 'rgba(255,255,255,.82)' : '#fff';
      context.stroke();
      if (wasExpanded) {
        context.beginPath();
        context.setLineDash([2.8 / globalScale, 2.8 / globalScale]);
        context.arc(node.x ?? 0, node.y ?? 0, radius + 4 / globalScale, 0, Math.PI * 2);
        context.lineWidth = 1.2 / globalScale;
        context.strokeStyle = darkMode ? 'rgba(141,199,255,.68)' : 'rgba(0,111,214,.52)';
        context.stroke();
        context.setLineDash([]);
      }
      if (graphData.nodes.length <= 72 || globalScale >= 1.2 || selected || hovered) {
        drawNodeLabel(context, node, radius, globalScale, darkMode, selected || hovered);
      }
      context.restore();
    },
    [adjacency, darkMode, expandedNodeIds, focusedNodeId, graphData.nodes.length, hoveredNodeId, selectedNodeId],
  );

  const paintPointerArea = useCallback(
    (node: NodeObject<GraphNodeDatum>, color: string, context: CanvasRenderingContext2D) => {
      context.beginPath();
      context.arc(node.x ?? 0, node.y ?? 0, graphNodeRadius(node.degree ?? 0) + 4, 0, Math.PI * 2);
      context.fillStyle = color;
      context.fill();
    },
    [],
  );

  const clearSelection = () => {
    setSelectedNodeId('');
    setSelectedEdgeId('');
  };

  const focusNode = (node: NodeObject<GraphNodeDatum>) => {
    const nodeId = String(node.id);
    const currentVisible = visibleNodeIds.size > 0 ? visibleNodeIds : initialVisibleNodeIds;
    const additions = overviewMode || completeFilterMode
      ? new Set<string>()
      : graphNeighborAdditions(nodeId, filtered.links, currentVisible, nodeById, 12);
    if (additions.size > 0) {
      setVisibleNodeIds((current) => new Set([...current, ...additions]));
      setExpandedNodeIds((current) => new Set([...current, nodeId]));
      window.requestAnimationFrame(() => graphRef.current?.d3ReheatSimulation());
    }
    setSelectedNodeId(nodeId);
    setSelectedEdgeId('');
    if (typeof node.x === 'number' && typeof node.y === 'number') {
      graphRef.current?.centerAt(node.x, node.y, reducedMotion ? 0 : 420);
      graphRef.current?.zoom(Math.max(1.25, Math.min(1.9, graphRef.current.zoom() * 1.08)), reducedMotion ? 0 : 420);
    }
  };

  const returnToOverview = () => {
    setQuery('');
    setSubmittedQuery('');
    setNodeType('');
    setRelationshipType('');
    setVisibleNodeIds(new Set());
    setExpandedNodeIds(new Set());
    clearSelection();
    fittedRef.current = false;
    window.requestAnimationFrame(() => graphRef.current?.d3ReheatSimulation());
  };

  const relaunchLayout = () => {
    graphData.nodes.forEach((node) => {
      const positioned = node as NodeObject<GraphNodeDatum>;
      positioned.fx = undefined;
      positioned.fy = undefined;
    });
    fittedRef.current = false;
    graphRef.current?.d3ReheatSimulation();
  };

  const paintLinkLabel = useCallback(
    (link: LinkObject<GraphNodeDatum, GraphLinkDatum>, context: CanvasRenderingContext2D, globalScale: number) => {
      const highlighted = String(link.id) === selectedEdgeId || Boolean(focusedNodeId && graphLinkTouches(link, focusedNodeId));
      if (!highlighted && (graphData.links.length > 62 || globalScale < 0.82)) return;
      drawGraphLinkLabel(context, link, globalScale, darkMode, highlighted, focusedNodeId);
    },
    [darkMode, focusedNodeId, graphData.links.length, selectedEdgeId],
  );

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmittedQuery(query.trim());
    setNodeType('');
    setRelationshipType('');
    clearSelection();
  };

  const selectNodeType = (key: string) => {
    setQuery('');
    setSubmittedQuery('');
    setRelationshipType('');
    setNodeType((current) => current === key ? '' : key);
    clearSelection();
  };

  const selectRelationshipType = (key: string) => {
    setQuery('');
    setSubmittedQuery('');
    setNodeType('');
    setRelationshipType((current) => current === key ? '' : key);
    clearSelection();
  };

  const refresh = () => {
    clearSelection();
    setRevision((current) => current + 1);
  };

  const connectionState = loading && !data ? 'connecting' : error || (data && !data.available) ? 'unavailable' : 'connected';
  const connectionLabel = connectionState === 'connecting' ? '正在连接 Neo4j Aura' : connectionState === 'unavailable' ? '图谱暂不可用' : 'Neo4j Aura 已连接';

  return (
    <section className={`knowledge-explorer-page ${expanded ? 'is-expanded' : ''}`}>
      <header className="knowledge-explorer-hero">
        <div className="knowledge-explorer-heading">
          <span className={`knowledge-connection-state ${connectionState}`}><i />{connectionLabel}</span>
          <h1>图谱探索</h1>
          <p>从疾病出发，沿症状、病原、传播途径与防治措施追溯知识关系和原始证据。</p>
        </div>
        <form className="knowledge-explorer-search" onSubmit={submitSearch}>
          <Search size={17} />
          <input
            aria-label="搜索知识图谱"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索疾病、症状、病原或防治措施"
            maxLength={80}
          />
          {query && <button type="button" className="clear" aria-label="清空搜索词" onClick={() => setQuery('')}><X size={15} /></button>}
          <button type="submit" className="search-action">探索</button>
          <button type="button" className="refresh-action" aria-label="刷新图谱" title="刷新图谱" onClick={refresh} disabled={loading}>
            <RefreshCcw className={loading ? 'spinning' : ''} size={16} />
          </button>
        </form>
      </header>

      {!authenticated ? (
        <KnowledgeAccessState onRequireAuth={onRequireAuth} />
      ) : loading && !data ? (
        <KnowledgeLoadingState />
      ) : error ? (
        <KnowledgeErrorState message={error} onRetry={refresh} />
      ) : !graph.available ? (
        <KnowledgeErrorState message={graph.reason || 'Neo4j Aura 图谱尚未完成配置'} onRetry={refresh} />
      ) : (
        <>
          <div className="knowledge-explorer-summary" aria-label="图谱概览">
            <span><b>{graph.schema.total_nodes.toLocaleString('zh-CN')}</b>实体</span>
            <span><b>{graph.schema.total_relationships.toLocaleString('zh-CN')}</b>关系</span>
            <span><b>{graph.snapshot.source_count.toLocaleString('zh-CN')}</b>本地发布来源</span>
            <small><ShieldCheck size={14} />{graph.snapshot.scope_label} · 只读查询</small>
          </div>

          {graph.result.truncated && (
            <div className="knowledge-explorer-warning">
              <AlertTriangle size={15} />
              匹配到 {graph.result.matching_relationships.toLocaleString('zh-CN')} 条关系，当前加载前 {graph.result.relationship_count.toLocaleString('zh-CN')} 条。可输入关键词缩小范围。
            </div>
          )}

          {allNodes.length === 0 ? (
            <KnowledgeEmptyState query={submittedQuery} />
          ) : (
            <div className="knowledge-explorer-studio">
              <aside className="knowledge-explorer-filters">
                <div className="knowledge-panel-title">
                  <span><GitBranch size={16} /><span className="knowledge-panel-copy">知识脉络<small>点击类型查看子图</small></span></span>
                  {!overviewMode && <button type="button" onClick={returnToOverview}>返回全景</button>}
                </div>
                <GraphFilter
                  title="实体类型"
                  items={graph.schema.node_types}
                  active={nodeType}
                  colorized
                  onSelect={selectNodeType}
                />
                <GraphFilter
                  title="关系类型"
                  items={graph.schema.relationship_types}
                  active={relationshipType}
                  onSelect={selectRelationshipType}
                />
              </aside>

              <main className="knowledge-explorer-result">
                <div className="knowledge-explorer-result-bar">
                  <span><Network size={15} />{sceneTitle}</span>
                  <div className="knowledge-view-switch" aria-label="结果视图">
                    <button type="button" className={viewMode === 'graph' ? 'active' : ''} onClick={() => setViewMode('graph')}><Network size={13} />图谱</button>
                    <button type="button" className={viewMode === 'table' ? 'active' : ''} onClick={() => setViewMode('table')}><Table2 size={13} />关系表</button>
                  </div>
                </div>

                {viewMode === 'graph' ? (
                  <div className="knowledge-explorer-canvas" ref={viewportRef} role="img" aria-label="可缩放的家蚕疾病知识图谱">
                    <ForceGraph2D<GraphNodeDatum, GraphLinkDatum>
                      ref={graphRef}
                      graphData={graphData}
                      width={viewport.width}
                      height={viewport.height}
                      backgroundColor="rgba(0,0,0,0)"
                      nodeId="id"
                      nodeVal={(node) => Math.max(1, Math.log2((node.degree ?? 0) + 2))}
                      nodeLabel={(node) => {
                        const hiddenCount = hiddenNeighborCounts.get(String(node.id)) ?? 0;
                        return `<div class="knowledge-graph-tooltip"><b>${escapeHtml(node.name)}</b><span>${escapeHtml(node.type_label)} · ${node.degree ?? 0} 条关系${hiddenCount > 0 ? ` · ${hiddenCount} 个待展开` : ''}</span></div>`;
                      }}
                      nodeCanvasObjectMode={() => 'replace'}
                      nodeCanvasObject={paintNode}
                      nodePointerAreaPaint={paintPointerArea}
                      linkSource="source"
                      linkTarget="target"
                      linkCurvature={(link) => link.curvature ?? 0}
                      linkColor={(link) => graphLinkColor(link, focusedNodeId, selectedEdgeId, darkMode)}
                      linkWidth={(link) => link.id === selectedEdgeId ? 2.6 : focusedNodeId && graphLinkTouches(link, focusedNodeId) ? 1.55 : overviewMode || denseSubgraph ? 0.42 : 0.82}
                      linkDirectionalArrowLength={(link) => link.id === selectedEdgeId ? 7 : overviewMode || denseSubgraph ? 2.2 : 4.5}
                      linkDirectionalArrowRelPos={0.88}
                      linkDirectionalArrowColor={(link) => graphLinkColor(link, focusedNodeId, selectedEdgeId, darkMode)}
                      linkLabel={(link) => `<div class="knowledge-graph-tooltip"><b>${escapeHtml(link.relation)}</b><span>${escapeHtml(graphNodeName(link.source, nodeById))} → ${escapeHtml(graphNodeName(link.target, nodeById))}</span></div>`}
                      linkCanvasObjectMode={() => 'after'}
                      linkCanvasObject={paintLinkLabel}
                      linkDirectionalParticles={(link) => reducedMotion ? 0 : link.id === selectedEdgeId ? 3 : focusedNodeId && graphLinkTouches(link, focusedNodeId) ? 1 : 0}
                      linkDirectionalParticleSpeed={0.004}
                      linkDirectionalParticleWidth={(link) => link.id === selectedEdgeId ? 2.4 : 1.5}
                      linkDirectionalParticleColor={(link) => graphLinkColor(link, focusedNodeId, selectedEdgeId, darkMode)}
                      onNodeClick={focusNode}
                      onNodeHover={(node) => setHoveredNodeId(node ? String(node.id) : '')}
                      onNodeDragEnd={(node) => { node.fx = node.x; node.fy = node.y; }}
                      onLinkClick={(link) => { setSelectedEdgeId(String(link.id)); setSelectedNodeId(''); }}
                      onBackgroundClick={clearSelection}
                      minZoom={0.18}
                      maxZoom={12}
                      warmupTicks={reducedMotion ? 1 : overviewMode ? 38 : 95}
                      cooldownTicks={reducedMotion ? 1 : overviewMode ? 130 : 240}
                      cooldownTime={reducedMotion ? 20 : overviewMode ? 3800 : 5600}
                      d3VelocityDecay={0.22}
                      onEngineStop={() => {
                        if (fittedRef.current) return;
                        fittedRef.current = true;
                        graphRef.current?.zoomToFit(reducedMotion ? 0 : 720, 68);
                      }}
                    />
                    <div className={`knowledge-exploration-hud${completeFilterMode ? ' is-complete-filter' : ''}`}>
                      <span><MousePointer2 size={13} />{overviewMode ? '全景模式 · 悬停查看关联' : completeFilterMode ? '完整子图 · 已显示全部匹配项' : '搜索子图 · 点击节点继续展开'}</span>
                      {!overviewMode && <button type="button" onClick={returnToOverview}>返回全景</button>}
                    </div>
                    <div className="knowledge-canvas-count">
                      {overviewMode ? (
                        <><b>{scene.nodes.length}</b> 实体 <i /> <b>{scene.links.length}</b> 全部关系</>
                      ) : completeFilterMode && nodeType ? (
                        <>已显示 <b>{selectedNodeTypeVisibleCount}</b> / {selectedNodeTypeTotal} {activeFilterLabel} <i /> <b>{scene.nodes.length}</b> 实体 <i /> <b>{scene.links.length}</b> 全部关系</>
                      ) : completeFilterMode ? (
                        <><b>{scene.nodes.length}</b> 实体 <i /> 已显示 <b>{scene.links.length}</b> / {filtered.links.length} {activeFilterLabel}关系</>
                      ) : (
                        <><b>{scene.nodes.length}</b> / {filtered.nodes.length} 实体 <i /> <b>{scene.links.length}</b> 关系</>
                      )}
                    </div>
                    <div className="knowledge-canvas-controls">
                      <button type="button" title="放大" aria-label="放大" onClick={() => graphRef.current?.zoom(graphRef.current.zoom() * 1.35, 220)}><ZoomIn size={16} /></button>
                      <button type="button" title="缩小" aria-label="缩小" onClick={() => graphRef.current?.zoom(graphRef.current.zoom() / 1.35, 220)}><ZoomOut size={16} /></button>
                      <button type="button" title="适应画布" aria-label="适应画布" onClick={() => graphRef.current?.zoomToFit(500, 38)}><Network size={16} /></button>
                      <button type="button" title="重新布局" aria-label="重新布局" onClick={relaunchLayout}><RotateCcw size={16} /></button>
                      <button type="button" title={expanded ? '退出全屏' : '全屏查看'} aria-label={expanded ? '退出全屏' : '全屏查看'} onClick={() => setExpanded((current) => !current)}>{expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>
                    </div>
                  </div>
                ) : (
                  <RelationshipTable links={filtered.links} nodes={nodeById} selectedId={selectedEdgeId} onSelect={(id) => { setSelectedEdgeId(id); setSelectedNodeId(''); }} />
                )}
              </main>

              <aside className="knowledge-explorer-detail">
                <div className="knowledge-panel-title">
                  <span><BookOpen size={16} />{selectedNode || selectedEdge ? '证据脉络' : '阅读指南'}</span>
                  {(selectedNode || selectedEdge) && <button type="button" aria-label="关闭详情" onClick={clearSelection}><X size={15} /></button>}
                </div>
                {selectedNode || selectedEdge ? (
                  <GraphDetail
                    fallbackNode={selectedNode}
                    fallbackEdge={selectedEdge}
                    nodeById={nodeById}
                    detail={detail}
                    loading={detailLoading}
                    error={detailError}
                  />
                ) : (
                  <GraphGuide
                    snapshot={graph.snapshot}
                    overview={overviewMode}
                    completeSubgraph={completeFilterMode}
                    filterLabel={activeFilterLabel}
                  />
                )}
              </aside>
            </div>
          )}
        </>
      )}
    </section>
  );
}


function GraphFilter({ title, items, active, colorized = false, onSelect }: { title: string; items: GraphSchemaItem[]; active: string; colorized?: boolean; onSelect: (key: string) => void }) {
  return (
    <section className="knowledge-filter-group">
      <h2>{title}<small>{items.reduce((sum, item) => sum + item.count, 0).toLocaleString('zh-CN')}</small></h2>
      <div>
        {items.map((item) => (
          <button
            type="button"
            key={item.key}
            className={active === item.key ? 'active' : ''}
            style={colorized ? { '--node-color': NODE_COLORS[item.key] ?? '#82909a' } as CSSProperties : undefined}
            onClick={() => onSelect(item.key)}
          >
            {colorized && <i />}
            <span>{item.label}</span>
            <b>{item.count}</b>
          </button>
        ))}
      </div>
    </section>
  );
}


function GraphGuide({ snapshot, overview, completeSubgraph, filterLabel }: {
  snapshot: KnowledgeGraphResponse['snapshot'];
  overview: boolean;
  completeSubgraph: boolean;
  filterLabel: string;
}) {
  return (
    <div className="knowledge-graph-guide">
      <div className="knowledge-guide-mark"><Network size={22} /><i /><i /><i /></div>
      <h2>{overview ? '先看全景，再进入一条脉络' : completeSubgraph ? '完整展示当前知识脉络' : '从一个实体向外探索'}</h2>
      <p>{overview
        ? '当前展示全部实体和关系。悬停查看局部关联；点击左侧类型进入完整子图。'
        : completeSubgraph
          ? `当前已完整显示“${filterLabel}”的匹配项与直接关系。悬停查看关联；可缩放、拖动或固定节点。`
          : '点击节点会展开一圈相邻知识并读取实体说明；点击关系可追溯证据。拖动节点可以固定位置。'}</p>
      <dl>
        <div><dt>数据范围</dt><dd>{snapshot.scope_label}</dd></div>
        <div><dt>访问方式</dt><dd>参数化只读查询</dd></div>
      </dl>
      {snapshot.sources.length > 0 && (
        <section className="knowledge-source-list">
          <h3>当前本地发布来源</h3>
          {snapshot.sources.slice(0, 5).map((source, index) => (
            <SourceRecord source={source} key={`${source.title}-${source.version ?? index}`} />
          ))}
          {snapshot.sources.length > 5 && <small>另有 {snapshot.sources.length - 5} 个本地已发布来源</small>}
        </section>
      )}
    </div>
  );
}


function GraphDetail({ fallbackNode, fallbackEdge, nodeById, detail, loading, error }: { fallbackNode: GraphNodeDatum | null; fallbackEdge: GraphLinkDatum | null; nodeById: Map<string, GraphNodeDatum>; detail: KnowledgeGraphDetailResponse | null; loading: boolean; error: string }) {
  if (loading) return <div className="knowledge-detail-loading"><LoaderCircle className="spinning" size={18} />正在读取证据…</div>;
  if (error) return <div className="knowledge-detail-error"><AlertTriangle size={16} />{error}</div>;
  if (fallbackNode) {
    const node = detail?.node;
    return (
      <div className="knowledge-node-detail">
        <span className="knowledge-detail-type" style={{ '--node-color': NODE_COLORS[fallbackNode.type] ?? '#82909a' } as CSSProperties}><i />{fallbackNode.type_label}</span>
        <h2>{node?.name ?? fallbackNode.name}</h2>
        {node?.english_label && <small>{node.english_label}</small>}
        <p className="knowledge-detail-degree">{node?.degree ?? fallbackNode.degree} 条可见关系</p>
        {node?.description && <p className="knowledge-detail-description">{node.description}</p>}
        {node?.aliases && node.aliases.length > 0 && <div className="knowledge-aliases"><span>别名</span>{node.aliases.map((alias) => <i key={alias}>{alias}</i>)}</div>}
        {node?.evidence && <EvidenceBlock evidence={node.evidence} />}
        {node?.source_documents && node.source_documents.length > 0 && <SourceDocuments documents={node.source_documents} />}
        <KnowledgeReviewMeta confidence={node?.confidence ?? null} status={node?.review_status ?? null} />
      </div>
    );
  }
  if (fallbackEdge) {
    const relationship = detail?.relationship;
    const sourceName = relationship?.source_name ?? graphNodeName(fallbackEdge.source, nodeById);
    const targetName = relationship?.target_name ?? graphNodeName(fallbackEdge.target, nodeById);
    return (
      <div className="knowledge-relationship-detail">
        <span className="knowledge-detail-type relation"><GitBranch size={13} />{relationship?.relation ?? fallbackEdge.relation}</span>
        <h2>{sourceName}</h2>
        <div className="knowledge-relation-path"><i /><span>{relationship?.relation ?? fallbackEdge.relation}</span><i /></div>
        <h2>{targetName}</h2>
        {relationship?.evidence ? <EvidenceBlock evidence={relationship.evidence} /> : <p className="knowledge-no-evidence">此关系没有可公开的文字证据。</p>}
        {relationship?.source_record && <section className="knowledge-source-list"><h3>发布来源</h3><SourceRecord source={relationship.source_record} /></section>}
        {relationship?.source_documents && relationship.source_documents.length > 0 && <SourceDocuments documents={relationship.source_documents} />}
        <KnowledgeReviewMeta confidence={relationship?.confidence ?? null} status={relationship?.review_status ?? null} />
      </div>
    );
  }
  return null;
}


function EvidenceBlock({ evidence }: { evidence: string }) {
  return <blockquote className="knowledge-evidence-block"><span>证据摘录</span><p>{evidence}</p></blockquote>;
}


function SourceDocuments({ documents }: { documents: string[] }) {
  return <section className="knowledge-source-documents"><h3>来源文档</h3>{documents.map((document) => <span key={document}><BookOpen size={13} />{document}</span>)}</section>;
}


function SourceRecord({ source }: { source: KnowledgeGraphSource }) {
  const url = safeExternalUrl(source.url);
  const body = <><BookOpen size={14} /><span><b>{source.title}</b><small>{[source.version, formatGraphDate(source.published_at)].filter(Boolean).join(' · ') || '受控知识来源'}</small></span>{url && <ExternalLink size={13} />}</>;
  return url ? <a href={url} target="_blank" rel="noreferrer">{body}</a> : <div>{body}</div>;
}


function KnowledgeReviewMeta({ confidence, status }: { confidence: string | number | null; status: string | null }) {
  if (confidence === null && !status) return null;
  return (
    <dl className="knowledge-review-meta">
      {confidence !== null && <div><dt>置信度</dt><dd>{formatConfidence(confidence)}</dd></div>}
      {status && <div><dt>审核状态</dt><dd>{formatReviewStatus(status)}</dd></div>}
    </dl>
  );
}


function RelationshipTable({ links, nodes, selectedId, onSelect }: { links: GraphLinkDatum[]; nodes: Map<string, GraphNodeDatum>; selectedId: string; onSelect: (id: string) => void }) {
  const visible = links.slice(0, 500);
  return (
    <div className="knowledge-relationship-table">
      <header><span>关系结果</span><b>{links.length.toLocaleString('zh-CN')}</b>{links.length > visible.length && <small>为保证页面流畅，仅列出前 {visible.length} 条</small>}</header>
      <div>
        {visible.map((link) => (
          <button type="button" className={selectedId === link.id ? 'selected' : ''} key={link.id} onClick={() => onSelect(link.id)}>
            <span><i style={{ background: NODE_COLORS[nodes.get(graphEndpointId(link.source))?.type ?? ''] ?? '#82909a' }} />{graphNodeName(link.source, nodes)}</span>
            <strong>{link.relation}</strong>
            <span><i style={{ background: NODE_COLORS[nodes.get(graphEndpointId(link.target))?.type ?? ''] ?? '#82909a' }} />{graphNodeName(link.target, nodes)}</span>
            <small className={link.has_evidence ? 'has-evidence' : ''}>{link.has_evidence ? '有证据' : '无摘录'}</small>
          </button>
        ))}
      </div>
    </div>
  );
}


function KnowledgeAccessState({ onRequireAuth }: { onRequireAuth: () => void }) {
  return (
    <div className="knowledge-explorer-state">
      <span><ShieldCheck size={26} /></span>
      <h2>登录后探索知识图谱</h2>
      <p>图谱属于受控知识资产。登录后可搜索实体、查看关系，并追溯已公开的证据来源。</p>
      <button type="button" onClick={onRequireAuth}>登录并继续</button>
    </div>
  );
}


function KnowledgeLoadingState() {
  return <div className="knowledge-explorer-state loading"><LoaderCircle className="spinning" size={27} /><h2>正在连接 Neo4j Aura</h2><p>读取受控 Schema、实体和关系，请稍候。</p></div>;
}


function KnowledgeErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="knowledge-explorer-state error"><span><AlertTriangle size={25} /></span><h2>图谱暂时无法读取</h2><p>{message}</p><button type="button" onClick={onRetry}>重新连接</button></div>;
}


function KnowledgeEmptyState({ query }: { query: string }) {
  return <div className="knowledge-explorer-state empty"><span><Search size={25} /></span><h2>{query ? `没有找到“${query}”` : '当前没有可展示的关系'}</h2><p>{query ? '尝试疾病全名、症状关键词、病原名称或防治措施。' : 'Neo4j 已连接，但受控范围内还没有关系数据。'}</p></div>;
}


function useElementSize<T extends HTMLElement>(ref: RefObject<T | null>, fallbackWidth: number, fallbackHeight: number, active = true) {
  const [size, setSize] = useState({ width: fallbackWidth, height: fallbackHeight });
  useEffect(() => {
    if (!active) return;
    const element = ref.current;
    if (!element) return;
    const measure = () => {
      const next = { width: Math.max(320, element.clientWidth), height: Math.max(440, element.clientHeight) };
      setSize((current) => current.width === next.width && current.height === next.height ? current : next);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [active, fallbackHeight, fallbackWidth, ref]);
  return size;
}


function graphEndpointId(endpoint: string | NodeObject<GraphNodeDatum>): string {
  return typeof endpoint === 'object' && endpoint !== null ? String(endpoint.id) : String(endpoint);
}


function graphNodeName(endpoint: string | NodeObject<GraphNodeDatum>, nodes: Map<string, GraphNodeDatum>): string {
  if (typeof endpoint === 'object' && endpoint !== null && endpoint.name) return endpoint.name;
  return nodes.get(graphEndpointId(endpoint))?.name ?? graphEndpointId(endpoint);
}


function graphNodeRadius(degree: number): number {
  return 9.8 + Math.min(8.2, Math.log2(Math.max(1, degree) + 1) * 1.35);
}


function drawNodeLabel(context: CanvasRenderingContext2D, node: NodeObject<GraphNodeDatum>, radius: number, globalScale: number, darkMode: boolean, highlighted: boolean) {
  const name = node.name.length > 18 ? `${node.name.slice(0, 17)}…` : node.name;
  const fontSize = (highlighted ? 11.5 : 10.2) / globalScale;
  const paddingX = 6 / globalScale;
  const paddingY = 3.4 / globalScale;
  const x = node.x ?? 0;
  const y = (node.y ?? 0) + radius + 10 / globalScale;
  context.font = `${highlighted ? 700 : 620} ${fontSize}px "Microsoft YaHei", sans-serif`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  const width = context.measureText(name).width + paddingX * 2;
  const height = fontSize + paddingY * 2;
  context.shadowColor = darkMode ? 'rgba(0,0,0,.28)' : 'rgba(34,57,50,.12)';
  context.shadowBlur = 6 / globalScale;
  context.shadowOffsetY = 1.5 / globalScale;
  drawRoundedRect(context, x - width / 2, y - height / 2, width, height, 5 / globalScale);
  context.fillStyle = darkMode ? 'rgba(39,39,42,.93)' : 'rgba(255,255,255,.95)';
  context.fill();
  context.shadowColor = 'transparent';
  context.lineWidth = (highlighted ? 1.1 : 0.65) / globalScale;
  context.strokeStyle = highlighted
    ? darkMode ? 'rgba(100,181,255,.72)' : 'rgba(0,122,255,.5)'
    : darkMode ? 'rgba(255,255,255,.15)' : 'rgba(63,84,77,.14)';
  context.stroke();
  context.fillStyle = darkMode ? '#f2f2f7' : '#242b29';
  context.fillText(name, x, y);
}


function drawGraphLinkLabel(
  context: CanvasRenderingContext2D,
  link: LinkObject<GraphNodeDatum, GraphLinkDatum>,
  globalScale: number,
  darkMode: boolean,
  highlighted: boolean,
  focusedNodeId: string,
) {
  if (typeof link.source !== 'object' || typeof link.target !== 'object') return;
  const sourceX = link.source.x;
  const sourceY = link.source.y;
  const targetX = link.target.x;
  const targetY = link.target.y;
  if (![sourceX, sourceY, targetX, targetY].every((value) => typeof value === 'number')) return;
  const dx = (targetX as number) - (sourceX as number);
  const dy = (targetY as number) - (sourceY as number);
  const distance = Math.max(1, Math.hypot(dx, dy));
  const sourceIsFocused = Boolean(focusedNodeId) && graphEndpointId(link.source) === focusedNodeId;
  const targetIsFocused = Boolean(focusedNodeId) && graphEndpointId(link.target) === focusedNodeId;
  const position = sourceIsFocused ? 0.64 : targetIsFocused ? 0.36 : 0.5;
  const curveOffset = (link.curvature ?? 0) * distance * 0.48 * (4 * position * (1 - position));
  const x = (sourceX as number) + dx * position - (dy / distance) * curveOffset;
  const y = (sourceY as number) + dy * position + (dx / distance) * curveOffset;
  const label = link.relation.length > 12 ? `${link.relation.slice(0, 11)}…` : link.relation;
  const fontSize = (highlighted ? 9.8 : 8.8) / globalScale;
  const paddingX = 5 / globalScale;
  const paddingY = 2.5 / globalScale;
  context.save();
  context.font = `${highlighted ? 700 : 620} ${fontSize}px "Microsoft YaHei", sans-serif`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  const width = context.measureText(label).width + paddingX * 2;
  const height = fontSize + paddingY * 2;
  drawRoundedRect(context, x - width / 2, y - height / 2, width, height, height / 2);
  context.fillStyle = highlighted
    ? darkMode ? 'rgba(32,74,108,.95)' : 'rgba(230,244,255,.97)'
    : darkMode ? 'rgba(38,38,41,.88)' : 'rgba(255,255,255,.9)';
  context.fill();
  context.lineWidth = 0.7 / globalScale;
  context.strokeStyle = highlighted
    ? darkMode ? 'rgba(100,181,255,.65)' : 'rgba(0,122,255,.38)'
    : darkMode ? 'rgba(255,255,255,.12)' : 'rgba(73,94,87,.14)';
  context.stroke();
  context.fillStyle = highlighted ? darkMode ? '#b9ddff' : '#0066bd' : darkMode ? '#d1d1d6' : '#586560';
  context.fillText(label, x, y);
  context.restore();
}


function drawRoundedRect(context: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  const safeRadius = Math.min(radius, width / 2, height / 2);
  context.beginPath();
  context.roundRect(x, y, width, height, safeRadius);
}


function buildGraphAdjacency(links: GraphLinkDatum[]): Map<string, Set<string>> {
  const adjacency = new Map<string, Set<string>>();
  links.forEach((link) => {
    const source = graphEndpointId(link.source);
    const target = graphEndpointId(link.target);
    if (!adjacency.has(source)) adjacency.set(source, new Set());
    if (!adjacency.has(target)) adjacency.set(target, new Set());
    adjacency.get(source)?.add(target);
    adjacency.get(target)?.add(source);
  });
  return adjacency;
}


function buildInitialVisibleNodeIds(nodes: GraphNodeDatum[], links: GraphLinkDatum[], query: string): Set<string> {
  if (nodes.length === 0) return new Set();
  if (nodes.length <= 44) return new Set(nodes.map((node) => node.id));
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const normalizedQuery = query.trim().toLocaleLowerCase('zh-CN');
  const rankedNodes = [...nodes].sort((left, right) => right.degree - left.degree || left.name.localeCompare(right.name, 'zh-CN'));
  const queryMatches = normalizedQuery
    ? rankedNodes.filter((node) => node.name.toLocaleLowerCase('zh-CN').includes(normalizedQuery))
    : [];
  const exactMatches = queryMatches.filter((node) => node.name.toLocaleLowerCase('zh-CN') === normalizedQuery);
  const diseaseSeeds = rankedNodes.filter((node) => node.type === 'Disease');
  const seeds = (exactMatches.length > 0 ? exactMatches : queryMatches.length > 0 ? queryMatches : diseaseSeeds.length > 0 ? diseaseSeeds : rankedNodes).slice(0, normalizedQuery ? 3 : 1);
  const incident = indexIncidentLinks(links);
  const visible = new Set(seeds.map((node) => node.id));
  const queue = seeds.map((node) => ({ id: node.id, depth: 0 }));
  const expanded = new Set<string>();
  const nodeLimit = normalizedQuery ? 68 : 54;

  while (queue.length > 0 && visible.size < nodeLimit) {
    const current = queue.shift();
    if (!current || expanded.has(current.id) || current.depth > 0) continue;
    expanded.add(current.id);
    const branchLimit = current.depth === 0 ? (normalizedQuery ? 24 : 20) : 7;
    const candidates = prioritizeIncidentLinks(incident.get(current.id) ?? [], current.id, nodeById).slice(0, branchLimit);
    candidates.forEach((link) => {
      if (visible.size >= nodeLimit) return;
      const neighborId = graphOtherEndpoint(link, current.id);
      if (!nodeById.has(neighborId) || visible.has(neighborId)) return;
      visible.add(neighborId);
      queue.push({ id: neighborId, depth: current.depth + 1 });
    });
  }
  return visible;
}


function selectReadableSceneLinks(nodes: GraphNodeDatum[], links: GraphLinkDatum[], query: string): GraphLinkDatum[] {
  const maxLinks = Math.min(72, Math.max(28, nodes.length + 10));
  if (links.length <= maxLinks) return links;
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const normalizedQuery = query.trim().toLocaleLowerCase('zh-CN');
  const rankedNodes = [...nodes].sort((left, right) => right.degree - left.degree || left.name.localeCompare(right.name, 'zh-CN'));
  const matchingNodes = normalizedQuery
    ? rankedNodes.filter((node) => node.name.toLocaleLowerCase('zh-CN').includes(normalizedQuery))
    : [];
  const diseaseNodes = rankedNodes.filter((node) => node.type === 'Disease');
  const roots = (matchingNodes.length > 0 ? matchingNodes : diseaseNodes.length > 0 ? diseaseNodes : rankedNodes).slice(0, normalizedQuery ? 3 : 1);
  const incident = indexIncidentLinks(links);
  const visitedNodes = new Set<string>();
  const selectedLinks: GraphLinkDatum[] = [];
  const selectedIds = new Set<string>();
  const queue = roots.map((node) => node.id);
  roots.forEach((node) => visitedNodes.add(node.id));

  const connectComponent = () => {
    while (queue.length > 0 && selectedLinks.length < maxLinks) {
      const nodeId = queue.shift();
      if (!nodeId) continue;
      const candidates = prioritizeIncidentLinks(incident.get(nodeId) ?? [], nodeId, nodeById);
      candidates.forEach((link) => {
        if (selectedLinks.length >= maxLinks) return;
        const neighborId = graphOtherEndpoint(link, nodeId);
        if (visitedNodes.has(neighborId) || !nodeById.has(neighborId)) return;
        visitedNodes.add(neighborId);
        selectedIds.add(link.id);
        selectedLinks.push(link);
        queue.push(neighborId);
      });
    }
  };

  connectComponent();
  rankedNodes.forEach((node) => {
    if (selectedLinks.length >= maxLinks || visitedNodes.has(node.id)) return;
    visitedNodes.add(node.id);
    queue.push(node.id);
    connectComponent();
  });

  [...links]
    .sort((left, right) => Number(right.has_evidence) - Number(left.has_evidence) || left.relation.localeCompare(right.relation, 'zh-CN'))
    .forEach((link) => {
      if (selectedLinks.length >= maxLinks || selectedIds.has(link.id)) return;
      selectedIds.add(link.id);
      selectedLinks.push(link);
    });
  return selectedLinks;
}


function graphNeighborAdditions(
  nodeId: string,
  links: GraphLinkDatum[],
  visibleNodeIds: Set<string>,
  nodeById: Map<string, GraphNodeDatum>,
  limit: number,
): Set<string> {
  const incident = links.filter((link) => graphLinkTouches(link, nodeId));
  const prioritized = prioritizeIncidentLinks(incident, nodeId, nodeById);
  const additions = new Set<string>();
  prioritized.forEach((link) => {
    if (additions.size >= limit) return;
    const neighborId = graphOtherEndpoint(link, nodeId);
    if (!visibleNodeIds.has(neighborId) && nodeById.has(neighborId)) additions.add(neighborId);
  });
  return additions;
}


function indexIncidentLinks(links: GraphLinkDatum[]): Map<string, GraphLinkDatum[]> {
  const index = new Map<string, GraphLinkDatum[]>();
  links.forEach((link) => {
    const source = graphEndpointId(link.source);
    const target = graphEndpointId(link.target);
    index.set(source, [...(index.get(source) ?? []), link]);
    index.set(target, [...(index.get(target) ?? []), link]);
  });
  return index;
}


function prioritizeIncidentLinks(links: GraphLinkDatum[], nodeId: string, nodeById: Map<string, GraphNodeDatum>): GraphLinkDatum[] {
  const groups = new Map<string, GraphLinkDatum[]>();
  links.forEach((link) => groups.set(link.relation_key, [...(groups.get(link.relation_key) ?? []), link]));
  groups.forEach((group) => group.sort((left, right) => {
    if (left.has_evidence !== right.has_evidence) return left.has_evidence ? -1 : 1;
    return (nodeById.get(graphOtherEndpoint(right, nodeId))?.degree ?? 0) - (nodeById.get(graphOtherEndpoint(left, nodeId))?.degree ?? 0);
  }));
  const result: GraphLinkDatum[] = [];
  let round = 0;
  let found = true;
  while (found) {
    found = false;
    groups.forEach((group) => {
      if (group[round]) {
        result.push(group[round]);
        found = true;
      }
    });
    round += 1;
  }
  return result;
}


function graphOtherEndpoint(link: GraphLinkDatum, nodeId: string): string {
  const source = graphEndpointId(link.source);
  return source === nodeId ? graphEndpointId(link.target) : source;
}


function applyLinkCurvature(links: GraphLinkDatum[]): GraphLinkDatum[] {
  const groups = new Map<string, GraphLinkDatum[]>();
  links.forEach((link) => {
    const endpoints = [graphEndpointId(link.source), graphEndpointId(link.target)].sort();
    const key = endpoints.join('|');
    groups.set(key, [...(groups.get(key) ?? []), link]);
  });
  groups.forEach((group) => {
    if (group.length === 1) {
      group[0].curvature = 0;
      return;
    }
    const midpoint = (group.length - 1) / 2;
    group.forEach((link, index) => {
      const offset = index - midpoint;
      link.curvature = offset === 0 ? 0.08 : offset * 0.18;
    });
  });
  return links;
}


function graphLinkTouches(link: LinkObject<GraphNodeDatum, GraphLinkDatum> | GraphLinkDatum, nodeId: string): boolean {
  return graphEndpointId(link.source as string | NodeObject<GraphNodeDatum>) === nodeId || graphEndpointId(link.target as string | NodeObject<GraphNodeDatum>) === nodeId;
}


function graphLinkColor(link: LinkObject<GraphNodeDatum, GraphLinkDatum> | GraphLinkDatum, focusedNodeId: string, selectedEdgeId: string, darkMode: boolean): string {
  if (String(link.id) === selectedEdgeId) return darkMode ? 'rgba(100,181,255,.96)' : 'rgba(0,122,255,.92)';
  if (focusedNodeId) return graphLinkTouches(link, focusedNodeId) ? (darkMode ? 'rgba(209,209,214,.82)' : 'rgba(67,91,84,.82)') : 'rgba(129,145,151,.07)';
  return darkMode ? 'rgba(174,174,178,.34)' : 'rgba(91,113,106,.4)';
}


function escapeHtml(input: string): string {
  return input.replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character] ?? character);
}


function safeExternalUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}


function formatGraphDate(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' }).format(date);
}


function formatConfidence(value: string | number): string {
  if (typeof value === 'number' && value >= 0 && value <= 1) return `${Math.round(value * 100)}%`;
  const labels: Record<string, string> = { high: '高', medium: '中', low: '低' };
  return labels[String(value).toLowerCase()] ?? String(value);
}


function formatReviewStatus(value: string): string {
  const labels: Record<string, string> = { approved: '已审核', published: '已发布', confirmed: '已确认', pending: '待审核' };
  return labels[value] ?? value;
}

import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import {
  addEdge,
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  type Connection,
  type Edge,
  type Node,
  type OnConnect,
  type ReactFlowInstance,
  type Viewport,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'
import {
  compileWorkflowGraph,
  getCompiledWorkflowGraph,
  getWorkflowGraphRun,
  getWorkflowGraphRunEvents,
  runWorkflowGraph,
} from '../lib/api'
import NodeInfoCard from '../components/workflow/NodeInfoCard'
import NodeTemplatePalette, { type NodeTemplatePaletteItem } from '../components/workflow/NodeTemplatePalette'
import { getNodeSchema } from '../components/workflow/nodeSchemaRegistry'
import {
  DEFAULT_WORKFLOW_LINK_PRESET_KEY,
  WORKFLOW_LINK_PRESET_BY_KEY,
  WORKFLOW_LINK_PRESETS,
  WORKFLOW_MODULE_TEMPLATES,
} from '../components/workflow/moduleTemplateCatalog'
import { BACKEND_TASK_CATALOG } from '../components/workflow/backendTaskCatalog'
import '@xyflow/react/dist/style.css'

type DesignerDsl = {
  version: '1.0'
  nodes: Node[]
  edges: Edge[]
  viewport?: Viewport
  meta?: {
    updatedAt: string
  }
}

type NodeType = 'vector_search' | 'llm_call' | 'join' | 'filter' | 'frontend_input' | 'database_sink'

type NodeTemplate = NodeTemplatePaletteItem<Record<string, unknown>> & {
  nodeType: NodeType
}

type NodeInfoProfile = {
  key: string
  label: string
  nodeType: NodeType
  description?: string
  data: Record<string, unknown>
}

type NodeOutputOption = {
  nodeId: string
  nodeLabel?: string
  outputKeys: string[]
}

type CanvasPanelKey = 'templates' | 'p2p' | 'preset' | 'runtime' | 'json' | 'results'

type LlmDesignerPageProps = {
  projectKey: string
  onExportDsl?: (dsl: DesignerDsl) => void
  presentationMode?: 'runtime' | 'storybook-lite'
}

type DesignerLinkParams = {
  templateKey: string
  fromNodeId: string
  toNodeId: string
  graphId: string
  runId: string
  runInputText: string
  nodeId: string
  frontendPayload: string
  frontendQueryKey: string
  databaseStoreUri: string
  databaseTable: string
}

function readDesignerLinkParams(): DesignerLinkParams {
  const raw = String(window.location.hash || '').replace(/^#/, '')
  const queryIndex = raw.indexOf('?')
  const rawQuery = queryIndex >= 0 ? raw.slice(queryIndex + 1) : ''
  const query = new URLSearchParams(rawQuery)

  const runInputRaw = query.get('input') || query.get('run_input') || ''
  let runInputText = '{}'
  if (runInputRaw.trim()) {
    try {
      runInputText = JSON.stringify(JSON.parse(runInputRaw), null, 2)
    } catch {
      runInputText = runInputRaw
    }
  }

  return {
    templateKey: String(query.get('template') || query.get('tpl') || '').trim(),
    fromNodeId: String(query.get('from') || '').trim(),
    toNodeId: String(query.get('to') || '').trim(),
    graphId: String(query.get('graph_id') || '').trim(),
    runId: String(query.get('run_id') || '').trim(),
    runInputText,
    nodeId: String(query.get('node') || '').trim(),
    frontendPayload: String(query.get('frontend_payload') || query.get('input_payload') || '').trim(),
    frontendQueryKey: String(query.get('frontend_query_key') || query.get('query_key') || '').trim(),
    databaseStoreUri: String(query.get('database_store_uri') || query.get('db_uri') || '').trim(),
    databaseTable: String(query.get('database_table') || '').trim(),
  }
}

function mergeUniqueTemplates(...groups: NodeTemplate[][]) {
  const seen = new Set<string>()
  return groups.flatMap((group) =>
    group.filter((item) => {
      if (seen.has(item.key)) return false
      seen.add(item.key)
      return true
    }),
  )
}

function isStorybookIframe() {
  return typeof window !== 'undefined' && window.location.pathname.includes('iframe.html')
}

function createModuleTemplates(): NodeTemplate[] {
  return WORKFLOW_MODULE_TEMPLATES.map((item) => ({
    key: item.key,
    label: item.label,
    description: item.description,
    nodeType: resolveNodeType(item.nodeType),
    data: {
      ...item.data,
      module_type: item.moduleType,
      module_key: item.key,
      node_type: resolveNodeType(item.nodeType),
    },
  }))
}

function createTemplateCatalog(): NodeTemplate[] {
  return mergeUniqueTemplates(NODE_TEMPLATES, createModuleTemplates())
}

const NODE_TEMPLATES: NodeTemplate[] = [
  {
    key: 'user-input',
    label: 'User Input',
    nodeType: 'vector_search',
    description: '用户输入/问题入口',
    data: { label: 'User Input', node_type: 'vector_search', role: 'input', query_key: 'query' },
  },
  {
    key: 'vector-search',
    label: 'Vector Search',
    nodeType: 'vector_search',
    description: '向量检索上下文',
    data: { label: 'Vector Search', node_type: 'vector_search', top_k: 5, source: 'default_corpus' },
  },
  {
    key: 'llm-call',
    label: 'LLM Call',
    nodeType: 'llm_call',
    description: '调用大模型生成',
    data: {
      label: 'LLM Call',
      node_type: 'llm_call',
      provider: 'openai',
      model: 'gpt-4.1',
      temperature: 0.2,
      top_p: 1,
      max_tokens: 1024,
      prompt_class: 'analyst',
      prompt_template: 'Analyze input and provide concise, evidence-based findings.',
    },
  },
  {
    key: 'filter-predicate',
    label: 'Filter (Predicate)',
    nodeType: 'filter',
    description: '表达式筛选策略',
    data: {
      label: 'Filter Predicate',
      node_type: 'filter',
      strategy: 'predicate',
      predicate_expr: '={{$input.query}}',
      predicate_mode: 'keep',
    },
  },
  {
    key: 'filter-topk',
    label: 'Filter (TopK)',
    nodeType: 'filter',
    description: '评分阈值/TopK 筛选',
    data: {
      label: 'Filter TopK',
      node_type: 'filter',
      strategy: 'topk',
      topk_k: 20,
      topk_score_field: 'score',
      topk_desc: true,
    },
  },
  {
    key: 'join',
    label: 'Join',
    nodeType: 'join',
    description: '聚合多路节点输出',
    data: { label: 'Join', node_type: 'join', strategy: 'concat' },
  },
  {
    key: 'final-output',
    label: 'Final Output',
    nodeType: 'join',
    description: '最终输出节点',
    data: { label: 'Final Output', node_type: 'join', role: 'output' },
  },
]

const SOURCE_TYPE_BY_NODE: Record<NodeType, string> = {
  vector_search: 'retrieval',
  llm_call: 'model',
  join: 'aggregator',
  filter: 'filter',
  frontend_input: 'frontend',
  database_sink: 'database',
}

const NODE_INFO_PROFILES: NodeInfoProfile[] = [
  {
    key: 'llm-precise',
    label: 'LLM Precise',
    nodeType: 'llm_call',
    description: '低温度，稳定输出',
    data: {
      provider: 'openai',
      model: 'gpt-4.1',
      temperature: 0.1,
      top_p: 0.9,
      max_tokens: 1024,
      prompt_class: 'analyst',
      prompt_template: 'Answer with concise facts.',
    },
  },
  {
    key: 'llm-creative',
    label: 'LLM Creative',
    nodeType: 'llm_call',
    description: '高温度，发散输出',
    data: {
      provider: 'openai',
      model: 'gpt-4.1',
      temperature: 0.8,
      top_p: 1,
      max_tokens: 1400,
      prompt_class: 'rewriter',
      prompt_template: 'Provide multiple creative options.',
    },
  },
  {
    key: 'llm-summarizer',
    label: 'LLM Summarizer',
    nodeType: 'llm_call',
    description: '摘要生成',
    data: {
      provider: 'openai',
      model: 'gpt-4.1-mini',
      temperature: 0.2,
      top_p: 1,
      max_tokens: 800,
      prompt_class: 'summarizer',
      prompt_template: 'Summarize key points with clear bullets.',
    },
  },
  {
    key: 'llm-extractor',
    label: 'LLM Extractor',
    nodeType: 'llm_call',
    description: '结构化字段提取',
    data: {
      provider: 'openai',
      model: 'gpt-4.1-mini',
      temperature: 0,
      top_p: 1,
      max_tokens: 700,
      prompt_class: 'extractor',
      prompt_template: 'Extract entities and fields in strict JSON.',
    },
  },
  {
    key: 'vec-fast',
    label: 'Vector Fast',
    nodeType: 'vector_search',
    description: '快速检索',
    data: { top_k: 5, source: 'default_corpus', rerank: false },
  },
  {
    key: 'vec-deep',
    label: 'Vector Deep',
    nodeType: 'vector_search',
    description: '深度检索+重排',
    data: { top_k: 20, source: 'default_corpus', rerank: true },
  },
  {
    key: 'filter-predicate-keep',
    label: 'Filter Predicate Keep',
    nodeType: 'filter',
    description: '表达式命中后保留',
    data: {
      strategy: 'predicate',
      predicate_expr: '={{$input.query}}',
      predicate_mode: 'keep',
    },
  },
  {
    key: 'filter-topk-desc',
    label: 'Filter TopK Desc',
    nodeType: 'filter',
    description: '按分数降序取 TopK',
    data: {
      strategy: 'topk',
      topk_k: 20,
      topk_score_field: 'score',
      topk_desc: true,
    },
  },
  {
    key: 'join-concat',
    label: 'Join Concat',
    nodeType: 'join',
    description: '字符串拼接',
    data: { strategy: 'concat', delimiter: '\\n\\n' },
  },
  {
    key: 'join-json',
    label: 'Join JSON',
    nodeType: 'join',
    description: 'JSON 合并',
    data: { strategy: 'json_merge' },
  },
]

const baseNodes: Node[] = [
  { id: 'input-1', type: 'input', position: { x: 80, y: 120 }, data: { label: 'Input', node_type: 'vector_search' } },
  {
    id: 'llm-1',
    position: { x: 360, y: 120 },
    data: {
      label: 'LLM',
      node_type: 'llm_call',
      provider: 'openai',
      model: 'gpt-4.1',
      temperature: 0.2,
      top_p: 1,
      max_tokens: 1024,
      prompt_class: 'analyst',
    },
  },
  { id: 'output-1', type: 'output', position: { x: 640, y: 120 }, data: { label: 'Output', node_type: 'join' } },
]

const baseEdges: Edge[] = [
  { id: 'e-input-llm', source: 'input-1', target: 'llm-1', animated: true },
  { id: 'e-llm-output', source: 'llm-1', target: 'output-1' },
]

const FRONT_INPUT_NODE_ID = 'frontend-input'
const DATABASE_NODE_ID = 'database-sink'
const AUTO_BRIDGE_EDGE_PREFIX = 'auto-bridge-'
const DEFAULT_FRONTEND_PAYLOAD = '{"query":""}'
const DEFAULT_DATABASE_STORE_URI = 'sqlite:///tmp/workflow.db'
const DEFAULT_DATABASE_TABLE = 'workflow_results'

type BoundaryNodeConfig = {
  frontendPayload?: string
  frontendQueryKey?: string
  databaseStoreUri?: string
  databaseTable?: string
}

function isBoundaryNodeId(nodeId: string): boolean {
  return nodeId === FRONT_INPUT_NODE_ID || nodeId === DATABASE_NODE_ID
}

function createBoundaryNodes(base: Node[], config?: BoundaryNodeConfig): Node[] {
  const nodes = base.filter((node) => !isBoundaryNodeId(node.id))
  const frontendPayload = (config?.frontendPayload || '').trim() || DEFAULT_FRONTEND_PAYLOAD
  const frontendQueryKey = (config?.frontendQueryKey || '').trim() || 'query'
  const databaseStoreUri = (config?.databaseStoreUri || '').trim() || DEFAULT_DATABASE_STORE_URI
  const databaseTable = (config?.databaseTable || '').trim() || DEFAULT_DATABASE_TABLE
  if (!nodes.length) {
    return [
      {
        id: FRONT_INPUT_NODE_ID,
        type: 'default',
        position: { x: -280, y: 120 },
        data: {
          label: 'Frontend Input',
          node_type: 'frontend_input',
          role: 'frontend_input',
          query_key: frontendQueryKey,
          input_payload: frontendPayload,
          output_vars: [{ name: frontendQueryKey || 'query', value_type: 'string', required: true }],
        },
        draggable: false,
        selectable: true,
        style: { borderColor: '#2563eb', background: '#dbeafe', color: '#1e3a8a', fontWeight: 700 },
      },
      {
        id: DATABASE_NODE_ID,
        type: 'default',
        position: { x: 980, y: 120 },
        data: {
          label: 'Database Sink',
          node_type: 'database_sink',
          role: 'database_sink',
          store_uri: databaseStoreUri,
          table: databaseTable,
          input_vars: [{ name: 'result', value_type: 'json', source: 'node_output', required: true }],
        },
        draggable: false,
        selectable: true,
        style: { borderColor: '#0f766e', background: '#ccfbf1', color: '#134e4a', fontWeight: 700 },
      },
    ]
  }
  const xs = nodes.map((item) => item.position.x)
  const ys = nodes.map((item) => item.position.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const centerY = ys.reduce((acc, value) => acc + value, 0) / ys.length
  return [
    {
      id: FRONT_INPUT_NODE_ID,
      type: 'default',
      position: { x: minX - 360, y: centerY },
      data: {
        label: 'Frontend Input',
        node_type: 'frontend_input',
        role: 'frontend_input',
        query_key: frontendQueryKey,
        input_payload: frontendPayload,
        output_vars: [{ name: frontendQueryKey || 'query', value_type: 'string', required: true }],
      },
      draggable: false,
      selectable: true,
      style: { borderColor: '#2563eb', background: '#dbeafe', color: '#1e3a8a', fontWeight: 700 },
    },
    {
      id: DATABASE_NODE_ID,
      type: 'default',
      position: { x: maxX + 360, y: centerY },
      data: {
        label: 'Database Sink',
        node_type: 'database_sink',
        role: 'database_sink',
        store_uri: databaseStoreUri,
        table: databaseTable,
        input_vars: [{ name: 'result', value_type: 'json', source: 'node_output', required: true }],
      },
      draggable: false,
      selectable: true,
      style: { borderColor: '#0f766e', background: '#ccfbf1', color: '#134e4a', fontWeight: 700 },
    },
  ]
}

function ensureBoundaryNodes(base: Node[], config?: BoundaryNodeConfig): Node[] {
  const frontendExisting = base.find((node) => node.id === FRONT_INPUT_NODE_ID)
  const databaseExisting = base.find((node) => node.id === DATABASE_NODE_ID)
  const nonBoundaryNodes = base.filter((node) => !isBoundaryNodeId(node.id))
  const [frontendDefault, databaseDefault] = createBoundaryNodes(nonBoundaryNodes, config)
  const frontendNode = frontendExisting
    ? { ...frontendExisting, draggable: false, selectable: true, style: frontendDefault.style }
    : frontendDefault
  const databaseNode = databaseExisting
    ? { ...databaseExisting, draggable: false, selectable: true, style: databaseDefault.style }
    : databaseDefault
  return [...nonBoundaryNodes, frontendNode, databaseNode]
}

function buildAutoBridgeEdges(nodes: Node[], edges: Edge[]): Edge[] {
  const dataNodes = nodes.filter((node) => !isBoundaryNodeId(node.id))
  if (!dataNodes.length) return []
  const edgeKeySet = new Set(edges.map((edge) => `${edge.source}::${edge.target}`))
  const inDegree = new Map<string, number>()
  const outDegree = new Map<string, number>()
  for (const node of dataNodes) {
    inDegree.set(node.id, 0)
    outDegree.set(node.id, 0)
  }
  for (const edge of edges) {
    if (!inDegree.has(edge.target) || !outDegree.has(edge.source)) continue
    inDegree.set(edge.target, (inDegree.get(edge.target) || 0) + 1)
    outDegree.set(edge.source, (outDegree.get(edge.source) || 0) + 1)
  }
  const heads = dataNodes.filter((node) => (inDegree.get(node.id) || 0) === 0 && node.type !== 'output')
  const tails = dataNodes.filter((node) => (outDegree.get(node.id) || 0) === 0 && node.type !== 'input')
  const normalizedHeads = heads.length ? heads : [...dataNodes].sort((a, b) => a.position.x - b.position.x).slice(0, 1)
  const normalizedTails = tails.length ? tails : [...dataNodes].sort((a, b) => b.position.x - a.position.x).slice(0, 1)

  const bridgeEdges: Edge[] = []
  for (const head of normalizedHeads) {
    const key = `${FRONT_INPUT_NODE_ID}::${head.id}`
    if (edgeKeySet.has(key)) continue
    bridgeEdges.push({
      id: `${AUTO_BRIDGE_EDGE_PREFIX}in-${head.id}`,
      source: FRONT_INPUT_NODE_ID,
      target: head.id,
      type: 'smoothstep',
      label: 'frontend input',
      animated: true,
      style: { stroke: '#2563eb', strokeDasharray: '6 5', strokeWidth: 1.8 },
      labelStyle: { fill: '#1d4ed8', fontSize: 11, fontWeight: 600 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#2563eb' },
    })
  }
  for (const tail of normalizedTails) {
    const key = `${tail.id}::${DATABASE_NODE_ID}`
    if (edgeKeySet.has(key)) continue
    bridgeEdges.push({
      id: `${AUTO_BRIDGE_EDGE_PREFIX}out-${tail.id}`,
      source: tail.id,
      target: DATABASE_NODE_ID,
      type: 'smoothstep',
      label: 'persist',
      animated: true,
      style: { stroke: '#0f766e', strokeDasharray: '6 5', strokeWidth: 1.8 },
      labelStyle: { fill: '#0f766e', fontSize: 11, fontWeight: 600 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#0f766e' },
    })
  }
  return bridgeEdges
}

function inferNodeType(node: Node): NodeType {
  const raw = String((node.data as { node_type?: unknown })?.node_type || node.id || '').toLowerCase()
  if (raw.includes('frontend_input')) return 'frontend_input'
  if (raw.includes('database_sink')) return 'database_sink'
  if (raw.includes('filter')) return 'filter'
  if (raw.includes('llm') || raw.includes('model')) return 'llm_call'
  if (raw.includes('join') || raw.includes('merge')) return 'join'
  return 'vector_search'
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function asList(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return []
  return value.map((item) => asObject(item)).filter((item) => Object.keys(item).length > 0)
}

function asKey(value: unknown, fallback: string): string {
  const next = String(value || '').trim()
  return next || fallback
}

function validateNodeConfigDraft(data: Record<string, unknown>): string | null {
  const inputVars = asList(data.input_vars)
  for (const item of inputVars) {
    const name = asKey(item.name, '')
    if (!name) return 'Input variable name is required'
    const source = asKey(item.source, 'input')
    if (source === 'node_output') {
      if (!asKey(item.from_node, '')) return `Input '${name}' missing from_node`
      if (!asKey(item.from_key, '')) return `Input '${name}' missing from_key`
    }
    if (source === 'expression' && !asKey(item.expr, '')) {
      return `Input '${name}' missing expr`
    }
  }
  return null
}

function resolveNodeType(raw: unknown): NodeType {
  const value = String(raw || '').trim().toLowerCase()
  if (value === 'frontend_input' || value === 'frontend') return 'frontend_input'
  if (value === 'database_sink' || value === 'database' || value === 'sink') return 'database_sink'
  if (value === 'filter') return 'filter'
  if (value === 'llm_call' || value === 'llm' || value === 'model') return 'llm_call'
  if (value === 'join' || value === 'merge') return 'join'
  return 'vector_search'
}

function pickModuleMeta(data: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  Object.entries(data).forEach(([key, value]) => {
    if (key.startsWith('module_')) out[key] = value
  })
  return out
}

function normalizeTemplateData(template: NodeTemplate, existingData?: Record<string, unknown>): Record<string, unknown> {
  const preservedMeta = existingData ? pickModuleMeta(existingData) : {}
  return {
    ...(existingData || {}),
    ...template.data,
    ...preservedMeta,
    node_type: template.nodeType,
  }
}

function createConnectedInputVars(sourceNode: Node, targetNode: Node): Array<Record<string, unknown>> {
  const sourceData = asObject(sourceNode.data)
  const targetData = asObject(targetNode.data)
  const sourceOutputs = asList(sourceData.output_vars)
  const outputKeys = (sourceOutputs.length
    ? sourceOutputs.map((item) => asKey(item.name, 'output'))
    : ['output'])
  const sourceNodeType = resolveNodeType((sourceData as { node_type?: unknown }).node_type || sourceNode.id)
  const sourceValueType = asKey(sourceData.output_type, 'string')
  const sourceKind = SOURCE_TYPE_BY_NODE[sourceNodeType]

  const nextInputs = [...asList(targetData.input_vars)]
  for (const outputKey of outputKeys) {
    const inputName = `${sourceNode.id}.${outputKey}`
    const exists = nextInputs.some((item) => asKey(item.name, '') === inputName)
    if (exists) continue
    nextInputs.push({
      name: inputName,
      value_type: sourceValueType,
      source: 'node_output',
      source_type: sourceKind,
      from_node: sourceNode.id,
      from_key: outputKey,
      from_node_type: sourceNodeType,
      required: false,
    })
  }
  return nextInputs
}

function DesignerCanvas({ onExportDsl }: LlmDesignerPageProps) {
  const isStorybookCanvas = useMemo(isStorybookIframe, [])
  const linkParams = useMemo(readDesignerLinkParams, [])
  const boundaryConfig = useMemo<BoundaryNodeConfig>(
    () => ({
      frontendPayload: linkParams.frontendPayload,
      frontendQueryKey: linkParams.frontendQueryKey,
      databaseStoreUri: linkParams.databaseStoreUri,
      databaseTable: linkParams.databaseTable,
    }),
    [linkParams.databaseStoreUri, linkParams.databaseTable, linkParams.frontendPayload, linkParams.frontendQueryKey],
  )
  const templateCatalog = useMemo(createTemplateCatalog, [])
  const resolvedTemplateKey = useMemo(() => {
    const key = linkParams.templateKey
    if (!key) return templateCatalog[2]?.key || 'llm-call'
    return templateCatalog.some((item) => item.key === key) ? key : (templateCatalog[2]?.key || 'llm-call')
  }, [linkParams.templateKey, templateCatalog])

  const [nodes, setNodes, onNodesChange] = useNodesState(ensureBoundaryNodes(baseNodes, boundaryConfig))
  const [edges, setEdges, onEdgesChange] = useEdgesState(baseEdges)
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([])
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<string[]>([])
  const [selectedTemplateKey, setSelectedTemplateKey] = useState(resolvedTemplateKey)
  const [jsonDraft, setJsonDraft] = useState('')
  const [status, setStatus] = useState('Ready')
  const [graphId, setGraphId] = useState(linkParams.graphId)
  const [runId, setRunId] = useState(linkParams.runId)
  const [runInputText, setRunInputText] = useState(linkParams.runInputText)
  const [compileResultText, setCompileResultText] = useState('')
  const [runResultText, setRunResultText] = useState('')
  const [busyAction, setBusyAction] = useState('')
  const [fromNodeId, setFromNodeId] = useState(linkParams.fromNodeId)
  const [toNodeId, setToNodeId] = useState(linkParams.toNodeId)
  const [selectedPresetKey, setSelectedPresetKey] = useState<string>(DEFAULT_WORKFLOW_LINK_PRESET_KEY)
  const [isNodeSidebarCollapsed, setIsNodeSidebarCollapsed] = useState(isStorybookCanvas)
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(isStorybookCanvas ? 240 : 320)
  const [rightStackWidth, setRightStackWidth] = useState(isStorybookCanvas ? 360 : 520)
  const [nodeSidebarQuery, setNodeSidebarQuery] = useState('')
  const [panelCollapsed, setPanelCollapsed] = useState<Record<CanvasPanelKey, boolean>>({
    templates: isStorybookCanvas,
    p2p: true,
    preset: true,
    runtime: isStorybookCanvas,
    json: true,
    results: isStorybookCanvas,
  })

  const [editingNodeId, setEditingNodeId] = useState(linkParams.nodeId)
  const [nodeInfoDraft, setNodeInfoDraft] = useState('{}')
  const [nodeInfoCard, setNodeInfoCard] = useState({ open: Boolean(linkParams.nodeId), x: 20, y: 20, width: 420, height: 420 })
  const [activeResize, setActiveResize] = useState<null | { target: 'left' | 'right'; startX: number; startWidth: number }>(null)

  const nextIdRef = useRef(2)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const flowRef = useRef<ReactFlowInstance<Node, Edge> | null>(null)
  const canvasRef = useRef<HTMLDivElement | null>(null)

  const selectedCount = selectedNodeIds.length + selectedEdgeIds.length
  const bridgeEdges = useMemo(() => buildAutoBridgeEdges(nodes, edges), [edges, nodes])
  const allEdges = useMemo(() => [...edges, ...bridgeEdges], [bridgeEdges, edges])
  const selectedNode = useMemo(() => {
    if (!editingNodeId) return null
    return nodes.find((item) => item.id === editingNodeId) || null
  }, [editingNodeId, nodes])
  const selectedNodeType = useMemo(() => (selectedNode ? inferNodeType(selectedNode) : null), [selectedNode])
  const selectedNodeProfiles = useMemo(
    () => (selectedNodeType ? NODE_INFO_PROFILES.filter((item) => item.nodeType === selectedNodeType) : []),
    [selectedNodeType],
  )
  const selectedNodeSchema = useMemo(
    () => (selectedNodeType ? getNodeSchema(selectedNodeType) : null),
    [selectedNodeType],
  )
  const availableNodeOutputs = useMemo<NodeOutputOption[]>(() => {
    if (!selectedNode) return []
    const upstreamNodeIds = new Set(edges.filter((edge) => edge.target === selectedNode.id).map((edge) => edge.source))
    const outputMap = new Map<string, Set<string>>()
    const labelMap = new Map<string, string>()
    for (const node of nodes) {
      if (node.id === selectedNode.id || !upstreamNodeIds.has(node.id)) continue
      const nodeData = asObject(node.data)
      const outputs = asList(nodeData.output_vars)
      const nodeLabel = asKey(nodeData.label, node.id)
      labelMap.set(node.id, nodeLabel)
      const outputSet = outputMap.get(node.id) || new Set<string>()
      if (!outputs.length) {
        outputSet.add('output')
        outputMap.set(node.id, outputSet)
        continue
      }
      for (const output of outputs) {
        outputSet.add(asKey(output.name, 'output'))
      }
      outputMap.set(node.id, outputSet)
    }
    return Array.from(outputMap.entries()).map(([nodeId, keys]) => ({
      nodeId,
      nodeLabel: labelMap.get(nodeId) || nodeId,
      outputKeys: Array.from(keys),
    }))
  }, [edges, nodes, selectedNode])
  const availableVariables = useMemo<string[]>(() => {
    const out = new Set<string>(['$input.query', '$input.state', '$input.prompt'])
    try {
      const parsed = JSON.parse(runInputText || '{}') as Record<string, unknown>
      Object.keys(parsed || {}).forEach((key) => out.add(`$input.${key}`))
    } catch {
      // ignore invalid run input JSON for variable hints
    }
    for (const item of availableNodeOutputs) {
      for (const key of item.outputKeys) out.add(`$node.${item.nodeId}.${key}`)
    }
    return Array.from(out)
  }, [availableNodeOutputs, runInputText])

  useEffect(() => {
    if (!editingNodeId) return
    if (nodes.some((item) => item.id === editingNodeId)) return
    setEditingNodeId('')
    setNodeInfoCard((prev) => ({ ...prev, open: false }))
  }, [editingNodeId, nodes])

  useEffect(() => {
    if (isStorybookCanvas) return
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    const collapsedWidth = 56
    const effectiveLeft = isNodeSidebarCollapsed ? collapsedWidth : leftSidebarWidth
    const maxLeft = Math.max(240, Math.min(560, rect.width - rightStackWidth - 120))
    const maxRight = Math.max(320, Math.min(760, rect.width - effectiveLeft - 120))
    setLeftSidebarWidth((prev) => Math.min(maxLeft, Math.max(240, prev)))
    setRightStackWidth((prev) => Math.min(maxRight, Math.max(320, prev)))
  }, [isNodeSidebarCollapsed, isStorybookCanvas, leftSidebarWidth, rightStackWidth])

  useEffect(() => {
    if (!activeResize) return
    const onPointerMove = (event: PointerEvent) => {
      const rect = canvasRef.current?.getBoundingClientRect()
      if (!rect) return
      if (activeResize.target === 'left') {
        const delta = event.clientX - activeResize.startX
        const nextRaw = activeResize.startWidth + delta
        const maxLeft = Math.max(240, Math.min(560, rect.width - rightStackWidth - 120))
        setLeftSidebarWidth(Math.min(maxLeft, Math.max(240, nextRaw)))
        return
      }
      const delta = activeResize.startX - event.clientX
      const nextRaw = activeResize.startWidth + delta
      const effectiveLeft = isNodeSidebarCollapsed ? 56 : leftSidebarWidth
      const maxRight = Math.max(320, Math.min(760, rect.width - effectiveLeft - 120))
      setRightStackWidth(Math.min(maxRight, Math.max(320, nextRaw)))
    }

    const onPointerUp = () => {
      setActiveResize(null)
    }

    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
    document.body.style.cursor = activeResize.target === 'left' ? 'ew-resize' : 'col-resize'
    return () => {
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
      document.body.style.cursor = ''
    }
  }, [activeResize, isNodeSidebarCollapsed, leftSidebarWidth, rightStackWidth])

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target || connection.source === connection.target) return
      if (connection.source === DATABASE_NODE_ID || connection.target === FRONT_INPUT_NODE_ID) {
        setStatus('Connect failed: invalid direction for boundary endpoints')
        return
      }
      const edgeId = `e-${connection.source ?? 'unknown'}-${connection.target ?? 'unknown'}-${Date.now()}`
      setEdges((current) => {
        const exists = current.some((edge) => edge.source === connection.source && edge.target === connection.target)
        if (exists) return current
        return addEdge({ ...connection, id: edgeId }, current)
      })
      setNodes((currentNodes) => {
        const sourceNode = currentNodes.find((item) => item.id === connection.source)
        const targetNode = currentNodes.find((item) => item.id === connection.target)
        if (!sourceNode || !targetNode) return currentNodes
        const nextInputs = createConnectedInputVars(sourceNode, targetNode)
        const targetData = asObject(targetNode.data)
        return currentNodes.map((node) =>
          node.id === connection.target
            ? { ...node, data: { ...targetData, input_vars: nextInputs } }
            : node,
        )
      })
      setStatus('Connected')
    },
    [setEdges, setNodes],
  )

  const addTemplateNode = useCallback((templateItem?: NodeTemplatePaletteItem<Record<string, unknown>>) => {
    const template = templateCatalog.find((item) => item.key === (templateItem?.key || selectedTemplateKey)) || templateCatalog[2]
    if (!template) return
    const id = `${template.key}-${nextIdRef.current}`
    nextIdRef.current += 1
    const nextNode: Node = {
      id,
      position: { x: 160 + nodes.length * 24, y: 160 + nodes.length * 18 },
      data: { ...normalizeTemplateData(template), label: `${template.label} ${nextIdRef.current - 1}` },
    }
    setNodes((current) => ensureBoundaryNodes([...current, nextNode], boundaryConfig))
    setStatus(`Added template node: ${template.label}`)
  }, [nodes.length, selectedTemplateKey, setNodes, templateCatalog, boundaryConfig])

  const applyTemplateToSelected = useCallback((templateItem?: NodeTemplatePaletteItem<Record<string, unknown>>) => {
    if (selectedNodeIds.length !== 1) {
      setStatus('Apply template failed: select exactly one node')
      return
    }
    const template = templateCatalog.find((item) => item.key === (templateItem?.key || selectedTemplateKey)) || templateCatalog[2]
    if (!template) return
    const targetNodeId = selectedNodeIds[0]
    if (isBoundaryNodeId(targetNodeId)) {
      setStatus('Apply template failed: boundary endpoint template is fixed')
      return
    }
    setNodes((current) =>
      current.map((node) =>
        node.id === targetNodeId
          ? {
              ...node,
              data: {
                ...normalizeTemplateData(template, asObject(node.data)),
                label: `${template.label} ${targetNodeId}`,
              },
            }
          : node,
      ),
    )
    setStatus(`Applied template ${template.label} to ${targetNodeId}`)
  }, [selectedNodeIds, selectedTemplateKey, setNodes, templateCatalog])

  const connectPointToPoint = useCallback(() => {
    const source = fromNodeId.trim()
    const target = toNodeId.trim()
    if (!source || !target || source === target) {
      setStatus('P2P connect failed: choose valid from/to nodes')
      return
    }
    const sourceExists = nodes.some((item) => item.id === source)
    const targetExists = nodes.some((item) => item.id === target)
    if (!sourceExists || !targetExists) {
      setStatus('P2P connect failed: node not found')
      return
    }
    if (source === DATABASE_NODE_ID || target === FRONT_INPUT_NODE_ID) {
      setStatus('P2P connect failed: invalid direction for boundary endpoints')
      return
    }
    setEdges((current) => {
      const exists = current.some((edge) => edge.source === source && edge.target === target)
      if (exists) return current
      return addEdge({ id: `e-${source}-${target}-${current.length + 1}`, source, target }, current)
    })
    setNodes((currentNodes) => {
      const sourceNode = currentNodes.find((item) => item.id === source)
      const targetNode = currentNodes.find((item) => item.id === target)
      if (!sourceNode || !targetNode) return currentNodes
      const nextInputs = createConnectedInputVars(sourceNode, targetNode)
      const targetData = asObject(targetNode.data)
      return currentNodes.map((node) =>
        node.id === target
          ? { ...node, data: { ...targetData, input_vars: nextInputs } }
          : node,
      )
    })
    setStatus(`Connected ${source} -> ${target}`)
  }, [fromNodeId, nodes, setEdges, setNodes, toNodeId])

  const removeSelection = useCallback(() => {
    if (!selectedCount) return
    setNodes((current) =>
      current.filter((node) => !selectedNodeIds.includes(node.id) || isBoundaryNodeId(node.id)),
    )
    setEdges((current) => current.filter((edge) => !selectedEdgeIds.includes(edge.id)))
    setStatus(`Removed ${selectedCount} selected item(s)`)
  }, [selectedCount, selectedEdgeIds, selectedNodeIds, setEdges, setNodes])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.key === 'Delete' || event.key === 'Backspace') && (selectedNodeIds.length || selectedEdgeIds.length)) {
        event.preventDefault()
        setNodes((current) =>
          current.filter((node) => !selectedNodeIds.includes(node.id) || isBoundaryNodeId(node.id)),
        )
        setEdges((current) => current.filter((edge) => !selectedEdgeIds.includes(edge.id)))
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedEdgeIds, selectedNodeIds, setEdges, setNodes])

  const resetGraph = useCallback(() => {
    setNodes(ensureBoundaryNodes(baseNodes, boundaryConfig))
    setEdges(baseEdges)
    setSelectedNodeIds([])
    setSelectedEdgeIds([])
    setStatus('Reset to template')
    window.requestAnimationFrame(() => {
      flowRef.current?.fitView({ duration: 300, padding: 0.2 })
    })
  }, [boundaryConfig, setEdges, setNodes])

  const collectDsl = useCallback((): DesignerDsl => {
    const viewport = flowRef.current?.getViewport()
    return { version: '1.0', nodes, edges: allEdges, viewport, meta: { updatedAt: new Date().toISOString() } }
  }, [allEdges, nodes])

  const exportDsl = useCallback(() => {
    const dsl = collectDsl()
    const json = JSON.stringify(dsl, null, 2)
    setJsonDraft(json)
    onExportDsl?.(dsl)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `llm-designer-dsl-${Date.now()}.json`
    link.click()
    URL.revokeObjectURL(url)
    setStatus('Exported DSL')
  }, [collectDsl, onExportDsl])

  const importDslFromText = useCallback((text: string) => {
    const parsed = JSON.parse(text) as Partial<DesignerDsl>
    if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
      throw new Error('JSON must include nodes[] and edges[]')
    }
    setNodes(ensureBoundaryNodes(parsed.nodes as Node[], boundaryConfig))
    setEdges(parsed.edges as Edge[])
    if (parsed.viewport) {
      window.requestAnimationFrame(() => {
        flowRef.current?.setViewport(parsed.viewport as Viewport, { duration: 280 })
      })
    }
  }, [boundaryConfig, setEdges, setNodes])

  const onImportJson = useCallback(() => {
    try {
      importDslFromText(jsonDraft)
      setStatus('Imported from JSON text')
    } catch (error) {
      setStatus(`Import failed: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }, [importDslFromText, jsonDraft])

  const onCompileGraph = useCallback(async () => {
    setBusyAction('compile')
    try {
      const response = await compileWorkflowGraph({
        graph_id: graphId.trim() || undefined,
        dsl: {
          version: '1.0',
          options: { source: 'xyflow' },
          nodes: nodes.map((node) => ({
            node_id: String(node.id),
            node_type: inferNodeType(node),
            config: { label: String((node.data as { label?: unknown })?.label || node.id), ...((node.data || {}) as Record<string, unknown>) },
          })),
          edges: allEdges.map((edge) => ({ from: edge.source, to: edge.target })),
        },
      })
      const nextGraphId = String(response.graph_id || '').trim()
      if (nextGraphId) setGraphId(nextGraphId)
      setCompileResultText(JSON.stringify(response, null, 2))
      setStatus(nextGraphId ? `Compiled graph: ${nextGraphId}` : 'Compiled')
    } catch (error) {
      setStatus(`Compile failed: ${error instanceof Error ? error.message : 'unknown error'}`)
    } finally {
      setBusyAction('')
    }
  }, [graphId, nodes, allEdges])

  const onRunGraph = useCallback(async () => {
    const targetGraphId = graphId.trim()
    if (!targetGraphId) {
      setStatus('Run failed: graph_id required')
      return
    }
    setBusyAction('run')
    try {
      const input = JSON.parse(runInputText || '{}') as Record<string, unknown>
      const response = await runWorkflowGraph({ graph_id: targetGraphId, input })
      const nextRunId = String(response.run_id || '').trim()
      if (nextRunId) setRunId(nextRunId)
      setRunResultText(JSON.stringify(response, null, 2))
      setStatus(nextRunId ? `Run started: ${nextRunId}` : 'Run submitted')
    } catch (error) {
      setStatus(`Run failed: ${error instanceof Error ? error.message : 'unknown error'}`)
    } finally {
      setBusyAction('')
    }
  }, [graphId, runInputText])

  const onGetRunDetail = useCallback(async () => {
    const targetRunId = runId.trim()
    if (!targetRunId) {
      setStatus('Run detail failed: run_id required')
      return
    }
    setBusyAction('run-detail')
    try {
      const response = await getWorkflowGraphRun(targetRunId)
      setRunResultText(JSON.stringify(response, null, 2))
      setStatus(`Fetched run detail: ${targetRunId}`)
    } catch (error) {
      setStatus(`Run detail failed: ${error instanceof Error ? error.message : 'unknown error'}`)
    } finally {
      setBusyAction('')
    }
  }, [runId])

  const onGetRunEvents = useCallback(async () => {
    const targetRunId = runId.trim()
    if (!targetRunId) {
      setStatus('Run events failed: run_id required')
      return
    }
    setBusyAction('run-events')
    try {
      const response = await getWorkflowGraphRunEvents(targetRunId)
      setRunResultText(JSON.stringify(response, null, 2))
      setStatus(`Fetched run events: ${targetRunId}`)
    } catch (error) {
      setStatus(`Run events failed: ${error instanceof Error ? error.message : 'unknown error'}`)
    } finally {
      setBusyAction('')
    }
  }, [runId])

  const onGetCompiledGraph = useCallback(async () => {
    const targetGraphId = graphId.trim()
    if (!targetGraphId) {
      setStatus('Compiled graph query failed: graph_id required')
      return
    }
    setBusyAction('compiled')
    try {
      const response = await getCompiledWorkflowGraph(targetGraphId)
      setCompileResultText(JSON.stringify(response, null, 2))
      setStatus(`Fetched compiled graph: ${targetGraphId}`)
    } catch (error) {
      setStatus(`Compiled graph query failed: ${error instanceof Error ? error.message : 'unknown error'}`)
    } finally {
      setBusyAction('')
    }
  }, [graphId])

  const applyInfoProfileByKey = useCallback((profileKey: string) => {
    if (!selectedNode || !selectedNodeType) {
      setStatus('Apply node info template failed: select one node')
      return
    }
    const profile = NODE_INFO_PROFILES.find((item) => item.key === profileKey && item.nodeType === selectedNodeType)
    if (!profile) {
      setStatus('Apply node info template failed: choose template')
      return
    }
    const nextData = {
      ...(selectedNode.data || {}),
      ...profile.data,
      node_type: selectedNodeType,
      label: String((selectedNode.data as { label?: unknown })?.label || selectedNode.id),
    }
    setNodes((current) => current.map((node) => (node.id === selectedNode.id ? { ...node, data: nextData } : node)))
    setNodeInfoDraft(JSON.stringify(nextData, null, 2))
    setStatus(`Applied node info template: ${profile.label}`)
  }, [selectedNode, selectedNodeType, setNodes])

  const saveNodeInfoDraft = useCallback(() => {
    if (!selectedNode || !selectedNodeType) {
      setStatus('Save node info failed: select one node')
      return
    }
    try {
      const parsed = JSON.parse(nodeInfoDraft || '{}') as Record<string, unknown>
      const validationError = validateNodeConfigDraft(parsed)
      if (validationError) {
        setStatus(`Save node info failed: ${validationError}`)
        return
      }
      const nextData = {
        ...(selectedNode.data || {}),
        ...parsed,
        node_type: selectedNodeType,
        label: String(parsed.label || (selectedNode.data as { label?: unknown })?.label || selectedNode.id),
      }
      setNodes((current) => current.map((node) => (node.id === selectedNode.id ? { ...node, data: nextData } : node)))
      setStatus(`Saved node info: ${selectedNode.id}`)
    } catch (error) {
      setStatus(`Save node info failed: ${error instanceof Error ? error.message : 'invalid JSON'}`)
    }
  }, [nodeInfoDraft, selectedNode, selectedNodeType, setNodes])

  const handleCardMove = useCallback((x: number, y: number) => {
    const rect = canvasRef.current?.getBoundingClientRect()
    const maxX = rect ? Math.max(0, rect.width - 160) : Number.MAX_SAFE_INTEGER
    const maxY = rect ? Math.max(0, rect.height - 80) : Number.MAX_SAFE_INTEGER
    setNodeInfoCard((prev) => ({ ...prev, x: Math.min(maxX, Math.max(0, x)), y: Math.min(maxY, Math.max(0, y)) }))
  }, [])

  const handleCardResize = useCallback((payload: { x: number; y: number; width: number; height: number }) => {
    const rect = canvasRef.current?.getBoundingClientRect()
    const maxWidth = rect ? Math.max(300, rect.width - 8) : payload.width
    const maxHeight = rect ? Math.max(220, rect.height - 8) : payload.height
    setNodeInfoCard((prev) => ({
      ...prev,
      x: Math.max(0, payload.x),
      y: Math.max(0, payload.y),
      width: Math.min(maxWidth, Math.max(300, payload.width)),
      height: Math.min(maxHeight, Math.max(220, payload.height)),
    }))
  }, [])

  const statsText = `Nodes ${nodes.length} · Edges ${allEdges.length}`

  const addNodeAtPoint = useCallback((clientX: number, clientY: number) => {
    const instance = flowRef.current
    if (!instance) return
    const template = templateCatalog.find((item) => item.key === selectedTemplateKey) || templateCatalog[2]
    if (!template) return
    const position = instance.screenToFlowPosition({ x: clientX, y: clientY })
    const id = `${template.key}-${nextIdRef.current}`
    nextIdRef.current += 1
    const nextNode: Node = {
      id,
      position,
      data: { ...normalizeTemplateData(template), label: `${template.label} ${nextIdRef.current - 1}` },
    }
    setNodes((current) => ensureBoundaryNodes([...current, nextNode], boundaryConfig))
    setStatus(`Added node at cursor: ${id}`)
  }, [selectedTemplateKey, setNodes, templateCatalog, boundaryConfig])

  const generatePresetChain = useCallback(() => {
    const preset = WORKFLOW_LINK_PRESET_BY_KEY[selectedPresetKey as keyof typeof WORKFLOW_LINK_PRESET_BY_KEY]
    if (!preset) {
      setStatus('Preset generation failed: choose valid preset')
      return
    }
    const templateByKey = new Map(templateCatalog.map((item) => [item.key, item]))
    const startIndex = Date.now()
    const idMap = new Map<string, string>()
    const nextNodes: Node[] = preset.nodes.map((presetNode, index) => {
      const template = templateByKey.get(presetNode.templateKey)
      if (!template) {
        return {
          id: `${presetNode.id}-${startIndex + index}`,
          position: presetNode.position,
          data: { label: `Missing template: ${presetNode.templateKey}`, node_type: 'join' },
        }
      }
      const nextId = `${presetNode.id}-${startIndex + index}`
      idMap.set(presetNode.id, nextId)
      return {
        id: nextId,
        position: presetNode.position,
        data: {
          ...normalizeTemplateData(template, asObject(presetNode.overrides)),
          label: `${template.label} ${index + 1}`,
        },
      }
    })

    const nextEdges: Edge[] = preset.edges
      .map((edge, index) => {
        const source = idMap.get(edge.source)
        const target = idMap.get(edge.target)
        if (!source || !target) return null
        return {
          id: `${edge.id}-${startIndex + index}`,
          source,
          target,
          label: edge.label,
          animated: true,
        } as Edge
      })
      .filter((item): item is Edge => Boolean(item))

    const enrichedNodes = nextNodes.map((node) => {
      const upstream = nextEdges.filter((edge) => edge.target === node.id).map((edge) => edge.source)
      if (!upstream.length) return node
      const inputVars = upstream.flatMap((sourceId) => {
        const sourceNode = nextNodes.find((item) => item.id === sourceId)
        if (!sourceNode) return []
        return createConnectedInputVars(sourceNode, node)
      })
      if (!inputVars.length) return node
      return {
        ...node,
        data: {
          ...asObject(node.data),
          input_vars: inputVars,
        },
      }
    })

    setNodes(ensureBoundaryNodes(enrichedNodes, boundaryConfig))
    setEdges(nextEdges)
    setSelectedNodeIds([])
    setSelectedEdgeIds([])
    setStatus(`Generated preset chain: ${preset.label}`)
    window.requestAnimationFrame(() => {
      flowRef.current?.fitView({ duration: 260, padding: 0.2 })
    })
  }, [selectedPresetKey, setEdges, setNodes, templateCatalog, boundaryConfig])

  const selectedPreset = useMemo(
    () => WORKFLOW_LINK_PRESET_BY_KEY[selectedPresetKey as keyof typeof WORKFLOW_LINK_PRESET_BY_KEY] || null,
    [selectedPresetKey],
  )
  const startLeftResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    if (isNodeSidebarCollapsed) return
    event.preventDefault()
    event.stopPropagation()
    setActiveResize({ target: 'left', startX: event.clientX, startWidth: leftSidebarWidth })
  }, [isNodeSidebarCollapsed, leftSidebarWidth])
  const startRightResize = useCallback((event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.stopPropagation()
    setActiveResize({ target: 'right', startX: event.clientX, startWidth: rightStackWidth })
  }, [rightStackWidth])
  const togglePanel = useCallback((key: CanvasPanelKey) => {
    setPanelCollapsed((prev) => ({ ...prev, [key]: !prev[key] }))
  }, [])
  const renderCanvasPanel = useCallback((key: CanvasPanelKey, title: string, content: ReactNode) => {
    const collapsed = Boolean(panelCollapsed[key])
    return (
      <section className={`llm-canvas-panel ${collapsed ? 'is-collapsed' : ''}`}>
        <header className="llm-canvas-panel__head">
          <button type="button" onClick={() => togglePanel(key)}>
            {collapsed ? '▶' : '▼'} {title}
          </button>
        </header>
        {collapsed ? null : <div className="llm-canvas-panel__body">{content}</div>}
      </section>
    )
  }, [panelCollapsed, togglePanel])
  const filteredNodes = useMemo(() => {
    const query = nodeSidebarQuery.trim().toLowerCase()
    if (!query) return nodes
    return nodes.filter((node) => {
      const nodeData = asObject(node.data)
      const label = asKey(nodeData.label, '')
      const nodeType = asKey(nodeData.node_type, '')
      return `${node.id} ${label} ${nodeType}`.toLowerCase().includes(query)
    })
  }, [nodeSidebarQuery, nodes])

  const openNodeCardById = useCallback((nodeId: string) => {
    const targetNode = nodes.find((item) => item.id === nodeId)
    if (!targetNode) {
      setStatus(`Node not found: ${nodeId}`)
      return
    }
    const cardX = isNodeSidebarCollapsed ? 24 : leftSidebarWidth + 24
    setEditingNodeId(nodeId)
    setSelectedNodeIds([nodeId])
    setNodeInfoDraft(JSON.stringify((targetNode.data || {}) as Record<string, unknown>, null, 2))
    setNodeInfoCard((prev) => ({ ...prev, open: true, x: cardX, y: 28 }))
    setFromNodeId((prev) => prev || nodeId)
    setToNodeId((prev) => (prev && prev !== nodeId ? prev : ''))
  }, [isNodeSidebarCollapsed, leftSidebarWidth, nodes])

  const focusNodeById = useCallback((nodeId: string) => {
    const targetNode = nodes.find((item) => item.id === nodeId)
    const instance = flowRef.current
    if (!targetNode || !instance) {
      setStatus(`Focus failed: ${nodeId}`)
      return
    }
    const zoom = Math.max(instance.getZoom(), 1)
    void instance.setCenter(targetNode.position.x + 120, targetNode.position.y + 32, { duration: 260, zoom })
    setStatus(`Focused node: ${nodeId}`)
  }, [nodes])

  const deleteNodeById = useCallback((nodeId: string) => {
    if (isBoundaryNodeId(nodeId)) {
      setStatus(`Delete blocked: ${nodeId} is a fixed endpoint`)
      return
    }
    if (!nodes.some((item) => item.id === nodeId)) {
      setStatus(`Delete failed: ${nodeId}`)
      return
    }
    setNodes((current) => current.filter((node) => node.id !== nodeId))
    setEdges((current) => current.filter((edge) => edge.source !== nodeId && edge.target !== nodeId))
    setSelectedNodeIds((current) => current.filter((id) => id !== nodeId))
    setSelectedEdgeIds([])
    if (editingNodeId === nodeId) {
      setEditingNodeId('')
      setNodeInfoCard((prev) => ({ ...prev, open: false }))
    }
    setStatus(`Deleted node: ${nodeId}`)
  }, [editingNodeId, nodes, setEdges, setNodes])

  return (
    <section className="llm-designer-page llm-designer-page--full llm-designer-page--quiet">
      <header className="llm-designer-header">
        <div className="llm-designer-header__copy">
          <small>workflow composition</small>
          <h2>LLM Designer</h2>
          <p>让模板、连线、运行态和结果检查留在同一块安静的画布里，而不是变成一组过度抢眼的控制台。</p>
        </div>
        <div className="llm-designer-header__stats">{statsText}</div>
      </header>

      <div
        className="llm-designer-canvas"
        ref={canvasRef}
        style={{ position: 'relative' }}
        onDoubleClick={(event) => {
          const target = event.target as HTMLElement
          if (!target.closest('.react-flow__pane')) return
          addNodeAtPoint(event.clientX, event.clientY)
        }}
      >
        <aside
          className={`llm-canvas-left-sidebar ${isNodeSidebarCollapsed ? 'is-collapsed' : ''}`.trim()}
          style={{
            position: 'absolute',
            left: 12,
            top: 12,
            bottom: 12,
            width: isNodeSidebarCollapsed ? 56 : leftSidebarWidth,
            zIndex: 12,
            transition: 'width 180ms ease',
          }}
        >
          <div className="llm-canvas-sidebar__head">
            {!isNodeSidebarCollapsed && <strong>Nodes</strong>}
            <button
              type="button"
              className="llm-canvas-sidebar__toggle"
              onClick={() => setIsNodeSidebarCollapsed((prev) => !prev)}
              aria-label={isNodeSidebarCollapsed ? 'Expand node sidebar' : 'Collapse node sidebar'}
            >
              {isNodeSidebarCollapsed ? '>' : '<'}
            </button>
          </div>

          {!isNodeSidebarCollapsed && (
            <>
              <div className="llm-canvas-sidebar__search">
                <input
                  className="llm-canvas-sidebar__search-input"
                  value={nodeSidebarQuery}
                  onChange={(event) => setNodeSidebarQuery(event.target.value)}
                  placeholder="Search node id / label / type"
                />
              </div>
              <div className="llm-canvas-sidebar__count">
                {filteredNodes.length}/{nodes.length} node(s)
              </div>
              <div className="llm-canvas-sidebar__list">
                {filteredNodes.map((node) => {
                  const nodeData = asObject(node.data)
                  const label = asKey(nodeData.label, node.id)
                  const isSelected = selectedNodeIds.includes(node.id)
                  return (
                    <article
                      key={node.id}
                      className={`llm-canvas-node-item ${isSelected ? 'is-selected' : ''}`.trim()}
                    >
                      <button
                        type="button"
                        className="llm-canvas-node-item__meta"
                        onClick={() => openNodeCardById(node.id)}
                      >
                        <div className="llm-canvas-node-item__label">{label}</div>
                        <div className="llm-canvas-node-item__id">{node.id}</div>
                      </button>
                      <div className="llm-canvas-node-item__actions">
                        <button
                          type="button"
                          className="llm-canvas-node-item__action"
                          onClick={() => focusNodeById(node.id)}
                        >
                          Focus
                        </button>
                        <button
                          type="button"
                          className="llm-canvas-node-item__action is-danger"
                          onClick={() => deleteNodeById(node.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </article>
                  )
                })}
                {!filteredNodes.length && (
                  <div className="llm-canvas-sidebar__empty">No nodes matched.</div>
                )}
              </div>
            </>
          )}
          {!isStorybookCanvas && !isNodeSidebarCollapsed && (
            <div className="llm-canvas-resize-handle llm-canvas-resize-handle--left" onPointerDown={startLeftResize} />
          )}
        </aside>

        <div className="llm-canvas-right-stack" style={{ width: rightStackWidth }}>
          {!isStorybookCanvas ? <div className="llm-canvas-resize-handle llm-canvas-resize-handle--right" onPointerDown={startRightResize} /> : null}
          {renderCanvasPanel('templates', '模板', (
            <NodeTemplatePalette
              templates={templateCatalog}
              selectedTemplateKey={selectedTemplateKey}
              onSelectTemplate={(template) => setSelectedTemplateKey(template.key)}
              onAddTemplate={addTemplateNode}
              onApplyTemplateToSelected={applyTemplateToSelected}
              selectedNodeCount={selectedNodeIds.length}
              title="Node Template Palette"
            />
          ))}

          {renderCanvasPanel('p2p', '连接与画布操作', (
            <>
              <div className="form-grid cols-2">
                <label>
                  <span>point from</span>
                  <select value={fromNodeId} onChange={(event) => setFromNodeId(event.target.value)}>
                    <option value="">Select source node</option>
                    {nodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {asKey(asObject(node.data).label, node.id)} ({node.id})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>point to</span>
                  <select value={toNodeId} onChange={(event) => setToNodeId(event.target.value)}>
                    <option value="">Select target node</option>
                    {nodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {asKey(asObject(node.data).label, node.id)} ({node.id})
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="inline-actions">
                <button type="button" onClick={connectPointToPoint}>Connect P2P</button>
                <button type="button" onClick={removeSelection} disabled={!selectedCount}>Delete Selected</button>
                <button type="button" onClick={resetGraph}>Reset</button>
                <button type="button" onClick={exportDsl}>Export JSON</button>
                <button type="button" onClick={() => fileInputRef.current?.click()}>Import File</button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json,application/json"
                  hidden
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) void (async () => {
                      try {
                        const text = await file.text()
                        setJsonDraft(text)
                        importDslFromText(text)
                        setStatus(`Imported file: ${file.name}`)
                      } catch (error) {
                        setStatus(`Import failed: ${error instanceof Error ? error.message : 'Unknown error'}`)
                      }
                    })()
                    event.target.value = ''
                  }}
                />
              </div>
            </>
          ))}

          {renderCanvasPanel('preset', '业务链条模板', (
            <>
              <div className="form-grid cols-2">
                <label>
                  <span>业务链条模板（下拉选择）</span>
                  <select value={selectedPresetKey} onChange={(event) => setSelectedPresetKey(event.target.value)}>
                    {WORKFLOW_LINK_PRESETS.map((preset) => (
                      <option key={preset.key} value={preset.key}>
                        {preset.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>链路说明</span>
                  <input value={selectedPreset?.description || ''} readOnly />
                </label>
              </div>
              <div className="inline-actions">
                <button type="button" onClick={generatePresetChain}>生成所选业务链条</button>
              </div>
            </>
          ))}

          {renderCanvasPanel('runtime', '运行与调试', (
            <>
              <div className="form-grid cols-3">
                <label>
                  <span>graph_id</span>
                  <input value={graphId} onChange={(event) => setGraphId(event.target.value)} placeholder="optional when compile, required when run/query" />
                </label>
                <label>
                  <span>run_id</span>
                  <input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="required for run detail/events" />
                </label>
                <label>
                  <span>run input (JSON)</span>
                  <input value={runInputText} onChange={(event) => setRunInputText(event.target.value)} placeholder='{"query":"..."}' />
                </label>
              </div>
              <div className="inline-actions">
                <button type="button" onClick={onCompileGraph} disabled={Boolean(busyAction)}>{busyAction === 'compile' ? 'Compiling...' : 'Compile Graph'}</button>
                <button type="button" onClick={onRunGraph} disabled={Boolean(busyAction)}>{busyAction === 'run' ? 'Running...' : 'Run Graph'}</button>
                <button type="button" onClick={onGetRunDetail} disabled={Boolean(busyAction)}>{busyAction === 'run-detail' ? 'Loading...' : 'Get Run Detail'}</button>
                <button type="button" onClick={onGetRunEvents} disabled={Boolean(busyAction)}>{busyAction === 'run-events' ? 'Loading...' : 'Get Run Events'}</button>
                <button type="button" onClick={onGetCompiledGraph} disabled={Boolean(busyAction)}>{busyAction === 'compiled' ? 'Loading...' : 'Get Compiled Graph'}</button>
              </div>
              <div className="status-line">Double-click canvas to add selected template; `Delete` removes selection; status: {status}</div>
            </>
          ))}

          {renderCanvasPanel('json', 'DSL JSON', (
            <div className="llm-designer-json">
              <label htmlFor="llm-designer-json-input">JSON import / export</label>
              <textarea id="llm-designer-json-input" value={jsonDraft} onChange={(event) => setJsonDraft(event.target.value)} spellCheck={false} placeholder="Paste exported DSL JSON here..." />
              <div className="llm-designer-json-actions">
                <button type="button" onClick={onImportJson}>Import JSON Text</button>
              </div>
            </div>
          ))}

          {renderCanvasPanel('results', '运行结果', (
            <div className="form-grid cols-2">
              <label>
                <span>compile response</span>
                <textarea rows={10} value={compileResultText} onChange={(event) => setCompileResultText(event.target.value)} />
              </label>
              <label>
                <span>run response / events</span>
                <textarea rows={10} value={runResultText} onChange={(event) => setRunResultText(event.target.value)} />
              </label>
            </div>
          ))}
        </div>

        <ReactFlow
          nodes={nodes}
          edges={allEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onInit={(instance) => {
            flowRef.current = instance
            if (!isStorybookCanvas) {
              instance.fitView({ padding: 0.2 })
            }
          }}
          onNodeClick={(event, node) => {
            const rect = canvasRef.current?.getBoundingClientRect()
            const x = rect ? event.clientX - rect.left + 12 : 20
            const y = rect ? event.clientY - rect.top + 12 : 20
            setEditingNodeId(node.id)
            setSelectedNodeIds([node.id])
            setNodeInfoDraft(JSON.stringify((node.data || {}) as Record<string, unknown>, null, 2))
            setNodeInfoCard((prev) => ({ ...prev, open: true, x: Math.max(0, x), y: Math.max(0, y) }))
          }}
          onSelectionChange={({ nodes: pickedNodes, edges: pickedEdges }) => {
            const pickedIds = (pickedNodes || []).map((node) => node.id)
            setSelectedNodeIds(pickedIds)
            setSelectedEdgeIds(
              (pickedEdges || [])
                .map((edge) => edge.id)
                .filter((edgeId) => !edgeId.startsWith(AUTO_BRIDGE_EDGE_PREFIX)),
            )
            if (pickedIds.length === 1) {
              setFromNodeId((prev) => prev || pickedIds[0])
              setToNodeId((prev) => (prev && prev !== pickedIds[0] ? prev : ''))
            }
          }}
          zoomOnScroll={!isStorybookCanvas}
          panOnDrag={!isStorybookCanvas}
          selectionOnDrag={!isStorybookCanvas}
        >
          {!isStorybookCanvas ? <MiniMap pannable zoomable /> : null}
          {!isStorybookCanvas ? <Controls /> : null}
          {!isStorybookCanvas ? <Background gap={24} size={1} /> : null}
        </ReactFlow>

        <NodeInfoCard
          open={nodeInfoCard.open && Boolean(selectedNode)}
          x={nodeInfoCard.x}
          y={nodeInfoCard.y}
          width={nodeInfoCard.width}
          height={nodeInfoCard.height}
          onMove={handleCardMove}
          onResize={handleCardResize}
          onClose={() => setNodeInfoCard((prev) => ({ ...prev, open: false }))}
          nodeId={selectedNode?.id || ''}
          nodeType={selectedNodeType || ''}
          templates={selectedNodeProfiles.map((profile) => ({ key: profile.key, label: profile.label, description: profile.description }))}
          draft={nodeInfoDraft}
          apply={applyInfoProfileByKey}
          save={saveNodeInfoDraft}
          onDraftChange={setNodeInfoDraft}
          availableNodeOutputs={availableNodeOutputs}
          availableVariables={availableVariables}
          schema={selectedNodeSchema}
          backendTasks={BACKEND_TASK_CATALOG}
        />
      </div>

    </section>
  )
}

function LlmDesignerStorybookLite({ projectKey }: Pick<LlmDesignerPageProps, 'projectKey'>) {
  const templateCatalog = useMemo(() => createTemplateCatalog(), [])
  const preset = WORKFLOW_LINK_PRESET_BY_KEY[DEFAULT_WORKFLOW_LINK_PRESET_KEY]
  const previewNodes = useMemo(() => ensureBoundaryNodes(baseNodes).map((node) => ({
    id: node.id,
    label: asKey(asObject(node.data).label, node.id),
    nodeType: asKey(asObject(node.data).node_type, node.type || 'unknown'),
    role: asKey(asObject(node.data).role, ''),
  })), [])
  const previewEdges = useMemo(() => [...baseEdges, ...buildAutoBridgeEdges(ensureBoundaryNodes(baseNodes), baseEdges)], [])
  const visibleTemplates = useMemo(() => templateCatalog.slice(0, 8), [templateCatalog])
  const visibleProfiles = useMemo(() => NODE_INFO_PROFILES.slice(0, 4), [])

  return (
    <section className="llm-designer-page llm-designer-page--full llm-designer-page--quiet">
      <header className="llm-designer-header">
        <div className="llm-designer-header__copy">
          <small>storybook-lite contract</small>
          <h2>LLM Designer</h2>
          <p>Storybook 只保留 agent 后续开发真正需要的模板、链路和运行 contract，不再承接完整 ReactFlow 运行时。</p>
        </div>
        <div className="llm-designer-header__stats">Templates {templateCatalog.length} · Nodes {previewNodes.length} · Edges {previewEdges.length}</div>
      </header>

      <div className="content-stack">
        <section className="panel">
          <div className="panel-header">
            <h2>Storybook Contract Surface</h2>
            <span className="chip">project: {projectKey}</span>
          </div>
          <p className="status-line">
            生产页继续使用完整 runtime canvas；Storybook 使用轻量入口，避免 iframe 中的布局反馈、自动 fit 和重交互拖垮 story。
          </p>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Default Workflow Preview</h2>
            <span className="chip">{preset.label}</span>
          </div>
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
              {previewNodes.map((node) => (
                <article key={node.id} style={{ border: '1px solid rgba(148, 163, 184, 0.3)', borderRadius: 12, padding: 12, background: 'rgba(255,255,255,0.72)' }}>
                  <strong>{node.label}</strong>
                  <div className="status-line">{node.id}</div>
                  <div className="status-line">type: {node.nodeType}</div>
                  <div className="status-line">role: {node.role || '-'}</div>
                </article>
              ))}
            </div>
            <div className="status-line">
              edges: {previewEdges.map((edge) => `${edge.source} -> ${edge.target}`).join(' | ')}
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Template Palette</h2>
            <span className="chip">deduped</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            {visibleTemplates.map((template) => (
              <article key={template.key} style={{ border: '1px solid rgba(148, 163, 184, 0.3)', borderRadius: 12, padding: 12, background: 'rgba(255,255,255,0.72)' }}>
                <strong>{template.label}</strong>
                <div className="status-line">{template.key}</div>
                <div className="status-line">{template.description || 'No description'}</div>
                <div className="status-line">node_type: {template.nodeType}</div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Node Profiles</h2>
            <span className="chip">editable presets</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            {visibleProfiles.map((profile) => (
              <article key={profile.key} style={{ border: '1px solid rgba(148, 163, 184, 0.3)', borderRadius: 12, padding: 12, background: 'rgba(255,255,255,0.72)' }}>
                <strong>{profile.label}</strong>
                <div className="status-line">{profile.description || '-'}</div>
                <div className="status-line">node_type: {profile.nodeType}</div>
                <div className="status-line">model: {asKey(profile.data.model, '-')}</div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Runtime Contract</h2>
            <span className="chip">api integration</span>
          </div>
          <div className="form-grid cols-3">
            <label>
              <span>graph_id</span>
              <input value="graph-demo-001" readOnly />
            </label>
            <label>
              <span>run_id</span>
              <input value="run-demo-001" readOnly />
            </label>
            <label>
              <span>run input</span>
              <input value='{"query":"battery market"}' readOnly />
            </label>
          </div>
          <div className="inline-actions">
            <button type="button" disabled>Compile Graph</button>
            <button type="button" disabled>Run Graph</button>
            <button type="button" disabled>Get Run Detail</button>
            <button type="button" disabled>Get Run Events</button>
          </div>
        </section>
      </div>
    </section>
  )
}

export default function LlmDesignerPage({ presentationMode = 'runtime', ...props }: LlmDesignerPageProps) {
  if (presentationMode === 'storybook-lite') {
    return <LlmDesignerStorybookLite projectKey={props.projectKey} />
  }
  return (
    <ReactFlowProvider>
      <DesignerCanvas {...props} />
    </ReactFlowProvider>
  )
}

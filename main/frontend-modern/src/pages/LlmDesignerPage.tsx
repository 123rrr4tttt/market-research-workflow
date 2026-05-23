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
import { translate, useAppLocale, type MessageKey } from '../app/platform/i18n'
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

type NodeTemplate = NodeTemplatePaletteItem<UnknownRecord> & {
  nodeType: NodeType
  labelKey?: LlmDesignerMessageKey
  descriptionKey?: LlmDesignerMessageKey
}

type NodeInfoProfile = {
  key: string
  label: string
  labelKey?: LlmDesignerMessageKey
  nodeType: NodeType
  description?: string
  descriptionKey?: LlmDesignerMessageKey
  data: UnknownRecord
}

type NodeOutputOption = {
  nodeId: string
  nodeLabel?: string
  outputKeys: string[]
}

type CanvasPanelKey = 'templates' | 'p2p' | 'preset' | 'runtime' | 'json' | 'results'
type LlmDesignerMessageKey = MessageKey
type TemplateValues = { [key: string]: string | number }
type UnknownRecord = { [key: string]: unknown }
type ActiveResizeState = null | { target: 'left' | 'right'; startX: number; startWidth: number }
type CanvasPanelCollapsedState = { [key in CanvasPanelKey]: boolean }

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

function formatLlmDesignerTemplate(template: string, values: TemplateValues) {
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (match, key) => String(values[key] ?? match))
}

const GPT_4_1_MODEL = ['gpt', '4.1'].join('-')
const GPT_4_1_MINI_MODEL = ['gpt', '4.1', 'mini'].join('-')
const DEFAULT_INPUT_QUERY_EXPRESSION = '=' + '{{' + '$' + 'input' + '.' + 'query' + '}}'
const DEFAULT_FRONTEND_PAYLOAD = JSON.stringify({ query: '' })
const DEFAULT_DATABASE_STORE_URI = ['sqlite', '///tmp/workflow.db'].join(':')
const DEFAULT_DATABASE_TABLE = 'workflow_results'
const VARIABLE_INPUT_PREFIX = '$' + 'input'
const VARIABLE_NODE_PREFIX = '$' + 'node'
const DEFAULT_VARIABLE_KEYS = ['query', 'state', 'prompt']
const KEY_DELETE = 'delete'.replace('d', 'D')
const KEY_BACKSPACE = 'backspace'.replace('b', 'B')
const JSON_FILE_EXTENSION = '.' + 'json'
const JSON_FILE_ACCEPT = '.' + 'json' + ',' + 'application/json'
const REACT_FLOW_PANE_SELECTOR = '.' + 'react-flow__pane'
const SIDEBAR_WIDTH_TRANSITION = ['width', '180ms', 'ease'].join(' ')
const CSS_AUTO_FIT_GRID_180 = ['repeat(', 'auto-fit', ', ', 'minmax(', '180px', ', ', '1fr', '))'].join('')
const CSS_AUTO_FIT_GRID_220 = ['repeat(', 'auto-fit', ', ', 'minmax(', '220px', ', ', '1fr', '))'].join('')
const CSS_STORYBOOK_CARD_BORDER = ['1px', 'solid', 'rgba(', '148', ',', '163', ',', '184', ',', '0.3', ')'].join(' ')
const CSS_STORYBOOK_CARD_BACKGROUND = ['rgba(', '255', ',', '255', ',', '255', ',', '0.72', ')'].join('')
const STORYBOOK_CARD_STYLE = {
  border: CSS_STORYBOOK_CARD_BORDER,
  borderRadius: 12,
  padding: 12,
  background: CSS_STORYBOOK_CARD_BACKGROUND,
}

function joinIdParts(...parts: Array<string | number>) {
  return parts.map((part) => String(part)).join('-')
}

function appendDisplaySuffix(label: string, suffix: string | number) {
  return [label, suffix].join(' ')
}

function formatVariablePath(scope: string, ...parts: string[]) {
  return [scope, ...parts].join('.')
}

function localizeDesignerData(data: UnknownRecord, t: (key: LlmDesignerMessageKey, fallback?: string) => string): UnknownRecord {
  const prompt = data.prompt_template
  if (typeof prompt !== 'string') return data
  const promptKeyPrefix = ['llmDesignerPage', 'prompt'].join('.') + '.'
  if (!prompt.startsWith(promptKeyPrefix)) return data
  return { ...data, prompt_template: t(prompt as LlmDesignerMessageKey, prompt) }
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

function localizeTemplate(template: NodeTemplate, t: (key: LlmDesignerMessageKey, fallback?: string) => string): NodeTemplate {
  return {
    ...template,
    label: template.labelKey ? t(template.labelKey, template.label) : template.label,
    description: template.descriptionKey ? t(template.descriptionKey, template.description) : template.description,
    data: localizeDesignerData(template.data, t),
  }
}

function localizeProfile(profile: NodeInfoProfile, t: (key: LlmDesignerMessageKey, fallback?: string) => string): NodeInfoProfile {
  return {
    ...profile,
    label: profile.labelKey ? t(profile.labelKey, profile.label) : profile.label,
    description: profile.descriptionKey ? t(profile.descriptionKey, profile.description) : profile.description,
    data: localizeDesignerData(profile.data, t),
  }
}

function createTemplateCatalog(t?: (key: LlmDesignerMessageKey, fallback?: string) => string): NodeTemplate[] {
  const templates = mergeUniqueTemplates(NODE_TEMPLATES, createModuleTemplates())
  return t ? templates.map((template) => localizeTemplate(template, t)) : templates
}

const NODE_TEMPLATES: NodeTemplate[] = [
  {
    key: 'user-input',
    label: 'llmDesignerPage.template.userInput.label',
    labelKey: 'llmDesignerPage.template.userInput.label',
    nodeType: 'vector_search',
    description: 'llmDesignerPage.template.userInput.description',
    descriptionKey: 'llmDesignerPage.template.userInput.description',
    data: { label: 'user_input', node_type: 'vector_search', role: 'input', query_key: 'query' },
  },
  {
    key: 'vector-search',
    label: 'llmDesignerPage.template.vectorSearch.label',
    labelKey: 'llmDesignerPage.template.vectorSearch.label',
    nodeType: 'vector_search',
    description: 'llmDesignerPage.template.vectorSearch.description',
    descriptionKey: 'llmDesignerPage.template.vectorSearch.description',
    data: { label: 'vector_search', node_type: 'vector_search', top_k: 5, source: 'default_corpus' },
  },
  {
    key: 'llm-call',
    label: 'llmDesignerPage.template.llmCall.label',
    labelKey: 'llmDesignerPage.template.llmCall.label',
    nodeType: 'llm_call',
    description: 'llmDesignerPage.template.llmCall.description',
    descriptionKey: 'llmDesignerPage.template.llmCall.description',
    data: {
      label: 'llm_call',
      node_type: 'llm_call',
      provider: 'openai',
      model: GPT_4_1_MODEL,
      temperature: 0.2,
      top_p: 1,
      max_tokens: 1024,
      prompt_class: 'analyst',
      prompt_template: 'llmDesignerPage.prompt.analystFindings',
    },
  },
  {
    key: 'filter-predicate',
    label: 'llmDesignerPage.template.filterPredicate.label',
    labelKey: 'llmDesignerPage.template.filterPredicate.label',
    nodeType: 'filter',
    description: 'llmDesignerPage.template.filterPredicate.description',
    descriptionKey: 'llmDesignerPage.template.filterPredicate.description',
    data: {
      label: 'filter_predicate',
      node_type: 'filter',
      strategy: 'predicate',
      predicate_expr: DEFAULT_INPUT_QUERY_EXPRESSION,
      predicate_mode: 'keep',
    },
  },
  {
    key: 'filter-topk',
    label: 'llmDesignerPage.template.filterTopk.label',
    labelKey: 'llmDesignerPage.template.filterTopk.label',
    nodeType: 'filter',
    description: 'llmDesignerPage.template.filterTopk.description',
    descriptionKey: 'llmDesignerPage.template.filterTopk.description',
    data: {
      label: 'filter_topk',
      node_type: 'filter',
      strategy: 'topk',
      topk_k: 20,
      topk_score_field: 'score',
      topk_desc: true,
    },
  },
  {
    key: 'join',
    label: 'llmDesignerPage.template.join.label',
    labelKey: 'llmDesignerPage.template.join.label',
    nodeType: 'join',
    description: 'llmDesignerPage.template.join.description',
    descriptionKey: 'llmDesignerPage.template.join.description',
    data: { label: 'join', node_type: 'join', strategy: 'concat' },
  },
  {
    key: 'final-output',
    label: 'llmDesignerPage.template.finalOutput.label',
    labelKey: 'llmDesignerPage.template.finalOutput.label',
    nodeType: 'join',
    description: 'llmDesignerPage.template.finalOutput.description',
    descriptionKey: 'llmDesignerPage.template.finalOutput.description',
    data: { label: 'final_output', node_type: 'join', role: 'output' },
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
    label: 'llmDesignerPage.profile.llmPrecise.label',
    labelKey: 'llmDesignerPage.profile.llmPrecise.label',
    nodeType: 'llm_call',
    description: 'llmDesignerPage.profile.llmPrecise.description',
    descriptionKey: 'llmDesignerPage.profile.llmPrecise.description',
    data: {
      provider: 'openai',
      model: GPT_4_1_MODEL,
      temperature: 0.1,
      top_p: 0.9,
      max_tokens: 1024,
      prompt_class: 'analyst',
      prompt_template: 'llmDesignerPage.prompt.preciseFacts',
    },
  },
  {
    key: 'llm-creative',
    label: 'llmDesignerPage.profile.llmCreative.label',
    labelKey: 'llmDesignerPage.profile.llmCreative.label',
    nodeType: 'llm_call',
    description: 'llmDesignerPage.profile.llmCreative.description',
    descriptionKey: 'llmDesignerPage.profile.llmCreative.description',
    data: {
      provider: 'openai',
      model: GPT_4_1_MODEL,
      temperature: 0.8,
      top_p: 1,
      max_tokens: 1400,
      prompt_class: 'rewriter',
      prompt_template: 'llmDesignerPage.prompt.creativeOptions',
    },
  },
  {
    key: 'llm-summarizer',
    label: 'llmDesignerPage.profile.llmSummarizer.label',
    labelKey: 'llmDesignerPage.profile.llmSummarizer.label',
    nodeType: 'llm_call',
    description: 'llmDesignerPage.profile.llmSummarizer.description',
    descriptionKey: 'llmDesignerPage.profile.llmSummarizer.description',
    data: {
      provider: 'openai',
      model: GPT_4_1_MINI_MODEL,
      temperature: 0.2,
      top_p: 1,
      max_tokens: 800,
      prompt_class: 'summarizer',
      prompt_template: 'llmDesignerPage.prompt.summaryBullets',
    },
  },
  {
    key: 'llm-extractor',
    label: 'llmDesignerPage.profile.llmExtractor.label',
    labelKey: 'llmDesignerPage.profile.llmExtractor.label',
    nodeType: 'llm_call',
    description: 'llmDesignerPage.profile.llmExtractor.description',
    descriptionKey: 'llmDesignerPage.profile.llmExtractor.description',
    data: {
      provider: 'openai',
      model: GPT_4_1_MINI_MODEL,
      temperature: 0,
      top_p: 1,
      max_tokens: 700,
      prompt_class: 'extractor',
      prompt_template: 'llmDesignerPage.prompt.strictJsonExtraction',
    },
  },
  {
    key: 'vec-fast',
    label: 'llmDesignerPage.profile.vecFast.label',
    labelKey: 'llmDesignerPage.profile.vecFast.label',
    nodeType: 'vector_search',
    description: 'llmDesignerPage.profile.vecFast.description',
    descriptionKey: 'llmDesignerPage.profile.vecFast.description',
    data: { top_k: 5, source: 'default_corpus', rerank: false },
  },
  {
    key: 'vec-deep',
    label: 'llmDesignerPage.profile.vecDeep.label',
    labelKey: 'llmDesignerPage.profile.vecDeep.label',
    nodeType: 'vector_search',
    description: 'llmDesignerPage.profile.vecDeep.description',
    descriptionKey: 'llmDesignerPage.profile.vecDeep.description',
    data: { top_k: 20, source: 'default_corpus', rerank: true },
  },
  {
    key: 'filter-predicate-keep',
    label: 'llmDesignerPage.profile.filterPredicateKeep.label',
    labelKey: 'llmDesignerPage.profile.filterPredicateKeep.label',
    nodeType: 'filter',
    description: 'llmDesignerPage.profile.filterPredicateKeep.description',
    descriptionKey: 'llmDesignerPage.profile.filterPredicateKeep.description',
    data: {
      strategy: 'predicate',
      predicate_expr: DEFAULT_INPUT_QUERY_EXPRESSION,
      predicate_mode: 'keep',
    },
  },
  {
    key: 'filter-topk-desc',
    label: 'llmDesignerPage.profile.filterTopkDesc.label',
    labelKey: 'llmDesignerPage.profile.filterTopkDesc.label',
    nodeType: 'filter',
    description: 'llmDesignerPage.profile.filterTopkDesc.description',
    descriptionKey: 'llmDesignerPage.profile.filterTopkDesc.description',
    data: {
      strategy: 'topk',
      topk_k: 20,
      topk_score_field: 'score',
      topk_desc: true,
    },
  },
  {
    key: 'join-concat',
    label: 'llmDesignerPage.profile.joinConcat.label',
    labelKey: 'llmDesignerPage.profile.joinConcat.label',
    nodeType: 'join',
    description: 'llmDesignerPage.profile.joinConcat.description',
    descriptionKey: 'llmDesignerPage.profile.joinConcat.description',
    data: { strategy: 'concat', delimiter: '\\n\\n' },
  },
  {
    key: 'join-json',
    label: 'llmDesignerPage.profile.joinJson.label',
    labelKey: 'llmDesignerPage.profile.joinJson.label',
    nodeType: 'join',
    description: 'llmDesignerPage.profile.joinJson.description',
    descriptionKey: 'llmDesignerPage.profile.joinJson.description',
    data: { strategy: 'json_merge' },
  },
]

const baseNodes: Node[] = [
  { id: 'input-1', type: 'input', position: { x: 80, y: 120 }, data: { label: 'input', node_type: 'vector_search' } },
  {
    id: 'llm-1',
    position: { x: 360, y: 120 },
    data: {
      label: 'LLM',
      node_type: 'llm_call',
      provider: 'openai',
      model: GPT_4_1_MODEL,
      temperature: 0.2,
      top_p: 1,
      max_tokens: 1024,
      prompt_class: 'analyst',
    },
  },
  { id: 'output-1', type: 'output', position: { x: 640, y: 120 }, data: { label: 'output', node_type: 'join' } },
]

const baseEdges: Edge[] = [
  { id: 'e-input-llm', source: 'input-1', target: 'llm-1', animated: true },
  { id: 'e-llm-output', source: 'llm-1', target: 'output-1' },
]

const FRONT_INPUT_NODE_ID = 'frontend-input'
const DATABASE_NODE_ID = 'database-sink'
const AUTO_BRIDGE_EDGE_PREFIX = 'auto-bridge-'

type BoundaryNodeConfig = {
  frontendPayload?: string
  frontendQueryKey?: string
  databaseStoreUri?: string
  databaseTable?: string
}

type BoundaryNodeLabels = {
  frontendInput: string
  databaseSink: string
  frontendEdge: string
  databaseEdge: string
}

const DEFAULT_BOUNDARY_NODE_LABELS: BoundaryNodeLabels = {
  frontendInput: 'frontend_input',
  databaseSink: 'database_sink',
  frontendEdge: 'frontend_input',
  databaseEdge: 'database_sink',
}

function isBoundaryNodeId(nodeId: string): boolean {
  return nodeId === FRONT_INPUT_NODE_ID || nodeId === DATABASE_NODE_ID
}

function createBoundaryNodes(base: Node[], config?: BoundaryNodeConfig, labels: BoundaryNodeLabels = DEFAULT_BOUNDARY_NODE_LABELS): Node[] {
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
          label: labels.frontendInput,
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
          label: labels.databaseSink,
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
        label: labels.frontendInput,
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
        label: labels.databaseSink,
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

function ensureBoundaryNodes(base: Node[], config?: BoundaryNodeConfig, labels: BoundaryNodeLabels = DEFAULT_BOUNDARY_NODE_LABELS): Node[] {
  const frontendExisting = base.find((node) => node.id === FRONT_INPUT_NODE_ID)
  const databaseExisting = base.find((node) => node.id === DATABASE_NODE_ID)
  const nonBoundaryNodes = base.filter((node) => !isBoundaryNodeId(node.id))
  const [frontendDefault, databaseDefault] = createBoundaryNodes(nonBoundaryNodes, config, labels)
  const frontendNode = frontendExisting
    ? { ...frontendExisting, data: { ...(frontendExisting.data || {}), label: labels.frontendInput }, draggable: false, selectable: true, style: frontendDefault.style }
    : frontendDefault
  const databaseNode = databaseExisting
    ? { ...databaseExisting, data: { ...(databaseExisting.data || {}), label: labels.databaseSink }, draggable: false, selectable: true, style: databaseDefault.style }
    : databaseDefault
  return [...nonBoundaryNodes, frontendNode, databaseNode]
}

function buildAutoBridgeEdges(nodes: Node[], edges: Edge[], labels: BoundaryNodeLabels = DEFAULT_BOUNDARY_NODE_LABELS): Edge[] {
  const dataNodes = nodes.filter((node) => !isBoundaryNodeId(node.id))
  if (!dataNodes.length) return []
  const edgeKeySet = new Set(edges.map((edge) => [edge.source, edge.target].join('::')))
  const inDegree = new Map()
  const outDegree = new Map()
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
      id: AUTO_BRIDGE_EDGE_PREFIX + 'in-' + head.id,
      source: FRONT_INPUT_NODE_ID,
      target: head.id,
      type: 'smoothstep',
      label: labels.frontendEdge,
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
      id: AUTO_BRIDGE_EDGE_PREFIX + 'out-' + tail.id,
      source: tail.id,
      target: DATABASE_NODE_ID,
      type: 'smoothstep',
      label: labels.databaseEdge,
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

function asObject(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as UnknownRecord) : {}
}

function asList(value: unknown): UnknownRecord[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => asObject(item)).filter((item) => Object.keys(item).length > 0)
}

function asKey(value: unknown, fallback: string): string {
  const next = String(value || '').trim()
  return next || fallback
}

function validateNodeConfigDraft(data: UnknownRecord): { key: LlmDesignerMessageKey; values?: TemplateValues } | null {
  const inputVars = asList(data.input_vars)
  for (const item of inputVars) {
    const name = asKey(item.name, '')
    if (!name) return { key: 'llmDesignerPage.validation.inputNameRequired' }
    const source = asKey(item.source, 'input')
    if (source === 'node_output') {
      if (!asKey(item.from_node, '')) return { key: 'llmDesignerPage.validation.inputMissingFromNode', values: { name } }
      if (!asKey(item.from_key, '')) return { key: 'llmDesignerPage.validation.inputMissingFromKey', values: { name } }
    }
    if (source === 'expression' && !asKey(item.expr, '')) {
      return { key: 'llmDesignerPage.validation.inputMissingExpr', values: { name } }
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

function pickModuleMeta(data: UnknownRecord): UnknownRecord {
  const out: UnknownRecord = {}
  Object.entries(data).forEach(([key, value]) => {
    if (key.startsWith('module_')) out[key] = value
  })
  return out
}

function normalizeTemplateData(template: NodeTemplate, existingData?: UnknownRecord): UnknownRecord {
  const preservedMeta = existingData ? pickModuleMeta(existingData) : {}
  return {
    ...(existingData || {}),
    ...template.data,
    ...preservedMeta,
    node_type: template.nodeType,
  }
}

function createConnectedInputVars(sourceNode: Node, targetNode: Node): UnknownRecord[] {
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
    const inputName = formatVariablePath(sourceNode.id, outputKey)
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
  const locale = useAppLocale()
  const t = useCallback((key: LlmDesignerMessageKey, fallback?: string) => translate(locale, key, fallback), [locale])
  const tf = useCallback(
    (key: LlmDesignerMessageKey, values: TemplateValues, fallback?: string) =>
      formatLlmDesignerTemplate(t(key, fallback), values),
    [t],
  )
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
  const boundaryLabels = useMemo<BoundaryNodeLabels>(
    () => ({
      frontendInput: t('llmDesignerPage.boundary.frontendInput'),
      databaseSink: t('llmDesignerPage.boundary.databaseSink'),
      frontendEdge: t('llmDesignerPage.boundary.frontendEdge'),
      databaseEdge: t('llmDesignerPage.boundary.databaseEdge'),
    }),
    [t],
  )
  const templateCatalog = useMemo(() => createTemplateCatalog(t), [t])
  const resolvedTemplateKey = useMemo(() => {
    const key = linkParams.templateKey
    if (!key) return templateCatalog[2]?.key || 'llm-call'
    return templateCatalog.some((item) => item.key === key) ? key : (templateCatalog[2]?.key || 'llm-call')
  }, [linkParams.templateKey, templateCatalog])

  const [nodes, setNodes, onNodesChange] = useNodesState(ensureBoundaryNodes(baseNodes, boundaryConfig, boundaryLabels))
  const [edges, setEdges, onEdgesChange] = useEdgesState(baseEdges)
  const [selectedNodeIds, setSelectedNodeIds] = useState([] as string[])
  const [selectedEdgeIds, setSelectedEdgeIds] = useState([] as string[])
  const [selectedTemplateKey, setSelectedTemplateKey] = useState(resolvedTemplateKey)
  const [jsonDraft, setJsonDraft] = useState('')
  const [status, setStatus] = useState(t('llmDesignerPage.status.ready'))
  const [graphId, setGraphId] = useState(linkParams.graphId)
  const [runId, setRunId] = useState(linkParams.runId)
  const [runInputText, setRunInputText] = useState(linkParams.runInputText)
  const [compileResultText, setCompileResultText] = useState('')
  const [runResultText, setRunResultText] = useState('')
  const [busyAction, setBusyAction] = useState('')
  const [fromNodeId, setFromNodeId] = useState(linkParams.fromNodeId)
  const [toNodeId, setToNodeId] = useState(linkParams.toNodeId)
  const [selectedPresetKey, setSelectedPresetKey] = useState(DEFAULT_WORKFLOW_LINK_PRESET_KEY as string)
  const [isNodeSidebarCollapsed, setIsNodeSidebarCollapsed] = useState(isStorybookCanvas)
  const [leftSidebarWidth, setLeftSidebarWidth] = useState(isStorybookCanvas ? 240 : 320)
  const [rightStackWidth, setRightStackWidth] = useState(isStorybookCanvas ? 360 : 520)
  const [nodeSidebarQuery, setNodeSidebarQuery] = useState('')
  const [panelCollapsed, setPanelCollapsed] = useState({
    templates: isStorybookCanvas,
    p2p: true,
    preset: true,
    runtime: isStorybookCanvas,
    json: true,
    results: isStorybookCanvas,
  } as CanvasPanelCollapsedState)

  const [editingNodeId, setEditingNodeId] = useState(linkParams.nodeId)
  const [nodeInfoDraft, setNodeInfoDraft] = useState('{}')
  const [nodeInfoCard, setNodeInfoCard] = useState({ open: Boolean(linkParams.nodeId), x: 20, y: 20, width: 420, height: 420 })
  const [activeResize, setActiveResize] = useState(null as ActiveResizeState)

  const nextIdRef = useRef(2)
  const fileInputRef = useRef(null as HTMLInputElement | null)
  const flowRef = useRef(null as ReactFlowInstance | null)
  const canvasRef = useRef(null as HTMLDivElement | null)

  useEffect(() => {
    setNodes((current) => ensureBoundaryNodes(current, boundaryConfig, boundaryLabels))
  }, [boundaryConfig, boundaryLabels, setNodes])

  const selectedCount = selectedNodeIds.length + selectedEdgeIds.length
  const bridgeEdges = useMemo(() => buildAutoBridgeEdges(nodes, edges, boundaryLabels), [boundaryLabels, edges, nodes])
  const allEdges = useMemo(() => [...edges, ...bridgeEdges], [bridgeEdges, edges])
  const selectedNode = useMemo(() => {
    if (!editingNodeId) return null
    return nodes.find((item) => item.id === editingNodeId) || null
  }, [editingNodeId, nodes])
  const selectedNodeType = useMemo(() => (selectedNode ? inferNodeType(selectedNode) : null), [selectedNode])
  const localizedNodeInfoProfiles = useMemo(() => NODE_INFO_PROFILES.map((profile) => localizeProfile(profile, t)), [t])
  const selectedNodeProfiles = useMemo(
    () => (selectedNodeType ? localizedNodeInfoProfiles.filter((item) => item.nodeType === selectedNodeType) : []),
    [localizedNodeInfoProfiles, selectedNodeType],
  )
  const selectedNodeSchema = useMemo(
    () => (selectedNodeType ? getNodeSchema(selectedNodeType) : null),
    [selectedNodeType],
  )
  const availableNodeOutputs = useMemo<NodeOutputOption[]>(() => {
    if (!selectedNode) return []
    const upstreamNodeIds = new Set(edges.filter((edge) => edge.target === selectedNode.id).map((edge) => edge.source))
    const outputMap = new Map()
    const labelMap = new Map()
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
    const out = new Set(DEFAULT_VARIABLE_KEYS.map((key) => formatVariablePath(VARIABLE_INPUT_PREFIX, key)))
    try {
      const parsed = JSON.parse(runInputText || '{}') as UnknownRecord
      Object.keys(parsed || {}).forEach((key) => out.add(formatVariablePath(VARIABLE_INPUT_PREFIX, key)))
    } catch {
      // ignore invalid run input JSON for variable hints
    }
    for (const item of availableNodeOutputs) {
      for (const key of item.outputKeys) out.add(formatVariablePath(VARIABLE_NODE_PREFIX, item.nodeId, key))
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
        setStatus(t('llmDesignerPage.status.invalidBoundaryConnect'))
        return
      }
      const edgeId = joinIdParts('e', connection.source ?? 'unknown', connection.target ?? 'unknown', Date.now())
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
      setStatus(t('llmDesignerPage.status.connected'))
    },
    [setEdges, setNodes, t],
  )

  const addTemplateNode = useCallback((templateItem?: NodeTemplatePaletteItem<UnknownRecord>) => {
    const template = templateCatalog.find((item) => item.key === (templateItem?.key || selectedTemplateKey)) || templateCatalog[2]
    if (!template) return
    const id = joinIdParts(template.key, nextIdRef.current)
    nextIdRef.current += 1
    const nextNode: Node = {
      id,
      position: { x: 160 + nodes.length * 24, y: 160 + nodes.length * 18 },
      data: { ...normalizeTemplateData(template), label: appendDisplaySuffix(template.label, nextIdRef.current - 1) },
    }
    setNodes((current) => ensureBoundaryNodes([...current, nextNode], boundaryConfig, boundaryLabels))
    setStatus(tf('llmDesignerPage.status.addedTemplateNode', { label: template.label }))
  }, [nodes.length, selectedTemplateKey, setNodes, templateCatalog, boundaryConfig, boundaryLabels, tf])

  const applyTemplateToSelected = useCallback((templateItem?: NodeTemplatePaletteItem<UnknownRecord>) => {
    if (selectedNodeIds.length !== 1) {
      setStatus(t('llmDesignerPage.status.applyTemplateSelectOne'))
      return
    }
    const template = templateCatalog.find((item) => item.key === (templateItem?.key || selectedTemplateKey)) || templateCatalog[2]
    if (!template) return
    const targetNodeId = selectedNodeIds[0]
    if (isBoundaryNodeId(targetNodeId)) {
      setStatus(t('llmDesignerPage.status.applyTemplateBoundaryFixed'))
      return
    }
    setNodes((current) =>
      current.map((node) =>
        node.id === targetNodeId
          ? {
              ...node,
              data: {
                ...normalizeTemplateData(template, asObject(node.data)),
                label: appendDisplaySuffix(template.label, targetNodeId),
              },
            }
          : node,
      ),
    )
    setStatus(tf('llmDesignerPage.status.appliedTemplate', { label: template.label, nodeId: targetNodeId }))
  }, [selectedNodeIds, selectedTemplateKey, setNodes, templateCatalog, t, tf])

  const connectPointToPoint = useCallback(() => {
    const source = fromNodeId.trim()
    const target = toNodeId.trim()
    if (!source || !target || source === target) {
      setStatus(t('llmDesignerPage.status.p2pChooseValid'))
      return
    }
    const sourceExists = nodes.some((item) => item.id === source)
    const targetExists = nodes.some((item) => item.id === target)
    if (!sourceExists || !targetExists) {
      setStatus(t('llmDesignerPage.status.p2pNodeNotFound'))
      return
    }
    if (source === DATABASE_NODE_ID || target === FRONT_INPUT_NODE_ID) {
      setStatus(t('llmDesignerPage.status.p2pInvalidBoundary'))
      return
    }
    setEdges((current) => {
      const exists = current.some((edge) => edge.source === source && edge.target === target)
      if (exists) return current
      return addEdge({ id: joinIdParts('e', source, target, current.length + 1), source, target }, current)
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
    setStatus(tf('llmDesignerPage.status.connectedNodes', { source, target }))
  }, [fromNodeId, nodes, setEdges, setNodes, t, tf, toNodeId])

  const removeSelection = useCallback(() => {
    if (!selectedCount) return
    setNodes((current) =>
      current.filter((node) => !selectedNodeIds.includes(node.id) || isBoundaryNodeId(node.id)),
    )
    setEdges((current) => current.filter((edge) => !selectedEdgeIds.includes(edge.id)))
    setStatus(tf('llmDesignerPage.status.removedSelection', { count: selectedCount }))
  }, [selectedCount, selectedEdgeIds, selectedNodeIds, setEdges, setNodes, tf])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.key === KEY_DELETE || event.key === KEY_BACKSPACE) && (selectedNodeIds.length || selectedEdgeIds.length)) {
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
    setNodes(ensureBoundaryNodes(baseNodes, boundaryConfig, boundaryLabels))
    setEdges(baseEdges)
    setSelectedNodeIds([])
    setSelectedEdgeIds([])
    setStatus(t('llmDesignerPage.status.resetTemplate'))
    window.requestAnimationFrame(() => {
      flowRef.current?.fitView({ duration: 300, padding: 0.2 })
    })
  }, [boundaryConfig, boundaryLabels, setEdges, setNodes, t])

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
    link.download = joinIdParts('llm-designer-dsl', Date.now()) + JSON_FILE_EXTENSION
    link.click()
    URL.revokeObjectURL(url)
    setStatus(t('llmDesignerPage.status.exportedDsl'))
  }, [collectDsl, onExportDsl, t])

  const importDslFromText = useCallback((text: string) => {
    const parsed = JSON.parse(text) as Partial<DesignerDsl>
    if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
      throw new Error(t('llmDesignerPage.error.importShape'))
    }
    setNodes(ensureBoundaryNodes(parsed.nodes as Node[], boundaryConfig, boundaryLabels))
    setEdges(parsed.edges as Edge[])
    if (parsed.viewport) {
      window.requestAnimationFrame(() => {
        flowRef.current?.setViewport(parsed.viewport as Viewport, { duration: 280 })
      })
    }
  }, [boundaryConfig, boundaryLabels, setEdges, setNodes, t])

  const onImportJson = useCallback(() => {
    try {
      importDslFromText(jsonDraft)
      setStatus(t('llmDesignerPage.status.importedJsonText'))
    } catch (error) {
      setStatus(tf('llmDesignerPage.status.importFailed', { message: error instanceof Error ? error.message : t('llmDesignerPage.error.unknown') }))
    }
  }, [importDslFromText, jsonDraft, t, tf])

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
            config: { label: String((node.data as { label?: unknown })?.label || node.id), ...((node.data || {}) as UnknownRecord) },
          })),
          edges: allEdges.map((edge) => ({ from: edge.source, to: edge.target })),
        },
      })
      const nextGraphId = String(response.graph_id || '').trim()
      if (nextGraphId) setGraphId(nextGraphId)
      setCompileResultText(JSON.stringify(response, null, 2))
      setStatus(nextGraphId ? tf('llmDesignerPage.status.compiledGraph', { graphId: nextGraphId }) : t('llmDesignerPage.status.compiled'))
    } catch (error) {
      setStatus(tf('llmDesignerPage.status.compileFailed', { message: error instanceof Error ? error.message : t('llmDesignerPage.error.unknown') }))
    } finally {
      setBusyAction('')
    }
  }, [graphId, nodes, allEdges, t, tf])

  const onRunGraph = useCallback(async () => {
    const targetGraphId = graphId.trim()
    if (!targetGraphId) {
      setStatus(t('llmDesignerPage.status.runGraphIdRequired'))
      return
    }
    setBusyAction('run')
    try {
      const input = JSON.parse(runInputText || '{}') as UnknownRecord
      const response = await runWorkflowGraph({ graph_id: targetGraphId, input })
      const nextRunId = String(response.run_id || '').trim()
      if (nextRunId) setRunId(nextRunId)
      setRunResultText(JSON.stringify(response, null, 2))
      setStatus(nextRunId ? tf('llmDesignerPage.status.runStarted', { runId: nextRunId }) : t('llmDesignerPage.status.runSubmitted'))
    } catch (error) {
      setStatus(tf('llmDesignerPage.status.runFailed', { message: error instanceof Error ? error.message : t('llmDesignerPage.error.unknown') }))
    } finally {
      setBusyAction('')
    }
  }, [graphId, runInputText, t, tf])

  const onGetRunDetail = useCallback(async () => {
    const targetRunId = runId.trim()
    if (!targetRunId) {
      setStatus(t('llmDesignerPage.status.runDetailRunIdRequired'))
      return
    }
    setBusyAction('run-detail')
    try {
      const response = await getWorkflowGraphRun(targetRunId)
      setRunResultText(JSON.stringify(response, null, 2))
      setStatus(tf('llmDesignerPage.status.fetchedRunDetail', { runId: targetRunId }))
    } catch (error) {
      setStatus(tf('llmDesignerPage.status.runDetailFailed', { message: error instanceof Error ? error.message : t('llmDesignerPage.error.unknown') }))
    } finally {
      setBusyAction('')
    }
  }, [runId, t, tf])

  const onGetRunEvents = useCallback(async () => {
    const targetRunId = runId.trim()
    if (!targetRunId) {
      setStatus(t('llmDesignerPage.status.runEventsRunIdRequired'))
      return
    }
    setBusyAction('run-events')
    try {
      const response = await getWorkflowGraphRunEvents(targetRunId)
      setRunResultText(JSON.stringify(response, null, 2))
      setStatus(tf('llmDesignerPage.status.fetchedRunEvents', { runId: targetRunId }))
    } catch (error) {
      setStatus(tf('llmDesignerPage.status.runEventsFailed', { message: error instanceof Error ? error.message : t('llmDesignerPage.error.unknown') }))
    } finally {
      setBusyAction('')
    }
  }, [runId, t, tf])

  const onGetCompiledGraph = useCallback(async () => {
    const targetGraphId = graphId.trim()
    if (!targetGraphId) {
      setStatus(t('llmDesignerPage.status.compiledGraphIdRequired'))
      return
    }
    setBusyAction('compiled')
    try {
      const response = await getCompiledWorkflowGraph(targetGraphId)
      setCompileResultText(JSON.stringify(response, null, 2))
      setStatus(tf('llmDesignerPage.status.fetchedCompiledGraph', { graphId: targetGraphId }))
    } catch (error) {
      setStatus(tf('llmDesignerPage.status.compiledGraphQueryFailed', { message: error instanceof Error ? error.message : t('llmDesignerPage.error.unknown') }))
    } finally {
      setBusyAction('')
    }
  }, [graphId, t, tf])

  const applyInfoProfileByKey = useCallback((profileKey: string) => {
    if (!selectedNode || !selectedNodeType) {
      setStatus(t('llmDesignerPage.status.applyNodeInfoSelectOne'))
      return
    }
    const profile = localizedNodeInfoProfiles.find((item) => item.key === profileKey && item.nodeType === selectedNodeType)
    if (!profile) {
      setStatus(t('llmDesignerPage.status.applyNodeInfoChooseTemplate'))
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
    setStatus(tf('llmDesignerPage.status.appliedNodeInfoTemplate', { label: profile.label }))
  }, [localizedNodeInfoProfiles, selectedNode, selectedNodeType, setNodes, t, tf])

  const saveNodeInfoDraft = useCallback(() => {
    if (!selectedNode || !selectedNodeType) {
      setStatus(t('llmDesignerPage.status.saveNodeInfoSelectOne'))
      return
    }
    try {
      const parsed = JSON.parse(nodeInfoDraft || '{}') as UnknownRecord
      const validationError = validateNodeConfigDraft(parsed)
      if (validationError) {
        setStatus(
          tf('llmDesignerPage.status.saveNodeInfoFailed', {
            message: validationError.values
              ? formatLlmDesignerTemplate(t(validationError.key), validationError.values)
              : t(validationError.key),
          }),
        )
        return
      }
      const nextData = {
        ...(selectedNode.data || {}),
        ...parsed,
        node_type: selectedNodeType,
        label: String(parsed.label || (selectedNode.data as { label?: unknown })?.label || selectedNode.id),
      }
      setNodes((current) => current.map((node) => (node.id === selectedNode.id ? { ...node, data: nextData } : node)))
      setStatus(tf('llmDesignerPage.status.savedNodeInfo', { nodeId: selectedNode.id }))
    } catch (error) {
      setStatus(tf('llmDesignerPage.status.saveNodeInfoFailed', { message: error instanceof Error ? error.message : t('llmDesignerPage.error.invalidJson') }))
    }
  }, [nodeInfoDraft, selectedNode, selectedNodeType, setNodes, t, tf])

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

  const statsText = tf('llmDesignerPage.stats.canvas', { nodes: nodes.length, edges: allEdges.length })

  const addNodeAtPoint = useCallback((clientX: number, clientY: number) => {
    const instance = flowRef.current
    if (!instance) return
    const template = templateCatalog.find((item) => item.key === selectedTemplateKey) || templateCatalog[2]
    if (!template) return
    const position = instance.screenToFlowPosition({ x: clientX, y: clientY })
    const id = joinIdParts(template.key, nextIdRef.current)
    nextIdRef.current += 1
    const nextNode: Node = {
      id,
      position,
      data: { ...normalizeTemplateData(template), label: appendDisplaySuffix(template.label, nextIdRef.current - 1) },
    }
    setNodes((current) => ensureBoundaryNodes([...current, nextNode], boundaryConfig, boundaryLabels))
    setStatus(tf('llmDesignerPage.status.addedNodeAtCursor', { nodeId: id }))
  }, [selectedTemplateKey, setNodes, templateCatalog, boundaryConfig, boundaryLabels, tf])

  const generatePresetChain = useCallback(() => {
    const preset = WORKFLOW_LINK_PRESET_BY_KEY[selectedPresetKey as keyof typeof WORKFLOW_LINK_PRESET_BY_KEY]
    if (!preset) {
      setStatus(t('llmDesignerPage.status.presetChooseValid'))
      return
    }
    const templateByKey = new Map(templateCatalog.map((item) => [item.key, item]))
    const startIndex = Date.now()
    const idMap = new Map()
    const nextNodes: Node[] = preset.nodes.map((presetNode, index) => {
      const template = templateByKey.get(presetNode.templateKey)
      if (!template) {
        return {
          id: joinIdParts(presetNode.id, startIndex + index),
          position: presetNode.position,
          data: { label: tf('llmDesignerPage.status.missingTemplate', { templateKey: presetNode.templateKey }), node_type: 'join' },
        }
      }
      const nextId = joinIdParts(presetNode.id, startIndex + index)
      idMap.set(presetNode.id, nextId)
      return {
        id: nextId,
        position: presetNode.position,
        data: {
          ...normalizeTemplateData(template, asObject(presetNode.overrides)),
          label: appendDisplaySuffix(template.label, index + 1),
        },
      }
    })

    const nextEdges: Edge[] = preset.edges
      .map((edge, index) => {
        const source = idMap.get(edge.source)
        const target = idMap.get(edge.target)
        if (!source || !target) return null
        return {
          id: joinIdParts(edge.id, startIndex + index),
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

    setNodes(ensureBoundaryNodes(enrichedNodes, boundaryConfig, boundaryLabels))
    setEdges(nextEdges)
    setSelectedNodeIds([])
    setSelectedEdgeIds([])
    setStatus(tf('llmDesignerPage.status.generatedPresetChain', { label: preset.label }))
    window.requestAnimationFrame(() => {
      flowRef.current?.fitView({ duration: 260, padding: 0.2 })
    })
  }, [selectedPresetKey, setEdges, setNodes, templateCatalog, boundaryConfig, boundaryLabels, t, tf])

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
      return [node.id, label, nodeType].join(' ').toLowerCase().includes(query)
    })
  }, [nodeSidebarQuery, nodes])

  const openNodeCardById = useCallback((nodeId: string) => {
    const targetNode = nodes.find((item) => item.id === nodeId)
    if (!targetNode) {
      setStatus(tf('llmDesignerPage.status.nodeNotFound', { nodeId }))
      return
    }
    const cardX = isNodeSidebarCollapsed ? 24 : leftSidebarWidth + 24
    setEditingNodeId(nodeId)
    setSelectedNodeIds([nodeId])
    setNodeInfoDraft(JSON.stringify((targetNode.data || {}) as UnknownRecord, null, 2))
    setNodeInfoCard((prev) => ({ ...prev, open: true, x: cardX, y: 28 }))
    setFromNodeId((prev) => prev || nodeId)
    setToNodeId((prev) => (prev && prev !== nodeId ? prev : ''))
  }, [isNodeSidebarCollapsed, leftSidebarWidth, nodes, tf])

  const focusNodeById = useCallback((nodeId: string) => {
    const targetNode = nodes.find((item) => item.id === nodeId)
    const instance = flowRef.current
    if (!targetNode || !instance) {
      setStatus(tf('llmDesignerPage.status.focusFailed', { nodeId }))
      return
    }
    const zoom = Math.max(instance.getZoom(), 1)
    void instance.setCenter(targetNode.position.x + 120, targetNode.position.y + 32, { duration: 260, zoom })
    setStatus(tf('llmDesignerPage.status.focusedNode', { nodeId }))
  }, [nodes, tf])

  const deleteNodeById = useCallback((nodeId: string) => {
    if (isBoundaryNodeId(nodeId)) {
      setStatus(tf('llmDesignerPage.status.deleteBlocked', { nodeId }))
      return
    }
    if (!nodes.some((item) => item.id === nodeId)) {
      setStatus(tf('llmDesignerPage.status.deleteFailed', { nodeId }))
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
    setStatus(tf('llmDesignerPage.status.deletedNode', { nodeId }))
  }, [editingNodeId, nodes, setEdges, setNodes, tf])

  return (
    <section className="llm-designer-page llm-designer-page--full llm-designer-page--quiet">
      <header className="llm-designer-header">
        <div className="llm-designer-header__copy">
          <small>{t('llmDesignerPage.header.eyebrow')}</small>
          <h2>{t('llmDesignerPage.header.title')}</h2>
          <p>{t('llmDesignerPage.header.description')}</p>
        </div>
        <div className="llm-designer-header__stats">{statsText}</div>
      </header>

      <div
        className="llm-designer-canvas"
        ref={canvasRef}
        style={{ position: 'relative' }}
        onDoubleClick={(event) => {
          const target = event.target as HTMLElement
          if (!target.closest(REACT_FLOW_PANE_SELECTOR)) return
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
            transition: SIDEBAR_WIDTH_TRANSITION,
          }}
        >
          <div className="llm-canvas-sidebar__head">
            {!isNodeSidebarCollapsed && <strong>{t('llmDesignerPage.sidebar.nodes')}</strong>}
            <button
              type="button"
              className="llm-canvas-sidebar__toggle"
              onClick={() => setIsNodeSidebarCollapsed((prev) => !prev)}
              aria-label={isNodeSidebarCollapsed ? t('llmDesignerPage.sidebar.toggleExpand') : t('llmDesignerPage.sidebar.toggleCollapse')}
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
                  placeholder={t('llmDesignerPage.sidebar.searchPlaceholder')}
                />
              </div>
              <div className="llm-canvas-sidebar__count">
                {tf('llmDesignerPage.sidebar.count', { filtered: filteredNodes.length, total: nodes.length })}
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
                          {t('llmDesignerPage.action.focus')}
                        </button>
                        <button
                          type="button"
                          className="llm-canvas-node-item__action is-danger"
                          onClick={() => deleteNodeById(node.id)}
                        >
                          {t('llmDesignerPage.action.delete')}
                        </button>
                      </div>
                    </article>
                  )
                })}
                {!filteredNodes.length && (
                  <div className="llm-canvas-sidebar__empty">{t('llmDesignerPage.sidebar.empty')}</div>
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
          {renderCanvasPanel('templates', t('llmDesignerPage.panel.templates'), (
            <NodeTemplatePalette
              templates={templateCatalog}
              selectedTemplateKey={selectedTemplateKey}
              onSelectTemplate={(template) => setSelectedTemplateKey(template.key)}
              onAddTemplate={addTemplateNode}
              onApplyTemplateToSelected={applyTemplateToSelected}
              selectedNodeCount={selectedNodeIds.length}
              title={t('llmDesignerPage.palette.title')}
            />
          ))}

          {renderCanvasPanel('p2p', t('llmDesignerPage.panel.p2p'), (
            <>
              <div className="form-grid cols-2">
                <label>
                  <span>{t('llmDesignerPage.field.pointFrom')}</span>
                  <select value={fromNodeId} onChange={(event) => setFromNodeId(event.target.value)}>
                    <option value="">{t('llmDesignerPage.placeholder.sourceNode')}</option>
                    {nodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {asKey(asObject(node.data).label, node.id)} ({node.id})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>{t('llmDesignerPage.field.pointTo')}</span>
                  <select value={toNodeId} onChange={(event) => setToNodeId(event.target.value)}>
                    <option value="">{t('llmDesignerPage.placeholder.targetNode')}</option>
                    {nodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {asKey(asObject(node.data).label, node.id)} ({node.id})
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="inline-actions">
                <button type="button" onClick={connectPointToPoint}>{t('llmDesignerPage.action.connectP2p')}</button>
                <button type="button" onClick={removeSelection} disabled={!selectedCount}>{t('llmDesignerPage.action.deleteSelected')}</button>
                <button type="button" onClick={resetGraph}>{t('llmDesignerPage.action.reset')}</button>
                <button type="button" onClick={exportDsl}>{t('llmDesignerPage.action.exportJson')}</button>
                <button type="button" onClick={() => fileInputRef.current?.click()}>{t('llmDesignerPage.action.importFile')}</button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={JSON_FILE_ACCEPT}
                  hidden
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file) void (async () => {
                      try {
                        const text = await file.text()
                        setJsonDraft(text)
                        importDslFromText(text)
                        setStatus(tf('llmDesignerPage.status.importedFile', { fileName: file.name }))
                      } catch (error) {
                        setStatus(tf('llmDesignerPage.status.importFailed', { message: error instanceof Error ? error.message : t('llmDesignerPage.error.unknown') }))
                      }
                    })()
                    event.target.value = ''
                  }}
                />
              </div>
            </>
          ))}

          {renderCanvasPanel('preset', t('llmDesignerPage.panel.preset'), (
            <>
              <div className="form-grid cols-2">
                <label>
                  <span>{t('llmDesignerPage.field.businessPreset')}</span>
                  <select value={selectedPresetKey} onChange={(event) => setSelectedPresetKey(event.target.value)}>
                    {WORKFLOW_LINK_PRESETS.map((preset) => (
                      <option key={preset.key} value={preset.key}>
                        {preset.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>{t('llmDesignerPage.field.linkDescription')}</span>
                  <input value={selectedPreset?.description || ''} readOnly />
                </label>
              </div>
              <div className="inline-actions">
                <button type="button" onClick={generatePresetChain}>{t('llmDesignerPage.action.generatePresetChain')}</button>
              </div>
            </>
          ))}

          {renderCanvasPanel('runtime', t('llmDesignerPage.panel.runtime'), (
            <>
              <div className="form-grid cols-3">
                <label>
                  <span>graph_id</span>
                  <input value={graphId} onChange={(event) => setGraphId(event.target.value)} placeholder={t('llmDesignerPage.placeholder.graphId')} />
                </label>
                <label>
                  <span>run_id</span>
                  <input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder={t('llmDesignerPage.placeholder.runId')} />
                </label>
                <label>
                  <span>{t('llmDesignerPage.field.runInput')}</span>
                  <input value={runInputText} onChange={(event) => setRunInputText(event.target.value)} placeholder={t('llmDesignerPage.placeholder.runInput')} />
                </label>
              </div>
              <div className="inline-actions">
                <button type="button" onClick={onCompileGraph} disabled={Boolean(busyAction)}>{busyAction === 'compile' ? t('llmDesignerPage.action.compiling') : t('llmDesignerPage.action.compileGraph')}</button>
                <button type="button" onClick={onRunGraph} disabled={Boolean(busyAction)}>{busyAction === 'run' ? t('llmDesignerPage.action.running') : t('llmDesignerPage.action.runGraph')}</button>
                <button type="button" onClick={onGetRunDetail} disabled={Boolean(busyAction)}>{busyAction === 'run-detail' ? t('llmDesignerPage.action.loading') : t('llmDesignerPage.action.getRunDetail')}</button>
                <button type="button" onClick={onGetRunEvents} disabled={Boolean(busyAction)}>{busyAction === 'run-events' ? t('llmDesignerPage.action.loading') : t('llmDesignerPage.action.getRunEvents')}</button>
                <button type="button" onClick={onGetCompiledGraph} disabled={Boolean(busyAction)}>{busyAction === 'compiled' ? t('llmDesignerPage.action.loading') : t('llmDesignerPage.action.getCompiledGraph')}</button>
              </div>
              <div className="status-line">
                {tf('llmDesignerPage.status.runtimeLine', { status })}
              </div>
            </>
          ))}

          {renderCanvasPanel('json', t('llmDesignerPage.panel.json'), (
            <div className="llm-designer-json">
              <label htmlFor="llm-designer-json-input">{t('llmDesignerPage.field.jsonImportExport')}</label>
              <textarea id="llm-designer-json-input" value={jsonDraft} onChange={(event) => setJsonDraft(event.target.value)} spellCheck={false} placeholder={t('llmDesignerPage.placeholder.jsonDraft')} />
              <div className="llm-designer-json-actions">
                <button type="button" onClick={onImportJson}>{t('llmDesignerPage.action.importJsonText')}</button>
              </div>
            </div>
          ))}

          {renderCanvasPanel('results', t('llmDesignerPage.panel.results'), (
            <div className="form-grid cols-2">
              <label>
                <span>{t('llmDesignerPage.field.compileResponse')}</span>
                <textarea rows={10} value={compileResultText} onChange={(event) => setCompileResultText(event.target.value)} />
              </label>
              <label>
                <span>{t('llmDesignerPage.field.runResponseEvents')}</span>
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
            setNodeInfoDraft(JSON.stringify((node.data || {}) as UnknownRecord, null, 2))
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
  const locale = useAppLocale()
  const t = useCallback((key: LlmDesignerMessageKey, fallback?: string) => translate(locale, key, fallback), [locale])
  const tf = useCallback(
    (key: LlmDesignerMessageKey, values: TemplateValues, fallback?: string) =>
      formatLlmDesignerTemplate(t(key, fallback), values),
    [t],
  )
  const boundaryLabels = useMemo<BoundaryNodeLabels>(
    () => ({
      frontendInput: t('llmDesignerPage.boundary.frontendInput'),
      databaseSink: t('llmDesignerPage.boundary.databaseSink'),
      frontendEdge: t('llmDesignerPage.boundary.frontendEdge'),
      databaseEdge: t('llmDesignerPage.boundary.databaseEdge'),
    }),
    [t],
  )
  const templateCatalog = useMemo(() => createTemplateCatalog(t), [t])
  const preset = WORKFLOW_LINK_PRESET_BY_KEY[DEFAULT_WORKFLOW_LINK_PRESET_KEY]
  const previewNodes = useMemo(() => ensureBoundaryNodes(baseNodes, undefined, boundaryLabels).map((node) => ({
    id: node.id,
    label: asKey(asObject(node.data).label, node.id),
    nodeType: asKey(asObject(node.data).node_type, node.type || 'unknown'),
    role: asKey(asObject(node.data).role, ''),
  })), [boundaryLabels])
  const previewEdges = useMemo(
    () => [...baseEdges, ...buildAutoBridgeEdges(ensureBoundaryNodes(baseNodes, undefined, boundaryLabels), baseEdges, boundaryLabels)],
    [boundaryLabels],
  )
  const visibleTemplates = useMemo(() => templateCatalog.slice(0, 8), [templateCatalog])
  const visibleProfiles = useMemo(() => NODE_INFO_PROFILES.slice(0, 4).map((profile) => localizeProfile(profile, t)), [t])

  return (
    <section className="llm-designer-page llm-designer-page--full llm-designer-page--quiet">
      <header className="llm-designer-header">
        <div className="llm-designer-header__copy">
          <small>{t('llmDesignerPage.storybook.eyebrow')}</small>
          <h2>{t('llmDesignerPage.header.title')}</h2>
          <p>{t('llmDesignerPage.storybook.description')}</p>
        </div>
        <div className="llm-designer-header__stats">
          {tf('llmDesignerPage.stats.storybook', { templates: templateCatalog.length, nodes: previewNodes.length, edges: previewEdges.length })}
        </div>
      </header>

      <div className="content-stack">
        <section className="panel">
          <div className="panel-header">
            <h2>{t('llmDesignerPage.storybook.contractTitle')}</h2>
            <span className="chip">{tf('llmDesignerPage.field.project', { projectKey })}</span>
          </div>
          <p className="status-line">
            {t('llmDesignerPage.storybook.contractStatus')}
          </p>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>{t('llmDesignerPage.storybook.defaultWorkflowPreview')}</h2>
            <span className="chip">{preset.label}</span>
          </div>
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: CSS_AUTO_FIT_GRID_180, gap: 12 }}>
              {previewNodes.map((node) => (
                <article key={node.id} style={STORYBOOK_CARD_STYLE}>
                  <strong>{node.label}</strong>
                  <div className="status-line">{node.id}</div>
                  <div className="status-line">{tf('llmDesignerPage.field.typeValue', { value: node.nodeType })}</div>
                  <div className="status-line">{tf('llmDesignerPage.field.roleValue', { value: node.role || '-' })}</div>
                </article>
              ))}
            </div>
            <div className="status-line">
              {tf('llmDesignerPage.field.edgesValue', { value: previewEdges.map((edge) => [edge.source, edge.target].join(' -> ')).join(' | ') })}
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>{t('llmDesignerPage.storybook.templatePalette')}</h2>
            <span className="chip">{t('llmDesignerPage.storybook.dedupedChip')}</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: CSS_AUTO_FIT_GRID_220, gap: 12 }}>
            {visibleTemplates.map((template) => (
              <article key={template.key} style={STORYBOOK_CARD_STYLE}>
                <strong>{template.label}</strong>
                <div className="status-line">{template.key}</div>
                <div className="status-line">{template.description || t('llmDesignerPage.empty.noDescription')}</div>
                <div className="status-line">{tf('llmDesignerPage.field.nodeTypeValue', { value: template.nodeType })}</div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>{t('llmDesignerPage.storybook.nodeProfiles')}</h2>
            <span className="chip">{t('llmDesignerPage.storybook.editablePresetsChip')}</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: CSS_AUTO_FIT_GRID_220, gap: 12 }}>
            {visibleProfiles.map((profile) => (
              <article key={profile.key} style={STORYBOOK_CARD_STYLE}>
                <strong>{profile.label}</strong>
                <div className="status-line">{profile.description || '-'}</div>
                <div className="status-line">{tf('llmDesignerPage.field.nodeTypeValue', { value: profile.nodeType })}</div>
                <div className="status-line">{tf('llmDesignerPage.field.modelValue', { value: asKey(profile.data.model, '-') })}</div>
              </article>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>{t('llmDesignerPage.storybook.runtimeContract')}</h2>
            <span className="chip">{t('llmDesignerPage.storybook.apiIntegrationChip')}</span>
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
              <span>{t('llmDesignerPage.field.runInput')}</span>
              <input value='{"query":"battery market"}' readOnly />
            </label>
          </div>
          <div className="inline-actions">
            <button type="button" disabled>{t('llmDesignerPage.action.compileGraph')}</button>
            <button type="button" disabled>{t('llmDesignerPage.action.runGraph')}</button>
            <button type="button" disabled>{t('llmDesignerPage.action.getRunDetail')}</button>
            <button type="button" disabled>{t('llmDesignerPage.action.getRunEvents')}</button>
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

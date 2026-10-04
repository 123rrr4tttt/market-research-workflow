import './workflow-manager.css'
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import GraphWorkspace, {
  type GraphWorkspaceEdge,
  type GraphWorkspaceNode,
} from './graph/GraphWorkspace'
import { GRAPH_COLOR_THEMES, assignLegendColors, type PaletteKey } from '../lib/graph-colors'
import {
  createFunctorialMotif,
  createFunctorialWorkflow,
  listFunctorialMotifs,
  listFunctorialOperators,
  listFunctorialWorkflows,
  runFunctorialWorkflow,
  type MotifSpec,
  type OperatorSpec,
  type WorkflowSpec,
} from '../lib/api/domains/functorial'

type WorkflowManagerPageProps = {
  projectKey: string
  presentationMode?: 'runtime' | 'storybook-lite'
}

type CatalogKind = 'operator' | 'motif' | 'workflow'
type ViewTab = 'motif' | 'workflow' | 'network'
type ControlSectionKey = 'catalog' | 'motif' | 'workflow' | 'run'

type AsyncActionState = {
  isPending: boolean
  error: string | null
  result: string | null
}

const QUERY_KEYS = {
  operators: ['functorial', 'operators'] as const,
  motifs: ['functorial', 'motifs'] as const,
  workflows: ['functorial', 'workflows'] as const,
}

const KIND_LABEL: Record<CatalogKind, string> = {
  operator: 'Operator',
  motif: 'Motif',
  workflow: 'Workflow',
}

const IDLE_ACTION: AsyncActionState = { isPending: false, error: null, result: null }
const PALETTE_KEY: PaletteKey = 'bcp_unified'
const PALETTE = GRAPH_COLOR_THEMES[PALETTE_KEY]

const KIND_COLOR = assignLegendColors(
  ['operator', 'motif', 'workflow'],
  PALETTE_KEY,
  'node',
  { contrast: 0.48, spread: 0.72, domainExpand: 0.18 },
)

function kindColor(kind: CatalogKind) {
  return KIND_COLOR[kind] || PALETTE.anchors[1]
}

function parseRef(ref: string): { kind: 'operator' | 'motif'; id: string } {
  const str = String(ref ?? '')
  const separator = str.indexOf(':')
  if (separator <= 0) return { kind: 'operator', id: str }
  const head = str.slice(0, separator)
  const tail = str.slice(separator + 1)
  return { kind: head === 'motif' ? 'motif' : 'operator', id: tail || str }
}

function expandRefsToOperators(
  refs: string[],
  motifById: Map<string, MotifSpec>,
): { operatorIds: string[]; skippedMotifs: string[] } {
  const operatorIds: string[] = []
  const skippedMotifs: string[] = []
  const visiting = new Set<string>()

  function appendRef(ref: string) {
    const { kind, id } = parseRef(ref)
    if (!id) return
    if (kind === 'operator') {
      operatorIds.push(id)
      return
    }
    // motif → recurse into its composition (preserve order), cycle-safe
    if (visiting.has(id)) {
      skippedMotifs.push(id)
      return
    }
    const motif = motifById.get(id)
    if (!motif) {
      skippedMotifs.push(id)
      return
    }
    visiting.add(id)
    const composition = motif.composition ?? []
    composition.forEach(appendRef)
    visiting.delete(id)
  }

  refs.forEach(appendRef)
  return { operatorIds, skippedMotifs }
}

function schemaFieldKeys(schema: Record<string, unknown> | undefined, fallback: string[]): string[] {
  const properties = schema?.properties
  if (properties && typeof properties === 'object' && !Array.isArray(properties)) {
    const keys = Object.keys(properties)
    if (keys.length > 0) return keys
  }
  return fallback
}

type OperatorIONode = {
  kind: 'input' | 'output'
  id: string
  label: string
  field: string
  operatorId?: string
  connectedOperatorIds: string[]
}

type GraphNode = OperatorNode | OperatorIONode

function isPortNode(node: GraphNode): node is OperatorIONode {
  return node.kind === 'input' || node.kind === 'output'
}

const inputPortId = (field: string) => `input:${field}`
const outputPortId = (operatorId: string, field: string) => `output:${operatorId}:${field}`

function operatorDomain(id: string): string {
  const parts = id.split('.')
  return parts.length >= 2 ? parts.slice(0, 2).join('.') : id
}

type NetworkEdge = {
  source: string
  target: string
  kind: 'input' | 'output' | 'io' | 'composition' | 'domain'
}

function buildOperatorIONetwork(
  operators: OperatorSpec[],
  motifs: MotifSpec[],
  workflows: WorkflowSpec[],
): { nodes: GraphNode[]; edges: NetworkEdge[] } {
  const motifById = new Map(motifs.map((item) => [item.motif_id, item]))
  const nodeById = new Map<string, OperatorNode>()
  const inputPorts = new Map<string, { connected: string[] }>()
  const outputPorts = new Map<string, { operatorId: string; field: string }>()

  operators.forEach((op) => {
    const inputFields = schemaFieldKeys(op.input_schema, ['object'])
    const outputFields = schemaFieldKeys(op.output_schema, ['object'])
    nodeById.set(op.operator_id, {
      kind: 'operator',
      id: op.operator_id,
      label: op.name || op.operator_id,
      risk: op.risk,
      inputFields,
      outputFields,
      inputSummary: schemaSummary(op.input_schema),
      outputSummary: schemaSummary(op.output_schema),
    })
    inputFields.forEach((field) => {
      const id = inputPortId(field)
      const port = inputPorts.get(id) || { connected: [] }
      if (!port.connected.includes(op.operator_id)) port.connected.push(op.operator_id)
      inputPorts.set(id, port)
    })
    outputFields.forEach((field) => {
      outputPorts.set(outputPortId(op.operator_id, field), { operatorId: op.operator_id, field })
    })
  })

  const nodes: GraphNode[] = Array.from(nodeById.values())
  inputPorts.forEach((port, id) => {
    const field = id.slice('input:'.length)
    nodes.push({
      kind: 'input',
      id,
      label: `in ${field}`,
      field,
      connectedOperatorIds: port.connected,
    })
  })
  outputPorts.forEach((port, id) => {
    nodes.push({
      kind: 'output',
      id,
      label: `out ${port.field}`,
      field: port.field,
      operatorId: port.operatorId,
      connectedOperatorIds: [port.operatorId],
    })
  })

  const edgeSet = new Set<string>()
  const edges: NetworkEdge[] = []
  const pushEdge = (source: string, target: string, kind: NetworkEdge['kind']) => {
    if (!source || !target || source === target) return
    const key = `${source}→${target}→${kind}`
    if (edgeSet.has(key)) return
    edgeSet.add(key)
    edges.push({ source, target, kind })
  }

  // 1) 全局端口基底：operator 只和自己的端口直连，不同 operator 通过同名 I/O 端口连通。
  inputPorts.forEach((port, inputId) => {
    port.connected.forEach((operatorId) => pushEdge(inputId, operatorId, 'input'))
  })
  outputPorts.forEach((_, outputId) => {
    const port = outputPorts.get(outputId)!
    pushEdge(port.operatorId, outputId, 'output')
  })

  const ids = Array.from(nodeById.keys())
  ids.forEach((a) => {
    const aOut = nodeById.get(a)!.outputFields ?? []
    ids.forEach((b) => {
      if (a === b) return
      const bIn = nodeById.get(b)!.inputFields ?? []
      aOut.forEach((field) => {
        if (bIn.includes(field)) pushEdge(outputPortId(a, field), inputPortId(field), 'io')
      })
    })
  })

  // 2) 组合边：motif.composition / workflow.steps 递归展开后的顺序边
  const motifsSeq = motifs.map((item) => expandRefsToOperators(item.composition ?? [], motifById).operatorIds)
  const workflowsSeq = workflows.map((item) =>
    expandRefsToOperators(
      ((item.steps as unknown as Array<string | { ref?: string }> | undefined) ?? []).map((step) =>
        typeof step === 'string' ? step : step?.ref ?? '',
      ),
      motifById,
    ).operatorIds,
  )
  ;[...motifsSeq, ...workflowsSeq].forEach((seq) => {
    for (let i = 1; i < seq.length; i++) pushEdge(seq[i - 1], seq[i], 'composition')
  })

  // 3) 兜底同域弱连接：同一 domain 内以第一个为聚合点，避免孤点
  const byDomain = new Map<string, string[]>()
  ids.forEach((id) => {
    const domain = operatorDomain(id)
    const list = byDomain.get(domain) || []
    list.push(id)
    byDomain.set(domain, list)
  })
  byDomain.forEach((members) => {
    if (members.length < 2) return
    const sorted = [...members].sort()
    const hub = sorted[0]
    sorted.slice(1).forEach((member) => pushEdge(hub, member, 'domain'))
  })

  return { nodes, edges }
}

function buildOperatorNetwork(
  operators: OperatorSpec[],
  motifs: MotifSpec[],
  workflows: WorkflowSpec[],
): { nodes: GraphNode[]; edges: NetworkEdge[] } {
  const network = buildOperatorIONetwork(operators, motifs, workflows)
  const nodes = network.nodes.filter((node) => !isPortNode(node))
  const nodeIds = new Set(nodes.map((node) => node.id))
  return {
    nodes,
    edges: network.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)),
  }
}

function schemaSummary(schema: Record<string, unknown> | undefined): string {
  if (!schema) return '-'
  const properties = schema.properties
  if (properties && typeof properties === 'object' && !Array.isArray(properties)) {
    const keys = Object.keys(properties)
    if (keys.length > 0) {
      const typeLabel = typeof schema.type === 'string' ? schema.type : 'object'
      return `${typeLabel} { ${keys.join(', ')} }`
    }
  }
  if (typeof schema.type === 'string') return schema.type
  return 'object'
}

function splitRefs(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function splitLaws(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error || '')
}

type OperatorNode = {
  kind: 'operator'
  id: string
  label: string
  risk?: string
  inputSummary: string
  outputSummary: string
  inputFields?: string[]
  outputFields?: string[]
}

type CatalogItem = { id: string; label: string }

const VIEW_TABS: { id: ViewTab; label: string }[] = [
  { id: 'motif', label: 'Motif' },
  { id: 'workflow', label: 'Workflow' },
  { id: 'network', label: 'Operator 网络' },
]

const VIEW_TITLE: Record<ViewTab, string> = {
  motif: 'Motif · Operator 展开',
  workflow: 'Workflow · Operator 展开',
  network: 'Operator 网络',
}


function AgentField({
  label,
  value,
  onChange,
  placeholder,
  textarea = false,
  rows = 3,
  mono = false,
  hint,
}: {
  label: string
  value: string
  onChange: (next: string) => void
  placeholder?: string
  textarea?: boolean
  rows?: number
  mono?: boolean
  hint?: string
}) {
  return (
    <label className="gv2-control-chip wm-field">
      <span className="wm-field-label">{label}</span>
      {textarea ? (
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          rows={rows}
          className={`wm-textarea${mono ? ' wm-input--mono' : ''}`}
        />
      ) : (
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className={`wm-input${mono ? ' wm-input--mono' : ''}`}
        />
      )}
      {hint ? <span className="wm-field-hint">{hint}</span> : null}
    </label>
  )
}

function ActionFeedback({ action }: { action: AsyncActionState }) {
  if (action.result) {
    return (
      <div className="wm-feedback wm-feedback--ok" role="status">
        <span aria-hidden>✔</span>
        <span>{action.result}</span>
      </div>
    )
  }
  if (action.error) {
    return (
      <div className="wm-feedback wm-feedback--err" role="alert">
        <span aria-hidden>✕</span>
        <span>{action.error}</span>
      </div>
    )
  }
  return null
}

type WorkflowManagerShellProps = {
  projectKey: string
  operators: OperatorSpec[]
  motifs: MotifSpec[]
  workflows: WorkflowSpec[]
  loading: boolean
  error: string | null
  motifAction: AsyncActionState
  workflowAction: AsyncActionState
  runAction: AsyncActionState
  onCreateMotif: (payload: MotifSpec) => void
  onCreateWorkflow: (payload: WorkflowSpec) => void
  onRunWorkflow: (workflowId: string, inputs: Record<string, unknown>) => void
}

function WorkflowManagerShell({
  projectKey,
  operators,
  motifs,
  workflows,
  loading,
  error,
  motifAction,
  workflowAction,
  runAction,
  onCreateMotif,
  onCreateWorkflow,
  onRunWorkflow,
}: WorkflowManagerShellProps) {
  const [viewTab, setViewTab] = useState<ViewTab>('motif')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [catalogQuery, setCatalogQuery] = useState('')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [openSections, setOpenSections] = useState<Record<ControlSectionKey, boolean>>({
    catalog: true,
    motif: false,
    workflow: false,
    run: false,
  })

  const [motifId, setMotifId] = useState('')
  const [motifName, setMotifName] = useState('')
  const [motifComposition, setMotifComposition] = useState('')
  const [workflowId, setWorkflowId] = useState('')
  const [workflowName, setWorkflowName] = useState('')
  const [workflowSteps, setWorkflowSteps] = useState('')
  const [workflowLaws, setWorkflowLaws] = useState('')
  const [runWorkflowId, setRunWorkflowId] = useState('')
  const [runInputs, setRunInputs] = useState('{\n  "query": ""\n}')
  const [runParseError, setRunParseError] = useState<string | null>(null)

  const motifItems = useMemo(
    () => motifs.map((item) => ({ id: item.motif_id, label: item.name || item.motif_id })),
    [motifs],
  )
  const workflowItems = useMemo(
    () => workflows.map((item) => ({ id: item.workflow_id, label: item.name || item.workflow_id })),
    [workflows],
  )
  const operatorItems = useMemo(
    () => operators.map((item) => ({ id: item.operator_id, label: item.name || item.operator_id })),
    [operators],
  )

  const motifById = useMemo(() => new Map(motifs.map((m) => [m.motif_id, m])), [motifs])
  const workflowById = useMemo(() => new Map(workflows.map((w) => [w.workflow_id, w])), [workflows])

  const isNetwork = viewTab === 'network'
  const catalogItems = isNetwork ? operatorItems : viewTab === 'motif' ? motifItems : workflowItems
  const catalogKind: CatalogKind = isNetwork ? 'operator' : viewTab
  const activeItems = isNetwork ? [] as CatalogItem[] : viewTab === 'motif' ? motifItems : workflowItems
  const effectiveId = isNetwork
    ? null
    : expandedId && activeItems.some((item) => item.id === expandedId)
      ? expandedId
      : activeItems[0]?.id ?? null

  const expansion = useMemo(() => {
    if (!effectiveId) {
      return {
        nodes: [] as GraphNode[],
        edges: [] as NetworkEdge[],
        skipped: [] as string[],
      }
    }
    const refs =
      viewTab === 'motif'
        ? (motifById.get(effectiveId)?.composition ?? []).filter((ref): ref is string => Boolean(ref))
        : ((workflowById.get(effectiveId)?.steps as unknown as Array<string | { ref?: string }> | undefined) ?? [])
            .map((step) => (typeof step === 'string' ? step : step?.ref ?? ''))
            .filter((ref): ref is string => Boolean(ref))
    const { operatorIds, skippedMotifs } = expandRefsToOperators(refs, motifById)
    const selected = new Set(operatorIds)
    const global = buildOperatorIONetwork(operators, motifs, workflows)
    const nodes = global.nodes
      .filter((node) => !isPortNode(node)
        ? selected.has(node.id)
        : node.connectedOperatorIds.some((id) => selected.has(id)))
      .map((node) => {
        if (!isPortNode(node)) return node
        return { ...node, connectedOperatorIds: node.connectedOperatorIds.filter((id) => selected.has(id)) }
      })
    const nodeIds = new Set(nodes.map((node) => node.id))
    const edges = global.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
    return { nodes, edges, skipped: skippedMotifs }
  }, [effectiveId, viewTab, motifById, workflowById, operators, motifs, workflows])

  const network = useMemo(() => {
    if (!isNetwork) return { nodes: [] as GraphNode[], edges: [] as NetworkEdge[] }
    return buildOperatorNetwork(operators, motifs, workflows)
  }, [isNetwork, operators, motifs, workflows])

  const activeGraph = useMemo(
    () => (isNetwork ? network : { nodes: expansion.nodes, edges: expansion.edges }),
    [isNetwork, network, expansion],
  )
  const workspaceNodes = useMemo<GraphWorkspaceNode[]>(
    () => activeGraph.nodes.map((node) => {
      if (isPortNode(node)) {
        return {
          id: node.id,
          name: node.label,
          type: node.kind,
          symbolSize: isNetwork ? 28 : 24,
          detail: [
            `方向：${node.kind}`,
            `字段：${node.field}`,
            `相连 operator：${node.connectedOperatorIds.join('、') || '-'}`,
          ],
        }
      }
      return {
        id: node.id,
        name: node.label,
        type: 'operator',
        symbolSize: isNetwork ? 28 : 34,
        detail: [
          `risk：${node.risk || '未标注'}`,
          `输入：${node.inputFields?.length ? node.inputFields.join('、') : node.inputSummary}`,
          `输出：${node.outputFields?.length ? node.outputFields.join('、') : node.outputSummary}`,
        ],
      }
    }),
    [activeGraph.nodes, isNetwork],
  )
  const workspaceEdges = useMemo<GraphWorkspaceEdge[]>(
    () => activeGraph.edges.map((edge) => ({
      source: edge.source,
      target: edge.target,
      type: `edge:${edge.kind}`,
      dashed: edge.kind === 'domain',
      arrow: edge.kind !== 'domain',
    })),
    [activeGraph.edges],
  )
  const selectedDetail = selectedNodeId
    ? activeGraph.nodes.find((item) => item.id === selectedNodeId) || null
    : null

  const normalizedCatalog = catalogQuery.trim().toLowerCase()
  const filteredCatalog = normalizedCatalog
    ? catalogItems.filter((item) => item.label.toLowerCase().includes(normalizedCatalog) || item.id.toLowerCase().includes(normalizedCatalog))
    : catalogItems
  const selectedCatalogId = isNetwork ? selectedNodeId : effectiveId

  function toggleSection(key: ControlSectionKey) {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  function handleCreateMotif() {
    onCreateMotif({ motif_id: motifId.trim(), name: motifName.trim(), composition: splitRefs(motifComposition) })
  }

  function handleCreateWorkflow() {
    onCreateWorkflow({
      workflow_id: workflowId.trim(),
      name: workflowName.trim(),
      steps: splitRefs(workflowSteps).map((ref) => ({ ref })),
      laws: splitLaws(workflowLaws),
    })
  }

  function handleRunWorkflow() {
    setRunParseError(null)
    let inputs: Record<string, unknown>
    try {
      inputs = JSON.parse(runInputs) as Record<string, unknown>
    } catch (err) {
      setRunParseError(errorMessage(err))
      return
    }
    onRunWorkflow(runWorkflowId, inputs)
  }

  const handleViewTabChange = (tab: ViewTab) => {
    setSelectedNodeId(null)
    setExpandedId(null)
    setViewTab(tab)
  }
  const handleExpandedIdChange = (id: string) => {
    setSelectedNodeId(null)
    setExpandedId(id)
  }
  const macroStats = [
    { label: '图', value: 1 },
    { label: 'Operators', value: operators.length },
    { label: 'Motifs', value: motifs.length },
    { label: 'Workflows', value: workflows.length },
    { label: '边数', value: workspaceEdges.length },
    { label: '已选', value: selectedDetail ? 1 : 0 },
    { label: '节点', value: workspaceNodes.length },
  ]

  return (
    <div className="workflow-manager-page gv2-root" data-testid="workflow-manager-page">
      <section className="gv2-main">
        <div className="gv2-head">
          <div>
            <strong>Workflow &amp; Motif 管理器</strong>
            <span>Agent 函子化 Operator / Motif / Workflow</span>
          </div>
          <div className="wm-head-right">
            <span>project · {projectKey}</span>
            {loading ? <span role="status">加载中…</span> : null}
            {error ? <span className="is-error" role="alert">数据加载异常</span> : null}
          </div>
        </div>

        <div className="gv2-layout">
          <GraphWorkspace
            nodes={workspaceNodes}
            edges={workspaceEdges}
            loading={loading}
            error={error}
            resetKey={`${viewTab}:${effectiveId ?? 'network'}`}
            testId="workflow-chart"
            dataAttributes={{
              'data-view-tab': viewTab,
              'data-active-id': effectiveId ?? selectedNodeId ?? '',
              'data-node-count': workspaceNodes.length,
            }}
            onNodeClick={setSelectedNodeId}
            toolbar={
              <>
                <strong>{VIEW_TITLE[viewTab]}</strong>
                <div className="gv2-view-tabs" role="tablist" aria-label="图谱视图">
                  {VIEW_TABS.map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      role="tab"
                      aria-selected={viewTab === tab.id}
                      className={`gv2-select-mode-btn${viewTab === tab.id ? ' is-active' : ''}`}
                      onClick={() => handleViewTabChange(tab.id)}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </>
            }
            controls={
              <>
                <section className={`gv2-control-section${openSections.catalog ? '' : ' is-collapsed'}`}>
                  <button
                    type="button"
                    className="gv2-control-section-head"
                    onClick={() => toggleSection('catalog')}
                  >
                    <strong>当前展开选择</strong>
                    <span>{openSections.catalog ? '收起' : '展开'}</span>
                  </button>
                  {openSections.catalog ? (
                    <div className="gv2-control-section-body wm-section-body">
                      <label className="gv2-control-chip wm-field">
                        <span className="wm-field-label">展开目标</span>
                        <select
                          className="wm-select wm-expansion-select"
                          value={selectedCatalogId ?? ''}
                          onChange={(event) => {
                            if (isNetwork) setSelectedNodeId(event.target.value)
                            else handleExpandedIdChange(event.target.value)
                          }}
                        >
                          {(isNetwork ? operatorItems : activeItems).length === 0 ? <option value="">暂无</option> : null}
                          {(isNetwork ? operatorItems : activeItems).map((item) => (
                            <option key={item.id} value={item.id}>{item.label}</option>
                          ))}
                        </select>
                      </label>
                      <label className="gv2-control-chip wm-field">
                        <span className="wm-field-label">筛选 {KIND_LABEL[catalogKind]}</span>
                        <input
                          className="wm-input"
                          value={catalogQuery}
                          onChange={(event) => setCatalogQuery(event.target.value)}
                          placeholder="名称或 ID"
                          aria-label={`筛选 ${KIND_LABEL[catalogKind]}`}
                        />
                      </label>
                      <div className="wm-catalog-list">
                        {filteredCatalog.length === 0 ? (
                          <div className="wm-catalog-empty">{catalogItems.length === 0 ? '暂无数据' : '无匹配项'}</div>
                        ) : filteredCatalog.slice(0, 80).map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            className={`wm-catalog-item${selectedCatalogId === item.id ? ' is-selected' : ''}`}
                            onClick={() => {
                              if (isNetwork) setSelectedNodeId(item.id)
                              else handleExpandedIdChange(item.id)
                            }}
                          >
                            <span className="wm-catalog-label">
                              <i className="wm-catalog-dot" style={{ background: kindColor(catalogKind) }} aria-hidden />
                              <span>{item.label}</span>
                            </span>
                            <span className="wm-catalog-id">{item.id}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </section>

                <section className={`gv2-control-section${openSections.motif ? '' : ' is-collapsed'}`}>
                  <button type="button" className="gv2-control-section-head" onClick={() => toggleSection('motif')}>
                    <strong>生成 Motif</strong>
                    <span>{openSections.motif ? '收起' : '展开'}</span>
                  </button>
                  {openSections.motif ? (
                    <div className="gv2-control-section-body wm-section-body">
                      <AgentField label="motif_id" value={motifId} onChange={setMotifId} placeholder="embodied.signals.bundle" mono />
                      <AgentField label="name" value={motifName} onChange={setMotifName} placeholder="信号组合" />
                      <AgentField
                        label="composition"
                        value={motifComposition}
                        onChange={setMotifComposition}
                        placeholder={'operator:project.structured_data.search\noperator:agent_artifact.search'}
                        textarea
                        mono
                        hint="每行一个 ref，可用换行或逗号分隔"
                      />
                      <div className="gv2-control-chip">
                        <button
                          type="button"
                          className="wm-btn wm-btn--primary"
                          onClick={handleCreateMotif}
                          disabled={motifAction.isPending || !motifId.trim()}
                        >
                          {motifAction.isPending ? '生成中…' : '生成 Motif'}
                        </button>
                      </div>
                      <ActionFeedback action={motifAction} />
                    </div>
                  ) : null}
                </section>

                <section className={`gv2-control-section${openSections.workflow ? '' : ' is-collapsed'}`}>
                  <button type="button" className="gv2-control-section-head" onClick={() => toggleSection('workflow')}>
                    <strong>生成 Workflow</strong>
                    <span>{openSections.workflow ? '收起' : '展开'}</span>
                  </button>
                  {openSections.workflow ? (
                    <div className="gv2-control-section-body wm-section-body">
                      <AgentField label="workflow_id" value={workflowId} onChange={setWorkflowId} placeholder="embodied.report.write" mono />
                      <AgentField label="name" value={workflowName} onChange={setWorkflowName} placeholder="报告写入" />
                      <AgentField
                        label="steps"
                        value={workflowSteps}
                        onChange={setWorkflowSteps}
                        placeholder={'motif:embodied.signals.bundle\noperator:writing.document.create'}
                        textarea
                        mono
                        hint="每行一个 ref，可用换行或逗号分隔"
                      />
                      <AgentField label="laws" value={workflowLaws} onChange={setWorkflowLaws} placeholder="identity, associativity" mono hint="逗号分隔" />
                      <div className="gv2-control-chip">
                        <button
                          type="button"
                          className="wm-btn wm-btn--primary"
                          onClick={handleCreateWorkflow}
                          disabled={workflowAction.isPending || !workflowId.trim()}
                        >
                          {workflowAction.isPending ? '生成中…' : '生成 Workflow'}
                        </button>
                      </div>
                      <ActionFeedback action={workflowAction} />
                    </div>
                  ) : null}
                </section>

                <section className={`gv2-control-section${openSections.run ? '' : ' is-collapsed'}`}>
                  <button type="button" className="gv2-control-section-head" onClick={() => toggleSection('run')}>
                    <strong>执行</strong>
                    <span>{openSections.run ? '收起' : '展开'}</span>
                  </button>
                  {openSections.run ? (
                    <div className="gv2-control-section-body wm-section-body">
                      <label className="gv2-control-chip wm-field">
                        <span className="wm-field-label">workflow</span>
                        <select
                          className="wm-select"
                          value={runWorkflowId}
                          onChange={(event) => setRunWorkflowId(event.target.value)}
                        >
                          <option value="">请选择</option>
                          {workflowItems.map((item) => (
                            <option key={item.id} value={item.id}>{item.label}</option>
                          ))}
                        </select>
                      </label>
                      <AgentField label="inputs（JSON）" value={runInputs} onChange={setRunInputs} textarea rows={4} mono />
                      {runParseError ? (
                        <div className="wm-feedback wm-feedback--err" role="alert">
                          <span aria-hidden>✕</span>
                          <span>{runParseError}</span>
                        </div>
                      ) : null}
                      <div className="gv2-control-chip">
                        <button
                          type="button"
                          className="wm-btn wm-btn--primary"
                          onClick={handleRunWorkflow}
                          disabled={runAction.isPending || !runWorkflowId}
                        >
                          {runAction.isPending ? '执行中…' : '运行'}
                        </button>
                      </div>
                      <ActionFeedback action={runAction} />
                    </div>
                  ) : null}
                </section>

                <section className="gv2-control-section">
                  <div className="gv2-control-section-head is-static">
                    <strong>节点详情</strong>
                    <span>{selectedDetail ? '已选中' : '未选中'}</span>
                  </div>
                  <div className="gv2-control-section-body wm-section-body">
                    {selectedDetail && isPortNode(selectedDetail) ? (
                      <div className="gv2-node-context">
                        <strong>{selectedDetail.label}</strong>
                        <div className="gv2-node-tags">
                          <span>{selectedDetail.id}</span>
                          <span>方向 · {selectedDetail.kind}</span>
                          <span>字段 · {selectedDetail.field}</span>
                        </div>
                        <div className="gv2-node-context">
                          <strong>相连 operator</strong>
                          <div className="gv2-node-tags">
                            {selectedDetail.connectedOperatorIds.map((id) => (
                              <span key={`connected-${id}`}>{id}</span>
                            ))}
                          </div>
                        </div>
                        <button type="button" className="secondary wm-context-close" onClick={() => setSelectedNodeId(null)}>关闭</button>
                      </div>
                    ) : selectedDetail ? (
                      <div className="gv2-node-context">
                        <strong>{selectedDetail.label}</strong>
                        <div className="gv2-node-tags">
                          <span>{selectedDetail.id}</span>
                          <span>risk · {selectedDetail.risk || '未标注'}</span>
                        </div>
                        <div className="gv2-node-context">
                          <strong>输入</strong>
                          <div className="gv2-node-tags">
                            {(selectedDetail.inputFields?.length ? selectedDetail.inputFields : [selectedDetail.inputSummary]).map((field) => (
                              <span key={`input-${field}`}>{field}</span>
                            ))}
                          </div>
                        </div>
                        <div className="gv2-node-context">
                          <strong>输出</strong>
                          <div className="gv2-node-tags">
                            {(selectedDetail.outputFields?.length ? selectedDetail.outputFields : [selectedDetail.outputSummary]).map((field) => (
                              <span key={`output-${field}`}>{field}</span>
                            ))}
                          </div>
                        </div>
                        <button type="button" className="secondary wm-context-close" onClick={() => setSelectedNodeId(null)}>关闭</button>
                      </div>
                    ) : (
                      <div className="wm-graph-hit-hint">点击图中节点查看 input/output 详情</div>
                    )}
                  </div>
                </section>
                {expansion.skipped.length ? (
                  <div className="wm-feedback wm-feedback--err" role="alert">
                    <span>无法解析 motif：{expansion.skipped.join('、')}</span>
                  </div>
                ) : null}
              </>
            }
          />

          <div className="gv2-macro-stats">
            {macroStats.map((stat) => (
              <div key={stat.label} className="gv2-macro-stat">
                <span>{stat.label}</span>
                <strong>{stat.value}</strong>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}

const DEMO_OPERATORS: OperatorSpec[] = [
  {
    operator_id: 'project.structured_data.search',
    name: '结构化数据检索',
    input_schema: { type: 'object', properties: { query: { type: 'string' } } },
    output_schema: { type: 'object', properties: { items: { type: 'array' } } },
    impl_ref: 'agent_runtime.read_only_tools:project.structured_data.search',
    risk: 'read_only',
  },
  {
    operator_id: 'agent_artifact.search',
    name: 'Artifact 检索',
    input_schema: { type: 'object', properties: { query: { type: 'string' }, limit: { type: 'integer' } } },
    output_schema: { type: 'object', properties: { artifacts: { type: 'array' } } },
    risk: 'read_only',
  },
  {
    operator_id: 'writing.document.create',
    name: '文档写入',
    input_schema: { type: 'object', properties: { title: { type: 'string' }, body: { type: 'string' } } },
    output_schema: { type: 'object', properties: { document_id: { type: 'string' } } },
  },
]

const DEMO_MOTIFS: MotifSpec[] = [
  {
    motif_id: 'embodied.signals.bundle',
    name: '信号组合',
    composition: ['operator:project.structured_data.search', 'operator:agent_artifact.search'],
  },
]

const DEMO_WORKFLOWS: WorkflowSpec[] = [
  {
    workflow_id: 'embodied.report.write',
    name: '报告写入',
    steps: [{ ref: 'motif:embodied.signals.bundle' }, { ref: 'operator:writing.document.create' }],
    laws: ['identity', 'associativity'],
    version: 1,
  },
]

function WorkflowManagerStorybookLite({ projectKey }: { projectKey: string }) {
  return (
    <WorkflowManagerShell
      projectKey={projectKey}
      operators={DEMO_OPERATORS}
      motifs={DEMO_MOTIFS}
      workflows={DEMO_WORKFLOWS}
      loading={false}
      error={null}
      motifAction={IDLE_ACTION}
      workflowAction={IDLE_ACTION}
      runAction={IDLE_ACTION}
      onCreateMotif={() => undefined}
      onCreateWorkflow={() => undefined}
      onRunWorkflow={() => undefined}
    />
  )
}

function WorkflowManagerRuntime({ projectKey }: { projectKey: string }) {
  const queryClient = useQueryClient()
  const operatorsQuery = useQuery({ queryKey: QUERY_KEYS.operators, queryFn: listFunctorialOperators, retry: false })
  const motifsQuery = useQuery({ queryKey: QUERY_KEYS.motifs, queryFn: listFunctorialMotifs, retry: false })
  const workflowsQuery = useQuery({ queryKey: QUERY_KEYS.workflows, queryFn: listFunctorialWorkflows, retry: false })

  const motifMutation = useMutation({
    mutationFn: (payload: MotifSpec) => createFunctorialMotif(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.motifs }),
  })
  const workflowMutation = useMutation({
    mutationFn: (payload: WorkflowSpec) => createFunctorialWorkflow(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.workflows }),
  })
  const runMutation = useMutation({
    mutationFn: ({ workflowId, inputs }: { workflowId: string; inputs: Record<string, unknown> }) =>
      runFunctorialWorkflow(workflowId, inputs),
  })

  const operators = operatorsQuery.data ?? []
  const motifs = motifsQuery.data ?? []
  const workflows = workflowsQuery.data ?? []
  const loading = operatorsQuery.isPending || motifsQuery.isPending || workflowsQuery.isPending
  const error =
    [operatorsQuery.error, motifsQuery.error, workflowsQuery.error]
      .filter(Boolean)
      .map(errorMessage)
      .join('；') || null

  const motifAction: AsyncActionState = {
    isPending: motifMutation.isPending,
    error: motifMutation.error ? errorMessage(motifMutation.error) : null,
    result: motifMutation.data ? `已生成 motif：${motifMutation.data.motif_id}` : null,
  }
  const workflowAction: AsyncActionState = {
    isPending: workflowMutation.isPending,
    error: workflowMutation.error ? errorMessage(workflowMutation.error) : null,
    result: workflowMutation.data ? `已生成 workflow：${workflowMutation.data.workflow_id}` : null,
  }
  const runAction: AsyncActionState = {
    isPending: runMutation.isPending,
    error: runMutation.error ? errorMessage(runMutation.error) : null,
    result: runMutation.data
      ? `运行完成：${runMutation.data.status || 'ok'}${
          runMutation.data.result != null ? ` ${JSON.stringify(runMutation.data.result)}` : ''
        }`
      : null,
  }

  return (
    <WorkflowManagerShell
      projectKey={projectKey}
      operators={operators}
      motifs={motifs}
      workflows={workflows}
      loading={loading}
      error={error}
      motifAction={motifAction}
      workflowAction={workflowAction}
      runAction={runAction}
      onCreateMotif={(payload) => motifMutation.mutate(payload)}
      onCreateWorkflow={(payload) => workflowMutation.mutate(payload)}
      onRunWorkflow={(workflowId, inputs) => runMutation.mutate({ workflowId, inputs })}
    />
  )
}

export default function WorkflowManagerPage({
  projectKey,
  presentationMode = 'runtime',
}: WorkflowManagerPageProps) {
  if (presentationMode === 'storybook-lite') {
    return <WorkflowManagerStorybookLite projectKey={projectKey} />
  }
  return <WorkflowManagerRuntime projectKey={projectKey} />
}

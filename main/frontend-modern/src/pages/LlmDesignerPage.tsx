import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  addEdge,
  Background,
  Controls,
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

type NodeType = 'vector_search' | 'llm_call' | 'join'

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

type LlmDesignerPageProps = {
  projectKey: string
  onExportDsl?: (dsl: DesignerDsl) => void
}

type DesignerLinkParams = {
  templateKey: string
  fromNodeId: string
  toNodeId: string
  graphId: string
  runId: string
  runInputText: string
  nodeId: string
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
  }
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

function inferNodeType(node: Node): NodeType {
  const raw = String((node.data as { node_type?: unknown })?.node_type || node.id || '').toLowerCase()
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

function DesignerCanvas({ onExportDsl }: LlmDesignerPageProps) {
  const linkParams = useMemo(readDesignerLinkParams, [])
  const resolvedTemplateKey = useMemo(() => {
    const key = linkParams.templateKey
    if (!key) return NODE_TEMPLATES[2]?.key || 'llm-call'
    return NODE_TEMPLATES.some((item) => item.key === key) ? key : (NODE_TEMPLATES[2]?.key || 'llm-call')
  }, [linkParams.templateKey])

  const [nodes, setNodes, onNodesChange] = useNodesState(baseNodes)
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

  const [editingNodeId, setEditingNodeId] = useState(linkParams.nodeId)
  const [nodeInfoDraft, setNodeInfoDraft] = useState('{}')
  const [nodeInfoCard, setNodeInfoCard] = useState({ open: Boolean(linkParams.nodeId), x: 20, y: 20, width: 420, height: 420 })

  const nextIdRef = useRef(2)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const flowRef = useRef<ReactFlowInstance<Node, Edge> | null>(null)
  const canvasRef = useRef<HTMLDivElement | null>(null)

  const selectedCount = selectedNodeIds.length + selectedEdgeIds.length
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

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target || connection.source === connection.target) return
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

        const sourceData = asObject(sourceNode.data)
        const targetData = asObject(targetNode.data)
        const sourceOutputs = asList(sourceData.output_vars)
        const outputKeys = (sourceOutputs.length
          ? sourceOutputs.map((item) => asKey(item.name, 'output'))
          : ['output'])

        const currentInputs = asList(targetData.input_vars)
        const nextInputs = [...currentInputs]
        for (const outputKey of outputKeys) {
          const inputName = `${connection.source}.${outputKey}`
          const exists = nextInputs.some((item) => asKey(item.name, '') === inputName)
          if (exists) continue
          nextInputs.push({
            name: inputName,
            value_type: 'string',
            source: 'node_output',
            from_node: connection.source,
            from_key: outputKey,
            required: false,
          })
        }
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
    const template = NODE_TEMPLATES.find((item) => item.key === (templateItem?.key || selectedTemplateKey)) || NODE_TEMPLATES[2]
    if (!template) return
    const id = `${template.key}-${nextIdRef.current}`
    nextIdRef.current += 1
    const nextNode: Node = {
      id,
      position: { x: 160 + nodes.length * 24, y: 160 + nodes.length * 18 },
      data: { ...template.data, label: `${template.label} ${nextIdRef.current - 1}` },
    }
    setNodes((current) => [...current, nextNode])
    setStatus(`Added template node: ${template.label}`)
  }, [nodes.length, selectedTemplateKey, setNodes])

  const applyTemplateToSelected = useCallback((templateItem?: NodeTemplatePaletteItem<Record<string, unknown>>) => {
    if (selectedNodeIds.length !== 1) {
      setStatus('Apply template failed: select exactly one node')
      return
    }
    const template = NODE_TEMPLATES.find((item) => item.key === (templateItem?.key || selectedTemplateKey)) || NODE_TEMPLATES[2]
    if (!template) return
    const targetNodeId = selectedNodeIds[0]
    setNodes((current) =>
      current.map((node) =>
        node.id === targetNodeId
          ? {
              ...node,
              data: {
                ...node.data,
                ...template.data,
                label: `${template.label} ${targetNodeId}`,
              },
            }
          : node,
      ),
    )
    setStatus(`Applied template ${template.label} to ${targetNodeId}`)
  }, [selectedNodeIds, selectedTemplateKey, setNodes])

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
    setEdges((current) => {
      const exists = current.some((edge) => edge.source === source && edge.target === target)
      if (exists) return current
      return addEdge({ id: `e-${source}-${target}-${current.length + 1}`, source, target }, current)
    })
    setNodes((currentNodes) => {
      const sourceNode = currentNodes.find((item) => item.id === source)
      const targetNode = currentNodes.find((item) => item.id === target)
      if (!sourceNode || !targetNode) return currentNodes

      const sourceData = asObject(sourceNode.data)
      const targetData = asObject(targetNode.data)
      const sourceOutputs = asList(sourceData.output_vars)
      const outputKeys = (sourceOutputs.length
        ? sourceOutputs.map((item) => asKey(item.name, 'output'))
        : ['output'])

      const currentInputs = asList(targetData.input_vars)
      const nextInputs = [...currentInputs]
      for (const outputKey of outputKeys) {
        const inputName = `${source}.${outputKey}`
        const exists = nextInputs.some((item) => asKey(item.name, '') === inputName)
        if (exists) continue
        nextInputs.push({
          name: inputName,
          value_type: 'string',
          source: 'node_output',
          from_node: source,
          from_key: outputKey,
          required: false,
        })
      }
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
    setNodes((current) => current.filter((node) => !selectedNodeIds.includes(node.id)))
    setEdges((current) => current.filter((edge) => !selectedEdgeIds.includes(edge.id)))
    setStatus(`Removed ${selectedCount} selected item(s)`)
  }, [selectedCount, selectedEdgeIds, selectedNodeIds, setEdges, setNodes])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.key === 'Delete' || event.key === 'Backspace') && (selectedNodeIds.length || selectedEdgeIds.length)) {
        event.preventDefault()
        setNodes((current) => current.filter((node) => !selectedNodeIds.includes(node.id)))
        setEdges((current) => current.filter((edge) => !selectedEdgeIds.includes(edge.id)))
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedEdgeIds, selectedNodeIds, setEdges, setNodes])

  const resetGraph = useCallback(() => {
    setNodes(baseNodes)
    setEdges(baseEdges)
    setSelectedNodeIds([])
    setSelectedEdgeIds([])
    setStatus('Reset to template')
    window.requestAnimationFrame(() => {
      flowRef.current?.fitView({ duration: 300, padding: 0.2 })
    })
  }, [setEdges, setNodes])

  const collectDsl = useCallback((): DesignerDsl => {
    const viewport = flowRef.current?.getViewport()
    return { version: '1.0', nodes, edges, viewport, meta: { updatedAt: new Date().toISOString() } }
  }, [edges, nodes])

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
    setNodes(parsed.nodes as Node[])
    setEdges(parsed.edges as Edge[])
    if (parsed.viewport) {
      window.requestAnimationFrame(() => {
        flowRef.current?.setViewport(parsed.viewport as Viewport, { duration: 280 })
      })
    }
  }, [setEdges, setNodes])

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
          edges: edges.map((edge) => ({ from: edge.source, to: edge.target })),
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
  }, [graphId, nodes, edges])

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

  const statsText = `Nodes ${nodes.length} · Edges ${edges.length}`

  const addNodeAtPoint = useCallback((clientX: number, clientY: number) => {
    const instance = flowRef.current
    if (!instance) return
    const template = NODE_TEMPLATES.find((item) => item.key === selectedTemplateKey) || NODE_TEMPLATES[2]
    if (!template) return
    const position = instance.screenToFlowPosition({ x: clientX, y: clientY })
    const id = `${template.key}-${nextIdRef.current}`
    nextIdRef.current += 1
    const nextNode: Node = {
      id,
      position,
      data: { ...template.data, label: `${template.label} ${nextIdRef.current - 1}` },
    }
    setNodes((current) => [...current, nextNode])
    setStatus(`Added node at cursor: ${id}`)
  }, [selectedTemplateKey, setNodes])

  return (
    <section className="llm-designer-page panel">
      <header className="llm-designer-header">
        <h2>LLM Designer</h2>
        <p>{statsText}</p>
      </header>

      <NodeTemplatePalette
        templates={NODE_TEMPLATES}
        selectedTemplateKey={selectedTemplateKey}
        onSelectTemplate={(template) => setSelectedTemplateKey(template.key)}
        onAddTemplate={addTemplateNode}
        onApplyTemplateToSelected={applyTemplateToSelected}
        selectedNodeCount={selectedNodeIds.length}
        title="Node Template Palette"
      />

      <div className="form-grid cols-2">
        <label>
          <span>point from</span>
          <select value={fromNodeId} onChange={(event) => setFromNodeId(event.target.value)}>
            <option value="">Select source node</option>
            {nodes.map((node) => (
              <option key={node.id} value={node.id}>{node.id}</option>
            ))}
          </select>
        </label>
        <label>
          <span>point to</span>
          <select value={toNodeId} onChange={(event) => setToNodeId(event.target.value)}>
            <option value="">Select target node</option>
            {nodes.map((node) => (
              <option key={node.id} value={node.id}>{node.id}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="inline-actions">
        <button type="button" onClick={connectPointToPoint}>Connect P2P</button>
        <button type="button" onClick={removeSelection} disabled={!selectedCount}>Delete Selected</button>
        <button type="button" onClick={resetGraph}>Reset</button>
        <button type="button" onClick={exportDsl}>Export JSON</button>
        <span className="status-line">Double-click canvas to add selected template; `Delete` removes selection</span>
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

      <div
        className="llm-designer-canvas"
        ref={canvasRef}
        onDoubleClick={(event) => {
          const target = event.target as HTMLElement
          if (!target.closest('.react-flow__pane')) return
          addNodeAtPoint(event.clientX, event.clientY)
        }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onInit={(instance) => {
            flowRef.current = instance
            instance.fitView({ padding: 0.2 })
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
            setSelectedEdgeIds((pickedEdges || []).map((edge) => edge.id))
            if (pickedIds.length === 1) {
              setFromNodeId((prev) => prev || pickedIds[0])
              setToNodeId((prev) => (prev && prev !== pickedIds[0] ? prev : ''))
            }
          }}
          fitView
        >
          <MiniMap pannable zoomable />
          <Controls />
          <Background gap={24} size={1} />
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
        />
      </div>

      <div className="llm-designer-json">
        <label htmlFor="llm-designer-json-input">JSON import / export</label>
        <textarea id="llm-designer-json-input" value={jsonDraft} onChange={(event) => setJsonDraft(event.target.value)} spellCheck={false} placeholder="Paste exported DSL JSON here..." />
        <div className="llm-designer-json-actions">
          <button type="button" onClick={onImportJson}>Import JSON Text</button>
          <span className="llm-designer-status">{status}</span>
        </div>
      </div>

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
    </section>
  )
}

export default function LlmDesignerPage(props: LlmDesignerPageProps) {
  return (
    <ReactFlowProvider>
      <DesignerCanvas {...props} />
    </ReactFlowProvider>
  )
}

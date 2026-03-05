import { useCallback, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type ReactFlowInstance,
  type ReactFlowJsonObject,
} from '@xyflow/react'

type LlmNodeData = {
  label: string
  detail: string
}

const initialNodes: Array<Node<LlmNodeData>> = [
  {
    id: 'input-1',
    type: 'input',
    position: { x: 80, y: 180 },
    data: { label: 'User Input', detail: 'Question / context' },
  },
  {
    id: 'prompt-1',
    position: { x: 360, y: 180 },
    data: { label: 'Prompt Template', detail: 'System + variables' },
  },
  {
    id: 'model-1',
    position: { x: 660, y: 180 },
    data: { label: 'LLM Call', detail: 'model=gpt-4.1 / temp=0.2' },
  },
  {
    id: 'output-1',
    type: 'output',
    position: { x: 960, y: 180 },
    data: { label: 'Final Output', detail: 'Answer + confidence' },
  },
]

const initialEdges: Array<Edge> = [
  { id: 'e-input-prompt', source: 'input-1', target: 'prompt-1', animated: true },
  { id: 'e-prompt-model', source: 'prompt-1', target: 'model-1' },
  { id: 'e-model-output', source: 'model-1', target: 'output-1' },
]

function createNode(
  type: 'default' | 'input' | 'output',
  suffix: number,
  positionY: number,
): Node<LlmNodeData> {
  const key = `${type}-${suffix}`
  return {
    id: key,
    type,
    position: { x: 120 + suffix * 120, y: positionY },
    data: {
      label: type === 'default' ? `Transform ${suffix}` : `${type.toUpperCase()} ${suffix}`,
      detail: 'Edit node payload in workflow JSON',
    },
  }
}

export default function LlmNodeDesigner() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<LlmNodeData>>(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance<Node<LlmNodeData>, Edge> | null>(null)
  const [jsonDraft, setJsonDraft] = useState('')
  const [statusMessage, setStatusMessage] = useState('Ready')

  const nodeStats = useMemo(() => {
    const inputs = nodes.filter((node) => node.type === 'input').length
    const outputs = nodes.filter((node) => node.type === 'output').length
    return { total: nodes.length, edges: edges.length, inputs, outputs }
  }, [edges.length, nodes])

  const onConnect = useCallback((connection: Connection) => {
    setEdges((currentEdges) => addEdge({ ...connection, animated: true }, currentEdges))
  }, [setEdges])

  const appendNode = useCallback((type: 'default' | 'input' | 'output') => {
    setNodes((current) => {
      const next = createNode(type, current.length + 1, 120 + (current.length % 6) * 72)
      return [...current, next]
    })
  }, [setNodes])

  const onExportJson = useCallback(() => {
    const payload: ReactFlowJsonObject<Node<LlmNodeData>, Edge> = flowInstance?.toObject() ?? {
      nodes,
      edges,
      viewport: { x: 0, y: 0, zoom: 1 },
    }
    setJsonDraft(JSON.stringify(payload, null, 2))
    setStatusMessage(`Exported ${payload.nodes.length} nodes / ${payload.edges.length} edges`)
  }, [edges, flowInstance, nodes])

  const onImportJson = useCallback(() => {
    try {
      const parsed = JSON.parse(jsonDraft) as Partial<ReactFlowJsonObject<Node<LlmNodeData>, Edge>>
      if (!Array.isArray(parsed.nodes) || !Array.isArray(parsed.edges)) {
        throw new Error('JSON must include nodes[] and edges[]')
      }

      setNodes(parsed.nodes)
      setEdges(parsed.edges)

      const viewport = parsed.viewport
      if (flowInstance && viewport) {
        flowInstance.setViewport(viewport, { duration: 200 })
      }
      setStatusMessage(`Imported ${parsed.nodes.length} nodes / ${parsed.edges.length} edges`)
    } catch (error) {
      setStatusMessage(`Import failed: ${error instanceof Error ? error.message : 'invalid JSON'}`)
    }
  }, [flowInstance, jsonDraft, setEdges, setNodes])

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>LLM Node Designer</h2>
        <span className="chip">React Flow Draft</span>
      </div>

      <div className="inline-actions" style={{ marginBottom: 10 }}>
        <button onClick={() => appendNode('input')}>Add Input</button>
        <button onClick={() => appendNode('default')}>Add Transform</button>
        <button onClick={() => appendNode('output')}>Add Output</button>
        <button onClick={onExportJson}>Export JSON</button>
        <button onClick={onImportJson}>Import JSON</button>
      </div>

      <p className="status-line">
        {statusMessage} | Nodes: {nodeStats.total} (in:{nodeStats.inputs} out:{nodeStats.outputs}) | Edges: {nodeStats.edges}
      </p>

      <div
        style={{
          width: '100%',
          height: 560,
          borderRadius: 14,
          border: '1px solid rgba(120, 143, 183, 0.36)',
          overflow: 'hidden',
          background: 'rgba(255, 255, 255, 0.55)',
        }}
      >
        <ReactFlow<Node<LlmNodeData>, Edge>
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onInit={setFlowInstance}
          fitView
        >
          <MiniMap pannable zoomable />
          <Controls showInteractive={false} />
          <Background gap={16} />
          <Panel position="top-right">
            <span className="status-line">Drag from handle to create edges</span>
          </Panel>
        </ReactFlow>
      </div>

      <label style={{ display: 'grid', gap: 8, marginTop: 12 }}>
        <span className="status-line">Workflow JSON</span>
        <textarea
          rows={16}
          value={jsonDraft}
          onChange={(event) => setJsonDraft(event.target.value)}
          placeholder="Paste React Flow JSON here for import, or click Export JSON to generate."
          style={{
            width: '100%',
            resize: 'vertical',
            borderRadius: 12,
            border: '1px solid rgba(120, 143, 183, 0.36)',
            background: 'rgba(255, 255, 255, 0.64)',
            padding: 10,
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            fontSize: 12,
            lineHeight: 1.5,
          }}
        />
      </label>
    </section>
  )
}

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import type { NodeSchema } from './nodeSchemaRegistry'
import type { BackendTaskSpec } from './backendTaskCatalog'

type NodeInfoTemplate = {
  key: string
  label: string
  description?: string
}

type ResizeDirection =
  | 'top'
  | 'right'
  | 'bottom'
  | 'left'
  | 'top-left'
  | 'top-right'
  | 'bottom-left'
  | 'bottom-right'

type NodeInfoCardResizePayload = {
  x: number
  y: number
  width: number
  height: number
}

type TabKey = 'overview' | 'params' | 'io' | 'advanced'

type NodeIOItem = {
  name: string
  valueType: 'string' | 'number' | 'boolean' | 'json' | 'array'
  source: 'input' | 'context' | 'node_output' | 'constant' | 'expression'
  fromNode: string
  fromKey: string
  expr: string
  defaultValue: string
  required: boolean
}

type AvailableNodeOutput = {
  nodeId: string
  nodeLabel?: string
  outputKeys: string[]
}

type NodeInfoCardProps = {
  open: boolean
  x: number
  y: number
  width: number
  height: number
  onMove: (x: number, y: number) => void
  onResize: (payload: NodeInfoCardResizePayload) => void
  onClose: () => void
  nodeId: string
  nodeType: string
  templates: NodeInfoTemplate[]
  draft: string
  apply: (templateKey: string) => void
  save: () => void
  onDraftChange?: (nextDraft: string) => void
  availableNodeOutputs?: AvailableNodeOutput[]
  availableVariables?: string[]
  schema?: NodeSchema | null
  backendTasks?: BackendTaskSpec[]
  minWidth?: number
  minHeight?: number
}

type DragState = {
  active: boolean
  startX: number
  startY: number
  originX: number
  originY: number
}

type ResizeState = {
  active: boolean
  startX: number
  startY: number
  originX: number
  originY: number
  originWidth: number
  originHeight: number
  direction: ResizeDirection | null
}

type DraftMutator = (
  base: Record<string, unknown>,
  inputs: NodeIOItem[],
  outputs: NodeIOItem[],
) => void

const RESIZE_HANDLE_STYLE: CSSProperties = {
  position: 'absolute',
  zIndex: 2,
  userSelect: 'none',
}

const RESIZE_HANDLE_STYLES: Record<ResizeDirection, CSSProperties> = {
  top: { ...RESIZE_HANDLE_STYLE, top: -4, left: 10, right: 10, height: 8, cursor: 'ns-resize' },
  right: { ...RESIZE_HANDLE_STYLE, top: 10, bottom: 10, right: -4, width: 8, cursor: 'ew-resize' },
  bottom: { ...RESIZE_HANDLE_STYLE, bottom: -4, left: 10, right: 10, height: 8, cursor: 'ns-resize' },
  left: { ...RESIZE_HANDLE_STYLE, top: 10, bottom: 10, left: -4, width: 8, cursor: 'ew-resize' },
  'top-left': { ...RESIZE_HANDLE_STYLE, top: -5, left: -5, width: 12, height: 12, cursor: 'nwse-resize' },
  'top-right': { ...RESIZE_HANDLE_STYLE, top: -5, right: -5, width: 12, height: 12, cursor: 'nesw-resize' },
  'bottom-left': { ...RESIZE_HANDLE_STYLE, bottom: -5, left: -5, width: 12, height: 12, cursor: 'nesw-resize' },
  'bottom-right': { ...RESIZE_HANDLE_STYLE, bottom: -5, right: -5, width: 12, height: 12, cursor: 'nwse-resize' },
}

const RESIZE_DIRECTIONS: ResizeDirection[] = ['top', 'right', 'bottom', 'left', 'top-left', 'top-right', 'bottom-left', 'bottom-right']
const TYPE_OPTIONS: NodeIOItem['valueType'][] = ['string', 'number', 'boolean', 'json', 'array']
const SOURCE_OPTIONS: NodeIOItem['source'][] = ['input', 'context', 'node_output', 'constant', 'expression']
const TAB_ITEMS: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: 'Overview' },
  { key: 'params', label: 'Params' },
  { key: 'io', label: 'IO' },
  { key: 'advanced', label: 'Advanced' },
]

function clamp(value: number, min: number): number {
  return Number.isFinite(value) ? Math.max(min, value) : min
}

function safeObjectParse(text: string): Record<string, unknown> {
  const parsed = JSON.parse(text) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Draft JSON must be an object')
  return parsed as Record<string, unknown>
}

function toIOList(raw: unknown): NodeIOItem[] {
  if (!Array.isArray(raw)) return []
  return raw.map((item) => {
    const row = (item && typeof item === 'object' && !Array.isArray(item) ? item : {}) as Record<string, unknown>
    const type = String(row.value_type || row.type || 'string') as NodeIOItem['valueType']
    const source = String(row.source || 'input') as NodeIOItem['source']
    return {
      name: String(row.name || row.key || ''),
      valueType: TYPE_OPTIONS.includes(type) ? type : 'string',
      source: SOURCE_OPTIONS.includes(source) ? source : 'input',
      fromNode: String(row.from_node || ''),
      fromKey: String(row.from_key || ''),
      expr: String(row.expr || ''),
      defaultValue: row.default_value == null ? '' : String(row.default_value),
      required: Boolean(row.required),
    }
  })
}

function fromIOList(items: NodeIOItem[], withSource: boolean): Array<Record<string, unknown>> {
  return items
    .filter((item) => item.name.trim())
    .map((item) => {
      const next: Record<string, unknown> = {
        name: item.name.trim(),
        value_type: item.valueType,
        required: item.required,
      }
      if (withSource) next.source = item.source
      if (withSource && item.source === 'node_output') {
        if (item.fromNode.trim()) next.from_node = item.fromNode.trim()
        if (item.fromKey.trim()) next.from_key = item.fromKey.trim()
      }
      if (withSource && item.source === 'expression' && item.expr.trim()) next.expr = item.expr.trim()
      if (item.defaultValue.trim()) next.default_value = item.defaultValue.trim()
      return next
    })
}

export default function NodeInfoCard({
  open,
  x,
  y,
  width,
  height,
  onMove,
  onResize,
  onClose,
  nodeId,
  nodeType,
  templates,
  draft,
  apply,
  save,
  onDraftChange,
  availableNodeOutputs = [],
  availableVariables = [],
  schema = null,
  backendTasks = [],
  minWidth = 300,
  minHeight = 220,
}: NodeInfoCardProps) {
  const [selectedTemplateKey, setSelectedTemplateKey] = useState<string>('')
  const [draftError, setDraftError] = useState('')
  const [activeTab, setActiveTab] = useState<TabKey>('overview')
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({})

  const dragRef = useRef<DragState>({ active: false, startX: 0, startY: 0, originX: 0, originY: 0 })
  const resizeRef = useRef<ResizeState>({
    active: false,
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0,
    originWidth: 0,
    originHeight: 0,
    direction: null,
  })

  const activeTemplateKey = useMemo(() => {
    if (selectedTemplateKey && templates.some((item) => item.key === selectedTemplateKey)) return selectedTemplateKey
    return templates[0]?.key || ''
  }, [selectedTemplateKey, templates])

  const parsedDraft = useMemo(() => {
    try {
      return safeObjectParse(draft)
    } catch {
      return null
    }
  }, [draft])

  const inputVars = useMemo(() => toIOList(parsedDraft?.input_vars || parsedDraft?.inputs), [parsedDraft])
  const outputVars = useMemo(() => toIOList(parsedDraft?.output_vars || parsedDraft?.outputs), [parsedDraft])
  const nodeOutputMap = useMemo(() => {
    return new Map(availableNodeOutputs.map((item) => [item.nodeId, item]))
  }, [availableNodeOutputs])
  const selectedBackendTaskKey = String(parsedDraft?.backend_task_key || '')
  const selectedBackendTask = useMemo(
    () => backendTasks.find((item) => item.taskKey === selectedBackendTaskKey) || null,
    [backendTasks, selectedBackendTaskKey],
  )

  const toggleSection = useCallback((key: string) => {
    setCollapsedSections((prev) => ({ ...prev, [key]: !prev[key] }))
  }, [])

  const mutateDraft = useCallback((mutator: DraftMutator) => {
    try {
      const base = parsedDraft ? { ...parsedDraft } : {}
      const inputs = [...inputVars]
      const outputs = [...outputVars]
      mutator(base, inputs, outputs)
      const next: Record<string, unknown> = {
        ...base,
        input_vars: fromIOList(inputs, true),
        output_vars: fromIOList(outputs, false),
      }
      setDraftError('')
      onDraftChange?.(JSON.stringify(next, null, 2))
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : 'Draft update failed')
    }
  }, [inputVars, onDraftChange, outputVars, parsedDraft])

  const setScalarField = useCallback((key: string, raw: string | boolean) => {
    mutateDraft((base) => {
      if (!key.trim()) return
      const current = base[key]
      if (typeof raw === 'boolean') {
        base[key] = raw
        return
      }
      const text = raw.trim()
      if (!text) {
        delete base[key]
        return
      }
      if (typeof current === 'number') {
        const parsed = Number(text)
        base[key] = Number.isFinite(parsed) ? parsed : text
        return
      }
      if (text === 'true' || text === 'false') {
        base[key] = text === 'true'
        return
      }
      const parsed = Number(text)
      base[key] = Number.isFinite(parsed) && /^-?\d+(\.\d+)?$/.test(text) ? parsed : text
    })
  }, [mutateDraft])

  const syncBackendTaskIO = useCallback((taskKey: string) => {
    const task = backendTasks.find((item) => item.taskKey === taskKey)
    if (!task) return
    mutateDraft((base, inputs, outputs) => {
      base.backend_task_key = task.taskKey
      base.backend_task_name = task.label
      base.module_type = 'task_module'
      base.module_group = task.moduleGroup
      base.module_key = task.taskKey
      base.node_type = task.suggestedNodeType

      inputs.splice(
        0,
        inputs.length,
        ...task.inputs.map((field) => ({
          name: field.name,
          valueType: field.valueType,
          source: 'input' as NodeIOItem['source'],
          fromNode: '',
          fromKey: '',
          expr: '',
          defaultValue: field.defaultValue || '',
          required: field.required,
        })),
      )

      outputs.splice(
        0,
        outputs.length,
        ...task.outputs.map((field) => ({
          name: field.name,
          valueType: field.valueType,
          source: 'constant' as NodeIOItem['source'],
          fromNode: '',
          fromKey: '',
          expr: '',
          defaultValue: field.defaultValue || '',
          required: field.required,
        })),
      )
    })
  }, [backendTasks, mutateDraft])

  const upsertInputRow = useCallback((index: number, next: NodeIOItem) => {
    mutateDraft((base, inputs) => {
      void base
      if (!inputs[index]) return
      inputs[index] = next
    })
  }, [mutateDraft])

  const upsertOutputRow = useCallback((index: number, next: NodeIOItem) => {
    mutateDraft((base, inputs, outputs) => {
      void base
      void inputs
      if (!outputs[index]) return
      outputs[index] = next
    })
  }, [mutateDraft])

  const insertInputRow = useCallback((index: number) => {
    mutateDraft((base, inputs) => {
      void base
      inputs.splice(index, 0, {
        name: '',
        valueType: 'string',
        source: 'input',
        fromNode: '',
        fromKey: '',
        expr: '',
        defaultValue: '',
        required: false,
      })
    })
  }, [mutateDraft])

  const insertOutputRow = useCallback((index: number) => {
    mutateDraft((base, inputs, outputs) => {
      void base
      void inputs
      outputs.splice(index, 0, {
        name: '',
        valueType: 'string',
        source: 'constant',
        fromNode: '',
        fromKey: '',
        expr: '',
        defaultValue: '',
        required: false,
      })
    })
  }, [mutateDraft])

  const appendVariableToInput = useCallback((index: number, variable: string, target: 'expr' | 'defaultValue') => {
    if (!variable) return
    mutateDraft((base, inputs) => {
      void base
      const current = inputs[index]
      if (!current) return
      const token = `{{${variable}}}`
      if (target === 'expr') {
        const currentExpr = current.expr || ''
        const nextExpr = currentExpr
          ? `${currentExpr}${currentExpr.endsWith(' ') ? '' : ' '}${token}`
          : `=${token}`
        inputs[index] = { ...current, expr: nextExpr }
        return
      }
      inputs[index] = { ...current, defaultValue: `${current.defaultValue || ''}${token}` }
    })
  }, [mutateDraft])

  const section = useCallback((key: string, title: string, content: ReactNode, action?: ReactNode) => {
    const collapsed = Boolean(collapsedSections[key])
    return (
      <section className="llm-io-section" style={{ marginBottom: 8 }}>
        <div className="llm-io-header" style={{ alignItems: 'center' }}>
          <button
            type="button"
            onClick={() => toggleSection(key)}
            style={{
              border: 'none',
              background: 'transparent',
              fontWeight: 700,
              fontSize: 13,
              padding: 0,
              cursor: 'pointer',
              color: 'inherit',
            }}
          >
            {collapsed ? '▶' : '▼'} {title}
          </button>
          {action}
        </div>
        {collapsed ? null : <div className="llm-io-list">{content}</div>}
      </section>
    )
  }, [collapsedSections, toggleSection])

  useEffect(() => {
    const onMouseMove = (event: MouseEvent) => {
      if (dragRef.current.active) {
        const dx = event.clientX - dragRef.current.startX
        const dy = event.clientY - dragRef.current.startY
        onMove(Math.max(0, dragRef.current.originX + dx), Math.max(0, dragRef.current.originY + dy))
      }
      if (resizeRef.current.active && resizeRef.current.direction) {
        const dx = event.clientX - resizeRef.current.startX
        const dy = event.clientY - resizeRef.current.startY
        const direction = resizeRef.current.direction

        let nextX = resizeRef.current.originX
        let nextY = resizeRef.current.originY
        let nextWidth = resizeRef.current.originWidth
        let nextHeight = resizeRef.current.originHeight

        if (direction.includes('right')) nextWidth = clamp(resizeRef.current.originWidth + dx, minWidth)
        if (direction.includes('left')) {
          nextWidth = clamp(resizeRef.current.originWidth - dx, minWidth)
          nextX = resizeRef.current.originX + (resizeRef.current.originWidth - nextWidth)
        }
        if (direction.includes('bottom')) nextHeight = clamp(resizeRef.current.originHeight + dy, minHeight)
        if (direction.includes('top')) {
          nextHeight = clamp(resizeRef.current.originHeight - dy, minHeight)
          nextY = resizeRef.current.originY + (resizeRef.current.originHeight - nextHeight)
        }
        onResize({ x: Math.max(0, nextX), y: Math.max(0, nextY), width: nextWidth, height: nextHeight })
      }
    }

    const onMouseUp = () => {
      dragRef.current.active = false
      resizeRef.current.active = false
      resizeRef.current.direction = null
    }

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [minHeight, minWidth, onMove, onResize])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
        event.preventDefault()
        save()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose, save])

  if (!open) return null

  const primaryButtonStyle: CSSProperties = {
    background: '#1f6feb',
    color: '#fff',
    border: '1px solid #1f6feb',
  }

  const secondaryButtonStyle: CSSProperties = {
    background: '#fff',
    color: '#24292f',
    border: '1px solid #d0d7de',
  }

  const renderOverviewTab = () => (
    <>
      {section(
        'template',
        'Template',
        templates.length ? (
          <div className="llm-node-template-cards">
            {templates.map((template) => (
              <button
                key={template.key}
                type="button"
                className={`llm-node-template-card ${activeTemplateKey === template.key ? 'is-active' : ''}`}
                onClick={() => setSelectedTemplateKey(template.key)}
                aria-pressed={activeTemplateKey === template.key}
              >
                <strong>{template.label}</strong>
                <span>{template.description || template.key}</span>
              </button>
            ))}
          </div>
        ) : (
          <div className="status-line">No templates available</div>
        ),
      )}

      {section(
        'identity',
        'Node Identity',
        <div className="form-grid cols-2">
          <label>
            <span>node_id</span>
            <input value={nodeId} readOnly />
          </label>
          <label>
            <span>node_type</span>
            <input value={nodeType} readOnly />
          </label>
        </div>,
      )}

      {section(
        'backend',
        'Backend Task Binding',
        <div>
          <div className="llm-io-row">
            <span>backend task</span>
            <select
              value={selectedBackendTaskKey}
              onChange={(e) => {
                const nextKey = e.target.value
                setScalarField('backend_task_key', nextKey)
                const task = backendTasks.find((item) => item.taskKey === nextKey)
                if (task) {
                  setScalarField('backend_task_name', task.label)
                  setScalarField('module_group', task.moduleGroup)
                }
              }}
            >
              <option value="">select task</option>
              {backendTasks.map((task) => (
                <option key={task.taskKey} value={task.taskKey}>
                  {task.label} ({task.taskKey})
                </option>
              ))}
            </select>
          </div>
          {selectedBackendTask ? (
            <>
              <div className="status-line">{selectedBackendTask.description}</div>
              <div className="status-line">inputs: {selectedBackendTask.inputs.map((x) => x.name).join(', ') || '-'}</div>
              <div className="status-line">outputs: {selectedBackendTask.outputs.map((x) => x.name).join(', ') || '-'}</div>
            </>
          ) : null}
        </div>,
        <button
          type="button"
          onClick={() => syncBackendTaskIO(selectedBackendTaskKey)}
          disabled={!selectedBackendTaskKey}
          style={primaryButtonStyle}
        >
          Sync Task IO
        </button>,
      )}
    </>
  )

  const renderParamsTab = () => (
    <>
      {schema?.fields?.length ? section(
        'params',
        'Node Params',
        <>
          {schema.fields.map((field) => {
            const currentValue = parsedDraft?.[field.key]
            if (field.type === 'boolean') {
              return (
                <div className="llm-io-row" key={`field-${field.key}`}>
                  <label className="llm-io-check">
                    <input
                      type="checkbox"
                      checked={Boolean(currentValue)}
                      onChange={(e) => setScalarField(field.key, e.target.checked)}
                    />
                    {field.label}
                  </label>
                </div>
              )
            }
            if (field.type === 'select') {
              return (
                <div className="llm-io-row" key={`field-${field.key}`}>
                  <span>{field.label}</span>
                  <select
                    value={String(currentValue ?? '')}
                    onChange={(e) => setScalarField(field.key, e.target.value)}
                  >
                    <option value="">select</option>
                    {(field.options || []).map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                  </select>
                </div>
              )
            }
            if (field.type === 'textarea') {
              return (
                <div className="llm-io-row" key={`field-${field.key}`}>
                  <span>{field.label}</span>
                  <textarea
                    rows={3}
                    value={String(currentValue ?? '')}
                    placeholder={field.placeholder}
                    onChange={(e) => setScalarField(field.key, e.target.value)}
                  />
                </div>
              )
            }
            return (
              <div className="llm-io-row" key={`field-${field.key}`}>
                <span>{field.label}</span>
                <input
                  value={String(currentValue ?? '')}
                  placeholder={field.placeholder}
                  onChange={(e) => setScalarField(field.key, e.target.value)}
                />
              </div>
            )
          })}
        </>,
      ) : (
        <div className="status-line">No schema fields for this node type</div>
      )}
    </>
  )

  const renderIOTab = () => (
    <>
      {section(
        'inputs',
        'Input Variables',
        <>
          {inputVars.map((item, index) => (
            <div key={`in-${index}`} style={{ border: '1px solid #d0d7de', borderRadius: 8, padding: 8, marginBottom: 8 }}>
              <div className="llm-io-row" style={{ marginBottom: 6 }}>
                <input
                  value={item.name}
                  placeholder="name"
                  onChange={(e) => upsertInputRow(index, { ...item, name: e.target.value })}
                />
                <select
                  value={item.valueType}
                  onChange={(e) => upsertInputRow(index, { ...item, valueType: e.target.value as NodeIOItem['valueType'] })}
                >
                  {TYPE_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
                <select
                  value={item.source}
                  onChange={(e) => upsertInputRow(index, { ...item, source: e.target.value as NodeIOItem['source'] })}
                >
                  {SOURCE_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
              </div>
              {item.source === 'node_output' ? (
                <div className="llm-io-row" style={{ marginBottom: 6 }}>
                  <select
                    value={item.fromNode}
                    onChange={(e) => {
                      const fromNode = e.target.value
                      const nextKeys = nodeOutputMap.get(fromNode)?.outputKeys || []
                      const fromKey = nextKeys.includes(item.fromKey) ? item.fromKey : (nextKeys[0] || '')
                      upsertInputRow(index, { ...item, fromNode, fromKey })
                    }}
                  >
                    <option value="">from node</option>
                    {availableNodeOutputs.map((nodeOutput) => (
                      <option key={nodeOutput.nodeId} value={nodeOutput.nodeId}>
                        {nodeOutput.nodeLabel ? `${nodeOutput.nodeLabel} (${nodeOutput.nodeId})` : nodeOutput.nodeId}
                      </option>
                    ))}
                  </select>
                  <select
                    value={item.fromKey}
                    onChange={(e) => upsertInputRow(index, { ...item, fromKey: e.target.value })}
                  >
                    <option value="">from key</option>
                    {(nodeOutputMap.get(item.fromNode)?.outputKeys || []).map((key) => (
                      <option key={key} value={key}>{key}</option>
                    ))}
                  </select>
                </div>
              ) : null}
              {item.source === 'expression' ? (
                <div className="llm-io-row" style={{ marginBottom: 6 }}>
                  <input
                    value={item.expr}
                    placeholder="={{$input.query}}"
                    onChange={(e) => upsertInputRow(index, { ...item, expr: e.target.value })}
                  />
                  <select
                    value=""
                    onChange={(e) => appendVariableToInput(index, e.target.value, 'expr')}
                  >
                    <option value="">insert variable</option>
                    {availableVariables.map((value) => <option key={value} value={value}>{value}</option>)}
                  </select>
                  <select
                    value=""
                    onChange={(e) => appendVariableToInput(index, e.target.value, 'defaultValue')}
                  >
                    <option value="">insert to default</option>
                    {availableVariables.map((value) => <option key={`default-${value}`} value={value}>{value}</option>)}
                  </select>
                </div>
              ) : null}
              <div className="llm-io-row" style={{ marginBottom: 4 }}>
                <input
                  value={item.defaultValue}
                  placeholder="default"
                  onChange={(e) => upsertInputRow(index, { ...item, defaultValue: e.target.value })}
                />
                <label className="llm-io-check">
                  <input
                    type="checkbox"
                    checked={item.required}
                    onChange={(e) => upsertInputRow(index, { ...item, required: e.target.checked })}
                  />
                  required
                </label>
              </div>
              <div className="inline-actions">
                <button type="button" style={secondaryButtonStyle} onClick={() => insertInputRow(index)}>+ Above</button>
                <button type="button" style={secondaryButtonStyle} onClick={() => insertInputRow(index + 1)}>+ Below</button>
                <button
                  type="button"
                  style={secondaryButtonStyle}
                  onClick={() => mutateDraft((base, inputs) => {
                    void base
                    inputs.splice(index, 1)
                  })}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
          {!inputVars.length ? <div className="status-line">No input vars</div> : null}
        </>,
        <button type="button" style={secondaryButtonStyle} onClick={() => insertInputRow(inputVars.length)}>+ Input</button>,
      )}

      {section(
        'outputs',
        'Output Variables',
        <>
          {outputVars.map((item, index) => (
            <div key={`out-${index}`} style={{ border: '1px solid #d0d7de', borderRadius: 8, padding: 8, marginBottom: 8 }}>
              <div className="llm-io-row" style={{ marginBottom: 6 }}>
                <input
                  value={item.name}
                  placeholder="name"
                  onChange={(e) => upsertOutputRow(index, { ...item, name: e.target.value })}
                />
                <select
                  value={item.valueType}
                  onChange={(e) => upsertOutputRow(index, { ...item, valueType: e.target.value as NodeIOItem['valueType'] })}
                >
                  {TYPE_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
                <input
                  value={item.defaultValue}
                  placeholder="default"
                  onChange={(e) => upsertOutputRow(index, { ...item, defaultValue: e.target.value })}
                />
              </div>
              <div className="llm-io-row" style={{ marginBottom: 4 }}>
                <label className="llm-io-check">
                  <input
                    type="checkbox"
                    checked={item.required}
                    onChange={(e) => upsertOutputRow(index, { ...item, required: e.target.checked })}
                  />
                  required
                </label>
              </div>
              <div className="inline-actions">
                <button type="button" style={secondaryButtonStyle} onClick={() => insertOutputRow(index)}>+ Above</button>
                <button type="button" style={secondaryButtonStyle} onClick={() => insertOutputRow(index + 1)}>+ Below</button>
                <button
                  type="button"
                  style={secondaryButtonStyle}
                  onClick={() => mutateDraft((base, inputs, outputs) => {
                    void base
                    void inputs
                    outputs.splice(index, 1)
                  })}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
          {!outputVars.length ? <div className="status-line">No output vars</div> : null}
        </>,
        <button type="button" style={secondaryButtonStyle} onClick={() => insertOutputRow(outputVars.length)}>+ Output</button>,
      )}
    </>
  )

  const renderAdvancedTab = () => (
    <>
      {section(
        'json',
        'Advanced JSON',
        <label style={{ display: 'grid', gap: 6 }}>
          <span>raw draft</span>
          <textarea
            rows={12}
            value={draft}
            onChange={(event) => onDraftChange?.(event.target.value)}
            placeholder="Edit full node info JSON"
            style={{ minHeight: 180 }}
          />
        </label>,
      )}
      {draftError ? <span className="status-line" style={{ color: '#b42318' }}>{draftError}</span> : null}
    </>
  )

  return (
    <aside
      className="llm-node-card panel"
      style={{ left: `${x}px`, top: `${y}px`, width: `${width}px`, height: `${height}px` }}
    >
      <div
        className="llm-node-card__drag"
        onMouseDown={(event) => {
          event.preventDefault()
          dragRef.current.active = true
          dragRef.current.startX = event.clientX
          dragRef.current.startY = event.clientY
          dragRef.current.originX = x
          dragRef.current.originY = y
        }}
      >
        <span>Node Info</span>
        <span className="chip">{nodeId}</span>
      </div>

      <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <div className="inline-actions">
          {TAB_ITEMS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              aria-pressed={activeTab === tab.key}
              style={activeTab === tab.key ? primaryButtonStyle : secondaryButtonStyle}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="inline-actions" style={{ justifyContent: 'flex-end' }}>
          <button type="button" style={secondaryButtonStyle} onClick={() => apply(activeTemplateKey)} disabled={!activeTemplateKey}>
            Apply Template
          </button>
          <button type="button" style={secondaryButtonStyle} onClick={onClose}>Close</button>
          <button type="button" style={primaryButtonStyle} onClick={save}>Save Node</button>
        </div>
      </div>

      <div className="llm-node-card__body" style={{ display: 'grid', gap: 10, height: 'calc(100% - 104px)', overflow: 'auto', alignContent: 'start' }}>
        {activeTab === 'overview' ? renderOverviewTab() : null}
        {activeTab === 'params' ? renderParamsTab() : null}
        {activeTab === 'io' ? renderIOTab() : null}
        {activeTab === 'advanced' ? renderAdvancedTab() : null}
      </div>

      {RESIZE_DIRECTIONS.map((direction) => (
        <div
          key={direction}
          role="presentation"
          style={RESIZE_HANDLE_STYLES[direction]}
          onMouseDown={(event) => {
            event.preventDefault()
            event.stopPropagation()
            resizeRef.current.active = true
            resizeRef.current.startX = event.clientX
            resizeRef.current.startY = event.clientY
            resizeRef.current.originX = x
            resizeRef.current.originY = y
            resizeRef.current.originWidth = width
            resizeRef.current.originHeight = height
            resizeRef.current.direction = direction
          }}
        />
      ))}
    </aside>
  )
}

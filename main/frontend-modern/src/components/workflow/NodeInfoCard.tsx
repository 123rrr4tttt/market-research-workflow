import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import type { NodeSchema } from './nodeSchemaRegistry'

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
  minWidth = 300,
  minHeight = 220,
}: NodeInfoCardProps) {
  const [selectedTemplateKey, setSelectedTemplateKey] = useState<string>('')
  const [draftError, setDraftError] = useState('')

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

      <div className="inline-actions" style={{ justifyContent: 'flex-end', marginBottom: 8 }}>
        <button type="button" onClick={() => apply(activeTemplateKey)} disabled={!activeTemplateKey}>Apply Template</button>
        <button type="button" onClick={save}>Save Node</button>
        <button type="button" onClick={onClose}>Close</button>
      </div>

      <div className="llm-node-card__body" style={{ display: 'grid', gap: 10, height: 'calc(100% - 104px)' }}>
        <div className="llm-node-template-cards">
          {templates.length ? templates.map((template) => (
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
          )) : <div className="status-line">No templates available</div>}
        </div>

        <div className="form-grid cols-2">
          <label>
            <span>node_id</span>
            <input value={nodeId} readOnly />
          </label>
          <label>
            <span>node_type</span>
            <input value={nodeType} readOnly />
          </label>
        </div>

        {schema?.fields?.length ? (
          <div className="llm-io-section">
            <div className="llm-io-header">
              <strong>Node Params</strong>
            </div>
            <div className="llm-io-list">
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
            </div>
          </div>
        ) : null}

        <div className="llm-io-section">
          <div className="llm-io-header">
            <strong>Input Variables</strong>
            <button type="button" onClick={() => mutateDraft((base, inputs) => { void base; inputs.push({ name: '', valueType: 'string', source: 'input', fromNode: '', fromKey: '', expr: '', defaultValue: '', required: false }) })}>+ Input</button>
          </div>
          <div className="llm-io-list">
            {inputVars.map((item, index) => (
              <div className="llm-io-row" key={`in-${index}`}>
                <input value={item.name} placeholder="name" onChange={(e) => mutateDraft((base, inputs) => { void base; inputs[index] = { ...inputs[index], name: e.target.value } })} />
                <select value={item.valueType} onChange={(e) => mutateDraft((base, inputs) => { void base; inputs[index] = { ...inputs[index], valueType: e.target.value as NodeIOItem['valueType'] } })}>
                  {TYPE_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
                <select value={item.source} onChange={(e) => mutateDraft((base, inputs) => { void base; inputs[index] = { ...inputs[index], source: e.target.value as NodeIOItem['source'] } })}>
                  {SOURCE_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
                {item.source === 'node_output' ? (
                  <>
                    <select
                      value={item.fromNode}
                      onChange={(e) => mutateDraft((base, inputs) => {
                        void base
                        const fromNode = e.target.value
                        const nextKeys = nodeOutputMap.get(fromNode)?.outputKeys || []
                        const fromKey = nextKeys.includes(inputs[index]?.fromKey || '')
                          ? (inputs[index]?.fromKey || '')
                          : (nextKeys[0] || '')
                        inputs[index] = { ...inputs[index], fromNode, fromKey }
                      })}
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
                      onChange={(e) => mutateDraft((base, inputs) => {
                        void base
                        inputs[index] = { ...inputs[index], fromKey: e.target.value }
                      })}
                    >
                      <option value="">from key</option>
                      {(nodeOutputMap.get(item.fromNode)?.outputKeys || []).map((key) => (
                        <option key={key} value={key}>{key}</option>
                      ))}
                    </select>
                  </>
                ) : null}
                {item.source === 'expression' ? (
                  <>
                    <input
                      value={item.expr}
                      placeholder="={{$input.query}}"
                      onChange={(e) => mutateDraft((base, inputs) => {
                        void base
                        inputs[index] = { ...inputs[index], expr: e.target.value }
                      })}
                    />
                    <select
                      value=""
                      onChange={(e) => mutateDraft((base, inputs) => {
                        void base
                        const token = e.target.value
                        if (!token) return
                        const currentExpr = inputs[index]?.expr || ''
                        const nextExpr = currentExpr ? `${currentExpr}${token}` : `={{${token}}}`
                        inputs[index] = { ...inputs[index], expr: nextExpr }
                      })}
                    >
                      <option value="">insert var</option>
                      {availableVariables.map((value) => <option key={value} value={value}>{value}</option>)}
                    </select>
                  </>
                ) : null}
                <input value={item.defaultValue} placeholder="default" onChange={(e) => mutateDraft((base, inputs) => { void base; inputs[index] = { ...inputs[index], defaultValue: e.target.value } })} />
                <label className="llm-io-check"><input type="checkbox" checked={item.required} onChange={(e) => mutateDraft((base, inputs) => { void base; inputs[index] = { ...inputs[index], required: e.target.checked } })} />req</label>
                <button type="button" onClick={() => mutateDraft((base, inputs) => { void base; inputs.splice(index, 1) })}>x</button>
              </div>
            ))}
          </div>
        </div>

        <div className="llm-io-section">
          <div className="llm-io-header">
            <strong>Output Variables</strong>
            <button type="button" onClick={() => mutateDraft((base, inputs, outputs) => { void base; void inputs; outputs.push({ name: '', valueType: 'string', source: 'constant', fromNode: '', fromKey: '', expr: '', defaultValue: '', required: false }) })}>+ Output</button>
          </div>
          <div className="llm-io-list">
            {outputVars.map((item, index) => (
              <div className="llm-io-row" key={`out-${index}`}>
                <input value={item.name} placeholder="name" onChange={(e) => mutateDraft((base, inputs, outputs) => { void base; void inputs; outputs[index] = { ...outputs[index], name: e.target.value } })} />
                <select value={item.valueType} onChange={(e) => mutateDraft((base, inputs, outputs) => { void base; void inputs; outputs[index] = { ...outputs[index], valueType: e.target.value as NodeIOItem['valueType'] } })}>
                  {TYPE_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                </select>
                <input value={item.defaultValue} placeholder="default" onChange={(e) => mutateDraft((base, inputs, outputs) => { void base; void inputs; outputs[index] = { ...outputs[index], defaultValue: e.target.value } })} />
                <label className="llm-io-check"><input type="checkbox" checked={item.required} onChange={(e) => mutateDraft((base, inputs, outputs) => { void base; void inputs; outputs[index] = { ...outputs[index], required: e.target.checked } })} />req</label>
                <button type="button" onClick={() => mutateDraft((base, inputs, outputs) => { void base; void inputs; outputs.splice(index, 1) })}>x</button>
              </div>
            ))}
          </div>
        </div>

        <label style={{ display: 'grid', gap: 6 }}>
          <span>advanced JSON</span>
          <textarea rows={8} value={draft} onChange={(event) => onDraftChange?.(event.target.value)} placeholder="Edit full node info JSON" style={{ minHeight: 140 }} />
        </label>
        {draftError ? <span className="status-line" style={{ color: '#b42318' }}>{draftError}</span> : null}
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

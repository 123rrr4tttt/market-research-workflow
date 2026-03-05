import { useMemo, useState, type CSSProperties } from 'react'

export type NodeTemplatePaletteItem<TData = Record<string, unknown>> = {
  key: string
  label: string
  description?: string
  nodeType?: string
  data: TData
}

export type NodeTemplatePaletteProps<TData = Record<string, unknown>> = {
  templates: Array<NodeTemplatePaletteItem<TData>>
  selectedTemplateKey?: string
  defaultSelectedTemplateKey?: string
  selectedNodeCount?: number
  disabled?: boolean
  title?: string
  addButtonLabel?: string
  applyButtonLabel?: string
  emptyText?: string
  onSelectTemplate?: (template: NodeTemplatePaletteItem<TData>) => void
  onAddTemplate?: (template: NodeTemplatePaletteItem<TData>) => void
  onApplyTemplateToSelected?: (template: NodeTemplatePaletteItem<TData>) => void
}

const panelStyle: CSSProperties = {
  display: 'grid',
  gap: 12,
  padding: 12,
  borderRadius: 14,
  border: '1px solid rgba(120, 143, 183, 0.35)',
  background: 'rgba(255, 255, 255, 0.72)',
}

const actionRowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  flexWrap: 'wrap',
  gap: 8,
}

const actionGroupStyle: CSSProperties = {
  display: 'inline-flex',
  gap: 8,
  alignItems: 'center',
}

const gridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
  gap: 10,
}

const cardBaseStyle: CSSProperties = {
  appearance: 'none',
  textAlign: 'left',
  width: '100%',
  borderRadius: 12,
  border: '1px solid rgba(120, 143, 183, 0.35)',
  background: 'rgba(248, 251, 255, 0.95)',
  padding: '10px 12px',
  display: 'grid',
  gap: 6,
  cursor: 'pointer',
  transition: 'all 160ms ease',
}

const cardActiveStyle: CSSProperties = {
  borderColor: 'rgba(34, 109, 221, 0.95)',
  boxShadow: '0 0 0 2px rgba(34, 109, 221, 0.18)',
  background: 'rgba(233, 242, 255, 0.96)',
}

const cardDisabledStyle: CSSProperties = {
  cursor: 'not-allowed',
  opacity: 0.65,
}

export default function NodeTemplatePalette<TData = Record<string, unknown>>({
  templates,
  selectedTemplateKey,
  defaultSelectedTemplateKey,
  selectedNodeCount = 0,
  disabled = false,
  title = 'Node Templates',
  addButtonLabel = 'Add Template Node',
  applyButtonLabel = 'Apply To Selected Node',
  emptyText = 'No templates available',
  onSelectTemplate,
  onAddTemplate,
  onApplyTemplateToSelected,
}: NodeTemplatePaletteProps<TData>) {
  const [internalSelectedKey, setInternalSelectedKey] = useState<string>(() => {
    if (defaultSelectedTemplateKey) return defaultSelectedTemplateKey
    return templates[0]?.key || ''
  })

  const isControlled = typeof selectedTemplateKey === 'string'
  const activeKey = isControlled ? selectedTemplateKey || '' : (internalSelectedKey || defaultSelectedTemplateKey || templates[0]?.key || '')

  const selectedTemplate = useMemo(() => {
    if (!templates.length) return null
    return templates.find((item) => item.key === activeKey) || templates[0]
  }, [activeKey, templates])

  const onSelect = (template: NodeTemplatePaletteItem<TData>) => {
    if (disabled) return
    if (!isControlled) setInternalSelectedKey(template.key)
    onSelectTemplate?.(template)
  }

  const canAdd = Boolean(onAddTemplate && selectedTemplate && !disabled)
  const canApply = Boolean(onApplyTemplateToSelected && selectedTemplate && !disabled && selectedNodeCount > 0)

  return (
    <section style={panelStyle} aria-label="node-template-palette">
      <div style={actionRowStyle}>
        <strong>{title}</strong>
        <span className="status-line">Selected nodes: {selectedNodeCount}</span>
      </div>

      <div style={gridStyle}>
        {templates.length ? templates.map((template) => {
          const isActive = selectedTemplate?.key === template.key
          return (
            <button
              key={template.key}
              type="button"
              onClick={() => onSelect(template)}
              style={{
                ...cardBaseStyle,
                ...(isActive ? cardActiveStyle : null),
                ...(disabled ? cardDisabledStyle : null),
              }}
              aria-pressed={isActive}
              aria-label={`Select template ${template.label}`}
              disabled={disabled}
            >
              <strong>{template.label}</strong>
              <span className="status-line">{template.key}</span>
              <span className="status-line">{template.description || 'No description'}</span>
            </button>
          )
        }) : <div className="status-line">{emptyText}</div>}
      </div>

      <div style={actionGroupStyle}>
        <button
          type="button"
          onClick={() => selectedTemplate && onAddTemplate?.(selectedTemplate)}
          disabled={!canAdd}
        >
          {addButtonLabel}
        </button>
        <button
          type="button"
          onClick={() => selectedTemplate && onApplyTemplateToSelected?.(selectedTemplate)}
          disabled={!canApply}
        >
          {applyButtonLabel}
        </button>
      </div>
    </section>
  )
}

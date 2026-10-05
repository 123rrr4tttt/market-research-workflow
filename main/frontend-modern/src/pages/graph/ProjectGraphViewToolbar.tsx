import { useId, useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { Filter, GitBranchPlus, ListFilter, LoaderCircle, Plus, Save, SlidersHorizontal, X } from 'lucide-react'
import type { MessageKey } from '../../app/platform/i18n'

type GraphMessageParams = Record<string, number | string>

type ToggleOption = {
  key: string
  label: string
  hidden: boolean
}

type NodeOption = {
  value: string
  label: string
}

type EdgeDraft = {
  sourceType: string
  targetType: string
  relation: string
}

type Props = {
  translate: (key: MessageKey) => string
  formatMessage: (key: MessageKey, params: GraphMessageParams) => string
  mode: 'all' | 'selection'
  selectedCount: number
  onModeChange: (mode: 'all' | 'selection') => void
  onCaptureSelection: () => void
  nodeTypes: ToggleOption[]
  relations: ToggleOption[]
  onToggleNodeType: (type: string, hidden: boolean) => void
  onToggleRelation: (relation: string, hidden: boolean) => void
  viewName: string
  onViewNameChange: (name: string) => void
  saveBusy: boolean
  saveStatus: string
  onSave: () => void
  newNodeType: string
  onNewNodeTypeChange: (type: string) => void
  onAddNode: () => void
  nodeTypeOptions: NodeOption[]
  edgeDraft: EdgeDraft
  onEdgeDraftChange: (draft: EdgeDraft) => void
  onAddEdge: () => void
  relationOptions: NodeOption[]
  typeStatus: string
  advancedOpen: boolean
  onAdvancedToggle: () => void
  legendOpen: boolean
  onLegendToggle: () => void
}

type ToolbarPanel = 'projection' | 'save' | 'node' | 'edge'

function optionToken(value: string, index: number) {
  const token = value.replace(/[^a-zA-Z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  return token || `option-${index + 1}`
}

export function ProjectGraphViewToolbar({
  translate: t,
  formatMessage: tf,
  mode,
  selectedCount,
  onModeChange,
  onCaptureSelection,
  nodeTypes,
  relations,
  onToggleNodeType,
  onToggleRelation,
  viewName,
  onViewNameChange,
  saveBusy,
  saveStatus,
  onSave,
  newNodeType,
  onNewNodeTypeChange,
  onAddNode,
  nodeTypeOptions,
  edgeDraft,
  onEdgeDraftChange,
  onAddEdge,
  relationOptions,
  typeStatus,
  advancedOpen,
  onAdvancedToggle,
  legendOpen,
  onLegendToggle,
}: Props) {
  const [openPanel, setOpenPanel] = useState<ToolbarPanel | null>(null)
  const nodeDatalistId = useId()
  const relationDatalistId = useId()
  const closePanel = () => {
    const closingPanel = openPanel
    setOpenPanel(null)
    if (!closingPanel) return
    window.requestAnimationFrame(() => document.getElementById(`graph-view-${closingPanel}-trigger`)?.focus())
  }
  const togglePanel = (panel: ToolbarPanel) => {
    setOpenPanel((prev) => (prev === panel ? null : panel))
  }
  const popoverProps = (label: string) => ({
    role: 'dialog' as const,
    'aria-label': label,
    onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      closePanel()
    },
  })

  return (
    <div className="gv2-builder-toolbar" role="toolbar" aria-label={t('graphPage.view.toolbar')}>
      <button
        id="graph-view-projection-trigger"
        type="button"
        data-testid="graph-view-projection-toggle"
        aria-expanded={openPanel === 'projection'}
        aria-haspopup="dialog"
        title={t('graphPage.view.projectionToggle')}
        aria-label={t('graphPage.view.projectionToggle')}
        className={openPanel === 'projection' ? 'is-active' : undefined}
        onClick={() => togglePanel('projection')}
      >
        <Filter aria-hidden="true" size={14} />
      </button>
      <button
        id="graph-view-save-trigger"
        type="button"
        data-testid="graph-view-save-toggle"
        aria-expanded={openPanel === 'save'}
        aria-haspopup="dialog"
        title={t('graphPage.view.saveToggle')}
        aria-label={t('graphPage.view.saveToggle')}
        className={openPanel === 'save' ? 'is-active' : undefined}
        onClick={() => togglePanel('save')}
      >
        <Save aria-hidden="true" size={14} />
      </button>
      <button
        id="graph-view-node-trigger"
        type="button"
        data-testid="graph-view-node-toggle"
        aria-expanded={openPanel === 'node'}
        aria-haspopup="dialog"
        title={t('graphPage.view.addNodeType')}
        aria-label={t('graphPage.view.addNodeType')}
        className={openPanel === 'node' ? 'is-active' : undefined}
        onClick={() => togglePanel('node')}
      >
        <Plus aria-hidden="true" size={14} />
      </button>
      <button
        id="graph-view-edge-trigger"
        type="button"
        data-testid="graph-view-edge-toggle"
        aria-expanded={openPanel === 'edge'}
        aria-haspopup="dialog"
        title={t('graphPage.view.addRelationType')}
        aria-label={t('graphPage.view.addRelationType')}
        className={openPanel === 'edge' ? 'is-active' : undefined}
        onClick={() => togglePanel('edge')}
      >
        <GitBranchPlus aria-hidden="true" size={14} />
      </button>
      <button
        type="button"
        data-testid="graph-view-advanced-toggle"
        title={t('graphPage.view.advanced')}
        aria-label={t('graphPage.view.advanced')}
        aria-pressed={advancedOpen}
        className={advancedOpen ? 'is-active' : undefined}
        onClick={onAdvancedToggle}
      >
        <ListFilter aria-hidden="true" size={14} />
      </button>
      <button
        type="button"
        title={t('graphPage.view.legend')}
        aria-label={t('graphPage.view.legend')}
        aria-pressed={legendOpen}
        className={legendOpen ? 'is-active' : undefined}
        onClick={onLegendToggle}
      >
        <SlidersHorizontal aria-hidden="true" size={14} />
      </button>

      {openPanel === 'projection' ? (
        <div className="gv2-builder-popover" {...popoverProps(t('graphPage.view.projectionToggle'))}>
          <div>
            <strong>{t('graphPage.view.projectionToggle')}</strong>
            <button type="button" autoFocus onClick={closePanel} aria-label={t('graphPage.action.close')} title={t('graphPage.action.close')}>
              <X aria-hidden="true" size={13} />
            </button>
          </div>
          <div role="group" aria-label={t('graphPage.view.modeSelection')}>
            <button
              type="button"
              data-testid="graph-view-mode-all"
              aria-pressed={mode === 'all'}
              className={mode === 'all' ? 'is-active' : undefined}
              onClick={() => onModeChange('all')}
            >
              {t('graphPage.view.modeAll')}
            </button>
            <button
              type="button"
              data-testid="graph-view-mode-selection"
              aria-pressed={mode === 'selection'}
              className={mode === 'selection' ? 'is-active' : undefined}
              onClick={() => onModeChange('selection')}
            >
              {t('graphPage.view.modeSelection')}
            </button>
          </div>
          <button type="button" onClick={onCaptureSelection} disabled={!selectedCount} title={tf('graphPage.view.captureSelection', { count: selectedCount })}>
            {tf('graphPage.view.captureSelection', { count: selectedCount })}
          </button>
          <fieldset>
            <legend>{t('graphPage.view.nodeTypes')}</legend>
            {nodeTypes.map((item, index) => (
              <label key={item.key}>
                <input
                  type="checkbox"
                  checked={!item.hidden}
                  data-testid={`graph-view-type-${optionToken(item.key, index)}`}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onToggleNodeType(item.key, !event.target.checked)}
                />
                <span>{item.label}</span>
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>{t('graphPage.view.edgeTypes')}</legend>
            {relations.map((item, index) => (
              <label key={item.key}>
                <input
                  type="checkbox"
                  checked={!item.hidden}
                  data-relation-token={optionToken(item.key, index)}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => onToggleRelation(item.key, !event.target.checked)}
                />
                <span>{item.label}</span>
              </label>
            ))}
          </fieldset>
        </div>
      ) : null}

      {openPanel === 'save' ? (
        <div className="gv2-builder-popover" {...popoverProps(t('graphPage.view.saveToggle'))}>
          <div>
            <strong>{t('graphPage.view.saveToggle')}</strong>
            <button type="button" onClick={closePanel} aria-label={t('graphPage.action.close')} title={t('graphPage.action.close')}>
              <X aria-hidden="true" size={13} />
            </button>
          </div>
          <label>
            {t('graphPage.view.viewName')}
            <input
              data-testid="graph-view-name"
              value={viewName}
              autoFocus
              onChange={(event) => onViewNameChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key !== 'Enter' || saveBusy || !viewName.trim()) return
                event.preventDefault()
                onSave()
              }}
            />
          </label>
          <button type="button" data-testid="graph-view-save" onClick={onSave} disabled={saveBusy || !viewName.trim()}>
            {saveBusy ? <LoaderCircle aria-hidden="true" size={13} /> : null}
            {saveBusy ? t('graphPage.view.saving') : t('graphPage.view.save')}
          </button>
          {saveStatus ? <span role="status">{saveStatus}</span> : null}
        </div>
      ) : null}

      {openPanel === 'node' ? (
        <div className="gv2-builder-popover" {...popoverProps(t('graphPage.view.addNodeType'))}>
          <div>
            <strong>{t('graphPage.view.addNodeType')}</strong>
            <button type="button" onClick={closePanel} aria-label={t('graphPage.action.close')} title={t('graphPage.action.close')}>
              <X aria-hidden="true" size={13} />
            </button>
          </div>
          <label>
            {t('graphPage.field.newNodeType')}
            <input
              autoFocus
              value={newNodeType}
              list={nodeDatalistId}
              onChange={(event) => onNewNodeTypeChange(event.target.value)}
            />
          </label>
          <datalist id={nodeDatalistId}>
            {nodeTypeOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </datalist>
          <button type="button" onClick={onAddNode} disabled={!newNodeType.trim()}>{t('graphPage.view.addNodeType')}</button>
          {typeStatus ? <span role="status">{typeStatus}</span> : null}
        </div>
      ) : null}

      {openPanel === 'edge' ? (
        <div className="gv2-builder-popover" {...popoverProps(t('graphPage.view.addRelationType'))}>
          <div>
            <strong>{t('graphPage.view.addRelationType')}</strong>
            <button type="button" onClick={closePanel} aria-label={t('graphPage.action.close')} title={t('graphPage.action.close')}>
              <X aria-hidden="true" size={13} />
            </button>
          </div>
          <label>
            {t('graphPage.view.sourceType')}
            <select
              autoFocus
              value={edgeDraft.sourceType}
              onChange={(event) => onEdgeDraftChange({ ...edgeDraft, sourceType: event.target.value })}
            >
              <option value="">{t('graphPage.placeholder.selectSource')}</option>
              {nodeTypeOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label>
            {t('graphPage.view.targetType')}
            <select
              value={edgeDraft.targetType}
              onChange={(event) => onEdgeDraftChange({ ...edgeDraft, targetType: event.target.value })}
            >
              <option value="">{t('graphPage.placeholder.selectTarget')}</option>
              {nodeTypeOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label>
            {t('graphPage.field.relation')}
            <input
              value={edgeDraft.relation}
              list={relationDatalistId}
              placeholder={t('graphPage.placeholder.relation')}
              onChange={(event) => onEdgeDraftChange({ ...edgeDraft, relation: event.target.value })}
            />
          </label>
          <datalist id={relationDatalistId}>
            {relationOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </datalist>
          <button type="button" onClick={onAddEdge} disabled={!edgeDraft.sourceType || !edgeDraft.targetType || !edgeDraft.relation.trim()}>{t('graphPage.view.addRelationType')}</button>
          {typeStatus ? <span role="status">{typeStatus}</span> : null}
        </div>
      ) : null}
    </div>
  )
}

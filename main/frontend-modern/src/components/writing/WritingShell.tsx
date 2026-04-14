import type { CSSProperties, ReactNode } from 'react'

export type WritingShellViewMode = 'write' | 'preview' | 'split'

export type WritingShellDocumentSummary = {
  id: string
  title: string
  status: string
  updatedAt: string
  active?: boolean
}

export type WritingShellTemplateSummary = {
  id: string
  label: string
  description: string
}

export type WritingShellInsightSummary = {
  id: string
  title: string
  subtitle: string
  tag: string
}

export type WritingShellActivitySummary = {
  id: string
  label: string
  meta: string
}

export type WritingShellProps = {
  projectKey: string
  title: string
  subtitle: string
  viewMode: WritingShellViewMode
  onViewModeChange: (mode: WritingShellViewMode) => void
  documents: WritingShellDocumentSummary[]
  templates: WritingShellTemplateSummary[]
  insights: WritingShellInsightSummary[]
  activity: WritingShellActivitySummary[]
  onSelectDocument?: (documentId: string) => void
  onSelectTemplate?: (templateId: string) => void
  editorSlot: ReactNode
  previewSlot: ReactNode
  rightSidebarSlot?: ReactNode
}

const shellLayoutStyle = {
  display: 'grid',
  gap: '16px',
  gridTemplateColumns: 'minmax(220px, 260px) minmax(0, 1fr) minmax(260px, 320px)',
  alignItems: 'start',
} satisfies CSSProperties

const stackStyle = {
  display: 'grid',
  gap: '16px',
} satisfies CSSProperties

const splitPaneStyle = {
  display: 'grid',
  gap: '12px',
  gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)',
} satisfies CSSProperties

const inlineMetaStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  gap: '8px',
  alignItems: 'center',
} satisfies CSSProperties

type ListCardProps = {
  title: string
  items: Array<{
    id: string
    title: string
    subtitle: string
    badge?: string
    active?: boolean
  }>
  onSelectItem?: (itemId: string) => void
}

function ListCard({ title, items, onSelectItem }: ListCardProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>{title}</h2>
      </div>
      <div style={stackStyle}>
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className="button-secondary"
            onClick={() => onSelectItem?.(item.id)}
            style={{
              textAlign: 'left',
              justifyContent: 'flex-start',
              padding: '12px 14px',
              borderColor: item.active ? 'var(--accent-strong, #7c3aed)' : undefined,
            }}
          >
            <div style={stackStyle}>
              <div style={inlineMetaStyle}>
                <strong>{item.title}</strong>
                {item.badge ? <span className="chip chip-warn">{item.badge}</span> : null}
              </div>
              <span className="text-muted">{item.subtitle}</span>
            </div>
          </button>
        ))}
        {!items.length ? <div className="empty-cell">暂无内容</div> : null}
      </div>
    </section>
  )
}

export default function WritingShell({
  projectKey,
  title,
  subtitle,
  viewMode,
  onViewModeChange,
  documents,
  templates,
  insights,
  activity,
  onSelectDocument,
  onSelectTemplate,
  editorSlot,
  previewSlot,
  rightSidebarSlot,
}: WritingShellProps) {
  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>{title}</h2>
            <p className="text-muted">{subtitle}</p>
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <span className="chip chip-ok">project: {projectKey}</span>
            <button type="button" className={viewMode === 'write' ? 'button-primary' : 'button-secondary'} onClick={() => onViewModeChange('write')}>
              Write
            </button>
            <button
              type="button"
              className={viewMode === 'preview' ? 'button-primary' : 'button-secondary'}
              onClick={() => onViewModeChange('preview')}
            >
              Preview
            </button>
            <button type="button" className={viewMode === 'split' ? 'button-primary' : 'button-secondary'} onClick={() => onViewModeChange('split')}>
              Split
            </button>
          </div>
        </div>
      </section>

      <div className="writing-shell-grid" style={shellLayoutStyle}>
        <div style={stackStyle}>
          <ListCard
            title="文档"
            items={documents.map((item) => ({
              id: item.id,
              title: item.title,
              subtitle: `${item.status} · ${item.updatedAt}`,
              badge: item.active ? '当前' : undefined,
              active: item.active,
            }))}
            onSelectItem={onSelectDocument}
          />
          <ListCard
            title="模板"
            items={templates.map((item) => ({
              id: item.id,
              title: item.label,
              subtitle: item.description,
            }))}
            onSelectItem={onSelectTemplate}
          />
        </div>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>正文工作区</h2>
              <p className="text-muted">页面壳层已就位，后续由编辑器与预览子任务填充。</p>
            </div>
            <span className="chip chip-warn">{viewMode}</span>
          </div>
          {viewMode === 'write' ? editorSlot : null}
          {viewMode === 'preview' ? previewSlot : null}
          {viewMode === 'split' ? <div className="writing-shell-split" style={splitPaneStyle}>{editorSlot}{previewSlot}</div> : null}
        </section>

        <div className="writing-right-column" style={stackStyle}>
          <ListCard
            title="相关资料"
            items={insights.map((item) => ({
              id: item.id,
              title: item.title,
              subtitle: item.subtitle,
              badge: item.tag,
            }))}
          />
          <ListCard
            title="最近动作"
            items={activity.map((item) => ({
              id: item.id,
              title: item.label,
              subtitle: item.meta,
            }))}
          />
          {rightSidebarSlot}
        </div>
      </div>
    </div>
  )
}

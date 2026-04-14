import { useMemo, useState, type CSSProperties, type DragEvent, type MouseEvent as ReactMouseEvent, type Ref } from 'react'
import type { WritingCitation } from '../../lib/api'
import { readDraggedCard, type WritingDraggedCardPayload } from './dragPayload'

export type CitationBasketProps = {
  citations: WritingCitation[]
  containerRef?: Ref<HTMLElement>
  dockEdge?: 'left' | 'right' | 'top' | 'bottom'
  style?: CSSProperties
  collapsed?: boolean
  dragActive?: boolean
  onMouseDown?: (event: ReactMouseEvent<HTMLElement>) => void
  onToggleCollapsed?: () => void
  onHeaderMouseDown?: (event: ReactMouseEvent<HTMLDivElement>) => void
  onRemoveCitation?: (citationId: number | undefined) => void
  onOpenCitation?: (citation: WritingCitation) => void
  onDropCard?: (payload: WritingDraggedCardPayload) => void
  onDragEnter?: () => void
  onDragLeave?: () => void
}

function citationKey(citation: WritingCitation, index: number) {
  return String(citation.id || `${citation.card_id || 'citation'}-${index}`)
}

function shortText(value?: string | null) {
  if (!value) return '暂无摘录内容'
  return value.replace(/\s+/g, ' ').trim()
}

export default function CitationBasket({
  citations,
  containerRef,
  dockEdge = 'bottom',
  style,
  collapsed = false,
  dragActive = false,
  onMouseDown,
  onToggleCollapsed,
  onHeaderMouseDown,
  onRemoveCitation,
  onOpenCitation,
  onDropCard,
  onDragEnter,
  onDragLeave,
}: CitationBasketProps) {
  const [activeCitationKey, setActiveCitationKey] = useState<string | null>(null)
  const citationEntries = useMemo(
    () =>
      citations.map((citation, index) => ({
        key: citationKey(citation, index),
        citation,
        index,
      })),
    [citations],
  )

  const resolvedActiveCitationKey =
    activeCitationKey && citationEntries.some((item) => item.key === activeCitationKey)
      ? activeCitationKey
      : citationEntries[0]?.key || null
  const handleDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    const payload = readDraggedCard(event.nativeEvent)
    onDragLeave?.()
    if (!payload) return
    onDropCard?.(payload)
  }

  const handleDragOver = (event: DragEvent<HTMLElement>) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
    onDragEnter?.()
  }
  const handleOpenEntry = (citation: WritingCitation, key: string) => {
    setActiveCitationKey(key)
    onOpenCitation?.(citation)
  }

  return (
    <section
      ref={containerRef}
      style={style}
      className={`writing-citation-bar is-docked-${dockEdge}${collapsed ? ' is-collapsed' : ''}${dragActive ? ' is-drag-over' : ''}`}
      onMouseDown={onMouseDown}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onDragEnter={() => onDragEnter?.()}
      onDragLeave={(event) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
        onDragLeave?.()
      }}
    >
      {dragActive ? (
        <div
          className="writing-citation-drop-target"
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onDragEnter={() => onDragEnter?.()}
          onDragLeave={(event) => {
            if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
            onDragLeave?.()
          }}
        >
          <div className="writing-citation-drop-target__glow" />
          <div className="writing-citation-drop-target__label">拖到这里加入引用</div>
        </div>
      ) : null}

      <div className="panel-header writing-citation-bar__header">
        <span className="writing-floating-drag-handle" onMouseDown={onHeaderMouseDown} aria-label="拖动引用带" />
        <strong>引用</strong>
        <div className="writing-citation-bar__meta">
          <span className={`chip ${dragActive ? 'chip-ok' : 'chip-warn'}`}>{dragActive ? 'drop now' : `${citations.length} refs`}</span>
          <button type="button" className="button-secondary" onClick={onToggleCollapsed}>
            {collapsed ? '展开' : '折叠'}
          </button>
        </div>
      </div>

      {!collapsed ? (
        <div className="writing-citation-bar__content">
          <div className="writing-citation-mini-rail" role="list" aria-label="引用迷你卡片">
            {citationEntries.map(({ key, citation, index }) => (
              <article
                key={key}
                role="listitem"
                className={`writing-citation-mini-card${key === resolvedActiveCitationKey ? ' is-active' : ''}`}
              >
                <div
                  role="button"
                  tabIndex={0}
                  className="writing-citation-mini-card__hit"
                  onClick={() => handleOpenEntry(citation, key)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      handleOpenEntry(citation, key)
                    }
                  }}
                >
                  <div className="writing-citation-mini-card__head">
                    <strong>{citation.source_title || citation.card_id || `Reference ${index + 1}`}</strong>
                    <div className="writing-citation-mini-card__actions">
                      <span className="chip">{index + 1}</span>
                      <button
                        type="button"
                        className="button-secondary writing-citation-mini-card__remove"
                        onClick={(event) => {
                          event.stopPropagation()
                          onRemoveCitation?.(citation.id)
                        }}
                      >
                        移除
                      </button>
                    </div>
                  </div>
                  <p>{shortText(citation.quote_text)}</p>
                  <small>{citation.source_uri || citation.position_anchor || 'local-source'}</small>
                </div>
              </article>
            ))}
            {!citationEntries.length ? <div className="empty-cell">暂无引用，拖一张资料卡进来试试。</div> : null}
          </div>
        </div>
      ) : null}
    </section>
  )
}

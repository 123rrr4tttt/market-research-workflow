import type { WritingCitation } from '../../lib/api'

export type CitationBasketProps = {
  citations: WritingCitation[]
  onRemoveCitation?: (citationId: number | undefined) => void
}

export default function CitationBasket({ citations, onRemoveCitation }: CitationBasketProps) {
  return (
    <section className="panel writing-side-panel">
      <div className="panel-header">
        <div>
          <h2>引用篮</h2>
          <p className="text-muted writing-panel-subtitle">把资料卡拖进正文前，先在这里确认引用片段。</p>
        </div>
        <span className="chip chip-ok">{citations.length}</span>
      </div>

      <div className="writing-list">
        {citations.map((citation, index) => (
          <article key={citation.id || `${citation.card_id || 'citation'}-${index}`} className="writing-list-card is-static">
            <div className="writing-list-card__header">
              <strong>{citation.source_title || citation.card_id || `Reference ${index + 1}`}</strong>
              <span className="chip">{citation.position_anchor || 'anchor'}</span>
            </div>
            <p>{citation.quote_text || '暂无摘录内容'}</p>
            <div className="writing-list-card__footer">
              <span className="text-muted">{citation.source_uri || 'local-source'}</span>
              <button type="button" className="button-secondary" onClick={() => onRemoveCitation?.(citation.id)}>
                移除
              </button>
            </div>
          </article>
        ))}
        {!citations.length ? <div className="empty-cell">暂无引用，点击资料卡后可加入这里。</div> : null}
      </div>
    </section>
  )
}

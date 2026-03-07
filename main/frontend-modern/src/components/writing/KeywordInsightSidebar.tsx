import type { WritingKeywordCard, WritingKeywordCardDetail, WritingKeywordCardPreview, WritingSuggestItem } from '../../lib/api'

export type KeywordInsightSidebarProps = {
  cards: WritingKeywordCard[]
  preview?: WritingKeywordCardPreview | null
  detail?: WritingKeywordCardDetail | null
  suggestItems?: WritingSuggestItem[]
  selectionText?: string
  selectedCardId?: string | null
  loading?: boolean
  error?: string | null
  onSelectCard?: (cardId: string) => void
  onAddCitation?: (cardId: string) => void
  onUseSuggestion?: (query: string) => void
}

function scoreLabel(score?: number | null) {
  if (score == null) return 'n/a'
  return score.toFixed(2)
}

export default function KeywordInsightSidebar({
  cards,
  preview,
  detail,
  suggestItems = [],
  selectionText,
  selectedCardId,
  loading = false,
  error,
  onSelectCard,
  onAddCitation,
  onUseSuggestion,
}: KeywordInsightSidebarProps) {
  return (
    <section className="panel writing-side-panel">
      <div className="panel-header">
        <div>
          <h2>相关资料卡</h2>
          <p className="text-muted writing-panel-subtitle">划词后优先展示可引用的资料线索和推荐搜索。</p>
        </div>
        {loading ? <span className="chip chip-warn">loading</span> : <span className="chip chip-ok">{cards.length} cards</span>}
      </div>

      {selectionText ? <p className="text-muted writing-panel-subtitle">当前选区: {selectionText}</p> : null}
      {error ? <p className="status-line">{error}</p> : null}

      {preview ? (
        <article className="writing-preview-card">
          <div className="writing-preview-card__meta">
            <span className="chip chip-warn">{preview.source_type}</span>
            <span className="writing-score">score {scoreLabel(preview.score)}</span>
          </div>
          <strong>{preview.title}</strong>
          <p>{preview.snippet || '暂无摘要'}</p>
          {preview.publisher ? <span className="text-muted">{preview.publisher}</span> : null}
          <div className="writing-list-card__footer">
            <span className="text-muted">{preview.url || 'local-preview'}</span>
            <button type="button" className="button-secondary" onClick={() => onAddCitation?.(preview.card_id)}>
              加入引用
            </button>
          </div>
        </article>
      ) : null}

      {detail ? (
        <article className="writing-preview-card">
          <div className="writing-preview-card__meta">
            <span className="chip">{detail.source_type}</span>
            <span className="writing-score">detail</span>
          </div>
          <strong>{detail.title}</strong>
          {detail.evidence ? <p>{detail.evidence}</p> : null}
          <div className="writing-chip-wrap">
            {detail.publisher ? <span className="chip">{detail.publisher}</span> : null}
            {detail.published_at ? <span className="chip">{detail.published_at}</span> : null}
            <span className="chip">provenance {Object.keys(detail.provenance || {}).length}</span>
            <span className="chip">matches {Object.keys(detail.selection_matches || {}).length}</span>
          </div>
          {detail.url ? (
            <a href={detail.url} target="_blank" rel="noreferrer" className="text-muted">
              打开来源
            </a>
          ) : null}
        </article>
      ) : null}

      <div className="writing-list">
        {cards.map((card) => (
          <button
            key={card.card_id}
            type="button"
            className={`writing-list-card${selectedCardId === card.card_id ? ' is-active' : ''}`}
            onClick={() => onSelectCard?.(card.card_id)}
          >
            <div className="writing-list-card__header">
              <strong>{card.title}</strong>
              <span className="chip chip-warn">{card.source_type}</span>
            </div>
            <p>{card.snippet || card.evidence || '暂无摘要'}</p>
            <div className="writing-list-card__footer">
              <span className="text-muted">{card.publisher || '内部索引'}</span>
              <span className="writing-score">score {scoreLabel(card.score)}</span>
            </div>
            {card.quick_actions.length ? (
              <div className="writing-chip-wrap">
                {card.quick_actions.map((action) => (
                  <span key={`${card.card_id}-${action}`} className="chip">
                    {action}
                  </span>
                ))}
              </div>
            ) : null}
          </button>
        ))}
        {!cards.length && !loading ? <div className="empty-cell">划词后在这里出现资料卡片</div> : null}
      </div>

      {suggestItems.length ? (
        <div className="writing-suggest-block">
          <div className="panel-header">
            <h2>推荐补查</h2>
          </div>
          <div className="writing-chip-wrap">
            {suggestItems.map((item) => (
              <button key={item.id} type="button" className="chip" onClick={() => onUseSuggestion?.(item.label)}>
                {item.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  )
}

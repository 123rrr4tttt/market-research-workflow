import type { DragEvent } from 'react'
import type { WritingKeywordCard, WritingSuggestItem } from '../../lib/api'
import { toDraggedCardPayload, writeDraggedCard } from './dragPayload'

export type KeywordInsightSidebarProps = {
  cards: WritingKeywordCard[]
  suggestItems?: WritingSuggestItem[]
  selectionText?: string
  selectedCardId?: string | null
  loading?: boolean
  error?: string | null
  onSelectCard?: (cardId: string) => void
  onUseSuggestion?: (query: string) => void
  onDragCardStart?: (cardId: string) => void
  onDragCardEnd?: () => void
}

function scoreLabel(score?: number | null) {
  if (score == null) return 'n/a'
  return score.toFixed(2)
}

export default function KeywordInsightSidebar({
  cards,
  suggestItems = [],
  selectionText,
  selectedCardId,
  loading = false,
  error,
  onSelectCard,
  onUseSuggestion,
  onDragCardStart,
  onDragCardEnd,
}: KeywordInsightSidebarProps) {
  const handleDragStart = (event: DragEvent<HTMLButtonElement>, card: WritingKeywordCard) => {
    writeDraggedCard(event.nativeEvent, toDraggedCardPayload(card))
    onDragCardStart?.(card.card_id)
  }

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

      <div className="writing-list">
        {cards.map((card) => (
          <button
            key={card.card_id}
            type="button"
            className={`writing-list-card${selectedCardId === card.card_id ? ' is-active' : ''}`}
            draggable
            onClick={() => onSelectCard?.(card.card_id)}
            onDragStart={(event) => handleDragStart(event, card)}
            onDragEnd={() => onDragCardEnd?.()}
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

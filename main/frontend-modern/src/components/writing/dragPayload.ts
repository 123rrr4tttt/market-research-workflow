import type { WritingKeywordCard, WritingKeywordCardPreview } from '../../lib/api'

export const WRITING_CARD_DRAG_MIME = 'application/x-writing-card'

export type WritingDraggedCardPayload = {
  cardId: string
  title: string
  snippet: string
  url?: string | null
  publisher?: string | null
  sourceType: string
}

export function toDraggedCardPayload(card: WritingKeywordCard | WritingKeywordCardPreview): WritingDraggedCardPayload {
  return {
    cardId: card.card_id,
    title: card.title,
    snippet: card.snippet || '',
    url: card.url || null,
    publisher: card.publisher || null,
    sourceType: card.source_type,
  }
}

export function toDraggedCardPreview(payload: WritingDraggedCardPayload): WritingKeywordCardPreview {
  return {
    card_id: payload.cardId,
    title: payload.title,
    url: payload.url || null,
    publisher: payload.publisher || null,
    snippet: payload.snippet || '',
    score: 0,
    source_type: payload.sourceType as WritingKeywordCardPreview['source_type'],
    quick_actions: [],
  }
}

export function writeDraggedCard(event: DragEvent, payload: WritingDraggedCardPayload) {
  const serialized = JSON.stringify(payload)
  event.dataTransfer?.setData(WRITING_CARD_DRAG_MIME, serialized)
  event.dataTransfer?.setData('text/plain', serialized)
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'copy'
  }
}

export function readDraggedCard(event: DragEvent): WritingDraggedCardPayload | null {
  const raw =
    event.dataTransfer?.getData(WRITING_CARD_DRAG_MIME) ||
    event.dataTransfer?.getData('text/plain') ||
    ''
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<WritingDraggedCardPayload>
    if (!parsed.cardId || !parsed.title) return null
    return {
      cardId: parsed.cardId,
      title: parsed.title,
      snippet: parsed.snippet || '',
      url: parsed.url || null,
      publisher: parsed.publisher || null,
      sourceType: parsed.sourceType || 'document',
    }
  } catch {
    const fallbackCardId = raw.trim()
    if (!fallbackCardId) return null
    return {
      cardId: fallbackCardId,
      title: fallbackCardId,
      snippet: '',
      url: null,
      publisher: null,
      sourceType: 'document',
    }
  }
}

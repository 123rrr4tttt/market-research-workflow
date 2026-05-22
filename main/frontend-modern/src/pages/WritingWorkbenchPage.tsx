import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { hashByMode } from '../app/navigation'
import { isReservedProjectKey } from '../app/kernel/projectKeys'
import AgentWritingAssistantPanel, {
  type WritingAgentPanelMessage,
  type WritingAgentToolAction,
  type WritingAgentWorkbenchTool,
} from '../components/writing/AgentWritingAssistantPanel'
import CitationBasket from '../components/writing/CitationBasket'
import { toDraggedCardPreview, type WritingDraggedCardPayload } from '../components/writing/dragPayload'
import KeywordInsightSidebar from '../components/writing/KeywordInsightSidebar'
import MarkdownEditor, { type MarkdownSelectionState } from '../components/writing/MarkdownEditor'
import WritingInsightCard from '../components/writing/WritingInsightCard'
import MarkdownPreview from '../components/writing/MarkdownPreview'
import TemplateLibraryPanel from '../components/writing/TemplateLibraryPanel'
import { useSelectionLookup } from '../components/writing/useSelectionLookup'
import '../components/writing/writing-workbench.css'
import {
  autosaveWritingDraft,
  createWritingDocument,
  exportWritingMarkdown,
  getWritingCardDetail,
  getWritingDocument,
  getWritingKeywordCards,
  getWritingSuggest,
  listWritingCitations,
  listWritingDocuments,
  listWritingTemplates,
  previewWritingKeywordCard,
  readTypedKnowledgeWritingContextFromDocument,
  runAgentChatTurnStreaming,
  updateWritingDocument,
  upsertWritingCitations,
  validateWritingTemplate,
  withTypedKnowledgeWritingContext,
  writingTypedKnowledgeContextKey,
  type WritingDocument,
  type WritingKeywordCard,
  type WritingKeywordCardPreview,
  type WritingCitation,
  type WritingTemplateValidation,
} from '../lib/api'
import { queryKeys } from '../lib/queryKeys'
import type { AgentEventItem, AgentSessionEventStreamStatus } from '../lib/types'

export type WritingWorkbenchPageProps = {
  projectKey: string
  standalone?: boolean
}

type WritingCanvasViewMode = 'write' | 'preview' | 'split'
type FloatingSize = {
  width: number
  height: number
}
type ViewportSize = {
  width: number
  height: number
}
type InsightCardAnchor = {
  left: number
  top: number
  width: number
  height: number
}
type PinnedInsightCard = {
  cardId: string
  preview: WritingKeywordCardPreview
  anchor: InsightCardAnchor
}
type FloatingDockEdge = 'left' | 'right' | 'top' | 'bottom'
type DockedPosition = {
  edge: FloatingDockEdge
  left: number
  top: number
}
type FloatingWindowKey = 'documents' | 'templates' | 'insights' | 'llm' | 'citations'
type FloatingRect = {
  left: number
  top: number
  width: number
  height: number
}
type FloatingPoint = {
  left: number
  top: number
}
type CitationMutationSource =
  | { kind: 'selected' }
  | { kind: 'pinned'; pinnedCardId: string }
  | { kind: 'external' }

type WritingAgentUpdateLocator = {
  anchorId: string
  anchorText: string
  anchorHeading: string
  anchorLine: number | null
  rangeStart: number | null
  rangeEnd: number | null
  cursorOffset: number | null
  contentHash: string
}

type WritingAgentReviewStatus = 'pending' | 'accepted' | 'rejected'

type WritingAgentUpdate = {
  id: string
  callId: string
  toolName: string
  actor: string
  operation: string
  createdAt: string
  summary: string
  oldVersion: number | null
  newVersion: number | null
  insertedText: string
  insertedTextTruncated: boolean
  replacedText: string
  replacedTextTruncated: boolean
  reviewStatus: WritingAgentReviewStatus
  reviewedAt: string
  sourceRefs: string[]
  provenance: Record<string, unknown>
  locator: WritingAgentUpdateLocator
}

type WritingAgentUpdateAnchor = {
  update: WritingAgentUpdate
  range: { start: number; end: number } | null
  lineStart: number | null
  lineEnd: number | null
  preview: string
}

const EMPTY_MARKDOWN = `## 摘要

在这里直接开始写。
`
const PANEL_MIN_WIDTH = 300
const PANEL_MAX_WIDTH = 520
const PANEL_MIN_HEIGHT = 320
const DESKTOP_FLOATING_BREAKPOINT = 1280
const FLOATING_PANEL_TOP_INSET = 58
const FLOATING_PANEL_MARGIN = 12
const FLOATING_PANEL_MAX_HEIGHT = 520
const WRITING_TOOLBAR_MARGIN = 12
const CITATION_BAR_MARGIN = 10
const CITATION_BAR_HORIZONTAL_WIDTH = 820
const CITATION_BAR_SIDE_WIDTH = 300
const INSIGHT_CARD_MARGIN = 16
const INSIGHT_CARD_MIN_WIDTH = 340
const INSIGHT_CARD_WIDTH = 420
const INSIGHT_CARD_MIN_HEIGHT = 320
const INSIGHT_CARD_HEIGHT = 620
const INSIGHT_CARD_VISIBLE_HEADER = 72
const INSIGHT_CARD_BOTTOM_OVERFLOW = 180
const FLOATING_WINDOW_ORDER: FloatingWindowKey[] = ['documents', 'templates', 'insights', 'llm', 'citations']

function clampValue(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function readViewport(): ViewportSize {
  if (typeof window === 'undefined') {
    return { width: 1440, height: 900 }
  }
  return {
    width: window.innerWidth,
    height: window.innerHeight,
  }
}

function formatUpdatedAt(value?: string | null) {
  if (!value) return 'new'
  return value.replace('T', ' ').slice(0, 16)
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

function asText(value: unknown) {
  return typeof value === 'string' ? value : ''
}

function boundedText(value: string, limit: number) {
  const text = String(value || '').trim()
  if (text.length <= limit) return text
  return `${text.slice(0, limit)}\n...[truncated ${text.length - limit} chars]`
}

function extractWritingAgentChunk(event: AgentEventItem) {
  const eventType = String(event.event_type || '').toLowerCase()
  const payload =
    event.payload && typeof event.payload === 'object'
      ? (event.payload as Record<string, unknown>)
      : {}
  const firstText = (...keys: string[]) => {
    for (const key of keys) {
      const value = payload[key]
      if (typeof value === 'string' && value.length) return value
    }
    return ''
  }
  if (eventType.includes('assistant_delta')) return { mode: 'append' as const, text: firstText('delta', 'text', 'content') }
  if (eventType.includes('assistant_message')) return { mode: 'replace' as const, text: firstText('content', 'text', 'message').trim() }
  if (eventType.includes('final_answer')) return { mode: 'replace' as const, text: firstText('final_answer', 'answer', 'content', 'text').trim() }
  return null
}

function findHeadingBefore(markdown: string, offset: number) {
  const before = String(markdown || '').slice(0, Math.max(0, offset))
  const lines = before.split('\n').reverse()
  const heading = lines.find((line) => /^#{1,6}\s+\S/.test(line.trim()))
  return heading ? heading.replace(/^#{1,6}\s+/, '').trim() : ''
}

function asNumberOrNull(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function asTextList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const out: string[] = []
  for (const item of value) {
    const normalized = String(item || '').trim()
    if (normalized && !out.includes(normalized)) out.push(normalized)
  }
  return out
}

function normalizeAgentUpdate(value: unknown, fallbackIndex: number): WritingAgentUpdate | null {
  if (!isPlainRecord(value)) return null
  const locator = isPlainRecord(value.locator) ? value.locator : {}
  const fallbackId = asText(value.anchor_id) || asText(locator.anchor_id) || `agent-update-${fallbackIndex}`
  return {
    id: asText(value.id) || fallbackId,
    callId: asText(value.call_id),
    toolName: asText(value.tool_name),
    actor: asText(value.actor) || 'agent_core',
    operation: asText(value.operation) || 'append',
    createdAt: asText(value.created_at),
    summary: asText(value.summary),
    oldVersion: asNumberOrNull(value.old_version),
    newVersion: asNumberOrNull(value.new_version),
    insertedText: asText(value.inserted_text),
    insertedTextTruncated: Boolean(value.inserted_text_truncated),
    replacedText: asText(value.replaced_text),
    replacedTextTruncated: Boolean(value.replaced_text_truncated),
    reviewStatus: normalizeAgentReviewStatus(value.review_status),
    reviewedAt: asText(value.reviewed_at),
    sourceRefs: asTextList(value.source_refs),
    provenance: isPlainRecord(value.provenance) ? value.provenance : {},
    locator: {
      anchorId: asText(locator.anchor_id) || fallbackId,
      anchorText: asText(locator.anchor_text),
      anchorHeading: asText(locator.anchor_heading),
      anchorLine: asNumberOrNull(locator.anchor_line),
      rangeStart: asNumberOrNull(locator.range_start),
      rangeEnd: asNumberOrNull(locator.range_end),
      cursorOffset: asNumberOrNull(locator.cursor_offset),
      contentHash: asText(locator.content_hash) || asText(value.content_hash),
    },
  }
}

function readAgentUpdates(metadata: WritingDocument['metadata_json'] | null | undefined): WritingAgentUpdate[] {
  if (!isPlainRecord(metadata)) return []
  const raw = Array.isArray(metadata.agent_updates)
    ? metadata.agent_updates
    : isPlainRecord(metadata.last_agent_update)
      ? [metadata.last_agent_update]
      : []
  return raw
    .map((item, index) => normalizeAgentUpdate(item, index))
    .filter((item): item is WritingAgentUpdate => Boolean(item))
    .reverse()
}

function findAgentUpdateRange(markdown: string, update: WritingAgentUpdate): { start: number; end: number } | null {
  const rangeStart = update.locator.rangeStart
  const insertedText = update.insertedText.trim()
  if (rangeStart != null && rangeStart >= 0 && rangeStart <= markdown.length && insertedText) {
    const insertedEnd = Math.min(markdown.length, rangeStart + insertedText.length)
    if (markdown.slice(rangeStart, insertedEnd) === insertedText) {
      return { start: rangeStart, end: insertedEnd }
    }
  }
  if (
    rangeStart != null &&
    update.locator.rangeEnd != null &&
    rangeStart >= 0 &&
    update.locator.rangeEnd >= rangeStart &&
    update.locator.rangeEnd <= markdown.length
  ) {
    return { start: rangeStart, end: update.locator.rangeEnd }
  }

  const candidates = [
    update.insertedText,
    update.locator.anchorText,
    update.summary,
  ]
    .map((item) => item.trim())
    .filter(Boolean)

  for (const candidate of candidates) {
    const start = markdown.indexOf(candidate)
    if (start >= 0) return { start, end: start + candidate.length }
  }
  return null
}

function previewAgentUpdateText(update: WritingAgentUpdate) {
  return update.insertedText || update.locator.anchorText || update.summary || '暂无可展示的正文片段'
}

function buildAgentUpdateRejectedMarkdown(markdown: string, update: WritingAgentUpdate): string | null {
  const range = findAgentUpdateRange(markdown, update)
  if (!range) return null
  const shouldRestoreText = update.operation === 'replace_range' || update.operation === 'replace_text'
  const replacementText = shouldRestoreText ? update.replacedText : ''
  return `${markdown.slice(0, range.start)}${replacementText}${markdown.slice(range.end)}`.replace(/\n{3,}/g, '\n\n')
}

function buildAgentUpdateAnchors(markdown: string, updates: WritingAgentUpdate[]): WritingAgentUpdateAnchor[] {
  return updates.map((update) => {
    const range = findAgentUpdateRange(markdown, update)
    const lineStart = range ? markdown.slice(0, range.start).split('\n').length : update.locator.anchorLine
    const lineEnd = range ? (lineStart || 1) + Math.max(0, markdown.slice(range.start, range.end).split('\n').length - 1) : update.locator.anchorLine
    return {
      update,
      range,
      lineStart,
      lineEnd,
      preview: previewAgentUpdateText(update),
    }
  })
}

function agentUpdateVersionLabel(update: WritingAgentUpdate) {
  const before = update.oldVersion ? `v${update.oldVersion}` : '原版本'
  const after = update.newVersion ? `v${update.newVersion}` : 'Agent 写回'
  return `${before} -> ${after}`
}

function normalizeAgentReviewStatus(value: unknown): WritingAgentReviewStatus {
  const normalized = asText(value).trim().toLowerCase()
  if (normalized === 'accepted' || normalized === 'rejected') return normalized
  return 'pending'
}

function agentUpdateRawMatches(value: unknown, update: WritingAgentUpdate) {
  if (!isPlainRecord(value)) return false
  const locator = isPlainRecord(value.locator) ? value.locator : {}
  const ids = [
    asText(value.id),
    asText(value.anchor_id),
    asText(value.call_id),
    asText(locator.anchor_id),
  ].filter(Boolean)
  return ids.includes(update.id) || ids.includes(update.callId) || ids.includes(update.locator.anchorId)
}

function withAgentUpdateReviewStatus(
  metadata: WritingDocument['metadata_json'] | null | undefined,
  update: WritingAgentUpdate,
  reviewStatus: WritingAgentReviewStatus,
) {
  const next: Record<string, unknown> = isPlainRecord(metadata) ? { ...metadata } : {}
  const reviewedAt = new Date().toISOString()
  const applyStatus = (value: unknown) => {
    if (!isPlainRecord(value) || !agentUpdateRawMatches(value, update)) return value
    return {
      ...value,
      review_status: reviewStatus,
      reviewed_at: reviewedAt,
    }
  }
  if (Array.isArray(next.agent_updates)) {
    next.agent_updates = next.agent_updates.map(applyStatus)
  }
  if (isPlainRecord(next.last_agent_update)) {
    next.last_agent_update = applyStatus(next.last_agent_update)
  }
  return next
}

function panelButtonClass(active: boolean) {
  return active ? 'button-primary' : 'button-secondary'
}

function resolveInsightCardAnchor(anchor: InsightCardAnchor | null, viewport: ViewportSize): InsightCardAnchor {
  const rawAnchor = anchor || {
    left: Math.max(INSIGHT_CARD_MARGIN, viewport.width - INSIGHT_CARD_WIDTH - INSIGHT_CARD_MARGIN),
    top: 72,
    width: clampValue(
      INSIGHT_CARD_WIDTH,
      INSIGHT_CARD_MIN_WIDTH,
      Math.max(INSIGHT_CARD_MIN_WIDTH, viewport.width - INSIGHT_CARD_MARGIN * 2),
    ),
    height: clampValue(
      INSIGHT_CARD_HEIGHT,
      INSIGHT_CARD_MIN_HEIGHT,
      Math.max(INSIGHT_CARD_MIN_HEIGHT, viewport.height - 48),
    ),
  }
  const width = clampValue(
    rawAnchor.width,
    INSIGHT_CARD_MIN_WIDTH,
    Math.max(INSIGHT_CARD_MIN_WIDTH, viewport.width - INSIGHT_CARD_MARGIN * 2),
  )
  const height = clampValue(
    rawAnchor.height,
    INSIGHT_CARD_MIN_HEIGHT,
    Math.max(INSIGHT_CARD_MIN_HEIGHT, viewport.height + INSIGHT_CARD_BOTTOM_OVERFLOW - INSIGHT_CARD_MARGIN * 2),
  )

  return {
    width,
    height,
    left: clampValue(
      rawAnchor.left,
      INSIGHT_CARD_MARGIN,
      Math.max(INSIGHT_CARD_MARGIN, viewport.width - width - INSIGHT_CARD_MARGIN),
    ),
    top: clampValue(
      rawAnchor.top,
      INSIGHT_CARD_MARGIN,
      Math.max(INSIGHT_CARD_MARGIN, viewport.height - INSIGHT_CARD_VISIBLE_HEADER),
    ),
  }
}

function buildInsightCardStyle(anchor: InsightCardAnchor, zIndex: number) {
  return {
    position: 'fixed' as const,
    left: Math.round(anchor.left),
    top: Math.round(anchor.top),
    width: anchor.width,
    height: anchor.height,
    maxHeight: anchor.height,
    overflow: 'auto' as const,
    zIndex,
  }
}

function resolveDockFromRect(
  rect: { left: number; top: number; width: number; height: number },
  viewport: ViewportSize,
): DockedPosition {
  const distances: Array<{ edge: FloatingDockEdge; distance: number }> = [
    { edge: 'left', distance: Math.abs(rect.left - FLOATING_PANEL_MARGIN) },
    { edge: 'right', distance: Math.abs(viewport.width - FLOATING_PANEL_MARGIN - (rect.left + rect.width)) },
    { edge: 'top', distance: Math.abs(rect.top - FLOATING_PANEL_TOP_INSET) },
    { edge: 'bottom', distance: Math.abs(viewport.height - FLOATING_PANEL_MARGIN - (rect.top + rect.height)) },
  ]
  const nearest = distances.sort((a, b) => a.distance - b.distance)[0]?.edge || 'left'
  const clamped = clampFloatingRect(rect, viewport, FLOATING_PANEL_MARGIN, FLOATING_PANEL_TOP_INSET)
  if (nearest === 'left') {
    return { edge: nearest, left: FLOATING_PANEL_MARGIN, top: clamped.top }
  }
  if (nearest === 'right') {
    return { edge: nearest, left: viewport.width - rect.width - FLOATING_PANEL_MARGIN, top: clamped.top }
  }
  if (nearest === 'top') {
    return { edge: nearest, left: clamped.left, top: FLOATING_PANEL_TOP_INSET }
  }
  return { edge: nearest, left: clamped.left, top: viewport.height - rect.height - FLOATING_PANEL_MARGIN }
}

function clampFloatingRect(
  rect: FloatingRect,
  viewport: ViewportSize,
  margin: number,
  topInset: number,
): FloatingRect {
  return {
    ...rect,
    left: clampValue(rect.left, margin, Math.max(margin, viewport.width - rect.width - margin)),
    top: clampValue(rect.top, topInset, Math.max(topInset, viewport.height - rect.height - margin)),
  }
}

function buildDockedStyle(
  position: DockedPosition,
  viewport: ViewportSize,
  width: number,
  height: number,
): { left: number | string; right: number | string; top: number | string; bottom: number | string; width: number; height: number } {
  const clamped = clampFloatingRect(
    { left: position.left, top: position.top, width, height },
    viewport,
    FLOATING_PANEL_MARGIN,
    FLOATING_PANEL_TOP_INSET,
  )
  if (position.edge === 'left') {
    return { left: FLOATING_PANEL_MARGIN, right: 'auto', top: clamped.top, bottom: 'auto', width, height }
  }
  if (position.edge === 'right') {
    return { left: viewport.width - width - FLOATING_PANEL_MARGIN, right: 'auto', top: clamped.top, bottom: 'auto', width, height }
  }
  if (position.edge === 'top') {
    return { left: clamped.left, right: 'auto', top: FLOATING_PANEL_TOP_INSET, bottom: 'auto', width, height }
  }
  return { left: clamped.left, right: 'auto', top: viewport.height - height - FLOATING_PANEL_MARGIN, bottom: 'auto', width, height }
}

function buildCitationDockedStyle(
  position: DockedPosition,
  viewport: ViewportSize,
): {
  left: number | string
  right: number | string
  top: number | string
  bottom: number | string
  width: number
} {
  const isSide = position.edge === 'left' || position.edge === 'right'
  const width = isSide
    ? Math.min(CITATION_BAR_SIDE_WIDTH, Math.max(240, viewport.width - 24))
    : Math.min(CITATION_BAR_HORIZONTAL_WIDTH, Math.max(320, viewport.width - 28))
  const heightHint = isSide ? 240 : 108
  const clamped = {
    left: clampValue(position.left, CITATION_BAR_MARGIN, Math.max(CITATION_BAR_MARGIN, viewport.width - width - CITATION_BAR_MARGIN)),
    top: clampValue(position.top, FLOATING_PANEL_TOP_INSET, Math.max(FLOATING_PANEL_TOP_INSET, viewport.height - heightHint - CITATION_BAR_MARGIN)),
  }
  if (position.edge === 'left') {
    return { left: CITATION_BAR_MARGIN, right: 'auto', top: clamped.top, bottom: 'auto', width }
  }
  if (position.edge === 'right') {
    return { left: viewport.width - width - CITATION_BAR_MARGIN, right: 'auto', top: clamped.top, bottom: 'auto', width }
  }
  if (position.edge === 'top') {
    return { left: clamped.left, right: 'auto', top: FLOATING_PANEL_TOP_INSET, bottom: 'auto', width }
  }
  return { left: clamped.left, right: 'auto', top: viewport.height - heightHint - CITATION_BAR_MARGIN, bottom: 'auto', width }
}

export default function WritingWorkbenchPage({ projectKey, standalone = false }: WritingWorkbenchPageProps) {
  const queryClient = useQueryClient()
  const canUseWritingProject = Boolean(projectKey && !isReservedProjectKey(projectKey))
  const initialViewport = readViewport()
  const initialPanelHeight = Math.max(PANEL_MIN_HEIGHT, initialViewport.height - 148)
  const initialCenteredSideOffset = Math.max(
    FLOATING_PANEL_TOP_INSET,
    Math.round((initialViewport.height - initialPanelHeight) / 2),
  )
  const [viewMode, setViewMode] = useState<WritingCanvasViewMode>('write')
  const [documentsPanelOpen, setDocumentsPanelOpen] = useState(false)
  const [templatesPanelOpen, setTemplatesPanelOpen] = useState(false)
  const [insightsPanelOpen, setInsightsPanelOpen] = useState(false)
  const [llmPanelOpen, setLlmPanelOpen] = useState(false)
  const [agentUpdatesPanelOpen, setAgentUpdatesPanelOpen] = useState(false)
  const [expandedAgentUpdateId, setExpandedAgentUpdateId] = useState<string | null>(null)
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null)
  const [isCreatingDraft, setIsCreatingDraft] = useState(false)
  const [draftByKey, setDraftByKey] = useState<Record<string, { title: string; markdown: string }>>({})
  const [selectionText, setSelectionText] = useState('')
  const [selectionState, setSelectionState] = useState<MarkdownSelectionState | null>(null)
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null)
  const [pinnedInsightCards, setPinnedInsightCards] = useState<PinnedInsightCard[]>([])
  const [templateValidation, setTemplateValidation] = useState<WritingTemplateValidation | null>(null)
  const [writingAgentDraft, setWritingAgentDraft] = useState('')
  const [writingAgentMessages, setWritingAgentMessages] = useState<WritingAgentPanelMessage[]>([])
  const [writingAgentSessionId, setWritingAgentSessionId] = useState<string | null>(null)
  const [writingAgentStreamStatus, setWritingAgentStreamStatus] = useState<AgentSessionEventStreamStatus>('idle')
  const [writingAgentBusy, setWritingAgentBusy] = useState(false)
  const [citationTrayVisible, setCitationTrayVisible] = useState(true)
  const [citationTrayCollapsed, setCitationTrayCollapsed] = useState(false)
  const [citationTrayDragOver, setCitationTrayDragOver] = useState(false)
  const [autosaveMessage, setAutosaveMessage] = useState('idle')
  const [saveMessage, setSaveMessage] = useState('')
  const [exportMessage, setExportMessage] = useState('')
  const [viewport, setViewport] = useState<ViewportSize>(() => readViewport())
  const [activeFloatingWindow, setActiveFloatingWindow] = useState<FloatingWindowKey>('insights')
  const [documentsPanelSize, setDocumentsPanelSize] = useState<FloatingSize>(() => ({
    width: 360,
    height: initialPanelHeight,
  }))
  const [templatesPanelSize, setTemplatesPanelSize] = useState<FloatingSize>(() => ({
    width: 360,
    height: initialPanelHeight,
  }))
  const [insightsPanelSize, setInsightsPanelSize] = useState<FloatingSize>(() => ({
    width: 360,
    height: initialPanelHeight,
  }))
  const [llmPanelSize, setLlmPanelSize] = useState<FloatingSize>(() => ({
    width: 360,
    height: initialPanelHeight,
  }))
  const [documentsPanelPosition, setDocumentsPanelPosition] = useState<DockedPosition>(() => ({
    edge: 'left',
    left: FLOATING_PANEL_MARGIN,
    top: initialCenteredSideOffset,
  }))
  const [templatesPanelPosition, setTemplatesPanelPosition] = useState<DockedPosition>(() => ({
    edge: 'left',
    left: FLOATING_PANEL_MARGIN + 28,
    top: Math.min(initialViewport.height - initialPanelHeight - FLOATING_PANEL_MARGIN, initialCenteredSideOffset + 72),
  }))
  const [insightsPanelPosition, setInsightsPanelPosition] = useState<DockedPosition>(() => ({
    edge: 'right',
    left: initialViewport.width - 360 - FLOATING_PANEL_MARGIN,
    top: initialCenteredSideOffset,
  }))
  const [llmPanelPosition, setLlmPanelPosition] = useState<DockedPosition>(() => ({
    edge: 'right',
    left: initialViewport.width - 360 - FLOATING_PANEL_MARGIN - 28,
    top: Math.min(initialViewport.height - initialPanelHeight - FLOATING_PANEL_MARGIN, initialCenteredSideOffset + 72),
  }))
  const [citationTrayPosition, setCitationTrayPosition] = useState<DockedPosition>(() => ({
    edge: 'bottom',
    left: Math.max(CITATION_BAR_MARGIN, Math.round((initialViewport.width - Math.min(CITATION_BAR_HORIZONTAL_WIDTH, initialViewport.width - 28)) / 2)),
    top: initialViewport.height - CITATION_BAR_MARGIN - 108,
  }))
  const [documentsPanelDragRect, setDocumentsPanelDragRect] = useState<FloatingRect | null>(null)
  const [templatesPanelDragRect, setTemplatesPanelDragRect] = useState<FloatingRect | null>(null)
  const [insightsPanelDragRect, setInsightsPanelDragRect] = useState<FloatingRect | null>(null)
  const [llmPanelDragRect, setLlmPanelDragRect] = useState<FloatingRect | null>(null)
  const [citationTrayDragRect, setCitationTrayDragRect] = useState<FloatingRect | null>(null)
  const [toolbarPosition, setToolbarPosition] = useState<FloatingPoint | null>(null)
  const [insightCardAnchor, setInsightCardAnchor] = useState<InsightCardAnchor | null>(null)
  const canvasShellRef = useRef<HTMLDivElement | null>(null)
  const toolbarRef = useRef<HTMLDivElement | null>(null)
  const documentsPanelRef = useRef<HTMLElement | null>(null)
  const templatesPanelRef = useRef<HTMLElement | null>(null)
  const insightsPanelRef = useRef<HTMLElement | null>(null)
  const llmPanelRef = useRef<HTMLElement | null>(null)
  const citationTrayRef = useRef<HTMLElement | null>(null)
  const pendingCitationCardIdsRef = useRef<Set<string>>(new Set())
  const dismissInsightCard = useCallback(() => {
    setSelectedCardId(null)
  }, [])

  const documentsQuery = useQuery({
    queryKey: queryKeys.writing.documents(projectKey),
    queryFn: () => listWritingDocuments(),
    enabled: canUseWritingProject,
    refetchInterval: 10000,
    refetchOnWindowFocus: true,
  })
  const effectiveDocumentId = isCreatingDraft ? null : activeDocumentId ?? documentsQuery.data?.[0]?.id ?? null
  const documentDetailQuery = useQuery({
    queryKey: queryKeys.writing.documentDetail(projectKey, effectiveDocumentId),
    queryFn: () => getWritingDocument(effectiveDocumentId as number),
    enabled: canUseWritingProject && effectiveDocumentId != null,
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  })
  const citationsQuery = useQuery({
    queryKey: queryKeys.writing.citations(projectKey, effectiveDocumentId),
    queryFn: () => listWritingCitations(effectiveDocumentId as number),
    enabled: canUseWritingProject && effectiveDocumentId != null,
  })
  const templatesQuery = useQuery({
    queryKey: queryKeys.writing.templates(projectKey),
    queryFn: () => listWritingTemplates(),
  })
  const draftKey = effectiveDocumentId == null ? '__new__' : String(effectiveDocumentId)
  const persistedTitle = documentDetailQuery.data?.title || ''
  const persistedMarkdown = documentDetailQuery.data?.body_md || EMPTY_MARKDOWN
  const currentDraft = draftByKey[draftKey]
  const title = currentDraft?.title ?? persistedTitle
  const markdown = currentDraft?.markdown ?? persistedMarkdown
  const isDirty =
    effectiveDocumentId == null
      ? title.trim().length > 0 || markdown.trim().length > 0
      : title !== persistedTitle || markdown !== persistedMarkdown
  const agentUpdates = useMemo(
    () => readAgentUpdates(documentDetailQuery.data?.metadata_json),
    [documentDetailQuery.data?.metadata_json],
  )
  const agentUpdateAnchors = useMemo(
    () => buildAgentUpdateAnchors(markdown, agentUpdates),
    [agentUpdates, markdown],
  )
  const latestAgentUpdate = agentUpdates[0] || null
  const writingTypedContext = useMemo(
    () => readTypedKnowledgeWritingContextFromDocument(documentDetailQuery.data),
    [documentDetailQuery.data],
  )
  const writingTypedContextKey = useMemo(
    () => writingTypedKnowledgeContextKey(writingTypedContext),
    [writingTypedContext],
  )

  const resetContextPanels = () => {
    dismissInsightCard()
    setPinnedInsightCards([])
    setSelectionText('')
    setSelectionState(null)
    setTemplateValidation(null)
    setAgentUpdatesPanelOpen(false)
    setExpandedAgentUpdateId(null)
  }

  const saveDocumentMutation = useMutation({
    mutationFn: async () => {
      setSaveMessage('')
      if (effectiveDocumentId == null) {
        return createWritingDocument({
          title,
          body_md: markdown,
          metadata_json: { source: 'writing-workbench', project_key: projectKey },
        })
      }
      return updateWritingDocument(
        effectiveDocumentId,
        {
          title,
          body_md: markdown,
          base_version: documentDetailQuery.data?.version,
        },
        {
          ifMatch: documentDetailQuery.data?.etag,
        },
      )
    },
    onSuccess: async (document) => {
      const nextDocumentId = document?.id || effectiveDocumentId
      if (document?.id) {
        setIsCreatingDraft(false)
        setActiveDocumentId(document.id)
      }
      setDraftByKey((prev) => {
        const next = { ...prev }
        delete next[draftKey]
        if (nextDocumentId != null && nextDocumentId !== effectiveDocumentId) {
          delete next[String(nextDocumentId)]
        }
        return next
      })
      setAutosaveMessage('saved')
      setSaveMessage(effectiveDocumentId == null ? '文档已创建' : '正文已保存')
      setExportMessage('')
      await queryClient.invalidateQueries({ queryKey: queryKeys.writing.documents(projectKey) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.writing.documentDetail(projectKey, nextDocumentId) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.writing.citations(projectKey, nextDocumentId) })
    },
    onError: (error) => {
      setSaveMessage(error instanceof Error ? error.message : '保存失败')
    },
  })

  const validateTemplateMutation = useMutation({
    mutationFn: (templateKey: string) =>
      validateWritingTemplate({
        template_key: templateKey,
        template_content: templatesQuery.data?.find((item) => item.template_key === templateKey)?.template_content || '',
        sample_payload: { project_key: projectKey },
      }),
    onSuccess: setTemplateValidation,
  })

  const selectionLookup = useSelectionLookup({
    selectionText,
    enabled: canUseWritingProject && viewMode !== 'preview',
    lookupScopeKey: writingTypedContextKey,
    lookup: async (nextSelection, selectionHash) => {
      const [cardsResult, suggestResult] = await Promise.all([
        getWritingKeywordCards(
          withTypedKnowledgeWritingContext({
            project_key: projectKey,
            query: nextSelection,
            selection_hash: selectionHash,
            sources: ['document', 'resource', 'graph'],
          }, writingTypedContext),
        ),
        getWritingSuggest(nextSelection, { mode: 'material', limit: 6 }),
      ])
      return {
        cards: cardsResult.cards,
        suggestItems: suggestResult.items,
      }
    },
  })

  const visibleCards = useMemo(() => selectionLookup.data?.cards || [], [selectionLookup.data?.cards])
  const citationPreviewByCardId = useMemo(() => {
    const next = new Map<string, WritingKeywordCardPreview>()
    for (const citation of citationsQuery.data || []) {
      if (!citation.card_id || next.has(citation.card_id)) continue
      next.set(citation.card_id, {
        card_id: citation.card_id,
        title: citation.source_title || citation.card_id,
        url: citation.source_uri || null,
        publisher: null,
        snippet: citation.quote_text || '',
        score: 0,
        source_type: citation.source_uri ? 'resource' : 'document',
        quick_actions: [],
      })
    }
    return next
  }, [citationsQuery.data])
  const effectiveSelectedCardId =
    selectedCardId &&
    (visibleCards.some((item) => item.card_id === selectedCardId) ||
      citationPreviewByCardId.has(selectedCardId) ||
      pinnedInsightCards.some((item) => item.cardId === selectedCardId))
      ? selectedCardId
      : null
  const selectedPreview: WritingKeywordCardPreview | null =
    (visibleCards.find((item) => item.card_id === effectiveSelectedCardId) as WritingKeywordCard | undefined) || null

  const pinnedDetailQueries = useQueries({
    queries: pinnedInsightCards.map((item) => ({
      queryKey: queryKeys.writing.keywordCardDetail(projectKey, item.cardId),
      queryFn: () => getWritingCardDetail(item.cardId, { include_provenance: true, max_provenance_items: 12 }),
      enabled: canUseWritingProject,
    })),
  })
  const pinnedCardsWithDetail = useMemo(
    () =>
      pinnedInsightCards.map((item, index) => ({
        ...item,
        detail: pinnedDetailQueries[index]?.data || null,
        loading: Boolean(pinnedDetailQueries[index]?.isLoading),
      })),
    [pinnedDetailQueries, pinnedInsightCards],
  )
  const findCardPreview = useCallback(
    (cardId: string) =>
      pinnedInsightCards.find((item) => item.cardId === cardId)?.preview ||
      visibleCards.find((item) => item.card_id === cardId) ||
      citationPreviewByCardId.get(cardId) ||
      (selectedPreview?.card_id === cardId ? selectedPreview : null),
    [citationPreviewByCardId, pinnedInsightCards, selectedPreview, visibleCards],
  )

  const citationsMutation = useMutation({
    mutationFn: async ({
      cardId,
      previewOverride,
      source,
    }: {
      cardId: string
      previewOverride?: WritingKeywordCardPreview | null
      source: CitationMutationSource
    }) => {
      if (!cardId) {
        return { skippedDuplicate: true, targetDocumentId: effectiveDocumentId, source }
      }
      if (pendingCitationCardIdsRef.current.has(cardId)) {
        return { skippedDuplicate: true, duplicateReason: 'pending', targetDocumentId: effectiveDocumentId, source }
      }
      pendingCitationCardIdsRef.current.add(cardId)
      try {
      const preview = previewOverride || findCardPreview(cardId)
      let targetDocumentId = effectiveDocumentId
      let createdDocument: Awaited<ReturnType<typeof createWritingDocument>> | null = null

      if (targetDocumentId == null) {
        createdDocument = await createWritingDocument({
          title: title.trim() || 'Untitled report',
          body_md: markdown,
          metadata_json: { source: 'writing-workbench', project_key: projectKey },
        })
        targetDocumentId = createdDocument.id
      }

      const existingItems = targetDocumentId === effectiveDocumentId ? citationsQuery.data || [] : []
      if (existingItems.some((item) => item.card_id === cardId)) {
        return {
          createdDocument,
          targetDocumentId,
          saved: existingItems,
          skippedDuplicate: true,
          source,
        }
      }

      const nextItems = [
        ...existingItems,
        {
          card_id: cardId,
          source_title: preview?.title || cardId,
          source_uri: preview?.url || null,
          quote_text: preview?.snippet || selectionText || '',
          position_anchor: selectionLookup.selectionHash || 'selection',
        },
      ]
      const saved = await upsertWritingCitations(targetDocumentId, nextItems)
      return {
        createdDocument,
        targetDocumentId,
        saved,
        skippedDuplicate: false,
        source,
      }
      } finally {
        pendingCitationCardIdsRef.current.delete(cardId)
      }
    },
    onSuccess: async (result) => {
      if (!result?.targetDocumentId) return
      if (result.skippedDuplicate) {
        setCitationTrayCollapsed(false)
        setCitationTrayDragOver(false)
        setSaveMessage('引用已存在')
        return
      }
      if (result.createdDocument?.id) {
        setIsCreatingDraft(false)
        setActiveDocumentId(result.createdDocument.id)
        setDraftByKey((prev) => {
          const next = { ...prev }
          delete next[draftKey]
          delete next[String(result.createdDocument?.id)]
          return next
        })
        setAutosaveMessage('saved')
        setSaveMessage('文档已自动创建并加入引用')
        setExportMessage('')
        await queryClient.invalidateQueries({ queryKey: queryKeys.writing.documents(projectKey) })
        await queryClient.invalidateQueries({ queryKey: queryKeys.writing.documentDetail(projectKey, result.createdDocument.id) })
      }
      setCitationTrayCollapsed(false)
      setCitationTrayDragOver(false)
      setSaveMessage('已加入引用')
      if (result.source.kind === 'selected') {
        dismissInsightCard()
      } else if (result.source.kind === 'pinned') {
        removePinnedInsightCard(result.source.pinnedCardId)
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.writing.citations(projectKey, result.targetDocumentId) })
    },
  })

  const handleDropCardToCitationTray = useCallback(
    (payload: WritingDraggedCardPayload) => {
      citationsMutation.mutate({
        cardId: payload.cardId,
        previewOverride: toDraggedCardPreview(payload),
        source: { kind: 'external' },
      })
    },
    [citationsMutation],
  )

  const addPreviewToCitationTray = useCallback(
    (preview: WritingKeywordCardPreview | null | undefined, source: CitationMutationSource) => {
      if (!preview) return
      citationsMutation.mutate({
        cardId: preview.card_id,
        previewOverride: preview,
        source,
      })
    },
    [citationsMutation],
  )

  const selectedPreviewQuery = useQuery({
    queryKey: queryKeys.writing.keywordCardPreview(projectKey, effectiveSelectedCardId || '__none__'),
    queryFn: () => previewWritingKeywordCard({ card_id: effectiveSelectedCardId as string, query: selectionText || undefined }),
    enabled: canUseWritingProject && Boolean(effectiveSelectedCardId),
  })
  const resolvedSelectedPreview =
    selectedPreview ||
    selectedPreviewQuery.data ||
    (effectiveSelectedCardId ? citationPreviewByCardId.get(effectiveSelectedCardId) || null : null)
  const selectedDetailQuery = useQuery({
    queryKey: queryKeys.writing.keywordCardDetail(projectKey, effectiveSelectedCardId || '__none__'),
    queryFn: () => getWritingCardDetail(effectiveSelectedCardId as string, { include_provenance: true, max_provenance_items: 12 }),
    enabled: canUseWritingProject && Boolean(effectiveSelectedCardId),
  })
  const toolbarStatus = exportMessage || saveMessage || (autosaveMessage !== 'idle' ? autosaveMessage : '')
  const isDesktopFloating = viewport.width > DESKTOP_FLOATING_BREAKPOINT
  const maxPanelHeight = Math.max(PANEL_MIN_HEIGHT, viewport.height - 148)
  const maxPanelWidth = Math.max(PANEL_MIN_WIDTH, Math.min(PANEL_MAX_WIDTH, viewport.width - 120))
  const resolvedDocumentsPanelSize = {
    width: clampValue(documentsPanelSize.width, PANEL_MIN_WIDTH, maxPanelWidth),
    height: clampValue(documentsPanelSize.height, PANEL_MIN_HEIGHT, maxPanelHeight),
  }
  const resolvedTemplatesPanelSize = {
    width: clampValue(templatesPanelSize.width, PANEL_MIN_WIDTH, maxPanelWidth),
    height: clampValue(templatesPanelSize.height, PANEL_MIN_HEIGHT, maxPanelHeight),
  }
  const resolvedInsightsPanelSize = {
    width: clampValue(insightsPanelSize.width, PANEL_MIN_WIDTH, maxPanelWidth),
    height: clampValue(insightsPanelSize.height, PANEL_MIN_HEIGHT, maxPanelHeight),
  }
  const resolvedLlmPanelSize = {
    width: clampValue(llmPanelSize.width, PANEL_MIN_WIDTH, maxPanelWidth),
    height: clampValue(llmPanelSize.height, PANEL_MIN_HEIGHT, maxPanelHeight),
  }
  const effectiveFloatingPanelHeight = Math.min(
    FLOATING_PANEL_MAX_HEIGHT,
    Math.max(PANEL_MIN_HEIGHT, viewport.height - 112),
  )
  const effectiveDocumentsPanelSize = {
    width: resolvedDocumentsPanelSize.width,
    height: Math.min(resolvedDocumentsPanelSize.height, effectiveFloatingPanelHeight),
  }
  const effectiveTemplatesPanelSize = {
    width: resolvedTemplatesPanelSize.width,
    height: Math.min(resolvedTemplatesPanelSize.height, effectiveFloatingPanelHeight),
  }
  const effectiveInsightsPanelSize = {
    width: resolvedInsightsPanelSize.width,
    height: Math.min(resolvedInsightsPanelSize.height, effectiveFloatingPanelHeight),
  }
  const effectiveLlmPanelSize = {
    width: resolvedLlmPanelSize.width,
    height: Math.min(resolvedLlmPanelSize.height, effectiveFloatingPanelHeight),
  }

  useEffect(() => {
    if (effectiveDocumentId == null || !documentDetailQuery.data) return
    if (!isDirty || saveDocumentMutation.isPending) return

    const timer = window.setTimeout(() => {
      setAutosaveMessage('autosaving...')
      void autosaveWritingDraft(effectiveDocumentId, {
        draft_body_md: markdown,
        base_version: documentDetailQuery.data?.version,
        autosave_token: `writing-${effectiveDocumentId}`,
        request_id: `writing-${effectiveDocumentId}-${Date.now()}`,
        selection_snapshot: {
          selection_text: selectionText,
          selection_hash: selectionLookup.selectionHash,
        },
      })
        .then(() => {
          setAutosaveMessage('autosave ready')
        })
        .catch((error) => {
          setAutosaveMessage(error instanceof Error ? error.message : 'autosave failed')
        })
    }, 600)

    return () => window.clearTimeout(timer)
  }, [
    documentDetailQuery.data,
    effectiveDocumentId,
    isDirty,
    markdown,
    saveDocumentMutation.isPending,
    selectionLookup.selectionHash,
    selectionText,
  ])

  useEffect(() => {
    if (!effectiveSelectedCardId) return

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        dismissInsightCard()
      }
    }

    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [dismissInsightCard, effectiveSelectedCardId])

  useEffect(() => {
    const handleResize = () => setViewport(readViewport())
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const documentSummaries = useMemo(
    () =>
      (documentsQuery.data || []).map((item) => ({
        id: item.id,
        title: item.title,
        status: item.status,
        updatedAt: formatUpdatedAt(item.updated_at),
        active: item.id === effectiveDocumentId,
        agentUpdateCount: readAgentUpdates(item.metadata_json).length,
      })),
    [documentsQuery.data, effectiveDocumentId],
  )

  const currentTemplateKey = useMemo(() => {
    if (!templatesQuery.data?.length) return null
    const matched = templatesQuery.data.find((item) => item.template_content === markdown)
    return matched?.template_key || null
  }, [markdown, templatesQuery.data])

  const activateFloatingWindow = useCallback((key: FloatingWindowKey) => {
    setActiveFloatingWindow(key)
  }, [])

  const resolveFloatingWindowZIndex = useCallback(
    (key: FloatingWindowKey) => {
      const base = 56
      const orderIndex = FLOATING_WINDOW_ORDER.indexOf(key)
      return base + Math.max(orderIndex, 0) + (activeFloatingWindow === key ? 12 : 0)
    },
    [activeFloatingWindow],
  )

  const toggleDocumentsPanel = () =>
    setDocumentsPanelOpen((prev) => {
      const next = !prev
      if (next) activateFloatingWindow('documents')
      return next
    })
  const toggleTemplatesPanel = () =>
    setTemplatesPanelOpen((prev) => {
      const next = !prev
      if (next) activateFloatingWindow('templates')
      return next
    })
  const toggleInsightsPanel = () =>
    setInsightsPanelOpen((prev) => {
      const next = !prev
      if (next) activateFloatingWindow('insights')
      return next
    })
  const toggleLlmPanel = () =>
    setLlmPanelOpen((prev) => {
      const next = !prev
      if (next) activateFloatingWindow('llm')
      return next
    })

  const toggleCitationTray = () => {
    activateFloatingWindow('citations')
    setCitationTrayCollapsed((prev) => !prev)
  }

  const isAnchorOverCitationTray = useCallback((anchor: InsightCardAnchor) => {
    const tray = citationTrayRef.current
    if (!tray) return false
    const rect = tray.getBoundingClientRect()
    const anchorLeft = anchor.left
    const anchorRight = anchor.left + anchor.width
    const anchorBottom = anchor.top + anchor.height
    const horizontalOverlap = Math.min(anchorRight, rect.right) - Math.max(anchorLeft, rect.left)
    return horizontalOverlap > 96 && anchorBottom >= rect.top + 24
  }, [])

  const beginMouseSession = (
    event: ReactMouseEvent<HTMLElement | HTMLDivElement>,
    onMoveFrame: (deltaX: number, deltaY: number) => void,
    onEndFrame?: () => void,
  ) => {
    event.preventDefault()
    event.stopPropagation()
    const startX = event.clientX
    const startY = event.clientY
    const onMove = (moveEvent: MouseEvent) => {
      onMoveFrame(moveEvent.clientX - startX, moveEvent.clientY - startY)
    }
    const onEnd = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onEnd)
      onEndFrame?.()
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onEnd)
  }

  const beginPanelResize =
    (
      edge: 'e' | 'w' | 's' | 'se' | 'sw',
      start: FloatingSize,
      setSize: (updater: FloatingSize) => void,
    ) =>
    (event: ReactMouseEvent<HTMLDivElement>) => {
      if (!isDesktopFloating) return
      beginMouseSession(event, (deltaX, deltaY) => {
        setSize({
          width: clampValue(
            start.width + (edge === 'w' || edge === 'sw' ? -deltaX : edge === 'e' || edge === 'se' ? deltaX : 0),
            PANEL_MIN_WIDTH,
            maxPanelWidth,
          ),
          height: clampValue(
            start.height + (edge === 's' || edge === 'se' || edge === 'sw' ? deltaY : 0),
            PANEL_MIN_HEIGHT,
            maxPanelHeight,
          ),
        })
      })
    }

  const beginDockedPanelDrag = (
    event: ReactMouseEvent<HTMLDivElement>,
    panelRef: React.RefObject<HTMLElement | null>,
    setDragRect: (rect: FloatingRect | null) => void,
    setPosition: (position: DockedPosition) => void,
  ) => {
    if (!isDesktopFloating || event.button !== 0) return
    const target = event.target as HTMLElement | null
    if (target?.closest('button, input, textarea, a')) return
    const rect = panelRef.current?.getBoundingClientRect()
    if (!rect) return
    const startRect = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    }
    let droppedRect = startRect
    beginMouseSession(event, (deltaX, deltaY) => {
      droppedRect = clampFloatingRect(
        {
          left: startRect.left + deltaX,
          top: startRect.top + deltaY,
          width: startRect.width,
          height: startRect.height,
        },
        viewport,
        FLOATING_PANEL_MARGIN,
        FLOATING_PANEL_TOP_INSET,
      )
      setDragRect(droppedRect)
    }, () => {
      setDragRect(null)
      setPosition(resolveDockFromRect(droppedRect, viewport))
    })
  }

  const clampToolbarPosition = useCallback((position: FloatingPoint): FloatingPoint => {
    const shellRect = canvasShellRef.current?.getBoundingClientRect()
    const toolbarRect = toolbarRef.current?.getBoundingClientRect()
    if (!shellRect || !toolbarRect) return position

    return {
      left: clampValue(
        position.left,
        WRITING_TOOLBAR_MARGIN,
        Math.max(WRITING_TOOLBAR_MARGIN, shellRect.width - toolbarRect.width - WRITING_TOOLBAR_MARGIN),
      ),
      top: clampValue(
        position.top,
        WRITING_TOOLBAR_MARGIN,
        Math.max(WRITING_TOOLBAR_MARGIN, shellRect.height - toolbarRect.height - WRITING_TOOLBAR_MARGIN),
      ),
    }
  }, [])

  const handleToolbarDragStart = (event: ReactMouseEvent<HTMLSpanElement>) => {
    if (!isDesktopFloating || event.button !== 0) return
    const shellRect = canvasShellRef.current?.getBoundingClientRect()
    const toolbarRect = toolbarRef.current?.getBoundingClientRect()
    if (!shellRect || !toolbarRect) return

    const startPosition = {
      left: toolbarRect.left - shellRect.left,
      top: toolbarRect.top - shellRect.top,
    }

    beginMouseSession(event, (deltaX, deltaY) => {
      setToolbarPosition(clampToolbarPosition({
        left: startPosition.left + deltaX,
        top: startPosition.top + deltaY,
      }))
    })
  }

  const resetToolbarPosition = () => {
    setToolbarPosition(null)
  }

  useEffect(() => {
    if (!toolbarPosition) return
    const nextPosition = clampToolbarPosition(toolbarPosition)
    if (nextPosition.left !== toolbarPosition.left || nextPosition.top !== toolbarPosition.top) {
      setToolbarPosition(nextPosition)
    }
  }, [clampToolbarPosition, toolbarPosition, viewport])

  const handleDocumentsPanelResizeStart = (edge: 'e' | 's' | 'se') =>
    beginPanelResize(edge, effectiveDocumentsPanelSize, setDocumentsPanelSize)

  const handleTemplatesPanelResizeStart = (edge: 'e' | 's' | 'se') =>
    beginPanelResize(edge, effectiveTemplatesPanelSize, setTemplatesPanelSize)

  const handleInsightsPanelResizeStart = (edge: 'w' | 's' | 'sw') =>
    beginPanelResize(edge, effectiveInsightsPanelSize, setInsightsPanelSize)

  const handleLlmPanelResizeStart = (edge: 'w' | 's' | 'sw') =>
    beginPanelResize(edge, effectiveLlmPanelSize, setLlmPanelSize)

  const handleDocumentsPanelDragStart = (event: ReactMouseEvent<HTMLDivElement>) =>
    beginDockedPanelDrag(event, documentsPanelRef, setDocumentsPanelDragRect, setDocumentsPanelPosition)

  const handleTemplatesPanelDragStart = (event: ReactMouseEvent<HTMLDivElement>) =>
    beginDockedPanelDrag(event, templatesPanelRef, setTemplatesPanelDragRect, setTemplatesPanelPosition)

  const handleInsightsPanelDragStart = (event: ReactMouseEvent<HTMLDivElement>) =>
    beginDockedPanelDrag(event, insightsPanelRef, setInsightsPanelDragRect, setInsightsPanelPosition)

  const handleLlmPanelDragStart = (event: ReactMouseEvent<HTMLDivElement>) =>
    beginDockedPanelDrag(event, llmPanelRef, setLlmPanelDragRect, setLlmPanelPosition)

  const handleCitationTrayDragStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!isDesktopFloating || event.button !== 0) return
    const target = event.target as HTMLElement | null
    if (target?.closest('button, input, textarea, a')) return
    const tray = citationTrayRef.current
    const rect = tray?.getBoundingClientRect()
    if (!rect) return
    let droppedRect: FloatingRect = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    }
    beginMouseSession(event, (deltaX, deltaY) => {
      droppedRect = clampFloatingRect(
        {
          left: rect.left + deltaX,
          top: rect.top + deltaY,
          width: rect.width,
          height: rect.height,
        },
        viewport,
        CITATION_BAR_MARGIN,
        FLOATING_PANEL_TOP_INSET,
      )
      setCitationTrayDragRect(droppedRect)
    }, () => {
      setCitationTrayDragRect(null)
      setCitationTrayPosition(resolveDockFromRect(droppedRect, viewport))
    })
  }

  const resolvedInsightCardAnchor = resolveInsightCardAnchor(insightCardAnchor, viewport)

  const movePinnedCardToFront = useCallback((cardId: string) => {
    setPinnedInsightCards((prev) => {
      const target = prev.find((item) => item.cardId === cardId)
      if (!target) return prev
      return [...prev.filter((item) => item.cardId !== cardId), target]
    })
  }, [])

  const updatePinnedInsightCardAnchor = useCallback((cardId: string, nextAnchor: InsightCardAnchor) => {
    setPinnedInsightCards((prev) =>
      prev.map((item) =>
        item.cardId === cardId
          ? {
              ...item,
              anchor: resolveInsightCardAnchor(nextAnchor, viewport),
            }
          : item,
      ),
    )
  }, [viewport])

  const removePinnedInsightCard = useCallback((cardId: string) => {
    setPinnedInsightCards((prev) => prev.filter((item) => item.cardId !== cardId))
  }, [])

  const pinSelectedInsightCard = useCallback(() => {
    if (!resolvedSelectedPreview) return
    const nextAnchor = resolveInsightCardAnchor(
      {
        ...resolvedInsightCardAnchor,
        left: resolvedInsightCardAnchor.left + 24,
        top: resolvedInsightCardAnchor.top + 24,
      },
      viewport,
    )
    setPinnedInsightCards((prev) => {
      const existing = prev.find((item) => item.cardId === resolvedSelectedPreview.card_id)
      if (existing) {
        return [
          ...prev.filter((item) => item.cardId !== resolvedSelectedPreview.card_id),
          { ...existing, preview: resolvedSelectedPreview, anchor: nextAnchor },
        ]
      }
      return [
        ...prev,
        {
          cardId: resolvedSelectedPreview.card_id,
          preview: resolvedSelectedPreview,
          anchor: nextAnchor,
        },
      ]
    })
    setSelectedCardId(null)
  }, [resolvedInsightCardAnchor, resolvedSelectedPreview, viewport])

  const handleInsightCardDragStart = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!isDesktopFloating || event.button !== 0) return
    const target = event.target as HTMLElement | null
    if (target?.closest('button, a')) return
    const current = resolvedInsightCardAnchor
    const offsetX = event.clientX - current.left
    const offsetY = event.clientY - current.top
    let nextAnchor = current
    setCitationTrayDragOver(true)
    beginMouseSession(event, (deltaX, deltaY) => {
      const maxLeft = Math.max(INSIGHT_CARD_MARGIN, viewport.width - current.width - INSIGHT_CARD_MARGIN)
      const maxTop = Math.max(INSIGHT_CARD_MARGIN, viewport.height - INSIGHT_CARD_VISIBLE_HEADER)
      nextAnchor = {
        left: clampValue(event.clientX + deltaX - offsetX, INSIGHT_CARD_MARGIN, maxLeft),
        top: clampValue(event.clientY + deltaY - offsetY, INSIGHT_CARD_MARGIN, maxTop),
        width: current.width,
        height: current.height,
      }
      setInsightCardAnchor(nextAnchor)
    }, () => {
      setCitationTrayDragOver(false)
      if (isAnchorOverCitationTray(nextAnchor)) {
        addPreviewToCitationTray(resolvedSelectedPreview, { kind: 'selected' })
      }
    })
  }

  const handlePinnedInsightCardDragStart = (cardId: string) => (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!isDesktopFloating || event.button !== 0) return
    const target = event.target as HTMLElement | null
    if (target?.closest('button, a')) return
    const currentCard = pinnedInsightCards.find((item) => item.cardId === cardId)
    if (!currentCard) return
    const current = resolveInsightCardAnchor(currentCard.anchor, viewport)
    movePinnedCardToFront(cardId)
    const offsetX = event.clientX - current.left
    const offsetY = event.clientY - current.top
    let nextAnchor = current
    setCitationTrayDragOver(true)
    beginMouseSession(event, (deltaX, deltaY) => {
      const maxLeft = Math.max(INSIGHT_CARD_MARGIN, viewport.width - current.width - INSIGHT_CARD_MARGIN)
      const maxTop = Math.max(INSIGHT_CARD_MARGIN, viewport.height - INSIGHT_CARD_VISIBLE_HEADER)
      nextAnchor = {
        left: clampValue(event.clientX + deltaX - offsetX, INSIGHT_CARD_MARGIN, maxLeft),
        top: clampValue(event.clientY + deltaY - offsetY, INSIGHT_CARD_MARGIN, maxTop),
        width: current.width,
        height: current.height,
      }
      updatePinnedInsightCardAnchor(cardId, nextAnchor)
    }, () => {
      setCitationTrayDragOver(false)
      if (isAnchorOverCitationTray(nextAnchor)) {
        addPreviewToCitationTray(currentCard.preview, { kind: 'pinned', pinnedCardId: cardId })
      }
    })
  }

  const handleInsightCardResizeStart = (edge: 'n' | 'e' | 'w' | 's' | 'ne' | 'nw' | 'se' | 'sw') => (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!isDesktopFloating) return
    const start = resolvedInsightCardAnchor
    const maxWidth = Math.max(INSIGHT_CARD_MIN_WIDTH, viewport.width - INSIGHT_CARD_MARGIN * 2)
    const maxHeight = Math.max(INSIGHT_CARD_MIN_HEIGHT, viewport.height + INSIGHT_CARD_BOTTOM_OVERFLOW - INSIGHT_CARD_MARGIN * 2)
    beginMouseSession(event, (deltaX, deltaY) => {
        let nextLeft = start.left
        let nextTop = start.top
        let nextWidth = start.width
        let nextHeight = start.height

        if (edge === 'e' || edge === 'se' || edge === 'ne') {
          nextWidth = clampValue(start.width + deltaX, INSIGHT_CARD_MIN_WIDTH, Math.min(maxWidth, viewport.width - start.left - INSIGHT_CARD_MARGIN))
        }
        if (edge === 'w' || edge === 'sw' || edge === 'nw') {
          const nextRawLeft = clampValue(start.left + deltaX, INSIGHT_CARD_MARGIN, start.left + start.width - INSIGHT_CARD_MIN_WIDTH)
          nextLeft = nextRawLeft
          nextWidth = clampValue(start.width - (nextRawLeft - start.left), INSIGHT_CARD_MIN_WIDTH, maxWidth)
        }
        if (edge === 's' || edge === 'se' || edge === 'sw') {
          nextHeight = clampValue(
            start.height + deltaY,
            INSIGHT_CARD_MIN_HEIGHT,
            Math.min(maxHeight, viewport.height + INSIGHT_CARD_BOTTOM_OVERFLOW - start.top),
          )
        }
        if (edge === 'n' || edge === 'ne' || edge === 'nw') {
          const nextRawTop = clampValue(
            start.top + deltaY,
            INSIGHT_CARD_MARGIN,
            start.top + start.height - INSIGHT_CARD_MIN_HEIGHT,
          )
          nextTop = nextRawTop
          nextHeight = clampValue(start.height - (nextRawTop - start.top), INSIGHT_CARD_MIN_HEIGHT, maxHeight)
        }

        setInsightCardAnchor({
          left: clampValue(nextLeft, INSIGHT_CARD_MARGIN, Math.max(INSIGHT_CARD_MARGIN, viewport.width - nextWidth - INSIGHT_CARD_MARGIN)),
          top: clampValue(nextTop, INSIGHT_CARD_MARGIN, Math.max(INSIGHT_CARD_MARGIN, viewport.height - INSIGHT_CARD_VISIBLE_HEADER)),
          width: nextWidth,
          height: nextHeight,
        })
      })
  }

  const handlePinnedInsightCardResizeStart =
    (cardId: string, edge: 'n' | 'e' | 'w' | 's' | 'ne' | 'nw' | 'se' | 'sw') => (event: ReactMouseEvent<HTMLDivElement>) => {
      if (!isDesktopFloating) return
      const currentCard = pinnedInsightCards.find((item) => item.cardId === cardId)
      if (!currentCard) return
      const start = resolveInsightCardAnchor(currentCard.anchor, viewport)
      const maxWidth = Math.max(INSIGHT_CARD_MIN_WIDTH, viewport.width - INSIGHT_CARD_MARGIN * 2)
      const maxHeight = Math.max(INSIGHT_CARD_MIN_HEIGHT, viewport.height + INSIGHT_CARD_BOTTOM_OVERFLOW - INSIGHT_CARD_MARGIN * 2)
      movePinnedCardToFront(cardId)
      beginMouseSession(event, (deltaX, deltaY) => {
        let nextLeft = start.left
        let nextTop = start.top
        let nextWidth = start.width
        let nextHeight = start.height

        if (edge === 'e' || edge === 'se' || edge === 'ne') {
          nextWidth = clampValue(
            start.width + deltaX,
            INSIGHT_CARD_MIN_WIDTH,
            Math.min(maxWidth, viewport.width - start.left - INSIGHT_CARD_MARGIN),
          )
        }
        if (edge === 'w' || edge === 'sw' || edge === 'nw') {
          const nextRawLeft = clampValue(
            start.left + deltaX,
            INSIGHT_CARD_MARGIN,
            start.left + start.width - INSIGHT_CARD_MIN_WIDTH,
          )
          nextLeft = nextRawLeft
          nextWidth = clampValue(start.width - (nextRawLeft - start.left), INSIGHT_CARD_MIN_WIDTH, maxWidth)
        }
        if (edge === 's' || edge === 'se' || edge === 'sw') {
          nextHeight = clampValue(
            start.height + deltaY,
            INSIGHT_CARD_MIN_HEIGHT,
            Math.min(maxHeight, viewport.height + INSIGHT_CARD_BOTTOM_OVERFLOW - start.top),
          )
        }
        if (edge === 'n' || edge === 'ne' || edge === 'nw') {
          const nextRawTop = clampValue(
            start.top + deltaY,
            INSIGHT_CARD_MARGIN,
            start.top + start.height - INSIGHT_CARD_MIN_HEIGHT,
          )
          nextTop = nextRawTop
          nextHeight = clampValue(start.height - (nextRawTop - start.top), INSIGHT_CARD_MIN_HEIGHT, maxHeight)
        }

        updatePinnedInsightCardAnchor(cardId, {
          left: clampValue(
            nextLeft,
            INSIGHT_CARD_MARGIN,
            Math.max(INSIGHT_CARD_MARGIN, viewport.width - nextWidth - INSIGHT_CARD_MARGIN),
          ),
          top: clampValue(
            nextTop,
            INSIGHT_CARD_MARGIN,
            Math.max(INSIGHT_CARD_MARGIN, viewport.height - INSIGHT_CARD_VISIBLE_HEADER),
          ),
          width: nextWidth,
          height: nextHeight,
        })
      })
    }

  const documentsPanelStyle = isDesktopFloating
    ? documentsPanelDragRect
      ? {
          left: documentsPanelDragRect.left,
          top: documentsPanelDragRect.top,
          right: 'auto',
          bottom: 'auto',
          width: effectiveDocumentsPanelSize.width,
          height: effectiveDocumentsPanelSize.height,
          zIndex: resolveFloatingWindowZIndex('documents'),
        }
      : {
          ...buildDockedStyle(documentsPanelPosition, viewport, effectiveDocumentsPanelSize.width, effectiveDocumentsPanelSize.height),
          zIndex: resolveFloatingWindowZIndex('documents'),
        }
    : undefined

  const templatesPanelStyle = isDesktopFloating
    ? templatesPanelDragRect
      ? {
          left: templatesPanelDragRect.left,
          top: templatesPanelDragRect.top,
          right: 'auto',
          bottom: 'auto',
          width: effectiveTemplatesPanelSize.width,
          height: effectiveTemplatesPanelSize.height,
          zIndex: resolveFloatingWindowZIndex('templates'),
        }
      : {
          ...buildDockedStyle(templatesPanelPosition, viewport, effectiveTemplatesPanelSize.width, effectiveTemplatesPanelSize.height),
          zIndex: resolveFloatingWindowZIndex('templates'),
        }
    : undefined

  const insightsPanelStyle = isDesktopFloating
    ? insightsPanelDragRect
      ? {
          left: insightsPanelDragRect.left,
          top: insightsPanelDragRect.top,
          right: 'auto',
          bottom: 'auto',
          width: effectiveInsightsPanelSize.width,
          height: effectiveInsightsPanelSize.height,
          zIndex: resolveFloatingWindowZIndex('insights'),
        }
      : {
          ...buildDockedStyle(insightsPanelPosition, viewport, effectiveInsightsPanelSize.width, effectiveInsightsPanelSize.height),
          zIndex: resolveFloatingWindowZIndex('insights'),
        }
    : undefined

  const llmPanelStyle = isDesktopFloating
    ? llmPanelDragRect
      ? {
          left: llmPanelDragRect.left,
          top: llmPanelDragRect.top,
          right: 'auto',
          bottom: 'auto',
          width: effectiveLlmPanelSize.width,
          height: effectiveLlmPanelSize.height,
          zIndex: resolveFloatingWindowZIndex('llm'),
        }
      : {
          ...buildDockedStyle(llmPanelPosition, viewport, effectiveLlmPanelSize.width, effectiveLlmPanelSize.height),
          zIndex: resolveFloatingWindowZIndex('llm'),
        }
    : undefined
  const citationTrayStyle = isDesktopFloating
    ? citationTrayDragRect
      ? {
          left: citationTrayDragRect.left,
          top: citationTrayDragRect.top,
          right: 'auto',
          bottom: 'auto',
          width: citationTrayDragRect.width,
          zIndex: resolveFloatingWindowZIndex('citations'),
        }
      : {
          ...buildCitationDockedStyle(citationTrayPosition, viewport),
          zIndex: resolveFloatingWindowZIndex('citations'),
        }
    : undefined
  const toolbarStyle = toolbarPosition
    ? {
        left: Math.round(toolbarPosition.left),
        top: Math.round(toolbarPosition.top),
        right: 'auto',
        transform: 'none',
      }
    : undefined

  const insightCardStyle = effectiveSelectedCardId ? buildInsightCardStyle(resolvedInsightCardAnchor, 96) : undefined

  const handleExportMarkdown = async () => {
    if (effectiveDocumentId == null) {
      setExportMessage('请先保存文档')
      return
    }
    if (isDirty) {
      setExportMessage('请先保存当前修改，再导出 Markdown')
      return
    }

    try {
      setExportMessage('exporting...')
      const exported = await exportWritingMarkdown(effectiveDocumentId, projectKey)
      const blob = new Blob([exported.markdown], { type: 'text/markdown;charset=utf-8' })
      const url = window.URL.createObjectURL(blob)
      const anchor = window.document.createElement('a')
      anchor.href = url
      anchor.download = exported.filename
      anchor.click()
      window.URL.revokeObjectURL(url)
      setExportMessage(`已导出 ${exported.filename}`)
    } catch (error) {
      setExportMessage(error instanceof Error ? error.message : '导出失败')
    }
  }

  const startNewDraft = () => {
    setIsCreatingDraft(true)
    setActiveDocumentId(null)
    resetContextPanels()
    setSaveMessage('')
    setExportMessage('')
    setAutosaveMessage('new draft')
    setDocumentsPanelOpen(false)
    setTemplatesPanelOpen(false)
    setDraftByKey((prev) => ({
      ...prev,
      __new__: {
        title: '',
        markdown: EMPTY_MARKDOWN,
      },
    }))
  }

  const handleSelectDocument = (documentId: number) => {
    setIsCreatingDraft(false)
    setActiveDocumentId(documentId)
    resetContextPanels()
    setSaveMessage('')
    setExportMessage('')
    setAutosaveMessage('idle')
    setDocumentsPanelOpen(false)
  }

  const handleApplyTemplate = (templateKey: string) => {
    const template = templatesQuery.data?.find((item) => item.template_key === templateKey)
    if (!template) return
    setDraftByKey((prev) => ({
      ...prev,
      [draftKey]: { title, markdown: template.template_content },
    }))
    setTemplateValidation(null)
    setViewMode('write')
    setTemplatesPanelOpen(false)
  }

  const handleBackToWorkspace = () => {
    window.location.hash = hashByMode.overviewTasks
  }

  const handleSelectInsightCard = (cardId: string) => {
    if (pinnedInsightCards.some((item) => item.cardId === cardId)) {
      movePinnedCardToFront(cardId)
      setSelectedCardId(null)
      return
    }
    setSelectedCardId(cardId)
  }

  const handleOpenCitationCard = useCallback(
    (citation: WritingCitation) => {
      const cardId = citation.card_id
      if (!cardId) return
      setCitationTrayCollapsed(false)
      setInsightsPanelOpen(true)
      activateFloatingWindow('insights')
      if (pinnedInsightCards.some((item) => item.cardId === cardId)) {
        movePinnedCardToFront(cardId)
        setSelectedCardId(null)
        return
      }
      setSelectedCardId(cardId)
    },
    [activateFloatingWindow, movePinnedCardToFront, pinnedInsightCards],
  )

  const handleSelectionTextChange = (nextSelectionText: string, nextSelectionState?: MarkdownSelectionState) => {
    setSelectionText(nextSelectionText)
    setSelectionState(nextSelectionState || null)
    setSelectedCardId(null)
    if (!nextSelectionText.trim()) return
    setInsightsPanelOpen(true)
    activateFloatingWindow('insights')
  }

  const handleRefreshWritingState = useCallback(async () => {
    setAutosaveMessage('refreshing...')
    const refreshes: Array<Promise<unknown>> = [documentsQuery.refetch()]
    if (effectiveDocumentId != null) {
      refreshes.push(documentDetailQuery.refetch())
      refreshes.push(citationsQuery.refetch())
    }
    try {
      await Promise.all(refreshes)
      setAutosaveMessage('refreshed')
      setSaveMessage('已刷新工作台')
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : '刷新失败')
    }
  }, [citationsQuery, documentDetailQuery, documentsQuery, effectiveDocumentId])

  const buildWritingAgentCommand = useCallback(
    (userCommand: string) => {
      const selection = selectionState
      const activeHeading = selection ? findHeadingBefore(markdown, selection.start) : ''
      const documentContext = {
        project_key: projectKey,
        doc_id: effectiveDocumentId,
        title: title || 'Untitled report',
        version: documentDetailQuery.data?.version ?? null,
        etag: documentDetailQuery.data?.etag ?? null,
        dirty_in_browser: isDirty,
        selected_text: boundedText(selectionText, 1400),
        selection_start: selection?.start ?? null,
        selection_end: selection?.end ?? null,
        cursor_offset: selection?.end ?? null,
        selection_line: selection?.line ?? null,
        active_heading: activeHeading,
        before_selection: boundedText(selection?.before || '', 900),
        after_selection: boundedText(selection?.after || '', 900),
        visible_markdown_excerpt: effectiveDocumentId == null ? boundedText(markdown, 2200) : boundedText(markdown.slice(0, 1600), 1600),
        citation_count: citationsQuery.data?.length ?? 0,
        pinned_materials: pinnedInsightCards.slice(-5).map((item) => ({
          card_id: item.cardId,
          title: item.preview.title,
          snippet: boundedText(item.preview.snippet || '', 360),
          source_type: item.preview.source_type,
        })),
      }
      return [
        '你正在写作工作台中作为 AgentCore 写作协作核心工作。不要调用旧的 writing/llm-actions；需要资料、文档读取或写回时使用 AgentCore 可见工具。',
        '如果用户要求修改文档，优先先调用 writing.document.read 获取 version/etag，然后调用 writing.document.insert_paragraph。',
        '定位规则：有 selected_text 且 selection_start/selection_end 可用时，替换优先用 operation=replace_range + range_start + range_end + selection_snapshot；在光标处续写优先用 operation=insert_at_offset + cursor_offset；锚点文本只作为 range 不可用时的 fallback，使用 replace_text/insert_after_text/insert_before_text + anchor_text=selected_text；无选区但有 active_heading 时，用 operation=after_heading。',
        '如果当前文档 dirty_in_browser=true，先提醒用户保存，除非用户明确要求以服务器最新版 allow_latest=true 写回。',
        `用户请求：${userCommand}`,
        `写作工作台上下文 JSON：${JSON.stringify(documentContext, null, 2)}`,
      ].join('\n\n')
    },
    [
      citationsQuery.data?.length,
      documentDetailQuery.data?.etag,
      documentDetailQuery.data?.version,
      effectiveDocumentId,
      isDirty,
      markdown,
      pinnedInsightCards,
      projectKey,
      selectionState,
      selectionText,
      title,
    ],
  )

  const runWritingAgentCommand = useCallback(
    async (rawCommand: string) => {
      const command = rawCommand.trim()
      if (!command || writingAgentBusy) return
      if (!canUseWritingProject) {
        setWritingAgentMessages((prev) => [
          ...prev,
          {
            id: `writing-agent-system-${Date.now()}`,
            role: 'system',
            content: '当前项目仍在解析中，等顶部项目切换到真实 project_key 后再调用写作 Agent。',
          },
        ])
        return
      }
      const loadingId = `writing-agent-loading-${Date.now()}`
      setWritingAgentDraft('')
      setWritingAgentBusy(true)
      setWritingAgentStreamStatus('connecting')
      setWritingAgentMessages((prev) => [
        ...prev,
        { id: `writing-agent-user-${Date.now()}`, role: 'user', content: command },
        { id: loadingId, role: 'assistant', content: '正在处理写作上下文...', pending: true },
      ])

      let streamedText = ''
      const updateLoading = (content: string, pending = true) => {
        setWritingAgentMessages((prev) =>
          prev.map((message) =>
            message.id === loadingId
              ? {
                  ...message,
                  content,
                  pending,
                }
              : message,
          ),
        )
      }

      try {
        const result = await runAgentChatTurnStreaming(
          {
            message: buildWritingAgentCommand(command),
            project_key: projectKey || null,
            session_id: writingAgentSessionId || null,
            enable_model_tool_loop: true,
            require_high_risk_approval: false,
          },
          {
            onStatus: setWritingAgentStreamStatus,
            onEvent: (event) => {
              const chunk = extractWritingAgentChunk(event)
              if (!chunk?.text) return
              streamedText = chunk.mode === 'append' ? `${streamedText}${chunk.text}` : chunk.text
              updateLoading(streamedText || '正在处理写作上下文...')
            },
          },
        )
        const nextSessionId = String(result?.session?.session_id || result?.stream?.session_id || '').trim()
        if (nextSessionId) setWritingAgentSessionId(nextSessionId)
        updateLoading(String(result?.final_answer || streamedText || '写作 Agent 已完成本轮处理。').trim(), false)
        setWritingAgentStreamStatus('closed')
        await handleRefreshWritingState()
      } catch (error) {
        setWritingAgentStreamStatus('error')
        updateLoading(`写作 Agent 调用失败：${error instanceof Error ? error.message : String(error)}`, false)
      } finally {
        setWritingAgentBusy(false)
      }
    },
    [buildWritingAgentCommand, canUseWritingProject, handleRefreshWritingState, projectKey, writingAgentBusy, writingAgentSessionId],
  )

  const handleLocateAgentUpdate = (update: WritingAgentUpdate) => {
    const range = findAgentUpdateRange(markdown, update)
    if (!range) {
      setSaveMessage('未在当前正文中找到该 Agent 块')
      return
    }

    setViewMode('write')
    setSaveMessage(`已定位 ${update.locator.anchorId}`)
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const textarea = canvasShellRef.current?.querySelector<HTMLTextAreaElement>('.writing-editor__textarea')
        if (!textarea) return
        textarea.focus()
        textarea.setSelectionRange(range.start, range.end)
        const lineCountBefore = markdown.slice(0, range.start).split('\n').length - 1
        const lineHeight = Number.parseFloat(window.getComputedStyle(textarea).lineHeight || '') || 30
        textarea.scrollTop = Math.max(0, lineCountBefore * lineHeight - textarea.clientHeight / 3)
      })
    })
  }

  const persistAgentUpdateReview = async (
    update: WritingAgentUpdate,
    reviewStatus: WritingAgentReviewStatus,
    nextMarkdown = persistedMarkdown,
  ) => {
    if (effectiveDocumentId == null || !documentDetailQuery.data) {
      setSaveMessage('当前没有可更新的文档')
      return
    }
    if (isDirty) {
      setSaveMessage('请先保存当前草稿，再处理 Agent 写回')
      return
    }
    const nextMetadata = withAgentUpdateReviewStatus(documentDetailQuery.data.metadata_json, update, reviewStatus)
    try {
      const document = await updateWritingDocument(
        effectiveDocumentId,
        {
          title: persistedTitle || title,
          body_md: nextMarkdown,
          base_version: documentDetailQuery.data.version,
          metadata_json: nextMetadata,
        },
        { ifMatch: documentDetailQuery.data.etag },
      )
      setDraftByKey((prev) => {
        const next = { ...prev }
        delete next[draftKey]
        return next
      })
      setAutosaveMessage('saved')
      setSaveMessage(reviewStatus === 'accepted' ? '已采纳 Agent 写回' : '已撤回 Agent 写回')
      await queryClient.invalidateQueries({ queryKey: queryKeys.writing.documents(projectKey) })
      await queryClient.invalidateQueries({ queryKey: queryKeys.writing.documentDetail(projectKey, document.id || effectiveDocumentId) })
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : 'Agent 写回状态更新失败')
    }
  }

  const handleAcceptAgentUpdate = (update: WritingAgentUpdate) => {
    void persistAgentUpdateReview(update, 'accepted')
  }

  const handleRejectAgentUpdate = (update: WritingAgentUpdate) => {
    if (isDirty) {
      setSaveMessage('请先保存当前草稿，再撤回 Agent 写回')
      return
    }
    const nextMarkdown = buildAgentUpdateRejectedMarkdown(persistedMarkdown, update)
    if (nextMarkdown == null) {
      setSaveMessage('未在服务器正文中找到可撤回的 Agent 块')
      return
    }
    void persistAgentUpdateReview(update, 'rejected', nextMarkdown)
  }

  const writingAgentToolActions: WritingAgentToolAction[] = [
    {
      id: 'rewrite-selection',
      label: '改写选区',
      description: '将当前划词和精确 range 交给 Agent 改写。',
      prompt: '改写当前选区，保持原论证含义但让表达更清晰；请写回当前文档，优先使用 replace_range。',
      disabled: !selectionText,
    },
    {
      id: 'continue-after-selection',
      label: '选区后续写',
      description: '从当前划词后继续扩写一段。',
      prompt: '在当前选区后续写一段，承接上下文并写回当前文档，优先使用 insert_at_offset。',
      disabled: !selectionText,
    },
    {
      id: 'insert-before-selection',
      label: '选区前补桥段',
      description: '在当前划词前补一段过渡或定义。',
      prompt: '在当前选区前补一段必要的过渡、定义或论证铺垫，写回当前文档，使用 insert_before_text。',
      disabled: !selectionText,
    },
    {
      id: 'expand-section',
      label: '扩写当前节',
      description: '根据当前标题和附近上下文扩写当前小节。',
      prompt: '扩写当前标题下的小节，先读取文档，再在当前标题后插入一段结构化内容。',
      disabled: effectiveDocumentId == null,
    },
    {
      id: 'material-search',
      label: '按选区找资料',
      description: '围绕当前选区检索项目内结构化、图谱和资料库信息。',
      prompt: '围绕当前选区检索项目内 documents、graph_nodes、resource_pool 等资料，给出可用于写作的证据点，不要先写回。',
      disabled: !selectionText,
    },
    {
      id: 'evidence-to-paragraph',
      label: '证据转段落',
      description: '把当前资料上下文整理成可写入段落。',
      prompt: '基于当前选区、引用和已钉住资料，生成一段带证据指向的写作段落，并询问或在明确可定位时写回。',
    },
    {
      id: 'outline',
      label: '生成提纲',
      description: '读取当前文档后生成或补全提纲。',
      prompt: '读取当前文档，生成一份可以继续写作的分层提纲；如果文档为空，创建一个适合当前标题的提纲。',
    },
    {
      id: 'review-structure',
      label: '结构审阅',
      description: '检查论证结构、断裂点和需要补证据的位置。',
      prompt: '审阅当前文档结构，指出论证断裂、重复、需要补证据的位置，并给出下一步写作操作建议。',
    },
  ]

  const writingAgentWorkbenchTools: WritingAgentWorkbenchTool[] = [
    { id: 'documents', label: '文档', active: documentsPanelOpen, onClick: toggleDocumentsPanel },
    { id: 'templates', label: '模板', active: templatesPanelOpen, onClick: toggleTemplatesPanel },
    { id: 'insights', label: '资料', active: insightsPanelOpen, onClick: toggleInsightsPanel },
    {
      id: 'citations',
      label: '引用',
      active: citationTrayVisible,
      onClick: () => {
        activateFloatingWindow('citations')
        setCitationTrayVisible((prev) => !prev)
      },
    },
    { id: 'updates', label: '写回', active: agentUpdatesPanelOpen, onClick: () => setAgentUpdatesPanelOpen((prev) => !prev) },
    { id: 'save', label: '保存', disabled: saveDocumentMutation.isPending, onClick: () => saveDocumentMutation.mutate() },
    { id: 'refresh', label: '刷新', onClick: () => void handleRefreshWritingState() },
  ]

  return (
    <div className={`writing-workbench-page${standalone ? ' is-standalone' : ''}`} data-testid="writing-workbench-page">
      <div ref={canvasShellRef} className="writing-canvas-shell" data-testid="writing-canvas-shell">
        <div ref={toolbarRef} className="writing-floating-toolbar" style={toolbarStyle} data-testid="writing-workbench-toolbar">
          <span
            className="writing-toolbar-drag-handle"
            onMouseDown={handleToolbarDragStart}
            onDoubleClick={resetToolbarPosition}
            aria-label="拖动写作条"
            title="拖动写作条，双击恢复默认位置"
          />
          <div className="writing-toolbar-cluster writing-toolbar-cluster--title">
            {standalone ? (
              <button type="button" className="button-secondary" onClick={handleBackToWorkspace}>
                返
              </button>
            ) : null}
            <input
              className="writing-title-input"
              data-testid="writing-title-input"
              aria-label="writing document title"
              value={title}
              onChange={(event) =>
                setDraftByKey((prev) => ({
                  ...prev,
                  [draftKey]: { title: event.target.value, markdown },
                }))
              }
              placeholder="Untitled report"
            />
          </div>

          <div className="writing-toolbar-cluster writing-toolbar-cluster--panels">
            <button type="button" className={panelButtonClass(documentsPanelOpen)} data-testid="writing-panel-documents" onClick={toggleDocumentsPanel}>
              文档
            </button>
            <button type="button" className={panelButtonClass(templatesPanelOpen)} data-testid="writing-panel-templates" onClick={toggleTemplatesPanel}>
              模板
            </button>
            <button type="button" className={panelButtonClass(insightsPanelOpen)} data-testid="writing-panel-insights" onClick={toggleInsightsPanel}>
              资料
            </button>
            <button type="button" className={panelButtonClass(citationTrayVisible)} data-testid="writing-panel-citations" onClick={() => { activateFloatingWindow('citations'); setCitationTrayVisible((prev) => !prev) }}>
              引用
            </button>
            <button type="button" className={panelButtonClass(llmPanelOpen)} data-testid="writing-panel-llm" onClick={toggleLlmPanel}>
              Agent
            </button>
            <button
              type="button"
              className={panelButtonClass(agentUpdatesPanelOpen)}
              data-testid="writing-panel-agent-updates"
              onClick={() => setAgentUpdatesPanelOpen((prev) => !prev)}
            >
              Agent{agentUpdates.length ? ` ${agentUpdates.length}` : ''}
            </button>
          </div>

          <div className="writing-toolbar-cluster writing-toolbar-cluster--actions">
            <button type="button" className={panelButtonClass(viewMode === 'write')} data-testid="writing-mode-write" onClick={() => setViewMode('write')}>
              写
            </button>
            <button type="button" className={panelButtonClass(viewMode === 'preview')} data-testid="writing-mode-preview" onClick={() => setViewMode('preview')}>
              预
            </button>
            <button type="button" className={panelButtonClass(viewMode === 'split')} data-testid="writing-mode-split" onClick={() => setViewMode('split')}>
              分
            </button>
            <button type="button" className="button-secondary" data-testid="writing-new-draft" onClick={startNewDraft}>
              新建
            </button>
            <button type="button" className="button-primary" data-testid="writing-save" onClick={() => saveDocumentMutation.mutate()} disabled={saveDocumentMutation.isPending}>
              保存
            </button>
            <button type="button" className="button-secondary" data-testid="writing-export" onClick={() => void handleExportMarkdown()} disabled={effectiveDocumentId == null || isDirty}>
              导出
            </button>
            <button type="button" className="button-secondary" data-testid="writing-refresh" onClick={() => void handleRefreshWritingState()}>
              刷新
            </button>
          </div>
          <div className="writing-toolbar-cluster writing-toolbar-cluster--meta">
            {latestAgentUpdate ? (
              <span className="chip chip-ok">Agent v{latestAgentUpdate.newVersion || documentDetailQuery.data?.version || '-'}</span>
            ) : null}
            {toolbarStatus ? <span className="writing-toolbar-status">{toolbarStatus}</span> : null}
            {effectiveDocumentId != null ? <span className="chip chip-warn">doc {effectiveDocumentId}</span> : null}
          </div>
        </div>

        <aside
          ref={documentsPanelRef}
          className={`writing-floating-panel writing-floating-panel--left is-docked-${documentsPanelPosition.edge}${documentsPanelOpen ? ' is-open' : ''}`}
          style={documentsPanelStyle}
          onMouseDown={() => activateFloatingWindow('documents')}
        >
          <div className="writing-floating-panel__chrome">
            <span className="writing-floating-drag-handle" onMouseDown={handleDocumentsPanelDragStart} aria-label="拖动文档面板" />
            <div className="writing-floating-panel__tabs">
              <span className="chip chip-warn">文档</span>
            </div>
            <button type="button" className="button-secondary" onClick={() => setDocumentsPanelOpen(false)}>
              收起
            </button>
          </div>

          <div className="writing-floating-panel__body">
            <section className="panel writing-side-panel">
              <div className="panel-header">
                <div>
                  <h2>文档列表</h2>
                  <p className="text-muted writing-panel-subtitle">只保留文档切换，不再和模板共窗。</p>
                </div>
                <span className="chip chip-ok">{documentSummaries.length}</span>
              </div>

              <div className="writing-list">
                <button type="button" className="button-primary" onClick={startNewDraft}>
                  新建空白报告
                </button>
                {documentSummaries.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`writing-list-card${item.active ? ' is-active' : ''}`}
                    data-testid="writing-document-card"
                    data-document-id={item.id}
                    onClick={() => handleSelectDocument(item.id)}
                  >
                    <div className="writing-list-card__header">
                      <strong>{item.title}</strong>
                      <span className={`chip ${item.active ? 'chip-ok' : 'chip-warn'}`}>{item.status}</span>
                    </div>
                    <div className="writing-list-card__footer">
                      <span className="text-muted">{item.updatedAt}</span>
                      <span className="writing-list-card__badges">
                        {item.agentUpdateCount ? <span className="chip chip-ok">Agent {item.agentUpdateCount}</span> : null}
                        {item.active ? <span className="chip chip-ok">当前</span> : null}
                      </span>
                    </div>
                  </button>
                ))}
                {!documentSummaries.length ? <div className="empty-cell">暂无已保存文档，先创建一篇。</div> : null}
              </div>
            </section>
          </div>
          {isDesktopFloating ? (
            <>
              <div className="writing-resize-handle writing-resize-handle--e" onMouseDown={handleDocumentsPanelResizeStart('e')} />
              <div className="writing-resize-handle writing-resize-handle--s" onMouseDown={handleDocumentsPanelResizeStart('s')} />
              <div className="writing-resize-handle writing-resize-handle--se" onMouseDown={handleDocumentsPanelResizeStart('se')} />
            </>
          ) : null}
        </aside>

        <aside
          ref={templatesPanelRef}
          className={`writing-floating-panel writing-floating-panel--left is-docked-${templatesPanelPosition.edge}${templatesPanelOpen ? ' is-open' : ''}`}
          style={templatesPanelStyle}
          onMouseDown={() => activateFloatingWindow('templates')}
        >
          <div className="writing-floating-panel__chrome">
            <span className="writing-floating-drag-handle" onMouseDown={handleTemplatesPanelDragStart} aria-label="拖动模板面板" />
            <div className="writing-floating-panel__tabs">
              <span className="chip chip-warn">模板</span>
            </div>
            <button type="button" className="button-secondary" onClick={() => setTemplatesPanelOpen(false)}>
              收起
            </button>
          </div>

          <div className="writing-floating-panel__body">
            <TemplateLibraryPanel
              templates={templatesQuery.data || []}
              activeTemplateKey={currentTemplateKey}
              validation={templateValidation}
              validating={validateTemplateMutation.isPending}
              onValidateTemplate={(templateKey) => validateTemplateMutation.mutate(templateKey)}
              onApplyTemplate={handleApplyTemplate}
            />
          </div>
          {isDesktopFloating ? (
            <>
              <div className="writing-resize-handle writing-resize-handle--e" onMouseDown={handleTemplatesPanelResizeStart('e')} />
              <div className="writing-resize-handle writing-resize-handle--s" onMouseDown={handleTemplatesPanelResizeStart('s')} />
              <div className="writing-resize-handle writing-resize-handle--se" onMouseDown={handleTemplatesPanelResizeStart('se')} />
            </>
          ) : null}
        </aside>

        <aside
          ref={insightsPanelRef}
          className={`writing-floating-panel writing-floating-panel--right is-docked-${insightsPanelPosition.edge}${insightsPanelOpen ? ' is-open' : ''}`}
          style={insightsPanelStyle}
          onMouseDown={() => activateFloatingWindow('insights')}
        >
          <div className="writing-floating-panel__chrome">
            <span className="writing-floating-drag-handle" onMouseDown={handleInsightsPanelDragStart} aria-label="拖动资料面板" />
            <div className="writing-floating-panel__tabs">
              <span className="chip chip-warn">资料</span>
            </div>
            <button type="button" className="button-secondary" onClick={() => setInsightsPanelOpen(false)}>
              收起
            </button>
          </div>

          <div className="writing-floating-panel__body">
            <KeywordInsightSidebar
              cards={selectionLookup.data?.cards || []}
              suggestItems={selectionLookup.data?.suggestItems || []}
              selectionText={selectionText}
              selectedCardId={effectiveSelectedCardId}
              loading={selectionLookup.status === 'loading'}
              error={selectionLookup.error}
              onSelectCard={handleSelectInsightCard}
              onUseSuggestion={handleSelectionTextChange}
              onDragCardStart={() => setCitationTrayDragOver(true)}
              onDragCardEnd={() => setCitationTrayDragOver(false)}
            />
          </div>
          {isDesktopFloating ? (
            <>
              <div className="writing-resize-handle writing-resize-handle--w" onMouseDown={handleInsightsPanelResizeStart('w')} />
              <div className="writing-resize-handle writing-resize-handle--s" onMouseDown={handleInsightsPanelResizeStart('s')} />
              <div className="writing-resize-handle writing-resize-handle--sw" onMouseDown={handleInsightsPanelResizeStart('sw')} />
            </>
          ) : null}
        </aside>

        <aside
          ref={llmPanelRef}
          className={`writing-floating-panel writing-floating-panel--right is-docked-${llmPanelPosition.edge}${llmPanelOpen ? ' is-open' : ''}`}
          style={llmPanelStyle}
          onMouseDown={() => activateFloatingWindow('llm')}
        >
          <div className="writing-floating-panel__chrome">
            <span className="writing-floating-drag-handle" onMouseDown={handleLlmPanelDragStart} aria-label="拖动 Agent 面板" />
            <div className="writing-floating-panel__tabs">
              <span className="chip chip-warn">Agent</span>
            </div>
            <button type="button" className="button-secondary" onClick={() => setLlmPanelOpen(false)}>
              收起
            </button>
          </div>

          <div className="writing-floating-panel__body">
            <AgentWritingAssistantPanel
              messages={writingAgentMessages}
              draft={writingAgentDraft}
              busy={writingAgentBusy}
              streamStatus={writingAgentStreamStatus}
              sessionId={writingAgentSessionId}
              documentLabel={effectiveDocumentId == null ? '未保存草稿' : `doc ${effectiveDocumentId} · v${documentDetailQuery.data?.version || '-'}`}
              selectionText={selectionText}
              selectionLine={selectionState?.line || null}
              actions={writingAgentToolActions}
              workbenchTools={writingAgentWorkbenchTools}
              onDraftChange={setWritingAgentDraft}
              onSend={(message) => void runWritingAgentCommand(message)}
              onRunAction={(action) => void runWritingAgentCommand(action.prompt)}
            />
          </div>
          {isDesktopFloating ? (
            <>
              <div className="writing-resize-handle writing-resize-handle--w" onMouseDown={handleLlmPanelResizeStart('w')} />
              <div className="writing-resize-handle writing-resize-handle--s" onMouseDown={handleLlmPanelResizeStart('s')} />
              <div className="writing-resize-handle writing-resize-handle--sw" onMouseDown={handleLlmPanelResizeStart('sw')} />
            </>
          ) : null}
        </aside>

        {agentUpdatesPanelOpen ? (
          <aside className="writing-agent-updates-panel" aria-label="Agent 更新" data-testid="writing-agent-updates-panel">
            <div className="writing-agent-updates-panel__header">
              <div>
                <span className="chip chip-ok">Agent 更新</span>
                <p className="writing-panel-subtitle">
                  {agentUpdates.length ? `当前文档 ${agentUpdates.length} 条` : '当前文档暂无 Agent 写回记录'}
                </p>
              </div>
              <div className="writing-agent-updates-panel__actions">
                <button type="button" className="button-secondary" onClick={() => void handleRefreshWritingState()}>
                  刷新
                </button>
                <button type="button" className="button-secondary" onClick={() => setAgentUpdatesPanelOpen(false)}>
                  收起
                </button>
              </div>
            </div>

            <div className="writing-agent-update-list">
              {agentUpdates.map((update, index) => {
                const provenanceKeys = Object.keys(update.provenance).slice(0, 4)
                return (
                  <article key={`${update.id}-${update.callId || 'call'}-${index}`} className="writing-agent-update-card" data-testid="writing-agent-update-card">
	                    <div className="writing-agent-update-card__head">
	                      <span className="chip chip-warn">{update.operation}</span>
	                      <span className={update.reviewStatus === 'accepted' ? 'chip chip-ok' : update.reviewStatus === 'rejected' ? 'chip chip-danger' : 'chip'}>
	                        {update.reviewStatus === 'accepted' ? '已采纳' : update.reviewStatus === 'rejected' ? '已撤回' : '待处理'}
	                      </span>
	                      <span className="writing-score">{formatUpdatedAt(update.createdAt)}</span>
	                    </div>
                    <strong>{update.summary || update.locator.anchorText || update.callId || update.id}</strong>
                    {update.locator.anchorText ? <p>{update.locator.anchorText}</p> : null}
                    <div className="writing-agent-update-card__meta">
                      {update.locator.anchorLine ? <span>line {update.locator.anchorLine}</span> : null}
                      {update.newVersion ? <span>v{update.newVersion}</span> : null}
                      {update.sourceRefs.length ? <span>{update.sourceRefs.length} refs</span> : null}
                      {provenanceKeys.length ? <span>{provenanceKeys.join(', ')}</span> : null}
                    </div>
	                    <div className="writing-agent-update-card__actions">
	                      <button type="button" className="button-primary" data-testid="writing-agent-update-locate" onClick={() => handleLocateAgentUpdate(update)}>
	                        定位
	                      </button>
	                      <button type="button" className="button-secondary" data-testid="writing-agent-update-accept" onClick={() => handleAcceptAgentUpdate(update)}>
	                        采纳
	                      </button>
	                      <button type="button" className="button-secondary" data-testid="writing-agent-update-reject" onClick={() => handleRejectAgentUpdate(update)}>
	                        撤回
	                      </button>
                      <button
                        type="button"
                        className="button-secondary"
                        data-testid="writing-agent-update-diff"
                        onClick={() => setExpandedAgentUpdateId((current) => (current === update.id ? null : update.id))}
                      >
                        差异
                      </button>
                      {update.insertedTextTruncated ? <span className="writing-score">正文片段已截断</span> : null}
                      {update.replacedTextTruncated ? <span className="writing-score">原选区已截断</span> : null}
	                    </div>
                    {expandedAgentUpdateId === update.id ? (
                      <div className="writing-agent-update-diff" data-testid="writing-agent-update-diff-panel">
                        {update.replacedText ? (
                          <div className="writing-agent-update-diff__pane">
                            <small>原选区</small>
                            <strong>rollback source</strong>
                            <pre>{update.replacedText}</pre>
                          </div>
                        ) : null}
                        <div className="writing-agent-update-diff__pane">
                          <small>定位</small>
                          <strong>{agentUpdateVersionLabel(update)}</strong>
                          <p>{update.locator.anchorHeading || update.locator.anchorId || '未提供标题定位'}</p>
                          {update.locator.anchorLine ? <span>line {update.locator.anchorLine}</span> : null}
                        </div>
                        <div className="writing-agent-update-diff__pane is-added">
                          <small>Agent 写入</small>
                          <strong>{update.operation}</strong>
                          <pre>{previewAgentUpdateText(update)}</pre>
                        </div>
                        <div className="writing-agent-update-diff__meta">
                          {update.sourceRefs.length ? <span>refs: {update.sourceRefs.slice(0, 3).join(', ')}</span> : null}
                          {provenanceKeys.length ? <span>provenance: {provenanceKeys.join(', ')}</span> : null}
                          {update.callId ? <span>call: {update.callId}</span> : null}
                        </div>
                      </div>
                    ) : null}
                  </article>
                )
              })}
              {!agentUpdates.length ? (
                <div className="empty-cell">AgentCore 写回后会在这里显示 provenance 和定位入口。</div>
              ) : null}
            </div>
          </aside>
        ) : null}

        <main className={`writing-canvas-stage is-${viewMode}`} data-testid="writing-canvas-stage">
          {(viewMode === 'write' || viewMode === 'split') ? (
            <section className="writing-canvas-pane writing-canvas-pane--editor" data-testid="writing-editor-pane">
              <div className={`writing-editor-collab${agentUpdateAnchors.length ? ' has-agent-anchors' : ''}`}>
                <MarkdownEditor
                  value={markdown}
                  autosaveLabel={
                    saveDocumentMutation.isPending
                      ? 'saving...'
                      : effectiveDocumentId == null
                        ? 'new draft'
                        : autosaveMessage
                  }
                  onChange={(nextMarkdown) =>
                    setDraftByKey((prev) => ({
                      ...prev,
                      [draftKey]: { title, markdown: nextMarkdown },
                    }))
                  }
                  onSelectionChange={handleSelectionTextChange}
                />
                {agentUpdateAnchors.length ? (
                  <aside className="writing-agent-collab-rail" aria-label="Agent 段落协作" data-testid="writing-agent-collab-rail">
                    <div className="writing-agent-collab-rail__header">
                      <span className="chip chip-ok">Agent 段落</span>
                      <span className="writing-score">{agentUpdateAnchors.length}</span>
                    </div>
                    <div className="writing-agent-collab-rail__list">
                      {agentUpdateAnchors.map(({ update, lineStart, lineEnd, range, preview }, index) => {
                        const lineLabel =
                          lineStart && lineEnd && lineEnd !== lineStart
                            ? `L${lineStart}-${lineEnd}`
                            : lineStart
                              ? `L${lineStart}`
                              : '未定位'
                        return (
                          <article
                            key={`rail-${update.id}-${update.callId || 'call'}-${index}`}
                            className={`writing-agent-anchor-card is-${update.reviewStatus}${range ? '' : ' is-unresolved'}`}
                            data-testid="writing-agent-anchor-card"
                          >
                            <div className="writing-agent-anchor-card__head">
                              <span className="chip chip-warn">{lineLabel}</span>
                              <span className={update.reviewStatus === 'accepted' ? 'chip chip-ok' : update.reviewStatus === 'rejected' ? 'chip chip-danger' : 'chip'}>
                                {update.reviewStatus === 'accepted' ? '已采纳' : update.reviewStatus === 'rejected' ? '已撤回' : '待处理'}
                              </span>
                            </div>
                            <strong>{update.summary || update.operation || update.id}</strong>
                            <p>{preview}</p>
                            <div className="writing-agent-anchor-card__meta">
                              {update.sourceRefs.length ? <span>{update.sourceRefs.length} refs</span> : null}
                              {update.callId ? <span>{update.callId}</span> : null}
                            </div>
                            <div className="writing-agent-anchor-card__actions">
                              <button type="button" className="button-primary" data-testid="writing-agent-anchor-locate" onClick={() => handleLocateAgentUpdate(update)}>
                                定位
                              </button>
                              <button type="button" className="button-secondary" data-testid="writing-agent-anchor-accept" onClick={() => handleAcceptAgentUpdate(update)}>
                                采纳
                              </button>
                              <button type="button" className="button-secondary" data-testid="writing-agent-anchor-reject" onClick={() => handleRejectAgentUpdate(update)}>
                                撤回
                              </button>
                              <button
                                type="button"
                                className="button-secondary"
                                data-testid="writing-agent-anchor-diff"
                                onClick={() => {
                                  setAgentUpdatesPanelOpen(true)
                                  setExpandedAgentUpdateId((current) => (current === update.id ? null : update.id))
                                }}
                              >
                                差异
                              </button>
                            </div>
                          </article>
                        )
                      })}
                    </div>
                  </aside>
                ) : null}
              </div>
            </section>
          ) : null}

          {(viewMode === 'preview' || viewMode === 'split') ? (
            <section className="writing-canvas-pane writing-canvas-pane--preview" data-testid="writing-preview-pane">
              <MarkdownPreview markdown={`# ${title}\n\n${markdown}`} />
            </section>
          ) : null}
        </main>

        {citationTrayVisible && <CitationBasket
          containerRef={citationTrayRef}
          dockEdge={citationTrayPosition.edge}
          style={citationTrayStyle}
          citations={citationsQuery.data || []}
          collapsed={citationTrayCollapsed}
          dragActive={citationTrayDragOver}
          onMouseDown={() => activateFloatingWindow('citations')}
          onToggleCollapsed={toggleCitationTray}
          onHeaderMouseDown={handleCitationTrayDragStart}
          onOpenCitation={handleOpenCitationCard}
          onDropCard={handleDropCardToCitationTray}
          onDragEnter={() => setCitationTrayDragOver(true)}
          onDragLeave={() => setCitationTrayDragOver(false)}
          onRemoveCitation={(citationId) => {
            if (citationId == null || effectiveDocumentId == null) return
            const nextItems = (citationsQuery.data || []).filter((item) => item.id !== citationId)
            void upsertWritingCitations(effectiveDocumentId, nextItems).then(async () => {
              await queryClient.invalidateQueries({ queryKey: queryKeys.writing.citations(projectKey, effectiveDocumentId) })
            })
          }}
        />}

        {pinnedCardsWithDetail.map((item, index) => {
          const resolvedPinnedAnchor = resolveInsightCardAnchor(item.anchor, viewport)
          return (
            <div key={item.cardId}>
              <WritingInsightCard
                preview={item.preview}
                detail={item.detail}
                loading={item.loading}
                pinned
                style={buildInsightCardStyle(resolvedPinnedAnchor, 90 + index)}
                onClose={() => removePinnedInsightCard(item.cardId)}
                onHeadMouseDown={handlePinnedInsightCardDragStart(item.cardId)}
                onAddCitation={(cardId) =>
                  citationsMutation.mutate({
                    cardId,
                    previewOverride: item.preview,
                    source: { kind: 'pinned', pinnedCardId: item.cardId },
                  })
                }
                onTogglePin={() => removePinnedInsightCard(item.cardId)}
                onDragCardStart={() => setCitationTrayDragOver(true)}
                onDragCardEnd={() => setCitationTrayDragOver(false)}
              />
              {isDesktopFloating ? (
                <>
                  <div
                    className="writing-resize-handle writing-resize-handle--card-n"
                    style={{
                      left: Math.round(resolvedPinnedAnchor.left + 12),
                      top: Math.round(resolvedPinnedAnchor.top - 10),
                      width: Math.max(80, resolvedPinnedAnchor.width - 24),
                    }}
                    onMouseDown={handlePinnedInsightCardResizeStart(item.cardId, 'n')}
                  />
                  <div
                    className="writing-resize-handle writing-resize-handle--card-e"
                    style={{
                      left: Math.round(resolvedPinnedAnchor.left + resolvedPinnedAnchor.width - 10),
                      top: Math.round(resolvedPinnedAnchor.top + 12),
                      height: Math.max(56, resolvedPinnedAnchor.height - 24),
                    }}
                    onMouseDown={handlePinnedInsightCardResizeStart(item.cardId, 'e')}
                  />
                  <div
                    className="writing-resize-handle writing-resize-handle--card-w"
                    style={{
                      left: Math.round(resolvedPinnedAnchor.left - 10),
                      top: Math.round(resolvedPinnedAnchor.top + 12),
                      height: Math.max(56, resolvedPinnedAnchor.height - 24),
                    }}
                    onMouseDown={handlePinnedInsightCardResizeStart(item.cardId, 'w')}
                  />
                  <div
                    className="writing-resize-handle writing-resize-handle--card-s"
                    style={{
                      left: Math.round(resolvedPinnedAnchor.left + 12),
                      top: Math.round(resolvedPinnedAnchor.top + resolvedPinnedAnchor.height - 10),
                      width: Math.max(80, resolvedPinnedAnchor.width - 24),
                    }}
                    onMouseDown={handlePinnedInsightCardResizeStart(item.cardId, 's')}
                  />
                  <div
                    className="writing-resize-handle writing-resize-handle--card-ne"
                    style={{
                      left: Math.round(resolvedPinnedAnchor.left + resolvedPinnedAnchor.width - 12),
                      top: Math.round(resolvedPinnedAnchor.top - 12),
                    }}
                    onMouseDown={handlePinnedInsightCardResizeStart(item.cardId, 'ne')}
                  />
                  <div
                    className="writing-resize-handle writing-resize-handle--card-nw"
                    style={{
                      left: Math.round(resolvedPinnedAnchor.left - 12),
                      top: Math.round(resolvedPinnedAnchor.top - 12),
                    }}
                    onMouseDown={handlePinnedInsightCardResizeStart(item.cardId, 'nw')}
                  />
                  <div
                    className="writing-resize-handle writing-resize-handle--card-se"
                    style={{
                      left: Math.round(resolvedPinnedAnchor.left + resolvedPinnedAnchor.width - 12),
                      top: Math.round(resolvedPinnedAnchor.top + resolvedPinnedAnchor.height - 12),
                    }}
                    onMouseDown={handlePinnedInsightCardResizeStart(item.cardId, 'se')}
                  />
                  <div
                    className="writing-resize-handle writing-resize-handle--card-sw"
                    style={{
                      left: Math.round(resolvedPinnedAnchor.left - 12),
                      top: Math.round(resolvedPinnedAnchor.top + resolvedPinnedAnchor.height - 12),
                    }}
                    onMouseDown={handlePinnedInsightCardResizeStart(item.cardId, 'sw')}
                  />
                </>
              ) : null}
            </div>
          )
        })}

        {effectiveSelectedCardId ? (
          <>
            <WritingInsightCard
              preview={resolvedSelectedPreview}
              detail={selectedDetailQuery.data || null}
              loading={selectedPreviewQuery.isLoading || selectedDetailQuery.isLoading}
              pinned={false}
              style={insightCardStyle}
              onClose={dismissInsightCard}
              onHeadMouseDown={handleInsightCardDragStart}
              onAddCitation={(cardId) =>
                citationsMutation.mutate({
                  cardId,
                  previewOverride: resolvedSelectedPreview,
                  source: { kind: 'selected' },
                })
              }
              onTogglePin={pinSelectedInsightCard}
              onDragCardStart={() => setCitationTrayDragOver(true)}
              onDragCardEnd={() => setCitationTrayDragOver(false)}
            />
            {isDesktopFloating ? (
              <>
                <div
                  className="writing-resize-handle writing-resize-handle--card-n"
                  style={{
                    left: Math.round(resolvedInsightCardAnchor.left + 12),
                    top: Math.round(resolvedInsightCardAnchor.top - 10),
                    width: Math.max(80, resolvedInsightCardAnchor.width - 24),
                  }}
                  onMouseDown={handleInsightCardResizeStart('n')}
                />
                <div
                  className="writing-resize-handle writing-resize-handle--card-e"
                  style={{
                    left: Math.round(resolvedInsightCardAnchor.left + resolvedInsightCardAnchor.width - 10),
                    top: Math.round(resolvedInsightCardAnchor.top + 12),
                    height: Math.max(56, resolvedInsightCardAnchor.height - 24),
                  }}
                  onMouseDown={handleInsightCardResizeStart('e')}
                />
                <div
                  className="writing-resize-handle writing-resize-handle--card-w"
                  style={{
                    left: Math.round(resolvedInsightCardAnchor.left - 10),
                    top: Math.round(resolvedInsightCardAnchor.top + 12),
                    height: Math.max(56, resolvedInsightCardAnchor.height - 24),
                  }}
                  onMouseDown={handleInsightCardResizeStart('w')}
                />
                <div
                  className="writing-resize-handle writing-resize-handle--card-s"
                  style={{
                    left: Math.round(resolvedInsightCardAnchor.left + 12),
                    top: Math.round(resolvedInsightCardAnchor.top + resolvedInsightCardAnchor.height - 10),
                    width: Math.max(80, resolvedInsightCardAnchor.width - 24),
                  }}
                  onMouseDown={handleInsightCardResizeStart('s')}
                />
                <div
                  className="writing-resize-handle writing-resize-handle--card-ne"
                  style={{
                    left: Math.round(resolvedInsightCardAnchor.left + resolvedInsightCardAnchor.width - 12),
                    top: Math.round(resolvedInsightCardAnchor.top - 12),
                  }}
                  onMouseDown={handleInsightCardResizeStart('ne')}
                />
                <div
                  className="writing-resize-handle writing-resize-handle--card-nw"
                  style={{
                    left: Math.round(resolvedInsightCardAnchor.left - 12),
                    top: Math.round(resolvedInsightCardAnchor.top - 12),
                  }}
                  onMouseDown={handleInsightCardResizeStart('nw')}
                />
                <div
                  className="writing-resize-handle writing-resize-handle--card-se"
                  style={{
                    left: Math.round(resolvedInsightCardAnchor.left + resolvedInsightCardAnchor.width - 12),
                    top: Math.round(resolvedInsightCardAnchor.top + resolvedInsightCardAnchor.height - 12),
                  }}
                  onMouseDown={handleInsightCardResizeStart('se')}
                />
                <div
                  className="writing-resize-handle writing-resize-handle--card-sw"
                  style={{
                    left: Math.round(resolvedInsightCardAnchor.left - 12),
                    top: Math.round(resolvedInsightCardAnchor.top + resolvedInsightCardAnchor.height - 12),
                  }}
                  onMouseDown={handleInsightCardResizeStart('sw')}
                />
              </>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  )
}

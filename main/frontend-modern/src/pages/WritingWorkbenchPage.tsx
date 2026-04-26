import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { hashByMode } from '../app/navigation'
import CitationBasket from '../components/writing/CitationBasket'
import { toDraggedCardPreview, type WritingDraggedCardPayload } from '../components/writing/dragPayload'
import KeywordInsightSidebar from '../components/writing/KeywordInsightSidebar'
import LlmAssistantPanel from '../components/writing/LlmAssistantPanel'
import MarkdownEditor from '../components/writing/MarkdownEditor'
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
  getWritingLlmActionDetail,
  getWritingSuggest,
  listWritingCitations,
  listWritingDocuments,
  listWritingLlmActionHistory,
  listWritingTemplates,
  previewWritingKeywordCard,
  runWritingLlmAction,
  updateWritingDocument,
  upsertWritingCitations,
  validateWritingTemplate,
  type WritingKeywordCard,
  type WritingKeywordCardPreview,
  type WritingCitation,
  type WritingLlmActionId,
  type WritingTemplateValidation,
} from '../lib/api'
import { queryKeys } from '../lib/queryKeys'

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
type CitationMutationSource =
  | { kind: 'selected' }
  | { kind: 'pinned'; pinnedCardId: string }
  | { kind: 'external' }

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
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null)
  const [isCreatingDraft, setIsCreatingDraft] = useState(false)
  const [draftByKey, setDraftByKey] = useState<Record<string, { title: string; markdown: string }>>({})
  const [selectionText, setSelectionText] = useState('')
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null)
  const [pinnedInsightCards, setPinnedInsightCards] = useState<PinnedInsightCard[]>([])
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [templateValidation, setTemplateValidation] = useState<WritingTemplateValidation | null>(null)
  const [llmOutput, setLlmOutput] = useState('')
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
  const [insightCardAnchor, setInsightCardAnchor] = useState<InsightCardAnchor | null>(null)
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
  })
  const effectiveDocumentId = isCreatingDraft ? null : activeDocumentId ?? documentsQuery.data?.[0]?.id ?? null
  const documentDetailQuery = useQuery({
    queryKey: queryKeys.writing.documentDetail(projectKey, effectiveDocumentId),
    queryFn: () => getWritingDocument(effectiveDocumentId as number),
    enabled: effectiveDocumentId != null,
  })
  const citationsQuery = useQuery({
    queryKey: queryKeys.writing.citations(projectKey, effectiveDocumentId),
    queryFn: () => listWritingCitations(effectiveDocumentId as number),
    enabled: effectiveDocumentId != null,
  })
  const templatesQuery = useQuery({
    queryKey: queryKeys.writing.templates(projectKey),
    queryFn: () => listWritingTemplates(),
  })
  const llmHistoryQuery = useQuery({
    queryKey: queryKeys.writing.llmHistory(projectKey),
    queryFn: () => listWritingLlmActionHistory(),
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

  const resetContextPanels = () => {
    dismissInsightCard()
    setPinnedInsightCards([])
    setSelectedJobId(null)
    setSelectionText('')
    setTemplateValidation(null)
    setLlmOutput('')
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

  const llmActionMutation = useMutation({
    mutationFn: (actionId: WritingLlmActionId) =>
      runWritingLlmAction({
        action_id: actionId,
        document_id: effectiveDocumentId == null ? undefined : String(effectiveDocumentId),
        input_markdown: markdown,
        selection_text: selectionText || undefined,
      }),
    onSuccess: async (result) => {
      setLlmOutput(result.content || '')
      setLlmPanelOpen(true)
      activateFloatingWindow('llm')
      dismissInsightCard()
      await queryClient.invalidateQueries({ queryKey: queryKeys.writing.llmHistory(projectKey) })
    },
  })

  const selectionLookup = useSelectionLookup({
    selectionText,
    enabled: viewMode !== 'preview',
    lookup: async (nextSelection, selectionHash) => {
      const [cardsResult, suggestResult] = await Promise.all([
        getWritingKeywordCards({
          query: nextSelection,
          selection_hash: selectionHash,
          sources: ['document', 'resource', 'graph'],
        }),
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
  const effectiveSelectedJobId = selectedJobId ?? llmHistoryQuery.data?.[0]?.job_id ?? null
  const selectedPreview: WritingKeywordCardPreview | null =
    (visibleCards.find((item) => item.card_id === effectiveSelectedCardId) as WritingKeywordCard | undefined) || null

  const pinnedDetailQueries = useQueries({
    queries: pinnedInsightCards.map((item) => ({
      queryKey: queryKeys.writing.keywordCardDetail(projectKey, item.cardId),
      queryFn: () => getWritingCardDetail(item.cardId, { include_provenance: true, max_provenance_items: 12 }),
      enabled: true,
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
    enabled: Boolean(effectiveSelectedCardId),
  })
  const resolvedSelectedPreview =
    selectedPreview ||
    selectedPreviewQuery.data ||
    (effectiveSelectedCardId ? citationPreviewByCardId.get(effectiveSelectedCardId) || null : null)
  const selectedDetailQuery = useQuery({
    queryKey: queryKeys.writing.keywordCardDetail(projectKey, effectiveSelectedCardId || '__none__'),
    queryFn: () => getWritingCardDetail(effectiveSelectedCardId as string, { include_provenance: true, max_provenance_items: 12 }),
    enabled: Boolean(effectiveSelectedCardId),
  })
  const selectedLlmDetailQuery = useQuery({
    queryKey: queryKeys.writing.llmDetail(projectKey, effectiveSelectedJobId),
    queryFn: () => getWritingLlmActionDetail(effectiveSelectedJobId as number),
    enabled: effectiveSelectedJobId != null,
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

  const handleSelectionTextChange = (nextSelectionText: string) => {
    setSelectionText(nextSelectionText)
    setSelectedCardId(null)
    if (!nextSelectionText.trim()) return
    setInsightsPanelOpen(true)
    activateFloatingWindow('insights')
  }

  return (
    <div className={`writing-workbench-page${standalone ? ' is-standalone' : ''}`}>
      <div className="writing-canvas-shell">
        <div className="writing-floating-toolbar">
          <div className="writing-toolbar-cluster writing-toolbar-cluster--title">
            {standalone ? (
              <button type="button" className="button-secondary" onClick={handleBackToWorkspace}>
                返
              </button>
            ) : null}
            <input
              className="writing-title-input"
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
            <button type="button" className={panelButtonClass(documentsPanelOpen)} onClick={toggleDocumentsPanel}>
              文档
            </button>
            <button type="button" className={panelButtonClass(templatesPanelOpen)} onClick={toggleTemplatesPanel}>
              模板
            </button>
            <button type="button" className={panelButtonClass(insightsPanelOpen)} onClick={toggleInsightsPanel}>
              资料
            </button>
            <button type="button" className={panelButtonClass(citationTrayVisible)} onClick={() => { activateFloatingWindow('citations'); setCitationTrayVisible((prev) => !prev) }}>
              引用
            </button>
            <button type="button" className={panelButtonClass(llmPanelOpen)} onClick={toggleLlmPanel}>
              AI
            </button>
          </div>

          <div className="writing-toolbar-cluster writing-toolbar-cluster--actions">
            <button type="button" className={panelButtonClass(viewMode === 'write')} onClick={() => setViewMode('write')}>
              写
            </button>
            <button type="button" className={panelButtonClass(viewMode === 'preview')} onClick={() => setViewMode('preview')}>
              预
            </button>
            <button type="button" className={panelButtonClass(viewMode === 'split')} onClick={() => setViewMode('split')}>
              分
            </button>
            <button type="button" className="button-secondary" onClick={startNewDraft}>
              新建
            </button>
            <button type="button" className="button-primary" onClick={() => saveDocumentMutation.mutate()} disabled={saveDocumentMutation.isPending}>
              保存
            </button>
            <button type="button" className="button-secondary" onClick={() => void handleExportMarkdown()} disabled={effectiveDocumentId == null || isDirty}>
              导出
            </button>
          </div>
          <div className="writing-toolbar-cluster writing-toolbar-cluster--meta">
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
                    onClick={() => handleSelectDocument(item.id)}
                  >
                    <div className="writing-list-card__header">
                      <strong>{item.title}</strong>
                      <span className={`chip ${item.active ? 'chip-ok' : 'chip-warn'}`}>{item.status}</span>
                    </div>
                    <div className="writing-list-card__footer">
                      <span className="text-muted">{item.updatedAt}</span>
                      {item.active ? <span className="chip chip-ok">当前</span> : null}
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
            <span className="writing-floating-drag-handle" onMouseDown={handleLlmPanelDragStart} aria-label="拖动 AI 面板" />
            <div className="writing-floating-panel__tabs">
              <span className="chip chip-warn">AI</span>
            </div>
            <button type="button" className="button-secondary" onClick={() => setLlmPanelOpen(false)}>
              收起
            </button>
          </div>

          <div className="writing-floating-panel__body">
            <LlmAssistantPanel
              history={llmHistoryQuery.data || []}
              selectedJobId={effectiveSelectedJobId}
              detail={selectedLlmDetailQuery.data || null}
              busy={llmActionMutation.isPending}
              generatedContent={llmOutput}
              onRunAction={(actionId) => llmActionMutation.mutate(actionId)}
              onSelectHistory={setSelectedJobId}
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

        <main className={`writing-canvas-stage is-${viewMode}`}>
          {(viewMode === 'write' || viewMode === 'split') ? (
            <section className="writing-canvas-pane writing-canvas-pane--editor">
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
            </section>
          ) : null}

          {(viewMode === 'preview' || viewMode === 'split') ? (
            <section className="writing-canvas-pane writing-canvas-pane--preview">
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

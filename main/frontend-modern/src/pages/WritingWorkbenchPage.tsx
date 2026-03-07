import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import CitationBasket from '../components/writing/CitationBasket'
import KeywordInsightSidebar from '../components/writing/KeywordInsightSidebar'
import LlmAssistantPanel from '../components/writing/LlmAssistantPanel'
import MarkdownEditor from '../components/writing/MarkdownEditor'
import MarkdownPreview from '../components/writing/MarkdownPreview'
import TemplateLibraryPanel from '../components/writing/TemplateLibraryPanel'
import WritingShell, { type WritingShellViewMode } from '../components/writing/WritingShell'
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
  type WritingKeywordCardPreview,
  type WritingLlmActionId,
  type WritingTemplateValidation,
} from '../lib/api'
import { queryKeys } from '../lib/queryKeys'

export type WritingWorkbenchPageProps = {
  projectKey: string
}

const EMPTY_MARKDOWN = `# 内置写作工作台

## 目标

- 一边写 Markdown，一边预览
- 划词后在右侧调出相关资料卡片
- 优先基于模板和资料写，不重复造轮子
`

function formatUpdatedAt(value?: string | null) {
  if (!value) return 'new'
  return value.replace('T', ' ').slice(0, 16)
}

export default function WritingWorkbenchPage({ projectKey }: WritingWorkbenchPageProps) {
  const queryClient = useQueryClient()
  const [viewMode, setViewMode] = useState<WritingShellViewMode>('split')
  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null)
  const [isCreatingDraft, setIsCreatingDraft] = useState(false)
  const [draftByKey, setDraftByKey] = useState<Record<string, { title: string; markdown: string }>>({})
  const [selectionText, setSelectionText] = useState('')
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null)
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [templateValidation, setTemplateValidation] = useState<WritingTemplateValidation | null>(null)
  const [llmOutput, setLlmOutput] = useState('')
  const [autosaveMessage, setAutosaveMessage] = useState('idle')
  const [saveMessage, setSaveMessage] = useState('')
  const [exportMessage, setExportMessage] = useState('')

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
  const persistedTitle = documentDetailQuery.data?.title || '内置写作工作台'
  const persistedMarkdown = documentDetailQuery.data?.body_md || EMPTY_MARKDOWN
  const currentDraft = draftByKey[draftKey]
  const title = currentDraft?.title ?? persistedTitle
  const markdown = currentDraft?.markdown ?? persistedMarkdown
  const isDirty =
    effectiveDocumentId == null
      ? title.trim().length > 0 || markdown.trim().length > 0
      : title !== persistedTitle || markdown !== persistedMarkdown

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
  const effectiveSelectedCardId = selectedCardId ?? selectionLookup.data?.cards?.[0]?.card_id ?? null
  const effectiveSelectedJobId = selectedJobId ?? llmHistoryQuery.data?.[0]?.job_id ?? null

  const citationsMutation = useMutation({
    mutationFn: async (cardId: string) => {
      if (effectiveDocumentId == null) return null
      const nextItems = [
        ...(citationsQuery.data || []),
        {
          card_id: cardId,
          source_title: selectedPreview?.title || cardId,
          source_uri: selectedPreview?.url || null,
          quote_text: selectedPreview?.snippet || selectionText || '',
          position_anchor: selectionLookup.selectionHash || 'selection',
        },
      ]
      return upsertWritingCitations(effectiveDocumentId, nextItems)
    },
    onSuccess: async () => {
      if (effectiveDocumentId == null) return
      await queryClient.invalidateQueries({ queryKey: queryKeys.writing.citations(projectKey, effectiveDocumentId) })
    },
  })

  const selectedPreviewQuery = useQuery({
    queryKey: queryKeys.writing.keywordCardPreview(projectKey, effectiveSelectedCardId || '__none__'),
    queryFn: () => previewWritingKeywordCard({ card_id: effectiveSelectedCardId as string, query: selectionText || undefined }),
    enabled: Boolean(effectiveSelectedCardId),
  })
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
  const selectedPreview: WritingKeywordCardPreview | null = selectedPreviewQuery.data || null

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
    isCreatingDraft,
    isDirty,
    markdown,
    saveDocumentMutation.isPending,
    selectionLookup.selectionHash,
    selectionText,
  ])

  const documentSummaries = useMemo(
    () =>
      (documentsQuery.data || []).map((item) => ({
        id: String(item.id),
        title: item.title,
        status: item.status,
        updatedAt: formatUpdatedAt(item.updated_at),
        active: item.id === effectiveDocumentId,
      })),
    [documentsQuery.data, effectiveDocumentId],
  )

  const templateSummaries = useMemo(
    () =>
      (templatesQuery.data || []).map((item) => ({
        id: item.template_key,
        label: item.label,
        description: item.description || item.template_key,
      })),
    [templatesQuery.data],
  )

  const insightSummaries = useMemo(
    () =>
      (selectionLookup.data?.cards || []).slice(0, 3).map((item) => ({
        id: item.card_id,
        title: item.title,
        subtitle: item.snippet || item.publisher || '资料卡',
        tag: item.source_type,
      })),
    [selectionLookup.data?.cards],
  )

  const activitySummaries = useMemo(
    () =>
      (llmHistoryQuery.data || []).slice(0, 3).map((item) => ({
        id: String(item.job_id),
        label: item.action_id || item.job_type,
        meta: `${item.status} · ${item.created_at || 'pending'}`,
      })),
    [llmHistoryQuery.data],
  )

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
    setSelectedCardId(null)
    setSelectionText('')
    setTemplateValidation(null)
    setLlmOutput('')
    setSaveMessage('')
    setExportMessage('')
    setAutosaveMessage('new draft')
    setDraftByKey((prev) => ({
      ...prev,
      __new__: {
        title: '未命名报告',
        markdown: EMPTY_MARKDOWN,
      },
    }))
  }

  return (
    <WritingShell
      projectKey={projectKey}
      title="写作工作台"
      subtitle="Markdown 编辑、预览、资料卡、模板和 LLM 动作都收拢在同一工作台里。"
      viewMode={viewMode}
      onViewModeChange={setViewMode}
      documents={documentSummaries}
      templates={templateSummaries}
      insights={insightSummaries}
      activity={activitySummaries}
      onSelectDocument={(documentId) => {
        setIsCreatingDraft(false)
        setActiveDocumentId(Number(documentId))
        setSaveMessage('')
        setExportMessage('')
      }}
      onSelectTemplate={(templateId) => {
        const template = templatesQuery.data?.find((item) => item.template_key === templateId)
        if (!template) return
        setDraftByKey((prev) => ({
          ...prev,
          [draftKey]: { title, markdown: template.template_content },
        }))
        setTemplateValidation(null)
      }}
      editorSlot={
        <div className="writing-editor-stack">
          <div className="inline-actions">
            <button type="button" className="button-secondary" onClick={startNewDraft}>
              新建文档
            </button>
            <button type="button" className="button-primary" onClick={() => saveDocumentMutation.mutate()} disabled={saveDocumentMutation.isPending}>
              {effectiveDocumentId == null ? '创建文档' : '保存正文'}
            </button>
            <button type="button" className="button-secondary" onClick={() => void handleExportMarkdown()} disabled={effectiveDocumentId == null || isDirty}>
              导出 Markdown
            </button>
          </div>
          <div className="inline-actions">
            <span className="chip chip-ok">{effectiveDocumentId == null ? '新草稿' : `doc:${effectiveDocumentId}`}</span>
            <span className="text-muted">{autosaveMessage}</span>
            {saveMessage ? <span className="text-muted">{saveMessage}</span> : null}
            {exportMessage ? <span className="text-muted">{exportMessage}</span> : null}
          </div>
          <label>
            <span>标题</span>
            <input
              value={title}
              onChange={(event) =>
                setDraftByKey((prev) => ({
                  ...prev,
                  [draftKey]: { title: event.target.value, markdown },
                }))
              }
              placeholder="Untitled report"
            />
          </label>
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
            onSelectionChange={setSelectionText}
          />
        </div>
      }
      previewSlot={<MarkdownPreview markdown={`# ${title}\n\n${markdown}`} />}
      rightSidebarSlot={
        <div className="writing-right-column">
          <KeywordInsightSidebar
            cards={selectionLookup.data?.cards || []}
            preview={selectedPreview}
            detail={selectedDetailQuery.data || null}
            suggestItems={selectionLookup.data?.suggestItems || []}
            selectionText={selectionText}
            selectedCardId={effectiveSelectedCardId}
            loading={selectionLookup.status === 'loading' || selectedPreviewQuery.isLoading || selectedDetailQuery.isLoading}
            error={selectionLookup.error}
            onSelectCard={setSelectedCardId}
            onAddCitation={(cardId) => citationsMutation.mutate(cardId)}
            onUseSuggestion={setSelectionText}
          />
          <CitationBasket
            citations={citationsQuery.data || []}
            onRemoveCitation={(citationId) => {
              if (citationId == null || effectiveDocumentId == null) return
              const nextItems = (citationsQuery.data || []).filter((item) => item.id !== citationId)
              void upsertWritingCitations(effectiveDocumentId, nextItems).then(async () => {
                await queryClient.invalidateQueries({ queryKey: queryKeys.writing.citations(projectKey, effectiveDocumentId) })
              })
            }}
          />
          <TemplateLibraryPanel
            templates={templatesQuery.data || []}
            validation={templateValidation}
            validating={validateTemplateMutation.isPending}
            onValidateTemplate={(templateKey) => validateTemplateMutation.mutate(templateKey)}
            onApplyTemplate={(templateKey) => {
              const template = templatesQuery.data?.find((item) => item.template_key === templateKey)
              if (!template) return
              setDraftByKey((prev) => ({
                ...prev,
                [draftKey]: { title, markdown: template.template_content },
              }))
            }}
          />
          <LlmAssistantPanel
            history={llmHistoryQuery.data || []}
            selectedJobId={effectiveSelectedJobId}
            detail={selectedLlmDetailQuery.data || null}
            busy={llmActionMutation.isPending}
            generatedContent={llmOutput}
            onRunAction={(actionId) => llmActionMutation.mutate(actionId)}
            onSelectHistory={setSelectedJobId}
          />
          <div className="inline-actions">
            <button type="button" className="button-primary" onClick={() => saveDocumentMutation.mutate()} disabled={saveDocumentMutation.isPending}>
              保存正文
            </button>
            <button
              type="button"
              className="button-secondary"
              onClick={() => void handleExportMarkdown()}
              disabled={effectiveDocumentId == null || isDirty}
            >
              导出 Markdown
            </button>
            <button
              type="button"
              className="button-secondary"
              onClick={() => {
                if (!selectedCardId) return
                citationsMutation.mutate(selectedCardId)
              }}
              disabled={!selectedCardId || citationsMutation.isPending}
            >
              引用当前资料卡
            </button>
          </div>
          {exportMessage ? <p className="text-muted">{exportMessage}</p> : null}
        </div>
      }
    />
  )
}

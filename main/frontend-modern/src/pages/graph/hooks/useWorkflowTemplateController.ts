import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  activateWorkflowGraphTemplateVersion,
  applyWorkflowTemplateRollback,
  createWorkflowGraphTemplate,
  createWorkflowGraphTemplateVersion,
  deleteWorkflowGraphTemplate,
  diffWorkflowTemplate,
  getWorkflowGraphTemplateVersion,
  listWorkflowGraphTemplates,
  listWorkflowGraphTemplateVersions,
  listWorkflowTemplateVersions,
  previewWorkflowTemplateRollback,
  promoteWorkflowTemplate,
  runWorkflow,
  stageWorkflowTemplate,
  updateWorkflowGraphTemplate,
} from '../../../lib/api'
import type { GraphEdgeItem, GraphNodeItem, WorkflowRunResult, WorkflowTemplateDiffResponse, WorkflowTemplateRollbackResponse, WorkflowTemplateStageName, WorkflowTemplateStageRecord } from '../../../lib/types'
import type { MessageKey } from '../../../app/platform/i18n'
import type { GraphProjectionDefinition } from '../realizer/contract'
import {
  asTemplateRecord,
  asVersionRecord,
  buildTemplateRollbackTraceId,
  buildTemplateStageAuditSummary,
  buildWorkflowTemplatePayloadFromDraft,
  describeTemplateRollbackAudit,
  describeTemplateRollbackPlan,
  formatWorkflowRunScalar,
  isPlainRecord,
  normalizeWorkflowDryRunSteps,
  normalizeWorkflowTemplateStageRecords,
  parseTemplateRollbackVersion,
  summarizeWorkflowDryRunResult,
  type GraphTemplateRecord,
  type GraphTemplateVersionRecord,
  type TemplateStageAuditSummary,
} from '../realizer/workflowTemplate'

type GraphKind = GraphProjectionDefinition['graphKind']
type GraphMessageParams = Record<string, number | string>

type UseWorkflowTemplateControllerParams = {
  enabled: boolean
  projectKey: string
  graphKind: GraphKind
  draftNodes: GraphNodeItem[]
  draftEdges: GraphEdgeItem[]
  markDraftSaved: () => void
  replaceDraft: (nodes: GraphNodeItem[], edges: GraphEdgeItem[], options?: { markAsDirty?: boolean }) => void
  setGraphEditStatus: (status: string) => void
  translate: (key: MessageKey) => string
  formatMessage: (key: MessageKey, params: GraphMessageParams) => string
}

export function useWorkflowTemplateController({
  enabled,
  projectKey,
  graphKind,
  draftNodes,
  draftEdges,
  markDraftSaved,
  replaceDraft,
  setGraphEditStatus,
  translate,
  formatMessage,
}: UseWorkflowTemplateControllerParams) {
  const [templateItems, setTemplateItems] = useState<GraphTemplateRecord[]>([])
  const [versionItems, setVersionItems] = useState<GraphTemplateVersionRecord[]>([])
  const [templateStageItems, setTemplateStageItems] = useState<WorkflowTemplateStageRecord[]>([])
  const [templateStageAuditSummary, setTemplateStageAuditSummary] = useState<TemplateStageAuditSummary | null>(null)
  const [templateRollbackDraft, setTemplateRollbackDraft] = useState({
    targetStage: 'staging' as WorkflowTemplateStageName,
    targetVersion: '',
    reason: '',
  })
  const [templateRollbackPreview, setTemplateRollbackPreview] = useState<WorkflowTemplateRollbackResponse | null>(null)
  const [templateRollbackError, setTemplateRollbackError] = useState('')
  const [templateNameDraft, setTemplateNameDraft] = useState('')
  const [renameTemplateDraft, setRenameTemplateDraft] = useState('')
  const [versionNameDraft, setVersionNameDraft] = useState('')
  const [activeTemplateKey, setActiveTemplateKey] = useState('')
  const [activeVersionKey, setActiveVersionKey] = useState('')
  const [templateBusy, setTemplateBusy] = useState(false)
  const [templateStageBusy, setTemplateStageBusy] = useState(false)
  const [templateRollbackBusy, setTemplateRollbackBusy] = useState(false)
  const [templateDiffBusy, setTemplateDiffBusy] = useState(false)
  const [templateDiffPreview, setTemplateDiffPreview] = useState<WorkflowTemplateDiffResponse | null>(null)
  const [templateDryRunBusy, setTemplateDryRunBusy] = useState(false)
  const [templateDryRunResult, setTemplateDryRunResult] = useState<WorkflowRunResult | null>(null)

  const loadTemplateList = useCallback(async () => {
    const raw = await listWorkflowGraphTemplates()
    const parsed = (raw.items || []).map(asTemplateRecord).filter((item): item is GraphTemplateRecord => Boolean(item))
    setTemplateItems(parsed)
    setActiveTemplateKey((prev) => prev || parsed[0]?.key || '')
    return parsed
  }, [])

  const loadVersionList = useCallback(async (templateKey: string) => {
    if (!templateKey) {
      setVersionItems([])
      return []
    }
    const raw = await listWorkflowGraphTemplateVersions(templateKey)
    const rawRecord: Record<string, unknown> = isPlainRecord(raw) ? raw : {}
    const activeVersion = String(rawRecord.active_version_id || '').trim()
    const parsed = (raw.items || [])
      .map(asVersionRecord)
      .filter((item): item is GraphTemplateVersionRecord => Boolean(item))
      .map((item) => ({ ...item, activated: item.key === activeVersion || item.activated }))
    setVersionItems(parsed)
    setActiveVersionKey((prev) => activeVersion || prev || parsed[0]?.key || '')
    return parsed
  }, [])

  const loadWorkflowTemplateStageAudit = useCallback(async (workflowName: string) => {
    if (!workflowName) {
      setTemplateStageItems([])
      setTemplateStageAuditSummary(null)
      return []
    }
    const raw = await listWorkflowTemplateVersions(workflowName, projectKey)
    const items = normalizeWorkflowTemplateStageRecords(raw.items || [])
    setTemplateStageItems(items)
    setTemplateStageAuditSummary(buildTemplateStageAuditSummary(raw))
    return items
  }, [projectKey])

  const selectTemplate = useCallback((templateKey: string) => {
    setActiveTemplateKey(templateKey)
    setActiveVersionKey('')
    setVersionItems([])
    setTemplateDiffPreview(null)
    setTemplateDryRunResult(null)
    setTemplateRollbackPreview(null)
    setTemplateRollbackError('')
    if (templateKey) {
      void loadVersionList(templateKey)
      void loadWorkflowTemplateStageAudit(templateKey)
    } else {
      setTemplateStageItems([])
      setTemplateStageAuditSummary(null)
    }
  }, [loadVersionList, loadWorkflowTemplateStageAudit])

  useEffect(() => {
    if (!enabled) return
    let canceled = false
    const run = async () => {
      setTemplateBusy(true)
      try {
        const list = await loadTemplateList()
        const key = activeTemplateKey || list[0]?.key || ''
        if (!canceled && key) {
          await loadVersionList(key)
          await loadWorkflowTemplateStageAudit(key)
        }
      } catch (error) {
        if (canceled) return
        const message = error instanceof Error ? error.message : translate('graphPage.error.templateListLoadFailed')
        setGraphEditStatus(formatMessage('graphPage.error.templateListLoadFailedWithMessage', { message }))
      } finally {
        if (!canceled) setTemplateBusy(false)
      }
    }
    void run()
    return () => {
      canceled = true
    }
  }, [enabled, loadTemplateList, loadVersionList, loadWorkflowTemplateStageAudit, activeTemplateKey, translate, formatMessage, setGraphEditStatus])

  const handleLoadTemplateVersions = useCallback(async () => {
    if (!activeTemplateKey) return
    setTemplateBusy(true)
    try {
      await loadVersionList(activeTemplateKey)
      setGraphEditStatus(formatMessage('graphPage.status.templateVersionsLoaded', { templateKey: activeTemplateKey }))
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.versionListLoadFailed')
      setGraphEditStatus(formatMessage('graphPage.error.versionListLoadFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.versionListLoadFailedWithMessage', { message }))
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, loadVersionList, translate, formatMessage, setGraphEditStatus])

  const handlePreviewWorkflowTemplateDiff = useCallback(async () => {
    const workflowName = activeTemplateKey.trim()
    if (!workflowName) {
      window.alert(translate('graphPage.error.selectTemplate'))
      return
    }
    if (!draftNodes.length) {
      window.alert(translate('graphPage.error.noSubmittableDraftNodes'))
      return
    }
    setTemplateDiffBusy(true)
    try {
      const preview = await diffWorkflowTemplate(workflowName, buildWorkflowTemplatePayloadFromDraft({
        projectKey,
        nodes: draftNodes,
        edges: draftEdges,
        graphKind,
      }))
      setTemplateDiffPreview(preview)
      setGraphEditStatus(formatMessage('graphPage.status.configDiffLoaded', {
        workflowName,
        current: preview.current_version ?? '-',
        next: preview.next_version ?? '-',
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.configDiffFailed')
      setGraphEditStatus(formatMessage('graphPage.error.configDiffFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.configDiffFailedWithMessage', { message }))
    } finally {
      setTemplateDiffBusy(false)
    }
  }, [activeTemplateKey, draftNodes, draftEdges, projectKey, graphKind, translate, formatMessage, setGraphEditStatus])

  const handleWorkflowTemplateDryRun = useCallback(async () => {
    const workflowName = activeTemplateKey.trim()
    if (!workflowName) {
      window.alert(translate('graphPage.error.selectTemplate'))
      return
    }
    setTemplateDryRunBusy(true)
    try {
      const result = await runWorkflow(workflowName, {}, { dryRun: true })
      const summary = summarizeWorkflowDryRunResult(result)
      setTemplateDryRunResult(result)
      setGraphEditStatus(formatMessage('graphPage.status.workflowDryRunLoaded', {
        workflowName,
        configVersion: formatWorkflowRunScalar(summary.configVersion),
        readiness: formatWorkflowRunScalar(summary.readiness),
        writesBlocked: formatWorkflowRunScalar(summary.writesBlocked),
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.workflowDryRunFailed')
      setGraphEditStatus(formatMessage('graphPage.error.workflowDryRunFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.workflowDryRunFailedWithMessage', { message }))
    } finally {
      setTemplateDryRunBusy(false)
    }
  }, [activeTemplateKey, translate, formatMessage, setGraphEditStatus])

  const handleRefreshWorkflowTemplateStages = useCallback(async () => {
    if (!activeTemplateKey) return
    setTemplateStageBusy(true)
    try {
      await loadWorkflowTemplateStageAudit(activeTemplateKey)
      setGraphEditStatus(formatMessage('graphPage.status.templateStageAuditLoaded', { templateKey: activeTemplateKey }))
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateStageAuditLoadFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateStageAuditLoadFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateStageAuditLoadFailedWithMessage', { message }))
    } finally {
      setTemplateStageBusy(false)
    }
  }, [activeTemplateKey, loadWorkflowTemplateStageAudit, translate, formatMessage, setGraphEditStatus])

  const handleSaveWorkflowTemplateDraftStage = useCallback(async () => {
    const workflowName = activeTemplateKey.trim()
    if (!workflowName) {
      window.alert(translate('graphPage.error.selectTemplate'))
      return
    }
    if (!draftNodes.length) {
      window.alert(translate('graphPage.error.noSubmittableDraftNodes'))
      return
    }
    setTemplateStageBusy(true)
    try {
      const response = await stageWorkflowTemplate(workflowName, {
        ...buildWorkflowTemplatePayloadFromDraft({
          projectKey,
          nodes: draftNodes,
          edges: draftEdges,
          graphKind,
        }),
        stage: 'draft',
      })
      setTemplateStageAuditSummary(buildTemplateStageAuditSummary(response))
      await loadWorkflowTemplateStageAudit(workflowName)
      setGraphEditStatus(formatMessage('graphPage.status.templateStageDraftSaved', {
        next: response.next_version ?? '-',
        requiresPublish: String(Boolean(response.version_summary?.requires_publish)),
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateStageSaveFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateStageSaveFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateStageSaveFailedWithMessage', { message }))
    } finally {
      setTemplateStageBusy(false)
    }
  }, [activeTemplateKey, draftNodes, draftEdges, projectKey, graphKind, loadWorkflowTemplateStageAudit, translate, formatMessage, setGraphEditStatus])

  const handlePromoteWorkflowTemplateStage = useCallback(async (
    fromStage: Extract<WorkflowTemplateStageName, 'draft' | 'staging'>,
    toStage: Extract<WorkflowTemplateStageName, 'staging' | 'active'>,
  ) => {
    const workflowName = activeTemplateKey.trim()
    if (!workflowName) {
      window.alert(translate('graphPage.error.selectTemplate'))
      return
    }
    setTemplateStageBusy(true)
    try {
      const response = await promoteWorkflowTemplate(workflowName, {
        project_key: projectKey,
        from_stage: fromStage,
        to_stage: toStage,
      })
      setTemplateStageAuditSummary(buildTemplateStageAuditSummary(response))
      await loadWorkflowTemplateStageAudit(workflowName)
      setGraphEditStatus(formatMessage('graphPage.status.templateStagePromoted', {
        fromStage,
        toStage,
        next: response.next_version ?? '-',
        requiresPublish: String(Boolean(response.version_summary?.requires_publish)),
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateStagePromoteFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateStagePromoteFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateStagePromoteFailedWithMessage', { message }))
    } finally {
      setTemplateStageBusy(false)
    }
  }, [activeTemplateKey, projectKey, loadWorkflowTemplateStageAudit, translate, formatMessage, setGraphEditStatus])

  const handlePreviewWorkflowTemplateRollback = useCallback(async () => {
    const workflowName = activeTemplateKey.trim()
    if (!workflowName) {
      window.alert(translate('graphPage.error.selectTemplate'))
      return
    }
    const targetVersion = parseTemplateRollbackVersion(templateRollbackDraft.targetVersion)
    if (targetVersion === null) {
      window.alert(translate('graphPage.error.templateRollbackVersionRequired'))
      return
    }
    setTemplateRollbackBusy(true)
    setTemplateRollbackError('')
    try {
      const response = await previewWorkflowTemplateRollback(workflowName, {
        project_key: projectKey,
        target_stage: templateRollbackDraft.targetStage,
        target_version: targetVersion,
        reason: templateRollbackDraft.reason.trim() || undefined,
        actor: 'graph-ui',
        requested_by: 'graph-ui',
        trace_id: buildTemplateRollbackTraceId(workflowName, templateRollbackDraft.targetStage, targetVersion),
      })
      setTemplateRollbackPreview(response)
      setGraphEditStatus(formatMessage('graphPage.status.templateRollbackPreviewLoaded', {
        targetStage: templateRollbackDraft.targetStage,
        targetVersion,
        canExecute: String(Boolean(response.rollback_plan?.can_execute ?? response.rollback_plan?.executable)),
        willMutate: String(Boolean(response.rollback_plan?.will_mutate)),
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateRollbackPreviewFailed')
      setTemplateRollbackError(message)
      setGraphEditStatus(formatMessage('graphPage.error.templateRollbackPreviewFailedWithMessage', { message }))
    } finally {
      setTemplateRollbackBusy(false)
    }
  }, [activeTemplateKey, projectKey, templateRollbackDraft, translate, formatMessage, setGraphEditStatus])

  const handleApplyWorkflowTemplateRollback = useCallback(async () => {
    const workflowName = activeTemplateKey.trim()
    if (!workflowName) {
      window.alert(translate('graphPage.error.selectTemplate'))
      return
    }
    const targetVersion = parseTemplateRollbackVersion(templateRollbackDraft.targetVersion)
    if (targetVersion === null) {
      window.alert(translate('graphPage.error.templateRollbackVersionRequired'))
      return
    }
    setTemplateRollbackBusy(true)
    setTemplateRollbackError('')
    try {
      const response = await applyWorkflowTemplateRollback(workflowName, {
        project_key: projectKey,
        target_stage: templateRollbackDraft.targetStage,
        target_version: targetVersion,
        reason: templateRollbackDraft.reason.trim() || undefined,
        actor: 'graph-ui',
        requested_by: 'graph-ui',
        trace_id: buildTemplateRollbackTraceId(workflowName, templateRollbackDraft.targetStage, targetVersion),
      })
      setTemplateRollbackPreview(response)
      setTemplateStageAuditSummary(buildTemplateStageAuditSummary(response))
      await loadWorkflowTemplateStageAudit(workflowName)
      setGraphEditStatus(formatMessage('graphPage.status.templateRollbackApplied', {
        targetStage: templateRollbackDraft.targetStage,
        targetVersion,
        next: response.next_version ?? '-',
      }))
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateRollbackApplyFailed')
      setTemplateRollbackError(message)
      setGraphEditStatus(formatMessage('graphPage.error.templateRollbackApplyFailedWithMessage', { message }))
    } finally {
      setTemplateRollbackBusy(false)
    }
  }, [activeTemplateKey, projectKey, templateRollbackDraft, loadWorkflowTemplateStageAudit, translate, formatMessage, setGraphEditStatus])

  const handleCreateTemplate = useCallback(async () => {
    const name = templateNameDraft.trim()
    if (!name) return
    setTemplateBusy(true)
    try {
      const templateId = name.replace(/\s+/g, '_')
      await createWorkflowGraphTemplate({
        template_id: templateId,
        name,
        dsl: { nodes: draftNodes, edges: draftEdges },
      })
      setTemplateNameDraft('')
      setGraphEditStatus(formatMessage('graphPage.status.templateCreated', { name }))
      await loadTemplateList()
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateCreateFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateCreateFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateCreateFailedWithMessage', { message }))
    } finally {
      setTemplateBusy(false)
    }
  }, [templateNameDraft, draftNodes, draftEdges, loadTemplateList, translate, formatMessage, setGraphEditStatus])

  const handleRenameTemplate = useCallback(async () => {
    if (!activeTemplateKey) return
    const name = renameTemplateDraft.trim()
    if (!name) return
    setTemplateBusy(true)
    try {
      await updateWorkflowGraphTemplate(activeTemplateKey, { name })
      setRenameTemplateDraft('')
      setGraphEditStatus(formatMessage('graphPage.status.templateRenamed', { name }))
      await loadTemplateList()
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateRenameFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateRenameFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateRenameFailedWithMessage', { message }))
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, renameTemplateDraft, loadTemplateList, translate, formatMessage, setGraphEditStatus])

  const handleDeleteTemplate = useCallback(async () => {
    if (!activeTemplateKey) return
    setTemplateBusy(true)
    try {
      await deleteWorkflowGraphTemplate(activeTemplateKey)
      setGraphEditStatus(formatMessage('graphPage.status.templateDeleted', { templateKey: activeTemplateKey }))
      setActiveTemplateKey('')
      setActiveVersionKey('')
      setVersionItems([])
      setTemplateStageItems([])
      setTemplateStageAuditSummary(null)
      setTemplateDryRunResult(null)
      setTemplateRollbackPreview(null)
      setTemplateRollbackError('')
      await loadTemplateList()
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateDeleteFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateDeleteFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateDeleteFailedWithMessage', { message }))
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, loadTemplateList, translate, formatMessage, setGraphEditStatus])

  const handleSaveVersion = useCallback(async () => {
    if (!activeTemplateKey) {
      window.alert(translate('graphPage.error.selectTemplate'))
      return
    }
    const versionName = versionNameDraft.trim() || `v-${new Date().toISOString()}`
    setTemplateBusy(true)
    try {
      await createWorkflowGraphTemplateVersion(activeTemplateKey, {
        version_id: versionName,
        dsl: { nodes: draftNodes, edges: draftEdges },
      })
      setVersionNameDraft('')
      setGraphEditStatus(formatMessage('graphPage.status.versionSaved', { versionName }))
      await loadVersionList(activeTemplateKey)
      markDraftSaved()
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.versionSaveFailed')
      setGraphEditStatus(formatMessage('graphPage.error.versionSaveFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.versionSaveFailedWithMessage', { message }))
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, versionNameDraft, draftNodes, draftEdges, loadVersionList, markDraftSaved, translate, formatMessage, setGraphEditStatus])

  const handleLoadVersion = useCallback(async () => {
    if (!activeTemplateKey || !activeVersionKey) return
    setTemplateBusy(true)
    try {
      const raw = await getWorkflowGraphTemplateVersion(activeTemplateKey, activeVersionKey)
      const payload: Record<string, unknown> = isPlainRecord(raw) ? raw : {}
      const versionPayload: Record<string, unknown> = isPlainRecord(payload.version) ? payload.version : payload
      const dslPayload = isPlainRecord(versionPayload.dsl) ? versionPayload.dsl : versionPayload
      const nextNodes = Array.isArray(dslPayload.nodes) ? dslPayload.nodes as GraphNodeItem[] : []
      const nextEdges = Array.isArray(dslPayload.edges) ? dslPayload.edges as GraphEdgeItem[] : []
      if (!nextNodes.length && !nextEdges.length) {
        window.alert(translate('graphPage.status.versionLoadedEmpty'))
      }
      replaceDraft(nextNodes, nextEdges, { markAsDirty: true })
      setGraphEditStatus(formatMessage('graphPage.status.versionLoaded', { versionKey: activeVersionKey }))
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.versionLoadFailed')
      setGraphEditStatus(formatMessage('graphPage.error.versionLoadFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.versionLoadFailedWithMessage', { message }))
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, activeVersionKey, replaceDraft, translate, formatMessage, setGraphEditStatus])

  const handleActivateVersion = useCallback(async () => {
    if (!activeTemplateKey || !activeVersionKey) return
    setTemplateBusy(true)
    try {
      await activateWorkflowGraphTemplateVersion(activeTemplateKey, activeVersionKey)
      setGraphEditStatus(formatMessage('graphPage.status.versionActivated', { versionKey: activeVersionKey }))
      await loadVersionList(activeTemplateKey)
    } catch (error) {
      const message = error instanceof Error ? error.message : translate('graphPage.error.versionActivateFailed')
      setGraphEditStatus(formatMessage('graphPage.error.versionActivateFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.versionActivateFailedWithMessage', { message }))
    } finally {
      setTemplateBusy(false)
    }
  }, [activeTemplateKey, activeVersionKey, loadVersionList, translate, formatMessage, setGraphEditStatus])

  const templateDryRunSummary = useMemo(() => summarizeWorkflowDryRunResult(templateDryRunResult), [templateDryRunResult])
  const templateDryRunSteps = useMemo(() => normalizeWorkflowDryRunSteps(templateDryRunResult), [templateDryRunResult])
  const templateRollbackPlan = useMemo(() => describeTemplateRollbackPlan(templateRollbackPreview), [templateRollbackPreview])
  const templateRollbackAudit = useMemo(() => describeTemplateRollbackAudit(templateRollbackPreview), [templateRollbackPreview])
  const templateRollbackHistoryCount = Array.isArray(templateRollbackPreview?.history) ? templateRollbackPreview.history.length : 0
  const hasDraftTemplateStage = templateStageItems.some((item) => item.stage === 'draft')
  const hasStagingTemplateStage = templateStageItems.some((item) => item.stage === 'staging')

  return {
    templateItems,
    versionItems,
    templateStageItems,
    templateStageAuditSummary,
    templateRollbackDraft,
    setTemplateRollbackDraft,
    templateRollbackPreview,
    templateRollbackError,
    templateNameDraft,
    setTemplateNameDraft,
    renameTemplateDraft,
    setRenameTemplateDraft,
    versionNameDraft,
    setVersionNameDraft,
    activeTemplateKey,
    setActiveTemplateKey,
    activeVersionKey,
    setActiveVersionKey,
    templateBusy,
    templateStageBusy,
    templateRollbackBusy,
    templateDiffBusy,
    templateDiffPreview,
    templateDryRunBusy,
    templateDryRunResult,
    templateDryRunSummary,
    templateDryRunSteps,
    templateRollbackPlan,
    templateRollbackAudit,
    templateRollbackHistoryCount,
    hasDraftTemplateStage,
    hasStagingTemplateStage,
    loadTemplateList,
    loadVersionList,
    loadWorkflowTemplateStageAudit,
    selectTemplate,
    handleLoadTemplateVersions,
    handlePreviewWorkflowTemplateDiff,
    handleWorkflowTemplateDryRun,
    handleRefreshWorkflowTemplateStages,
    handleSaveWorkflowTemplateDraftStage,
    handlePromoteWorkflowTemplateStage,
    handlePreviewWorkflowTemplateRollback,
    handleApplyWorkflowTemplateRollback,
    handleCreateTemplate,
    handleRenameTemplate,
    handleDeleteTemplate,
    handleSaveVersion,
    handleLoadVersion,
    handleActivateVersion,
  }
}

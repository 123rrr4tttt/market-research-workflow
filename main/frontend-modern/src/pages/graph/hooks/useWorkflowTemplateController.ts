import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  activateWorkflowGraphTemplateVersion,
  applyWorkflowTemplateRollback,
  createWorkflowGraphTemplate,
  createWorkflowGraphTemplateVersion,
  deleteWorkflowGraphTemplate,
  diffWorkflowTemplate,
  getWorkflowGraphTemplateVersion,
  listWorkflowGraphTemplateVersions,
  listWorkflowTemplateVersions,
  previewWorkflowTemplateRollback,
  promoteWorkflowTemplate,
  runWorkflow,
  stageWorkflowTemplate,
  updateWorkflowGraphTemplate,
} from '../../../lib/api'
import { getProjectKey } from '../../../lib/api/client'
import type { GraphEdgeItem, GraphNodeItem, WorkflowRunResult, WorkflowTemplateDiffResponse, WorkflowTemplateRollbackResponse, WorkflowTemplateStageName, WorkflowTemplateStageRecord } from '../../../lib/types'
import type { MessageKey } from '../../../app/platform/i18n'
import type { GraphProjectionDefinition } from '../realizer/contract'
import {
  normalizeProjectGraphViewSpec,
  type ProjectGraphViewSpec,
} from '../realizer/projectGraphView'
import { getGraphTemplateRouteFromHash } from '../realizer/workspaceNavigation'
import {
  projectGraphTemplatesQueryOptions,
  useProjectGraphTemplates,
} from './useProjectGraphTemplates'
import {
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
  type GraphTemplateVersionRecord,
  type TemplateStageAuditSummary,
} from '../realizer/workflowTemplate'

type GraphKind = GraphProjectionDefinition['graphKind']
type GraphMessageParams = Record<string, number | string>

type TemplateVersionGraph = {
  kind: 'legacy'
  nodes: GraphNodeItem[]
  edges: GraphEdgeItem[]
} | {
  kind: 'project-view'
  spec: ProjectGraphViewSpec
} | {
  kind: 'invalid-project-view'
}

function readTemplateVersionGraph(raw: unknown): TemplateVersionGraph {
  const payload: Record<string, unknown> = isPlainRecord(raw) ? raw : {}
  const versionPayload: Record<string, unknown> = isPlainRecord(payload.version) ? payload.version : payload
  const dslPayload = isPlainRecord(versionPayload.dsl) ? versionPayload.dsl : versionPayload
  const nodes = Array.isArray(dslPayload.nodes) ? dslPayload.nodes as GraphNodeItem[] : []
  const edges = Array.isArray(dslPayload.edges) ? dslPayload.edges as GraphEdgeItem[] : []
  if (!Object.prototype.hasOwnProperty.call(dslPayload, 'project_view')) {
    return { kind: 'legacy', nodes, edges }
  }
  const spec = normalizeProjectGraphViewSpec(dslPayload.project_view)
  return spec ? { kind: 'project-view', spec } : { kind: 'invalid-project-view' }
}

type UseWorkflowTemplateControllerParams = {
  enabled: boolean
  autoSelectFirstTemplate?: boolean
  projectKey: string
  graphKind: GraphKind
  draftNodes: GraphNodeItem[]
  draftEdges: GraphEdgeItem[]
  markDraftSaved: () => void
  replaceDraft: (nodes: GraphNodeItem[], edges: GraphEdgeItem[], options?: { markAsDirty?: boolean }) => void
  setGraphEditStatus: (status: string) => void
  viewSpec?: ProjectGraphViewSpec
  onLoadViewSpec?: (spec: ProjectGraphViewSpec | null) => void
  onResetProjectView?: () => void
  translate: (key: MessageKey) => string
  formatMessage: (key: MessageKey, params: GraphMessageParams) => string
}

export function useWorkflowTemplateController({
  enabled,
  autoSelectFirstTemplate = true,
  projectKey,
  graphKind,
  draftNodes,
  draftEdges,
  markDraftSaved,
  replaceDraft,
  setGraphEditStatus,
  viewSpec,
  onLoadViewSpec,
  onResetProjectView,
  translate,
  formatMessage,
}: UseWorkflowTemplateControllerParams) {
  const queryClient = useQueryClient()
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
  const [templateStageBusy, setTemplateStageBusy] = useState(false)
  const [templateRollbackBusy, setTemplateRollbackBusy] = useState(false)
  const [templateDiffBusy, setTemplateDiffBusy] = useState(false)
  const [templateDiffPreview, setTemplateDiffPreview] = useState<WorkflowTemplateDiffResponse | null>(null)
  const [templateDryRunBusy, setTemplateDryRunBusy] = useState(false)
  const [templateDryRunResult, setTemplateDryRunResult] = useState<WorkflowRunResult | null>(null)
  const [templateMutationBusy, setTemplateBusy] = useState(false)
  const [templateRouteHash, setTemplateRouteHash] = useState(() => window.location.hash)
  const templateRequestEpochRef = useRef(0)
  const activeTemplateKeyRef = useRef('')
  const attemptedTemplateRouteRef = useRef('')

  const templatesQuery = useProjectGraphTemplates(projectKey, enabled)
  const templateItems = useMemo(() => templatesQuery.data || [], [templatesQuery.data])
  const templateBusy = templateMutationBusy || templatesQuery.isFetching
  const normalizedViewSpec = useMemo(
    () => (viewSpec === undefined ? null : normalizeProjectGraphViewSpec(viewSpec)),
    [viewSpec],
  )

  const isCurrentTemplateRequest = useCallback((requestEpoch: number, templateKey?: string) => (
    requestEpoch === templateRequestEpochRef.current
    && getProjectKey() === projectKey
    && (templateKey === undefined || activeTemplateKeyRef.current === templateKey)
  ), [projectKey])

  const clearTemplateSelection = useCallback(() => {
    setActiveTemplateKey('')
    setActiveVersionKey('')
    setVersionItems([])
    setTemplateStageItems([])
    setTemplateStageAuditSummary(null)
    setTemplateDiffPreview(null)
    setTemplateDryRunResult(null)
    setTemplateRollbackPreview(null)
    setTemplateRollbackError('')
  }, [])

  useEffect(() => {
    templateRequestEpochRef.current += 1
    activeTemplateKeyRef.current = ''
    attemptedTemplateRouteRef.current = ''
    const reset = window.setTimeout(() => {
      clearTemplateSelection()
      setTemplateBusy(false)
      setTemplateStageBusy(false)
      setTemplateRollbackBusy(false)
      setTemplateDiffBusy(false)
      setTemplateDryRunBusy(false)
    }, 0)
    return () => window.clearTimeout(reset)
  }, [clearTemplateSelection, projectKey, setTemplateBusy])

  const loadTemplateList = useCallback(async () => {
    const requestEpoch = templateRequestEpochRef.current
    setTemplateBusy(true)
    try {
      const items = await queryClient.fetchQuery({
        ...projectGraphTemplatesQueryOptions(projectKey),
        staleTime: 0,
      })
      return isCurrentTemplateRequest(requestEpoch) ? items : []
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch)) return []
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateListLoadFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateListLoadFailedWithMessage', { message }))
      return []
    } finally {
      if (isCurrentTemplateRequest(requestEpoch)) setTemplateBusy(false)
    }
  }, [formatMessage, isCurrentTemplateRequest, projectKey, queryClient, setGraphEditStatus, setTemplateBusy, translate])

  const loadVersionList = useCallback(async (templateKey: string, requestEpoch = templateRequestEpochRef.current) => {
    if (!templateKey) {
      setVersionItems([])
      return []
    }
    const raw = await listWorkflowGraphTemplateVersions(templateKey)
    if (!isCurrentTemplateRequest(requestEpoch, templateKey)) return []
    const rawRecord: Record<string, unknown> = isPlainRecord(raw) ? raw : {}
    const activeVersion = String(rawRecord.active_version_id || '').trim()
    const parsed = (raw.items || [])
      .map(asVersionRecord)
      .filter((item): item is GraphTemplateVersionRecord => Boolean(item))
      .map((item) => ({ ...item, activated: item.key === activeVersion || item.activated }))
    setVersionItems(parsed)
    setActiveVersionKey((prev) => activeVersion || prev || parsed[0]?.key || '')
    return parsed
  }, [isCurrentTemplateRequest])

  const loadWorkflowTemplateStageAudit = useCallback(async (workflowName: string, requestEpoch = templateRequestEpochRef.current) => {
    if (!workflowName) {
      setTemplateStageItems([])
      setTemplateStageAuditSummary(null)
      return []
    }
    const raw = await listWorkflowTemplateVersions(workflowName, projectKey)
    if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return []
    const items = normalizeWorkflowTemplateStageRecords(raw.items || [])
    setTemplateStageItems(items)
    setTemplateStageAuditSummary(buildTemplateStageAuditSummary(raw))
    return items
  }, [isCurrentTemplateRequest, projectKey])

  const reportVersionListError = useCallback((error: unknown, templateKey: string, requestEpoch: number) => {
    if (!isCurrentTemplateRequest(requestEpoch, templateKey)) return
    const message = error instanceof Error ? error.message : translate('graphPage.error.versionListLoadFailed')
    setGraphEditStatus(formatMessage('graphPage.error.versionListLoadFailedWithMessage', { message }))
  }, [formatMessage, isCurrentTemplateRequest, setGraphEditStatus, translate])

  const reportStageAuditError = useCallback((error: unknown, templateKey: string, requestEpoch: number) => {
    if (!isCurrentTemplateRequest(requestEpoch, templateKey)) return
    const message = error instanceof Error ? error.message : translate('graphPage.error.templateStageAuditLoadFailed')
    setGraphEditStatus(formatMessage('graphPage.error.templateStageAuditLoadFailedWithMessage', { message }))
  }, [formatMessage, isCurrentTemplateRequest, setGraphEditStatus, translate])

  const selectTemplate = useCallback((templateKey: string) => {
    const requestEpoch = templateRequestEpochRef.current + 1
    templateRequestEpochRef.current = requestEpoch
    activeTemplateKeyRef.current = templateKey
    setTemplateBusy(false)
    setTemplateStageBusy(false)
    setTemplateRollbackBusy(false)
    setTemplateDiffBusy(false)
    setTemplateDryRunBusy(false)
    setActiveTemplateKey(templateKey)
    setActiveVersionKey('')
    setVersionItems([])
    setTemplateDiffPreview(null)
    setTemplateDryRunResult(null)
    setTemplateRollbackPreview(null)
    setTemplateRollbackError('')
    if (templateKey) {
      void loadVersionList(templateKey, requestEpoch)
        .catch((error) => reportVersionListError(error, templateKey, requestEpoch))
      void loadWorkflowTemplateStageAudit(templateKey, requestEpoch)
        .catch((error) => reportStageAuditError(error, templateKey, requestEpoch))
    } else {
      setTemplateStageItems([])
      setTemplateStageAuditSummary(null)
    }
  }, [
    loadVersionList,
    loadWorkflowTemplateStageAudit,
    reportStageAuditError,
    reportVersionListError,
    setTemplateBusy,
  ])

  useEffect(() => {
    const syncRouteHash = () => setTemplateRouteHash(window.location.hash)
    syncRouteHash()
    window.addEventListener('hashchange', syncRouteHash)
    return () => window.removeEventListener('hashchange', syncRouteHash)
  }, [])

  useEffect(() => {
    if (!templatesQuery.isError) return
    const error = templatesQuery.error
    const message = error instanceof Error ? error.message : translate('graphPage.error.templateListLoadFailed')
    setGraphEditStatus(formatMessage('graphPage.error.templateListLoadFailedWithMessage', { message }))
  }, [formatMessage, setGraphEditStatus, templatesQuery.error, templatesQuery.isError, translate])

  const { templateKey: routeTemplateKey, versionKey: routeVersionKey } = useMemo(
    () => getGraphTemplateRouteFromHash(templateRouteHash),
    [templateRouteHash],
  )

  useEffect(() => {
    if (!routeTemplateKey) {
      if (!attemptedTemplateRouteRef.current) return
      templateRequestEpochRef.current += 1
      activeTemplateKeyRef.current = ''
      const reset = window.setTimeout(() => {
        attemptedTemplateRouteRef.current = ''
        clearTemplateSelection()
        onResetProjectView?.()
        setTemplateBusy(false)
        setTemplateStageBusy(false)
        setTemplateRollbackBusy(false)
        setTemplateDiffBusy(false)
        setTemplateDryRunBusy(false)
      }, 0)
      return () => window.clearTimeout(reset)
    }
    if (!enabled || templatesQuery.isFetching || !templateItems.some((item) => item.key === routeTemplateKey)) return

    const attemptKey = `${projectKey}\0${routeTemplateKey}\0${routeVersionKey}`
    if (attemptedTemplateRouteRef.current === attemptKey) return
    attemptedTemplateRouteRef.current = attemptKey
    const requestEpoch = templateRequestEpochRef.current + 1
    templateRequestEpochRef.current = requestEpoch
    activeTemplateKeyRef.current = routeTemplateKey
    setActiveTemplateKey(routeTemplateKey)
    setActiveVersionKey('')
    setVersionItems([])
    setTemplateStageItems([])
    setTemplateStageAuditSummary(null)
    setTemplateDiffPreview(null)
    setTemplateDryRunResult(null)
    setTemplateRollbackPreview(null)
    setTemplateRollbackError('')

    const run = async () => {
      setTemplateBusy(true)
      try {
        const versions = await loadVersionList(routeTemplateKey, requestEpoch)
        if (!isCurrentTemplateRequest(requestEpoch, routeTemplateKey)) return
        const template = templateItems.find((item) => item.key === routeTemplateKey)
        const versionKey = routeVersionKey || template?.activeVersion || versions.find((item) => item.activated)?.key || ''
        if (!versionKey) return
        setActiveVersionKey(versionKey)
        const raw = await getWorkflowGraphTemplateVersion(routeTemplateKey, versionKey)
        if (!isCurrentTemplateRequest(requestEpoch, routeTemplateKey)) return
        const versionGraph = readTemplateVersionGraph(raw)
        if (versionGraph.kind === 'invalid-project-view') {
          onLoadViewSpec?.(null)
          setGraphEditStatus(formatMessage('graphPage.error.projectViewSchemaInvalid', {}))
          return
        }
        if (versionGraph.kind === 'project-view') {
          onLoadViewSpec?.(versionGraph.spec)
          setGraphEditStatus(formatMessage('graphPage.status.versionLoaded', { versionKey }))
          void loadWorkflowTemplateStageAudit(routeTemplateKey, requestEpoch)
            .catch((error) => reportStageAuditError(error, routeTemplateKey, requestEpoch))
          return
        }
        onLoadViewSpec?.(null)
        if (!versionGraph.nodes.length && !versionGraph.edges.length) {
          window.alert(translate('graphPage.status.versionLoadedEmpty'))
        }
        replaceDraft(versionGraph.nodes, versionGraph.edges, { markAsDirty: false })
        setGraphEditStatus(formatMessage('graphPage.status.versionLoaded', { versionKey }))
        void loadWorkflowTemplateStageAudit(routeTemplateKey, requestEpoch)
          .catch((error) => reportStageAuditError(error, routeTemplateKey, requestEpoch))
      } catch (error) {
        if (!isCurrentTemplateRequest(requestEpoch, routeTemplateKey)) return
        const message = error instanceof Error ? error.message : translate('graphPage.error.versionLoadFailed')
        setGraphEditStatus(formatMessage('graphPage.error.versionLoadFailedWithMessage', { message }))
      } finally {
        if (isCurrentTemplateRequest(requestEpoch, routeTemplateKey)) setTemplateBusy(false)
      }
    }
    void run()
  }, [clearTemplateSelection, enabled, formatMessage, isCurrentTemplateRequest, loadVersionList, loadWorkflowTemplateStageAudit, onLoadViewSpec, onResetProjectView, projectKey, replaceDraft, reportStageAuditError, routeTemplateKey, routeVersionKey, setGraphEditStatus, setTemplateBusy, templateItems, templatesQuery.isFetching, translate])

  useEffect(() => {
    if (!autoSelectFirstTemplate || !enabled || templatesQuery.isFetching || routeTemplateKey || activeTemplateKey || !templateItems.length) return
    const templateKey = templateItems[0].key
    const select = window.setTimeout(() => selectTemplate(templateKey), 0)
    return () => window.clearTimeout(select)
  }, [activeTemplateKey, autoSelectFirstTemplate, enabled, routeTemplateKey, selectTemplate, templateItems, templatesQuery.isFetching])

  const handleLoadTemplateVersions = useCallback(async () => {
    if (!activeTemplateKey) return
    const requestEpoch = templateRequestEpochRef.current
    setTemplateBusy(true)
    try {
      await loadVersionList(activeTemplateKey, requestEpoch)
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      setGraphEditStatus(formatMessage('graphPage.status.templateVersionsLoaded', { templateKey: activeTemplateKey }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.versionListLoadFailed')
      setGraphEditStatus(formatMessage('graphPage.error.versionListLoadFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.versionListLoadFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) setTemplateBusy(false)
    }
  }, [activeTemplateKey, formatMessage, isCurrentTemplateRequest, loadVersionList, setGraphEditStatus, setTemplateBusy, translate])

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
    const requestEpoch = templateRequestEpochRef.current
    setTemplateDiffBusy(true)
    try {
      const preview = await diffWorkflowTemplate(workflowName, buildWorkflowTemplatePayloadFromDraft({
        projectKey,
        nodes: draftNodes,
        edges: draftEdges,
        graphKind,
      }))
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      setTemplateDiffPreview(preview)
      setGraphEditStatus(formatMessage('graphPage.status.configDiffLoaded', {
        workflowName,
        current: preview.current_version ?? '-',
        next: preview.next_version ?? '-',
      }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.configDiffFailed')
      setGraphEditStatus(formatMessage('graphPage.error.configDiffFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.configDiffFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, workflowName)) setTemplateDiffBusy(false)
    }
  }, [activeTemplateKey, draftNodes, draftEdges, formatMessage, graphKind, isCurrentTemplateRequest, projectKey, setGraphEditStatus, translate])

  const handleWorkflowTemplateDryRun = useCallback(async () => {
    const workflowName = activeTemplateKey.trim()
    if (!workflowName) {
      window.alert(translate('graphPage.error.selectTemplate'))
      return
    }
    const requestEpoch = templateRequestEpochRef.current
    setTemplateDryRunBusy(true)
    try {
      const result = await runWorkflow(workflowName, {}, { dryRun: true })
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      const summary = summarizeWorkflowDryRunResult(result)
      setTemplateDryRunResult(result)
      setGraphEditStatus(formatMessage('graphPage.status.workflowDryRunLoaded', {
        workflowName,
        configVersion: formatWorkflowRunScalar(summary.configVersion),
        readiness: formatWorkflowRunScalar(summary.readiness),
        writesBlocked: formatWorkflowRunScalar(summary.writesBlocked),
      }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.workflowDryRunFailed')
      setGraphEditStatus(formatMessage('graphPage.error.workflowDryRunFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.workflowDryRunFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, workflowName)) setTemplateDryRunBusy(false)
    }
  }, [activeTemplateKey, formatMessage, isCurrentTemplateRequest, setGraphEditStatus, translate])

  const handleRefreshWorkflowTemplateStages = useCallback(async () => {
    if (!activeTemplateKey) return
    const requestEpoch = templateRequestEpochRef.current
    setTemplateStageBusy(true)
    try {
      await loadWorkflowTemplateStageAudit(activeTemplateKey, requestEpoch)
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      setGraphEditStatus(formatMessage('graphPage.status.templateStageAuditLoaded', { templateKey: activeTemplateKey }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateStageAuditLoadFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateStageAuditLoadFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateStageAuditLoadFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) setTemplateStageBusy(false)
    }
  }, [activeTemplateKey, formatMessage, isCurrentTemplateRequest, loadWorkflowTemplateStageAudit, setGraphEditStatus, translate])

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
    const requestEpoch = templateRequestEpochRef.current
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
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      setTemplateStageAuditSummary(buildTemplateStageAuditSummary(response))
      await loadWorkflowTemplateStageAudit(workflowName, requestEpoch)
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      setGraphEditStatus(formatMessage('graphPage.status.templateStageDraftSaved', {
        next: response.next_version ?? '-',
        requiresPublish: String(Boolean(response.version_summary?.requires_publish)),
      }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateStageSaveFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateStageSaveFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateStageSaveFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, workflowName)) setTemplateStageBusy(false)
    }
  }, [activeTemplateKey, draftNodes, draftEdges, formatMessage, graphKind, isCurrentTemplateRequest, loadWorkflowTemplateStageAudit, projectKey, setGraphEditStatus, translate])

  const handlePromoteWorkflowTemplateStage = useCallback(async (
    fromStage: Extract<WorkflowTemplateStageName, 'draft' | 'staging'>,
    toStage: Extract<WorkflowTemplateStageName, 'staging' | 'active'>,
  ) => {
    const workflowName = activeTemplateKey.trim()
    if (!workflowName) {
      window.alert(translate('graphPage.error.selectTemplate'))
      return
    }
    const requestEpoch = templateRequestEpochRef.current
    setTemplateStageBusy(true)
    try {
      const response = await promoteWorkflowTemplate(workflowName, {
        project_key: projectKey,
        from_stage: fromStage,
        to_stage: toStage,
      })
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      setTemplateStageAuditSummary(buildTemplateStageAuditSummary(response))
      await loadWorkflowTemplateStageAudit(workflowName, requestEpoch)
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      setGraphEditStatus(formatMessage('graphPage.status.templateStagePromoted', {
        fromStage,
        toStage,
        next: response.next_version ?? '-',
        requiresPublish: String(Boolean(response.version_summary?.requires_publish)),
      }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateStagePromoteFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateStagePromoteFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateStagePromoteFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, workflowName)) setTemplateStageBusy(false)
    }
  }, [activeTemplateKey, formatMessage, isCurrentTemplateRequest, loadWorkflowTemplateStageAudit, projectKey, setGraphEditStatus, translate])

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
    const requestEpoch = templateRequestEpochRef.current
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
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      setTemplateRollbackPreview(response)
      setGraphEditStatus(formatMessage('graphPage.status.templateRollbackPreviewLoaded', {
        targetStage: templateRollbackDraft.targetStage,
        targetVersion,
        canExecute: String(Boolean(response.rollback_plan?.can_execute ?? response.rollback_plan?.executable)),
        willMutate: String(Boolean(response.rollback_plan?.will_mutate)),
      }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateRollbackPreviewFailed')
      setTemplateRollbackError(message)
      setGraphEditStatus(formatMessage('graphPage.error.templateRollbackPreviewFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, workflowName)) setTemplateRollbackBusy(false)
    }
  }, [activeTemplateKey, formatMessage, isCurrentTemplateRequest, projectKey, setGraphEditStatus, templateRollbackDraft, translate])

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
    const requestEpoch = templateRequestEpochRef.current
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
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      setTemplateRollbackPreview(response)
      setTemplateStageAuditSummary(buildTemplateStageAuditSummary(response))
      await loadWorkflowTemplateStageAudit(workflowName, requestEpoch)
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      setGraphEditStatus(formatMessage('graphPage.status.templateRollbackApplied', {
        targetStage: templateRollbackDraft.targetStage,
        targetVersion,
        next: response.next_version ?? '-',
      }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, workflowName)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateRollbackApplyFailed')
      setTemplateRollbackError(message)
      setGraphEditStatus(formatMessage('graphPage.error.templateRollbackApplyFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, workflowName)) setTemplateRollbackBusy(false)
    }
  }, [activeTemplateKey, formatMessage, isCurrentTemplateRequest, loadWorkflowTemplateStageAudit, projectKey, setGraphEditStatus, templateRollbackDraft, translate])

  const handleCreateTemplate = useCallback(async () => {
    const name = templateNameDraft.trim()
    if (!name) return
    const requestEpoch = templateRequestEpochRef.current
    setTemplateBusy(true)
    try {
      const templateId = name.replace(/\s+/g, '_')
      await createWorkflowGraphTemplate({
        template_id: templateId,
        name,
        dsl: { nodes: draftNodes, edges: draftEdges },
      })
      if (!isCurrentTemplateRequest(requestEpoch)) return
      await loadTemplateList()
      if (!isCurrentTemplateRequest(requestEpoch)) return
      setTemplateNameDraft('')
      setGraphEditStatus(formatMessage('graphPage.status.templateCreated', { name }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateCreateFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateCreateFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateCreateFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch)) setTemplateBusy(false)
    }
  }, [draftEdges, draftNodes, formatMessage, isCurrentTemplateRequest, loadTemplateList, setGraphEditStatus, setTemplateBusy, templateNameDraft, translate])

  const handleRenameTemplate = useCallback(async () => {
    if (!activeTemplateKey) return
    const name = renameTemplateDraft.trim()
    if (!name) return
    const requestEpoch = templateRequestEpochRef.current
    setTemplateBusy(true)
    try {
      await updateWorkflowGraphTemplate(activeTemplateKey, { name })
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      await loadTemplateList()
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      setRenameTemplateDraft('')
      setGraphEditStatus(formatMessage('graphPage.status.templateRenamed', { name }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateRenameFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateRenameFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateRenameFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) setTemplateBusy(false)
    }
  }, [activeTemplateKey, formatMessage, isCurrentTemplateRequest, loadTemplateList, renameTemplateDraft, setGraphEditStatus, setTemplateBusy, translate])

  const handleDeleteTemplate = useCallback(async () => {
    if (!activeTemplateKey) return
    const requestEpoch = templateRequestEpochRef.current
    setTemplateBusy(true)
    try {
      await deleteWorkflowGraphTemplate(activeTemplateKey)
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      setGraphEditStatus(formatMessage('graphPage.status.templateDeleted', { templateKey: activeTemplateKey }))
      selectTemplate('')
      await loadTemplateList()
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.templateDeleteFailed')
      setGraphEditStatus(formatMessage('graphPage.error.templateDeleteFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.templateDeleteFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) setTemplateBusy(false)
    }
  }, [activeTemplateKey, formatMessage, isCurrentTemplateRequest, loadTemplateList, selectTemplate, setGraphEditStatus, setTemplateBusy, translate])

  const handleSaveVersion = useCallback(async () => {
    if (!activeTemplateKey) {
      window.alert(translate('graphPage.error.selectTemplate'))
      return
    }
    const versionName = versionNameDraft.trim() || `v-${new Date().toISOString()}`
    const requestEpoch = templateRequestEpochRef.current
    setTemplateBusy(true)
    try {
      if (viewSpec !== undefined && !normalizedViewSpec) {
        setGraphEditStatus(formatMessage('graphPage.error.projectViewSchemaInvalid', {}))
        return
      }
      await createWorkflowGraphTemplateVersion(activeTemplateKey, {
        version_id: versionName,
        dsl: {
          nodes: draftNodes,
          edges: draftEdges,
          ...(viewSpec !== undefined && normalizedViewSpec ? { project_view: normalizedViewSpec } : {}),
        },
      })
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      await loadVersionList(activeTemplateKey, requestEpoch)
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      setVersionNameDraft('')
      setGraphEditStatus(formatMessage('graphPage.status.versionSaved', { versionName }))
      markDraftSaved()
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.versionSaveFailed')
      setGraphEditStatus(formatMessage('graphPage.error.versionSaveFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.versionSaveFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) setTemplateBusy(false)
    }
  }, [activeTemplateKey, draftEdges, draftNodes, formatMessage, isCurrentTemplateRequest, loadVersionList, markDraftSaved, normalizedViewSpec, setGraphEditStatus, setTemplateBusy, translate, versionNameDraft, viewSpec])

  const handleLoadVersion = useCallback(async () => {
    if (!activeTemplateKey || !activeVersionKey) return
    const requestEpoch = templateRequestEpochRef.current
    setTemplateBusy(true)
    try {
      const raw = await getWorkflowGraphTemplateVersion(activeTemplateKey, activeVersionKey)
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      const versionGraph = readTemplateVersionGraph(raw)
      if (versionGraph.kind === 'invalid-project-view') {
        onLoadViewSpec?.(null)
        setGraphEditStatus(formatMessage('graphPage.error.projectViewSchemaInvalid', {}))
        return
      }
      if (versionGraph.kind === 'project-view') {
        onLoadViewSpec?.(versionGraph.spec)
        setGraphEditStatus(formatMessage('graphPage.status.versionLoaded', { versionKey: activeVersionKey }))
        return
      }
      onLoadViewSpec?.(null)
      if (!versionGraph.nodes.length && !versionGraph.edges.length) {
        window.alert(translate('graphPage.status.versionLoadedEmpty'))
      }
      replaceDraft(versionGraph.nodes, versionGraph.edges, { markAsDirty: true })
      setGraphEditStatus(formatMessage('graphPage.status.versionLoaded', { versionKey: activeVersionKey }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.versionLoadFailed')
      setGraphEditStatus(formatMessage('graphPage.error.versionLoadFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.versionLoadFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) setTemplateBusy(false)
    }
  }, [activeTemplateKey, activeVersionKey, formatMessage, isCurrentTemplateRequest, onLoadViewSpec, replaceDraft, setGraphEditStatus, setTemplateBusy, translate])

  const handleActivateVersion = useCallback(async () => {
    if (!activeTemplateKey || !activeVersionKey) return
    const requestEpoch = templateRequestEpochRef.current
    setTemplateBusy(true)
    try {
      await activateWorkflowGraphTemplateVersion(activeTemplateKey, activeVersionKey)
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      await loadVersionList(activeTemplateKey, requestEpoch)
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      setGraphEditStatus(formatMessage('graphPage.status.versionActivated', { versionKey: activeVersionKey }))
    } catch (error) {
      if (!isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) return
      const message = error instanceof Error ? error.message : translate('graphPage.error.versionActivateFailed')
      setGraphEditStatus(formatMessage('graphPage.error.versionActivateFailedWithMessage', { message }))
      window.alert(formatMessage('graphPage.error.versionActivateFailedWithMessage', { message }))
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, activeTemplateKey)) setTemplateBusy(false)
    }
  }, [activeTemplateKey, activeVersionKey, formatMessage, isCurrentTemplateRequest, loadVersionList, setGraphEditStatus, setTemplateBusy, translate])

  const handleSaveProjectView = useCallback(async (name: string): Promise<{ templateKey: string; versionKey: string } | null> => {
    if (viewSpec === undefined) {
      setGraphEditStatus(formatMessage('graphPage.error.projectViewSpecMissing', {}))
      return null
    }
    if (!normalizedViewSpec) {
      setGraphEditStatus(formatMessage('graphPage.error.projectViewSchemaInvalid', {}))
      return null
    }

    const displayName = name.trim()
    let templateKey = activeTemplateKeyRef.current || activeTemplateKey
    if (!displayName && !templateKey) {
      setGraphEditStatus(formatMessage('graphPage.error.projectViewTemplateIdentityMissing', {}))
      return null
    }

    const requestEpoch = templateRequestEpochRef.current
    let failureStage = 'project_view.save_failed'
    const reportFailure = (stage: string, error?: unknown) => {
      if (!isCurrentTemplateRequest(requestEpoch, templateKey)) return
      const detail = error instanceof Error ? error.message : error === undefined ? '' : String(error)
      setGraphEditStatus(formatMessage('graphPage.error.projectViewSaveFailed', {
        stage,
        message: detail,
      }))
    }
    const bindTemplate = (key: string) => {
      templateKey = key
      activeTemplateKeyRef.current = key
      setActiveTemplateKey(key)
      setActiveVersionKey('')
      setVersionItems([])
      setTemplateStageItems([])
      setTemplateStageAuditSummary(null)
      setTemplateDiffPreview(null)
      setTemplateDryRunResult(null)
      setTemplateRollbackPreview(null)
      setTemplateRollbackError('')
    }

    setTemplateBusy(true)
    try {
      if (!templateKey) {
        const requestedTemplateKey = `view-${window.crypto.randomUUID()}`
        failureStage = 'project_view.create_template_failed'
        const created = await createWorkflowGraphTemplate({
          template_id: requestedTemplateKey,
          name: displayName,
          dsl: {
            nodes: draftNodes,
            edges: draftEdges,
            project_view: normalizedViewSpec,
          },
        })
        if (!isCurrentTemplateRequest(requestEpoch)) {
          reportFailure('project_view.create_template_stale')
          return null
        }
        bindTemplate(created.template?.template_id || requestedTemplateKey)
      }

      const requestedVersionKey = window.crypto.randomUUID()
      failureStage = 'project_view.create_version_failed'
      const version = await createWorkflowGraphTemplateVersion(templateKey, {
        version_id: requestedVersionKey,
        dsl: {
          nodes: draftNodes,
          edges: draftEdges,
          project_view: normalizedViewSpec,
        },
      })
      if (!isCurrentTemplateRequest(requestEpoch, templateKey)) {
        reportFailure('project_view.create_version_stale')
        return null
      }
      const versionKey = version.version_id || requestedVersionKey
      setActiveVersionKey(versionKey)

      failureStage = 'project_view.activate_version_failed'
      await activateWorkflowGraphTemplateVersion(templateKey, versionKey)
      if (!isCurrentTemplateRequest(requestEpoch, templateKey)) {
        reportFailure('project_view.activate_version_stale')
        return null
      }

      failureStage = 'project_view.refresh_templates_failed'
      await queryClient.fetchQuery({
        ...projectGraphTemplatesQueryOptions(projectKey),
        staleTime: 0,
      })
      if (!isCurrentTemplateRequest(requestEpoch, templateKey)) {
        reportFailure('project_view.refresh_templates_stale')
        return null
      }
      failureStage = 'project_view.refresh_versions_failed'
      await loadVersionList(templateKey, requestEpoch)
      if (!isCurrentTemplateRequest(requestEpoch, templateKey)) {
        reportFailure('project_view.refresh_versions_stale')
        return null
      }

      failureStage = 'project_view.finalize_failed'
      markDraftSaved()
      setGraphEditStatus(formatMessage('graphPage.status.projectViewSaved', {}))
      return { templateKey, versionKey }
    } catch (error) {
      reportFailure(failureStage, error)
      return null
    } finally {
      if (isCurrentTemplateRequest(requestEpoch, templateKey)) setTemplateBusy(false)
    }
  }, [activeTemplateKey, draftEdges, draftNodes, formatMessage, isCurrentTemplateRequest, loadVersionList, markDraftSaved, normalizedViewSpec, projectKey, queryClient, setGraphEditStatus, setTemplateBusy, viewSpec])

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
    handleSaveProjectView,
    handleLoadVersion,
    handleActivateVersion,
  }
}

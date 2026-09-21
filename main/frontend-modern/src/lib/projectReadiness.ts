import type { MessageKey } from '../app/platform/i18n'
import type { ProjectItem } from './types'

export type ProjectReadinessStatus = 'ready' | 'blocked' | 'unknown'

export type ProjectReadinessCheck = {
  labelKey: MessageKey
  status: ProjectReadinessStatus
  evidenceKey: MessageKey
  evidenceValues?: Record<string, string | number>
}

export type ProjectReadinessAction = {
  labelKey: MessageKey
  detailKey: MessageKey
  detailValues: Record<string, string | number>
  targetKey: MessageKey
  targetHash: '#projects-readiness' | '#projects-list'
  actionPriority: 'low' | 'medium' | 'high'
}

export type ProjectReadiness = {
  status: ProjectReadinessStatus
  summaryKey: MessageKey
  summaryValues: Record<string, string | number>
  nextAction: ProjectReadinessAction
  checks: ProjectReadinessCheck[]
}

export const READINESS_STATUS_LABEL_KEY_BY_STATUS: Record<ProjectReadinessStatus, MessageKey> = {
  ready: 'projects.readiness.status.ready',
  blocked: 'projects.readiness.status.blocked',
  unknown: 'projects.readiness.status.unknown',
}

const READINESS_SUMMARY_KEY_BY_STATUS: Record<ProjectReadinessStatus, MessageKey> = {
  ready: 'projects.readiness.summary.ready',
  blocked: 'projects.readiness.summary.blocked',
  unknown: 'projects.readiness.summary.unknown',
}

const READINESS_ACTION_LABEL_KEY_BY_STATUS: Record<ProjectReadinessStatus, MessageKey> = {
  ready: 'projects.readiness.action.ready',
  blocked: 'projects.readiness.action.blocked',
  unknown: 'projects.readiness.action.unknown',
}

const READINESS_ACTION_DETAIL_KEY_BY_STATUS: Record<ProjectReadinessStatus, MessageKey> = {
  ready: 'projects.readiness.actionDetail.ready',
  blocked: 'projects.readiness.actionDetail.blocked',
  unknown: 'projects.readiness.actionDetail.unknown',
}

const READINESS_ACTION_TARGET_KEY_BY_STATUS: Record<ProjectReadinessStatus, MessageKey> = {
  ready: 'projects.readiness.actionTarget.ready',
  blocked: 'projects.readiness.actionTarget.blocked',
  unknown: 'projects.readiness.actionTarget.unknown',
}

const READINESS_ACTION_PRIORITY_BY_STATUS: Record<ProjectReadinessStatus, ProjectReadinessAction['actionPriority']> = {
  ready: 'low',
  blocked: 'high',
  unknown: 'medium',
}

const READINESS_CHECK_LABEL_KEYS: MessageKey[] = [
  'projects.readiness.check.projectRecord',
  'projects.readiness.check.enabled',
  'projects.readiness.check.schema',
  'projects.readiness.check.activeMarker',
]

function getReadinessSummaryStatus(checks: ProjectReadinessCheck[]): ProjectReadinessStatus {
  if (checks.some((check) => check.status === 'blocked')) return 'blocked'
  if (checks.some((check) => check.status === 'unknown')) return 'unknown'
  return 'ready'
}

function buildNextAction(status: ProjectReadinessStatus, projectKey: string): ProjectReadinessAction {
  return {
    labelKey: READINESS_ACTION_LABEL_KEY_BY_STATUS[status],
    detailKey: READINESS_ACTION_DETAIL_KEY_BY_STATUS[status],
    detailValues: { projectKey: projectKey || 'unknown' },
    targetKey: READINESS_ACTION_TARGET_KEY_BY_STATUS[status],
    targetHash: status === 'blocked' ? '#projects-list' : '#projects-readiness',
    actionPriority: READINESS_ACTION_PRIORITY_BY_STATUS[status],
  }
}

function buildLoadingReadiness(projectKey: string, evidenceKey: MessageKey): ProjectReadiness {
  const fallbackProjectKey = projectKey || 'unknown'
  const checks: ProjectReadinessCheck[] = READINESS_CHECK_LABEL_KEYS.map((labelKey) => ({
    labelKey,
    status: 'unknown',
    evidenceKey,
    evidenceValues: { projectKey: fallbackProjectKey },
  }))

  return {
    status: 'unknown',
    summaryKey: READINESS_SUMMARY_KEY_BY_STATUS.unknown,
    summaryValues: { projectKey: fallbackProjectKey },
    nextAction: buildNextAction('unknown', fallbackProjectKey),
    checks,
  }
}

export function buildProjectReadiness({
  rows,
  projectKey,
  loading,
  error,
}: {
  rows?: ProjectItem[]
  projectKey: string
  loading: boolean
  error: boolean
}): ProjectReadiness {
  const currentProjectKey = projectKey.trim()
  const fallbackProjectKey = currentProjectKey || 'unknown'

  if (loading) return buildLoadingReadiness(fallbackProjectKey, 'projects.readiness.evidence.loading')
  if (error || !rows) return buildLoadingReadiness(fallbackProjectKey, 'projects.readiness.evidence.listUnavailable')

  const selectedProject = rows.find((item) => item.project_key === currentProjectKey)
  const fallbackActiveProject = selectedProject ? null : rows.find((item) => item.is_active)
  const inspectedProject = selectedProject || fallbackActiveProject || null
  const inspectedProjectKey = inspectedProject?.project_key || fallbackProjectKey

  const checks: ProjectReadinessCheck[] = [
    !currentProjectKey
      ? {
          labelKey: 'projects.readiness.check.projectRecord',
          status: 'unknown',
          evidenceKey: 'projects.readiness.evidence.noProjectKey',
        }
      : selectedProject
        ? {
            labelKey: 'projects.readiness.check.projectRecord',
            status: 'ready',
            evidenceKey: 'projects.readiness.evidence.projectFound',
            evidenceValues: { projectKey: currentProjectKey },
          }
        : fallbackActiveProject
          ? {
              labelKey: 'projects.readiness.check.projectRecord',
              status: 'blocked',
              evidenceKey: 'projects.readiness.evidence.fallbackActive',
              evidenceValues: { projectKey: currentProjectKey, fallbackProjectKey: fallbackActiveProject.project_key },
            }
          : {
              labelKey: 'projects.readiness.check.projectRecord',
              status: 'blocked',
              evidenceKey: 'projects.readiness.evidence.projectMissing',
              evidenceValues: { projectKey: currentProjectKey },
            },
    inspectedProject && typeof inspectedProject.enabled === 'boolean'
      ? {
          labelKey: 'projects.readiness.check.enabled',
          status: inspectedProject.enabled ? 'ready' : 'blocked',
          evidenceKey: inspectedProject.enabled ? 'projects.readiness.evidence.enabledTrue' : 'projects.readiness.evidence.enabledFalse',
          evidenceValues: { projectKey: inspectedProjectKey },
        }
      : {
          labelKey: 'projects.readiness.check.enabled',
          status: 'unknown',
          evidenceKey: 'projects.readiness.evidence.enabledUnknown',
          evidenceValues: { projectKey: inspectedProjectKey },
        },
    inspectedProject?.schema_name?.trim()
      ? {
          labelKey: 'projects.readiness.check.schema',
          status: 'ready',
          evidenceKey: 'projects.readiness.evidence.schemaKnown',
          evidenceValues: { schemaName: inspectedProject.schema_name },
        }
      : {
          labelKey: 'projects.readiness.check.schema',
          status: 'unknown',
          evidenceKey: 'projects.readiness.evidence.schemaMissing',
          evidenceValues: { projectKey: inspectedProjectKey },
        },
    inspectedProject && typeof inspectedProject.is_active === 'boolean'
      ? {
          labelKey: 'projects.readiness.check.activeMarker',
          status: inspectedProject.is_active && inspectedProject.project_key === currentProjectKey ? 'ready' : 'blocked',
          evidenceKey: inspectedProject.is_active && inspectedProject.project_key === currentProjectKey
            ? 'projects.readiness.evidence.activeTrue'
            : 'projects.readiness.evidence.activeFalse',
          evidenceValues: { projectKey: inspectedProjectKey, currentProjectKey: fallbackProjectKey },
        }
      : {
          labelKey: 'projects.readiness.check.activeMarker',
          status: 'unknown',
          evidenceKey: 'projects.readiness.evidence.activeUnknown',
          evidenceValues: { projectKey: inspectedProjectKey },
        },
  ]

  const status = getReadinessSummaryStatus(checks)
  return {
    status,
    summaryKey: READINESS_SUMMARY_KEY_BY_STATUS[status],
    summaryValues: { projectKey: fallbackProjectKey },
    nextAction: buildNextAction(status, fallbackProjectKey),
    checks,
  }
}

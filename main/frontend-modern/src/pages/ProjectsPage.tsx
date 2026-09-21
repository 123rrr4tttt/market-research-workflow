import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ClipboardCopy, CopyPlus, Edit3, ExternalLink, HardDriveDownload, RefreshCw, ShieldCheck, Trash2 } from 'lucide-react'
import { activateProject, archiveProject, autoCreateProject, createProject, deleteProject, listProjects, restoreProject, setProjectKey, updateProject } from '../lib/api'
import { translate, useAppLocale } from '../app/platform/i18n'
import { queryKeys } from '../lib/queryKeys'
import { buildProjectReadiness, READINESS_STATUS_LABEL_KEY_BY_STATUS } from '../lib/projectReadiness'

type ProjectsPageProps = {
  projectKey: string
  onProjectChange: (key: string) => void
}

function formatProjectTemplate(template: string, values: Record<string, string | number>) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

export default function ProjectsPage({ projectKey, onProjectChange }: ProjectsPageProps) {
  const locale = useAppLocale()
  const queryClient = useQueryClient()
  const [newProjectKey, setNewProjectKey] = useState('')
  const [newProjectName, setNewProjectName] = useState('')
  const [templateProjectKey, setTemplateProjectKey] = useState('demo_proj')
  const [llmServiceName, setLlmServiceName] = useState('keyword_generation')
  const [llmPromptTemplate, setLlmPromptTemplate] = useState('')
  const [editingProject, setEditingProject] = useState<{ key: string; name: string } | null>(null)
  const [readinessActionMessage, setReadinessActionMessage] = useState('')
  const llmServiceOptions = [
    'prompt_factory',
    'keyword_generation',
    'social_keyword_generation',
    'policy_extraction',
    'market_info_extraction',
    'entities_relations_extraction',
    'site_entry_classification',
    'document_classification',
  ]

  const projects = useQuery({ queryKey: queryKeys.projects.all(), queryFn: listProjects })
  const currentProjectMarker = formatProjectTemplate(translate(locale, 'projects.status.currentMarker'), {
    status: translate(locale, 'projects.status.current'),
  })
  const readiness = buildProjectReadiness({
    rows: projects.data,
    projectKey,
    loading: projects.isLoading,
    error: projects.isError,
  })

  const buildReadinessActionContext = () => ({
    schema_version: 'projects.readiness.quick_action.v1',
    project_key: projectKey || 'unknown',
    readiness: readiness.status,
    action_priority: readiness.nextAction.actionPriority,
    target_hash: readiness.nextAction.targetHash,
    next_action: {
      label_key: readiness.nextAction.labelKey,
      detail_key: readiness.nextAction.detailKey,
      detail_values: readiness.nextAction.detailValues,
      target_key: readiness.nextAction.targetKey,
    },
    checks: readiness.checks.map((check) => ({
      label_key: check.labelKey,
      status: check.status,
      evidence_key: check.evidenceKey,
      evidence_values: check.evidenceValues || {},
    })),
  })

  const copyReadinessActionContext = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(buildReadinessActionContext(), null, 2))
      setReadinessActionMessage(translate(locale, 'projects.readiness.message.contextCopied'))
    } catch {
      setReadinessActionMessage(translate(locale, 'projects.readiness.message.contextCopyFailed'))
    }
  }

  const openReadinessActionTarget = () => {
    const selector = readiness.nextAction.targetHash === '#projects-list'
      ? '[data-testid="projects-list"]'
      : '[data-testid="projects-readiness-panel"]'
    globalThis.document?.querySelector(selector)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setReadinessActionMessage(translate(locale, 'projects.readiness.message.targetOpened'))
  }

  const refreshReadinessActionStatus = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.projects.all() })
    setReadinessActionMessage(translate(locale, 'projects.readiness.message.statusRefreshed'))
  }

  const actionMutation = useMutation({
    mutationFn: async (payload: { kind: 'create' | 'archive' | 'restore' | 'delete' | 'update' | 'activateProject'; key?: string; name?: string }) => {
      if (payload.kind === 'create') return createProject({ project_key: newProjectKey.trim(), name: newProjectName.trim(), enabled: true })
      if (!payload.key) throw new Error(translate(locale, 'projects.error.missingProjectKey'))
      if (payload.kind === 'archive') return archiveProject(payload.key)
      if (payload.kind === 'restore') return restoreProject(payload.key)
      if (payload.kind === 'delete') return deleteProject(payload.key, true)
      if (payload.kind === 'activateProject') {
        const next = setProjectKey(payload.key)
        await activateProject(next)
        onProjectChange(next)
        return { ok: true }
      }
      return updateProject(payload.key, { name: payload.name })
    },
    onSuccess: async () => {
      setNewProjectKey('')
      setNewProjectName('')
      setEditingProject(null)
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects.all() })
    },
  })

  const autoCreateMutation = useMutation({
    mutationFn: async () =>
      autoCreateProject({
        project_name: newProjectName.trim(),
        project_key: newProjectKey.trim() || null,
        template_project_key: templateProjectKey,
        activate: true,
        copy_initial_data: true,
        llm_configs: llmPromptTemplate.trim()
          ? [
              {
                service_name: llmServiceName.trim() || 'keyword_generation',
                user_prompt_template: llmPromptTemplate.trim(),
                enabled: true,
              },
            ]
          : [],
      }),
    onSuccess: async (data) => {
      setNewProjectKey('')
      setNewProjectName('')
      setLlmPromptTemplate('')
      const next = data?.project_key ? setProjectKey(data.project_key) : null
      if (next) onProjectChange(next)
      await queryClient.invalidateQueries({ queryKey: queryKeys.projects.all() })
    },
  })

  return (
    <div className="content-stack projects-page">
      <section className="panel">
        <div className="panel-header"><h2><CopyPlus size={15} />{translate(locale, 'projects.create.title')}</h2></div>
        <div className="form-grid cols-3">
          <label><span>{translate(locale, 'projects.field.projectKey')}</span><input value={newProjectKey} onChange={(e) => setNewProjectKey(e.target.value)} placeholder={translate(locale, 'projects.placeholder.projectKey')} /></label>
          <label><span>{translate(locale, 'projects.field.name')}</span><input value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)} placeholder={translate(locale, 'projects.placeholder.projectName')} /></label>
          <div className="inline-actions">
            <button disabled={actionMutation.isPending || !newProjectKey.trim() || !newProjectName.trim()} onClick={() => actionMutation.mutate({ kind: 'create' })}><CopyPlus size={14} />{translate(locale, 'projects.action.create')}</button>
          </div>
        </div>
        <div className="form-grid cols-3" style={{ marginTop: 12 }}>
          <label>
            <span>{translate(locale, 'projects.field.templateProject')}</span>
            <select value={templateProjectKey} onChange={(e) => setTemplateProjectKey(e.target.value)}>
              <option value="demo_proj">demo_proj</option>
              <option value="online_lottery">online_lottery</option>
              <option value="business_survey">business_survey</option>
            </select>
          </label>
          <label>
            <span>{translate(locale, 'projects.field.llmServiceName')}</span>
            <select value={llmServiceName} onChange={(e) => setLlmServiceName(e.target.value)}>
              {llmServiceOptions.map((service) => (
                <option key={service} value={service}>{service}</option>
              ))}
            </select>
          </label>
          <div className="inline-actions">
            <button
              disabled={autoCreateMutation.isPending || !newProjectName.trim()}
              onClick={() => autoCreateMutation.mutate()}
            >
              <CopyPlus size={14} />{translate(locale, 'projects.action.createFromTemplate')}
            </button>
          </div>
        </div>
        <div className="form-grid cols-1" style={{ marginTop: 12 }}>
          <label>
            <span>{translate(locale, 'projects.field.llmPromptTemplate')}</span>
            <textarea value={llmPromptTemplate} onChange={(e) => setLlmPromptTemplate(e.target.value)} placeholder={translate(locale, 'projects.placeholder.llmPromptTemplate')} />
          </label>
        </div>
      </section>

      <section className="panel" aria-label={translate(locale, 'projects.readiness.title')} data-testid="projects-readiness-panel">
        <div className="panel-header">
          <h2><ShieldCheck size={15} />{translate(locale, 'projects.readiness.title')}</h2>
          <span className="status-line">
            {translate(locale, READINESS_STATUS_LABEL_KEY_BY_STATUS[readiness.status])}
          </span>
        </div>
        <p className="status-line">
          {formatProjectTemplate(translate(locale, readiness.summaryKey), readiness.summaryValues)}
        </p>
        <div className="status-line" data-testid="projects-readiness-action-card">
          <strong>{translate(locale, 'projects.readiness.field.nextAction')}: </strong>
          <span data-testid="projects-readiness-action-label">{translate(locale, readiness.nextAction.labelKey)}</span>
          <span> - {formatProjectTemplate(translate(locale, readiness.nextAction.detailKey), readiness.nextAction.detailValues)}</span>
          <span className="status-line">
            {translate(locale, 'projects.readiness.field.actionPriority')}: {readiness.nextAction.actionPriority}
          </span>
          <span>{translate(locale, readiness.nextAction.targetKey)}</span>
          <div className="inline-actions">
            <button type="button" data-testid="projects-readiness-copy-action" onClick={() => void copyReadinessActionContext()}>
              <ClipboardCopy size={12} />{translate(locale, 'projects.readiness.action.copyContext')}
            </button>
            <button type="button" data-testid="projects-readiness-open-target" onClick={openReadinessActionTarget}>
              <ExternalLink size={12} />{translate(locale, 'projects.readiness.action.openTarget')}
            </button>
            <button type="button" data-testid="projects-readiness-refresh-status" onClick={() => void refreshReadinessActionStatus()}>
              <RefreshCw size={12} />{translate(locale, 'projects.readiness.action.refreshStatus')}
            </button>
          </div>
          {readinessActionMessage && (
            <span data-testid="projects-readiness-action-status">{readinessActionMessage}</span>
          )}
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{translate(locale, 'projects.readiness.field.check')}</th>
                <th>{translate(locale, 'projects.readiness.field.status')}</th>
                <th>{translate(locale, 'projects.readiness.field.evidence')}</th>
              </tr>
            </thead>
            <tbody>
              {readiness.checks.map((check) => (
                <tr key={check.labelKey}>
                  <td>{translate(locale, check.labelKey)}</td>
                  <td>{translate(locale, READINESS_STATUS_LABEL_KEY_BY_STATUS[check.status])}</td>
                  <td>{formatProjectTemplate(translate(locale, check.evidenceKey), check.evidenceValues || {})}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel" data-testid="projects-list">
        <div className="panel-header"><h2><HardDriveDownload size={15} />{translate(locale, 'projects.list.title')}</h2><button onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.projects.all() })}><RefreshCw size={14} />{translate(locale, 'projects.action.refresh')}</button></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{translate(locale, 'projects.field.projectKey')}</th><th>{translate(locale, 'projects.field.name')}</th><th>{translate(locale, 'projects.field.schema')}</th><th>{translate(locale, 'projects.field.enabled')}</th><th>{translate(locale, 'projects.field.active')}</th><th>{translate(locale, 'projects.field.actions')}</th></tr></thead>
            <tbody>
              {(projects.data || []).map((item) => (
                <tr key={item.project_key}>
                  <td>{item.project_key}</td>
                  <td>
                    {editingProject?.key === item.project_key ? (
                      <input value={editingProject.name} onChange={(e) => setEditingProject({ key: item.project_key, name: e.target.value })} />
                    ) : (
                      item.name || '-'
                    )}
                  </td>
                  <td>{item.schema_name || '-'}</td>
                  <td>{item.enabled ? 'true' : 'false'}</td>
                  <td>{item.is_active ? 'true' : 'false'}{item.project_key === projectKey ? currentProjectMarker : ''}</td>
                  <td>
                    <div className="inline-actions">
                      <button disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ kind: 'activateProject', key: item.project_key })}>{translate(locale, 'projects.action.activate')}</button>
                      {editingProject?.key === item.project_key ? (
                        <button disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ kind: 'update', key: item.project_key, name: editingProject.name })}><Edit3 size={12} />{translate(locale, 'projects.action.save')}</button>
                      ) : (
                        <button onClick={() => setEditingProject({ key: item.project_key, name: item.name || '' })}><Edit3 size={12} />{translate(locale, 'projects.action.rename')}</button>
                      )}
                      {item.enabled ? (
                        <button disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ kind: 'archive', key: item.project_key })}><Archive size={12} />{translate(locale, 'projects.action.archive')}</button>
                      ) : (
                        <button disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ kind: 'restore', key: item.project_key })}><RefreshCw size={12} />{translate(locale, 'projects.action.restore')}</button>
                      )}
                      <button disabled={actionMutation.isPending} onClick={() => actionMutation.mutate({ kind: 'delete', key: item.project_key })}><Trash2 size={12} />{translate(locale, 'projects.action.delete')}</button>
                    </div>
                  </td>
                </tr>
              ))}
              {!projects.data?.length && <tr><td colSpan={6} className="empty-cell">{translate(locale, 'projects.list.empty')}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, CircleDashed, Clock3, GitBranch, Play, RefreshCw } from 'lucide-react'
import {
  deployCrawlerProject,
  getCrawlerProjectDetail,
  importCrawlerProject,
  listCrawlerDeployRuns,
  listCrawlerProjects,
  rollbackCrawlerProject,
} from '../lib/api'
import { translate, useAppLocale, type MessageKey } from '../app/platform/i18n'
import { getLocalJson, setLocalJson } from '../lib/localStore'
import { queryKeys } from '../lib/queryKeys'
import type { CrawlerDeployRunItem, CrawlerProjectItem } from '../lib/types'

type Props = {
  projectKey: string
}

type Draft = {
  crawlerProjectKey: string
  name: string
  repoUrl: string
  branch: string
  providerHint: 'auto' | 'scrapy' | 'crawlee'
  description: string
  enableNow: boolean
}

type CrawlerManageStateCache = {
  draft: Draft
  selectedCrawlerProjectKey: string
  deployVersion: string
  rollbackVersion: string
  plannerMode: 'heuristic' | 'manual'
}

type PlannerMode = CrawlerManageStateCache['plannerMode']
type TemplateValues = {
  [key: string]: string | number
}

function defaultDraft(): Draft {
  return {
    crawlerProjectKey: '',
    name: '',
    repoUrl: '',
    branch: 'main',
    providerHint: 'auto',
    description: '',
    enableNow: true,
  }
}

function summarizeRun(run?: Partial<CrawlerDeployRunItem> | null) {
  if (!run) return ''
  const fields: Array<[string, unknown]> = [
    ['id', run.id],
    ['action', run.action],
    ['status', run.status],
    ['requested_version', run.requested_version],
    ['from_version', run.from_version],
    ['to_version', run.to_version],
    ['external_job_id', run.external_job_id],
  ]
  return fields
    .filter(([, value]) => value !== null && value !== undefined && String(value) !== '')
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(' | ')
}

function formatCrawlerTemplate(template: string, values: TemplateValues) {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key: string) => String(values[key] ?? ''))
}

export default function CrawlerManagePage({ projectKey }: Props) {
  const storageKey = ['crawler_manage_state_v2', projectKey].join(':')
  const cached = getLocalJson(storageKey, null) as CrawlerManageStateCache | null
  const queryClient = useQueryClient()
  const locale = useAppLocale()
  const [draft, setDraft] = useState((): Draft => cached?.draft || defaultDraft())
  const [message, setMessage] = useState('')
  const [selectedCrawlerProjectKey, setSelectedCrawlerProjectKey] = useState(cached?.selectedCrawlerProjectKey || '')
  const [deployVersion, setDeployVersion] = useState(cached?.deployVersion || '')
  const [rollbackVersion, setRollbackVersion] = useState(cached?.rollbackVersion || '')
  const [plannerMode, setPlannerMode] = useState((): PlannerMode => cached?.plannerMode || 'heuristic')
  const t = (key: MessageKey, fallback?: string) => translate(locale, key, fallback)
  const tf = (key: MessageKey, values: TemplateValues, fallback?: string) =>
    formatCrawlerTemplate(t(key, fallback), values)

  useEffect(() => {
    const next = getLocalJson(storageKey, null) as CrawlerManageStateCache | null
    const timerId = window.setTimeout(() => {
      setDraft(next?.draft || defaultDraft())
      setSelectedCrawlerProjectKey(next?.selectedCrawlerProjectKey || '')
      setDeployVersion(next?.deployVersion || '')
      setRollbackVersion(next?.rollbackVersion || '')
      setPlannerMode(next?.plannerMode || 'heuristic')
    }, 0)
    return () => {
      window.clearTimeout(timerId)
    }
  }, [storageKey])

  const crawlerProjects = useQuery({
    queryKey: queryKeys.crawler.projects(projectKey),
    queryFn: () => listCrawlerProjects(),
    enabled: Boolean(projectKey),
  })

  const sortedProjects = useMemo(
    () => [...(crawlerProjects.data || [])].sort((a, b) => String(a.project_key).localeCompare(String(b.project_key))),
    [crawlerProjects.data],
  )
  const effectiveSelectedCrawlerProjectKey = useMemo(() => {
    if (!sortedProjects.length) return ''
    if (selectedCrawlerProjectKey && sortedProjects.some((item) => item.project_key === selectedCrawlerProjectKey)) {
      return selectedCrawlerProjectKey
    }
    return sortedProjects[0].project_key
  }, [selectedCrawlerProjectKey, sortedProjects])

  const crawlerDetail = useQuery({
    queryKey: queryKeys.crawler.projectDetail(projectKey, effectiveSelectedCrawlerProjectKey),
    queryFn: () => getCrawlerProjectDetail(effectiveSelectedCrawlerProjectKey),
    enabled: Boolean(projectKey && effectiveSelectedCrawlerProjectKey),
  })

  const deployRuns = useQuery({
    queryKey: queryKeys.crawler.deployRuns(projectKey, effectiveSelectedCrawlerProjectKey),
    queryFn: () => listCrawlerDeployRuns({ crawlerProjectKey: effectiveSelectedCrawlerProjectKey, limit: 100 }),
    enabled: Boolean(projectKey && effectiveSelectedCrawlerProjectKey),
  })

  const importMutation = useMutation({
    mutationFn: async () => {
      const repoUrl = draft.repoUrl.trim()
      if (!repoUrl) throw new Error(t('crawlerManagePage.error.missingGitUrl'))
      return importCrawlerProject({
        project_key: draft.crawlerProjectKey.trim() || null,
        name: draft.name.trim() || null,
        repo_url: repoUrl,
        branch: draft.branch.trim() || null,
        provider_hint: draft.providerHint,
        description: draft.description.trim() || null,
        enable_now: draft.enableNow,
      })
    },
    onSuccess: async (result) => {
      const nextKey = String(result?.project_key || '').trim()
      if (nextKey) setSelectedCrawlerProjectKey(nextKey)
      setMessage(nextKey ? tf('crawlerManagePage.message.importSuccessWithKey', { projectKey: nextKey }) : t('crawlerManagePage.message.importSuccess'))
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.projects(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.projectDetailBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.deployRunsBase(projectKey) }),
      ])
    },
    onError: (error) => {
      setMessage(tf('crawlerManagePage.message.importFailed', { message: error instanceof Error ? error.message : t('crawlerManagePage.error.unknown') }))
    },
  })

  const deployMutation = useMutation({
    mutationFn: async () => {
      if (!effectiveSelectedCrawlerProjectKey) throw new Error(t('crawlerManagePage.error.missingCrawlerProject'))
      return deployCrawlerProject(effectiveSelectedCrawlerProjectKey, {
        requested_version: deployVersion.trim() || null,
        planner_mode: plannerMode,
        async_mode: true,
      })
    },
    onSuccess: async (run) => {
      setMessage(tf('crawlerManagePage.message.deploySubmitted', { summary: summarizeRun(run) || t('crawlerManagePage.message.deployRunCreated') }))
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.projectDetail(projectKey, effectiveSelectedCrawlerProjectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.deployRuns(projectKey, effectiveSelectedCrawlerProjectKey) }),
      ])
    },
    onError: (error) => {
      setMessage(tf('crawlerManagePage.message.deployFailed', { message: error instanceof Error ? error.message : t('crawlerManagePage.error.unknown') }))
    },
  })

  const rollbackMutation = useMutation({
    mutationFn: async () => {
      if (!effectiveSelectedCrawlerProjectKey) throw new Error(t('crawlerManagePage.error.missingCrawlerProject'))
      return rollbackCrawlerProject(effectiveSelectedCrawlerProjectKey, {
        to_version: rollbackVersion.trim() || null,
        planner_mode: plannerMode,
        async_mode: true,
      })
    },
    onSuccess: async (run) => {
      setMessage(tf('crawlerManagePage.message.rollbackSubmitted', { summary: summarizeRun(run) || t('crawlerManagePage.message.rollbackRunCreated') }))
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.projectDetail(projectKey, effectiveSelectedCrawlerProjectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.deployRuns(projectKey, effectiveSelectedCrawlerProjectKey) }),
      ])
    },
    onError: (error) => {
      setMessage(tf('crawlerManagePage.message.rollbackFailed', { message: error instanceof Error ? error.message : t('crawlerManagePage.error.unknown') }))
    },
  })

  useEffect(() => {
    setLocalJson<CrawlerManageStateCache>(storageKey, {
      draft,
      selectedCrawlerProjectKey,
      deployVersion,
      rollbackVersion,
      plannerMode,
    })
  }, [storageKey, draft, selectedCrawlerProjectKey, deployVersion, rollbackVersion, plannerMode])

  const submitting = importMutation.isPending || deployMutation.isPending || rollbackMutation.isPending
  const detail = (crawlerDetail.data || null) as CrawlerProjectItem | null
  const detailSummary = detail
    ? tf('crawlerManagePage.detail.summary', {
        projectKey: detail.project_key,
        status: detail.status || '-',
        currentVersion: detail.current_version || '-',
        deployedVersion: detail.deployed_version || '-',
      })
    : t('crawlerManagePage.empty.selectProject')
  const detailRows = detail
    ? [
        [t('crawlerManagePage.field.projectKey'), detail.project_key],
        [t('crawlerManagePage.field.name'), detail.name || '-'],
        [t('crawlerManagePage.field.sourceUri'), detail.source_uri || '-'],
        [t('crawlerManagePage.field.provider'), detail.provider || '-'],
        [t('crawlerManagePage.field.status'), detail.status || '-'],
        [t('crawlerManagePage.field.currentVersion'), detail.current_version || '-'],
        [t('crawlerManagePage.field.deployedVersion'), detail.deployed_version || '-'],
        [t('crawlerManagePage.field.previousVersion'), detail.previous_version || '-'],
        [t('crawlerManagePage.field.updatedAt'), detail.updated_at || '-'],
      ]
    : []

  return (
    <div className="content-stack crawler-page">
      <section className="panel">
        <div className="panel-header">
          <h2><Bot size={15} />{t('crawlerManagePage.section.import')}</h2>
          <span className="status-line">{tf('crawlerManagePage.field.project', { projectKey })}</span>
        </div>
        <div className="form-grid cols-3" style={{ marginTop: 12 }}>
          <label>
            <span>{t('crawlerManagePage.field.crawlerProjectKey')}</span>
            <input
              value={draft.crawlerProjectKey}
              onChange={(e) => setDraft((prev) => ({ ...prev, crawlerProjectKey: e.target.value }))}
              placeholder={t('crawlerManagePage.placeholder.crawlerProjectKey')}
            />
          </label>
          <label>
            <span>{t('crawlerManagePage.field.name')}</span>
            <input
              value={draft.name}
              onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
              placeholder={t('crawlerManagePage.placeholder.name')}
            />
          </label>
          <label>
            <span>{t('crawlerManagePage.field.gitUrl')}</span>
            <input
              value={draft.repoUrl}
              onChange={(e) => setDraft((prev) => ({ ...prev, repoUrl: e.target.value }))}
              placeholder={t('crawlerManagePage.placeholder.gitUrl')}
            />
          </label>
          <label>
            <span>{t('crawlerManagePage.field.branchTag')}</span>
            <input
              value={draft.branch}
              onChange={(e) => setDraft((prev) => ({ ...prev, branch: e.target.value }))}
              placeholder={t('crawlerManagePage.placeholder.branchTag')}
            />
          </label>
          <label>
            <span>{t('crawlerManagePage.field.providerHint')}</span>
            <select
              value={draft.providerHint}
              onChange={(e) => setDraft((prev) => ({ ...prev, providerHint: e.target.value as Draft['providerHint'] }))}
            >
              <option value="auto">auto</option>
              <option value="scrapy">scrapy</option>
              <option value="crawlee">crawlee</option>
            </select>
          </label>
          <label>
            <span>{t('crawlerManagePage.field.description')}</span>
            <input
              value={draft.description}
              onChange={(e) => setDraft((prev) => ({ ...prev, description: e.target.value }))}
              placeholder={t('crawlerManagePage.placeholder.description')}
            />
          </label>
        </div>
        <div className="inline-actions" style={{ marginTop: 10 }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={draft.enableNow}
              onChange={(e) => setDraft((prev) => ({ ...prev, enableNow: e.target.checked }))}
            />
            {t('crawlerManagePage.control.enableNow')}
          </label>
          <button
            onClick={() => setMessage(t('crawlerManagePage.message.draftAutosaved'))}
            disabled={submitting}
            title={t('crawlerManagePage.tooltip.draftAutosave')}
          >
            <GitBranch size={14} />
            {t('crawlerManagePage.action.draftAutosave')}
          </button>
          <button onClick={() => importMutation.mutate()} disabled={submitting}><Play size={14} />{t('crawlerManagePage.action.importCrawlerProject')}</button>
          <button onClick={() => crawlerProjects.refetch()}><RefreshCw size={14} />{t('crawlerManagePage.action.refreshList')}</button>
        </div>
        <div className="form-grid cols-3" style={{ marginTop: 12 }}>
          <label>
            <span>{t('crawlerManagePage.field.selectedProject')}</span>
            <select
              value={effectiveSelectedCrawlerProjectKey}
              onChange={(e) => setSelectedCrawlerProjectKey(e.target.value)}
            >
              <option value="">{t('crawlerManagePage.empty.select')}</option>
              {sortedProjects.map((item) => (
                <option key={item.project_key} value={item.project_key}>
                  {item.project_key}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>{t('crawlerManagePage.field.deployVersion')}</span>
            <input
              value={deployVersion}
              onChange={(e) => setDeployVersion(e.target.value)}
              placeholder={t('crawlerManagePage.placeholder.deployVersion')}
            />
          </label>
          <label>
            <span>{t('crawlerManagePage.field.rollbackToVersion')}</span>
            <input
              value={rollbackVersion}
              onChange={(e) => setRollbackVersion(e.target.value)}
              placeholder={t('crawlerManagePage.placeholder.rollbackVersion')}
            />
          </label>
        </div>
        <div className="inline-actions" style={{ marginTop: 10 }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span>{t('crawlerManagePage.field.planner')}</span>
            <select value={plannerMode} onChange={(e) => setPlannerMode(e.target.value as PlannerMode)}>
              <option value="heuristic">heuristic</option>
              <option value="manual">manual</option>
            </select>
          </label>
          <button
            onClick={() => deployMutation.mutate()}
            disabled={submitting || !effectiveSelectedCrawlerProjectKey}
          >
            <Play size={14} />{t('crawlerManagePage.action.submitDeploy')}
          </button>
          <button
            onClick={() => rollbackMutation.mutate()}
            disabled={submitting || !effectiveSelectedCrawlerProjectKey}
          >
            <CircleDashed size={14} />{t('crawlerManagePage.action.submitRollback')}
          </button>
          <button onClick={() => { void crawlerDetail.refetch(); void deployRuns.refetch() }} disabled={!effectiveSelectedCrawlerProjectKey}>
            <RefreshCw size={14} />{t('crawlerManagePage.action.refreshDetail')}
          </button>
        </div>
        {message ? <p className="status-line" style={{ marginTop: 10 }}>{message}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2><CircleDashed size={15} />{t('crawlerManagePage.section.projects')}</h2>
          <button onClick={() => crawlerProjects.refetch()}><RefreshCw size={14} />{t('crawlerManagePage.action.refresh')}</button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('crawlerManagePage.field.projectKey')}</th>
                <th>{t('crawlerManagePage.field.name')}</th>
                <th>{t('crawlerManagePage.field.status')}</th>
                <th>{t('crawlerManagePage.field.provider')}</th>
                <th>{t('crawlerManagePage.field.deployedVersion')}</th>
              </tr>
            </thead>
            <tbody>
              {sortedProjects.map((row) => (
                <tr key={row.project_key}>
                  <td>
                    <button
                      onClick={() => setSelectedCrawlerProjectKey(row.project_key)}
                      style={{ padding: 0, border: 0, background: 'transparent', textDecoration: 'underline', cursor: 'pointer' }}
                    >
                      {row.project_key}
                    </button>
                  </td>
                  <td>{row.name || '-'}</td>
                  <td>{row.status || '-'}</td>
                  <td>{row.provider || '-'}</td>
                  <td>{row.deployed_version || '-'}</td>
                </tr>
              ))}
              {!sortedProjects.length && (
                <tr>
                  <td colSpan={5} className="empty-cell">{t('crawlerManagePage.empty.crawlerProjects')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2><Clock3 size={15} />{t('crawlerManagePage.section.deployRunsDetail')}</h2>
          <button onClick={() => { void crawlerDetail.refetch(); void deployRuns.refetch() }}><RefreshCw size={14} />{t('crawlerManagePage.action.refresh')}</button>
        </div>
        <p className="status-line">
          {t('crawlerManagePage.detail.label')}: {detailSummary}
        </p>
        <div className="table-wrap" style={{ marginTop: 10 }}>
          <table>
            <thead>
              <tr>
                <th>{t('crawlerManagePage.field.id')}</th>
                <th>{t('crawlerManagePage.field.action')}</th>
                <th>{t('crawlerManagePage.field.status')}</th>
                <th>{t('crawlerManagePage.field.requestedVersion')}</th>
                <th>{t('crawlerManagePage.field.fromTo')}</th>
                <th>{t('crawlerManagePage.field.startedAt')}</th>
                <th>{t('crawlerManagePage.field.finishedAt')}</th>
              </tr>
            </thead>
            <tbody>
              {(deployRuns.data || []).map((row) => (
                <tr key={String(row.id || [row.action || '-', row.started_at || '-'].join('-'))}>
                  <td>{row.id ?? '-'}</td>
                  <td>{row.action || '-'}</td>
                  <td>{row.status || '-'}</td>
                  <td>{row.requested_version || '-'}</td>
                  <td>{[row.from_version || '-', row.to_version || '-'].join(' -> ')}</td>
                  <td>{row.started_at || '-'}</td>
                  <td>{row.finished_at || '-'}</td>
                </tr>
              ))}
              {!(deployRuns.data || []).length && (
                <tr>
                  <td colSpan={7} className="empty-cell">{t('crawlerManagePage.empty.deployRuns')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="table-wrap" style={{ marginTop: 10 }}>
          <table>
            <thead>
              <tr>
                <th>{t('crawlerManagePage.field.field')}</th>
                <th>{t('crawlerManagePage.field.value')}</th>
              </tr>
            </thead>
            <tbody>
              {detail && (
                <>
                  {detailRows.map(([label, value]) => (
                    <tr key={label}><td>{label}</td><td>{value}</td></tr>
                  ))}
                </>
              )}
              {!detail && (
                <tr>
                  <td colSpan={2} className="empty-cell">{t('crawlerManagePage.empty.detailNotSelected')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

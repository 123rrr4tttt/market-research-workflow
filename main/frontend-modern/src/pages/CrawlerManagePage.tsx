import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, Bot, CircleDashed, Clock3, GitBranch, Layers3, Play, RefreshCw } from 'lucide-react'
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
import { useTaskSubmission } from '../hooks/useTaskSubmission'
import { TaskSubmissionNotice } from '../components/TaskSubmissionNotice'
import { fetchCrawlerAgentModules } from '../lib/api/services/crawlers'
import './crawler-management-page.css'

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

function isActiveDeployRun(run: CrawlerDeployRunItem) {
  return run.id != null && !run.finished_at && ['queued', 'running'].includes(String(run.status).toLowerCase())
}

const DEPLOY_OBSERVATION_MS = 120_000

export default function CrawlerManagePage({ projectKey }: Props) {
  const storageKey = ['crawler_manage_state_v2', projectKey].join(':')
  const cached = getLocalJson(storageKey, null) as CrawlerManageStateCache | null
  const queryClient = useQueryClient()
  const locale = useAppLocale()
  const [entryMode, setEntryMode] = useState<'collectors' | 'agent'>('collectors')
  const agentModules = useQuery({
    queryKey: ['crawler-agent-modules', projectKey],
    queryFn: () => fetchCrawlerAgentModules(projectKey),
    enabled: entryMode === 'agent',
  })
  const agentText = (zh: string, en: string) => locale === 'zh-CN' ? zh : en
  const [draft, setDraft] = useState((): Draft => cached?.draft || defaultDraft())
  const [message, setMessage] = useState('')
  const [selectedCrawlerProjectKey, setSelectedCrawlerProjectKey] = useState(cached?.selectedCrawlerProjectKey || '')
  const [deployVersion, setDeployVersion] = useState(cached?.deployVersion || '')
  const [rollbackVersion, setRollbackVersion] = useState(cached?.rollbackVersion || '')
  const [plannerMode, setPlannerMode] = useState((): PlannerMode => cached?.plannerMode || 'heuristic')
  const observedRuns = useRef(new Map<string, number>())
  const previousActiveRuns = useRef(new Set<string>())
  const currentProject = useRef(projectKey)
  const [observationEnded, setObservationEnded] = useState('')
  useEffect(() => { currentProject.current = projectKey }, [projectKey])
  const submission = useTaskSubmission({
    projectKey,
    invalidateOnSettled: [
      queryKeys.crawler.projects(projectKey),
      queryKeys.crawler.projectDetailBase(projectKey),
      queryKeys.crawler.deployRunsBase(projectKey),
    ],
  })
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
      setMessage('')
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
    queryFn: async () => {
      const runs = await listCrawlerDeployRuns({ crawlerProjectKey: effectiveSelectedCrawlerProjectKey, limit: 100 })
      const active = runs.filter(isActiveDeployRun)
      const ended = active.length > 0 && active.every((run) => {
        const firstObserved = observedRuns.current.get(`${projectKey}/${effectiveSelectedCrawlerProjectKey}/${run.id}`)
        return firstObserved != null && Date.now() - firstObserved >= DEPLOY_OBSERVATION_MS
      })
      setObservationEnded(ended ? `${projectKey}/${effectiveSelectedCrawlerProjectKey}` : '')
      return runs
    },
    enabled: Boolean(projectKey && effectiveSelectedCrawlerProjectKey),
    refetchInterval: (query) => {
      if (query.state.error) return false
      const now = Date.now()
      const activeRuns = (query.state.data || []).filter(isActiveDeployRun)
      const withinWindow = activeRuns.map((run) => {
        const identity = `${projectKey}/${effectiveSelectedCrawlerProjectKey}/${run.id}`
        if (!observedRuns.current.has(identity)) observedRuns.current.set(identity, now)
        return now - observedRuns.current.get(identity)! < DEPLOY_OBSERVATION_MS
      }).some(Boolean)
      return withinWindow ? 3000 : false
    },
  })

  useEffect(() => {
    const runs = deployRuns.data || []
    let settled = false
    for (const run of runs) {
      const identity = `${projectKey}/${effectiveSelectedCrawlerProjectKey}/${run.id}`
      if (!isActiveDeployRun(run) && previousActiveRuns.current.has(identity)) settled = true
    }
    previousActiveRuns.current = new Set(runs.filter(isActiveDeployRun).map((run) => `${projectKey}/${effectiveSelectedCrawlerProjectKey}/${run.id}`))
    if (!settled) return
    void queryClient.invalidateQueries({ queryKey: queryKeys.crawler.projects(projectKey) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.crawler.projectDetail(projectKey, effectiveSelectedCrawlerProjectKey) })
  }, [deployRuns.data, projectKey, effectiveSelectedCrawlerProjectKey, queryClient])

  const importMutation = useMutation({
    onMutate: () => ({ projectKey }),
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
    onSuccess: async (result, _variables, context) => {
      if (context?.projectKey !== currentProject.current) return
      const tracked = submission.track(result, t('crawlerManagePage.action.importCrawlerProject'))
      const nextKey = String(result?.project_key || '').trim()
      if (nextKey) setSelectedCrawlerProjectKey(nextKey)
      setMessage(tracked ? '' : nextKey ? tf('crawlerManagePage.message.importSuccessWithKey', { projectKey: nextKey }) : t('crawlerManagePage.message.importSuccess'))
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.projects(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.projectDetailBase(projectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.deployRunsBase(projectKey) }),
      ])
    },
    onError: (error, _variables, context) => {
      if (context?.projectKey !== currentProject.current) return
      setMessage(tf('crawlerManagePage.message.importFailed', { message: error instanceof Error ? error.message : t('crawlerManagePage.error.unknown') }))
    },
  })

  const deployMutation = useMutation({
    onMutate: () => ({ projectKey }),
    mutationFn: async () => {
      if (!effectiveSelectedCrawlerProjectKey) throw new Error(t('crawlerManagePage.error.missingCrawlerProject'))
      return deployCrawlerProject(effectiveSelectedCrawlerProjectKey, {
        requested_version: deployVersion.trim() || null,
        planner_mode: plannerMode,
        async_mode: true,
      })
    },
    onSuccess: async (run, _variables, context) => {
      if (context?.projectKey !== currentProject.current) return
      submission.track(run, t('crawlerManagePage.action.submitDeploy'))
      setMessage(tf('crawlerManagePage.message.deploySubmitted', { summary: summarizeRun(run) || t('crawlerManagePage.message.deployRunCreated') }))
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.projectDetail(projectKey, effectiveSelectedCrawlerProjectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.deployRuns(projectKey, effectiveSelectedCrawlerProjectKey) }),
      ])
    },
    onError: (error, _variables, context) => {
      if (context?.projectKey !== currentProject.current) return
      setMessage(tf('crawlerManagePage.message.deployFailed', { message: error instanceof Error ? error.message : t('crawlerManagePage.error.unknown') }))
    },
  })

  const rollbackMutation = useMutation({
    onMutate: () => ({ projectKey }),
    mutationFn: async () => {
      if (!effectiveSelectedCrawlerProjectKey) throw new Error(t('crawlerManagePage.error.missingCrawlerProject'))
      return rollbackCrawlerProject(effectiveSelectedCrawlerProjectKey, {
        to_version: rollbackVersion.trim() || null,
        planner_mode: plannerMode,
        async_mode: true,
      })
    },
    onSuccess: async (run, _variables, context) => {
      if (context?.projectKey !== currentProject.current) return
      submission.track(run, t('crawlerManagePage.action.submitRollback'))
      setMessage(tf('crawlerManagePage.message.rollbackSubmitted', { summary: summarizeRun(run) || t('crawlerManagePage.message.rollbackRunCreated') }))
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.projectDetail(projectKey, effectiveSelectedCrawlerProjectKey) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.crawler.deployRuns(projectKey, effectiveSelectedCrawlerProjectKey) }),
      ])
    },
    onError: (error, _variables, context) => {
      if (context?.projectKey !== currentProject.current) return
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
    <div className="content-stack crawler-page crawler-management-page">
      <div className="crawler-entry-tabs" role="tablist" aria-label={agentText('模块入口', 'Module entry')}>
        <button id="crawler-tab-collectors" role="tab" aria-selected={entryMode === 'collectors'} aria-controls="crawler-collectors" onClick={() => setEntryMode('collectors')}><CircleDashed size={15} />{agentText('采集工程', 'Collectors')}</button>
        <button id="crawler-tab-agent" role="tab" aria-selected={entryMode === 'agent'} aria-controls="crawler-agent" onClick={() => setEntryMode('agent')}><Bot size={15} />{agentText('Agent 接线', 'Agent wiring')}</button>
      </div>
      {entryMode === 'agent' ? <section id="crawler-agent" role="tabpanel" aria-labelledby="crawler-tab-agent" className="crawler-agent-module">
        <div className="panel-header">
          <h2>{agentText('概念工作台接线', 'Concept Workbench Wiring')}</h2>
          <button aria-label={agentText('刷新模块', 'Refresh modules')} title={agentText('刷新模块', 'Refresh modules')} onClick={() => void agentModules.refetch()} disabled={agentModules.isFetching}><RefreshCw size={15} /></button>
        </div>
        {agentModules.isLoading ? <p role="status">{agentText('正在读取模块', 'Loading modules')}</p> : null}
        {agentModules.isError ? <p role="alert">{agentText('模块状态读取失败', 'Module readback failed')}</p> : null}
        {!agentModules.isLoading && !agentModules.isError && !agentModules.data?.length ? <p>{agentText('暂无 Agent 模块', 'No Agent modules')}</p> : null}
        {agentModules.data?.map((module) => <div key={module.id} className="crawler-agent-content">
          <span className={`crawler-module-status ${module.available ? 'is-ready' : ''}`}>{module.available ? agentText('已注册', 'Registered') : agentText('未连接', 'Unavailable')}</span>
          {module.reason ? <p className="status-line">{module.reason}</p> : null}
          {module.available ? <>
            <h3>{agentText('项目目标', 'Project targets')}</h3>
            <ul className="crawler-module-list">{module.targets.map((target) => <li key={target.id}><span>{target.label}</span><code>{target.id}</code></li>)}</ul>
            <h3>{agentText('方法', 'Methods')}</h3>
            <ul className="crawler-module-list">{module.methods.map((method) => <li key={method.id}>{method.title}</li>)}</ul>
            <div className="crawler-agent-links">
              <a className="crawler-agent-link" href="#/workbench/agent">{agentText('打开 Agent', 'Open Agent')}<ArrowUpRight size={16} /></a>
              <a className="crawler-agent-link" href="#/workbench/cell"><Layers3 size={16} />{agentText('查看胞腔', 'View cell')}</a>
            </div>
          </> : null}
          <details className="crawler-module-details">
            <summary>{agentText('注册详情', 'Registration details')}</summary>
            <p><code>{module.cell_ref}</code></p>
            <ul className="crawler-module-list">{module.operations.map((operation) => <li key={operation.id}><code>{operation.id}</code><span>{operation.effect}</span></li>)}</ul>
          </details>
        </div>)}
      </section> : null}
      <div id="crawler-collectors" role="tabpanel" aria-labelledby="crawler-tab-collectors" className="content-stack" hidden={entryMode !== 'collectors'}>
      <section className="panel crawler-projects-panel">
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
              {crawlerProjects.isLoading && (
                <tr><td colSpan={5} className="empty-cell">{t('crawlerManagePage.state.loading')}</td></tr>
              )}
              {sortedProjects.map((row) => (
                <tr key={row.project_key}>
                  <td>
                    <button
                      disabled={submitting}
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
              {!crawlerProjects.isLoading && !crawlerProjects.isError && !sortedProjects.length && (
                <tr>
                  <td colSpan={5} className="empty-cell">{t('crawlerManagePage.empty.crawlerProjects')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel crawler-version-panel">
        <div className="panel-header"><h2><GitBranch size={15} />{t('crawlerManagePage.section.versionActions')}</h2></div>
        <div className="form-grid cols-3" style={{ marginTop: 12 }}>
          <label>
            <span>{t('crawlerManagePage.field.selectedProject')}</span>
            <select
              value={effectiveSelectedCrawlerProjectKey}
              disabled={submitting}
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
        {message ? <p className="status-line" style={{ marginTop: 10 }} role="status">{message}</p> : null}
        <TaskSubmissionNotice submission={submission} />
      </section>

      <section className="panel crawler-detail-panel">
        {crawlerProjects.isError ? <p className="status-line" role="alert">{t('crawlerManagePage.error.projectsLoad')}</p> : null}
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
                <th>{t('crawlerManagePage.field.externalJobId')}</th>
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
                  <td>{row.external_job_id || '-'}</td>
                </tr>
              ))}
              {deployRuns.isLoading ? <tr><td colSpan={8} className="empty-cell">{t('crawlerManagePage.state.loading')}</td></tr> : null}
              {!deployRuns.isLoading && !deployRuns.isError && !(deployRuns.data || []).length && (
                <tr>
                  <td colSpan={8} className="empty-cell">{t('crawlerManagePage.empty.deployRuns')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {deployRuns.isError ? <p className="status-line" role="alert">{t('crawlerManagePage.error.runsLoad')}</p> : null}
        {observationEnded === `${projectKey}/${effectiveSelectedCrawlerProjectKey}` ? <p className="status-line">{t('crawlerManagePage.state.observationEnded')}</p> : null}
        <details className="crawler-project-details">
          <summary>{t('crawlerManagePage.section.projectDetails')}</summary>
          {crawlerDetail.isLoading ? <p className="status-line">{t('crawlerManagePage.state.loading')}</p> : null}
          {crawlerDetail.isError ? <p className="status-line" role="alert">{t('crawlerManagePage.error.detailLoad')}</p> : null}
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
        </details>
      </section>
      <details className="panel crawler-import-panel">
        <summary className="panel-header">
          <h2><Bot size={15} />{t('crawlerManagePage.section.import')}</h2>
          <span className="status-line">{tf('crawlerManagePage.field.project', { projectKey })}</span>
        </summary>
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
      </details>
      </div>
    </div>
  )
}

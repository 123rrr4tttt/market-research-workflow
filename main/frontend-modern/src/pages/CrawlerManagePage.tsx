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
import { getLocalJson, setLocalJson } from '../lib/localStore'
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

export default function CrawlerManagePage({ projectKey }: Props) {
  const storageKey = `crawler_manage_state_v2:${projectKey}`
  const cached = getLocalJson<CrawlerManageStateCache | null>(storageKey, null)
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<Draft>(() => cached?.draft || defaultDraft())
  const [message, setMessage] = useState('')
  const [selectedCrawlerProjectKey, setSelectedCrawlerProjectKey] = useState(cached?.selectedCrawlerProjectKey || '')
  const [deployVersion, setDeployVersion] = useState(cached?.deployVersion || '')
  const [rollbackVersion, setRollbackVersion] = useState(cached?.rollbackVersion || '')
  const [plannerMode, setPlannerMode] = useState<'heuristic' | 'manual'>(cached?.plannerMode || 'heuristic')

  useEffect(() => {
    const next = getLocalJson<CrawlerManageStateCache | null>(`crawler_manage_state_v2:${projectKey}`, null)
    setDraft(next?.draft || defaultDraft())
    setSelectedCrawlerProjectKey(next?.selectedCrawlerProjectKey || '')
    setDeployVersion(next?.deployVersion || '')
    setRollbackVersion(next?.rollbackVersion || '')
    setPlannerMode(next?.plannerMode || 'heuristic')
  }, [projectKey])

  const crawlerProjects = useQuery({
    queryKey: ['crawler-manage', 'projects', projectKey],
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
    queryKey: ['crawler-manage', 'project-detail', projectKey, effectiveSelectedCrawlerProjectKey],
    queryFn: () => getCrawlerProjectDetail(effectiveSelectedCrawlerProjectKey),
    enabled: Boolean(projectKey && effectiveSelectedCrawlerProjectKey),
  })

  const deployRuns = useQuery({
    queryKey: ['crawler-manage', 'deploy-runs', projectKey, effectiveSelectedCrawlerProjectKey],
    queryFn: () => listCrawlerDeployRuns({ crawlerProjectKey: effectiveSelectedCrawlerProjectKey, limit: 100 }),
    enabled: Boolean(projectKey && effectiveSelectedCrawlerProjectKey),
  })

  const importMutation = useMutation({
    mutationFn: async () => {
      const repoUrl = draft.repoUrl.trim()
      if (!repoUrl) throw new Error('请先填写爬虫项目 Git URL。')
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
      setMessage(nextKey ? `导入成功: ${nextKey}` : '导入成功')
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['crawler-manage', 'projects', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['crawler-manage', 'project-detail', projectKey] }),
        queryClient.invalidateQueries({ queryKey: ['crawler-manage', 'deploy-runs', projectKey] }),
      ])
    },
    onError: (error) => {
      setMessage(`导入失败: ${error instanceof Error ? error.message : '未知错误'}`)
    },
  })

  const deployMutation = useMutation({
    mutationFn: async () => {
      if (!effectiveSelectedCrawlerProjectKey) throw new Error('请先选择爬虫项目')
      return deployCrawlerProject(effectiveSelectedCrawlerProjectKey, {
        requested_version: deployVersion.trim() || null,
        planner_mode: plannerMode,
        async_mode: true,
      })
    },
    onSuccess: async (run) => {
      setMessage(`部署已提交: ${summarizeRun(run) || '已创建 deploy run'}`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['crawler-manage', 'project-detail', projectKey, effectiveSelectedCrawlerProjectKey] }),
        queryClient.invalidateQueries({ queryKey: ['crawler-manage', 'deploy-runs', projectKey, effectiveSelectedCrawlerProjectKey] }),
      ])
    },
    onError: (error) => {
      setMessage(`部署失败: ${error instanceof Error ? error.message : '未知错误'}`)
    },
  })

  const rollbackMutation = useMutation({
    mutationFn: async () => {
      if (!effectiveSelectedCrawlerProjectKey) throw new Error('请先选择爬虫项目')
      return rollbackCrawlerProject(effectiveSelectedCrawlerProjectKey, {
        to_version: rollbackVersion.trim() || null,
        planner_mode: plannerMode,
        async_mode: true,
      })
    },
    onSuccess: async (run) => {
      setMessage(`回滚已提交: ${summarizeRun(run) || '已创建 rollback run'}`)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['crawler-manage', 'project-detail', projectKey, effectiveSelectedCrawlerProjectKey] }),
        queryClient.invalidateQueries({ queryKey: ['crawler-manage', 'deploy-runs', projectKey, effectiveSelectedCrawlerProjectKey] }),
      ])
    },
    onError: (error) => {
      setMessage(`回滚失败: ${error instanceof Error ? error.message : '未知错误'}`)
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

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2><Bot size={15} />爬虫项目接入</h2>
          <span className="status-line">project: {projectKey}</span>
        </div>
        <p className="status-line">
          该页面与“信息资源库管理”已拆分。这里专门用于管理爬虫项目导入、部署与运行观测。
        </p>
        <div className="form-grid cols-3" style={{ marginTop: 12 }}>
          <label>
            <span>Crawler Project Key</span>
            <input
              value={draft.crawlerProjectKey}
              onChange={(e) => setDraft((prev) => ({ ...prev, crawlerProjectKey: e.target.value }))}
              placeholder="crawler_demo"
            />
          </label>
          <label>
            <span>Name</span>
            <input
              value={draft.name}
              onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
              placeholder="Crawler Demo"
            />
          </label>
          <label>
            <span>Git URL</span>
            <input
              value={draft.repoUrl}
              onChange={(e) => setDraft((prev) => ({ ...prev, repoUrl: e.target.value }))}
              placeholder="https://github.com/your-org/your-spider-repo.git"
            />
          </label>
          <label>
            <span>Branch / Tag</span>
            <input
              value={draft.branch}
              onChange={(e) => setDraft((prev) => ({ ...prev, branch: e.target.value }))}
              placeholder="main"
            />
          </label>
          <label>
            <span>Provider Hint</span>
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
            <span>Description</span>
            <input
              value={draft.description}
              onChange={(e) => setDraft((prev) => ({ ...prev, description: e.target.value }))}
              placeholder="optional"
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
            导入后立即启用
          </label>
          <button
            onClick={() => setMessage('草稿已自动本地保存。')}
            disabled={submitting}
            title="当前页面变更会自动保存到本地，无需手动保存"
          >
            <GitBranch size={14} />
            草稿自动保存
          </button>
          <button onClick={() => importMutation.mutate()} disabled={submitting}><Play size={14} />导入爬虫项目</button>
          <button onClick={() => crawlerProjects.refetch()}><RefreshCw size={14} />刷新列表</button>
        </div>
        <div className="form-grid cols-3" style={{ marginTop: 12 }}>
          <label>
            <span>Selected Project</span>
            <select
              value={effectiveSelectedCrawlerProjectKey}
              onChange={(e) => setSelectedCrawlerProjectKey(e.target.value)}
            >
              <option value="">请选择</option>
              {sortedProjects.map((item) => (
                <option key={item.project_key} value={item.project_key}>
                  {item.project_key}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Deploy Version</span>
            <input
              value={deployVersion}
              onChange={(e) => setDeployVersion(e.target.value)}
              placeholder="v1.0.0 (optional)"
            />
          </label>
          <label>
            <span>Rollback To Version</span>
            <input
              value={rollbackVersion}
              onChange={(e) => setRollbackVersion(e.target.value)}
              placeholder="v0.9.0 (optional)"
            />
          </label>
        </div>
        <div className="inline-actions" style={{ marginTop: 10 }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span>planner</span>
            <select value={plannerMode} onChange={(e) => setPlannerMode(e.target.value as 'heuristic' | 'manual')}>
              <option value="heuristic">heuristic</option>
              <option value="manual">manual</option>
            </select>
          </label>
          <button
            onClick={() => deployMutation.mutate()}
            disabled={submitting || !effectiveSelectedCrawlerProjectKey}
          >
            <Play size={14} />提交部署
          </button>
          <button
            onClick={() => rollbackMutation.mutate()}
            disabled={submitting || !effectiveSelectedCrawlerProjectKey}
          >
            <CircleDashed size={14} />提交回滚
          </button>
          <button onClick={() => { void crawlerDetail.refetch(); void deployRuns.refetch() }} disabled={!effectiveSelectedCrawlerProjectKey}>
            <RefreshCw size={14} />刷新详情
          </button>
        </div>
        {message ? <p className="status-line" style={{ marginTop: 10 }}>{message}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2><CircleDashed size={15} />Crawler Projects</h2>
          <button onClick={() => crawlerProjects.refetch()}><RefreshCw size={14} />刷新</button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>project_key</th>
                <th>name</th>
                <th>status</th>
                <th>provider</th>
                <th>deployed_version</th>
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
                  <td colSpan={5} className="empty-cell">暂无 crawler 项目</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2><Clock3 size={15} />Deploy Runs / 详情</h2>
          <button onClick={() => { void crawlerDetail.refetch(); void deployRuns.refetch() }}><RefreshCw size={14} />刷新</button>
        </div>
        <p className="status-line">
          detail: {detail ? `${detail.project_key} | status=${detail.status || '-'} | current=${detail.current_version || '-'} | deployed=${detail.deployed_version || '-'}` : '请选择项目'}
        </p>
        <div className="table-wrap" style={{ marginTop: 10 }}>
          <table>
            <thead>
              <tr>
                <th>id</th>
                <th>action</th>
                <th>status</th>
                <th>requested_version</th>
                <th>from → to</th>
                <th>started_at</th>
                <th>finished_at</th>
              </tr>
            </thead>
            <tbody>
              {(deployRuns.data || []).map((row) => (
                <tr key={String(row.id || `${row.action}-${row.started_at}`)}>
                  <td>{row.id ?? '-'}</td>
                  <td>{row.action || '-'}</td>
                  <td>{row.status || '-'}</td>
                  <td>{row.requested_version || '-'}</td>
                  <td>{`${row.from_version || '-'} → ${row.to_version || '-'}`}</td>
                  <td>{row.started_at || '-'}</td>
                  <td>{row.finished_at || '-'}</td>
                </tr>
              ))}
              {!(deployRuns.data || []).length && (
                <tr>
                  <td colSpan={7} className="empty-cell">暂无 deploy/rollback 记录</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="table-wrap" style={{ marginTop: 10 }}>
          <table>
            <thead>
              <tr>
                <th>field</th>
                <th>value</th>
              </tr>
            </thead>
            <tbody>
              {detail && (
                <>
                  <tr><td>project_key</td><td>{detail.project_key}</td></tr>
                  <tr><td>name</td><td>{detail.name || '-'}</td></tr>
                  <tr><td>source_uri</td><td>{detail.source_uri || '-'}</td></tr>
                  <tr><td>provider</td><td>{detail.provider || '-'}</td></tr>
                  <tr><td>status</td><td>{detail.status || '-'}</td></tr>
                  <tr><td>current_version</td><td>{detail.current_version || '-'}</td></tr>
                  <tr><td>deployed_version</td><td>{detail.deployed_version || '-'}</td></tr>
                  <tr><td>previous_version</td><td>{detail.previous_version || '-'}</td></tr>
                  <tr><td>updated_at</td><td>{detail.updated_at || '-'}</td></tr>
                </>
              )}
              {!detail && (
                <tr>
                  <td colSpan={2} className="empty-cell">尚未选择 crawler 项目</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useAppLocale } from '../app/platform/i18n'
import {
  getCurrentRetrievalMode,
  getRetrievalRun,
  previewRetrievalPlan,
  startRetrievalRun,
  type RetrievalLimits,
  type RetrievalPlan,
} from '../lib/api/domains/project-retrieval'
import './project-retrieval-panel.css'

type Props = { projectKey: string }

const terminalStatuses = new Set([
  'completed', 'complete', 'succeeded', 'success', 'failed', 'error', 'cancelled',
  'canceled', 'partial', 'blocked', 'dispatch_failed', 'completed_with_gaps',
  'budget_exhausted', 'conflict',
])

const stepLabels: Record<string, [string, string]> = {
  discover_candidates: ['来源发现与查询', 'Discover sources and run query'],
  review_candidates: ['核查候选', 'Review candidates'],
  fetch_materials: ['获取材料', 'Fetch materials'],
  read_materials: ['阅读正文', 'Read material bodies'],
  judge_materials: ['判断材料与关系', 'Judge materials and relations'],
  validate_evidence: ['校验证据', 'Validate evidence'],
  followup_search: ['按缺口续查', 'Follow up on gaps'],
  write_topology: ['写入拓扑', 'Write topology'],
  report: ['形成线索报告', 'Build clue report'],
}

function describe(value: string | Record<string, unknown>, zh: boolean): string {
  if (typeof value === 'string') return value
  const label = value.label ?? value.title ?? value.name ?? value.message
  if (typeof label === 'string') return label
  if (typeof value.kind === 'string') {
    const name = stepLabels[value.kind]?.[zh ? 0 : 1] || value.kind.replaceAll('_', ' ')
    const detail = value.query_id ?? value.max_materials ?? value.max_rounds
    return detail === undefined ? name : `${name} · ${String(detail)}`
  }
  return typeof value.code === 'string' ? value.code : JSON.stringify(value)
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

function sessionRunKey(projectKey: string) {
  return `project-retrieval-run:${projectKey}`
}

export default function ProjectRetrievalPanel({ projectKey }: Props) {
  const locale = useAppLocale()
  const zh = locale === 'zh-CN'
  const [routeIdState, setRouteId] = useState('')
  const [queryIdsState, setQueryIds] = useState<string[]>([])
  const [limitsState, setLimits] = useState<RetrievalLimits | null>(null)
  const [selectionBinding, setSelectionBinding] = useState('')
  const [planState, setPlan] = useState<RetrievalPlan | null>(null)
  const [planBinding, setPlanBinding] = useState('')
  const [startKey, setStartKey] = useState('')
  const [launchedPlanId, setLaunchedPlanId] = useState('')
  const [runId, setRunId] = useState(() => window.sessionStorage.getItem(sessionRunKey(projectKey)) || '')

  const modeQuery = useQuery({
    queryKey: ['project-retrieval', 'mode', projectKey],
    queryFn: getCurrentRetrievalMode,
    enabled: Boolean(projectKey),
    retry: false,
  })
  const mode = modeQuery.data?.project_key === projectKey ? modeQuery.data : null
  const modeIdentity = mode ? `${mode.project_key}:${mode.mode_id}:${mode.version}:${mode.source_revision}` : ''
  const selectionCurrent = selectionBinding === modeIdentity
  const routeId = selectionCurrent ? routeIdState : mode?.routes[0]?.route_id || ''
  const route = mode?.routes.find((item) => item.route_id === routeId)
  const limits = selectionCurrent && limitsState ? limitsState : mode?.limits || { max_queries: 10, max_materials: 20, max_followups: 2 }
  const queryIds = selectionCurrent ? queryIdsState : route?.query_ids.slice(0, limits.max_queries) || []
  const plan = planBinding === modeIdentity ? planState : null

  const previewMutation = useMutation({
    mutationFn: previewRetrievalPlan,
    onSuccess: (nextPlan) => {
      setPlan(nextPlan)
      setPlanBinding(modeIdentity)
      setStartKey(window.crypto.randomUUID())
      setLaunchedPlanId('')
    },
  })
  const startMutation = useMutation({
    mutationFn: ({ planId, key }: { planId: string; key: string }) => startRetrievalRun(planId, key),
    onSuccess: (run) => {
      setRunId(run.run_id)
      setLaunchedPlanId(plan?.plan_id || '')
      window.sessionStorage.setItem(sessionRunKey(projectKey), run.run_id)
    },
  })
  const runQuery = useQuery({
    queryKey: ['project-retrieval', 'run', projectKey, runId],
    queryFn: () => getRetrievalRun(runId),
    enabled: Boolean(projectKey && runId),
    refetchInterval: (query) => terminalStatuses.has(query.state.data?.status?.toLowerCase() || '') ? false : 3000,
    retry: false,
  })

  const editSelection = () => {
    setPlan(null)
    setPlanBinding('')
    setStartKey('')
    setLaunchedPlanId('')
    previewMutation.reset()
    startMutation.reset()
  }
  const setRoute = (nextRouteId: string) => {
    const nextRoute = mode?.routes.find((item) => item.route_id === nextRouteId)
    setSelectionBinding(modeIdentity)
    setRouteId(nextRouteId)
    setQueryIds(nextRoute?.query_ids.slice(0, limits.max_queries) || [])
    editSelection()
  }
  const setLimit = (key: keyof RetrievalLimits, value: number) => {
    setSelectionBinding(modeIdentity)
    setLimits({ ...limits, [key]: value })
    setQueryIds(queryIds)
    editSelection()
  }
  const max = mode?.limits
  const invalidSelection = !route || queryIds.length === 0 || queryIds.length > limits.max_queries
  const busy = previewMutation.isPending || startMutation.isPending
  const hasBlockingDiagnostics = plan?.diagnostics.some((item) =>
    typeof item === 'object' && item !== null &&
    ['error', 'blocking', 'blocked'].includes(String(item.severity ?? item.level ?? '').toLowerCase()),
  ) || false

  return (
    <section className="panel project-retrieval-panel" data-testid="project-retrieval-panel">
      <div className="panel-header">
        <div>
          <h2>{zh ? '项目检索方法' : 'Project retrieval method'}</h2>
          <p className="project-retrieval-panel__intro">
            {zh ? '先预览本轮路线，再手动启动检索与成图。' : 'Preview a route before manually starting retrieval and graph writing.'}
          </p>
        </div>
        <button type="button" onClick={() => void modeQuery.refetch()} disabled={modeQuery.isFetching}>
          {zh ? '刷新绑定' : 'Refresh binding'}
        </button>
      </div>

      {modeQuery.isPending ? <p role="status">{zh ? '正在读取项目检索模式…' : 'Loading retrieval mode…'}</p> : null}
      {modeQuery.isError ? <p className="project-retrieval-panel__error" role="alert">
        {zh ? '无法读取项目检索模式：' : 'Could not load retrieval mode: '}{errorMessage(modeQuery.error)}
      </p> : null}
      {modeQuery.data && !mode ? <p className="project-retrieval-panel__error" role="alert">
        {zh ? '服务返回的项目与当前项目不一致。' : 'The service returned a different project.'}
      </p> : null}

      {mode ? <>
        <dl className="project-retrieval-panel__identity">
          <div><dt>{zh ? '模式' : 'Mode'}</dt><dd>{mode.mode_id}</dd></div>
          <div><dt>{zh ? '绑定版本' : 'Binding version'}</dt><dd>{String(mode.version)}</dd></div>
          <div><dt>{zh ? '总纲观察版本' : 'Source revision'}</dt><dd>{String(mode.source_revision)}</dd></div>
          <div><dt>{zh ? '历史来源记录' : 'Observed sources'}</dt><dd>{mode.source_registry_count}</dd></div>
        </dl>

        {mode.routes.length === 0 ? <p>{zh ? '当前绑定没有可运行的来源路线。' : 'This binding has no runnable source route.'}</p> : <>
          <div className="project-retrieval-panel__controls">
            <label>
              <span>{zh ? '来源路线' : 'Source route'}</span>
              <select value={routeId} onChange={(event) => setRoute(event.target.value)} disabled={busy}>
                {mode.routes.map((item) => <option key={item.route_id} value={item.route_id}>{item.label || item.route_id}</option>)}
              </select>
            </label>
            {max ? (['max_queries', 'max_materials', 'max_followups'] as const).map((key) => <label key={key}>
              <span>{key === 'max_queries' ? (zh ? '检索式上限' : 'Query limit') : key === 'max_materials' ? (zh ? '材料上限' : 'Material limit') : (zh ? '续查轮数' : 'Follow-up rounds')}</span>
              <input
                type="number"
                min={key === 'max_followups' ? 0 : 1}
                max={max[key]}
                value={limits[key]}
                onChange={(event) => {
                  const lower = key === 'max_followups' ? 0 : 1
                  setLimit(key, Math.max(lower, Math.min(max[key], Number(event.target.value) || lower)))
                }}
                disabled={busy}
              />
            </label>) : null}
          </div>

          <fieldset className="project-retrieval-panel__queries" disabled={busy}>
            <legend>{zh ? '本轮检索式' : 'Queries for this run'} <small>({queryIds.length}/{limits.max_queries})</small></legend>
            <div className="project-retrieval-panel__query-list">
              {route?.query_ids.map((queryId) => <label key={queryId}>
                <input
                  type="checkbox"
                  checked={queryIds.includes(queryId)}
                  onChange={(event) => {
                    setSelectionBinding(modeIdentity)
                    setLimits(limits)
                    setRouteId(routeId)
                    setQueryIds(event.target.checked ? [...queryIds, queryId] : queryIds.filter((id) => id !== queryId))
                    editSelection()
                  }}
                />
                <span>{queryId} · {mode.queries.find((query) => query.query_id === queryId)?.expression || queryId}</span>
              </label>)}
            </div>
          </fieldset>
          {invalidSelection ? <p className="project-retrieval-panel__error" role="status">
            {zh ? '请选择至少一条检索式，且数量不超过本轮上限。' : 'Select one or more queries within this run’s limit.'}
          </p> : null}
          <div className="project-retrieval-panel__actions">
            <button type="button" onClick={() => {
              if (route) previewMutation.mutate({ route_id: route.route_id, query_ids: queryIds, limits })
            }} disabled={busy || invalidSelection}>
              {previewMutation.isPending ? (zh ? '预览中…' : 'Previewing…') : (zh ? '预览运行链' : 'Preview plan')}
            </button>
            <button type="button" className="project-retrieval-panel__start" onClick={() => {
              if (plan && startKey) startMutation.mutate({ planId: plan.plan_id, key: startKey })
            }} disabled={busy || !plan || hasBlockingDiagnostics || launchedPlanId === plan?.plan_id}>
              {startMutation.isPending ? (zh ? '启动中…' : 'Starting…') : (zh ? '手动启动本轮' : 'Start run')}
            </button>
          </div>
          {previewMutation.isError ? <p className="project-retrieval-panel__error" role="alert">{errorMessage(previewMutation.error)}</p> : null}
          {startMutation.isError ? <p className="project-retrieval-panel__error" role="alert">{errorMessage(startMutation.error)}</p> : null}
        </>}
      </> : null}

      {plan ? <div className="project-retrieval-panel__result" aria-label={zh ? '运行链预览' : 'Plan preview'}>
        <h3>{zh ? '运行链预览' : 'Plan preview'} <small>{plan.plan_id}</small></h3>
        <p>{zh ? '路线' : 'Route'}: {plan.route_id} · {zh ? '检索式' : 'Queries'}: {plan.query_ids.length}</p>
        <ol>{plan.steps.map((step, index) => <li key={index}>{describe(step, zh)}</li>)}</ol>
        {plan.channels?.length ? <div className="project-retrieval-panel__diagnostics">
          <strong>{zh ? '执行通道注册状态（未探测网络）' : 'Execution channel registration (network not probed)'}</strong>
          <ul>{plan.channels.map((channel) => <li key={channel.capability}>
            {channel.capability}: {channel.registration}
          </li>)}</ul>
        </div> : null}
        {plan.diagnostics.length > 0 ? <div className="project-retrieval-panel__diagnostics">
          <strong>{zh ? '预检提示' : 'Diagnostics'}</strong>
          <ul>{plan.diagnostics.map((item, index) => <li key={index}>{describe(item, zh)}</li>)}</ul>
        </div> : null}
      </div> : null}

      {runId ? <div className="project-retrieval-panel__result" aria-live="polite">
        <h3>{zh ? '最近启动的轮次' : 'Latest run'} <small>{runId}</small></h3>
        {runQuery.isPending ? <p>{zh ? '正在读取运行状态…' : 'Loading run status…'}</p> : null}
        {runQuery.isError ? <p className="project-retrieval-panel__error" role="alert">{errorMessage(runQuery.error)}</p> : null}
        {runQuery.data ? <>
          <p><strong>{runQuery.data.status}</strong>{runQuery.data.phase ? ` · ${runQuery.data.phase}` : ''}</p>
          {runQuery.data.counts ? <dl className="project-retrieval-panel__counts">
            {Object.entries(runQuery.data.counts).map(([key, count]) => <div key={key}><dt>{key}</dt><dd>{count}</dd></div>)}
          </dl> : null}
          {runQuery.data.errors?.length ? <ul className="project-retrieval-panel__errors">
            {runQuery.data.errors.map((error, index) => <li key={index}>{describe(error, zh)}</li>)}
          </ul> : null}
        </> : null}
        <button type="button" onClick={() => void runQuery.refetch()} disabled={runQuery.isFetching}>
          {zh ? '刷新状态' : 'Refresh status'}
        </button>
      </div> : null}
    </section>
  )
}

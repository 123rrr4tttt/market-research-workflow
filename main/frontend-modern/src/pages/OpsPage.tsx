import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Eye, RefreshCw, Trash2, XCircle } from 'lucide-react'
import GraphNodeCard from '../components/graph-kit/GraphNodeCard'
import GraphBusinessCardSections from '../components/GraphBusinessCardSections'
import GraphExtensionsSections from '../components/GraphExtensionsSections'
import { endpoints } from '../lib/api/endpoints'
import { queryKeys } from '../lib/queryKeys'
import type { AgentArtifactItem, AgentEventItem, AgentMessageItem, AgentSessionDetail, AgentSessionItem, AgentTaskItem, DocumentItem } from '../lib/types'
import {
  cancelAgentSession,
  bulkUpdateDocumentExtractedData,
  clearDocumentExtractedData,
  cleanupGovernance,
  createAgentSession,
  getAdminDocument,
  deleteAdminDocuments,
  exportGraph,
  getAdminStats,
  getAgentSession,
  getSearchHistory,
  listAdminDocuments,
  listAgentSessions,
  reclaimExpiredAgentSessionTasks,
  reExtractDocuments,
  resolveAgentApproval,
  runAgentSessionCoordinatorPass,
  retryAgentSessionTask,
  syncAggregator,
  topicExtractDocuments,
} from '../lib/api'

type OpsPageProps = {
  projectKey: string
  variant?: 'ops' | 'backend'
}

type OpsCardTab = 'business' | 'graph_ext'

const OPS_CARD_PALETTE = [
  '#7dd3fc', // brand cyan
  '#93c5fd', // blue-300
  '#67e8f9', // cyan-300
  '#a5b4fc', // indigo-300
  '#86efac', // green-300
  '#c4b5fd', // violet-300
  '#5eead4', // teal-300
  '#bae6fd', // sky-200
]

function formatDate(value?: string | null) {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString('zh-CN')
}

function toGraphBusinessNode(doc: DocumentItem | undefined, activeDocId: number | null): Record<string, unknown> {
  const extracted = (doc?.extracted_data && typeof doc.extracted_data === 'object' && !Array.isArray(doc.extracted_data))
    ? doc.extracted_data
    : {}
  return {
    ...extracted,
    id: doc?.id ?? activeDocId ?? '-',
    type: doc?.doc_type || String((extracted as Record<string, unknown>).type || 'Document'),
    title: doc?.title || String((extracted as Record<string, unknown>).title || ''),
    name: String(
      (extracted as Record<string, unknown>).name
      || (extracted as Record<string, unknown>).canonical_name
      || '',
    ),
    state: doc?.state || String((extracted as Record<string, unknown>).state || ''),
    status: doc?.status || String((extracted as Record<string, unknown>).status || ''),
    publish_date: doc?.publish_date || String((extracted as Record<string, unknown>).publish_date || ''),
    platform: String((extracted as Record<string, unknown>).platform || ''),
    game: String((extracted as Record<string, unknown>).game || ''),
    policy_type: String((extracted as Record<string, unknown>).policy_type || ''),
    summary: doc?.summary || '',
    content: doc?.content || '',
    extracted_data: extracted,
    text: doc?.summary || doc?.content || '',
  }
}

function normalizeScalar(value: unknown) {
  if (value == null) return ''
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function normalizeObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function hashText(value: string) {
  let hash = 0
  for (let i = 0; i < value.length; i += 1) {
    hash = ((hash << 5) - hash) + value.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

function opsChipColorForIndex(index: number) {
  return OPS_CARD_PALETTE[index % OPS_CARD_PALETTE.length]
}

function opsElementColorForLabel(label: string) {
  return OPS_CARD_PALETTE[hashText(label || 'element') % OPS_CARD_PALETTE.length]
}

function buildOpsGraphExtension(doc: DocumentItem | undefined, activeDocId: number | null) {
  const node = toGraphBusinessNode(doc, activeDocId)
  const elementGroups = new Map<string, string[]>()
  Object.entries(node).forEach(([key, value]) => {
    if (value == null) return
    if (Array.isArray(value)) {
      const values = value.map((item) => normalizeScalar(item).trim()).filter(Boolean)
      if (!values.length) return
      const bucket = elementGroups.get(key) || []
      elementGroups.set(key, [...bucket, ...values])
      return
    }
    if (typeof value === 'object') {
      const obj = normalizeObject(value)
      const values = Object.entries(obj).map(([k, v]) => `${k}: ${normalizeScalar(v) || '[object]'}`)
      if (!values.length) return
      const bucket = elementGroups.get(key) || []
      elementGroups.set(key, [...bucket, ...values])
      return
    }
    const text = normalizeScalar(value).trim()
    if (!text) return
    const bucket = elementGroups.get(key) || []
    elementGroups.set(key, [...bucket, text])
  })

  const extracted = normalizeObject(doc?.extracted_data)
  const er = normalizeObject(extracted.entities_relations)
  const entities = Array.isArray(er.entities) ? er.entities : []
  const relations = Array.isArray(er.relations) ? er.relations : []

  const entityTypeCount = new Map<string, number>()
  const entityItemsByType = new Map<string, string[]>()
  entities.forEach((item) => {
    const entity = normalizeObject(item)
    const type = String(entity.type || entity.entity_type || entity.category || entity.label || 'Entity')
    const name = String(entity.name || entity.text || entity.value || entity.id || type)
    entityTypeCount.set(type, (entityTypeCount.get(type) || 0) + 1)
    const bucket = entityItemsByType.get(type) || []
    bucket.push(name)
    entityItemsByType.set(type, bucket)
  })

  const relationTypeCount = new Map<string, number>()
  const relationItemsByType = new Map<string, string[]>()
  const relationExamples: string[] = []
  relations.forEach((item) => {
    const relation = normalizeObject(item)
    const relType = String(relation.relation || relation.predicate || relation.type || relation.relation_type || relation.label || 'related_to')
    relationTypeCount.set(relType, (relationTypeCount.get(relType) || 0) + 1)
    const from = String(relation.subject || relation.source || relation.from || relation.head || 'source')
    const to = String(relation.object || relation.target || relation.to || relation.tail || 'target')
    const line = `${from} -${relType}-> ${to}`
    relationExamples.push(line)
    const bucket = relationItemsByType.get(relType) || []
    bucket.push(line)
    relationItemsByType.set(relType, bucket)
  })

  return {
    elementGroups: Array.from(elementGroups.entries())
      .map(([label, values]) => ({
        label,
        items: Array.from(new Set(values)).slice(0, 40).map((value, index) => ({ id: `${label}-${index}-${value}`, value, label })),
      }))
      .sort((a, b) => b.items.length - a.items.length)
      .slice(0, 20),
    entityTypeItems: Array.from(entityTypeCount.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count }))
      .slice(0, 20),
    relationTypeItems: Array.from(relationTypeCount.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count }))
      .slice(0, 20),
    entityItemsByType: Object.fromEntries(
      Array.from(entityItemsByType.entries()).map(([type, list]) => [type, Array.from(new Set(list)).slice(0, 40)]),
    ) as Record<string, string[]>,
    relationItemsByType: Object.fromEntries(
      Array.from(relationItemsByType.entries()).map(([type, list]) => [type, Array.from(new Set(list)).slice(0, 40)]),
    ) as Record<string, string[]>,
    relationExamples: relationExamples.slice(0, 24),
  }
}

function normalizeSessionList(items: AgentSessionItem[] | undefined) {
  return [...(items || [])].sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
}

function getArtifactPreview(artifact: AgentArtifactItem | undefined) {
  if (!artifact) return '-'
  const content = String(artifact.content || artifact.summary || '').trim()
  if (!content) return '-'
  return content.length > 1800 ? `${content.slice(0, 1800)}...` : content
}

function getEventLabel(event: AgentEventItem) {
  return [event.event_type, event.severity].filter(Boolean).join(' · ') || '-'
}

function getTaskProgressLabel(task: AgentTaskItem) {
  const progress = task.progress || {}
  const toolUseCount = Number(progress.tool_use_count || 0)
  const tokenUsage = Number(progress.token_usage || 0)
  return `tools ${toolUseCount} | tokens ${tokenUsage}`
}

function getMessageLabel(message: AgentMessageItem) {
  return [message.actor, message.role].filter(Boolean).join(' · ') || '-'
}

const detailPreStyle = {
  marginTop: 8,
  maxHeight: 280,
  overflow: 'auto' as const,
  whiteSpace: 'pre-wrap' as const,
  overflowWrap: 'anywhere' as const,
}

function statusClass(status?: string | null) {
  const key = String(status || '').toLowerCase()
  if (key.includes('fail') || key.includes('error')) return 'chip chip-danger'
  if (key.includes('done') || key.includes('success') || key.includes('completed') || key.includes('approved')) return 'chip chip-ok'
  return 'chip chip-warn'
}

export default function OpsPage({ projectKey, variant = 'ops' }: OpsPageProps) {
  const queryClient = useQueryClient()
  const [retentionDays, setRetentionDays] = useState(90)
  const [pending, setPending] = useState(false)
  const [activeAction, setActiveAction] = useState('')
  const [statusText, setStatusText] = useState('就绪')
  const [errorText, setErrorText] = useState('')
  const [docIdsText, setDocIdsText] = useState('')
  const [topicScope, setTopicScope] = useState<'all' | 'company' | 'product' | 'operation'>('all')
  const [docPage, setDocPage] = useState(1)
  const [docTypeFilter, setDocTypeFilter] = useState('')
  const [docStateFilter, setDocStateFilter] = useState('')
  const [docSearch, setDocSearch] = useState('')
  const [selectedDocIds, setSelectedDocIds] = useState<number[]>([])
  const [activeDocCardId, setActiveDocCardId] = useState<number | null>(null)
  const [opsCardTab, setOpsCardTab] = useState<OpsCardTab>('business')
  const [extractMode, setExtractMode] = useState<'replace' | 'merge'>('merge')
  const [extractJsonText, setExtractJsonText] = useState('{}')
  const [sessionGoal, setSessionGoal] = useState('Review the current agent-session state and outstanding approvals.')
  const [sessionSource, setSessionSource] = useState<'user' | 'agent_batch' | 'workflow_graph'>('user')
  const [sessionCompatMode, setSessionCompatMode] = useState(false)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [selectedArtifactName, setSelectedArtifactName] = useState<string | null>(null)

  const adminStats = useQuery({ queryKey: queryKeys.admin.stats(projectKey), queryFn: getAdminStats, enabled: Boolean(projectKey) })
  const searchHistory = useQuery({ queryKey: queryKeys.admin.searchHistory(projectKey), queryFn: () => getSearchHistory(1, 30), enabled: Boolean(projectKey) })
  const agentSessionsQuery = useQuery({
    queryKey: queryKeys.agentSessions.list(),
    queryFn: listAgentSessions,
  })
  const adminDocuments = useQuery({
    queryKey: queryKeys.admin.documents(projectKey, docPage, docTypeFilter, docStateFilter, docSearch),
    queryFn: () =>
      listAdminDocuments({
        page: docPage,
        page_size: 20,
        doc_type: docTypeFilter.trim() || null,
        state: docStateFilter.trim() || null,
        search: docSearch.trim() || null,
      }),
    enabled: Boolean(projectKey),
  })
  const activeDocDetail = useQuery({
    queryKey: queryKeys.admin.documentDetail(projectKey, activeDocCardId),
    queryFn: () => getAdminDocument(Number(activeDocCardId)),
    enabled: Boolean(projectKey && activeDocCardId),
  })
  const selectedSessionQuery = useQuery({
    queryKey: queryKeys.agentSessions.detail(selectedSessionId || 'none'),
    queryFn: () => getAgentSession(selectedSessionId || ''),
    enabled: Boolean(selectedSessionId),
  })
  const createSessionMutation = useMutation({
    mutationFn: async () =>
      createAgentSession({
        project_key: projectKey,
        source: sessionSource,
        goal: sessionGoal.trim(),
        entrypoint_type: 'ops_panel',
        compat_mode: sessionCompatMode,
        initial_context: {
          project_key: projectKey,
          surface: 'ops',
        },
      }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
      const sessionId = String((result as AgentSessionDetail | null)?.session_id || '').trim()
      if (sessionId) {
        setSelectedSessionId(sessionId)
        setSelectedTaskId(null)
        setSelectedArtifactName('memory.md')
      }
    },
  })
  const cancelSessionMutation = useMutation({
    mutationFn: (sessionId: string) => cancelAgentSession(sessionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
    },
  })
  const retryTaskMutation = useMutation({
    mutationFn: ({ sessionId, taskId }: { sessionId: string; taskId: string }) =>
      retryAgentSessionTask(sessionId, { task_id: taskId }),
    onSuccess: async (_result, variables) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(variables.sessionId) })
    },
  })
  const resolveApprovalMutation = useMutation({
    mutationFn: ({ approvalId, approved }: { approvalId: string; approved: boolean }) =>
      resolveAgentApproval(approvalId, { approved, reason: approved ? 'approved_from_ops_panel' : 'rejected_from_ops_panel' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
      if (selectedSessionId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
      }
    },
  })
  const reclaimExpiredMutation = useMutation({
    mutationFn: (sessionId: string) => reclaimExpiredAgentSessionTasks(sessionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
      if (selectedSessionId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
      }
    },
  })
  const coordinatorPassMutation = useMutation({
    mutationFn: (sessionId: string) => runAgentSessionCoordinatorPass(sessionId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
      if (selectedSessionId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
      }
    },
  })
  const normalizedSessions = useMemo(
    () => normalizeSessionList(agentSessionsQuery.data || undefined),
    [agentSessionsQuery.data],
  )
  useEffect(() => {
    if (!selectedSessionId && normalizedSessions.length) {
      setSelectedSessionId(normalizedSessions[0].session_id)
      setSelectedTaskId(null)
      setSelectedArtifactName('memory.md')
    }
  }, [normalizedSessions, selectedSessionId])
  const selectedSession = selectedSessionQuery.data
  const selectedSessionTasks = selectedSession?.tasks || []
  const selectedSessionEvents = selectedSession?.events || []
  const selectedSessionArtifacts = useMemo(
    () => selectedSession?.artifacts || [],
    [selectedSession?.artifacts],
  )
  const selectedSessionApprovals = selectedSession?.approvals || []
  const selectedSessionMessages = selectedSession?.messages || []
  const selectedArtifact = useMemo(
    () => selectedSessionArtifacts.find((artifact) => artifact.name === selectedArtifactName) || selectedSessionArtifacts[0],
    [selectedArtifactName, selectedSessionArtifacts],
  )
  const selectedAgentTask = selectedSessionTasks.find((task) => task.task_id === selectedTaskId) || selectedSessionTasks[0]

  useEffect(() => {
    if (!selectedSessionId || typeof window === 'undefined' || typeof EventSource === 'undefined') return undefined
    const streamUrl = `${endpoints.agentSessions.streamBySession(selectedSessionId)}?since_seq=0&poll_seconds=1&max_seconds=60`
    const source = new EventSource(streamUrl, { withCredentials: false })
    let refreshTimer: number | null = null
    const scheduleRefresh = () => {
      if (refreshTimer != null) window.clearTimeout(refreshTimer)
      refreshTimer = window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
        void queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.list() })
      }, 150)
    }
    source.onmessage = () => {
      scheduleRefresh()
    }
    source.onerror = () => {
      source.close()
    }
    return () => {
      if (refreshTimer != null) window.clearTimeout(refreshTimer)
      source.close()
    }
  }, [queryClient, selectedSessionId])

  const selectedCount = selectedDocIds.length
  const selectedCsv = useMemo(() => selectedDocIds.join(','), [selectedDocIds])
  const parsedDocIds = useMemo(() => {
    const tokens = docIdsText
      .split(/[,\s]+/)
      .map((item) => Number.parseInt(item.trim(), 10))
      .filter((item) => Number.isFinite(item) && item > 0)
    return Array.from(new Set(tokens))
  }, [docIdsText])
  const docTotalPages = Math.max(1, Math.ceil((adminDocuments.data?.total || 0) / Math.max(1, adminDocuments.data?.page_size || 20)))
  const graphExtension = useMemo(
    () => buildOpsGraphExtension(activeDocDetail.data, activeDocCardId),
    [activeDocDetail.data, activeDocCardId],
  )

  const toggleDocSelection = (docId: number) => {
    setSelectedDocIds((prev) => (prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]))
  }

  const selectCurrentPage = () => {
    const pageIds = (adminDocuments.data?.items || []).map((item) => item.id)
    setSelectedDocIds(pageIds)
  }

  const runAction = async (
    name: string,
    fn: () => Promise<unknown>,
    options?: { refreshStats?: boolean; refreshSearchHistory?: boolean; refreshDocuments?: boolean },
  ) => {
    setPending(true)
    setActiveAction(name)
    setErrorText('')
    setStatusText(`${name} 执行中...`)
    try {
      const result = await fn()
      const taskId = typeof (result as { task_id?: unknown })?.task_id === 'string' ? String((result as { task_id?: string }).task_id) : ''
      setStatusText(taskId ? `${name} 已提交，任务 ID: ${taskId}` : `${name} 完成`)
      if (options?.refreshStats !== false) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.admin.stats(projectKey) })
      }
      if (options?.refreshSearchHistory !== false) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.admin.searchHistory(projectKey) })
      }
      if (options?.refreshDocuments !== false) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.admin.documentsBase(projectKey) })
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : '未知错误'
      setStatusText(`${name} 失败`)
      setErrorText(message)
    } finally {
      setPending(false)
      setActiveAction('')
    }
  }

  return (
    <div className={`content-stack gv2-root ops-page ops-page--${variant}`}>
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'backend' ? '后端监控视图' : '数据运维视图'}</h2>
        </div>
      </section>
      <section className="kpi-grid">
        <article className="kpi-card"><span>文档</span><strong>{adminStats.data?.documents?.total || 0}</strong><small>今日 {adminStats.data?.documents?.recent_today || 0}</small></article>
        <article className="kpi-card"><span>社媒文档</span><strong>{adminStats.data?.social_data?.total || 0}</strong><small>今日 {adminStats.data?.social_data?.recent_today || 0}</small></article>
        <article className="kpi-card"><span>来源数</span><strong>{adminStats.data?.sources?.total || 0}</strong><small>resource pool</small></article>
        <article className="kpi-card"><span>搜索历史</span><strong>{adminStats.data?.search_history?.total || 0}</strong><small>history</small></article>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>
            <Eye size={15} />
            Agent Session 面板
          </h2>
          <div className="inline-actions">
            <button
              type="button"
              onClick={() => {
                void queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.all() })
                if (selectedSessionId) {
                  void queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
                }
              }}
            >
              <RefreshCw size={14} />
              刷新
            </button>
            <button
              type="button"
              onClick={() => {
                void createSessionMutation.mutateAsync()
              }}
              disabled={!sessionGoal.trim() || createSessionMutation.isPending}
            >
              创建 Session
            </button>
          </div>
        </div>

        <div className="grid-2" style={{ alignItems: 'start' }}>
          <div className="panel" style={{ margin: 0 }}>
            <div className="panel-header">
              <h3>新建 Session</h3>
            </div>
            <div className="stack" style={{ gap: 12 }}>
              <label className="stack" style={{ gap: 6 }}>
                <span>Goal</span>
                <textarea value={sessionGoal} onChange={(e) => setSessionGoal(e.target.value)} rows={4} />
              </label>
              <div className="grid-2">
                <label className="stack" style={{ gap: 6 }}>
                  <span>Source</span>
                  <select value={sessionSource} onChange={(e) => setSessionSource(e.target.value as 'user' | 'agent_batch' | 'workflow_graph')}>
                    <option value="user">user</option>
                    <option value="agent_batch">agent_batch</option>
                    <option value="workflow_graph">workflow_graph</option>
                  </select>
                </label>
                <label className="stack" style={{ gap: 6 }}>
                  <span>Compat Mode</span>
                  <label style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={sessionCompatMode}
                      onChange={(e) => setSessionCompatMode(e.target.checked)}
                    />
                    project compat projection
                  </label>
                </label>
              </div>
              <div className="inline-actions">
                <button
                  type="button"
                  onClick={() => {
                    void createSessionMutation.mutateAsync()
                  }}
                  disabled={!sessionGoal.trim() || createSessionMutation.isPending}
                >
                  {createSessionMutation.isPending ? '创建中...' : '创建'}
                </button>
                {selectedSessionId ? <span className="chip">当前 session: {selectedSessionId}</span> : null}
              </div>
            </div>
          </div>

          <div className="panel" style={{ margin: 0 }}>
            <div className="panel-header">
              <h3>Session 列表</h3>
              <span className="chip">{normalizedSessions.length} items</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Session</th>
                    <th>Status</th>
                    <th>Phase</th>
                    <th>Tasks</th>
                    <th>Updated</th>
                    <th>Open</th>
                  </tr>
                </thead>
                <tbody>
                  {normalizedSessions.map((session) => (
                    <tr key={session.session_id} className={session.session_id === selectedSessionId ? 'row-selected' : undefined}>
                      <td>
                        <div>{session.session_id}</div>
                        <small>{session.source || '-'} · {session.project_key || 'n/a'}</small>
                      </td>
                      <td><span className={statusClass(session.status)}>{session.status || '-'}</span></td>
                      <td>{session.current_phase || '-'}</td>
                      <td>{session.task_count ?? '-'}</td>
                      <td>{formatDate(session.updated_at)}</td>
                      <td>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedSessionId(session.session_id)
                            setSelectedTaskId(null)
                            setSelectedArtifactName('memory.md')
                          }}
                        >
                          查看
                        </button>
                      </td>
                    </tr>
                  ))}
                  {!normalizedSessions.length ? (
                    <tr>
                      <td colSpan={6} className="empty-cell">
                        暂无 session
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {selectedSession ? (
          <div className="grid-2" style={{ marginTop: 16, alignItems: 'start' }}>
            <div className="panel" style={{ margin: 0 }}>
              <div className="panel-header">
                <h3>Session 详情</h3>
                <div className="inline-actions">
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSessionId) return
                      void cancelSessionMutation.mutateAsync(selectedSessionId)
                    }}
                    disabled={!selectedSessionId || cancelSessionMutation.isPending}
                  >
                    <XCircle size={14} />
                    取消 Session
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSessionId) return
                      void queryClient.invalidateQueries({ queryKey: queryKeys.agentSessions.detail(selectedSessionId) })
                    }}
                  >
                    <RefreshCw size={14} />
                    刷新详情
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSessionId) return
                      void coordinatorPassMutation.mutateAsync(selectedSessionId)
                    }}
                    disabled={!selectedSessionId || coordinatorPassMutation.isPending}
                  >
                    <RefreshCw size={14} />
                    Coordinator Pass
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (!selectedSessionId) return
                      void reclaimExpiredMutation.mutateAsync(selectedSessionId)
                    }}
                    disabled={!selectedSessionId || reclaimExpiredMutation.isPending}
                  >
                    <Trash2 size={14} />
                    回收过期 Lease
                  </button>
                </div>
              </div>
              <div className="kpi-grid" style={{ marginTop: 0 }}>
                <article className="kpi-card">
                  <span>Status</span>
                  <strong>{selectedSession.status || '-'}</strong>
                  <small>{selectedSession.current_phase || '-'}</small>
                </article>
                <article className="kpi-card">
                  <span>Tasks</span>
                  <strong>{selectedSessionTasks.length}</strong>
                  <small>events {selectedSessionEvents.length} · messages {selectedSessionMessages.length}</small>
                </article>
                <article className="kpi-card">
                  <span>Artifacts</span>
                  <strong>{selectedSessionArtifacts.length}</strong>
                  <small>approvals {selectedSessionApprovals.length}</small>
                </article>
                <article className="kpi-card">
                  <span>Compat</span>
                  <strong>{selectedSession.compat_mode ? 'yes' : 'no'}</strong>
                  <small>{selectedSession.compat_projection_version || '-'}</small>
                </article>
              </div>
              <div className="stack" style={{ gap: 12 }}>
                <div>
                  <strong>Goal</strong>
                  <div>{selectedSession.goal || '-'}</div>
                </div>
                <div>
                  <strong>Artifacts</strong>
                  <div className="inline-actions" style={{ marginTop: 8, flexWrap: 'wrap' }}>
                    {selectedSessionArtifacts.map((artifact) => (
                      <button
                        key={artifact.artifact_id}
                        type="button"
                        className={artifact.name === selectedArtifactName ? 'chip chip-ok' : 'chip'}
                        onClick={() => setSelectedArtifactName(artifact.name || artifact.artifact_id)}
                      >
                        {artifact.name || artifact.artifact_id}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <strong>Selected Artifact</strong>
                  <pre style={{ ...detailPreStyle, maxHeight: 220 }}>{getArtifactPreview(selectedArtifact)}</pre>
                </div>
              </div>
            </div>

            <div className="panel" style={{ margin: 0 }}>
              <div className="panel-header">
                <h3>Tasks / Approvals / Events</h3>
              </div>
              <div className="stack" style={{ gap: 16 }}>
                <section className="panel" style={{ margin: 0 }}>
                  <div className="panel-header">
                    <h4>Task Tree</h4>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Task</th>
                          <th>Status</th>
                          <th>Phase</th>
                          <th>Progress</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedSessionTasks.map((task) => (
                          <tr key={task.task_id} className={task.task_id === selectedTaskId ? 'row-selected' : undefined}>
                            <td>
                              <div>{task.subject || task.task_id}</div>
                              <small>{task.task_type || '-'} · {task.owner || '-'}</small>
                            </td>
                            <td><span className={statusClass(task.status)}>{task.status || '-'}</span></td>
                            <td>{task.phase || '-'}</td>
                            <td>{getTaskProgressLabel(task)}</td>
                            <td>
                              <div className="inline-actions">
                                <button type="button" onClick={() => setSelectedTaskId(task.task_id)}>查看</button>
                                {String(task.status || '') === 'failed' ? (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      if (!selectedSessionId) return
                                      void retryTaskMutation.mutateAsync({ sessionId: selectedSessionId, taskId: task.task_id })
                                    }}
                                    disabled={!selectedSessionId || retryTaskMutation.isPending}
                                  >
                                    重试
                                  </button>
                                ) : null}
                              </div>
                            </td>
                          </tr>
                        ))}
                        {!selectedSessionTasks.length ? (
                          <tr>
                            <td colSpan={5} className="empty-cell">暂无任务</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                  {selectedAgentTask ? (
                    <div style={{ marginTop: 12 }}>
                      <strong>Selected Task Detail</strong>
                      <pre style={{ ...detailPreStyle, maxHeight: 200 }}>{JSON.stringify(selectedAgentTask, null, 2)}</pre>
                    </div>
                  ) : null}
                </section>

                <section className="panel" style={{ margin: 0 }}>
                  <div className="panel-header">
                    <h4>Approvals</h4>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Approval</th>
                          <th>Status</th>
                          <th>Requester</th>
                          <th>Expires</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedSessionApprovals.map((approval) => (
                          <tr key={approval.approval_id}>
                            <td>
                              <div>{approval.approval_id}</div>
                              <small>{approval.binding_hash || '-'}</small>
                            </td>
                            <td><span className={statusClass(approval.status)}>{approval.status || '-'}</span></td>
                            <td>
                              <div>{approval.requester_session_id || approval.session_id || approval.requested_by || '-'}</div>
                              <small>{approval.requester_task_id || approval.task_id || '-'}</small>
                            </td>
                            <td>{formatDate(approval.expires_at)}</td>
                            <td>
                              <div className="inline-actions">
                                <button
                                  type="button"
                                  onClick={() => {
                                    void resolveApprovalMutation.mutateAsync({ approvalId: approval.approval_id, approved: true })
                                  }}
                                  disabled={resolveApprovalMutation.isPending}
                                >
                                  <CheckCircle2 size={14} />
                                  批准
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    void resolveApprovalMutation.mutateAsync({ approvalId: approval.approval_id, approved: false })
                                  }}
                                  disabled={resolveApprovalMutation.isPending}
                                >
                                  <XCircle size={14} />
                                  拒绝
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                        {!selectedSessionApprovals.length ? (
                          <tr>
                            <td colSpan={5} className="empty-cell">暂无审批</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                  <div style={{ marginTop: 12 }}>
                    <strong>Approval Payload</strong>
                    <pre style={{ ...detailPreStyle, maxHeight: 180 }}>
                      {selectedSessionApprovals[0] ? JSON.stringify(selectedSessionApprovals[0].binding_payload || {}, null, 2) : '-'}
                    </pre>
                  </div>
                </section>

                <section className="panel" style={{ margin: 0 }}>
                  <div className="panel-header">
                    <h4>Events</h4>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Seq</th>
                          <th>Type</th>
                          <th>Task</th>
                          <th>Message</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedSessionEvents.slice().reverse().slice(0, 12).map((event) => (
                          <tr key={`${event.event_type}-${event.ts}-${event.task_id || event.session_id}`}>
                            <td>{(event as { seq?: number }).seq || '-'}</td>
                            <td>{getEventLabel(event)}</td>
                            <td>{event.task_id || '-'}</td>
                            <td>{event.message || JSON.stringify(event.payload || {})}</td>
                          </tr>
                        ))}
                        {!selectedSessionEvents.length ? (
                          <tr>
                            <td colSpan={4} className="empty-cell">暂无事件</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="panel" style={{ margin: 0 }}>
                  <div className="panel-header">
                    <h4>Coordinator Messages</h4>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>When</th>
                          <th>Actor</th>
                          <th>Task</th>
                          <th>Content</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selectedSessionMessages.slice().reverse().slice(0, 12).map((message) => (
                          <tr key={`${message.created_at}-${message.actor}-${message.task_id || 'session'}`}>
                            <td>{formatDate(message.created_at)}</td>
                            <td>{getMessageLabel(message)}</td>
                            <td>{message.task_id || '-'}</td>
                            <td>{message.content || '-'}</td>
                          </tr>
                        ))}
                        {!selectedSessionMessages.length ? (
                          <tr>
                            <td colSpan={4} className="empty-cell">暂无消息</td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                </section>
              </div>
            </div>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header"><h2>治理动作</h2></div>
        <div className="inline-actions">
          <label><span>retention_days</span><input type="number" min={1} max={3650} value={retentionDays} onChange={(e) => setRetentionDays(Number.parseInt(e.target.value || '90', 10) || 90)} /></label>
          <label>
            <span>doc_ids</span>
            <input type="text" value={docIdsText} onChange={(e) => setDocIdsText(e.target.value)} placeholder="101,102,103" />
          </label>
          <button
            disabled={!selectedCount}
            onClick={() => setDocIdsText(selectedCsv)}
          >
            使用所选({selectedCount})
          </button>
          <label>
            <span>topic_scope</span>
            <select value={topicScope} onChange={(e) => setTopicScope(e.target.value as 'all' | 'company' | 'product' | 'operation')}>
              <option value="all">all</option>
              <option value="company">company</option>
              <option value="product">product</option>
              <option value="operation">operation</option>
            </select>
          </label>
          <button disabled={pending} onClick={() => runAction('数据清理', () => cleanupGovernance(retentionDays))}><Trash2 size={14} />{activeAction === '数据清理' ? '执行中...' : '清理旧数据'}</button>
          <button
            disabled={pending}
            onClick={() => {
              const docIds = parsedDocIds
              runAction('文档重提取', () => reExtractDocuments(docIds.length ? { doc_ids: docIds } : {}))
            }}
          >
            <RefreshCw size={14} />{activeAction === '文档重提取' ? '执行中...' : '文档重提取'}
          </button>
          <button
            disabled={pending}
            onClick={() => {
              const docIds = parsedDocIds
              const topics: Array<'company' | 'product' | 'operation'> = topicScope === 'all' ? ['company', 'product', 'operation'] : [topicScope]
              const payload = {
                topics,
                ...(docIds.length ? { doc_ids: docIds } : {}),
              }
              runAction('专题提取', () => topicExtractDocuments(payload))
            }}
          >
            <RefreshCw size={14} />{activeAction === '专题提取' ? '执行中...' : '专题提取'}
          </button>
          <button
            disabled={pending}
            onClick={() => {
              const docIds = parsedDocIds
              if (!docIds.length) {
                setStatusText('图谱导出 失败')
                setErrorText('请先输入 doc_ids（逗号或空格分隔）')
                return
              }
              runAction(
                '图谱导出',
                async () => {
                  const result = await exportGraph(docIds)
                  const nodes = Array.isArray(result?.nodes) ? result.nodes.length : 0
                  const edges = Array.isArray(result?.edges) ? result.edges.length : 0
                  setStatusText(`图谱导出完成，nodes=${nodes}, edges=${edges}`)
                  return result
                },
                { refreshStats: false, refreshSearchHistory: false },
              )
            }}
          >
            <RefreshCw size={14} />{activeAction === '图谱导出' ? '执行中...' : '图谱导出'}
          </button>
          <button disabled={pending} onClick={() => runAction('聚合库同步', () => syncAggregator(true))}><RefreshCw size={14} />{activeAction === '聚合库同步' ? '执行中...' : '同步 Aggregator'}</button>
          <button onClick={() => { queryClient.invalidateQueries({ queryKey: queryKeys.admin.stats(projectKey) }); queryClient.invalidateQueries({ queryKey: queryKeys.admin.searchHistory(projectKey) }); }}><RefreshCw size={14} />刷新</button>
        </div>
        <p className="status-line">{statusText}</p>
        {!!errorText && <p className="status-line">{errorText}</p>}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>文档治理</h2>
          <div className="inline-actions">
            <button onClick={() => queryClient.invalidateQueries({ queryKey: queryKeys.admin.documentsBase(projectKey) })} disabled={adminDocuments.isFetching}>
              <RefreshCw size={14} />
              {adminDocuments.isFetching ? '刷新中...' : '刷新文档'}
            </button>
            <button onClick={selectCurrentPage} disabled={!(adminDocuments.data?.items || []).length}>选择当前页</button>
            <button onClick={() => setSelectedDocIds([])} disabled={!selectedCount}>清空选择</button>
          </div>
        </div>
        <div className="form-grid cols-4">
          <label>
            <span>doc_type</span>
            <input value={docTypeFilter} onChange={(e) => { setDocTypeFilter(e.target.value); setDocPage(1) }} placeholder="policy / market_info" />
          </label>
          <label>
            <span>state</span>
            <input value={docStateFilter} onChange={(e) => { setDocStateFilter(e.target.value); setDocPage(1) }} placeholder="state" />
          </label>
          <label>
            <span>search</span>
            <input value={docSearch} onChange={(e) => { setDocSearch(e.target.value); setDocPage(1) }} placeholder="标题关键词" />
          </label>
          <label>
            <span>extract_mode</span>
            <select value={extractMode} onChange={(e) => setExtractMode(e.target.value as 'replace' | 'merge')}>
              <option value="merge">merge</option>
              <option value="replace">replace</option>
            </select>
          </label>
        </div>
        <div className="form-grid cols-2">
          <label>
            <span>extracted_data(JSON)</span>
            <textarea rows={6} value={extractJsonText} onChange={(e) => setExtractJsonText(e.target.value)} />
          </label>
          <div className="inline-actions">
            <button
              disabled={pending || !selectedCount}
              onClick={() => {
                runAction('批量写入结构化', async () => {
                  let parsed: unknown
                  try {
                    parsed = JSON.parse(extractJsonText || '{}')
                  } catch {
                    throw new Error('extracted_data 不是合法 JSON')
                  }
                  return bulkUpdateDocumentExtractedData({
                    doc_ids: selectedDocIds,
                    mode: extractMode,
                    extracted_data: parsed,
                  })
                })
              }}
            >
              批量写入结构化
            </button>
            <button
              disabled={pending || !selectedCount}
              onClick={() => runAction('清空结构化', () => clearDocumentExtractedData(selectedDocIds))}
            >
              清空结构化
            </button>
            <button
              disabled={pending || !selectedCount}
              onClick={() => runAction('删除文档', () => deleteAdminDocuments({ ids: selectedDocIds }))}
            >
              删除文档
            </button>
          </div>
        </div>
        <p className="status-line">已选择文档: {selectedCount}</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>选中</th>
                <th>ID</th>
                <th>标题</th>
                <th>类型</th>
                <th>州</th>
                <th>提取</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {(adminDocuments.data?.items || []).map((row) => (
                <tr
                  key={row.id}
                  onClick={() => {
                    let nextId: number | null = row.id
                    setActiveDocCardId((prev) => {
                      nextId = prev === row.id ? null : row.id
                      return nextId
                    })
                    if (nextId === null) {
                      return
                    }
                    setOpsCardTab('business')
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedDocIds.includes(row.id)}
                      onChange={() => toggleDocSelection(row.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </td>
                  <td>{row.id}</td>
                  <td>{row.title || '-'}</td>
                  <td>{row.doc_type || '-'}</td>
                  <td>{row.state || '-'}</td>
                  <td>{String(row.has_extracted_data ?? false)}</td>
                  <td>{formatDate(row.updated_at)}</td>
                </tr>
              ))}
              {!adminDocuments.data?.items?.length ? (
                <tr>
                  <td colSpan={7} className="empty-cell">暂无文档</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="inline-actions">
          <button disabled={docPage <= 1} onClick={() => setDocPage((p) => Math.max(1, p - 1))}>上一页</button>
          <span className="chip">第 {docPage}/{docTotalPages} 页</span>
          <button disabled={docPage >= docTotalPages} onClick={() => setDocPage((p) => Math.min(docTotalPages, p + 1))}>下一页</button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header"><h2>搜索历史</h2></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>ID</th><th>topic</th><th>last_search_time</th></tr></thead>
            <tbody>
              {(searchHistory.data || []).map((row) => (
                <tr key={row.id}><td>{row.id}</td><td>{row.topic || '-'}</td><td>{formatDate(row.last_search_time)}</td></tr>
              ))}
              {!searchHistory.data?.length && <tr><td colSpan={3} className="empty-cell">暂无搜索历史</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      {activeDocCardId ? (
        <GraphNodeCard
          title={activeDocDetail.data?.title || `文档 ${activeDocCardId}`}
          subtitle={activeDocDetail.data?.doc_type || '-'}
          style={{
            position: 'fixed',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            width: 'min(720px, calc(100vw - 40px))',
            maxHeight: 'calc(100vh - 80px)',
            overflow: 'auto',
            zIndex: 80,
          }}
          actions={
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <div className="gv2-card-tabs" role="tablist" aria-label="卡片标签">
                <button
                  type="button"
                  role="tab"
                  aria-selected={opsCardTab === 'business'}
                  className={`gv2-card-tab ${opsCardTab === 'business' ? 'is-active' : ''}`.trim()}
                  onClick={() => {
                    setOpsCardTab('business')
                  }}
                  title="业务数据"
                >
                  业务数据
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={opsCardTab === 'graph_ext'}
                  className={`gv2-card-tab ${opsCardTab === 'graph_ext' ? 'is-active' : ''}`.trim()}
                  onClick={() => setOpsCardTab('graph_ext')}
                  title="图谱扩展"
                >
                  图谱扩展
                </button>
              </div>
              <button
                type="button"
                onClick={() => {
                  void queryClient.invalidateQueries({ queryKey: queryKeys.admin.documentDetail(projectKey, activeDocCardId) })
                }}
                title="刷新"
              >
                ↻
              </button>
            </div>
          }
          onClose={() => {
            setActiveDocCardId(null)
            setOpsCardTab('business')
          }}
        >
          {activeDocDetail.isFetching ? (
            <div className="gv2-node-grid">
              <div className="gv2-node-grid-item">
                <label>状态</label>
                <strong>加载中...</strong>
              </div>
            </div>
          ) : (
            <>
              {opsCardTab === 'business' ? <GraphBusinessCardSections node={toGraphBusinessNode(activeDocDetail.data, activeDocCardId)} /> : null}
              {opsCardTab === 'graph_ext' ? (
                <GraphExtensionsSections
                  key={`ops-graph-ext-${activeDocCardId || 'none'}`}
                  graphInfo={{
                    degree: graphExtension.relationExamples.length,
                    neighborTypeCount: graphExtension.entityTypeItems.length,
                    marketDocCount: graphExtension.relationTypeItems.length,
                    neighborTypeItems: graphExtension.entityTypeItems,
                    predicateItems: graphExtension.relationTypeItems.map((item) => ({ predicate: item.type, count: item.count })),
                    neighborNodesByType: Object.fromEntries(
                      Object.entries(graphExtension.entityItemsByType).map(([type, names]) => [
                        type,
                        names.map((name, idx) => ({ id: `${type}-${idx}`, name, type })),
                      ]),
                    ),
                    relationsByPredicate: Object.fromEntries(
                      Object.entries(graphExtension.relationItemsByType).map(([type, lines]) => [
                        type,
                        lines.map((line, idx) => ({ id: `${type}-${idx}`, direction: 'OUT' as const, targetName: line, targetType: 'Relation' })),
                      ]),
                    ),
                  }}
                  nodeElementGroups={graphExtension.elementGroups}
                  relationGroups={graphExtension.relationTypeItems.map((item) => ({
                    relation: item.type,
                    items: (graphExtension.relationItemsByType[item.type] || []).map((line, idx) => ({
                      id: `${item.type}-${idx}`,
                      direction: 'OUT' as const,
                      relation: item.type,
                      targetName: line,
                      targetType: 'Relation',
                    })),
                  }))}
                  nodeTypeColor={{ Relation: '#c4b5fd' }}
                  chipColorForIndex={opsChipColorForIndex}
                  elementColorForLabel={opsElementColorForLabel}
                />
              ) : null}
            </>
          )}
        </GraphNodeCard>
      ) : null}
    </div>
  )
}

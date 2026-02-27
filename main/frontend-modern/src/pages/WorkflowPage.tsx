import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, RefreshCw, Save, Trash2 } from 'lucide-react'
import { deleteWorkflowTemplate, getProcessTaskDetail, getProcessTaskLogs, getWorkflowTemplate, listWorkflows, runWorkflow, upsertWorkflowTemplate } from '../lib/api'
import type { WorkflowTemplatePayload } from '../lib/types'

type WorkflowPageProps = {
  projectKey: string
  variant?: 'workflow' | 'graphMarket' | 'graphSocial' | 'graphDeep'
}

export default function WorkflowPage({ projectKey, variant = 'workflow' }: WorkflowPageProps) {
  const queryClient = useQueryClient()
  const [workflowName, setWorkflowName] = useState('')
  const [paramsText, setParamsText] = useState('{}')
  const [stepsText, setStepsText] = useState('[]')
  const [boardLayoutText, setBoardLayoutText] = useState('{}')
  const [statusText, setStatusText] = useState('等待操作')
  const [validationText, setValidationText] = useState('')
  const [running, setRunning] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [runHistory, setRunHistory] = useState<Array<{ taskId: string; workflowName: string; createdAt: string }>>([])
  const [selectedRunTaskId, setSelectedRunTaskId] = useState<string | null>(null)

  const workflows = useQuery({ queryKey: ['workflows', projectKey], queryFn: listWorkflows, enabled: Boolean(projectKey) })

  useEffect(() => {
    if (!workflowName && workflows.data?.length) setWorkflowName(workflows.data[0])
  }, [workflowName, workflows.data])

  const workflowTemplate = useQuery({
    queryKey: ['workflow-template', projectKey, workflowName],
    queryFn: () => getWorkflowTemplate(workflowName),
    enabled: Boolean(projectKey) && Boolean(workflowName),
  })
  const selectedRunDetail = useQuery({
    queryKey: ['workflow-run-detail', projectKey, selectedRunTaskId],
    queryFn: () => getProcessTaskDetail(String(selectedRunTaskId)),
    enabled: Boolean(projectKey && selectedRunTaskId),
    refetchInterval: 8000,
    refetchIntervalInBackground: true,
  })
  const selectedRunLogs = useQuery({
    queryKey: ['workflow-run-logs', projectKey, selectedRunTaskId],
    queryFn: () => getProcessTaskLogs(String(selectedRunTaskId), 200),
    enabled: Boolean(projectKey && selectedRunTaskId),
    refetchInterval: 8000,
    refetchIntervalInBackground: true,
  })

  useEffect(() => {
    if (!workflowTemplate.data) return
    const steps = Array.isArray(workflowTemplate.data.steps) ? workflowTemplate.data.steps : []
    const boardLayout = workflowTemplate.data.board_layout ?? workflowTemplate.data.boardLayout ?? {}
    setStepsText(JSON.stringify(steps, null, 2))
    setBoardLayoutText(JSON.stringify(boardLayout, null, 2))
    setValidationText('')
  }, [workflowTemplate.data])

  const editedStepsPreview = useMemo(() => {
    try {
      const parsed = JSON.parse(stepsText || '[]') as unknown
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }, [stepsText])

  const parseTemplatePayload = (): WorkflowTemplatePayload => {
    let parsedSteps: unknown
    let parsedBoardLayout: unknown

    try {
      parsedSteps = JSON.parse(stepsText || '[]')
    } catch {
      throw new Error('steps 不是合法 JSON')
    }
    if (!Array.isArray(parsedSteps)) {
      throw new Error('steps 必须是数组')
    }
    if (!parsedSteps.length) {
      throw new Error('steps 不能为空')
    }
    for (const [index, step] of parsedSteps.entries()) {
      if (!step || typeof step !== 'object') {
        throw new Error(`steps[${index}] 必须是对象`)
      }
      const handler = (step as { handler?: unknown }).handler
      if (typeof handler !== 'string' || !handler.trim()) {
        throw new Error(`steps[${index}].handler 不能为空`)
      }
    }

    try {
      parsedBoardLayout = JSON.parse(boardLayoutText || '{}')
    } catch {
      throw new Error('board_layout 不是合法 JSON')
    }
    if (!parsedBoardLayout || typeof parsedBoardLayout !== 'object' || Array.isArray(parsedBoardLayout)) {
      throw new Error('board_layout 必须是对象')
    }

    return {
      project_key: projectKey,
      steps: parsedSteps as WorkflowTemplatePayload['steps'],
      board_layout: parsedBoardLayout as Record<string, unknown>,
    }
  }

  const onRun = async () => {
    if (!workflowName) return
    setRunning(true)
    setValidationText('')
    setStatusText('运行中...')
    try {
      const params = JSON.parse(paramsText || '{}') as Record<string, unknown>
      const result = await runWorkflow(workflowName, params)
      const taskId = typeof result?.task_id === 'string' ? result.task_id : ''
      if (taskId) {
        setRunHistory((prev) => {
          const next = [{ taskId, workflowName, createdAt: new Date().toISOString() }, ...prev.filter((item) => item.taskId !== taskId)]
          return next.slice(0, 15)
        })
        setSelectedRunTaskId(taskId)
      }
      setStatusText(taskId ? `已提交，任务 ID: ${taskId}` : '执行完成')
    } catch (error) {
      setStatusText(`执行失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setRunning(false)
    }
  }

  const onSaveTemplate = async () => {
    if (!workflowName) return
    let payload: WorkflowTemplatePayload
    try {
      payload = parseTemplatePayload()
    } catch (error) {
      const message = error instanceof Error ? error.message : '模板格式不正确'
      setValidationText(message)
      setStatusText(`保存失败: ${message}`)
      return
    }

    setSaving(true)
    setValidationText('')
    setStatusText('保存中...')
    try {
      await upsertWorkflowTemplate(workflowName, payload)
      setStatusText('模板已保存')
      await queryClient.invalidateQueries({ queryKey: ['workflow-template', projectKey, workflowName] })
      await queryClient.invalidateQueries({ queryKey: ['workflows', projectKey] })
    } catch (error) {
      setStatusText(`保存失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setSaving(false)
    }
  }

  const onDeleteTemplate = async () => {
    if (!workflowName) return
    setDeleting(true)
    setValidationText('')
    setStatusText('删除中...')
    try {
      await deleteWorkflowTemplate(workflowName, projectKey)
      setStatusText('模板已删除')
      await queryClient.invalidateQueries({ queryKey: ['workflow-template', projectKey, workflowName] })
      await queryClient.invalidateQueries({ queryKey: ['workflows', projectKey] })
    } catch (error) {
      setStatusText(`删除失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="content-stack">
      <section className="panel">
        <div className="panel-header">
          <h2>{variant === 'workflow' ? '工作流模板' : '图谱构建工作流'}</h2>
          <span className="chip">{variant}</span>
        </div>
      </section>
      <section className="panel">
        <div className="panel-header">
          <h2>工作流运行</h2>
          <div className="inline-actions">
            <button onClick={() => queryClient.invalidateQueries({ queryKey: ['workflows', projectKey] })}>
              <RefreshCw size={14} />刷新
            </button>
          </div>
        </div>

        <div className="form-grid cols-3">
          <label>
            <span>workflow</span>
            <select value={workflowName} onChange={(e) => setWorkflowName(e.target.value)}>
              {(workflows.data || []).map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </label>
          <label>
            <span>params(JSON)</span>
            <textarea rows={4} value={paramsText} onChange={(e) => setParamsText(e.target.value)} />
          </label>
          <div className="inline-actions">
            <button disabled={!workflowName || running} onClick={onRun}>
              <Play size={14} />{running ? '运行中...' : '运行'}
            </button>
          </div>
        </div>
        <p className="status-line">{statusText}</p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>运行结果回显</h2>
          <div className="inline-actions">
            <button
              disabled={!selectedRunTaskId}
              onClick={() => {
                if (!selectedRunTaskId) return
                void queryClient.invalidateQueries({ queryKey: ['workflow-run-detail', projectKey, selectedRunTaskId] })
                void queryClient.invalidateQueries({ queryKey: ['workflow-run-logs', projectKey, selectedRunTaskId] })
              }}
            >
              <RefreshCw size={14} />刷新详情
            </button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>task_id</th>
                <th>workflow</th>
                <th>created_at</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {runHistory.map((item) => (
                <tr key={item.taskId}>
                  <td>{item.taskId}</td>
                  <td>{item.workflowName}</td>
                  <td>{new Date(item.createdAt).toLocaleString('zh-CN')}</td>
                  <td>
                    <button onClick={() => setSelectedRunTaskId(item.taskId)}>{selectedRunTaskId === item.taskId ? '已选中' : '查看'}</button>
                  </td>
                </tr>
              ))}
              {!runHistory.length ? (
                <tr>
                  <td colSpan={4} className="empty-cell">暂无运行记录</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        {selectedRunTaskId ? (
          <div className="content-stack">
            <p className="status-line">task_id: {selectedRunTaskId}</p>
            <p className="status-line">status: {selectedRunDetail.data?.status || '-'}</p>
            <p className="status-line">started_at: {selectedRunDetail.data?.started_at || '-'}</p>
            <label>
              <span>progress/result</span>
              <textarea
                rows={6}
                value={JSON.stringify(selectedRunDetail.data?.progress || selectedRunDetail.data?.result || {}, null, 2)}
                readOnly
              />
            </label>
            <label>
              <span>logs (tail 200)</span>
              <textarea rows={8} value={selectedRunLogs.data?.text || ''} readOnly />
            </label>
          </div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>模板编辑</h2>
          <div className="inline-actions">
            <button onClick={() => queryClient.invalidateQueries({ queryKey: ['workflow-template', projectKey, workflowName] })}>
              <RefreshCw size={14} />刷新
            </button>
          </div>
        </div>

        <div className="form-grid cols-3">
          <label>
            <span>steps(JSON)</span>
            <textarea rows={10} value={stepsText} onChange={(e) => setStepsText(e.target.value)} />
          </label>
          <label>
            <span>board_layout(JSON)</span>
            <textarea rows={10} value={boardLayoutText} onChange={(e) => setBoardLayoutText(e.target.value)} />
          </label>
          <div className="inline-actions">
            <button disabled={!workflowName || saving || deleting} onClick={onSaveTemplate}>
              <Save size={14} />{saving ? '保存中...' : '保存模板'}
            </button>
            <button disabled={!workflowName || deleting || saving} onClick={onDeleteTemplate}>
              <Trash2 size={14} />{deleting ? '删除中...' : '删除模板'}
            </button>
          </div>
        </div>
        {validationText ? <p className="status-line">{validationText}</p> : null}

        <div className="panel-header">
          <h2>模板步骤预览</h2>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>handler</th><th>name</th><th>enabled</th></tr></thead>
            <tbody>
              {editedStepsPreview.map((step, idx) => (
                <tr key={`${String((step as { handler?: unknown }).handler || '')}-${idx}`}>
                  <td>{String((step as { handler?: unknown }).handler || '-')}</td>
                  <td>{String((step as { name?: unknown }).name || '-')}</td>
                  <td>{String((step as { enabled?: unknown }).enabled ?? true)}</td>
                </tr>
              ))}
              {!editedStepsPreview.length && (
                <tr><td colSpan={3} className="empty-cell">暂无模板步骤</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, RefreshCw } from 'lucide-react'
import { getWorkflowTemplate, listWorkflows, runWorkflow } from '../lib/api'

type WorkflowPageProps = {
  projectKey: string
  variant?: 'workflow' | 'graphMarket' | 'graphSocial' | 'graphDeep'
}

export default function WorkflowPage({ projectKey, variant = 'workflow' }: WorkflowPageProps) {
  const queryClient = useQueryClient()
  const [workflowName, setWorkflowName] = useState('')
  const [paramsText, setParamsText] = useState('{}')
  const [statusText, setStatusText] = useState('等待操作')
  const [running, setRunning] = useState(false)

  const workflows = useQuery({ queryKey: ['workflows', projectKey], queryFn: listWorkflows, enabled: Boolean(projectKey) })

  useEffect(() => {
    if (!workflowName && workflows.data?.length) setWorkflowName(workflows.data[0])
  }, [workflowName, workflows.data])

  const workflowTemplate = useQuery({
    queryKey: ['workflow-template', projectKey, workflowName],
    queryFn: () => getWorkflowTemplate(workflowName),
    enabled: Boolean(projectKey) && Boolean(workflowName),
  })

  const onRun = async () => {
    if (!workflowName) return
    setRunning(true)
    setStatusText('运行中...')
    try {
      const params = JSON.parse(paramsText || '{}') as Record<string, unknown>
      const result = await runWorkflow(workflowName, params)
      const taskId = typeof result?.task_id === 'string' ? result.task_id : ''
      setStatusText(taskId ? `已提交，任务 ID: ${taskId}` : '执行完成')
    } catch (error) {
      setStatusText(`执行失败: ${error instanceof Error ? error.message : '未知错误'}`)
    } finally {
      setRunning(false)
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
          <h2>模板步骤</h2>
          <div className="inline-actions">
            <button onClick={() => queryClient.invalidateQueries({ queryKey: ['workflow-template', projectKey, workflowName] })}>
              <RefreshCw size={14} />刷新
            </button>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>handler</th><th>name</th><th>enabled</th></tr></thead>
            <tbody>
              {(workflowTemplate.data?.steps || []).map((step, idx) => (
                <tr key={`${step.handler}-${idx}`}>
                  <td>{step.handler}</td>
                  <td>{step.name || '-'}</td>
                  <td>{String(step.enabled ?? true)}</td>
                </tr>
              ))}
              {!workflowTemplate.data?.steps?.length && (
                <tr><td colSpan={3} className="empty-cell">暂无模板步骤</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}

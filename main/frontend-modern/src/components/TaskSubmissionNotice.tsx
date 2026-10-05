import { AlertTriangle, CheckCircle2, Clock3, ExternalLink, LoaderCircle, RotateCw } from 'lucide-react'
import { translate, useAppLocale } from '../app/platform/i18n'
import { isTerminalTaskStatus, type TaskSubmissionState } from '../hooks/useTaskSubmission'
import './task-submission-notice.css'

export function TaskSubmissionNotice({ submission }: { submission: TaskSubmissionState }) {
  const locale = useAppLocale()
  const { receipt, taskDetail, readbackError, isReading, refresh } = submission
  if (!receipt) return null
  const status = String(taskDetail?.status || 'PENDING').toUpperCase()
  const failed = ['FAILURE', 'FAILED', 'REVOKED', 'CANCELED', 'CANCELLED'].includes(status)
  const terminal = isTerminalTaskStatus(status)
  const running = ['STARTED', 'RUNNING', 'PROGRESS'].includes(status)
  const Icon = readbackError || failed ? AlertTriangle : terminal ? CheckCircle2 : running ? LoaderCircle : Clock3
  const statusKey = readbackError ? 'readbackUnavailable' : failed ? 'failed' : terminal ? 'completed' : running ? 'running' : 'submitted'
  const href = `#/admin/process?task_id=${encodeURIComponent(receipt.taskId)}&source=${encodeURIComponent(receipt.action)}`

  return (
    <section className={`task-submission-notice${failed || readbackError ? ' is-warning' : ''}`} aria-label={translate(locale, 'taskSubmission.receipt')} data-testid="task-submission-notice">
      <Icon size={19} className={running && !readbackError ? 'task-submission-notice__spinner' : undefined} aria-hidden="true" />
      <div className="task-submission-notice__body" role="status" aria-live="polite">
        <strong>{receipt.action}</strong>
        <span>{translate(locale, `taskSubmission.${statusKey}`)}</span>
        <code title={receipt.taskId}>{receipt.taskId}</code>
        {readbackError && <small>{readbackError}</small>}
      </div>
      <a href={href}><ExternalLink size={15} aria-hidden="true" />{translate(locale, 'taskSubmission.openTask')}</a>
      <button type="button" disabled={isReading} onClick={() => void refresh()} title={translate(locale, 'taskSubmission.refresh')} aria-label={translate(locale, 'taskSubmission.refresh')}><RotateCw size={16} aria-hidden="true" /></button>
    </section>
  )
}

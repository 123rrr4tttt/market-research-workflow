import { useQuery } from '@tanstack/react-query'
import { Bot, Radio, RefreshCw, ShieldCheck } from 'lucide-react'
import { getCodexAuthStatus } from '../lib/api/domains/codex-auth'
import { translate, useAppLocale, type AppLocale } from '../app/platform/i18n'
import './codex-agent-page.css'

type CodexAgentPageProps = {
  projectKey: string
}

const LOCAL_HOSTNAMES = new Set(['localhost', '127.0.0.1', '[::1]'])
const HOST_WEBUI_URL = 'http://127.0.0.1:8172/'

function isExplicitLocalHttpOrigin() {
  return window.location.protocol === 'http:' && LOCAL_HOSTNAMES.has(window.location.hostname)
}

function statusCopy(locale: AppLocale, surfaceReady: boolean, statusFailed: boolean) {
  if (statusFailed) {
    return {
      label: translate(locale, 'codexAgentPage.status.error'),
      detail: translate(locale, 'codexAgentPage.status.errorDetail'),
    }
  }
  if (surfaceReady) {
    return {
      label: translate(locale, 'codexAgentPage.status.ready'),
      detail: translate(locale, 'codexAgentPage.status.readyDetail'),
    }
  }
  return {
    label: translate(locale, 'codexAgentPage.status.connecting'),
    detail: translate(locale, 'codexAgentPage.status.connectingDetail'),
  }
}

export default function CodexAgentPage({ projectKey }: CodexAgentPageProps) {
  const locale = useAppLocale()
  const codexAuthQuery = useQuery({
    queryKey: ['codex-agent-auth'],
    queryFn: getCodexAuthStatus,
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
  })
  const browserAuthenticated = Boolean(codexAuthQuery.data?.authenticated)
  const hostConnected = Boolean(codexAuthQuery.data?.token_sink_authenticated)
  const hostDirectAllowed = hostConnected && isExplicitLocalHttpOrigin()
  const codexUiUrl = browserAuthenticated
    ? '/codex/'
    : hostDirectAllowed
      ? HOST_WEBUI_URL
      : null
  const status = statusCopy(locale, codexUiUrl !== null, codexAuthQuery.isError)
  const connectionDetail = hostConnected
    ? translate(locale, 'codexAgentPage.auth.remoteHostDetail')
    : translate(locale, 'codexAgentPage.auth.detail')

  return (
    <div className="codex-agent-page" data-testid="codex-agent-page">
      <header className="codex-agent-page__bar">
        <div className="codex-agent-page__identity">
          <span className="codex-agent-page__mark" aria-hidden="true">
            <Bot size={18} />
          </span>
          <div>
            <small className="codex-agent-page__kicker">{translate(locale, 'codexAgentPage.status.kicker')}</small>
            <strong>{translate(locale, 'codexAgentPage.title')}</strong>
            <span className="codex-agent-page__project">{projectKey}</span>
          </div>
        </div>
        <div className="codex-agent-page__status">
          <span
            className={`codex-agent-page__pill is-${codexUiUrl ? 'ok' : 'wait'}`}
            data-testid="codex-agent-browser-auth"
          >
            {codexUiUrl ? <Radio size={13} /> : <ShieldCheck size={13} />}
            {status.label}
          </span>
          <span className="codex-agent-page__pill is-muted" data-testid="codex-agent-host-auth">
            {translate(
              locale,
              codexAuthQuery.data
                ? hostConnected
                  ? 'codexAgentPage.status.hostAuth'
                  : 'codexAgentPage.status.hostAuthMissing'
                : 'codexAgentPage.status.hostAuthUnknown',
            )}
          </span>
          <span className="codex-agent-page__pill is-muted">
            {translate(locale, 'codexAgentPage.status.snapshot')}
          </span>
          <button
            type="button"
            className="codex-agent-page__refresh"
            onClick={() => void codexAuthQuery.refetch()}
            disabled={codexAuthQuery.isFetching}
            title={translate(locale, 'codexAgentPage.status.refresh')}
            aria-label={translate(locale, 'codexAgentPage.status.refresh')}
          >
            <RefreshCw size={14} className={codexAuthQuery.isFetching ? 'codex-agent-page__spin' : undefined} />
          </button>
          <span className="codex-agent-page__hint" title={status.detail}>
            {status.detail}
          </span>
        </div>
      </header>
      <div
        className="codex-agent-page__stage"
        aria-busy={codexAuthQuery.isFetching}
        aria-label={translate(locale, 'codexAgentPage.status.booting')}
      >
        {codexUiUrl ? (
          <iframe
            className="codex-agent-page__frame"
            data-testid="codex-agent-frame"
            title="Codex Agent"
            src={codexUiUrl}
            allow="clipboard-write"
          />
        ) : (
          <section className="codex-agent-page__auth" data-testid="codex-agent-auth-panel">
            <ShieldCheck size={20} aria-hidden="true" />
            <div>
              <strong>{translate(locale, 'codexAgentPage.auth.title')}</strong>
              <p>
                {codexAuthQuery.isError
                  ? translate(locale, 'codexAgentPage.status.errorDetail')
                  : connectionDetail}
              </p>
            </div>
            {codexAuthQuery.isError ? (
              <button
                type="button"
                data-testid="codex-agent-auth-retry"
                onClick={() => void codexAuthQuery.refetch()}
                disabled={codexAuthQuery.isFetching}
              >
                <RefreshCw size={14} aria-hidden="true" />
                {translate(locale, 'codexAgentPage.auth.retry')}
              </button>
            ) : null}
          </section>
        )}
      </div>
    </div>
  )
}

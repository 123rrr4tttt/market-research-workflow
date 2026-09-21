import { useQuery } from '@tanstack/react-query'
import { Bot, Radio, RefreshCw, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getCodexAuthStatus } from '../lib/api/domains/codex-auth'
import { translate, useAppLocale, type AppLocale } from '../app/platform/i18n'
import './codex-agent-page.css'

type CodexAgentPageProps = {
  projectKey: string
}

function codexUiUrl() {
  // The MRW formal frontend proxies /codex/ to the host codex-web-remote proxy.
  // Keep the default localhost-only path; swap via env when a different origin is used.
  return '/codex/'
}

function statusCopy(locale: AppLocale, codexReady: boolean) {
  if (codexReady) {
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
  // authTried: true once we stop waiting for auto-login (success or timeout), so
  // the boot overlay always clears and the iframe (authed or manual-login) shows.
  const [authTried, setAuthTried] = useState(
    () => typeof window !== 'undefined' && Boolean(window.localStorage.getItem('codex.webui.jwt')),
  )
  const [frameKey, setFrameKey] = useState(0)
  const codexAuthQuery = useQuery({
    queryKey: ['codex-agent-auth'],
    queryFn: getCodexAuthStatus,
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: false,
  })
  const codexReady = Boolean(
    codexAuthQuery.data?.authenticated || codexAuthQuery.data?.token_sink_authenticated,
  )
  const status = statusCopy(locale, codexReady)
  const hostConnected = Boolean(codexAuthQuery.data?.token_sink_authenticated)

  // Auto-login into the embedded Codex WebUI. The codex-webui backend issues a
  // JWT at its own /api/auth/bootstrap (localhost/single-user) so the API key
  // never reaches the browser; we persist it in localStorage (shared with the
  // same-origin iframe) and remount the iframe so it loads already-authenticated.
  useEffect(() => {
    if (authTried) return
    let cancelled = false
    ;(async () => {
      try {
        const timeout = window.setTimeout(() => {
          if (!cancelled) setAuthTried(true)
        }, 5000)
        const res = await fetch('/codex/api/auth/bootstrap')
        if (res.ok) {
          const payload = (await res.json()) as { accessToken?: string }
          if (payload.accessToken) {
            window.localStorage.setItem('codex.webui.jwt', payload.accessToken)
            if (!cancelled) {
              setFrameKey((k) => k + 1)
            }
          }
        }
        window.clearTimeout(timeout)
        if (!cancelled) setAuthTried(true)
      } catch {
        if (!cancelled) setAuthTried(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authTried])

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
          <span className={`codex-agent-page__pill is-${codexReady ? 'ok' : 'wait'}`}>
            {codexReady ? <Radio size={13} /> : <ShieldCheck size={13} />}
            {status.label}
          </span>
          {hostConnected ? (
            <span className="codex-agent-page__pill">
              {translate(locale, 'codexAgentPage.status.hostAuth')}
            </span>
          ) : null}
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
          <a
            className="codex-agent-page__compat-link"
            href="#agent-chat-compat.html"
            data-testid="agent-chat-compat-link"
          >
            Agent Chat compatibility
          </a>
        </div>
      </header>
      <div className="codex-agent-page__stage">
        <iframe
          className="codex-agent-page__frame"
          key={frameKey}
          data-testid="codex-agent-frame"
          title="Codex Agent"
          src={codexUiUrl()}
          allow="clipboard-write"
        />
        {!authTried ? (
          <div className="codex-agent-page__boot" data-testid="codex-agent-boot">
            <span>{translate(locale, 'codexAgentPage.status.booting')}</span>
          </div>
        ) : null}
      </div>
    </div>
  )
}

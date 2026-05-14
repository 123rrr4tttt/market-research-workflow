import { endpoints } from '../endpoints'
import { httpGet, httpPost, resolveApiUrl } from '../client'

export type CodexAuthStatusResponse = {
  codex_oauth_enabled?: boolean
  authenticated?: boolean
  token_sink_authenticated?: boolean
  session?: {
    expires_at?: number
    scope?: string | null
    token_type?: string | null
  } | null
}

export type CodexCliBootstrapResponse = {
  authenticated: boolean
  codex_cli_installed: boolean
  install_attempted?: boolean
  install_succeeded?: boolean
  device_url?: string | null
  device_code?: string | null
  hint?: string | null
}

export async function getCodexAuthStatus() {
  return httpGet<CodexAuthStatusResponse>(endpoints.codexAuth.status)
}

export async function logoutCodexAuth() {
  return httpPost<{ logged_out: boolean }>(endpoints.codexAuth.logout, {})
}

export async function bootstrapCodexCliLogin() {
  return httpPost<CodexCliBootstrapResponse>(endpoints.codexAuth.cliBootstrap, {})
}

export function openCodexAuthLoginPopup(nextUrl?: string, forceOAuth = false) {
  const next = String(nextUrl || `${window.location.origin}${window.location.pathname}${window.location.search}${window.location.hash}`)
  const loginUrl = new URL(resolveApiUrl(endpoints.codexAuth.login), window.location.origin)
  loginUrl.searchParams.set('next_url', next)
  if (forceOAuth) {
    loginUrl.searchParams.set('force_oauth', 'true')
  }
  // Use same-tab redirect for maximum OAuth compatibility across browsers.
  window.location.assign(loginUrl.toString())
  return true
}

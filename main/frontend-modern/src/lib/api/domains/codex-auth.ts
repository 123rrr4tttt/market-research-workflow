import { endpoints } from '../endpoints'
import { httpGet, httpPost } from '../client'

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

export function openCodexAuthLoginPopup(nextUrl?: string) {
  const next = String(nextUrl || window.location.href)
  const joiner = endpoints.codexAuth.login.includes('?') ? '&' : '?'
  const loginUrl = `${endpoints.codexAuth.login}${joiner}next_url=${encodeURIComponent(next)}`
  // Use same-tab redirect for maximum OAuth compatibility across browsers.
  window.location.assign(loginUrl)
  return true
}

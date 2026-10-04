/** Manages the WebUI JWT for REST and WebSocket authentication. */
import { withBasePath } from './base-path';

const STORAGE_KEY = 'codex.webui.jwt';

/**
 * JWT is stored in localStorage (not sessionStorage) so a same-origin parent
 * (the MRW Codex Agent page) and this iframe share the credential. sessionStorage
 * is not reliably shared between a parent page and a same-origin iframe in Chromium.
 */
export function getApiToken(): string | null {
  return localStorage.getItem(STORAGE_KEY);
}

export function setApiToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token);
}

export function clearApiToken(): void {
  localStorage.removeItem(STORAGE_KEY);
}

/** Returns the Authorization header value, or null if no token. */
export function getAuthorizationHeader(): string | null {
  const token = getApiToken();
  return token ? `Bearer ${token}` : null;
}

/**
 * Builds a URL to the `/api/files/serve` endpoint with inline auth token.
 * Suitable for `<img src>`, `<embed src>`, etc. that cannot set Authorization headers.
 */
export function buildFileServeUrl(filePath: string): string {
  const token = getApiToken();
  const params = new URLSearchParams({ path: filePath });
  if (token) params.set('access_token', token);
  return `${withBasePath('/api/files/serve')}?${params.toString()}`;
}

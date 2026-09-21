import { appendFileSync } from 'node:fs'
import { createServer } from 'node:http'

const HOST = '127.0.0.1'
const DEFAULT_PORT = 18379
const rawPort = process.env.CODEX_STUB_PORT || String(DEFAULT_PORT)
const port = Number(rawPort)
if (!Number.isInteger(port) || port < 1 || port > 65_535) {
  throw new Error(`CODEX_STUB_PORT must be an integer from 1 to 65535; received ${JSON.stringify(rawPort)}`)
}

const logPath = process.env.CODEX_STUB_LOG_PATH || ''

function log(event) {
  const line = JSON.stringify({ timestamp: new Date().toISOString(), ...event })
  process.stdout.write(`${line}\n`)
  if (logPath) appendFileSync(logPath, `${line}\n`, { encoding: 'utf8', mode: 0o600 })
}

function requestObservation(request) {
  return {
    method: request.method || '',
    path: new URL(request.url || '/', `http://${HOST}:${port}`).pathname,
    headers: {
      accept: request.headers.accept || null,
      host: request.headers.host || null,
      'user-agent': request.headers['user-agent'] || null,
      'x-forwarded-prefix': request.headers['x-forwarded-prefix'] || null,
    },
    sensitive_headers_redacted: {
      authorization: Boolean(request.headers.authorization),
      cookie: Boolean(request.headers.cookie),
    },
  }
}

function respond(response, status, headers, body = '') {
  response.writeHead(status, {
    'Cache-Control': 'no-store',
    'X-Codex-E2E-Stub': '1',
    ...headers,
  })
  response.end(body)
}

const server = createServer((request, response) => {
  const observation = requestObservation(request)
  const { method, path } = observation
  const head = method === 'HEAD'
  let status = 404

  if ((method === 'GET' || head) && path === '/healthz') {
    status = 204
    respond(response, status, {})
  } else if ((method === 'GET' || head) && path === '/') {
    status = 200
    const body = '<!doctype html><html><head><meta charset="utf-8"><title>Codex E2E Stub</title></head><body><main data-testid="codex-stub-root" data-fixture-boundary="proxy-bootstrap-iframe-only">Synthetic Codex proxy fixture</main></body></html>'
    respond(response, status, { 'Content-Type': 'text/html; charset=utf-8' }, head ? '' : body)
  } else if ((method === 'GET' || head) && path === '/api/auth/bootstrap') {
    status = 200
    const body = JSON.stringify({
      accessToken: 'e2e-codex-stub-noncredential',
      fixture_boundary: 'synthetic_non_user_auth',
    })
    respond(response, status, { 'Content-Type': 'application/json; charset=utf-8' }, head ? '' : body)
  } else if (path.startsWith('/socket.io/')) {
    status = 501
    respond(response, status, { 'Content-Type': 'application/json; charset=utf-8' }, JSON.stringify({
      error: { code: 'WEBSOCKET_NOT_IMPLEMENTED', message: 'Synthetic stub does not implement Codex WebSocket behavior.' },
    }))
  } else if (!['GET', 'HEAD'].includes(method)) {
    status = 405
    respond(response, status, { Allow: 'GET, HEAD', 'Content-Type': 'application/json; charset=utf-8' }, JSON.stringify({
      error: { code: 'METHOD_NOT_ALLOWED', message: 'Synthetic stub is read-only.' },
    }))
  } else {
    respond(response, status, { 'Content-Type': 'application/json; charset=utf-8' }, JSON.stringify({
      error: { code: 'NOT_FOUND', message: 'Synthetic Codex stub route not found.' },
    }))
  }

  request.resume()
  log({ event: 'request', status, ...observation })
})

server.on('upgrade', (request, socket) => {
  const observation = requestObservation(request)
  socket.end([
    'HTTP/1.1 501 Not Implemented',
    'Connection: close',
    'Content-Type: application/json; charset=utf-8',
    'Cache-Control: no-store',
    'X-Codex-E2E-Stub: 1',
    '',
    JSON.stringify({ error: { code: 'WEBSOCKET_NOT_IMPLEMENTED' } }),
  ].join('\r\n'))
  log({ event: 'upgrade_rejected', status: 501, ...observation })
})

server.listen(port, HOST, () => {
  log({
    event: 'ready',
    host: HOST,
    port,
    fixture_boundary: 'proxy_bootstrap_iframe_only',
    does_not_claim: ['native_codex', 'user_auth', 'websocket', 'chat_semantics'],
  })
})

function close(signal) {
  log({ event: 'shutdown_requested', signal })
  server.close(() => {
    log({ event: 'stopped', signal })
    process.exit(0)
  })
}

process.on('SIGINT', () => close('SIGINT'))
process.on('SIGTERM', () => close('SIGTERM'))

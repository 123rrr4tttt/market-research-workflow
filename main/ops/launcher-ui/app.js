const APP_TOTAL = 6

const serviceOrder = [
  'db',
  'es',
  'redis',
  'backend',
  'celery-worker',
  'frontend-modern',
  'searxng',
  'yacy',
]

const serviceMeta = {
  db: { label: 'Database', detail: 'PostgreSQL :5432', optional: false },
  es: { label: 'Elasticsearch', detail: 'Search index :9200', optional: false },
  redis: { label: 'Redis', detail: 'Queue cache :6379', optional: false },
  backend: { label: 'Backend', detail: 'API :8000', optional: false },
  'celery-worker': { label: 'Worker', detail: 'Async jobs', optional: false },
  'frontend-modern': { label: 'Frontend', detail: 'App UI :5174', optional: false },
  searxng: { label: 'SearXNG', detail: 'Metasearch :8088', optional: true },
  yacy: { label: 'YaCy', detail: 'Local corpus :8090', optional: true },
}

const els = {
  state: document.getElementById('state'),
  headline: document.getElementById('headline'),
  runtimeDetail: document.getElementById('runtime-detail'),
  score: document.getElementById('score'),
  appCount: document.getElementById('app-count'),
  controlCount: document.getElementById('control-count'),
  services: document.getElementById('services'),
  control: document.getElementById('control'),
  socket: document.getElementById('socket'),
  ops: document.getElementById('ops'),
  updated: document.getElementById('updated'),
  message: document.getElementById('message'),
  codexPanel: document.getElementById('codex-device-panel'),
  codexCode: document.getElementById('codex-device-code'),
  copyCodexCode: document.getElementById('copy-codex-code'),
  openCodexAuth: document.getElementById('open-codex-auth'),
  codexCliState: document.getElementById('codex-cli-state'),
  codexAuthState: document.getElementById('codex-auth-state'),
  codexCoreState: document.getElementById('codex-core-state'),
  codexUpdated: document.getElementById('codex-updated'),
  start: document.getElementById('start'),
  stop: document.getElementById('stop'),
  restart: document.getElementById('restart'),
  refresh: document.getElementById('refresh'),
  codexAuth: document.getElementById('codex-auth'),
  withSearxng: document.getElementById('with-searxng'),
  withYacy: document.getElementById('with-yacy'),
}

let codexDeviceUrl = ''
let codexDeviceCode = ''

async function copyCodexCode() {
  if (!codexDeviceCode) return
  await navigator.clipboard?.writeText(codexDeviceCode).catch(() => {})
  els.message.textContent = `Device code copied: ${codexDeviceCode}`
}

function showCodexDeviceAuth(data) {
  codexDeviceUrl = data.device_url || ''
  codexDeviceCode = data.device_code || ''
  els.codexCode.textContent = codexDeviceCode || 'No code returned'
  els.codexPanel.hidden = false
  els.message.textContent = codexDeviceCode
    ? `Device code is ready and copied when allowed. Use it on the Codex auth page.`
    : data.hint || 'Codex CLI authentication did not return a device code.'
  copyCodexCode()
}

function openCodexAuthPage() {
  if (!codexDeviceUrl) return
  window.open(codexDeviceUrl, '_blank', 'noopener,noreferrer')
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || payload.output || `request failed: ${response.status}`)
  }
  return payload
}

function selectedProfiles({ includeAllOptional = false } = {}) {
  const profiles = ['modern-ui']
  if (includeAllOptional || els.withSearxng.checked || els.withYacy.checked) {
    profiles.push('search-enhancements')
  }
  return profiles
}

function selectedOptionalServices() {
  const services = []
  if (els.withSearxng.checked) services.push('searxng')
  if (els.withYacy.checked) services.push('yacy')
  return services
}

function setPending(pending) {
  for (const element of [els.start, els.stop, els.restart, els.refresh]) {
    element.disabled = pending
  }
  for (const button of document.querySelectorAll('[data-service-action]')) {
    button.disabled = pending
  }
}

function statusText(service, running) {
  if (running) return 'Stop'
  if (service === 'frontend-modern') return 'Start'
  if (service === 'backend') return 'Start'
  return 'Start'
}

function render(data) {
  const status = data.data || {}
  const runningServices = new Set(status.running_services || [])
  const running = Number(status.running_count || 0)
  const appRunning = serviceOrder.filter((service) => !serviceMeta[service].optional && runningServices.has(service)).length
  const score = Math.round((appRunning / APP_TOTAL) * 100)
  const controlServices = status.control_services || []

  els.score.textContent = String(score)
  els.appCount.textContent = `App ${appRunning}/${APP_TOTAL}`
  els.controlCount.textContent = `Control ${controlServices.length}/2`
  els.state.textContent = running > 0 ? `${running} Docker services online` : 'App stack stopped'
  els.state.className = running > 0 ? 'state running' : 'state'
  els.headline.textContent = appRunning === APP_TOTAL ? 'Docker app stack is running' : 'Docker launcher is ready'
  els.runtimeDetail.textContent =
    appRunning === APP_TOTAL
      ? 'Core app services are online. Optional search services can be started or stopped independently.'
      : 'Start the app stack from here, then open the app UI when the frontend service is online.'

  els.services.innerHTML = serviceOrder
    .map((service) => {
      const meta = serviceMeta[service]
      const runningNow = runningServices.has(service)
      const tone = runningNow ? 'good' : meta.optional ? 'warn' : 'bad'
      return `
        <article class="service-card ${tone}">
          <div class="service-dot"></div>
          <div class="service-copy">
            <strong>${meta.label}</strong>
            <span>${runningNow ? 'Running' : 'Stopped'} / ${meta.detail}</span>
          </div>
          <button data-service-action="${runningNow ? 'stop' : 'start'}" data-service="${service}" type="button">
            ${statusText(service, runningNow)}
          </button>
        </article>
      `
    })
    .join('')

  els.control.textContent = `Control services: ${controlServices.join(', ') || 'not running'}`
  els.socket.textContent = `Docker socket: ${status.docker_socket ? 'mounted' : 'not mounted'}`
  els.ops.textContent = `Ops dir: ${status.ops_dir || '-'}`
  els.updated.textContent = `Updated ${new Date().toLocaleTimeString()}`
  els.stop.disabled = running === 0
}

async function refresh() {
  try {
    const payload = await request('/api/launcher/status')
    render(payload)
    refreshCodexStatus()
  } catch (error) {
    els.message.textContent = error instanceof Error ? error.message : String(error)
  }
}

function renderCodexStatus(payload) {
  const data = payload.data || payload
  const core = data.persistent_core || {}
  const cliReady = Boolean(data.codex_cli_installed)
  const authed = Boolean(data.authenticated || data.token_sink_authenticated)
  els.codexCliState.textContent = `CLI: ${cliReady ? 'ready' : 'missing'}`
  els.codexAuthState.textContent = `Auth: ${authed ? 'authenticated' : data.device_auth_pending ? 'waiting for device auth' : 'not authenticated'}`
  els.codexCoreState.textContent = `Core: ${core.running ? 'running' : 'idle'}`
  els.codexUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`
}

async function refreshCodexStatus() {
  try {
    const payload = await request('/api/launcher/codex/status')
    renderCodexStatus(payload)
  } catch (error) {
    els.codexCliState.textContent = 'CLI: unknown'
    els.codexAuthState.textContent = 'Auth: unknown'
    els.codexCoreState.textContent = 'Core: unknown'
    els.codexUpdated.textContent = error instanceof Error ? error.message : 'Unavailable'
  }
}

async function action(name) {
  setPending(true)
  els.message.textContent = `${name} requested...`
  try {
    const profiles = name === 'stop' ? selectedProfiles({ includeAllOptional: true }) : selectedProfiles()
    await request(`/api/launcher/${name}`, {
      method: 'POST',
      body: JSON.stringify({ profiles, optional_services: selectedOptionalServices() }),
    })
    els.message.textContent = `${name} accepted`
    window.setTimeout(refresh, 1200)
    window.setTimeout(refresh, 5000)
  } catch (error) {
    els.message.textContent = error instanceof Error ? error.message : String(error)
  } finally {
    window.setTimeout(() => setPending(false), 800)
  }
}

async function serviceAction(service, actionName) {
  setPending(true)
  els.message.textContent = `${actionName} ${service} requested...`
  try {
    await request('/api/launcher/service', {
      method: 'POST',
      body: JSON.stringify({ service, action: actionName }),
    })
    els.message.textContent = `${actionName} ${service} accepted`
    window.setTimeout(refresh, 1000)
    window.setTimeout(refresh, 3500)
  } catch (error) {
    els.message.textContent = error instanceof Error ? error.message : String(error)
  } finally {
    window.setTimeout(() => setPending(false), 800)
  }
}

async function startCodexAuth() {
  els.message.textContent = 'Starting Codex CLI authentication...'
  try {
    const payload = await request('/api/launcher/codex/cli/bootstrap', {
      method: 'POST',
      body: JSON.stringify({}),
    })
    const data = payload.data || payload
    if (data.authenticated) {
      els.message.textContent = 'Codex is already authenticated.'
      return
    }
    if (data.device_url) {
      showCodexDeviceAuth(data)
      refreshCodexStatus()
      return
    }
    els.message.textContent = data.hint || 'Codex CLI authentication did not return a device URL.'
  } catch (error) {
    els.message.textContent = error instanceof Error ? error.message : String(error)
  }
}

els.start.addEventListener('click', () => action('start'))
els.stop.addEventListener('click', () => action('stop'))
els.restart.addEventListener('click', () => action('restart'))
els.refresh.addEventListener('click', refresh)
els.codexAuth.addEventListener('click', startCodexAuth)
els.copyCodexCode.addEventListener('click', copyCodexCode)
els.openCodexAuth.addEventListener('click', openCodexAuthPage)
els.services.addEventListener('click', (event) => {
  const target = event.target
  if (!(target instanceof HTMLElement)) return
  const button = target.closest('[data-service-action]')
  if (!(button instanceof HTMLElement)) return
  const service = button.dataset.service
  const actionName = button.dataset.serviceAction
  if (service && actionName) serviceAction(service, actionName)
})

refresh()
window.setInterval(refresh, 5000)

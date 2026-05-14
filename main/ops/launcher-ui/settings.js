const SETTINGS = [
  { group: 'llm', key: 'LLM_PROVIDER', label: 'LLM Provider', placeholder: 'openai / azure / ollama' },
  { group: 'llm', key: 'OPENAI_API_KEY', label: 'OpenAI API Key', secret: true },
  { group: 'llm', key: 'OPENAI_API_BASE', label: 'OpenAI API Base', placeholder: 'https://api.openai.com/v1' },
  { group: 'llm', key: 'AZURE_API_KEY', label: 'Azure API Key', secret: true },
  { group: 'llm', key: 'AZURE_API_BASE', label: 'Azure API Base' },
  { group: 'llm', key: 'AZURE_API_VERSION', label: 'Azure API Version' },
  { group: 'llm', key: 'AZURE_CHAT_DEPLOYMENT', label: 'Azure Chat Deployment' },
  { group: 'llm', key: 'OLLAMA_BASE_URL', label: 'Ollama Base URL', placeholder: 'http://host.docker.internal:11434' },
  { group: 'search', key: 'SERPER_API_KEY', label: 'Serper API Key', secret: true },
  { group: 'search', key: 'SERPAPI_KEY', label: 'SerpApi Key', secret: true },
  { group: 'search', key: 'SERPSTACK_KEY', label: 'Serpstack Key', secret: true },
  { group: 'search', key: 'GOOGLE_SEARCH_API_KEY', label: 'Google Search API Key', secret: true },
  { group: 'search', key: 'GOOGLE_SEARCH_CSE_ID', label: 'Google CSE ID' },
  { group: 'search', key: 'LEGISCAN_API_KEY', label: 'LegiScan API Key', secret: true },
  { group: 'search', key: 'TWITTER_BEARER_TOKEN', label: 'Twitter/X Bearer Token', secret: true },
  { group: 'search', key: 'SEARXNG_BASE_URL', label: 'SearXNG Base URL', placeholder: 'http://searxng:8080' },
  { group: 'search', key: 'YACY_BASE_URL', label: 'YaCy Base URL', placeholder: 'http://yacy:8090' },
  { group: 'search', key: 'YACY_RESOURCE_MODE', label: 'YaCy Resource Mode', placeholder: 'local / global' },
  { group: 'runtime', key: 'DATABASE_URL', label: 'Database URL' },
  { group: 'runtime', key: 'ES_URL', label: 'Elasticsearch URL', placeholder: 'http://es:9200' },
  { group: 'runtime', key: 'REDIS_URL', label: 'Redis URL', placeholder: 'redis://redis:6379/0' },
  { group: 'runtime', key: 'EXTRACTION_MAX_PARALLEL', label: 'Extraction Parallelism' },
  { group: 'runtime', key: 'TOPIC_WORKFLOW_MAX_PARALLEL', label: 'Topic Workflow Parallelism' },
]

const els = {
  state: document.getElementById('settings-state'),
  backendState: document.getElementById('backend-state'),
  count: document.getElementById('settings-count'),
  message: document.getElementById('settings-message'),
  codexPanel: document.getElementById('codex-device-panel'),
  codexCode: document.getElementById('codex-device-code'),
  copyCodexCode: document.getElementById('copy-codex-code'),
  openCodexAuth: document.getElementById('open-codex-auth'),
  codexCliState: document.getElementById('codex-cli-state'),
  codexAuthState: document.getElementById('codex-auth-state'),
  codexCoreState: document.getElementById('codex-core-state'),
  codexUpdated: document.getElementById('codex-updated'),
  save: document.getElementById('save-settings'),
  reload: document.getElementById('reload-settings'),
  refresh: document.getElementById('refresh-settings'),
  codexAuth: document.getElementById('codex-auth'),
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

function envelopeData(payload) {
  if (payload && payload.status === 'ok') return payload.data || {}
  return payload || {}
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok || payload.status === 'error' || payload.ok === false) {
    const message = payload?.error?.message || payload?.error || `request failed: ${response.status}`
    throw new Error(message)
  }
  return payload
}

function renderFields(values = {}) {
  for (const group of ['llm', 'search', 'runtime']) {
    const target = document.querySelector(`[data-group="${group}"]`)
    target.innerHTML = SETTINGS.filter((item) => item.group === group)
      .map((item) => {
        const value = values[item.key] || ''
        const masked = item.secret && value && value.includes('*')
        return `
          <label class="setting-field">
            <span>${item.label}</span>
            <input
              name="${item.key}"
              type="${item.secret ? 'password' : 'text'}"
              value="${escapeHtml(value)}"
              placeholder="${escapeHtml(item.placeholder || item.key)}"
              data-secret="${item.secret ? 'true' : 'false'}"
              data-masked="${masked ? 'true' : 'false'}"
            />
            <small>${item.key}</small>
          </label>
        `
      })
      .join('')
  }
  els.count.textContent = `${SETTINGS.length} fields`
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
}

function collectPayload() {
  const payload = {}
  for (const input of document.querySelectorAll('.setting-field input')) {
    const value = input.value.trim()
    if (!value) continue
    if (input.dataset.secret === 'true' && input.dataset.masked === 'true' && value.includes('*')) continue
    payload[input.name] = value
  }
  return payload
}

async function loadSettings() {
  els.message.textContent = ''
  els.state.textContent = 'Loading settings...'
  els.state.className = 'state'
  refreshCodexStatus()
  try {
    const payload = await api('/api/launcher/config/env')
    renderFields(envelopeData(payload))
    els.state.textContent = 'Backend config loaded'
    els.state.className = 'state running'
    els.backendState.textContent = 'Backend online'
  } catch (error) {
    renderFields({})
    els.state.textContent = 'Backend config unavailable'
    els.backendState.textContent = 'Backend offline'
    els.message.textContent = error instanceof Error ? error.message : String(error)
  }
}

function renderCodexStatus(payload) {
  const data = envelopeData(payload)
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
    const payload = await api('/api/launcher/codex/status')
    renderCodexStatus(payload)
  } catch (error) {
    els.codexCliState.textContent = 'CLI: unknown'
    els.codexAuthState.textContent = 'Auth: unknown'
    els.codexCoreState.textContent = 'Core: unknown'
    els.codexUpdated.textContent = error instanceof Error ? error.message : 'Unavailable'
  }
}

async function saveSettings() {
  const payload = collectPayload()
  if (Object.keys(payload).length === 0) {
    els.message.textContent = 'No changed or non-empty settings to save.'
    return
  }
  els.save.disabled = true
  els.message.textContent = 'Saving settings...'
  try {
    const result = await api('/api/launcher/config/env', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    const updated = envelopeData(result).updated || []
    els.message.textContent = `Saved ${updated.length || Object.keys(payload).length} setting(s).`
    await loadSettings()
  } catch (error) {
    els.message.textContent = error instanceof Error ? error.message : String(error)
  } finally {
    els.save.disabled = false
  }
}

async function reloadSettings() {
  els.reload.disabled = true
  els.message.textContent = 'Reloading backend settings...'
  try {
    await api('/api/launcher/config/reload', { method: 'POST', body: JSON.stringify({}) })
    els.message.textContent = 'Backend settings reloaded.'
    await loadSettings()
  } catch (error) {
    els.message.textContent = error instanceof Error ? error.message : String(error)
  } finally {
    els.reload.disabled = false
  }
}

async function startCodexAuth() {
  els.message.textContent = 'Starting Codex CLI authentication...'
  try {
    const result = await api('/api/launcher/codex/cli/bootstrap', {
      method: 'POST',
      body: JSON.stringify({}),
    })
    const data = envelopeData(result)
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

els.refresh.addEventListener('click', loadSettings)
els.save.addEventListener('click', saveSettings)
els.reload.addEventListener('click', reloadSettings)
els.codexAuth.addEventListener('click', startCodexAuth)
els.copyCodexCode.addEventListener('click', copyCodexCode)
els.openCodexAuth.addEventListener('click', openCodexAuthPage)

renderFields({})
loadSettings()

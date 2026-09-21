import type { APIRequestContext } from '@playwright/test'

export const SKIP_BACKEND_CHECK = 'FRONTEND_E2E_SKIP_BACKEND_CHECK'
export const RUNTIME_MODE_ENV = 'FRONTEND_E2E_RUNTIME_MODE'
const DEFAULT_READINESS_PATHS = ['/api/v1/health/deep', '/api/v1/health']
const REPO_ROOT = '/Users/wangyiliang/market-research-workflow'
const LOCAL_BACKEND_COMMAND = `cd ${REPO_ROOT} && ./scripts/local-deploy.sh start && ./scripts/local-deploy.sh health`
const DOCKER_BACKEND_COMMAND = `cd ${REPO_ROOT} && ./scripts/docker-deploy.sh preflight && ./scripts/docker-deploy.sh start --profile modern-ui && ./scripts/docker-deploy.sh health`

export type FrontendE2ERuntimeMode = 'local' | 'docker'

export type BackendFailureClassification =
  | 'blocked_by_environment'
  | 'data_setup_missing'
  | 'functional_failure'

type ReadinessAttempt = {
  path: string
  ok: boolean
  status?: number
  body?: string
  error?: string
}

export type RealBackendReadinessResult = {
  skipped: boolean
  reason?: string
  classification?: BackendFailureClassification
  runtimeMode: FrontendE2ERuntimeMode
  path?: string
  status?: number
  checkedEndpoints?: string[]
  recommendedCommand?: string
}

export async function requireRealBackendReadiness(request: APIRequestContext): Promise<RealBackendReadinessResult> {
  const runtimeMode = resolveRuntimeMode()
  const recommendedCommand = recommendedBackendCommand(runtimeMode)
  if (process.env[SKIP_BACKEND_CHECK] === '1') {
    return {
      skipped: true,
      reason: `${SKIP_BACKEND_CHECK}=1`,
      classification: 'blocked_by_environment',
      runtimeMode,
      checkedEndpoints: [],
      recommendedCommand,
    }
  }

  const attempts: ReadinessAttempt[] = []
  for (const path of DEFAULT_READINESS_PATHS) {
    try {
      const response = await request.get(path, { timeout: 5000 })
      const body = await response.text()
      const attempt: ReadinessAttempt = {
        path,
        ok: response.ok(),
        status: response.status(),
        body: truncate(body),
      }
      attempts.push(attempt)
      if (attempt.ok) {
        return {
          skipped: false,
          path,
          status: attempt.status,
          runtimeMode,
          classification: undefined,
          checkedEndpoints: attempts.map((item) => item.path),
          recommendedCommand,
        }
      }
    } catch (error) {
      attempts.push({
        path,
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  }

  throw new Error(buildReadinessError(attempts, runtimeMode))
}

export function buildClassifiedBackendFailure({
  title,
  classification,
  runtimeMode = resolveRuntimeMode(),
  checkedEndpoints,
  details,
  recommendedCommand = recommendedBackendCommand(runtimeMode),
}: {
  title: string
  classification: BackendFailureClassification
  runtimeMode?: FrontendE2ERuntimeMode
  checkedEndpoints: string[]
  details: string[]
  recommendedCommand?: string
}) {
  const payload = {
    classification,
    runtime_mode: runtimeMode,
    checked_endpoints: checkedEndpoints,
    recommended_command: recommendedCommand,
  }

  return [
    title,
    `classification: ${classification}`,
    `blocked_classification=${classification}`,
    `runtime_mode: ${runtimeMode}`,
    `checked_endpoints: ${checkedEndpoints.join(', ') || '(none)'}`,
    `recommended_command: ${recommendedCommand}`,
    `machine_readable: ${JSON.stringify(payload)}`,
    '',
    ...details,
  ].join('\n')
}

function buildReadinessError(attempts: ReadinessAttempt[], runtimeMode: FrontendE2ERuntimeMode) {
  const details = attempts.map((attempt) => {
    const status = attempt.status ? `status=${attempt.status}` : 'no status'
    const reason = attempt.error || attempt.body || 'empty response'
    return `- ${attempt.path}: ${status}; ${reason}`
  })

  return buildClassifiedBackendFailure({
    title: 'Frontend real-backend e2e readiness check failed.',
    classification: 'blocked_by_environment',
    runtimeMode,
    checkedEndpoints: attempts.map((attempt) => attempt.path),
    details: [
      'The frontend dev server is reachable, but no backend health endpoint passed before running a real-backend smoke test.',
      '',
      'Checked endpoints:',
      ...details,
      '',
      'Start the backend first, or set VITE_API_PROXY_TARGET to the running backend before Playwright starts.',
      `For fully mocked frontend e2e flows only, set ${SKIP_BACKEND_CHECK}=1 to bypass this readiness check.`,
    ],
  })
}

function resolveRuntimeMode(): FrontendE2ERuntimeMode {
  return process.env[RUNTIME_MODE_ENV] === 'docker' ? 'docker' : 'local'
}

function recommendedBackendCommand(runtimeMode: FrontendE2ERuntimeMode) {
  return runtimeMode === 'docker' ? DOCKER_BACKEND_COMMAND : LOCAL_BACKEND_COMMAND
}

function truncate(value: string) {
  return value.length > 500 ? `${value.slice(0, 500)}...` : value
}

import type { HealthResponse } from './types'

export function collectRuntimeMissingDependencies(runtimeStatus: HealthResponse | undefined) {
  const explicit = runtimeStatus?.missing_dependencies || []
  const serviceMissing = Object.values(runtimeStatus?.services || {}).flatMap((service) => service.missing_dependencies || [])
  return Array.from(new Set([...explicit, ...serviceMissing].filter(Boolean))).sort()
}

export function runtimeHealthTarget(service: NonNullable<HealthResponse['services']>[string] | undefined) {
  const healthUrl = String(service?.health_url || '').trim()
  const portHint = service?.port_hint == null ? '' : String(service.port_hint)
  return [healthUrl, portHint ? `:${portHint}` : ''].filter(Boolean).join(' ')
}

function probeStatusFromRuntime(status: string | undefined, hasTarget: boolean) {
  const key = String(status || '').toLowerCase()
  if (['ok', 'ready', 'healthy', 'running', 'available', 'passed'].some((token) => key.includes(token))) return 'passed'
  if (['fail', 'error', 'missing', 'down', 'unhealthy', 'unavailable'].some((token) => key.includes(token))) return 'failed'
  return hasTarget ? 'unknown' : 'skipped'
}

function firstRuntimePort(runtimeStatus: HealthResponse | undefined) {
  const servicePort = Object.values(runtimeStatus?.services || {}).find((service) => service.port_hint != null)?.port_hint
  const portHint = servicePort ?? Object.values(runtimeStatus?.port_hints || {})[0]
  return portHint == null ? null : portHint
}

export function buildRuntimeDiagnosticPackage(projectKey: string, runtimeStatus: HealthResponse | undefined) {
  const runtimeMode = runtimeStatus?.runtime_mode || 'unknown'
  const missingDependencies = collectRuntimeMissingDependencies(runtimeStatus)
  const services = Object.entries(runtimeStatus?.services || {}).map(([name, service]) => ({
    name,
    status: service.status || 'unknown',
    mode: service.mode || 'unknown',
    provider: service.provider || null,
    host: service.host || null,
    health_url: service.health_url || null,
    port_hint: service.port_hint || null,
    missing_dependencies: service.missing_dependencies || [],
    service_ping: {
      status: probeStatusFromRuntime(service.status, Boolean(service.health_url || service.host || service.port_hint)),
      health_url: service.health_url || null,
      host: service.host || null,
      port: service.port_hint || null,
    },
    service_ready: {
      status: probeStatusFromRuntime(service.status, Boolean(service.health_url || service.host || service.port_hint)),
      source: 'runtime_health_response',
    },
  }))
  const mixedRuntime = runtimeMode === 'mixed'
  const servicePingFailures = services.filter((service) => service.service_ping.status === 'failed')
  const serviceReadyFailures = services.filter((service) => service.service_ready.status === 'failed')
  const riskLevel = missingDependencies.length || mixedRuntime || serviceReadyFailures.length ? 'blocked' : 'ready'
  const recommendedCommand = './scripts/docker-deploy.sh preflight'
  const failFastReasons = [
    ...(mixedRuntime ? ['mixed runtime mode'] : []),
    ...missingDependencies.map((name) => `missing dependency: ${name}`),
    ...serviceReadyFailures.map((service) => `service not ready: ${service.name}`),
  ]
  return {
    schema_version: 'ops.runtime_diagnostic_package.v1',
    generated_at: new Date().toISOString(),
    project_key: projectKey,
    runtime_mode: runtimeMode,
    status: runtimeStatus?.status || 'unknown',
    provider: runtimeStatus?.provider || null,
    env: runtimeStatus?.env || null,
    readiness: {
      risk_level: riskLevel,
      can_seal_runtime_evidence: riskLevel === 'ready',
      mixed_runtime: mixedRuntime,
      missing_dependencies_count: missingDependencies.length,
      service_count: services.length,
    },
    service_ping: {
      status: servicePingFailures.length ? 'failed' : services.length ? 'passed' : 'skipped',
      failed_services: servicePingFailures.map((service) => service.name),
      services: services.map((service) => ({ name: service.name, ...service.service_ping })),
    },
    service_ready: {
      status: serviceReadyFailures.length ? 'failed' : services.length ? 'passed' : 'skipped',
      failed_services: serviceReadyFailures.map((service) => service.name),
      services: services.map((service) => ({ name: service.name, ...service.service_ready })),
    },
    port: {
      status: firstRuntimePort(runtimeStatus) == null ? 'not_configured' : 'configured',
      value: firstRuntimePort(runtimeStatus),
      port_hints: runtimeStatus?.port_hints || {},
    },
    secret: {
      status: 'not_checked',
      required: false,
      missing: [],
      checks: [],
    },
    dependency: {
      status: missingDependencies.length ? 'failed' : 'passed',
      missing: missingDependencies,
      checks: services.map((service) => ({
        name: service.name,
        status: service.missing_dependencies.length ? 'failed' : 'passed',
        missing: service.missing_dependencies,
      })),
    },
    fail_fast_decision: {
      should_fail: Boolean(failFastReasons.length),
      status: failFastReasons.length ? 'fail_fast' : 'continue',
      exit_code: failFastReasons.length ? 1 : 0,
      reasons: failFastReasons,
      recommended_command: recommendedCommand,
    },
    missing_dependencies: missingDependencies,
    health_readback: {
      health_url: runtimeStatus?.health_url || null,
      port_hints: runtimeStatus?.port_hints || {},
      services,
    },
    user_action_required: [
      ...(mixedRuntime ? ['Align backend and dependencies to one runtime mode before sealing evidence.'] : []),
      ...missingDependencies.map((name) => `Install or start missing dependency: ${name}`),
    ],
    recommended_commands: [
      recommendedCommand,
      'curl -fsS http://localhost:8000/health || curl -fsS http://localhost:8000/api/v1/health',
    ],
  }
}

import { createHash } from 'node:crypto'
import {
  chmodSync,
  closeSync,
  createWriteStream,
  existsSync,
  lstatSync,
  mkdirSync,
  openSync,
  readdirSync,
  readFileSync,
  realpathSync,
  readSync,
  readlinkSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs'
import { createServer } from 'node:net'
import { dirname, isAbsolute, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn, spawnSync } from 'node:child_process'

const FORBIDDEN_PREDECESSOR_IMAGE_SHA256 = 'e40af59580fc6a9dd5ade567618a133027a4b9ab8a8cebc5dc76e779ad766dac'
const FORBIDDEN_PREDECESSOR_NETWORK = 'mrw-stageconv-20260907-ytn-net'
const FORBIDDEN_PREDECESSOR_SECURITY_OWNER = 'v6_intake_v4_impl'
const EXPECTED_PNPM_BIN = '/root/.cache/node/corepack/v1/pnpm/11.22.0/bin/pnpm.mjs'
const EXPECTED_PNPM_STORE_DIR = '/root/.local/share/pnpm/store/v11'
const IMAGE_FRONTEND_ROOT = '/opt/mrw/frontend'
const SOURCE_ROOT = '/code'
const WORK_ROOT = '/work'
const ARTIFACTS_ROOT = '/artifacts'
const FRONTEND_PORT = 15179
const STORYBOOK_PORT = 16007
const BACKEND_PORT = 18139
const CODEX_STUB_PORT = 18379
const EXPECTED_MAIN_PLAYWRIGHT_TESTS = 112
const SECURITY_ADMISSION_SCHEMA = 'frontend-external-security-admission.v1'
const SECURITY_ADMISSION_STATUS = 'ADMITTED_NOT_AUTHORITY'
const NEGATIVE_PROBE_SCHEMA = 'frontend-network-internal-negative-probe-receipt.v1'
const NEGATIVE_PROBE_STATUS = 'PASS_NOT_AUTHORITY'
const NON_AUTHORITY = 'NOT_AUTHORITY'
const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const STUB_PATH = join(SCRIPT_DIR, 'codex-stub18379.mjs')

const EXPECTED_GATE_IDS = [
  'pnpm_frozen_offline_install',
  'frontend_lint',
  'frontend_typecheck',
  'frontend_named_static_checks',
  'frontend_build',
  'storybook_static_build',
  'storybook_interactions_all_stories',
  'backend_and_stub_readiness',
  'frontend_e2e_complete_no_maxfail',
]

const EXPECTED_STATIC_GATE_IDS = [
  'image_frozen_dependency_projection',
  ...EXPECTED_GATE_IDS.slice(1, 7),
]

const NAMED_STATIC_CHECK_SCRIPTS = [
  'check:graph-force3d-frontend-contract',
  'check:codex-agent-page-i18n-slice',
  'check:projects-i18n-slice',
  'check:settings-page-i18n-slice',
  'check:catalog-page-i18n-slice',
  'check:dashboard-page-i18n-slice',
  'check:process-page-i18n-slice',
  'check:graph-page-i18n-slice',
  'check:crawler-manage-i18n-slice',
  'check:llm-designer-page-i18n-slice',
  'check:ops-page-i18n-slice',
  'check:resource-page-i18n-slice',
  'check:i18n-page-shell-disjoint',
  'check:business-string-audit',
  'check:layer-shell-contract',
  'check:topology-platform',
  'check:writing-workbench-contract',
  'check:writing-workbench-typed-fetch',
  'check:writing-workbench-persisted-typed-card-readback',
]

const LOADED_ENV_FILE_NAMES = new Set([
  '.env',
  '.env.local',
  '.env.development',
  '.env.development.local',
  '.env.production',
  '.env.production.local',
  '.env.test',
  '.env.test.local',
])

const EXPECTED_STATIC_SKIPS = []

const FORBIDDEN_AMBIENT_SECRETS = [
  'OPENAI_API_KEY',
  'AZURE_API_KEY',
  'LITELLM_API_KEY',
  'SERPAPI_KEY',
  'SERPER_API_KEY',
  'GOOGLE_SEARCH_API_KEY',
  'NEWS_API_KEY',
  'CODEX_AUTH_TOKENS',
  'CODEX_OAUTH_CLIENT_SECRET',
  'CODEX_OAUTH_ID_TOKEN_SHARED_KEY',
]

function requiredEnv(name) {
  const value = String(process.env[name] || '').trim()
  if (!value) throw new Error(`MISSING_REQUIRED_ENV:${name}`)
  return value
}

function sha256Bytes(value) {
  return createHash('sha256').update(value).digest('hex')
}

function sha256File(path) {
  const hash = createHash('sha256')
  const fd = openSync(path, 'r')
  try {
    const buffer = Buffer.allocUnsafe(1024 * 1024)
    let bytesRead = 0
    do {
      bytesRead = readSync(fd, buffer, 0, buffer.length, null)
      if (bytesRead > 0) hash.update(buffer.subarray(0, bytesRead))
    } while (bytesRead > 0)
  } finally {
    closeSync(fd)
  }
  return hash.digest('hex')
}

function sha256Path(path) {
  const stat = lstatSync(path)
  if (stat.isSymbolicLink()) return sha256Bytes(Buffer.from(readlinkSync(path), 'utf8'))
  if (!stat.isFile()) throw new Error(`CANDIDATE_ENTRY_NOT_FILE_OR_SYMLINK:${path}`)
  return sha256File(path)
}

function runCapture(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    env: options.env,
    encoding: null,
    maxBuffer: 256 * 1024 * 1024,
  })
  if (result.status !== 0) {
    const stderr = Buffer.from(result.stderr || '').toString('utf8').slice(0, 2000)
    throw new Error(`COMMAND_FAILED:${command}:${result.status}:${stderr}`)
  }
  return Buffer.from(result.stdout || '')
}

function gitPaths(root, args) {
  const output = runCapture('git', ['-C', root, ...args])
  return output
    .toString('utf8')
    .split('\0')
    .filter(Boolean)
    .sort()
}

function gitIndexEntries(root) {
  const output = runCapture('git', ['-C', root, 'ls-files', '--stage', '-z']).toString('utf8')
  const entries = new Map()
  for (const record of output.split('\0').filter(Boolean)) {
    const match = /^([0-7]{6}) ([0-9a-f]+) ([0-3])\t([\s\S]+)$/.exec(record)
    if (!match) throw new Error('GIT_INDEX_RECORD_MALFORMED')
    const [, mode, objectId, stage, path] = match
    if (stage !== '0') throw new Error(`GIT_INDEX_UNMERGED_ENTRY:${path}:stage=${stage}`)
    if (entries.has(path)) throw new Error(`GIT_INDEX_DUPLICATE_PATH:${path}`)
    entries.set(path, { mode, object_id: objectId })
  }
  return entries
}

function safeCandidatePath(root, path) {
  if (!path || path.startsWith('/') || path.split('/').includes('..')) {
    throw new Error(`UNSAFE_CANDIDATE_PATH:${path}`)
  }
  const absolute = resolve(root, path)
  const prefix = `${resolve(root)}/`
  if (!absolute.startsWith(prefix)) throw new Error(`CANDIDATE_PATH_ESCAPES_ROOT:${path}`)
  return absolute
}

function candidateSnapshot(root) {
  const trackedEntries = gitIndexEntries(root)
  const tracked = [...trackedEntries.keys()].sort()
  const untracked = gitPaths(root, ['ls-files', '--others', '--exclude-standard', '-z'])
  const trackedSet = new Set(tracked)
  const paths = [...tracked, ...untracked.filter((path) => !trackedSet.has(path))].sort()
  const trackedHash = createHash('sha256')
  const surfaceHash = createHash('sha256')
  const entries = []

  for (const path of paths) {
    const absolute = safeCandidatePath(root, path)
    const stat = lstatSync(absolute)
    const scope = trackedSet.has(path) ? 'tracked' : 'untracked_nonignored'
    const indexEntry = trackedEntries.get(path)
    let kind
    let mode
    let sha256
    let git_object_id
    if (indexEntry?.mode === '160000') {
      if (!stat.isDirectory()) throw new Error(`GITLINK_NOT_DIRECTORY:${path}`)
      const materialized = readdirSync(absolute).length !== 0
      if (materialized) {
        const gitlinkHead = runCapture('git', ['-C', absolute, 'rev-parse', 'HEAD']).toString('utf8').trim()
        assertEqual(gitlinkHead, indexEntry.object_id, `GITLINK_HEAD_MISMATCH:${path}`)
        const gitlinkStatus = runCapture(
          'git',
          ['-C', absolute, 'status', '--porcelain=v1', '-z', '--untracked-files=all'],
        )
        if (gitlinkStatus.length !== 0) throw new Error(`GITLINK_WORKTREE_NOT_CLEAN:${path}`)
      }
      kind = materialized ? 'gitlink_materialized_clean' : 'gitlink_unmaterialized'
      mode = indexEntry.mode
      git_object_id = indexEntry.object_id
      sha256 = sha256Bytes(`${kind}:${indexEntry.object_id}`)
    } else {
      kind = stat.isSymbolicLink() ? 'symlink' : stat.isFile() ? 'file' : 'unsupported'
      if (kind === 'unsupported') throw new Error(`CANDIDATE_ENTRY_UNSUPPORTED:${path}`)
      mode = indexEntry?.mode || (stat.mode & 0o7777).toString(8).padStart(4, '0')
      sha256 = sha256Path(absolute)
    }
    const line = `${path}\0${kind}\0${mode}\0${sha256}\0`
    surfaceHash.update(line)
    if (scope === 'tracked') trackedHash.update(line)
    entries.push({ path, scope, kind, mode, sha256, ...(git_object_id ? { git_object_id } : {}) })
  }

  return {
    root,
    git_head: runCapture('git', ['-C', root, 'rev-parse', 'HEAD']).toString('utf8').trim(),
    git_tree: runCapture('git', ['-C', root, 'rev-parse', 'HEAD^{tree}']).toString('utf8').trim(),
    tracked_count: tracked.length,
    untracked_nonignored_count: untracked.length,
    tracked_root_sha256: trackedHash.digest('hex'),
    candidate_surface_root_sha256: surfaceHash.digest('hex'),
    entries,
  }
}

function writeJsonCreateOnly(path, value) {
  const fd = openSync(path, 'wx', 0o600)
  try {
    writeFileSync(fd, `${JSON.stringify(value, null, 2)}\n`, 'utf8')
  } finally {
    closeSync(fd)
  }
}

function writeBytesCreateOnly(path, value) {
  const fd = openSync(path, 'wx', 0o600)
  try {
    writeFileSync(fd, value)
  } finally {
    closeSync(fd)
  }
}

function readJsonWithHash(path, expectedSha256) {
  if (!isAbsolute(path)) throw new Error(`ADMISSION_PATH_NOT_ABSOLUTE:${path}`)
  if (realpathSync(path) !== resolve(path)) throw new Error(`ADMISSION_PATH_CONTAINS_SYMLINK:${path}`)
  const stat = lstatSync(path)
  if (stat.isSymbolicLink()) throw new Error(`ADMISSION_PATH_IS_SYMLINK:${path}`)
  if (!stat.isFile()) throw new Error(`ADMISSION_PATH_NOT_REGULAR_FILE:${path}`)
  if (!/^[0-9a-f]{64}$/.test(expectedSha256)) {
    throw new Error(`ADMISSION_EXPECTED_SHA256_INVALID:${path}:${expectedSha256}`)
  }
  const bytes = readFileSync(path)
  const actual = sha256Bytes(bytes)
  if (actual !== expectedSha256) throw new Error(`ADMISSION_HASH_MISMATCH:${path}:${actual}:${expectedSha256}`)
  const value = JSON.parse(bytes.toString('utf8'))
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`ADMISSION_JSON_ROOT_NOT_OBJECT:${path}`)
  }
  return value
}

function copyHashBoundInput(artifactRoot, destinationName, sourcePath, expectedSha256) {
  if (realpathSync(sourcePath) !== resolve(sourcePath)) {
    throw new Error(`INPUT_EVIDENCE_SOURCE_CONTAINS_SYMLINK:${sourcePath}`)
  }
  const sourceStat = lstatSync(sourcePath)
  if (sourceStat.isSymbolicLink()) throw new Error(`INPUT_EVIDENCE_SOURCE_IS_SYMLINK:${sourcePath}`)
  if (!sourceStat.isFile()) throw new Error(`INPUT_EVIDENCE_SOURCE_NOT_FILE:${sourcePath}`)
  const bytes = readFileSync(sourcePath)
  const actualSha256 = sha256Bytes(bytes)
  assertEqual(actualSha256, expectedSha256, `INPUT_EVIDENCE_SOURCE_HASH_MISMATCH:${sourcePath}`)
  const destinationPath = join(artifactRoot, 'admission-inputs', destinationName)
  writeBytesCreateOnly(destinationPath, bytes)
  const descriptor = artifactFileDescriptor(artifactRoot, destinationPath)
  assertEqual(descriptor.sha256, expectedSha256, `INPUT_EVIDENCE_COPY_HASH_MISMATCH:${destinationName}`)
  return { source_path: sourcePath, ...descriptor }
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label}:expected=${expected}:actual=${actual}`)
}

function assertExactKeys(value, expectedKeys, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label}_NOT_OBJECT`)
  }
  const actual = Object.keys(value).sort()
  const expected = [...expectedKeys].sort()
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${label}_KEYS_MISMATCH:expected=${expected.join(',')}:actual=${actual.join(',')}`)
  }
}

function assertAbsolutePathEqual(actual, expected, label) {
  if (typeof actual !== 'string' || !isAbsolute(actual)) throw new Error(`${label}_NOT_ABSOLUTE:${actual}`)
  if (typeof expected !== 'string' || !isAbsolute(expected)) throw new Error(`${label}_EXPECTED_NOT_ABSOLUTE:${expected}`)
  assertEqual(resolve(actual), resolve(expected), label)
}

function assertNonAuthority(value, label) {
  assertEqual(value.authority, NON_AUTHORITY, `${label}_AUTHORITY_MISMATCH`)
  assertEqual(value.production_release_authorized, false, `${label}_PRODUCTION_AUTHORITY_MISMATCH`)
}

function serviceTargetFingerprint(raw, allowedProtocols, label) {
  let url
  try {
    url = new URL(raw)
  } catch {
    throw new Error(`${label}_INVALID_URL`)
  }
  if (!allowedProtocols.includes(url.protocol)) {
    throw new Error(`${label}_PROTOCOL_NOT_ALLOWED:${url.protocol}`)
  }
  url.username = ''
  url.password = ''
  url.hash = ''
  return sha256Bytes(url.toString())
}

function assertNoEnvFallback(root) {
  if (!existsSync(root)) throw new Error(`ENV_SCAN_ROOT_MISSING:${root}`)
  for (const name of readdirSync(root)) {
    if (LOADED_ENV_FILE_NAMES.has(name)) {
      throw new Error(`ENV_FILE_FALLBACK_PRESENT:${join(root, name)}`)
    }
  }
}

function assertSourceReadOnly(runId) {
  const probe = join(SOURCE_ROOT, `.mrw-frontend-write-probe-${runId}`)
  let fd
  try {
    fd = openSync(probe, 'wx', 0o600)
  } catch (error) {
    if (error && ['EROFS', 'EACCES', 'EPERM'].includes(error.code)) return
    throw error
  }
  closeSync(fd)
  unlinkSync(probe)
  throw new Error('SOURCE_MOUNT_IS_WRITABLE:/code')
}

async function assertPortsFree(ports) {
  for (const port of ports) {
    await new Promise((resolvePromise, rejectPromise) => {
      const server = createServer()
      server.once('error', (error) => rejectPromise(new Error(`PORT_NOT_FREE:${port}:${error.message}`)))
      server.listen(port, '127.0.0.1', () => server.close(resolvePromise))
    })
  }
}

function makeChildEnv(workRunRoot, explicit) {
  const env = {}
  for (const key of ['PATH', 'LANG', 'LC_ALL', 'TZ', 'SSL_CERT_FILE', 'LD_LIBRARY_PATH']) {
    if (process.env[key]) env[key] = process.env[key]
  }
  return {
    ...env,
    CI: '1',
    NO_COLOR: '1',
    XDG_CACHE_HOME: join(workRunRoot, 'xdg-cache'),
    XDG_CONFIG_HOME: join(workRunRoot, 'xdg-config'),
    XDG_DATA_HOME: join(workRunRoot, 'xdg-data'),
    TMPDIR: join(workRunRoot, 'tmp'),
    npm_config_cache: join(workRunRoot, 'npm-cache'),
    npm_config_offline: 'true',
    COREPACK_DEFAULT_TO_LATEST: '0',
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: '1',
    ...explicit,
  }
}

function createNarrowPnpmWebServerAdapter(workRunRoot, frontendRoot) {
  const toolBin = join(workRunRoot, 'tool-bin')
  mkdirSync(toolBin, { recursive: false, mode: 0o700 })
  const adapterPath = join(toolBin, 'pnpm')
  const storybookBin = join(frontendRoot, 'node_modules/.bin/storybook')
  const viteBin = join(frontendRoot, 'node_modules/.bin/vite')
  const routes = {
    storybook: { bin: storybookBin, prefix: ['dev', '-p', '6006', '--host', '0.0.0.0'] },
    dev: { bin: viteBin, prefix: [] },
  }
  const source = `#!/opt/node-v22.23.2-linux-x64/bin/node
const { spawnSync } = require('node:child_process')
const [route, ...rawArgs] = process.argv.slice(2)
const routes = ${JSON.stringify(routes)}
if (!Object.prototype.hasOwnProperty.call(routes, route)) {
  process.stderr.write(\`NARROW_PNPM_ROUTE_REJECTED:\${String(route || 'missing')}\\n\`)
  process.exit(64)
}
const forwarded = route === 'dev' && rawArgs[0] === '--' ? rawArgs.slice(1) : rawArgs
const args = [...routes[route].prefix, ...forwarded]
const result = spawnSync(routes[route].bin, args, { env: process.env, stdio: 'inherit' })
if (result.error) {
  process.stderr.write(\`NARROW_PNPM_ROUTE_SPAWN_ERROR:\${result.error.message}\\n\`)
  process.exit(70)
}
if (result.signal) {
  process.stderr.write(\`NARROW_PNPM_ROUTE_SIGNAL:\${result.signal}\\n\`)
  process.exit(71)
}
process.exit(result.status ?? 72)
`
  const fd = openSync(adapterPath, 'wx', 0o700)
  try {
    writeFileSync(fd, source, 'utf8')
  } finally {
    closeSync(fd)
  }
  chmodSync(adapterPath, 0o700)
  return { toolBin, adapterPath, routes, sha256: sha256File(adapterPath) }
}

function runLogged(command, args, { cwd, env, logPath }) {
  return new Promise((resolvePromise) => {
    const log = createWriteStream(logPath, { flags: 'wx', mode: 0o600 })
    const startedAt = new Date().toISOString()
    const child = spawn(command, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] })
    child.stdout.pipe(log, { end: false })
    child.stderr.pipe(log, { end: false })
    child.once('error', (error) => {
      log.write(`\nRUNNER_SPAWN_ERROR:${error.message}\n`)
    })
    child.once('close', (code, signal) => {
      log.end(() => resolvePromise({
        command,
        args,
        cwd,
        started_at: startedAt,
        ended_at: new Date().toISOString(),
        exit_code: code,
        signal,
        log_path: logPath,
      }))
    })
  })
}

function startLoggedService(command, args, { cwd, env, logPath, name }) {
  const log = createWriteStream(logPath, { flags: 'wx', mode: 0o600 })
  const logClosed = new Promise((resolvePromise) => log.once('close', resolvePromise))
  const child = spawn(command, args, { cwd, env, stdio: ['ignore', 'pipe', 'pipe'] })
  child.stdout.pipe(log, { end: false })
  child.stderr.pipe(log, { end: false })
  const state = {
    name,
    child,
    log,
    log_path: logPath,
    pid: child.pid,
    started_at: new Date().toISOString(),
    exit: null,
    log_closed: logClosed,
  }
  child.once('error', (error) => {
    log.write(`\nRUNNER_SERVICE_SPAWN_ERROR:${error.message}\n`)
  })
  child.once('close', (code, signal) => {
    state.exit = { code, signal, at: new Date().toISOString() }
    log.end()
  })
  return state
}

async function stopService(service) {
  if (!service) return
  if (service.exit) {
    await service.log_closed
    return
  }
  const waitForClose = async (timeoutMs) => {
    if (service.exit) return true
    await Promise.race([
      new Promise((resolvePromise) => service.child.once('close', resolvePromise)),
      new Promise((resolvePromise) => setTimeout(resolvePromise, timeoutMs)),
    ])
    return Boolean(service.exit)
  }
  service.child.kill('SIGINT')
  if (await waitForClose(10_000)) {
    await service.log_closed
    return
  }
  service.child.kill('SIGTERM')
  if (await waitForClose(10_000)) {
    await service.log_closed
    return
  }
  service.child.kill('SIGKILL')
  if (await waitForClose(5_000)) {
    await service.log_closed
    return
  }
  throw new Error(`SERVICE_DID_NOT_EXIT:${service.name}:${service.pid}`)
}

async function waitForHttp(url, service, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs
  let last = 'not attempted'
  while (Date.now() < deadline) {
    if (service?.exit) throw new Error(`SERVICE_EXITED_BEFORE_READY:${service.name}:${JSON.stringify(service.exit)}`)
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(3_000) })
      const body = await response.text()
      if (response.ok) return { url, status: response.status, body_sha256: sha256Bytes(body) }
      last = `HTTP ${response.status}`
    } catch (error) {
      last = error instanceof Error ? error.message : String(error)
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 500))
  }
  throw new Error(`SERVICE_READINESS_TIMEOUT:${url}:${last}`)
}

function gitStatus(root) {
  return runCapture('git', ['-C', root, 'status', '--porcelain=v1', '-z', '--untracked-files=all']).toString('utf8')
}

function statusDifference(before, after) {
  const beforeRecords = new Set(before.split('\0').filter(Boolean))
  const afterRecords = new Set(after.split('\0').filter(Boolean))
  return {
    added_or_changed_records: [...afterRecords].filter((item) => !beforeRecords.has(item)).sort(),
    removed_or_resolved_records: [...beforeRecords].filter((item) => !afterRecords.has(item)).sort(),
  }
}

function collectPlaywrightTests(report) {
  const tests = []
  function walkSuite(suite, parents = []) {
    const nextParents = suite.title ? [...parents, suite.title] : parents
    for (const spec of suite.specs || []) {
      for (const test of spec.tests || []) {
        const resultStatuses = (test.results || []).map((item) => item.status)
        const skipped = test.status === 'skipped' || (resultStatuses.length > 0 && resultStatuses.every((status) => status === 'skipped'))
        tests.push({
          title: spec.title,
          full_title: [...nextParents, spec.title].filter(Boolean).join(' > '),
          project_name: test.projectName || null,
          status: test.status || null,
          result_statuses: resultStatuses,
          skipped,
        })
      }
    }
    for (const child of suite.suites || []) walkSuite(child, nextParents)
  }
  for (const suite of report.suites || []) walkSuite(suite)
  return tests
}

function validateStaticSkips(reportPath) {
  if (!existsSync(reportPath)) {
    return { valid: false, error: 'PLAYWRIGHT_JSON_REPORT_MISSING', report_path: reportPath }
  }
  const report = JSON.parse(readFileSync(reportPath, 'utf8'))
  const tests = collectPlaywrightTests(report)
  const skippedTitles = tests.filter((item) => item.skipped).map((item) => item.title).sort()
  const totalTestsMatch = tests.length === EXPECTED_MAIN_PLAYWRIGHT_TESTS
  const skippedTitlesMatch = JSON.stringify(skippedTitles) === JSON.stringify(EXPECTED_STATIC_SKIPS)
  return {
    valid: totalTestsMatch && skippedTitlesMatch,
    total_tests: tests.length,
    expected_total_tests: EXPECTED_MAIN_PLAYWRIGHT_TESTS,
    total_tests_match: totalTestsMatch,
    skipped_count: skippedTitles.length,
    skipped_titles: skippedTitles,
    expected_skipped_titles: EXPECTED_STATIC_SKIPS,
    skipped_titles_match: skippedTitlesMatch,
  }
}

function validateAdmission(identity, lifecycle, env, expectedImageSha256, expectedSecurityOwner) {
  assertEqual(identity.schema_version, 'frontend-preview-identity.v1', 'PREVIEW_IDENTITY_SCHEMA_MISMATCH')
  assertEqual(identity.commit, env.MRW_PREVIEW_COMMIT, 'PREVIEW_COMMIT_RECEIPT_MISMATCH')
  assertEqual(identity.tree, env.MRW_PREVIEW_TREE, 'PREVIEW_TREE_RECEIPT_MISMATCH')
  assertEqual(lifecycle.schema_version, 'frontend-backend-lifecycle-admission.v1', 'LIFECYCLE_SCHEMA_MISMATCH')
  assertEqual(lifecycle.image_sha256, expectedImageSha256, 'LIFECYCLE_IMAGE_MISMATCH')
  assertEqual(lifecycle.preview_tracked_root_sha256, identity.tracked_root_sha256, 'LIFECYCLE_PREVIEW_MISMATCH')
  assertEqual(lifecycle.database_target_sha256, env.MRW_DATABASE_TARGET_SHA256, 'LIFECYCLE_DATABASE_TARGET_MISMATCH')
  assertEqual(lifecycle.allow_test_backend_start, true, 'BACKEND_START_NOT_AUTHORIZED')
  assertEqual(lifecycle.startup_effect_policy, 'NO_UNSCOPED_CONFIG_SYNC', 'BACKEND_STARTUP_EFFECT_POLICY_MISMATCH')
  assertEqual(lifecycle.security_owner, expectedSecurityOwner, 'SECURITY_OWNER_MISMATCH')
}

function validateExternalSecurityAdmission(admission, context) {
  assertExactKeys(admission, [
    'schema_version',
    'status',
    'authority',
    'production_release_authorized',
    'run_id',
    'source_commit',
    'source_tree',
    'preview_identity_path',
    'preview_identity_sha256',
    'backend_lifecycle_admission_path',
    'backend_lifecycle_admission_sha256',
    'image_sha256',
    'network',
    'security_owner',
    'negative_probe_receipt',
  ], 'EXTERNAL_SECURITY_ADMISSION')
  assertEqual(admission.schema_version, SECURITY_ADMISSION_SCHEMA, 'EXTERNAL_SECURITY_ADMISSION_SCHEMA_MISMATCH')
  assertEqual(admission.status, SECURITY_ADMISSION_STATUS, 'EXTERNAL_SECURITY_ADMISSION_STATUS_MISMATCH')
  assertNonAuthority(admission, 'EXTERNAL_SECURITY_ADMISSION')
  assertEqual(admission.run_id, context.runId, 'EXTERNAL_SECURITY_ADMISSION_RUN_ID_MISMATCH')
  assertEqual(admission.source_commit, context.previewCommit, 'EXTERNAL_SECURITY_ADMISSION_COMMIT_MISMATCH')
  assertEqual(admission.source_tree, context.previewTree, 'EXTERNAL_SECURITY_ADMISSION_TREE_MISMATCH')
  assertAbsolutePathEqual(
    admission.preview_identity_path,
    context.previewIdentityPath,
    'EXTERNAL_SECURITY_ADMISSION_PREVIEW_IDENTITY_PATH_MISMATCH',
  )
  assertEqual(
    admission.preview_identity_sha256,
    context.previewIdentitySha256,
    'EXTERNAL_SECURITY_ADMISSION_PREVIEW_IDENTITY_HASH_MISMATCH',
  )
  assertAbsolutePathEqual(
    admission.backend_lifecycle_admission_path,
    context.lifecyclePath,
    'EXTERNAL_SECURITY_ADMISSION_LIFECYCLE_PATH_MISMATCH',
  )
  assertEqual(
    admission.backend_lifecycle_admission_sha256,
    context.lifecycleSha256,
    'EXTERNAL_SECURITY_ADMISSION_LIFECYCLE_HASH_MISMATCH',
  )
  assertEqual(admission.image_sha256, context.expectedImageSha256, 'EXTERNAL_SECURITY_ADMISSION_IMAGE_MISMATCH')
  assertExactKeys(admission.network, ['name', 'id', 'internal'], 'EXTERNAL_SECURITY_ADMISSION_NETWORK')
  assertEqual(admission.network.name, context.networkName, 'EXTERNAL_SECURITY_ADMISSION_NETWORK_NAME_MISMATCH')
  assertEqual(admission.network.id, context.networkId, 'EXTERNAL_SECURITY_ADMISSION_NETWORK_ID_MISMATCH')
  assertEqual(admission.network.internal, true, 'EXTERNAL_SECURITY_ADMISSION_NETWORK_NOT_INTERNAL')
  assertEqual(admission.security_owner, context.expectedSecurityOwner, 'EXTERNAL_SECURITY_ADMISSION_OWNER_MISMATCH')
  assertExactKeys(admission.negative_probe_receipt, ['path', 'sha256'], 'NEGATIVE_PROBE_REFERENCE')

  const negativeProbe = readJsonWithHash(
    admission.negative_probe_receipt.path,
    admission.negative_probe_receipt.sha256,
  )
  assertExactKeys(negativeProbe, [
    'schema_version',
    'status',
    'authority',
    'production_release_authorized',
    'run_id',
    'network_name',
    'network_id',
    'network_internal',
  ], 'NEGATIVE_PROBE_RECEIPT')
  assertEqual(negativeProbe.schema_version, NEGATIVE_PROBE_SCHEMA, 'NEGATIVE_PROBE_SCHEMA_MISMATCH')
  assertEqual(negativeProbe.status, NEGATIVE_PROBE_STATUS, 'NEGATIVE_PROBE_STATUS_MISMATCH')
  assertNonAuthority(negativeProbe, 'NEGATIVE_PROBE_RECEIPT')
  assertEqual(negativeProbe.run_id, context.runId, 'NEGATIVE_PROBE_RUN_ID_MISMATCH')
  assertEqual(negativeProbe.network_name, context.networkName, 'NEGATIVE_PROBE_NETWORK_NAME_MISMATCH')
  assertEqual(negativeProbe.network_id, context.networkId, 'NEGATIVE_PROBE_NETWORK_ID_MISMATCH')
  assertEqual(negativeProbe.network_internal, true, 'NEGATIVE_PROBE_NETWORK_NOT_INTERNAL')
  return {
    admission,
    negativeProbe: {
      path: admission.negative_probe_receipt.path,
      sha256: admission.negative_probe_receipt.sha256,
      receipt: negativeProbe,
    },
  }
}

function assertWithinArtifactRoot(artifactRoot, path, label) {
  const root = resolve(artifactRoot)
  const absolute = resolve(path)
  const rel = relative(root, absolute)
  if (!rel || rel === '..' || rel.startsWith('../') || isAbsolute(rel)) {
    throw new Error(`${label}_OUTSIDE_ARTIFACT_ROOT:${path}`)
  }
  return { absolute, relative: rel }
}

function artifactFileDescriptor(artifactRoot, path) {
  const bounded = assertWithinArtifactRoot(artifactRoot, path, 'EVIDENCE_PATH')
  if (realpathSync(bounded.absolute) !== bounded.absolute) {
    throw new Error(`EVIDENCE_PATH_CONTAINS_SYMLINK:${bounded.relative}`)
  }
  const stat = lstatSync(bounded.absolute)
  if (stat.isSymbolicLink()) throw new Error(`EVIDENCE_PATH_IS_SYMLINK:${bounded.relative}`)
  if (!stat.isFile()) throw new Error(`EVIDENCE_PATH_NOT_REGULAR_FILE:${bounded.relative}`)
  return {
    path: bounded.relative,
    bytes: stat.size,
    sha256: sha256File(bounded.absolute),
  }
}

function collectArtifactFiles(artifactRoot, path) {
  const bounded = assertWithinArtifactRoot(artifactRoot, path, 'EVIDENCE_PATH')
  const stat = lstatSync(bounded.absolute)
  if (stat.isSymbolicLink()) throw new Error(`EVIDENCE_PATH_IS_SYMLINK:${bounded.relative}`)
  if (stat.isFile()) return [artifactFileDescriptor(artifactRoot, bounded.absolute)]
  if (!stat.isDirectory()) throw new Error(`EVIDENCE_PATH_UNSUPPORTED_TYPE:${bounded.relative}`)
  const files = []
  for (const name of readdirSync(bounded.absolute).sort()) {
    files.push(...collectArtifactFiles(artifactRoot, join(bounded.absolute, name)))
  }
  return files
}

function collectLogPaths(value, paths = new Set()) {
  if (!value || typeof value !== 'object') return paths
  if (Array.isArray(value)) {
    for (const item of value) collectLogPaths(item, paths)
    return paths
  }
  for (const [key, item] of Object.entries(value)) {
    if (key === 'log_path' && typeof item === 'string') paths.add(item)
    else collectLogPaths(item, paths)
  }
  return paths
}

function gateRequiredEvidencePaths(gate, artifactRoot, services) {
  const paths = collectLogPaths(gate)
  if (gate.id === 'frontend_build' && gate.exit_code === 0) {
    paths.add(join(artifactRoot, 'frontend-dist'))
  }
  if (gate.id === 'storybook_static_build' && gate.exit_code === 0) {
    paths.add(join(artifactRoot, 'storybook-static'))
  }
  if (gate.id === 'storybook_interactions_all_stories') {
    paths.add(join(artifactRoot, 'storybook-playwright.json'))
    paths.add(join(artifactRoot, 'storybook-playwright.xml'))
    const results = join(artifactRoot, 'storybook-test-results')
    if (existsSync(results)) paths.add(results)
  }
  if (gate.id === 'frontend_e2e_complete_no_maxfail') {
    paths.add(join(artifactRoot, 'frontend-e2e.json'))
    paths.add(join(artifactRoot, 'frontend-e2e.xml'))
    const results = join(artifactRoot, 'frontend-e2e-test-results')
    if (existsSync(results)) paths.add(results)
  }
  if (gate.id === 'backend_and_stub_readiness') {
    for (const service of services) paths.add(service.log_path)
  }
  return [...paths].sort()
}

function copyBuildOutputEvidence(sourcePath, destinationPath, label) {
  if (!existsSync(sourcePath)) throw new Error(`${label}_OUTPUT_MISSING:${sourcePath}`)
  const sourceStat = lstatSync(sourcePath)
  if (!sourceStat.isDirectory()) throw new Error(`${label}_OUTPUT_NOT_DIRECTORY:${sourcePath}`)
  const copy = spawnSync('cp', ['-a', sourcePath, destinationPath], { encoding: 'utf8' })
  if (copy.status !== 0) {
    throw new Error(`${label}_OUTPUT_COPY_FAILED:${copy.status}:${String(copy.stderr || '').slice(0, 2000)}`)
  }
}

function materializeGateReceipts(artifactRoot, runId, gates, services) {
  const assertionRoot = join(artifactRoot, 'gate-assertions')
  const receiptRoot = join(artifactRoot, 'gate-receipts')
  mkdirSync(assertionRoot, { recursive: false, mode: 0o700 })
  mkdirSync(receiptRoot, { recursive: false, mode: 0o700 })
  for (const gate of gates) {
    const assertionPath = join(assertionRoot, `${gate.id}.json`)
    writeJsonCreateOnly(assertionPath, {
      schema_version: 'frontend-gate-assertion.v1',
      authority: NON_AUTHORITY,
      production_release_authorized: false,
      run_id: runId,
      gate,
    })
    const evidence = [artifactFileDescriptor(artifactRoot, assertionPath)]
    for (const path of gateRequiredEvidencePaths(gate, artifactRoot, services)) {
      if (!existsSync(path)) throw new Error(`GATE_REQUIRED_EVIDENCE_MISSING:${gate.id}:${path}`)
      evidence.push(...collectArtifactFiles(artifactRoot, path))
    }
    const uniqueEvidence = [...new Map(evidence.map((item) => [item.path, item])).values()]
      .sort((left, right) => left.path.localeCompare(right.path))
    const gateReceiptPath = join(receiptRoot, `${gate.id}.json`)
    writeJsonCreateOnly(gateReceiptPath, {
      schema_version: 'frontend-gate-receipt.v1',
      authority: NON_AUTHORITY,
      production_release_authorized: false,
      run_id: runId,
      gate_id: gate.id,
      exit_code: gate.exit_code,
      evidence_artifacts: uniqueEvidence,
    })
    gate.evidence_artifacts = uniqueEvidence
    gate.receipt_artifact = artifactFileDescriptor(artifactRoot, gateReceiptPath)
  }
}

function writeArtifactManifest(artifactRoot, runId, executionPhase) {
  const manifestPath = join(artifactRoot, 'artifact-manifest.v1.json')
  const excluded = new Set([
    relative(resolve(artifactRoot), manifestPath),
    'frontend-full-suite-result.v1.json',
    'frontend-full-suite-result.v1.sha256.json',
  ])
  const entries = readdirSync(artifactRoot)
    .sort()
    .flatMap((name) => collectArtifactFiles(artifactRoot, join(artifactRoot, name)))
    .filter((entry) => !excluded.has(entry.path))
    .sort((left, right) => left.path.localeCompare(right.path))
  if (entries.length === 0) throw new Error('ARTIFACT_MANIFEST_EMPTY')
  const duplicate = entries.find((entry, index) => index > 0 && entry.path === entries[index - 1].path)
  if (duplicate) throw new Error(`ARTIFACT_MANIFEST_DUPLICATE_PATH:${duplicate.path}`)
  writeJsonCreateOnly(manifestPath, {
    schema_version: 'frontend-artifact-manifest.v1',
    status: 'CONTENT_ADDRESSED_NOT_AUTHORITY',
    authority: NON_AUTHORITY,
    production_release_authorized: false,
    run_id: runId,
    execution_phase: executionPhase,
    artifact_root: resolve(artifactRoot),
    entry_count: entries.length,
    entries,
  })
  return {
    path: manifestPath,
    sha256: sha256File(manifestPath),
    entry_count: entries.length,
  }
}

function validateArtifactManifest(artifactRoot, expected) {
  const manifest = readJsonWithHash(expected.path, expected.sha256)
  assertExactKeys(manifest, [
    'schema_version',
    'status',
    'authority',
    'production_release_authorized',
    'run_id',
    'execution_phase',
    'artifact_root',
    'entry_count',
    'entries',
  ], 'ARTIFACT_MANIFEST')
  assertEqual(manifest.schema_version, 'frontend-artifact-manifest.v1', 'ARTIFACT_MANIFEST_SCHEMA_MISMATCH')
  assertEqual(manifest.status, 'CONTENT_ADDRESSED_NOT_AUTHORITY', 'ARTIFACT_MANIFEST_STATUS_MISMATCH')
  assertNonAuthority(manifest, 'ARTIFACT_MANIFEST')
  assertEqual(manifest.run_id, expected.runId, 'ARTIFACT_MANIFEST_RUN_ID_MISMATCH')
  assertEqual(manifest.execution_phase, expected.executionPhase, 'ARTIFACT_MANIFEST_PHASE_MISMATCH')
  assertAbsolutePathEqual(manifest.artifact_root, artifactRoot, 'ARTIFACT_MANIFEST_ROOT_MISMATCH')
  if (!Array.isArray(manifest.entries)) throw new Error('ARTIFACT_MANIFEST_ENTRIES_NOT_ARRAY')
  assertEqual(manifest.entry_count, manifest.entries.length, 'ARTIFACT_MANIFEST_ENTRY_COUNT_MISMATCH')
  assertEqual(manifest.entry_count, expected.entry_count, 'ARTIFACT_MANIFEST_EXPECTED_COUNT_MISMATCH')
  const seen = new Set()
  const entryByPath = new Map()
  for (const entry of manifest.entries) {
    assertExactKeys(entry, ['path', 'bytes', 'sha256'], 'ARTIFACT_MANIFEST_ENTRY')
    if (seen.has(entry.path)) throw new Error(`ARTIFACT_MANIFEST_DUPLICATE_PATH:${entry.path}`)
    seen.add(entry.path)
    const actual = artifactFileDescriptor(artifactRoot, join(artifactRoot, entry.path))
    assertEqual(actual.path, entry.path, `ARTIFACT_MANIFEST_PATH_MISMATCH:${entry.path}`)
    assertEqual(actual.bytes, entry.bytes, `ARTIFACT_MANIFEST_BYTES_MISMATCH:${entry.path}`)
    assertEqual(actual.sha256, entry.sha256, `ARTIFACT_MANIFEST_HASH_MISMATCH:${entry.path}`)
    entryByPath.set(entry.path, entry)
  }
  for (const gate of expected.gates) {
    if (!gate.receipt_artifact) throw new Error(`GATE_RECEIPT_ARTIFACT_MISSING:${gate.id}`)
    const receiptEntry = entryByPath.get(gate.receipt_artifact.path)
    if (!receiptEntry) throw new Error(`GATE_RECEIPT_NOT_IN_MANIFEST:${gate.id}`)
    assertEqual(receiptEntry.sha256, gate.receipt_artifact.sha256, `GATE_RECEIPT_HASH_NOT_CLOSED:${gate.id}`)
    if (!Array.isArray(gate.evidence_artifacts) || gate.evidence_artifacts.length === 0) {
      throw new Error(`GATE_EVIDENCE_ARTIFACTS_EMPTY:${gate.id}`)
    }
    for (const evidence of gate.evidence_artifacts) {
      const evidenceEntry = entryByPath.get(evidence.path)
      if (!evidenceEntry) throw new Error(`GATE_EVIDENCE_NOT_IN_MANIFEST:${gate.id}:${evidence.path}`)
      assertEqual(evidenceEntry.sha256, evidence.sha256, `GATE_EVIDENCE_HASH_NOT_CLOSED:${gate.id}:${evidence.path}`)
    }
  }
  return true
}

function assertImplementationInvariants() {
  for (const ids of [EXPECTED_GATE_IDS, EXPECTED_STATIC_GATE_IDS]) {
    assertEqual(new Set(ids).size, ids.length, 'DUPLICATE_EXPECTED_GATE_ID')
  }
  assertEqual(EXPECTED_STATIC_SKIPS.length, 0, 'STATIC_SKIP_ALLOWLIST_MUST_REMAIN_EMPTY')
  assertEqual(SECURITY_ADMISSION_STATUS.includes('NOT_AUTHORITY'), true, 'SECURITY_STATUS_MUST_BE_NON_AUTHORITY')
  assertEqual(NEGATIVE_PROBE_STATUS.includes('NOT_AUTHORITY'), true, 'NEGATIVE_PROBE_STATUS_MUST_BE_NON_AUTHORITY')
}

async function main() {
  assertImplementationInvariants()
  const executionPhase = requiredEnv('MRW_EXECUTION_PHASE')
  if (!['static-only', 'full'].includes(executionPhase)) {
    throw new Error(`INVALID_EXECUTION_PHASE:${executionPhase}`)
  }
  const fullExecution = executionPhase === 'full'
  const runId = requiredEnv('MRW_RUN_ID')
  if (!/^[a-zA-Z0-9._-]{8,96}$/.test(runId)) throw new Error(`INVALID_RUN_ID:${runId}`)
  const expectedImageSha256 = requiredEnv('MRW_IMAGE_ID_SHA256')
  if (!/^[0-9a-f]{64}$/.test(expectedImageSha256)) throw new Error('IMAGE_ID_SHA256_INVALID')
  if (expectedImageSha256 === FORBIDDEN_PREDECESSOR_IMAGE_SHA256) {
    throw new Error('PREDECESSOR_IMAGE_REUSE_FORBIDDEN')
  }
  if (String(process.env.MRW_NETWORK_INTERNAL_NEGATIVE_PROBE || '').trim()) {
    throw new Error('CALLER_ASSERTED_NETWORK_PROBE_FORBIDDEN:MRW_NETWORK_INTERNAL_NEGATIVE_PROBE')
  }
  const networkName = requiredEnv('MRW_NETWORK_NAME')
  const networkId = fullExecution ? requiredEnv('MRW_NETWORK_ID') : null
  if (fullExecution) {
    if (networkName === 'none' || networkName === FORBIDDEN_PREDECESSOR_NETWORK) {
      throw new Error('FRESH_INTERNAL_NETWORK_REQUIRED')
    }
    if (!/^[a-zA-Z0-9][a-zA-Z0-9._:-]{7,127}$/.test(networkId)) {
      throw new Error(`INVALID_NETWORK_ID:${networkId}`)
    }
  } else {
    assertEqual(networkName, 'none', 'NETWORK_NAME_MISMATCH')
  }
  const expectedSecurityOwner = fullExecution ? requiredEnv('MRW_SECURITY_OWNER') : null
  if (expectedSecurityOwner === FORBIDDEN_PREDECESSOR_SECURITY_OWNER) {
    throw new Error('PREDECESSOR_SECURITY_OWNER_REUSE_FORBIDDEN')
  }

  const previewCommit = requiredEnv('MRW_PREVIEW_COMMIT')
  const previewTree = requiredEnv('MRW_PREVIEW_TREE')
  const pnpmBin = requiredEnv('MRW_PNPM_BIN')
  const playwrightBrowsersPath = requiredEnv('PLAYWRIGHT_BROWSERS_PATH')
  assertEqual(pnpmBin, EXPECTED_PNPM_BIN, 'PNPM_DIRECT_EXECUTABLE_MISMATCH')
  const pnpmStoreDir = fullExecution ? requiredEnv('MRW_PNPM_STORE_DIR') : null
  if (fullExecution) assertEqual(pnpmStoreDir, EXPECTED_PNPM_STORE_DIR, 'PNPM_STORE_MISMATCH')
  for (const name of FORBIDDEN_AMBIENT_SECRETS) {
    if (String(process.env[name] || '').trim()) throw new Error(`FORBIDDEN_AMBIENT_SECRET_PRESENT:${name}`)
  }
  if (String(process.env.FRONTEND_E2E_SKIP_BACKEND_CHECK || '').trim()) {
    throw new Error('FORBIDDEN_BACKEND_SKIP_ENV_PRESENT:FRONTEND_E2E_SKIP_BACKEND_CHECK')
  }
  let identity = null
  let previewIdentityPath = null
  let previewIdentitySha256 = null
  let lifecyclePath = null
  let lifecycleSha256 = null
  let databaseTargetSha256 = null
  let databaseUrl = null
  let redisUrl = null
  let esUrl = null
  let projectKey = null
  let dbLeaseId = null
  let pythonBin = null
  let redisTargetSha256 = null
  let esTargetSha256 = null
  let candidateManifestPath = null
  let candidateManifestSha256 = null
  let securityAdmissionPath = null
  let securityAdmissionSha256 = null
  let validatedSecurityAdmission = null
  if (fullExecution) {
    assertEqual(requiredEnv('MRW_DB_SEQUENCE_AUTHORITY'), 'security-owner', 'DB_SEQUENCE_AUTHORITY_MISMATCH')
    previewIdentityPath = requiredEnv('MRW_PREVIEW_IDENTITY_PATH')
    previewIdentitySha256 = requiredEnv('MRW_PREVIEW_IDENTITY_SHA256')
    lifecyclePath = requiredEnv('MRW_BACKEND_LIFECYCLE_ADMISSION_PATH')
    lifecycleSha256 = requiredEnv('MRW_BACKEND_LIFECYCLE_ADMISSION_SHA256')
    securityAdmissionPath = requiredEnv('MRW_EXTERNAL_SECURITY_ADMISSION_PATH')
    securityAdmissionSha256 = requiredEnv('MRW_EXTERNAL_SECURITY_ADMISSION_SHA256')
    databaseTargetSha256 = requiredEnv('MRW_DATABASE_TARGET_SHA256')
    databaseUrl = requiredEnv('DATABASE_URL')
    redisUrl = requiredEnv('REDIS_URL')
    esUrl = requiredEnv('ES_URL')
    projectKey = requiredEnv('FRONTEND_E2E_PROJECT_KEY')
    dbLeaseId = requiredEnv('MRW_DB_SEQUENCE_LEASE')
    pythonBin = requiredEnv('MRW_PYTHON_BIN')
    if (projectKey === 'default' || !/^[a-zA-Z0-9._-]{3,60}$/.test(projectKey)) {
      throw new Error(`INVALID_OR_UNSCOPED_FRONTEND_E2E_PROJECT_KEY:${projectKey}`)
    }
    if (!/^[a-zA-Z0-9._-]{8,128}$/.test(dbLeaseId)) throw new Error(`INVALID_DB_SEQUENCE_LEASE:${dbLeaseId}`)
    const actualDatabaseTargetSha256 = serviceTargetFingerprint(
      databaseUrl,
      ['postgresql:', 'postgresql+psycopg2:'],
      'DATABASE_URL',
    )
    assertEqual(actualDatabaseTargetSha256, databaseTargetSha256, 'DATABASE_TARGET_FINGERPRINT_MISMATCH')
    redisTargetSha256 = serviceTargetFingerprint(redisUrl, ['redis:', 'rediss:'], 'REDIS_URL')
    esTargetSha256 = serviceTargetFingerprint(esUrl, ['http:', 'https:'], 'ES_URL')
    identity = readJsonWithHash(previewIdentityPath, previewIdentitySha256)
    const lifecycle = readJsonWithHash(lifecyclePath, lifecycleSha256)
    validateAdmission(identity, lifecycle, {
      MRW_PREVIEW_COMMIT: previewCommit,
      MRW_PREVIEW_TREE: previewTree,
      MRW_DATABASE_TARGET_SHA256: databaseTargetSha256,
    }, expectedImageSha256, expectedSecurityOwner)
    const securityAdmission = readJsonWithHash(securityAdmissionPath, securityAdmissionSha256)
    validatedSecurityAdmission = validateExternalSecurityAdmission(securityAdmission, {
      runId,
      previewCommit,
      previewTree,
      previewIdentityPath,
      previewIdentitySha256,
      lifecyclePath,
      lifecycleSha256,
      expectedImageSha256,
      networkName,
      networkId,
      expectedSecurityOwner,
    })
  } else {
    candidateManifestPath = requiredEnv('MRW_CANDIDATE_MANIFEST_PATH')
    candidateManifestSha256 = requiredEnv('MRW_CANDIDATE_MANIFEST_SHA256')
    const manifest = readJsonWithHash(candidateManifestPath, candidateManifestSha256)
    assertEqual(manifest.schema_version, 'mrw.stage2.exact-candidate-manifest.v3', 'CANDIDATE_MANIFEST_SCHEMA_MISMATCH')
    assertEqual(manifest.status, 'EXACT_CANDIDATE_INTAKE_NOT_AUTHORITY', 'CANDIDATE_MANIFEST_STATUS_MISMATCH')
  }

  for (const root of [SOURCE_ROOT, join(SOURCE_ROOT, 'main/backend'), join(SOURCE_ROOT, 'main/frontend-modern')]) {
    assertNoEnvFallback(root)
  }
  if (fullExecution && !existsSync(STUB_PATH)) throw new Error(`CODEX_STUB_MISSING:${STUB_PATH}`)
  assertSourceReadOnly(runId)
  await assertPortsFree(fullExecution
    ? [FRONTEND_PORT, STORYBOOK_PORT, BACKEND_PORT, CODEX_STUB_PORT]
    : [STORYBOOK_PORT])

  const workRunRoot = join(WORK_ROOT, `frontend-full-suite-${runId}`)
  const workRepo = join(workRunRoot, 'repo')
  const writablePnpmStore = join(workRunRoot, 'pnpm-store')
  const artifactRoot = join(ARTIFACTS_ROOT, `frontend-full-suite-${runId}`)
  mkdirSync(workRunRoot, { recursive: false, mode: 0o700 })
  mkdirSync(workRepo, { recursive: false, mode: 0o700 })
  if (fullExecution) mkdirSync(writablePnpmStore, { recursive: false, mode: 0o700 })
  mkdirSync(artifactRoot, { recursive: false, mode: 0o700 })
  mkdirSync(join(artifactRoot, 'admission-inputs'), { recursive: false, mode: 0o700 })
  for (const path of ['tmp', 'xdg-cache', 'xdg-config', 'xdg-data', 'npm-cache']) {
    mkdirSync(join(workRunRoot, path), { recursive: false, mode: 0o700 })
  }
  const inputEvidenceCopies = fullExecution
    ? [
        copyHashBoundInput(artifactRoot, 'preview-identity.json', previewIdentityPath, previewIdentitySha256),
        copyHashBoundInput(artifactRoot, 'backend-lifecycle-admission.json', lifecyclePath, lifecycleSha256),
        copyHashBoundInput(artifactRoot, 'external-security-admission.json', securityAdmissionPath, securityAdmissionSha256),
        copyHashBoundInput(
          artifactRoot,
          'network-internal-negative-probe-receipt.json',
          validatedSecurityAdmission.negativeProbe.path,
          validatedSecurityAdmission.negativeProbe.sha256,
        ),
      ]
    : [copyHashBoundInput(
        artifactRoot,
        'candidate-manifest.json',
        candidateManifestPath,
        candidateManifestSha256,
      )]

  const receipt = {
    schema_version: 'frontend-full-suite-result.v1',
    execution_phase: executionPhase,
    run_id: runId,
    status: 'RUNNING',
    authority: NON_AUTHORITY,
    production_release_authorized: false,
    claim_boundary: fullExecution
      ? 'LOCAL_FULL_SUITE_EXECUTION_ONLY_NOT_AUTHORITY'
      : 'STATIC_ONLY_NO_NETWORK_NO_BACKEND_NO_MAIN_E2E_NOT_AUTHORITY',
    started_at: new Date().toISOString(),
    image_sha256: expectedImageSha256,
    network: fullExecution
      ? {
          name: networkName,
          id: networkId,
          internal: true,
          internal_negative_probe: {
            status: validatedSecurityAdmission.negativeProbe.receipt.status,
            receipt_path: validatedSecurityAdmission.negativeProbe.path,
            receipt_sha256: validatedSecurityAdmission.negativeProbe.sha256,
          },
        }
      : {
          name: networkName,
          internal: null,
          internal_negative_probe: 'NOT_EXECUTED_STATIC_ONLY',
        },
    preview: {
      commit: previewCommit,
      tree: previewTree,
      ...(fullExecution
        ? { identity_path: previewIdentityPath, identity_sha256: previewIdentitySha256 }
        : { candidate_manifest_path: candidateManifestPath, candidate_manifest_sha256: candidateManifestSha256 }),
    },
    environment: {
      ...(fullExecution ? {
        fixture_project_key: projectKey,
        database_target_sha256: databaseTargetSha256,
        redis_target_sha256: redisTargetSha256,
        elasticsearch_target_sha256: esTargetSha256,
        db_sequence_lease: dbLeaseId,
        backend_lifecycle_admission_path: lifecyclePath,
        backend_lifecycle_admission_sha256: lifecycleSha256,
        external_security_admission_path: securityAdmissionPath,
        external_security_admission_sha256: securityAdmissionSha256,
        external_security_admission_status: validatedSecurityAdmission.admission.status,
        authority: NON_AUTHORITY,
        production_release_authorized: false,
        values_redacted: ['DATABASE_URL', 'REDIS_URL', 'ES_URL'],
      } : {}),
      forbidden_fallbacks: ['.env', 'host port publish', 'user Codex auth', 'external provider credentials'],
      pnpm_direct_executable: pnpmBin,
      ...(fullExecution ? {
        pnpm_store_source: pnpmStoreDir,
        pnpm_store_working_copy: writablePnpmStore,
      } : {
        dependency_projection_source: join(IMAGE_FRONTEND_ROOT, 'node_modules'),
        dependency_projection_scope: 'IMAGE_FROZEN_INSTALL_NOT_FRESH_CANDIDATE_INSTALL',
      }),
    },
    services: [],
    gates: [],
    input_evidence_copies: inputEvidenceCopies,
    skip_validation: null,
    source_integrity: {},
    errors: [],
  }

  let backendService
  let stubService
  let leasePath
  let statusBeforeTests = ''
  let sourceBefore
  try {
    sourceBefore = candidateSnapshot(SOURCE_ROOT)
    writeJsonCreateOnly(join(artifactRoot, 'source-before-copy.snapshot.json'), sourceBefore)
    assertEqual(sourceBefore.git_head, previewCommit, 'SOURCE_PREVIEW_COMMIT_MISMATCH')
    assertEqual(sourceBefore.git_tree, previewTree, 'SOURCE_PREVIEW_TREE_MISMATCH')
    if (fullExecution) {
      assertEqual(sourceBefore.tracked_root_sha256, identity.tracked_root_sha256, 'SOURCE_TRACKED_ROOT_MISMATCH')
      assertEqual(sourceBefore.candidate_surface_root_sha256, identity.candidate_surface_root_sha256, 'SOURCE_SURFACE_ROOT_MISMATCH')
    }

    const copy = spawnSync('cp', ['-a', `${SOURCE_ROOT}/.`, workRepo], { encoding: 'utf8' })
    if (copy.status !== 0) throw new Error(`COPY_FAILED:${copy.status}:${String(copy.stderr || '').slice(0, 2000)}`)
    for (const root of [workRepo, join(workRepo, 'main/backend'), join(workRepo, 'main/frontend-modern')]) {
      assertNoEnvFallback(root)
    }

    const workAfterCopy = candidateSnapshot(workRepo)
    writeJsonCreateOnly(join(artifactRoot, 'work-after-copy.snapshot.json'), workAfterCopy)
    assertEqual(workAfterCopy.tracked_root_sha256, sourceBefore.tracked_root_sha256, 'COPY_TRACKED_ROOT_MISMATCH')
    assertEqual(workAfterCopy.candidate_surface_root_sha256, sourceBefore.candidate_surface_root_sha256, 'COPY_SURFACE_ROOT_MISMATCH')

    const frontendRoot = join(workRepo, 'main/frontend-modern')
    const backendRoot = join(workRepo, 'main/backend')
    const packageEnv = makeChildEnv(workRunRoot, {
      PLAYWRIGHT_BROWSERS_PATH: playwrightBrowsersPath,
    })
    if (fullExecution) {
      const storeCopy = spawnSync('cp', ['-a', `${pnpmStoreDir}/.`, writablePnpmStore], { encoding: 'utf8' })
      if (storeCopy.status !== 0) {
        throw new Error(`PNPM_STORE_COPY_FAILED:${storeCopy.status}:${String(storeCopy.stderr || '').slice(0, 2000)}`)
      }
      const install = await runLogged(
        pnpmBin,
        ['install', '--frozen-lockfile', '--offline', '--store-dir', writablePnpmStore],
        { cwd: frontendRoot, env: packageEnv, logPath: join(artifactRoot, '00-pnpm-install.log') },
      )
      receipt.gates.push({ id: 'pnpm_frozen_offline_install', ...install })
    } else {
      const inputFiles = ['package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml']
      const inputHashes = {}
      for (const file of inputFiles) {
        const candidateSha256 = sha256File(join(frontendRoot, file))
        const imageSha256 = sha256File(join(IMAGE_FRONTEND_ROOT, file))
        assertEqual(imageSha256, candidateSha256, `IMAGE_DEPENDENCY_INPUT_MISMATCH:${file}`)
        inputHashes[file] = candidateSha256
      }
      assertEqual(
        sha256File(join(IMAGE_FRONTEND_ROOT, 'node_modules/.pnpm/lock.yaml')),
        inputHashes['pnpm-lock.yaml'],
        'IMAGE_VIRTUAL_STORE_LOCK_MISMATCH',
      )
      const projection = spawnSync(
        'cp',
        ['-a', join(IMAGE_FRONTEND_ROOT, 'node_modules'), frontendRoot],
        { encoding: 'utf8' },
      )
      if (projection.status !== 0) {
        throw new Error(`IMAGE_DEPENDENCY_PROJECTION_FAILED:${projection.status}:${String(projection.stderr || '').slice(0, 2000)}`)
      }
      const brokenLink = runCapture(
        'find',
        ['-L', join(frontendRoot, 'node_modules'), '-type', 'l', '-print', '-quit'],
      ).toString('utf8').trim()
      if (brokenLink) throw new Error(`IMAGE_DEPENDENCY_PROJECTION_BROKEN_LINK:${brokenLink}`)
      receipt.gates.push({
        id: 'image_frozen_dependency_projection',
        exit_code: 0,
        source: join(IMAGE_FRONTEND_ROOT, 'node_modules'),
        input_sha256: inputHashes,
        virtual_store_lock_sha256: inputHashes['pnpm-lock.yaml'],
        broken_links: 0,
        claim_boundary: 'IMAGE_FROZEN_INSTALL_NOT_FRESH_CANDIDATE_INSTALL',
      })
    }

    const webServerAdapter = createNarrowPnpmWebServerAdapter(workRunRoot, frontendRoot)
    const devHelp = runCapture(webServerAdapter.adapterPath, ['dev', '--', '--help'], { cwd: frontendRoot, env: packageEnv })
    const storybookHelp = runCapture(webServerAdapter.adapterPath, ['storybook', '--help'], { cwd: frontendRoot, env: packageEnv })
    const rejectedRoute = spawnSync(webServerAdapter.adapterPath, ['install'], {
      cwd: frontendRoot,
      env: packageEnv,
      encoding: 'utf8',
    })
    if (rejectedRoute.status !== 64 || !String(rejectedRoute.stderr || '').includes('NARROW_PNPM_ROUTE_REJECTED:install')) {
      throw new Error(`NARROW_PNPM_REJECTION_SELF_TEST_FAILED:${rejectedRoute.status}`)
    }
    receipt.environment.web_server_adapter = {
      path: webServerAdapter.adapterPath,
      sha256: webServerAdapter.sha256,
      allowed_routes: ['storybook', 'dev'],
      preserved_script_prefixes: webServerAdapter.routes,
      argv_forwarding_self_test: {
        dev_delimiter_help_exit: 0,
        dev_help_sha256: sha256Bytes(devHelp),
        storybook_help_exit: 0,
        storybook_help_sha256: sha256Bytes(storybookHelp),
        rejected_install_exit: rejectedRoute.status,
      },
      claim_boundary: 'EXTERNAL_EXECUTION_ADAPTER_NOT_CANDIDATE_SOURCE',
    }

    statusBeforeTests = gitStatus(workRepo)
    writeJsonCreateOnly(join(artifactRoot, 'work-status-before-tests.json'), {
      status_porcelain_v1_z_base64: Buffer.from(statusBeforeTests, 'utf8').toString('base64'),
      sha256: sha256Bytes(statusBeforeTests),
    })

    const frontendEnv = makeChildEnv(workRunRoot, {
      PATH: `${webServerAdapter.toolBin}:${process.env.PATH || ''}`,
      PLAYWRIGHT_BROWSERS_PATH: playwrightBrowsersPath,
      FRONTEND_E2E_ISOLATED: '1',
      FRONTEND_E2E_PORT: String(FRONTEND_PORT),
      FRONTEND_STORYBOOK_E2E_PORT: String(STORYBOOK_PORT),
      VITE_API_PROXY_TARGET: `http://127.0.0.1:${BACKEND_PORT}`,
      VITE_CODEX_PROXY_TARGET: `http://127.0.0.1:${CODEX_STUB_PORT}`,
      FRONTEND_E2E_RUNTIME_MODE: 'docker',
      TEST_WORKER_INDEX: runId.slice(0, 32),
      ...(fullExecution ? {
        FRONTEND_E2E_PROJECT_KEY: projectKey,
        AGENT_CORE_REAL_BACKEND_E2E: '1',
      } : {}),
    })

    const staticGates = fullExecution ? [
      { id: 'frontend_lint', command: pnpmBin, args: ['run', 'lint'] },
      { id: 'frontend_typecheck', command: pnpmBin, args: ['exec', 'tsc', '-b', '--pretty', 'false'] },
    ] : [
      { id: 'frontend_lint', command: join(frontendRoot, 'node_modules/.bin/eslint'), args: ['.'] },
      { id: 'frontend_typecheck', command: join(frontendRoot, 'node_modules/.bin/tsc'), args: ['-b', '--pretty', 'false'] },
    ]
    for (const gate of staticGates) {
      const result = await runLogged(gate.command, gate.args, {
        cwd: frontendRoot,
        env: frontendEnv,
        logPath: join(artifactRoot, `${gate.id}.log`),
      })
      receipt.gates.push({ id: gate.id, ...result })
    }

    const namedCheckResults = []
    for (const script of NAMED_STATIC_CHECK_SCRIPTS) {
      let command = pnpmBin
      let args = ['run', script]
      if (!fullExecution) {
        const packageJson = JSON.parse(readFileSync(join(frontendRoot, 'package.json'), 'utf8'))
        const scriptCommand = packageJson.scripts?.[script]
        const match = /^node (scripts\/[a-zA-Z0-9._/-]+\.mjs)$/.exec(scriptCommand || '')
        if (!match) throw new Error(`NAMED_STATIC_CHECK_NOT_DIRECT_NODE_SCRIPT:${script}:${scriptCommand || 'missing'}`)
        command = process.execPath
        args = [match[1]]
      }
      const result = await runLogged(command, args, {
        cwd: frontendRoot,
        env: frontendEnv,
        logPath: join(artifactRoot, `named-${script.replaceAll(':', '-')}.log`),
      })
      namedCheckResults.push({ script, ...result })
    }
    receipt.gates.push({
      id: 'frontend_named_static_checks',
      exit_code: namedCheckResults.every((result) => result.exit_code === 0) ? 0 : 1,
      checks: namedCheckResults,
    })

    if (fullExecution) {
      for (const gate of [
        { id: 'frontend_build', args: ['run', 'build'] },
        {
          id: 'storybook_static_build',
          args: ['run', 'storybook:build', '--output-dir', join(artifactRoot, 'storybook-static'), '--disable-telemetry'],
        },
      ]) {
        const result = await runLogged(pnpmBin, gate.args, {
          cwd: frontendRoot,
          env: frontendEnv,
          logPath: join(artifactRoot, `${gate.id}.log`),
        })
        receipt.gates.push({ id: gate.id, ...result })
      }
    } else {
      const buildChecks = []
      for (const commandSpec of [
        {
          name: 'tsc',
          command: join(frontendRoot, 'node_modules/.bin/tsc'),
          args: ['-b', '--pretty', 'false'],
        },
        {
          name: 'vite',
          command: join(frontendRoot, 'node_modules/.bin/vite'),
          args: ['build'],
        },
      ]) {
        const result = await runLogged(commandSpec.command, commandSpec.args, {
          cwd: frontendRoot,
          env: frontendEnv,
          logPath: join(artifactRoot, `frontend_build-${commandSpec.name}.log`),
        })
        buildChecks.push({ name: commandSpec.name, ...result })
      }
      receipt.gates.push({
        id: 'frontend_build',
        exit_code: buildChecks.every((result) => result.exit_code === 0) ? 0 : 1,
        checks: buildChecks,
      })
      const storybookBuild = await runLogged(
        join(frontendRoot, 'node_modules/.bin/storybook'),
        ['build', '--output-dir', join(artifactRoot, 'storybook-static'), '--disable-telemetry'],
        {
          cwd: frontendRoot,
          env: frontendEnv,
          logPath: join(artifactRoot, 'storybook_static_build.log'),
        },
      )
      receipt.gates.push({ id: 'storybook_static_build', ...storybookBuild })
    }

    const frontendBuildGate = receipt.gates.find((gate) => gate.id === 'frontend_build')
    if (frontendBuildGate?.exit_code === 0) {
      copyBuildOutputEvidence(
        join(frontendRoot, 'dist'),
        join(artifactRoot, 'frontend-dist'),
        'FRONTEND_BUILD',
      )
    }

    const storybookJson = join(artifactRoot, 'storybook-playwright.json')
    const storybookEnv = {
      ...frontendEnv,
      PLAYWRIGHT_JSON_OUTPUT_NAME: storybookJson,
      PLAYWRIGHT_JUNIT_OUTPUT_NAME: join(artifactRoot, 'storybook-playwright.xml'),
    }
    const storybook = await runLogged(
      fullExecution ? pnpmBin : join(frontendRoot, 'node_modules/.bin/playwright'),
      fullExecution ? [
        'exec', 'playwright', 'test',
        '--config', 'playwright.storybook.config.ts',
        '--workers', '1',
        '--reporter', 'line,json,junit',
        '--output', join(artifactRoot, 'storybook-test-results'),
      ] : [
        'test',
        '--config', 'playwright.storybook.config.ts',
        '--workers', '1',
        '--reporter', 'line,json,junit',
        '--output', join(artifactRoot, 'storybook-test-results'),
      ],
      { cwd: frontendRoot, env: storybookEnv, logPath: join(artifactRoot, 'storybook-interactions.log') },
    )
    receipt.gates.push({ id: 'storybook_interactions_all_stories', ...storybook })

    if (!fullExecution) return

    mkdirSync(join(ARTIFACTS_ROOT, 'locks'), { recursive: true, mode: 0o700 })
    leasePath = join(ARTIFACTS_ROOT, 'locks', 'mrw-stageconv-shared-db.lock')
    const leaseFd = openSync(leasePath, 'wx', 0o600)
    writeFileSync(leaseFd, `${JSON.stringify({ run_id: runId, lease_id: dbLeaseId, owner: 'frontend-full-suite' })}\n`, 'utf8')
    closeSync(leaseFd)

    const backendEnv = makeChildEnv(workRunRoot, {
      PYTHONPATH: backendRoot,
      ENV: 'test',
      DOCKER_ENV: 'true',
      DATABASE_URL: databaseUrl,
      REDIS_URL: redisUrl,
      ES_URL: esUrl,
      ACTIVE_PROJECT_KEY: projectKey,
      PROJECT_KEY_ENFORCEMENT_MODE: 'require',
      BOOTSTRAP_CREATE_INITIAL_PROJECT: 'false',
      AGENT_CORE_E2E_SCRIPTED_PROVIDER_ENABLED: 'true',
      CODEX_AUTH_ENABLED: 'false',
      CODEX_OAUTH_ENABLED: 'false',
      CODEX_OAUTH_TOKEN_SINK_ENABLED: 'false',
      CODEX_CLI_LLM_FALLBACK_ENABLED: 'false',
      CODEX_CLI_LLM_PERSISTENT_ENABLED: 'false',
      LOCAL_LLM_ENABLED: 'false',
    })

    stubService = startLoggedService(
      process.execPath,
      [STUB_PATH],
      {
        cwd: SCRIPT_DIR,
        env: makeChildEnv(workRunRoot, { CODEX_STUB_PORT: String(CODEX_STUB_PORT) }),
        logPath: join(artifactRoot, 'codex-stub18379.log'),
        name: 'codex-stub18379',
      },
    )
    backendService = startLoggedService(
      pythonBin,
      ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(BACKEND_PORT)],
      {
        cwd: backendRoot,
        env: backendEnv,
        logPath: join(artifactRoot, 'backend18139.log'),
        name: 'backend18139',
      },
    )
    receipt.services.push(
      { name: stubService.name, pid: stubService.pid, log_path: stubService.log_path },
      { name: backendService.name, pid: backendService.pid, log_path: backendService.log_path },
    )

    receipt.services[0].readiness = await waitForHttp(`http://127.0.0.1:${CODEX_STUB_PORT}/healthz`, stubService)
    receipt.services[1].health = await waitForHttp(`http://127.0.0.1:${BACKEND_PORT}/api/v1/health`, backendService)
    receipt.services[1].deep_health = await waitForHttp(`http://127.0.0.1:${BACKEND_PORT}/api/v1/health/deep`, backendService)
    receipt.gates.push({
      id: 'backend_and_stub_readiness',
      exit_code: 0,
      stub: receipt.services[0].readiness,
      backend_health: receipt.services[1].health,
      backend_deep_health: receipt.services[1].deep_health,
    })

    const e2eJson = join(artifactRoot, 'frontend-e2e.json')
    const e2eEnv = {
      ...frontendEnv,
      PLAYWRIGHT_JSON_OUTPUT_NAME: e2eJson,
      PLAYWRIGHT_JUNIT_OUTPUT_NAME: join(artifactRoot, 'frontend-e2e.xml'),
    }
    const e2e = await runLogged(
      pnpmBin,
      [
        'exec', 'playwright', 'test',
        '--config', 'playwright.config.ts',
        '--workers', '1',
        '--reporter', 'line,json,junit',
        '--output', join(artifactRoot, 'frontend-e2e-test-results'),
      ],
      { cwd: frontendRoot, env: e2eEnv, logPath: join(artifactRoot, 'frontend-e2e.log') },
    )
    receipt.gates.push({ id: 'frontend_e2e_complete_no_maxfail', ...e2e })
    receipt.skip_validation = validateStaticSkips(e2eJson)
  } catch (error) {
    receipt.errors.push(error instanceof Error ? `${error.name}:${error.message}` : String(error))
  } finally {
    for (const service of [backendService, stubService]) {
      try {
        await stopService(service)
      } catch (error) {
        receipt.errors.push(error instanceof Error ? `SERVICE_CLEANUP:${error.message}` : `SERVICE_CLEANUP:${String(error)}`)
      }
    }
    if (leasePath && existsSync(leasePath)) {
      const lease = readFileSync(leasePath, 'utf8')
      if (lease.includes(`"run_id":"${runId}"`)) unlinkSync(leasePath)
      else receipt.errors.push('DB_LEASE_OWNERSHIP_CHANGED_NOT_REMOVED')
    }

    if (existsSync(workRepo)) {
      try {
        const workAfterTests = candidateSnapshot(workRepo)
        const sourceAfterTests = candidateSnapshot(SOURCE_ROOT)
        writeJsonCreateOnly(join(artifactRoot, 'work-after-tests.snapshot.json'), workAfterTests)
        writeJsonCreateOnly(join(artifactRoot, 'source-after-tests.snapshot.json'), sourceAfterTests)
        const statusAfterTests = gitStatus(workRepo)
        const statusDelta = statusDifference(statusBeforeTests, statusAfterTests)
        writeJsonCreateOnly(join(artifactRoot, 'work-source-difference-after-tests.json'), {
          baseline_status_sha256: sha256Bytes(statusBeforeTests),
          after_status_sha256: sha256Bytes(statusAfterTests),
          status_unchanged: statusAfterTests === statusBeforeTests,
          ...statusDelta,
        })
        receipt.source_integrity = {
          source_mount_unchanged: sourceAfterTests.tracked_root_sha256 === sourceBefore?.tracked_root_sha256
            && sourceAfterTests.candidate_surface_root_sha256 === sourceBefore?.candidate_surface_root_sha256,
          work_tracked_unchanged: workAfterTests.tracked_root_sha256 === sourceBefore?.tracked_root_sha256,
          work_candidate_surface_unchanged: workAfterTests.candidate_surface_root_sha256 === sourceBefore?.candidate_surface_root_sha256,
          work_git_status_unchanged_from_test_baseline: statusAfterTests === statusBeforeTests,
          source_after_tracked_root_sha256: sourceAfterTests.tracked_root_sha256,
          source_after_candidate_surface_root_sha256: sourceAfterTests.candidate_surface_root_sha256,
          work_after_tracked_root_sha256: workAfterTests.tracked_root_sha256,
          work_after_candidate_surface_root_sha256: workAfterTests.candidate_surface_root_sha256,
          work_status_after_sha256: sha256Bytes(statusAfterTests),
        }
      } catch (error) {
        receipt.errors.push(error instanceof Error ? `POST_TEST_INTEGRITY:${error.message}` : `POST_TEST_INTEGRITY:${String(error)}`)
      }
    }

    let artifactManifest = null
    try {
      materializeGateReceipts(artifactRoot, runId, receipt.gates, receipt.services)
      artifactManifest = writeArtifactManifest(artifactRoot, runId, executionPhase)
      artifactManifest.validated = validateArtifactManifest(artifactRoot, {
        ...artifactManifest,
        runId,
        executionPhase,
        gates: receipt.gates,
      })
      receipt.artifact_manifest = artifactManifest
    } catch (error) {
      receipt.errors.push(error instanceof Error
        ? `ARTIFACT_CLOSURE:${error.message}`
        : `ARTIFACT_CLOSURE:${String(error)}`)
      receipt.artifact_manifest = {
        status: 'INVALID_OR_INCOMPLETE',
        authority: NON_AUTHORITY,
        production_release_authorized: false,
      }
    }

    const failedGates = receipt.gates.filter((gate) => gate.exit_code !== 0)
    const actualGateIds = receipt.gates.map((gate) => gate.id)
    const expectedGateIds = fullExecution ? EXPECTED_GATE_IDS : EXPECTED_STATIC_GATE_IDS
    const gateInventoryValid = JSON.stringify(actualGateIds) === JSON.stringify(expectedGateIds)
    const sourceIntegrityPass = receipt.source_integrity.source_mount_unchanged === true
      && receipt.source_integrity.work_tracked_unchanged === true
      && receipt.source_integrity.work_candidate_surface_unchanged === true
      && receipt.source_integrity.work_git_status_unchanged_from_test_baseline === true
    const pass = receipt.errors.length === 0
      && failedGates.length === 0
      && gateInventoryValid
      && (!fullExecution || receipt.skip_validation?.valid === true)
      && sourceIntegrityPass
      && artifactManifest !== null
    receipt.status = pass
      ? fullExecution
        ? 'PASS_COMPLETE_NO_SKIPS'
        : 'STATIC_SLICE_PASS_IMAGE_FROZEN_DEPS_NO_BACKEND_OR_MAIN_E2E_EXECUTED'
      : 'FAIL_OR_BLOCKED'
    receipt.ended_at = new Date().toISOString()
    receipt.failed_gate_ids = failedGates.map((gate) => gate.id)
    receipt.gate_inventory = {
      valid: gateInventoryValid,
      actual_ids: actualGateIds,
      expected_ids: expectedGateIds,
    }
    const resultPath = join(artifactRoot, 'frontend-full-suite-result.v1.json')
    const resultSidecarPath = join(artifactRoot, 'frontend-full-suite-result.v1.sha256.json')
    receipt.result_content_addressing = {
      algorithm: 'sha256',
      sidecar_path: resultSidecarPath,
      claim_boundary: 'LOCAL_EXECUTION_EVIDENCE_NOT_AUTHORITY',
    }
    writeJsonCreateOnly(resultPath, receipt)
    writeJsonCreateOnly(resultSidecarPath, {
      schema_version: 'frontend-full-suite-result-content-address.v1',
      authority: NON_AUTHORITY,
      production_release_authorized: false,
      run_id: runId,
      result_path: resultPath,
      bytes: lstatSync(resultPath).size,
      sha256: sha256File(resultPath),
      artifact_manifest_path: artifactManifest?.path || null,
      artifact_manifest_sha256: artifactManifest?.sha256 || null,
    })
    process.exitCode = pass ? 0 : 1
  }
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`)
  process.exitCode = 1
})

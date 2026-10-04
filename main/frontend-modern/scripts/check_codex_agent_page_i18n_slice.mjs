#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  page: 'src/pages/CodexAgentPage.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
}

const requiredKeys = [
  'codexAgentPage.title',
  'codexAgentPage.status.kicker',
  'codexAgentPage.status.ready',
  'codexAgentPage.status.readyDetail',
  'codexAgentPage.status.connecting',
  'codexAgentPage.status.connectingDetail',
  'codexAgentPage.status.error',
  'codexAgentPage.status.errorDetail',
  'codexAgentPage.status.hostAuth',
  'codexAgentPage.status.hostAuthMissing',
  'codexAgentPage.status.hostAuthUnknown',
  'codexAgentPage.status.snapshot',
  'codexAgentPage.status.refresh',
  'codexAgentPage.status.booting',
  'codexAgentPage.auth.title',
  'codexAgentPage.auth.detail',
  'codexAgentPage.auth.remoteHostDetail',
  'codexAgentPage.auth.retry',
]

function readFile(relPath) {
  return fs.readFileSync(path.join(rootDir, relPath), 'utf8')
}

const pageSource = readFile(files.page)
const catalogSource = readFile(files.catalog)
const failures = []

for (const key of requiredKeys) {
  if (!pageSource.includes(`'${key}'`)) {
    failures.push(`CodexAgentPage does not use ${key}`)
  }

  const shortKey = key.replace(/^codexAgentPage\./, '')
  const keyPattern = shortKey === 'title'
    ? /(?:^|\n)  codexAgentPage: \{[\s\S]*?\n    title:/g
    : new RegExp(`'${shortKey.replace(/\./g, '\\.')}':`, 'g')
  const catalogOccurrences = catalogSource.match(keyPattern) || []
  if (catalogOccurrences.length < 3) {
    failures.push(`codexAgentPage catalog key ${shortKey} must exist in shape, zh-CN, and en-US`)
  }
}

if (!pageSource.includes('useAppLocale()')) {
  failures.push('CodexAgentPage must read the shared app locale')
}
if (!pageSource.includes("from '../app/platform/i18n'")) {
  failures.push('CodexAgentPage must use the shared i18n entrypoint')
}
if (!catalogSource.includes('const namespaceCatalog = catalog[namespace as keyof CatalogShape]')) {
  failures.push('catalog readback must support the codexAgentPage namespace through generic namespace lookup')
}

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'codex_agent_page_i18n_slice',
  page: files.page,
  catalog_namespace: 'codexAgentPage',
  required_keys: requiredKeys.length,
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}

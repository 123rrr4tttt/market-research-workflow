#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(scriptDir, '..')

const frontendFiles = {
  appShell: 'src/app/shell/AppShell.tsx',
  frontendKernelApp: 'src/app/kernel/FrontendKernelApp.tsx',
  routes: 'src/app/kernel/routes.ts',
  i18nCatalog: 'src/app/platform/i18n/catalog.ts',
  i18nIndex: 'src/app/platform/i18n/index.ts',
  i18nStore: 'src/app/platform/i18n/store.ts',
  i18nTypes: 'src/app/platform/i18n/types.ts',
  adminLayerShell: 'src/app/kernel/AdminLayerShell.tsx',
  visualizationLayerShell: 'src/app/kernel/VisualizationLayerShell.tsx',
  workbenchLayerShell: 'src/app/kernel/WorkbenchLayerShell.tsx',
}

const requiredCatalogChecks = [
  { label: 'shell title keys', snippet: "'title.overviewTasks':" },
  { label: 'navigation group keys', snippet: "'group.overview':" },
  { label: 'navigation item keys', snippet: "'item.flowWriting':" },
  { label: 'settings locale keys', snippet: "'locale.en-US':" },
  { label: 'settings theme keys', snippet: "'theme.brand':" },
  { label: 'shared loading key', snippet: 'loading:' },
]

const requiredI18nEntrypoints = ['translate', 'useAppLocale', 'setAppLocale', 'getAppLocale']

const platformLeakPattern = /\.\.\/(?:kernel|shell)\b|AppShell|FrontendKernelApp|LayerShell/

const shellBlockerMarkers = [
  {
    key: 'unknown_route_falls_back_to_app_shell',
    file: 'frontendKernelApp',
    snippets: ["route.source === 'unknown'", 'return <AppShell />'],
    evidence:
      'FrontendKernelApp still routes unknown hashes through AppShell, so page-shell retirement is separate from i18n closure.',
  },
  {
    key: 'app_shell_reads_window_hash',
    file: 'appShell',
    snippets: ['resolveShellModeFromHash(window.location.hash'],
    evidence: 'AppShell still owns runtime hash resolution for the compatibility path.',
  },
  {
    key: 'legacy_shell_renderer_path',
    file: 'appShell',
    snippets: ["shellMode: 'legacy-shell'"],
    evidence: 'AppShell still renders kernel modules through a legacy-shell mode.',
  },
  {
    key: 'figma_side_nav_mounted_by_app_shell',
    file: 'appShell',
    snippets: ['<FigmaSideNav'],
    evidence: 'AppShell still mounts the legacy side navigation directly.',
  },
  {
    key: 'legacy_route_source_retained',
    file: 'routes',
    snippets: ["source: 'legacy'", "source: 'unknown'"],
    evidence: 'Kernel route resolution still classifies legacy and unknown sources explicitly.',
  },
]

const failures = []

function readFrontend(relPath) {
  return fs.readFileSync(path.join(frontendRoot, relPath), 'utf8')
}

function fail(message) {
  failures.push(message)
}

function includesAll(source, snippets) {
  return snippets.every((snippet) => source.includes(snippet))
}

const frontendSources = Object.fromEntries(
  Object.entries(frontendFiles).map(([key, relPath]) => [key, readFrontend(relPath)]),
)

const catalogSource = frontendSources.i18nCatalog
const i18nTypesSource = frontendSources.i18nTypes
const i18nIndexSource = frontendSources.i18nIndex

const catalogFailures = []
for (const check of requiredCatalogChecks) {
  if (!catalogSource.includes(check.snippet)) {
    catalogFailures.push(check.label)
    fail(`missing i18n catalog anchor: ${check.label}`)
  }
}

const localeMatches = Array.from(new Set(Array.from(i18nTypesSource.matchAll(/'([^']+)'/g)).map((match) => match[1])))
for (const locale of ['zh-CN', 'en-US']) {
  if (!localeMatches.includes(locale)) fail(`APP_LOCALES missing ${locale}`)
}

for (const entrypoint of requiredI18nEntrypoints) {
  if (!i18nIndexSource.includes(entrypoint)) fail(`i18n entrypoint does not export ${entrypoint}`)
}

const i18nPlatformFiles = ['i18nCatalog', 'i18nIndex', 'i18nStore', 'i18nTypes']
const platformLeaks = []
for (const key of i18nPlatformFiles) {
  if (platformLeakPattern.test(frontendSources[key])) {
    platformLeaks.push(frontendFiles[key])
    fail(`i18n platform file imports or references shell/kernel ownership: ${frontendFiles[key]}`)
  }
}

const shellConsumerChecks = [
  { label: 'AppShell', key: 'appShell' },
  { label: 'AdminLayerShell', key: 'adminLayerShell' },
  { label: 'VisualizationLayerShell', key: 'visualizationLayerShell' },
  { label: 'WorkbenchLayerShell', key: 'workbenchLayerShell' },
]

const shellConsumers = {}
for (const check of shellConsumerChecks) {
  const source = frontendSources[check.key]
  shellConsumers[check.label] = {
    use_app_locale: source.includes('useAppLocale()'),
    translate_nav_or_title: source.includes('translate(locale'),
  }
  if (!shellConsumers[check.label].use_app_locale) fail(`${check.label} does not read shared app locale`)
  if (!shellConsumers[check.label].translate_nav_or_title) fail(`${check.label} does not translate shell/nav labels`)
}

const shellBlockers = shellBlockerMarkers.map((marker) => ({
  key: marker.key,
  file: frontendFiles[marker.file],
  present: includesAll(frontendSources[marker.file], marker.snippets),
  evidence: marker.evidence,
}))

const presentShellBlockers = shellBlockers.filter((marker) => marker.present)

const summary = {
  status: failures.length ? 'failed' : 'ok',
  gate_type: 'i18n_page_shell_disjoint',
  decision: {
    dual_frontend_unique_blocker: false,
    dual_frontend_can_transfer_to_three_layer: failures.length === 0,
    frontend_i18n_platform_closed: failures.length === 0 && catalogFailures.length === 0 && platformLeaks.length === 0,
    page_shell_retirement_complete: presentShellBlockers.length === 0,
    three_layer_retains_page_shell_blocker: presentShellBlockers.length > 0,
  },
  i18n_platform: {
    locales: localeMatches.filter((locale) => locale === 'zh-CN' || locale === 'en-US'),
    required_catalog_anchors: requiredCatalogChecks.length,
    missing_catalog_anchors: catalogFailures,
    exported_entrypoints: requiredI18nEntrypoints,
    platform_leaks: platformLeaks,
    shell_consumers: shellConsumers,
  },
  page_shell_boundary: {
    blocker_markers_present: presentShellBlockers.length,
    blocker_markers_total: shellBlockers.length,
    blockers: shellBlockers,
  },
  interpretation: [
    'The dual-frontend topic has no separate repo-local implementation blocker once topology and layer-shell contracts are green.',
    'The frontend i18n platform gate is disjoint from page-shell retirement: i18n can be closed or migrated without claiming AppShell retirement.',
    'If page-shell blockers remain present, closure belongs to the three-layer rewrite lane rather than the dual-frontend topology lane.',
  ],
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}

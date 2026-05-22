#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  adminLayerShell: 'src/app/kernel/AdminLayerShell.tsx',
  frontendKernelApp: 'src/app/kernel/FrontendKernelApp.tsx',
  moduleChrome: 'src/app/kernel/moduleChrome.ts',
  moduleManifest: 'src/app/kernel/moduleManifest.ts',
  renderKernelModuleContent: 'src/app/kernel/renderKernelModuleContent.tsx',
  useKernelRuntime: 'src/app/kernel/useKernelRuntime.ts',
  visualizationLayerShell: 'src/app/kernel/VisualizationLayerShell.tsx',
  workbenchLayerShell: 'src/app/kernel/WorkbenchLayerShell.tsx',
}

const expectedSurfaceByLayer = {
  A: 'workbench',
  B: 'visualization',
  C: 'management',
}

const expectedRoutePrefixByLayer = {
  A: '/workbench/',
  B: '/visual/',
  C: '/admin/',
}

const failures = []

function readFile(relPath) {
  return fs.readFileSync(path.join(rootDir, relPath), 'utf8')
}

function fail(message) {
  failures.push(message)
}

function assertCondition(condition, message) {
  if (!condition) fail(message)
}

function unique(values) {
  return Array.from(new Set(values))
}

function countValues(values) {
  return values.reduce((acc, value) => {
    acc[value] = (acc[value] || 0) + 1
    return acc
  }, {})
}

function compareSets(label, expected, actual) {
  const expectedSet = new Set(expected)
  const actualSet = new Set(actual)
  const missing = expected.filter((item) => !actualSet.has(item))
  const extra = actual.filter((item) => !expectedSet.has(item))
  if (missing.length > 0) fail(`${label} missing: ${missing.join(', ')}`)
  if (extra.length > 0) fail(`${label} extra: ${extra.join(', ')}`)
}

function extractModuleManifest(source) {
  const entries = []
  const pattern =
    /defineModule\(\s*'([^']+)'\s*,\s*'([ABC])'\s*,\s*'(workbench|visualization|management)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'/g
  let match = pattern.exec(source)
  while (match) {
    entries.push({
      moduleKey: match[1],
      layerId: match[2],
      surfaceKind: match[3],
      entryRoute: match[4],
      legacyHash: match[5],
      navGroupKey: match[6],
    })
    match = pattern.exec(source)
  }
  if (entries.length === 0) fail('Could not read defineModule entries from moduleManifest')
  return entries
}

function extractAssignmentArrayBlock(source, variableName) {
  const markerIndex = source.indexOf(`const ${variableName}`)
  if (markerIndex === -1) {
    fail(`Could not find ${variableName}`)
    return ''
  }
  const assignmentIndex = source.indexOf('=', markerIndex)
  if (assignmentIndex === -1) {
    fail(`Could not find ${variableName} assignment`)
    return ''
  }
  const start = source.indexOf('[', assignmentIndex)
  if (start === -1) {
    fail(`Could not find ${variableName} array literal`)
    return ''
  }

  let depth = 0
  for (let index = start; index < source.length; index += 1) {
    const char = source[index]
    if (char === '[') depth += 1
    if (char === ']') depth -= 1
    if (depth === 0) return source.slice(start, index + 1)
  }

  fail(`Could not close ${variableName} array literal`)
  return ''
}

function extractKnownModuleKeysFromAssignment(source, variableName, knownModuleKeys) {
  const block = extractAssignmentArrayBlock(source, variableName)
  const keys = []
  const quotedString = /'([^']+)'/g
  let match = quotedString.exec(block)
  while (match) {
    if (knownModuleKeys.has(match[1])) keys.push(match[1])
    match = quotedString.exec(block)
  }
  return keys
}

function assertNoDuplicates(label, values) {
  for (const [value, count] of Object.entries(countValues(values))) {
    if (count > 1) fail(`${label} duplicated ${value} ${count} times`)
  }
}

const moduleManifestSource = readFile(files.moduleManifest)
const moduleEntries = extractModuleManifest(moduleManifestSource)
const moduleKeys = moduleEntries.map((entry) => entry.moduleKey)
const knownModuleKeys = new Set(moduleKeys)

assertNoDuplicates('moduleManifest.moduleKey', moduleKeys)
assertNoDuplicates('moduleManifest.entryRoute', moduleEntries.map((entry) => entry.entryRoute))
assertNoDuplicates('moduleManifest.legacyHash', moduleEntries.map((entry) => entry.legacyHash))

for (const entry of moduleEntries) {
  assertCondition(
    entry.surfaceKind === expectedSurfaceByLayer[entry.layerId],
    `moduleManifest ${entry.moduleKey} layer ${entry.layerId} must use ${expectedSurfaceByLayer[entry.layerId]} surface`,
  )
  assertCondition(
    entry.entryRoute.startsWith(expectedRoutePrefixByLayer[entry.layerId]),
    `moduleManifest ${entry.moduleKey} route ${entry.entryRoute} must start with ${expectedRoutePrefixByLayer[entry.layerId]}`,
  )
}

const modulesByLayer = {
  A: moduleEntries.filter((entry) => entry.layerId === 'A').map((entry) => entry.moduleKey),
  B: moduleEntries.filter((entry) => entry.layerId === 'B').map((entry) => entry.moduleKey),
  C: moduleEntries.filter((entry) => entry.layerId === 'C').map((entry) => entry.moduleKey),
}

const workbenchLayerShellSource = readFile(files.workbenchLayerShell)
const visualizationLayerShellSource = readFile(files.visualizationLayerShell)
const adminLayerShellSource = readFile(files.adminLayerShell)
const moduleChromeSource = readFile(files.moduleChrome)
const frontendKernelAppSource = readFile(files.frontendKernelApp)
const renderKernelModuleContentSource = readFile(files.renderKernelModuleContent)
const useKernelRuntimeSource = readFile(files.useKernelRuntime)

const shellModulesByLayer = {
  A: extractKnownModuleKeysFromAssignment(workbenchLayerShellSource, 'WORKBENCH_MODULES', knownModuleKeys),
  B: extractKnownModuleKeysFromAssignment(moduleChromeSource, 'VISUALIZATION_SHELL_SECTIONS', knownModuleKeys),
  C: extractKnownModuleKeysFromAssignment(adminLayerShellSource, 'ADMIN_GROUPS', knownModuleKeys),
}

for (const layerId of Object.keys(modulesByLayer)) {
  assertNoDuplicates(`Layer ${layerId} shell module list`, shellModulesByLayer[layerId])
  compareSets(`Layer ${layerId} shell module coverage`, modulesByLayer[layerId], shellModulesByLayer[layerId])
}

assertCondition(frontendKernelAppSource.includes("route.layerId === 'A'"), 'FrontendKernelApp must branch on Layer A')
assertCondition(frontendKernelAppSource.includes("route.layerId === 'B'"), 'FrontendKernelApp must branch on Layer B')
assertCondition(frontendKernelAppSource.includes("route.layerId === 'C'"), 'FrontendKernelApp must branch on Layer C')
assertCondition(frontendKernelAppSource.includes('<WorkbenchLayerShell activeModule={route.moduleKey} runtime={runtime} />'), 'Layer A must render WorkbenchLayerShell')
assertCondition(frontendKernelAppSource.includes('<VisualizationLayerShell activeModule={route.moduleKey} runtime={runtime} />'), 'Layer B must render VisualizationLayerShell')
assertCondition(frontendKernelAppSource.includes('<AdminLayerShell activeModule={route.moduleKey} runtime={runtime} />'), 'Layer C must render AdminLayerShell')
assertCondition(frontendKernelAppSource.includes('useAppTheme()'), 'FrontendKernelApp must read shared app theme')
assertCondition(frontendKernelAppSource.includes('applyThemeTokens(appTheme)'), 'FrontendKernelApp must apply shared theme tokens')

assertCondition(workbenchLayerShellSource.includes('useAppLocale()'), 'WorkbenchLayerShell must read shared app locale')
assertCondition(visualizationLayerShellSource.includes('useAppLocale()'), 'VisualizationLayerShell must read shared app locale')
assertCondition(adminLayerShellSource.includes('useAppLocale()'), 'AdminLayerShell must read shared app locale')
assertCondition(workbenchLayerShellSource.includes('translate(locale'), 'WorkbenchLayerShell must translate nav labels through i18n')
assertCondition(visualizationLayerShellSource.includes('translate(locale'), 'VisualizationLayerShell must translate nav labels through i18n')
assertCondition(adminLayerShellSource.includes('translate(locale'), 'AdminLayerShell must translate nav labels through i18n')
assertCondition(workbenchLayerShellSource.includes('activeLayer="A"'), 'WorkbenchLayerShell must expose LayerSwitch activeLayer A')
assertCondition(visualizationLayerShellSource.includes('activeLayer="B"'), 'VisualizationLayerShell must expose LayerSwitch activeLayer B')
assertCondition(adminLayerShellSource.includes('activeLayer="C"'), 'AdminLayerShell must expose LayerSwitch activeLayer C')
assertCondition(workbenchLayerShellSource.includes('shellMode="workbench"'), 'WorkbenchLayerShell must pass shellMode="workbench"')
assertCondition(visualizationLayerShellSource.includes('shellMode="visualization"'), 'VisualizationLayerShell must pass shellMode="visualization"')
assertCondition(adminLayerShellSource.includes('shellMode="admin"'), 'AdminLayerShell must pass shellMode="admin"')
assertCondition(renderKernelModuleContentSource.includes("'admin'"), 'KernelRenderShellMode must include admin shell mode')
assertCondition(useKernelRuntimeSource.includes('buildLayerRouteHash(moduleKey)'), 'Kernel runtime navigation must use layered route hashes')

const summary = {
  status: failures.length === 0 ? 'ok' : 'failed',
  modules: moduleEntries.length,
  layer_counts: {
    A: modulesByLayer.A.length,
    B: modulesByLayer.B.length,
    C: modulesByLayer.C.length,
  },
  shell_coverage_counts: {
    A: unique(shellModulesByLayer.A).length,
    B: unique(shellModulesByLayer.B).length,
    C: unique(shellModulesByLayer.C).length,
  },
  route_prefixes: expectedRoutePrefixByLayer,
  surface_by_layer: expectedSurfaceByLayer,
  checked_files: Object.values(files),
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}

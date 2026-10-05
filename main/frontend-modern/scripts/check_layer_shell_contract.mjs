#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  adminLayerShell: 'src/app/kernel/AdminLayerShell.tsx',
  i18nCatalog: 'src/app/platform/i18n/catalog.ts',
  frontendKernelApp: 'src/app/kernel/FrontendKernelApp.tsx',
  kernelTypes: 'src/app/kernel/types.ts',
  moduleChrome: 'src/app/kernel/moduleChrome.ts',
  moduleManifest: 'src/app/kernel/moduleManifest.ts',
  moduleRenderer: 'src/app/kernel/ModuleRenderer.tsx',
  projectGraphTemplatesHook: 'src/pages/graph/hooks/useProjectGraphTemplates.ts',
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

function extractAsConstObjectProperty(source, objectName, propertyName) {
  const declarationMarker = `export const ${objectName} = {`
  const declarationIndex = source.indexOf(declarationMarker)
  if (declarationIndex === -1) {
    fail(`Could not find ${objectName}`)
    return null
  }

  const objectStart = source.indexOf('{', declarationIndex)
  if (objectStart === -1) {
    fail(`Could not find ${objectName} object`)
    return null
  }

  let objectEnd = -1
  let depth = 0
  for (let index = objectStart; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1
    if (source[index] === '}') {
      depth -= 1
      if (depth === 0) {
        objectEnd = index
        break
      }
    }
  }
  if (objectEnd === -1) {
    fail(`Could not close ${objectName} object`)
    return null
  }
  if (!source.startsWith('} as const', objectEnd)) {
    fail(`${objectName} must be declared as const`)
    return null
  }

  const objectSource = source.slice(objectStart, objectEnd + 1)
  const propertyPattern = new RegExp(`^  ${propertyName}: '([^']+)',?$`, 'm')
  const propertyMatch = objectSource.match(propertyPattern)
  if (!propertyMatch) {
    fail(`${objectName} must declare ${propertyName}`)
    return null
  }

  return propertyMatch[1]
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
const kernelTypesSource = readFile(files.kernelTypes)
const moduleRendererSource = readFile(files.moduleRenderer)
const renderKernelModuleContentSource = readFile(files.renderKernelModuleContent)
const useKernelRuntimeSource = readFile(files.useKernelRuntime)
const projectGraphTemplatesHookSource = readFile(files.projectGraphTemplatesHook)

const shellModulesByLayer = {
  A: extractKnownModuleKeysFromAssignment(workbenchLayerShellSource, 'WORKBENCH_MODULES', knownModuleKeys),
  B: modulesByLayer.B.filter((moduleKey) => moduleKey === 'dataDashboard' || moduleKey.startsWith('graph')),
  C: extractKnownModuleKeysFromAssignment(moduleManifestSource, 'ADMIN_NAV_SECTIONS', knownModuleKeys),
}

const visualizationNavKeys = shellModulesByLayer.B
const declaredVisualizationNavKeys = extractKnownModuleKeysFromAssignment(
  moduleChromeSource,
  'VISUALIZATION_SHELL_SECTIONS',
  knownModuleKeys,
)
const retiredVisualizationNavKeys = modulesByLayer.B.filter((moduleKey) => (
  moduleKey.startsWith('data') && moduleKey !== 'dataDashboard'
) || moduleKey.startsWith('flow'))

assertCondition(adminLayerShellSource.includes('ADMIN_NAV_SECTIONS.map('), 'Layer C must render the manifest admin navigation sections')
assertCondition(adminLayerShellSource.includes('group.items.map('), 'Layer C must expose every item in each responsibility group')
assertCondition(!adminLayerShellSource.includes('kernel-admin__secondary-nav'), 'Layer C must not hide modules under a secondary navigation menu')
assertCondition(!adminLayerShellSource.includes('<BusinessChainGuide'), 'Layer C must render the business guide only through its own module')
assertCondition(moduleEntries.some((entry) => entry.moduleKey === 'sysBusinessGuide' && entry.entryRoute === '/admin/guide'), 'Business guide must have an independent manifest route')

assertNoDuplicates('Layer A shell module list', shellModulesByLayer.A)
assertNoDuplicates('Layer B visible navigation list', visualizationNavKeys)
assertNoDuplicates('Layer C shell module list', shellModulesByLayer.C)
compareSets('Layer A shell module coverage', modulesByLayer.A, shellModulesByLayer.A)
compareSets('Layer C shell module coverage', modulesByLayer.C, shellModulesByLayer.C)
assertCondition(
  declaredVisualizationNavKeys.includes('dataDashboard') && declaredVisualizationNavKeys.length === 1,
  'Visualization static section declaration must contain exactly the dataDashboard statistics entry',
)
assertCondition(
  moduleChromeSource.includes(".filter((entry) => entry.navGroupKey === 'navigation.group.graph')"),
  'Visualization graph navigation must derive its module keys from the manifest graph entry points',
)
assertCondition(
  modulesByLayer.B.length > unique(visualizationNavKeys).length,
  'Layer B must keep more routable catalog entries than the intentionally reduced visible navigation',
)
assertCondition(
  retiredVisualizationNavKeys.every((moduleKey) => !visualizationNavKeys.includes(moduleKey)),
  `Layer B retired nav routes must remain routable but hidden: ${retiredVisualizationNavKeys.join(', ')}`,
)
assertCondition(
  moduleChromeSource.includes('.filter((entry) => entry.layerId === \'B\')'),
  'Visualization coverage must retain the complete Layer B routable catalog',
)
assertCondition(
  moduleChromeSource.includes('getVisualizationShellSections(graphItems, [])'),
  'Visualization coverage must validate visible module navigation separately from template navigation',
)
assertCondition(
  moduleChromeSource.includes('invalidVisibleNav') && moduleChromeSource.includes('invalidTemplateKeys'),
  'Visualization coverage must report invalid visible and template identities separately',
)

const visualizationAuthorityChecks = [
  'queryKey: queryKeys.graph.config(projectKey)',
  'queryFn: getGraphConfig',
  'enabled: Boolean(projectKey)',
  'coerceGraphProjectionBindings(graphConfig.data?.graph_projections)',
  'applyWorkspaceTabBindings(GRAPH_WORKSPACE_TABS, declaredProjections)',
  'useProjectGraphTemplates(projectKey, Boolean(projectKey))',
  'buildGraphTemplateRoute(item.templateKey)',
  'getGraphTemplateKeyFromHash(routeHash)',
]
for (const check of visualizationAuthorityChecks) {
  assertCondition(
    visualizationLayerShellSource.includes(check),
    `Visualization shell must use the authoritative graph navigation chain: ${check}`,
  )
}
assertCondition(
  projectGraphTemplatesHookSource.includes('queryKey: queryKeys.graph.templates(projectKey)'),
  'Project graph template navigation must use the shared graph templates query key',
)
assertCondition(
  visualizationLayerShellSource.includes('graphTemplates.isSuccess ? graphTemplates.data || [] : []'),
  'Visualization template navigation may read the list only after the shared query succeeds',
)
assertCondition(
  visualizationLayerShellSource.includes('<header className="kernel-visual__masthead kernel-visual__topbar">'),
  'Visualization masthead must expose the compressed topbar class while retaining the masthead class',
)
assertCondition(
  !visualizationLayerShellSource.includes('kernel-visual__eyebrow')
    && !visualizationLayerShellSource.includes('observation surface')
    && !visualizationLayerShellSource.includes('activeContract.entryRoute'),
  'Visualization topbar must not render route-observation decoration',
)
assertCondition(
  visualizationLayerShellSource.includes('<main className="kernel-visual__main kernel-visual__stage">'),
  'Visualization main must directly carry the stage compatibility class',
)
assertCondition(
  !visualizationLayerShellSource.includes('<section className="kernel-visual__stage">'),
  'Visualization main must not nest a separate stage section',
)
assertCondition(
  visualizationLayerShellSource.includes('shell.visualization.statsTitle') && visualizationLayerShellSource.includes('shell.visualization.statsEmpty'),
  'Visualization non-graph routes must render the lightweight statistics empty state',
)
assertCondition(
  !visualizationLayerShellSource.includes('<ModuleRenderer\n') || visualizationLayerShellSource.includes('activeIsGraphModule ? ('),
  'Visualization ModuleRenderer must be limited to graph modules',
)
assertCondition(
  visualizationLayerShellSource.includes('<span className={statusChipClass(runtime.status.api)}>')
    && !visualizationLayerShellSource.includes('onClick={() => runtime.navigateToModule(\'overviewData\')}'),
  'Visualization health chips must be non-interactive spans',
)

const i18nCatalogSource = readFile(files.i18nCatalog)
for (const key of [
  'visualization.statsTitle',
  'visualization.statsEmpty',
  'visualizationSection.stats',
  'visualizationSection.projectGraph',
  'visualizationSection.graphTemplates',
]) {
  const occurrences = i18nCatalogSource.split(`'${key}'`).length - 1
  assertCondition(occurrences === 3, `Visualization i18n key must exist in shape, zh-CN, and en-US catalogs: ${key}`)
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
assertCondition(
  extractAsConstObjectProperty(kernelTypesSource, 'KERNEL_RENDER_SHELL_MODE', 'admin') === 'admin',
  'KernelRenderShellMode must declare admin shell mode',
)
assertCondition(
  moduleRendererSource.includes('shellMode?: KernelRenderShellMode'),
  'ModuleRenderer must type shellMode as KernelRenderShellMode',
)
assertCondition(
  renderKernelModuleContentSource.includes('shellMode?: KernelRenderShellMode'),
  'Kernel module rendering must type shellMode as KernelRenderShellMode',
)
assertCondition(useKernelRuntimeSource.includes('buildLayerRouteHash(moduleKey)'), 'Kernel runtime navigation must use layered route hashes')

const summary = {
  status: failures.length === 0 ? 'ok' : 'failed',
  modules: moduleEntries.length,
  layer_counts: {
    A: modulesByLayer.A.length,
    B: modulesByLayer.B.length,
    C: modulesByLayer.C.length,
  },
  visualization_route_catalog: unique(modulesByLayer.B),
  visualization_current_nav: unique(visualizationNavKeys),
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

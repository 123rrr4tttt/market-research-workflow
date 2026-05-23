#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  adminLayerShell: 'src/app/kernel/AdminLayerShell.tsx',
  catalog: 'src/app/platform/i18n/catalog.ts',
  frontendKernelApp: 'src/app/kernel/FrontendKernelApp.tsx',
  layerSwitch: 'src/app/kernel/LayerSwitch.tsx',
  moduleChrome: 'src/app/kernel/moduleChrome.ts',
  moduleManifest: 'src/app/kernel/moduleManifest.ts',
  moduleRenderer: 'src/app/kernel/ModuleRenderer.tsx',
  renderKernelModuleContent: 'src/app/kernel/renderKernelModuleContent.tsx',
  visualizationLayerShell: 'src/app/kernel/VisualizationLayerShell.tsx',
  workbenchLayerShell: 'src/app/kernel/WorkbenchLayerShell.tsx',
}

const expectedSurfaceByLayer = {
  A: 'workbench',
  B: 'visualization',
  C: 'management',
}

const shellFileLayer = {
  [files.workbenchLayerShell]: 'A',
  [files.visualizationLayerShell]: 'B',
  [files.adminLayerShell]: 'C',
}

const sharedKernelFiles = new Set([
  files.frontendKernelApp,
  files.layerSwitch,
  files.moduleChrome,
  files.moduleManifest,
  files.moduleRenderer,
  files.renderKernelModuleContent,
])

const allowedProductAcronyms = new Set(['API', 'LLM', 'SEARCH', 'NEWS', 'DB', 'CODEX', 'MRW'])

const userFacingLiteralValues = new Set([
  'activate',
  'activate project',
  'inject template',
  'injecting',
  'login',
  'missing',
  'process home',
  'ready',
  'starting',
  'status matrix',
  'switching',
  'target project',
  'workbench',
])

const explicitGapProperties = new Set(['aria-label', 'label', 'placeholder', 'title'])
const technicalProps = new Set([
  'activeLayer',
  'channel',
  'className',
  'contract_version',
  'entryRoute',
  'idempotency_key',
  'item_id',
  'key',
  'kind',
  'legacyHash',
  'navGroupKey',
  'projectKey',
  'routePath',
  'shellMode',
  'surfaceKind',
  'type',
  'value',
  'variant',
])

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

function increment(map, key, count = 1) {
  map[key] = (map[key] || 0) + count
}

function buildLineStarts(source) {
  const starts = [0]
  for (let index = 0; index < source.length; index += 1) {
    if (source.charCodeAt(index) === 10) starts.push(index + 1)
  }
  return starts
}

function lineNumberAt(lineStarts, index) {
  let low = 0
  let high = lineStarts.length - 1
  while (low <= high) {
    const mid = Math.floor((low + high) / 2)
    if (lineStarts[mid] <= index) low = mid + 1
    else high = mid - 1
  }
  return high + 1
}

function lineAt(source, lineStarts, index) {
  const start = lineStarts[lineNumberAt(lineStarts, index) - 1]
  const end = source.indexOf('\n', index)
  return source.slice(start, end === -1 ? source.length : end)
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
      titleKey: `shell.title.${match[1]}`,
      navLabelKey: `navigation.item.${match[1]}`,
      navGroupKey: match[6],
    })
    match = pattern.exec(source)
  }
  if (entries.length === 0) fail('Could not read defineModule entries from moduleManifest')
  return entries
}

function extractRendererComponentPaths(source) {
  const importByComponent = new Map()
  const importPattern = /const\s+([A-Z][A-Za-z0-9_]*)\s*=\s*lazy\(\(\)\s*=>\s*import\('([^']+)'\)\)/g
  let importMatch = importPattern.exec(source)
  while (importMatch) {
    const componentName = importMatch[1]
    const importPath = importMatch[2]
    const resolved = path.normalize(path.join('src/app/kernel', importPath))
    importByComponent.set(componentName, resolved.endsWith('.tsx') ? resolved : `${resolved}.tsx`)
    importMatch = importPattern.exec(source)
  }

  const moduleToComponent = new Map()
  const bindingPattern = /if\s*\(\s*moduleKey\s*===\s*'([^']+)'\s*\)[\s\S]*?return\s*<([A-Z][A-Za-z0-9_]*)/g
  let bindingMatch = bindingPattern.exec(source)
  while (bindingMatch) {
    moduleToComponent.set(bindingMatch[1], bindingMatch[2])
    bindingMatch = bindingPattern.exec(source)
  }

  const moduleToFile = new Map()
  for (const [moduleKey, componentName] of moduleToComponent.entries()) {
    const relPath = importByComponent.get(componentName)
    if (!relPath) fail(`Renderer component ${componentName} for ${moduleKey} has no lazy import`)
    else moduleToFile.set(moduleKey, relPath)
  }
  return moduleToFile
}

function extractCatalogKeys(source) {
  const keys = new Set()
  const namespacePattern = /(?:shell|navigation|settings|settingsPage|shared|agentChat|projects|catalogPage|rawDataPage|policyPage|opsPage|dashboardPage|ingestPage|graphPage|processPage|crawlerManagePage|resourcePage|llmDesignerPage|writingWorkbenchPage):\s*\{([\s\S]*?)\n\s*\}/g
  let namespaceMatch = namespacePattern.exec(source)
  while (namespaceMatch) {
    const namespaceText = namespaceMatch[0]
    const namespaceName = namespaceText.slice(0, namespaceText.indexOf(':')).trim()
    const keyPattern = /'([^']+)'\s*:/g
    let keyMatch = keyPattern.exec(namespaceText)
    while (keyMatch) {
      keys.add(`${namespaceName}.${keyMatch[1]}`)
      keyMatch = keyPattern.exec(namespaceText)
    }
    namespaceMatch = namespacePattern.exec(source)
  }
  if (keys.size === 0) fail('Could not read MESSAGE_KEY_SHAPE catalog keys')
  return keys
}

function extractStringLiterals(source, lineStarts) {
  const literals = []
  for (let index = 0; index < source.length; index += 1) {
    const quote = source[index]
    if (quote !== '\'' && quote !== '"' && quote !== '`') continue

    const start = index
    let value = ''
    index += 1
    while (index < source.length) {
      const char = source[index]
      if (char === '\\') {
        value += source[index + 1] || ''
        index += 2
        continue
      }
      if (char === quote) break
      value += char
      index += 1
    }
    literals.push({
      kind: quote === '`' ? 'template' : 'string',
      value,
      start,
      end: index + 1,
      line: lineNumberAt(lineStarts, start),
      lineText: lineAt(source, lineStarts, start).trim(),
    })
  }
  return literals
}

function extractJsxText(source, lineStarts, literalSpans) {
  const chars = Array.from(source)
  for (const span of literalSpans) {
    for (let index = span.start; index < span.end; index += 1) {
      chars[index] = ' '
    }
  }

  const masked = chars.join('')
  const nodes = []
  let index = 0
  while (index < masked.length) {
    const start = masked.indexOf('>', index)
    if (start === -1) break
    const end = masked.indexOf('<', start + 1)
    if (end === -1) break
    index = end + 1

    const tagOpen = masked.lastIndexOf('<', start)
    const tagText = tagOpen === -1 ? '' : masked.slice(tagOpen, start + 1).trim()
    const beforeTagText = masked.slice(Math.max(0, tagOpen - 24), tagOpen)
    const beforeTagChar = beforeTagText.trimEnd().slice(-1)
    const followsExpressionLikeToken = /[A-Za-z0-9_$\])]/.test(beforeTagChar) && !/\breturn\s*$/.test(beforeTagText)
    const isLikelyOpeningJsxTag =
      tagText === '<>' ||
      /^<\s*[A-Za-z][A-Za-z0-9_.:-]*(?:\s|>|\/)/.test(tagText)
    if (followsExpressionLikeToken || !isLikelyOpeningJsxTag || /^<\s*\//.test(tagText)) continue

    const body = masked.slice(start + 1, end)
    if (body.includes('{') || body.includes('}')) continue
    const raw = body.replace(/\s+/g, ' ').trim()
    if (!raw) continue
    if (!/[A-Za-z\u4e00-\u9fff]/.test(raw)) continue
    nodes.push({
      kind: 'jsx_text',
      value: raw,
      start: start + 1,
      end,
      line: lineNumberAt(lineStarts, start + 1),
      lineText: lineAt(source, lineStarts, start + 1).trim(),
    })
  }
  return nodes
}

function isImportOrPathLiteral(value, before) {
  if (/(?:from\s*|import\s*\(|lazy\(\(\)\s*=>\s*import\()$/.test(before)) return true
  if (/^(\.{1,2}\/|\/|#|https?:\/\/|about:)/.test(value)) return true
  if (/\.(md|png|svg|ts|tsx|js|jsx|css|html)$/.test(value)) return true
  return false
}

function isCssLiteral(value, before) {
  if (/className\s*=\s*$/.test(before) || /className\s*=\s*\{\s*$/.test(before)) return true
  if (/className\s*[:=][^'"]*$/.test(before)) return true
  if (/^[a-z0-9_-]+(?:\s+[a-z0-9_-]+)*$/.test(value) && /(?:__|--|is-|chip|kernel-|figma-|graph-|writing-|node-|toolbar|page|card)/.test(value)) {
    return true
  }
  return false
}

function isCssValueLiteral(value, propName) {
  if (!/^(?:transform|width|maxHeight|minHeight|height|left|right|top|bottom|margin|padding|gap|zIndex|overflow|display|position)$/.test(propName)) {
    return false
  }
  if (/^(?:translate|scale|rotate|calc|min|max|clamp|rgb|rgba|hsl|hsla)\(/.test(value)) return true
  if (/^-?\d+(?:\.\d+)?(?:px|rem|em|vh|vw|%)$/.test(value)) return true
  if (/^(?:auto|fixed|absolute|relative|sticky|hidden|visible|scroll|inline-flex|flex|grid|block|none)$/.test(value)) return true
  return false
}

function isCssPrimitiveLiteral(value) {
  if (/^(?:rgb|rgba|hsl|hsla)\([^)]+\)$/.test(value)) return true
  if (/^(?:-?\d+(?:\.\d+)?px|0)(?:\s+(?:-?\d+(?:\.\d+)?px|0)){1,3}$/.test(value)) return true
  if (/^[a-z0-9_-]+:(?:before|after)$/.test(value)) return true
  return false
}

function propNameBeforeLiteral(before) {
  const attrMatch = before.match(/([A-Za-z0-9_-]+)\s*=\s*\{?\s*$/)
  if (attrMatch) return attrMatch[1]
  const propMatch = before.match(/([A-Za-z0-9_-]+)\s*:\s*$/)
  if (propMatch) return propMatch[1]
  return ''
}

function isDefineModuleSurfaceKindLiteral(value, before) {
  if (!/^(workbench|visualization|management)$/.test(value)) return false
  return /defineModule\(\s*'[^']+'\s*,\s*'[ABC]'\s*,\s*$/.test(before)
}

function isCatalogKey(value) {
  return /^(shell|navigation|settings|settingsPage|shared|agentChat|projects|catalogPage|rawDataPage|policyPage|opsPage|dashboardPage|ingestPage|graphPage|processPage|crawlerManagePage|resourcePage|llmDesignerPage|writingWorkbenchPage)\.[A-Za-z0-9_.-]+$/.test(value)
}

function isModuleOrRouteToken(value) {
  if (value.length > 120) return false
  if (/^[ABC]$/.test(value)) return true
  if (/^(workbench|visualization|management)$/.test(value)) return true
  if (/^[A-Za-z][A-Za-z0-9_]*$/.test(value)) return true
  if (/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value)) return true
  if (/^[a-z0-9_]+(?:\.[a-z0-9_]+)*$/.test(value)) return true
  return false
}

function isEventOrEnumToken(value) {
  if (/^(?:approval|skill|coordinator)\.(?:[a-z0-9_]+\.?)*$/.test(value)) return true
  if (/^[a-z]+(?:_[a-z0-9]+)+(?:\.[a-z0-9_]+)*$/.test(value)) return true
  return false
}

function isGraphTaxonomyToken(value) {
  if (value.length > 80) return false
  if (/^(?:Company|Product|Operation|Policy|State|PolicyType|KeyPoint|Entity|Post|Keyword|Topic|TopicTag|SentimentTag|User|Subreddit|MarketData|Segment|Game)$/.test(value)) return true
  if (/^(?:Company|Product|Operation)[A-Z][A-Za-z0-9]*$/.test(value)) return true
  if (/^(?:circle|rect|roundRect|triangle|diamond|pin|arrow|emptyCircle|emptyRect|emptyRoundRect|emptyDiamond|emptyTriangle|emptyPin|convexStar)$/.test(value)) return true
  return false
}

function isTechnicalTemplateLiteral(value, before) {
  if (!value.includes('${')) return false
  if (/^: ''\}\$\{/.test(value)) return true
  if (/(?:\bid\s*:|\bkey\s*:|key\s*=\s*\{|getAgentEventKey|streamBySession|EventSource\()/.test(before)) return true
  if (/^graphpage[-.]/.test(value)) return true
  if (/^hsl\(\$\{[^}]+\}/.test(value)) return true
  if (/^rgba\(/.test(value)) return true
  if (/^v-\$\{/.test(value)) return true
  if (/^:\$\{looseId\}/.test(value)) return true
  if (/^\$\{resolved\./.test(value)) return true
  if (/^\$\{raw\.slice\(/.test(value)) return true
  if (/^\$\{String\(item\.action/.test(value)) return true
  if (/graphVariantLabel|edgeLegendLabel|edgeStrokeLabel/.test(value)) return true
  if (/t\('graphPage\./.test(value)) return true
  if (/String\(edge\./.test(value)) return true
  if (/^\$\{[^}]+\}(?:[-:/?&=.A-Za-z0-9_ ]+\$\{[^}]+\})*[-:/?&=.A-Za-z0-9_ ]*$/.test(value)) return true
  if (/\$\{[^}]+\}\.\.\.$/.test(value)) return true
  if (/\$\{[^}]+\}\s*-\$\{[^}]+\}->\s*\$\{[^}]+\}/.test(value)) return true
  if (/^\$\{labels\.[^}]+\}/.test(value) || /^\$\{labels\w*\.[^}]+\}/.test(value)) return true
  return false
}

function isOperationalStatusLiteral(value) {
  if (/^(?:submit|audit|rollback|handoff|sync|draft|report)_/.test(value)) return true
  if (/^(?:expected|latest)=/.test(value)) return true
  if (/^r\$\{/.test(value)) return true
  if (/^missing_api_method:/.test(value)) return true
  if (/^graphpage\.[a-z0-9_.-]+$/.test(value)) return true
  return false
}

function looksHumanFacing(value) {
  const trimmed = value.trim()
  if (!trimmed) return false
  if (/[\u4e00-\u9fff]/.test(trimmed)) return true
  if (userFacingLiteralValues.has(trimmed)) return true
  if (/\s/.test(trimmed) && /[A-Za-z]/.test(trimmed)) return true
  if (/^[A-Z][a-z]+(?:[A-Z][a-z]+)*$/.test(trimmed)) return true
  if (/[.!?。？！:：；，]/.test(trimmed) && /[A-Za-z\u4e00-\u9fff]/.test(trimmed)) return true
  return false
}

function classifyOccurrence(occurrence, source, relPath) {
  const value = occurrence.value.replace(/\s+/g, ' ').trim()
  const before = source.slice(Math.max(0, occurrence.start - 140), occurrence.start)
  const after = source.slice(occurrence.end, Math.min(source.length, occurrence.end + 140))
  const propName = propNameBeforeLiteral(before)

  if (!value) return { bucket: 'ignored', category: 'empty' }
  if (/^\s*\/\//.test(occurrence.lineText)) return { bucket: 'ignored', category: 'comment_literal' }
  if (relPath === files.catalog) return { bucket: 'allowed', category: 'localized_catalog' }
  if (allowedProductAcronyms.has(value)) return { bucket: 'allowed', category: 'product_acronym' }
  if (isImportOrPathLiteral(value, before)) return { bucket: 'allowed', category: 'import_path_or_route' }
  if (isCssLiteral(value, before)) return { bucket: 'allowed', category: 'css_selector_or_class' }
  if (isDefineModuleSurfaceKindLiteral(value, before)) return { bucket: 'allowed', category: 'technical_prop:surfaceKind' }
  if (isCatalogKey(value)) return { bucket: 'allowed', category: 'i18n_catalog_key' }
  if (technicalProps.has(propName)) return { bucket: 'allowed', category: `technical_prop:${propName}` }
  if (isCssValueLiteral(value, propName)) return { bucket: 'allowed', category: 'css_value' }
  if (isCssPrimitiveLiteral(value)) return { bucket: 'allowed', category: 'css_value' }
  if (/^path:\/\/[A-Za-z0-9 .,-]+$/.test(value)) return { bucket: 'allowed', category: 'chart_symbol_path' }
  if (isEventOrEnumToken(value)) return { bucket: 'allowed', category: 'event_or_enum_token' }
  if (relPath.endsWith('/GraphPage.tsx') && isGraphTaxonomyToken(value)) return { bucket: 'allowed', category: 'graph_taxonomy_token' }
  if (isTechnicalTemplateLiteral(value, before)) return { bucket: 'allowed', category: 'technical_template_literal' }
  if (isOperationalStatusLiteral(value)) return { bucket: 'allowed', category: 'operational_status_literal' }
  if (/^(true|false|null|undefined)$/.test(value)) return { bucket: 'allowed', category: 'language_literal' }
  if (/^#[0-9a-fA-F]{3,8}$/.test(value)) return { bucket: 'allowed', category: 'color_token' }
  if (/^[0-9.:-]+$/.test(value)) return { bucket: 'allowed', category: 'numeric_or_punctuation' }

  const visibleContext =
    occurrence.kind === 'jsx_text' ||
    explicitGapProperties.has(propName) ||
    /(?:setMessage|window\.confirm|alert|console\.warn)\s*\([^)]*$/.test(before) ||
    /\?\s*$/.test(before) ||
    /^(\s*:\s*)/.test(after)

  if (visibleContext && looksHumanFacing(value)) {
    return { bucket: 'remaining_gap', category: propName ? `visible_${propName}` : `visible_${occurrence.kind}` }
  }
  if (looksHumanFacing(value)) return { bucket: 'remaining_gap', category: 'human_text_literal' }
  if (isModuleOrRouteToken(value)) return { bucket: 'allowed', category: 'module_or_enum_token' }
  return { bucket: 'allowed', category: 'other_technical_literal' }
}

function surfaceForFile(relPath, modulesByFile) {
  const shellLayer = shellFileLayer[relPath]
  if (shellLayer) {
    return {
      layerIds: [shellLayer],
      surfaceKinds: [expectedSurfaceByLayer[shellLayer]],
      moduleKeys: [],
    }
  }
  if (sharedKernelFiles.has(relPath)) {
    return {
      layerIds: ['shared'],
      surfaceKinds: ['kernel'],
      moduleKeys: [],
    }
  }

  const modules = modulesByFile.get(relPath) || []
  return {
    layerIds: unique(modules.map((entry) => entry.layerId)),
    surfaceKinds: unique(modules.map((entry) => entry.surfaceKind)),
    moduleKeys: modules.map((entry) => entry.moduleKey),
  }
}

function scanFile(relPath, modulesByFile) {
  const source = readFile(relPath)
  const lineStarts = buildLineStarts(source)
  const stringLiterals = extractStringLiterals(source, lineStarts)
  const jsxText = relPath.endsWith('.tsx') ? extractJsxText(source, lineStarts, stringLiterals) : []
  const occurrences = [...stringLiterals, ...jsxText]
  const surface = surfaceForFile(relPath, modulesByFile)

  return occurrences
    .map((occurrence) => ({
      ...occurrence,
      relPath,
      value: occurrence.value.replace(/\s+/g, ' ').trim(),
      classification: classifyOccurrence(occurrence, source, relPath),
      layerIds: surface.layerIds,
      surfaceKinds: surface.surfaceKinds,
      moduleKeys: surface.moduleKeys,
    }))
    .filter((occurrence) => occurrence.classification.bucket !== 'ignored')
}

function compareSets(label, expected, actual) {
  const expectedSet = new Set(expected)
  const actualSet = new Set(actual)
  const missing = expected.filter((item) => !actualSet.has(item))
  const extra = actual.filter((item) => !expectedSet.has(item))
  if (missing.length > 0) fail(`${label} missing: ${missing.join(', ')}`)
  if (extra.length > 0) fail(`${label} extra: ${extra.join(', ')}`)
}

function sampleOccurrences(occurrences, limit = 20) {
  return occurrences.slice(0, limit).map((item) => ({
    file: item.relPath,
    line: item.line,
    value: item.value,
    category: item.classification.category,
    layerIds: item.layerIds,
    surfaceKinds: item.surfaceKinds,
    moduleKeys: item.moduleKeys.slice(0, 5),
  }))
}

const moduleManifestSource = readFile(files.moduleManifest)
const renderKernelModuleContentSource = readFile(files.renderKernelModuleContent)
const catalogSource = readFile(files.catalog)

const moduleEntries = extractModuleManifest(moduleManifestSource)
const catalogKeys = extractCatalogKeys(catalogSource)
const moduleToFile = extractRendererComponentPaths(renderKernelModuleContentSource)
const moduleEntryByKey = new Map(moduleEntries.map((entry) => [entry.moduleKey, entry]))
const moduleKeys = moduleEntries.map((entry) => entry.moduleKey)

for (const entry of moduleEntries) {
  assertCondition(
    entry.surfaceKind === expectedSurfaceByLayer[entry.layerId],
    `moduleManifest ${entry.moduleKey} layer ${entry.layerId} must use ${expectedSurfaceByLayer[entry.layerId]} surface`,
  )
  assertCondition(catalogKeys.has(entry.titleKey), `Missing catalog key ${entry.titleKey}`)
  assertCondition(catalogKeys.has(entry.navLabelKey), `Missing catalog key ${entry.navLabelKey}`)
  assertCondition(catalogKeys.has(entry.navGroupKey), `Missing catalog key ${entry.navGroupKey}`)
}

compareSets('renderKernelModuleContent module bindings', moduleKeys, Array.from(moduleToFile.keys()))

const modulesByFile = new Map()
for (const [moduleKey, relPath] of moduleToFile.entries()) {
  const entry = moduleEntryByKey.get(moduleKey)
  if (!entry) continue
  const current = modulesByFile.get(relPath) || []
  current.push(entry)
  modulesByFile.set(relPath, current)
}

const scanTargets = unique([...Object.values(files), ...Array.from(modulesByFile.keys())])
for (const relPath of scanTargets) {
  assertCondition(fs.existsSync(path.join(rootDir, relPath)), `Missing scan target ${relPath}`)
}

const findings = scanTargets.flatMap((relPath) => scanFile(relPath, modulesByFile))
const allowedFindings = findings.filter((item) => item.classification.bucket === 'allowed')
const remainingGaps = findings.filter((item) => item.classification.bucket === 'remaining_gap')

const allowedByCategory = countValues(allowedFindings.map((item) => item.classification.category))
const gapsByCategory = countValues(remainingGaps.map((item) => item.classification.category))
const gapsByFile = countValues(remainingGaps.map((item) => item.relPath))
const gapsByLayer = {}
const gapsBySurface = {}
for (const gap of remainingGaps) {
  for (const layerId of gap.layerIds.length > 0 ? gap.layerIds : ['unmapped']) increment(gapsByLayer, layerId)
  for (const surfaceKind of gap.surfaceKinds.length > 0 ? gap.surfaceKinds : ['unmapped']) increment(gapsBySurface, surfaceKind)
}

const modulesByLayer = {
  A: moduleEntries.filter((entry) => entry.layerId === 'A').map((entry) => entry.moduleKey),
  B: moduleEntries.filter((entry) => entry.layerId === 'B').map((entry) => entry.moduleKey),
  C: moduleEntries.filter((entry) => entry.layerId === 'C').map((entry) => entry.moduleKey),
}

const componentFilesByLayer = {}
for (const layerId of Object.keys(modulesByLayer)) {
  componentFilesByLayer[layerId] = unique(
    moduleEntries
      .filter((entry) => entry.layerId === layerId)
      .map((entry) => moduleToFile.get(entry.moduleKey))
      .filter(Boolean),
  )
}

const summary = {
  status: failures.length === 0 ? 'ok' : 'failed',
  gate_type: 'audit_readiness',
  full_business_string_migration_complete: remainingGaps.length === 0,
  modules: moduleEntries.length,
  checked_files: scanTargets,
  layer_surface_coverage: {
    A: {
      surface: expectedSurfaceByLayer.A,
      modules: modulesByLayer.A.length,
      component_files: componentFilesByLayer.A.length,
    },
    B: {
      surface: expectedSurfaceByLayer.B,
      modules: modulesByLayer.B.length,
      component_files: componentFilesByLayer.B.length,
    },
    C: {
      surface: expectedSurfaceByLayer.C,
      modules: modulesByLayer.C.length,
      component_files: componentFilesByLayer.C.length,
    },
  },
  known_allowed_literals: {
    total: allowedFindings.length,
    by_category: allowedByCategory,
    samples: sampleOccurrences(allowedFindings, 12),
  },
  remaining_migration_gaps: {
    total: remainingGaps.length,
    by_category: gapsByCategory,
    by_layer: gapsByLayer,
    by_surface: gapsBySurface,
    by_file: gapsByFile,
    samples: sampleOccurrences(remainingGaps, 40),
  },
  readiness_notes: [
    'This gate proves scan coverage, catalog anchoring, and classified string inventory for selected kernel/module surfaces.',
    remainingGaps.length === 0
      ? 'No remaining business string migration gaps were found in the selected kernel/module surfaces.'
      : 'Remaining migration gaps are reported but do not fail the gate; they are the input list for future page-level i18n migration.',
    'The gate is dependency-light and does not replace browser visual verification or full page refactor acceptance.',
  ],
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}

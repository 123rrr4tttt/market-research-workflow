#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const EXPECTED_THEME_GROUPS = [
  'background',
  'surface',
  'border',
  'text',
  'accent',
  'status',
  'interactive',
]

const files = {
  appShell: 'src/app/shell/AppShell.tsx',
  baselineInventory: 'src/app/topology/baselineInventory.ts',
  catalog: 'src/app/platform/i18n/catalog.ts',
  figmaSideNav: 'src/components/FigmaSideNav.tsx',
  kernelTypes: 'src/app/kernel/types.ts',
  moduleManifest: 'src/app/kernel/moduleManifest.ts',
  pagePlacement: 'src/app/topology/pagePlacementMatrix.ts',
  sharedContract: 'src/app/topology/sharedPlatformContract.ts',
  themeTokens: 'src/app/platform/theme/tokens.ts',
  themeTypes: 'src/app/platform/theme/types.ts',
  topologyContracts: 'src/app/topology/contracts.ts',
}

const failures = []

function readFile(relPath) {
  return fs.readFileSync(path.join(rootDir, relPath), 'utf8')
}

function parseFile(relPath) {
  const fullPath = path.join(rootDir, relPath)
  return ts.createSourceFile(fullPath, fs.readFileSync(fullPath, 'utf8'), ts.ScriptTarget.Latest, true)
}

function fail(message) {
  failures.push(message)
}

function assertCondition(condition, message) {
  if (!condition) fail(message)
}

function unwrap(node) {
  let current = node
  while (
    ts.isAsExpression(current) ||
    ts.isTypeAssertionExpression(current) ||
    ts.isParenthesizedExpression(current) ||
    (ts.isSatisfiesExpression && ts.isSatisfiesExpression(current))
  ) {
    current = current.expression
  }
  return current
}

function propertyNameToString(name) {
  if (!name) return ''
  if (ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)) return name.text
  return ''
}

function findVariableInitializer(sourceFile, variableName) {
  let initializer = null
  sourceFile.forEachChild((node) => {
    if (!ts.isVariableStatement(node)) return
    for (const declaration of node.declarationList.declarations) {
      if (ts.isIdentifier(declaration.name) && declaration.name.text === variableName) {
        initializer = declaration.initializer ? unwrap(declaration.initializer) : null
      }
    }
  })
  return initializer
}

function extractConstStringArray(sourceFile, variableName) {
  const initializer = findVariableInitializer(sourceFile, variableName)
  if (!initializer || !ts.isArrayLiteralExpression(initializer)) {
    fail(`Could not read array ${variableName}`)
    return []
  }
  return initializer.elements
    .map((element) => unwrap(element))
    .filter(ts.isStringLiteral)
    .map((element) => element.text)
}

function extractStringUnion(sourceFile, typeName) {
  let values = []
  sourceFile.forEachChild((node) => {
    if (!ts.isTypeAliasDeclaration(node) || node.name.text !== typeName) return
    if (!ts.isUnionTypeNode(node.type)) {
      fail(`${typeName} is not a string literal union`)
      return
    }
    values = node.type.types
      .filter(ts.isLiteralTypeNode)
      .map((item) => item.literal)
      .filter(ts.isStringLiteral)
      .map((literal) => literal.text)
  })
  if (values.length === 0) fail(`Could not read union ${typeName}`)
  return values
}

function extractObjectLiteralProperties(objectNode) {
  if (!objectNode || !ts.isObjectLiteralExpression(objectNode)) return []
  return objectNode.properties
    .filter(ts.isPropertyAssignment)
    .map((property) => ({ key: propertyNameToString(property.name), value: unwrap(property.initializer) }))
    .filter((property) => property.key)
}

function extractNestedCatalog(sourceFile, variableName) {
  const initializer = findVariableInitializer(sourceFile, variableName)
  const namespaces = new Map()
  for (const namespaceProperty of extractObjectLiteralProperties(initializer)) {
    if (!ts.isObjectLiteralExpression(namespaceProperty.value)) continue
    const messages = new Map()
    for (const messageProperty of extractObjectLiteralProperties(namespaceProperty.value)) {
      if (ts.isStringLiteral(messageProperty.value)) {
        messages.set(messageProperty.key, messageProperty.value.text)
      }
    }
    namespaces.set(namespaceProperty.key, messages)
  }
  if (namespaces.size === 0) fail(`Could not read catalog ${variableName}`)
  return namespaces
}

function hasCatalogKey(catalog, namespacedKey) {
  const [namespace, ...parts] = namespacedKey.split('.')
  const key = parts.join('.')
  const value = catalog.get(namespace)?.get(key)
  return typeof value === 'string' && value.trim().length > 0
}

function extractModuleManifest(sourceFile) {
  const initializer = findVariableInitializer(sourceFile, 'moduleManifest')
  if (!initializer || !ts.isArrayLiteralExpression(initializer)) {
    fail('Could not read moduleManifest')
    return []
  }
  const entries = []
  for (const element of initializer.elements) {
    const call = unwrap(element)
    if (!ts.isCallExpression(call)) {
      fail('moduleManifest must contain defineModule calls only')
      continue
    }
    const args = call.arguments.map((arg) => unwrap(arg))
    const stringArg = (index) => (ts.isStringLiteral(args[index]) ? args[index].text : '')
    entries.push({
      moduleKey: stringArg(0),
      layerId: stringArg(1),
      surfaceKind: stringArg(2),
      entryRoute: stringArg(3),
      legacyHash: stringArg(4),
      navGroupKey: stringArg(5),
    })
  }
  return entries
}

function extractPageRecords(sourceFile, variableName) {
  const initializer = findVariableInitializer(sourceFile, variableName)
  if (!initializer || !ts.isArrayLiteralExpression(initializer)) {
    fail(`Could not read page record array ${variableName}`)
    return []
  }
  return initializer.elements
    .map((element) => unwrap(element))
    .filter(ts.isObjectLiteralExpression)
    .map((record) => {
      const props = new Map(extractObjectLiteralProperties(record).map((property) => [property.key, property.value]))
      const pageValue = props.get('page')
      const surfaceValue = props.get('phase1Surface') || props.get('defaultSurface')
      const navModesValue = props.get('navModes')
      return {
        page: ts.isStringLiteral(pageValue) ? pageValue.text : '',
        surface: ts.isStringLiteral(surfaceValue) ? surfaceValue.text : '',
        navModes: ts.isArrayLiteralExpression(navModesValue)
          ? navModesValue.elements
              .map((item) => unwrap(item))
              .filter(ts.isStringLiteral)
              .map((item) => item.text)
          : [],
      }
    })
}

function extractObjectKeys(sourceFile, variableName) {
  const initializer = findVariableInitializer(sourceFile, variableName)
  return extractObjectLiteralProperties(initializer).map((property) => property.key)
}

function extractObjectArrayPropertyValues(sourceFile, variableName, propertyName) {
  const initializer = findVariableInitializer(sourceFile, variableName)
  if (!initializer || !ts.isArrayLiteralExpression(initializer)) {
    fail(`Could not read object array ${variableName}`)
    return []
  }
  return initializer.elements
    .map((element) => unwrap(element))
    .filter(ts.isObjectLiteralExpression)
    .map((record) => {
      const props = new Map(extractObjectLiteralProperties(record).map((property) => [property.key, property.value]))
      const value = props.get(propertyName)
      return ts.isStringLiteral(value) ? value.text : ''
    })
    .filter(Boolean)
}

function extractThemeTokenGroups(sourceFile) {
  const initializer = findVariableInitializer(sourceFile, 'THEME_TOKENS')
  const result = new Map()
  for (const themeProperty of extractObjectLiteralProperties(initializer)) {
    if (!ts.isObjectLiteralExpression(themeProperty.value)) continue
    result.set(themeProperty.key, extractObjectLiteralProperties(themeProperty.value).map((property) => property.key))
  }
  if (result.size === 0) fail('Could not read THEME_TOKENS')
  return result
}

function compareSets(label, expected, actual) {
  const expectedSet = new Set(expected)
  const actualSet = new Set(actual)
  const missing = expected.filter((item) => !actualSet.has(item))
  const extra = actual.filter((item) => !expectedSet.has(item))
  if (missing.length > 0) fail(`${label} missing: ${missing.join(', ')}`)
  if (extra.length > 0) fail(`${label} extra: ${extra.join(', ')}`)
}

function countValues(values) {
  return values.reduce((acc, value) => {
    acc[value] = (acc[value] || 0) + 1
    return acc
  }, {})
}

const kernelTypes = parseFile(files.kernelTypes)
const moduleManifestFile = parseFile(files.moduleManifest)
const pagePlacementFile = parseFile(files.pagePlacement)
const baselineInventoryFile = parseFile(files.baselineInventory)
const catalogFile = parseFile(files.catalog)
const themeTypesFile = parseFile(files.themeTypes)
const themeTokensFile = parseFile(files.themeTokens)
const sharedContractFile = parseFile(files.sharedContract)
const topologyContractsFile = parseFile(files.topologyContracts)

const kernelModes = extractStringUnion(kernelTypes, 'KernelModuleKey')
const navGroupKeys = extractConstStringArray(kernelTypes, 'MODULE_NAV_GROUP_KEYS')
const moduleEntries = extractModuleManifest(moduleManifestFile)
const manifestModes = moduleEntries.map((entry) => entry.moduleKey)
const placementRecords = extractPageRecords(pagePlacementFile, 'PAGE_PLACEMENT_BASELINE')
const baselineRecords = extractPageRecords(baselineInventoryFile, 'BASELINE_PAGE_INVENTORY')
const placementModes = placementRecords.flatMap((record) => record.navModes)
const baselineModes = baselineRecords.flatMap((record) => record.navModes)
const zhCNMessages = extractNestedCatalog(catalogFile, 'zhCNMessages')
const enUSMessages = extractNestedCatalog(catalogFile, 'enUSMessages')
const appThemes = extractConstStringArray(themeTypesFile, 'APP_THEMES')
const themeTokenGroups = extractThemeTokenGroups(themeTokensFile)
const sharedCapabilityIds = extractObjectArrayPropertyValues(sharedContractFile, 'SHARED_PLATFORM_CAPABILITIES', 'id')
const topologyScopeKeys = extractObjectKeys(topologyContractsFile, 'TOPOLOGY_SCOPE')

compareSets('KernelModuleKey vs moduleManifest', kernelModes, manifestModes)
compareSets('KernelModuleKey vs PAGE_PLACEMENT_BASELINE', kernelModes, placementModes)
compareSets('KernelModuleKey vs BASELINE_PAGE_INVENTORY', kernelModes, baselineModes)

for (const [mode, count] of Object.entries(countValues(placementModes))) {
  if (count !== 1) fail(`PAGE_PLACEMENT_BASELINE mode appears ${count} times: ${mode}`)
}
for (const [mode, count] of Object.entries(countValues(baselineModes))) {
  if (count !== 1) fail(`BASELINE_PAGE_INVENTORY mode appears ${count} times: ${mode}`)
}

const placementByMode = new Map()
for (const record of placementRecords) {
  for (const mode of record.navModes) placementByMode.set(mode, record.surface)
}
for (const record of baselineRecords) {
  for (const mode of record.navModes) {
    const placementSurface = placementByMode.get(mode)
    if (placementSurface !== record.surface) {
      fail(`Baseline inventory surface mismatch for ${mode}: ${record.surface} != ${placementSurface}`)
    }
  }
}

for (const entry of moduleEntries) {
  assertCondition(kernelModes.includes(entry.moduleKey), `Unknown moduleManifest moduleKey: ${entry.moduleKey}`)
  assertCondition(navGroupKeys.includes(entry.navGroupKey), `Unknown nav group for ${entry.moduleKey}: ${entry.navGroupKey}`)
  assertCondition(entry.entryRoute.startsWith('/'), `entryRoute must start with / for ${entry.moduleKey}`)
  assertCondition(entry.legacyHash.startsWith('#'), `legacyHash must start with # for ${entry.moduleKey}`)
  assertCondition(hasCatalogKey(zhCNMessages, `shell.title.${entry.moduleKey}`), `zh-CN missing shell title for ${entry.moduleKey}`)
  assertCondition(hasCatalogKey(enUSMessages, `shell.title.${entry.moduleKey}`), `en-US missing shell title for ${entry.moduleKey}`)
  assertCondition(hasCatalogKey(zhCNMessages, `navigation.item.${entry.moduleKey}`), `zh-CN missing nav item for ${entry.moduleKey}`)
  assertCondition(hasCatalogKey(enUSMessages, `navigation.item.${entry.moduleKey}`), `en-US missing nav item for ${entry.moduleKey}`)
  assertCondition(hasCatalogKey(zhCNMessages, entry.navGroupKey), `zh-CN missing nav group ${entry.navGroupKey}`)
  assertCondition(hasCatalogKey(enUSMessages, entry.navGroupKey), `en-US missing nav group ${entry.navGroupKey}`)
}

compareSets('APP_THEMES vs THEME_TOKENS', appThemes, Array.from(themeTokenGroups.keys()))
for (const theme of appThemes) {
  compareSets(`THEME_TOKENS.${theme}`, EXPECTED_THEME_GROUPS, themeTokenGroups.get(theme) || [])
}

assertCondition(sharedCapabilityIds.includes('theme-i18n'), 'Shared platform contract must include theme-i18n capability')
assertCondition(topologyScopeKeys.includes('baseline'), 'TOPOLOGY_SCOPE must include baseline')
assertCondition(topologyScopeKeys.includes('interpretation'), 'TOPOLOGY_SCOPE must include interpretation')
assertCondition(topologyScopeKeys.includes('nonGoals'), 'TOPOLOGY_SCOPE must include nonGoals')

const appShellSource = readFile(files.appShell)
const figmaSideNavSource = readFile(files.figmaSideNav)
assertCondition(appShellSource.includes('useAppLocale()'), 'AppShell must consume useAppLocale')
assertCondition(appShellSource.includes('useAppTheme()'), 'AppShell must consume useAppTheme')
assertCondition(appShellSource.includes('applyThemeTokens(appTheme)'), 'AppShell must apply theme tokens')
assertCondition(appShellSource.includes('getModuleDescriptor(viewMode).titleKey'), 'AppShell title must resolve through module descriptors')
assertCondition(figmaSideNavSource.includes('getModulesByGroup'), 'FigmaSideNav must read module registry by group')
assertCondition(figmaSideNavSource.includes('resolveInteractionSurface(item.mode) === surface'), 'FigmaSideNav must filter modules by interaction surface')
assertCondition(figmaSideNavSource.includes('translate(locale, item.navLabelKey'), 'FigmaSideNav labels must resolve through i18n keys')

const summary = {
  status: failures.length === 0 ? 'ok' : 'failed',
  modules: kernelModes.length,
  manifest_entries: moduleEntries.length,
  placement_records: placementRecords.length,
  baseline_inventory_records: baselineRecords.length,
  topology_surfaces: {
    management: placementModes.filter((mode) => placementByMode.get(mode) === 'management').length,
    workbench: placementModes.filter((mode) => placementByMode.get(mode) === 'workbench').length,
  },
  i18n_locales: ['zh-CN', 'en-US'],
  nav_groups: navGroupKeys.length,
  themes: appThemes,
  theme_token_groups: EXPECTED_THEME_GROUPS,
  checked_files: Object.values(files),
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}

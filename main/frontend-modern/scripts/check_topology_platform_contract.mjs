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

const EXPECTED_THEME_TOKEN_LEAVES = {
  background: ['app', 'subtle'],
  surface: ['base', 'raised'],
  border: ['default', 'strong'],
  text: ['primary', 'secondary'],
  accent: ['primary', 'contrast'],
  status: ['success', 'warning', 'danger'],
  interactive: ['hover', 'focus', 'active'],
}

const files = {
  appShell: 'src/app/shell/AppShell.tsx',
  baselineInventory: 'src/app/topology/baselineInventory.ts',
  catalog: 'src/app/platform/i18n/catalog.ts',
  figmaSideNav: 'src/components/FigmaSideNav.tsx',
  kernelTypes: 'src/app/kernel/types.ts',
  legacyHashAdapter: 'src/app/kernel/legacyHashAdapter.ts',
  localeStore: 'src/app/platform/i18n/store.ts',
  localeTypes: 'src/app/platform/i18n/types.ts',
  moduleManifest: 'src/app/kernel/moduleManifest.ts',
  navigationIndex: 'src/app/navigation/index.ts',
  pagePlacement: 'src/app/topology/pagePlacementMatrix.ts',
  registry: 'src/app/platform/modules/registry.ts',
  settingsPage: 'src/pages/SettingsPage.tsx',
  sharedContract: 'src/app/topology/sharedPlatformContract.ts',
  storageKeys: 'src/app/platform/storageKeys.ts',
  themeStore: 'src/app/platform/theme/store.ts',
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

function extractStringInitializer(sourceFile, variableName) {
  const initializer = findVariableInitializer(sourceFile, variableName)
  if (!initializer || !ts.isStringLiteral(initializer)) {
    fail(`Could not read string ${variableName}`)
    return ''
  }
  return initializer.text
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

function compareCatalogShape(label, expectedCatalog, actualCatalog) {
  const expectedNamespaces = Array.from(expectedCatalog.keys())
  const actualNamespaces = Array.from(actualCatalog.keys())
  compareSets(`${label} namespaces`, expectedNamespaces, actualNamespaces)
  for (const namespace of expectedNamespaces) {
    const expectedMessages = Array.from(expectedCatalog.get(namespace)?.keys() || [])
    const actualMessages = Array.from(actualCatalog.get(namespace)?.keys() || [])
    compareSets(`${label}.${namespace}`, expectedMessages, actualMessages)
    for (const key of expectedMessages) {
      const value = actualCatalog.get(namespace)?.get(key)
      if (typeof value !== 'string' || value.trim().length === 0) {
        fail(`${label}.${namespace}.${key} must be a non-empty message`)
      }
    }
  }
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

function extractThemeTokenLeaves(sourceFile) {
  const initializer = findVariableInitializer(sourceFile, 'THEME_TOKENS')
  const result = new Map()
  for (const themeProperty of extractObjectLiteralProperties(initializer)) {
    if (!ts.isObjectLiteralExpression(themeProperty.value)) continue
    const groups = new Map()
    for (const groupProperty of extractObjectLiteralProperties(themeProperty.value)) {
      if (!ts.isObjectLiteralExpression(groupProperty.value)) continue
      groups.set(groupProperty.key, extractObjectLiteralProperties(groupProperty.value).map((property) => property.key))
    }
    result.set(themeProperty.key, groups)
  }
  if (result.size === 0) fail('Could not read THEME_TOKENS leaves')
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
const localeTypesFile = parseFile(files.localeTypes)
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
const appLocales = extractConstStringArray(localeTypesFile, 'APP_LOCALES')
const defaultLocale = extractStringInitializer(localeTypesFile, 'DEFAULT_APP_LOCALE')
const moduleEntries = extractModuleManifest(moduleManifestFile)
const manifestModes = moduleEntries.map((entry) => entry.moduleKey)
const placementRecords = extractPageRecords(pagePlacementFile, 'PAGE_PLACEMENT_BASELINE')
const baselineRecords = extractPageRecords(baselineInventoryFile, 'BASELINE_PAGE_INVENTORY')
const placementModes = placementRecords.flatMap((record) => record.navModes)
const baselineModes = baselineRecords.flatMap((record) => record.navModes)
const catalogShape = extractNestedCatalog(catalogFile, 'MESSAGE_KEY_SHAPE')
const zhCNMessages = extractNestedCatalog(catalogFile, 'zhCNMessages')
const enUSMessages = extractNestedCatalog(catalogFile, 'enUSMessages')
const catalogLocales = extractObjectKeys(catalogFile, 'MESSAGE_CATALOGS')
const appThemes = extractConstStringArray(themeTypesFile, 'APP_THEMES')
const defaultTheme = extractStringInitializer(themeTypesFile, 'DEFAULT_APP_THEME')
const themeTokenGroups = extractThemeTokenGroups(themeTokensFile)
const themeTokenLeaves = extractThemeTokenLeaves(themeTokensFile)
const sharedCapabilityIds = extractObjectArrayPropertyValues(sharedContractFile, 'SHARED_PLATFORM_CAPABILITIES', 'id')
const topologyScopeKeys = extractObjectKeys(topologyContractsFile, 'TOPOLOGY_SCOPE')
const storageKeys = extractObjectKeys(parseFile(files.storageKeys), 'APP_STORAGE_KEYS')

compareSets('KernelModuleKey vs moduleManifest', kernelModes, manifestModes)
compareSets('KernelModuleKey vs PAGE_PLACEMENT_BASELINE', kernelModes, placementModes)
compareSets('KernelModuleKey vs BASELINE_PAGE_INVENTORY', kernelModes, baselineModes)
compareSets('APP_LOCALES vs MESSAGE_CATALOGS', appLocales, catalogLocales)
compareCatalogShape('zh-CN catalog shape', catalogShape, zhCNMessages)
compareCatalogShape('en-US catalog shape', catalogShape, enUSMessages)
assertCondition(appLocales.includes(defaultLocale), `DEFAULT_APP_LOCALE must be part of APP_LOCALES: ${defaultLocale}`)
assertCondition(appThemes.includes(defaultTheme), `DEFAULT_APP_THEME must be part of APP_THEMES: ${defaultTheme}`)
assertCondition(storageKeys.includes('locale'), 'APP_STORAGE_KEYS must include locale')
assertCondition(storageKeys.includes('theme'), 'APP_STORAGE_KEYS must include theme')

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
  const expectedSurfaceKind = entry.layerId === 'A' ? 'workbench' : entry.layerId === 'B' ? 'visualization' : 'management'
  assertCondition(
    entry.surfaceKind === expectedSurfaceKind,
    `Layer ${entry.layerId} surfaceKind mismatch for ${entry.moduleKey}: ${entry.surfaceKind} != ${expectedSurfaceKind}`,
  )
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
  const groups = themeTokenLeaves.get(theme) || new Map()
  for (const group of EXPECTED_THEME_GROUPS) {
    compareSets(`THEME_TOKENS.${theme}.${group}`, EXPECTED_THEME_TOKEN_LEAVES[group], groups.get(group) || [])
  }
}

assertCondition(sharedCapabilityIds.includes('theme-i18n'), 'Shared platform contract must include theme-i18n capability')
assertCondition(topologyScopeKeys.includes('baseline'), 'TOPOLOGY_SCOPE must include baseline')
assertCondition(topologyScopeKeys.includes('interpretation'), 'TOPOLOGY_SCOPE must include interpretation')
assertCondition(topologyScopeKeys.includes('nonGoals'), 'TOPOLOGY_SCOPE must include nonGoals')

const appShellSource = readFile(files.appShell)
const figmaSideNavSource = readFile(files.figmaSideNav)
const legacyHashAdapterSource = readFile(files.legacyHashAdapter)
const localeStoreSource = readFile(files.localeStore)
const navigationIndexSource = readFile(files.navigationIndex)
const registrySource = readFile(files.registry)
const settingsPageSource = readFile(files.settingsPage)
const sharedContractSource = readFile(files.sharedContract)
const themeStoreSource = readFile(files.themeStore)
assertCondition(appShellSource.includes('useAppLocale()'), 'AppShell must consume useAppLocale')
assertCondition(appShellSource.includes('useAppTheme()'), 'AppShell must consume useAppTheme')
assertCondition(appShellSource.includes('applyThemeTokens(appTheme)'), 'AppShell must apply theme tokens')
assertCondition(appShellSource.includes('getModuleDescriptor(viewMode).titleKey'), 'AppShell title must resolve through module descriptors')
assertCondition(appShellSource.includes('theme={appTheme}'), 'AppShell must pass the active theme into the side navigation')
assertCondition(appShellSource.includes('SURFACE_SWITCH_RULES[surface].retain'), 'AppShell surface switch copy must read retain rules from the shared contract')
assertCondition(figmaSideNavSource.includes('getModulesByGroup'), 'FigmaSideNav must read module registry by group')
assertCondition(figmaSideNavSource.includes('resolveInteractionSurface(item.mode) === surface'), 'FigmaSideNav must filter modules by interaction surface')
assertCondition(figmaSideNavSource.includes('translate(locale, item.navLabelKey'), 'FigmaSideNav labels must resolve through i18n keys')
assertCondition(registrySource.includes('moduleManifest.map'), 'Module registry must be generated from moduleManifest')
assertCondition(registrySource.includes('resolveInteractionSurface(mode)'), 'Module registry must derive interaction profile from topology contract')
assertCondition(legacyHashAdapterSource.includes('moduleManifest.map'), 'Hash adapter must be generated from moduleManifest')
assertCondition(navigationIndexSource.includes("from '../kernel/legacyHashAdapter'"), 'Navigation index must re-export the kernel hash adapter')
assertCondition(localeStoreSource.includes('storageKey: APP_STORAGE_KEYS.locale'), 'Locale store must use APP_STORAGE_KEYS.locale')
assertCondition(themeStoreSource.includes('storageKey: APP_STORAGE_KEYS.theme'), 'Theme store must use APP_STORAGE_KEYS.theme')
assertCondition(settingsPageSource.includes('onLocaleChange={setAppLocale}'), 'SettingsPage must wire locale control to setAppLocale')
assertCondition(settingsPageSource.includes('onThemeChange={setAppTheme}'), 'SettingsPage must wire theme control to setAppTheme')
assertCondition(settingsPageSource.includes('APP_LOCALES.map'), 'SettingsPage must render locale options from APP_LOCALES')
assertCondition(settingsPageSource.includes('APP_THEMES.map'), 'SettingsPage must render theme options from APP_THEMES')
assertCondition(sharedContractSource.includes("retain: ['projectKey', 'theme', 'locale'"), 'Surface switch retain rule must keep projectKey/theme/locale')

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
  i18n_locales: appLocales,
  nav_groups: navGroupKeys.length,
  themes: appThemes,
  theme_token_groups: EXPECTED_THEME_GROUPS,
  theme_token_leaves: EXPECTED_THEME_TOKEN_LEAVES,
  checked_files: Object.values(files),
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}

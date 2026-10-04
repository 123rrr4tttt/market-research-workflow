#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')
const backendDir = path.resolve(rootDir, '..', 'backend')

const files = {
  moduleManifest: 'src/app/kernel/moduleManifest.ts',
  moduleRendererBindings: 'src/app/kernel/moduleContributionRule.ts',
  hash: 'src/app/topology/hash.ts',
  endpoints: 'src/lib/api/endpoints.ts',
  writingDomain: 'src/lib/api/domains/writing.ts',
  story: 'src/pages/WritingWorkbenchPage.stories.tsx',
  backendSchema: path.join(backendDir, 'app/contracts/schemas/writing.py'),
  backendApi: path.join(backendDir, 'app/api/writing.py'),
}

const failures = []

function fail(message) {
  failures.push(message)
}

function assertCondition(condition, message) {
  if (!condition) fail(message)
}

function readFile(relOrAbsPath) {
  const fullPath = path.isAbsolute(relOrAbsPath) ? relOrAbsPath : path.join(rootDir, relOrAbsPath)
  return fs.readFileSync(fullPath, 'utf8')
}

function parseFile(relPath) {
  const fullPath = path.join(rootDir, relPath)
  return ts.createSourceFile(fullPath, fs.readFileSync(fullPath, 'utf8'), ts.ScriptTarget.Latest, true)
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
    fail(`Could not read string array ${variableName}`)
    return []
  }
  return initializer.elements
    .map((element) => unwrap(element))
    .filter(ts.isStringLiteral)
    .map((element) => element.text)
}

function extractTypePropertyKeys(sourceFile, typeName) {
  let keys = []
  sourceFile.forEachChild((node) => {
    if (!ts.isTypeAliasDeclaration(node) || node.name.text !== typeName) return
    const typeNode = unwrap(node.type)
    if (!ts.isTypeLiteralNode(typeNode)) {
      fail(`${typeName} is not a type literal`)
      return
    }
    keys = typeNode.members
      .filter(ts.isPropertySignature)
      .map((member) => propertyNameToString(member.name))
      .filter(Boolean)
  })
  if (keys.length === 0) fail(`Could not read type ${typeName}`)
  return keys
}

function extractObjectLiteralProperties(objectNode) {
  if (!objectNode || !ts.isObjectLiteralExpression(objectNode)) return []
  return objectNode.properties
    .filter(ts.isPropertyAssignment)
    .map((property) => ({ key: propertyNameToString(property.name), value: unwrap(property.initializer) }))
    .filter((property) => property.key)
}

function containsNode(node, predicate) {
  if (predicate(node)) return true
  let found = false
  node.forEachChild((child) => { if (!found) found = containsNode(child, predicate) })
  return found
}

function isPropertyAccess(node, objectName, propertyName) {
  const value = unwrap(node)
  return ts.isPropertyAccessExpression(value)
    && ts.isIdentifier(value.expression) && value.expression.text === objectName
    && value.name.text === propertyName
}

function extractNestedObjectKeys(sourceFile, variableName, nestedKey) {
  const initializer = findVariableInitializer(sourceFile, variableName)
  const nested = extractObjectLiteralProperties(initializer).find((property) => property.key === nestedKey)
  return extractObjectLiteralProperties(nested?.value).map((property) => property.key)
}

function extractModuleManifest(sourceFile) {
  const initializer = findVariableInitializer(sourceFile, 'moduleManifest')
  if (!initializer || !ts.isArrayLiteralExpression(initializer)) {
    fail('Could not read moduleManifest')
    return []
  }
  return initializer.elements.map((element) => {
    const call = unwrap(element)
    if (!ts.isCallExpression(call)) {
      fail('moduleManifest must contain defineModule calls only')
      return null
    }
    const args = call.arguments.map((arg) => unwrap(arg))
    const stringArg = (index) => (ts.isStringLiteral(args[index]) ? args[index].text : '')
    const loopsArg = args[6]
    let keepLoops = []
    if (ts.isIdentifier(loopsArg)) {
      keepLoops = extractConstStringArray(sourceFile, loopsArg.text)
    } else if (ts.isArrayLiteralExpression(loopsArg)) {
      keepLoops = loopsArg.elements
        .map((item) => unwrap(item))
        .filter(ts.isStringLiteral)
        .map((item) => item.text)
    }
    return {
      moduleKey: stringArg(0),
      layerId: stringArg(1),
      surfaceKind: stringArg(2),
      entryRoute: stringArg(3),
      legacyHash: stringArg(4),
      keepLoops,
    }
  }).filter(Boolean)
}

function assertIncludesAll(label, actual, expected) {
  for (const item of expected) {
    assertCondition(actual.includes(item), `${label} missing ${item}`)
  }
}

const moduleManifestFile = parseFile(files.moduleManifest)
const endpointsFile = parseFile(files.endpoints)
const writingDomainFile = parseFile(files.writingDomain)
const rendererSource = parseFile(files.moduleRendererBindings)
const hashSource = readFile(files.hash)
const storySource = readFile(files.story)
const backendSchemaSource = readFile(files.backendSchema)
const backendApiSource = readFile(files.backendApi)

const moduleEntries = extractModuleManifest(moduleManifestFile)
const writingEntry = moduleEntries.find((entry) => entry.moduleKey === 'flowWriting')
assertCondition(Boolean(writingEntry), 'moduleManifest must include flowWriting')
if (writingEntry) {
  assertCondition(writingEntry.layerId === 'A', 'flowWriting must stay in layer A')
  assertCondition(writingEntry.surfaceKind === 'workbench', 'flowWriting must stay on workbench surface')
  assertCondition(writingEntry.entryRoute === '/workbench/writing', 'flowWriting entry route must stay /workbench/writing')
  assertCondition(writingEntry.legacyHash === '#writing-workbench.html', 'flowWriting legacy hash must stay #writing-workbench.html')
  assertIncludesAll('flowWriting keepLoops', writingEntry.keepLoops, ['edit', 'preview', 'template', 'llm-assist', 'citation-basket', 'info-card'])
}

const moduleRenderers = findVariableInitializer(rendererSource, 'MODULE_RENDERERS')
const flowWritingRenderer = extractObjectLiteralProperties(moduleRenderers).find((property) => property.key === 'flowWriting')
assertCondition(Boolean(flowWritingRenderer), 'module renderer bindings must define flowWriting')
if (flowWritingRenderer) {
  const rendererBody = unwrap(flowWritingRenderer.value)
  assertCondition(
    containsNode(rendererBody, (node) => ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === 'h'
      && ts.isIdentifier(node.arguments[0]) && node.arguments[0].text === 'WritingWorkbenchPage'),
    'flowWriting renderer must render WritingWorkbenchPage',
  )
}
const writingPageLazyBinding = findVariableInitializer(rendererSource, 'WritingWorkbenchPage')
assertCondition(Boolean(writingPageLazyBinding) && containsNode(writingPageLazyBinding, (node) =>
  ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword
  && node.arguments.some((argument) => ts.isStringLiteral(argument) && argument.text === '../../pages/WritingWorkbenchPage')),
'WritingWorkbenchPage renderer binding must lazy-load the page module')
const rendererBindings = unwrap(findVariableInitializer(rendererSource, 'moduleRendererBindings'))
const rendererBindingsMap = ts.isCallExpression(rendererBindings) ? unwrap(rendererBindings.arguments[0]) : null
const rendererBindingMapper = ts.isCallExpression(rendererBindingsMap)
  && ts.isPropertyAccessExpression(rendererBindingsMap.expression)
  && rendererBindingsMap.expression.name.text === 'map'
  ? unwrap(rendererBindingsMap.arguments[0])
  : null
const rendererBindingTuple = ts.isArrowFunction(rendererBindingMapper)
  ? unwrap(rendererBindingMapper.body)
  : null
const rendererBindingValue = rendererBindingTuple && ts.isArrayLiteralExpression(rendererBindingTuple)
  ? unwrap(rendererBindingTuple.elements[1])
  : null
const rendererBindingProperties = extractObjectLiteralProperties(rendererBindingValue)
const rendererCatalogLookup = rendererBindingProperties.find((property) => property.key === 'renderer')?.value
assertCondition(
  ts.isCallExpression(rendererBindings)
    && isPropertyAccess(rendererBindings.expression, 'Object', 'fromEntries')
    && ts.isCallExpression(rendererBindingsMap)
    && ts.isPropertyAccessExpression(rendererBindingsMap.expression)
    && ts.isIdentifier(rendererBindingsMap.expression.expression)
    && rendererBindingsMap.expression.expression.text === 'moduleManifest'
    && ts.isArrowFunction(rendererBindingMapper)
    && rendererBindingTuple != null
    && ts.isArrayLiteralExpression(rendererBindingTuple)
    && rendererBindingTuple.elements.length === 2
    && isPropertyAccess(rendererBindingTuple.elements[0], 'entry', 'moduleKey')
    && isPropertyAccess(rendererBindingProperties.find((property) => property.key === 'moduleKey')?.value, 'entry', 'moduleKey')
    && ts.isElementAccessExpression(unwrap(rendererCatalogLookup))
    && ts.isIdentifier(unwrap(rendererCatalogLookup).expression)
    && unwrap(rendererCatalogLookup).expression.text === 'MODULE_RENDERERS'
    && isPropertyAccess(unwrap(rendererCatalogLookup).argumentExpression, 'entry', 'moduleKey'),
  'module renderer bindings must derive keyed renderers from moduleManifest',
)
assertCondition(hashSource.includes('writing-workbench.html'), 'standalone hash resolver must recognize writing-workbench.html')
assertCondition(hashSource.includes("mode === 'flowWriting'"), 'standalone hash resolver must map flowWriting')
assertCondition(storySource.includes('ShellWorkbench'), 'WritingWorkbenchPage stories must include shell workbench fixture')
assertCondition(storySource.includes('moduleKey="flowWriting"'), 'ShellWorkbench story must use flowWriting')

const writingEndpointKeys = extractNestedObjectKeys(endpointsFile, 'endpoints', 'writing')
assertIncludesAll('endpoints.writing', writingEndpointKeys, [
  'documents',
  'documentById',
  'documentDraft',
  'documentCitations',
  'templates',
  'templateValidate',
  'keywordCards',
  'keywordCardPreview',
  'cardById',
  'suggest',
  'llmActions',
  'llmActionHistory',
  'llmActionById',
  'exportMarkdown',
])

assertIncludesAll('WritingKeywordCardRequest', extractTypePropertyKeys(writingDomainFile, 'WritingKeywordCardRequest'), [
  'context',
  'graph_context',
])
assertIncludesAll('WritingContextEnvelope', extractTypePropertyKeys(writingDomainFile, 'WritingContextEnvelope'), [
  'typed_knowledge_context',
])
assertIncludesAll('WritingKeywordCardListResponse', extractTypePropertyKeys(writingDomainFile, 'WritingKeywordCardListResponse'), [
  'context_boundary',
  'dependency_gate',
])
assertIncludesAll('WritingLlmActionPayload', extractTypePropertyKeys(writingDomainFile, 'WritingLlmActionPayload'), [
  'target_scope',
])
assertIncludesAll('WritingLlmActionResponse', extractTypePropertyKeys(writingDomainFile, 'WritingLlmActionResponse'), [
  'requested_async',
  'execution_mode',
  'async_honored',
  'capability_truth',
  'action_boundary',
  'dependency_gate',
])

assertIncludesAll('backend writing schema', backendSchemaSource, [
  'class WritingContextEnvelope',
  'class TypedKnowledgeWritingHandoffData',
  'class TypedKnowledgeWritingContext',
  'typed_knowledge_context',
  'context_boundary',
  'dependency_gate',
  'action_boundary',
  'capability_truth',
  'requested_async',
  'execution_mode: Literal["inline"]',
  'async_honored',
  'target_scope',
])
assertIncludesAll('backend writing api', backendApiSource, [
  '"/documents"',
  '"/documents/{doc_id}/draft"',
  '"/documents/{doc_id}/citations"',
  '"/templates/validate"',
  '"/keyword-cards"',
  '"/keyword-cards/preview"',
  '"/cards/{card_id}"',
  '"/suggest"',
  '"/llm-actions"',
  '"/llm-actions/history"',
  '"/llm-actions/{job_id}"',
  '"/export/markdown"',
])

const summary = {
  status: failures.length === 0 ? 'ok' : 'failed',
  module: writingEntry,
  writing_endpoint_keys: writingEndpointKeys,
  checked_frontend_types: [
    'WritingKeywordCardRequest',
    'WritingKeywordCardListResponse',
    'WritingLlmActionPayload',
    'WritingLlmActionResponse',
  ],
  checked_files: Object.values(files),
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}

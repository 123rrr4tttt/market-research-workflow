#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')

const files = {
  packageJson: 'package.json',
  graphPage: 'src/pages/GraphPage.tsx',
  modeSwitch: 'src/pages/graph/hooks/useGraphModeSwitch.ts',
  loader: 'src/pages/graph/hooks/useForceGraph3DLoader.ts',
  viewport: 'src/pages/graph/hooks/useForceGraphViewport.ts',
  objects: 'src/pages/graph/renderers/force3dObjects.ts',
  lifecycle: 'tests/e2e/graph-renderer-lifecycle.spec.ts',
  e2e: 'tests/e2e/graphpage.spec.ts',
  runtimePixelGate: 'tests/e2e/graph-runtime-pixel-gate.spec.ts',
  css: 'src/index.css',
}

const failures = []

function readFile(relPath) {
  return fs.readFileSync(path.join(rootDir, relPath), 'utf8')
}

function fail(message) {
  failures.push(message)
}

function assertIncludes(source, needle, label) {
  if (!source.includes(needle)) fail(`${label}: missing ${needle}`)
}

function assertRegex(source, pattern, label) {
  if (!pattern.test(source)) fail(`${label}: missing ${pattern}`)
}

const packageJson = JSON.parse(readFile(files.packageJson))
const graphPage = readFile(files.graphPage)
const modeSwitch = readFile(files.modeSwitch)
const loader = readFile(files.loader)
const viewport = readFile(files.viewport)
const objects = readFile(files.objects)
const lifecycle = readFile(files.lifecycle)
const e2e = readFile(files.e2e)
const runtimePixelGate = readFile(files.runtimePixelGate)
const css = readFile(files.css)

if (!packageJson.dependencies?.['react-force-graph-3d']) {
  fail('package.json: react-force-graph-3d dependency is required')
}

assertIncludes(modeSwitch, 'requestRenderModeChange', files.modeSwitch)
assertIncludes(modeSwitch, 'renderModeRef.current = next', files.modeSwitch)
for (const retired of ['ProjectionEngine', 'requestProjectionEngineChange', 'SwitchTimerRef']) {
  if (modeSwitch.includes(retired)) fail(`${files.modeSwitch}: retired engine or deferred intent remains: ${retired}`)
}

assertIncludes(loader, "import('react-force-graph-3d')", files.loader)
assertRegex(loader, /const\s+MAX_RETRY\s*=\s*[2-9]/, files.loader)
assertIncludes(loader, 'forceGraph3DPromise = null', files.loader)
assertIncludes(loader, 'setRetryNonce((value) => value + 1)', files.loader)
assertIncludes(loader, 'setComponent(() => mod.default)', files.loader)

assertIncludes(viewport, 'ResizeObserver', files.viewport)
assertIncludes(viewport, "window.addEventListener('resize', updateViewport)", files.viewport)
assertIncludes(viewport, 'if (width <= 0 || height <= 0) return', files.viewport)
assertRegex(viewport, /useState\(\{\s*width:\s*1280,\s*height:\s*720\s*\}\)/, files.viewport)

assertIncludes(graphPage, 'class ForceGraphRenderBoundary', files.graphPage)
assertIncludes(graphPage, '<ForceGraphRenderBoundary', files.graphPage)
assertIncludes(graphPage, 'handleForceGraphRenderError', files.graphPage)
assertIncludes(graphPage, 'retryForceGraph', files.graphPage)
assertIncludes(graphPage, 'data-testid="graph-force3d-canvas-host"', files.graphPage)
assertIncludes(graphPage, 'width={forceViewport.width || displayResource.width}', files.graphPage)
assertIncludes(graphPage, 'height={forceViewport.height || displayResource.height}', files.graphPage)
assertIncludes(graphPage, 'key={forceGraphRenderBoundaryKey}', files.graphPage)
assertIncludes(graphPage, 'ref={attachForceGraph}', files.graphPage)
assertIncludes(graphPage, 'forceGraphMountEpoch', files.graphPage)
assertIncludes(graphPage, 'displayResource.ready', files.graphPage)
assertIncludes(graphPage, "window.__graph3dDebug = debugApi", files.graphPage)
assertIncludes(graphPage, 'getVisibilityStats: () => force3DVisibilityStatsGetterRef.current()', files.graphPage)
assertIncludes(graphPage, 'const visibleForceNodes = forceGraphData.nodes.filter', files.graphPage)
assertIncludes(graphPage, 'const dataNodes = visibleForceNodes.length', files.graphPage)
assertIncludes(graphPage, 'forceVisibleNodeKeySet.has(String(node.id || \'\'))', files.graphPage)
for (const retired of ['Legacy3DRenderer', 'projectionEngine', 'requestProjectionEngineChange', 'legacy-projection']) {
  if (graphPage.includes(retired)) fail(`${files.graphPage}: retired 3D implementation remains: ${retired}`)
}
assertIncludes(graphPage, 'const forceGraphRenderBoundaryKey = `${displayResourceKey}:${displayResource.epoch}:${forceGraphRetry}`', files.graphPage)
assertIncludes(graphPage, 'createForceNodeObject({', files.graphPage)
assertIncludes(objects, 'export function createForceNodeObject(', files.objects)
for (const retired of ['getOrCreateForceNodeObject', 'pruneForceNodeObjectCache']) {
  if (graphPage.includes(retired) || objects.includes(retired)) fail(`Retired node cache API remains: ${retired}`)
}
assertIncludes(viewport, 'mountEpoch', files.viewport)
assertIncludes(lifecycle, 'useGraphDisplayResourceScheduler', files.lifecycle)
assertIncludes(lifecycle, 'useForceGraphViewport', files.lifecycle)

assertIncludes(e2e, 'graph page renders force3d canvas backed by graph scene nodes', files.e2e)
assertIncludes(e2e, 'graph page preserves the final rapid 2D/3D selection and restores its viewport', files.e2e)
assertIncludes(e2e, 'graph-force3d-canvas-host', files.e2e)
assertIncludes(e2e, '__graph3dDebug', files.e2e)
for (const retired of ["selectOption('legacy')", "selectOption('force3d')", '已自动降级到 legacy-projection']) {
  if (e2e.includes(retired) || runtimePixelGate.includes(retired)) fail(`Retired fallback acceptance remains: ${retired}`)
}

assertIncludes(
  packageJson.scripts?.['check:graph-runtime-pixel-gate'] || '',
  'tests/e2e/graph-runtime-pixel-gate.spec.ts',
  files.packageJson,
)
assertIncludes(runtimePixelGate, 'graph runtime pixel gate proves force3d pixels without tenant DB', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'graph-runtime-pixel-gate', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'inspectPixelDiversity', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'nonblank-pixels', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'expect(pixelEvidence.nonblank).toBe(true)', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'externalGpuRequired: false', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'tenantDbRequired: false', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'stats.sceneNodeObjects >= expectedNodes', files.runtimePixelGate)

assertRegex(css, /\.gv2-chart--force3d\s*\{[\s\S]*position:\s*absolute;[\s\S]*inset:\s*0;[\s\S]*min-height:\s*0;/, files.css)
assertRegex(css, /\.gv2-chart--force3d canvas\s*\{[\s\S]*display:\s*block;/, files.css)

if (failures.length > 0) {
  console.error('Graph force3d frontend contract check failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('Graph force3d frontend contract check passed')

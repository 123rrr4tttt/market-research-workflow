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
const e2e = readFile(files.e2e)
const runtimePixelGate = readFile(files.runtimePixelGate)
const css = readFile(files.css)

if (!packageJson.dependencies?.['react-force-graph-3d']) {
  fail('package.json: react-force-graph-3d dependency is required')
}

assertIncludes(modeSwitch, "export type ProjectionEngine = 'legacy' | 'force3d'", files.modeSwitch)
assertIncludes(modeSwitch, "initialProjectionEngine = 'force3d'", files.modeSwitch)
assertRegex(modeSwitch, /const\s+DEFAULT_ENGINE_SWITCH_GUARD_MS\s*=\s*(1[0-9]{2}|[2-9][0-9]{2,})/, files.modeSwitch)
assertIncludes(modeSwitch, 'requestProjectionEngineChange', files.modeSwitch)
assertIncludes(modeSwitch, 'projectionEngineSwitchTimerRef', files.modeSwitch)
assertIncludes(modeSwitch, 'window.clearTimeout(projectionEngineSwitchTimerRef.current)', files.modeSwitch)

assertIncludes(loader, "import('react-force-graph-3d')", files.loader)
assertRegex(loader, /const\s+MAX_RETRY\s*=\s*[2-9]/, files.loader)
assertIncludes(loader, 'forceGraph3DPromise = null', files.loader)
assertIncludes(loader, 'setRetryNonce((value) => value + 1)', files.loader)

assertIncludes(viewport, 'ResizeObserver', files.viewport)
assertIncludes(viewport, "window.addEventListener('resize', updateViewport)", files.viewport)
assertIncludes(viewport, 'if (width <= 0 || height <= 0) return', files.viewport)
assertRegex(viewport, /useState\(\{\s*width:\s*1280,\s*height:\s*720\s*\}\)/, files.viewport)

assertIncludes(graphPage, 'class ForceGraphRenderBoundary', files.graphPage)
assertIncludes(graphPage, '<ForceGraphRenderBoundary', files.graphPage)
assertIncludes(graphPage, 'handleForceGraphRenderError', files.graphPage)
assertIncludes(graphPage, "requestProjectionEngineChange('legacy')", files.graphPage)
assertIncludes(graphPage, '3D引擎渲染失败，已自动降级到 legacy-projection', files.graphPage)
assertIncludes(graphPage, '3D引擎加载失败，已自动降级到 legacy-projection', files.graphPage)
assertIncludes(graphPage, 'data-testid="graph-force3d-canvas-host"', files.graphPage)
assertIncludes(graphPage, 'width={forceViewport.width}', files.graphPage)
assertIncludes(graphPage, 'height={forceViewport.height}', files.graphPage)
assertIncludes(graphPage, "window.__graph3dDebug = debugApi", files.graphPage)
assertIncludes(graphPage, 'getVisibilityStats: () => force3DVisibilityStatsGetterRef.current()', files.graphPage)
assertIncludes(graphPage, '<option value="legacy">legacy-projection</option>', files.graphPage)
assertIncludes(graphPage, '<option value="force3d">react-force-graph-3d</option>', files.graphPage)
assertIncludes(graphPage, "style={showForceGraphCanvas ? { display: 'none' } : undefined}", files.graphPage)
assertRegex(
  graphPage,
  /const\s+forceGraphRenderBoundaryKey\s*=\s*`\$\{renderMode\}:\$\{projectionEngine\}:\$\{forceGraphData\.nodes\.length\}:\$\{forceGraphData\.links\.length\}`/,
  files.graphPage,
)

assertIncludes(e2e, 'graph page renders force3d canvas backed by graph scene nodes', files.e2e)
assertIncludes(e2e, 'graph page survives rapid 3D engine switch with viewport evidence or fallback', files.e2e)
assertIncludes(e2e, 'graph-force3d-canvas-host', files.e2e)
assertIncludes(e2e, '__graph3dDebug', files.e2e)
assertIncludes(e2e, '已自动降级到 legacy-projection', files.e2e)
assertIncludes(e2e, "selectOption('legacy')", files.e2e)
assertIncludes(e2e, "selectOption('force3d')", files.e2e)

assertIncludes(
  packageJson.scripts?.['check:graph-runtime-pixel-gate'] || '',
  'tests/e2e/graph-runtime-pixel-gate.spec.ts',
  files.packageJson,
)
assertIncludes(runtimePixelGate, 'graph runtime pixel gate proves force3d pixels or shape framing without tenant DB', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'wave17-graph-runtime-pixel-gate', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'inspectPixelDiversity', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'nonblank-pixels', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'shape-framing', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'fallback-data-framing', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'externalGpuRequired: false', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'tenantDbRequired: false', files.runtimePixelGate)
assertIncludes(runtimePixelGate, 'stats.sceneNodeObjects >= expectedNodes', files.runtimePixelGate)
assertIncludes(runtimePixelGate, "metrics['节点总数'] === String(expectedNodes)", files.runtimePixelGate)

assertRegex(css, /\.gv2-chart--force3d\s*\{[\s\S]*position:\s*absolute;[\s\S]*inset:\s*0;[\s\S]*min-height:\s*0;/, files.css)
assertRegex(css, /\.gv2-chart--force3d canvas\s*\{[\s\S]*display:\s*block;/, files.css)

if (failures.length > 0) {
  console.error('Graph force3d frontend contract check failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('Graph force3d frontend contract check passed')

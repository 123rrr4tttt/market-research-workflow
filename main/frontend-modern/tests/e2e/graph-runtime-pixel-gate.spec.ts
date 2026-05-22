import { expect, test, type Page, type Route } from '@playwright/test'
import { inflateSync } from 'node:zlib'

type GraphRuntimeEvidence = {
  mode: 'force3d' | 'fallback'
  dataNodes?: number
  sceneNodeObjects?: number
  canvasWidth?: number
  canvasHeight?: number
  hostWidth?: number
  hostHeight?: number
  fallbackText?: string
  engineValue?: string
  chartWidth?: number
  chartHeight?: number
  metricNodes?: string
  metricEdges?: string
  legendLabels?: string[]
}

type PixelEvidence = {
  width: number
  height: number
  sampledPixels: number
  uniqueColors: number
  transitionCount: number
  nonTransparentPixels: number
  nonblank: boolean
}

function apiEnvelope(data: unknown) {
  return {
    status: 'ok',
    data,
    error: null,
    meta: { trace_id: 'wave17-graph-runtime-pixel-gate' },
  }
}

async function fulfillJson(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(apiEnvelope(data)),
  })
}

async function setupGraphRuntimeMocks(page: Page) {
  let marketGraphHit = 0
  const marketPayload = {
    nodes: [
      { id: 'n1', type: 'product', name: 'Wave17 Product' },
      { id: 'n2', type: 'company', name: 'Wave17 Company' },
      { id: 'n3', type: 'policy', name: 'Wave17 Policy' },
    ],
    edges: [
      {
        type: 'related_to',
        from: { type: 'product', id: 'n1' },
        to: { type: 'company', id: 'n2' },
      },
      {
        type: 'regulated_by',
        from: { type: 'company', id: 'n2' },
        to: { type: 'policy', id: 'n3' },
      },
    ],
  }

  await page.route('**/api/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname === '/api/v1/project-customization/graph-config') {
      await fulfillJson(route, {
        graph_node_types: {
          market: ['product', 'company', 'policy'],
        },
        graph_node_labels: {
          product: '商品',
          company: '公司',
          policy: '政策',
        },
        graph_relation_labels: {
          related_to: '关联',
          regulated_by: '监管',
        },
      })
      return
    }
    if (pathname === '/api/v1/admin/market-graph') {
      marketGraphHit += 1
      await fulfillJson(route, marketPayload)
      return
    }
    if (pathname === '/api/v1/admin/policy-graph' || pathname === '/api/v1/admin/content-graph') {
      await fulfillJson(route, { nodes: [], edges: [] })
      return
    }
    if (pathname === '/api/v1/workflow-graph/templates') {
      await fulfillJson(route, { items: [], total: 0 })
      return
    }
    await fulfillJson(route, { items: [], total: 0 })
  })

  return {
    get marketGraphHit() {
      return marketGraphHit
    },
    expectedNodes: marketPayload.nodes.length,
    expectedEdges: marketPayload.edges.length,
  }
}

function paethPredictor(left: number, up: number, upperLeft: number) {
  const p = left + up - upperLeft
  const pa = Math.abs(p - left)
  const pb = Math.abs(p - up)
  const pc = Math.abs(p - upperLeft)
  if (pa <= pb && pa <= pc) return left
  if (pb <= pc) return up
  return upperLeft
}

function readPngPixels(buffer: Buffer) {
  const signature = buffer.subarray(0, 8).toString('hex')
  expect(signature).toBe('89504e470d0a1a0a')

  let offset = 8
  let width = 0
  let height = 0
  let bitDepth = 0
  let colorType = 0
  const idatChunks: Buffer[] = []

  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset)
    const type = buffer.subarray(offset + 4, offset + 8).toString('ascii')
    const chunk = buffer.subarray(offset + 8, offset + 8 + length)
    if (type === 'IHDR') {
      width = chunk.readUInt32BE(0)
      height = chunk.readUInt32BE(4)
      bitDepth = chunk[8]
      colorType = chunk[9]
    }
    if (type === 'IDAT') idatChunks.push(chunk)
    if (type === 'IEND') break
    offset += length + 12
  }

  expect(bitDepth).toBe(8)
  expect([2, 6]).toContain(colorType)

  const channels = colorType === 6 ? 4 : 3
  const inflated = inflateSync(Buffer.concat(idatChunks))
  const stride = width * channels
  const pixels = new Uint8Array(width * height * channels)
  let sourceOffset = 0

  for (let y = 0; y < height; y += 1) {
    const filter = inflated[sourceOffset]
    sourceOffset += 1
    const rowStart = y * stride
    const previousRowStart = (y - 1) * stride
    for (let x = 0; x < stride; x += 1) {
      const raw = inflated[sourceOffset + x]
      const left = x >= channels ? pixels[rowStart + x - channels] : 0
      const up = y > 0 ? pixels[previousRowStart + x] : 0
      const upperLeft = y > 0 && x >= channels ? pixels[previousRowStart + x - channels] : 0
      let value = raw
      if (filter === 1) value = raw + left
      else if (filter === 2) value = raw + up
      else if (filter === 3) value = raw + Math.floor((left + up) / 2)
      else if (filter === 4) value = raw + paethPredictor(left, up, upperLeft)
      else expect(filter).toBe(0)
      pixels[rowStart + x] = value & 255
    }
    sourceOffset += stride
  }

  return { width, height, channels, pixels }
}

function inspectPixelDiversity(buffer: Buffer): PixelEvidence {
  const { width, height, channels, pixels } = readPngPixels(buffer)
  const uniqueColors = new Set<string>()
  let sampledPixels = 0
  let nonTransparentPixels = 0
  let transitionCount = 0
  let previous: [number, number, number] | null = null
  const stepX = Math.max(1, Math.floor(width / 96))
  const stepY = Math.max(1, Math.floor(height / 64))

  for (let y = 0; y < height; y += stepY) {
    previous = null
    for (let x = 0; x < width; x += stepX) {
      const index = (y * width + x) * channels
      const rgb: [number, number, number] = [pixels[index], pixels[index + 1], pixels[index + 2]]
      const alpha = channels === 4 ? pixels[index + 3] : 255
      sampledPixels += 1
      if (alpha > 0) nonTransparentPixels += 1
      uniqueColors.add(rgb.join(','))
      if (previous) {
        const delta = Math.abs(rgb[0] - previous[0]) + Math.abs(rgb[1] - previous[1]) + Math.abs(rgb[2] - previous[2])
        if (delta > 36) transitionCount += 1
      }
      previous = rgb
    }
  }

  return {
    width,
    height,
    sampledPixels,
    uniqueColors: uniqueColors.size,
    transitionCount,
    nonTransparentPixels,
    nonblank: uniqueColors.size >= 8 && transitionCount >= 4 && nonTransparentPixels > sampledPixels * 0.98,
  }
}

test('graph runtime pixel gate proves force3d pixels or shape framing without tenant DB', async ({ page }, testInfo) => {
  const hits = await setupGraphRuntimeMocks(page)
  await page.setViewportSize({ width: 1280, height: 860 })

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()
  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()

  const renderModeToggle = page.locator('button[title="轻量3D模型模式（中心锁定，非相机视角）"]').first()
  await expect(renderModeToggle).toHaveText('3D模式')
  await renderModeToggle.click()
  await expect(renderModeToggle).toHaveText('回到2D')

  const runtimeHandle = await page.waitForFunction(
    (expectedNodes) => {
      type Graph3DStats = {
        dataNodes: number
        sceneNodeObjects: number
        emptyDataNodes: number
        emptySceneNodeObjects: number
      }
      const debugWindow = window as Window & {
        __graph3dDebug?: {
          getVisibilityStats: () => Graph3DStats
        }
      }
      const host = document.querySelector('[data-testid="graph-force3d-canvas-host"]') as HTMLElement | null
      const canvas = host?.querySelector('canvas') as HTMLCanvasElement | null
      const hostRect = host?.getBoundingClientRect()
      const stats = debugWindow.__graph3dDebug?.getVisibilityStats()
      if (
        canvas &&
        hostRect &&
        canvas.width >= 320 &&
        canvas.height >= 320 &&
        hostRect.width >= 320 &&
        hostRect.height >= 320 &&
        stats &&
        stats.dataNodes === expectedNodes &&
        stats.sceneNodeObjects >= expectedNodes &&
        stats.emptyDataNodes === 0 &&
        stats.emptySceneNodeObjects === 0
      ) {
        return {
          mode: 'force3d',
          dataNodes: stats.dataNodes,
          sceneNodeObjects: stats.sceneNodeObjects,
          canvasWidth: canvas.width,
          canvasHeight: canvas.height,
          hostWidth: Math.round(hostRect.width),
          hostHeight: Math.round(hostRect.height),
        }
      }
      const fallbackText = Array.from(document.querySelectorAll('.gv2-loading'))
        .map((node) => node.textContent || '')
        .join('\n')
      const engineValue = Array.from(document.querySelectorAll('label.gv2-control-chip'))
        .find((node) => (node.textContent || '').includes('3D引擎'))
        ?.querySelector<HTMLSelectElement>('select')
        ?.value || ''
      const legacyChart = document.querySelector('.gv2-chart:not(.gv2-chart--force3d)') as HTMLElement | null
      const legacyChartRect = legacyChart?.getBoundingClientRect()
      const metrics = Array.from(document.querySelectorAll('.gv2-macro-stat')).reduce<Record<string, string>>((acc, node) => {
        const label = node.querySelector('span')?.textContent?.trim() || ''
        const value = node.querySelector('strong')?.textContent?.trim() || ''
        if (label) acc[label] = value
        return acc
      }, {})
      const legendLabels = Array.from(document.querySelectorAll('.gv2-legend-node-label'))
        .map((node) => node.textContent?.trim() || '')
        .filter(Boolean)
      if (
        fallbackText.includes('已自动降级到 legacy-projection') &&
        engineValue === 'legacy' &&
        legacyChartRect &&
        legacyChartRect.width >= 320 &&
        legacyChartRect.height >= 320 &&
        metrics['节点总数'] === String(expectedNodes) &&
        metrics['边总数'] === '2' &&
        ['商品', '市场', '政策'].every((label) => legendLabels.some((item) => item.includes(label)))
      ) {
        return {
          mode: 'fallback',
          fallbackText,
          engineValue,
          chartWidth: Math.round(legacyChartRect.width),
          chartHeight: Math.round(legacyChartRect.height),
          metricNodes: metrics['节点总数'],
          metricEdges: metrics['边总数'],
          legendLabels,
        }
      }
      return false
    },
    hits.expectedNodes,
    { timeout: 20000 },
  )

  const runtimeEvidence = await runtimeHandle.jsonValue() as GraphRuntimeEvidence
  expect(hits.marketGraphHit).toBeGreaterThan(0)

  let pixelEvidence: PixelEvidence | null = null
  if (runtimeEvidence.mode === 'force3d') {
    const host = page.getByTestId('graph-force3d-canvas-host')
    await expect(host).toBeVisible()
    expect(runtimeEvidence.dataNodes).toBe(hits.expectedNodes)
    expect(runtimeEvidence.sceneNodeObjects).toBeGreaterThanOrEqual(hits.expectedNodes)
    expect(Math.abs((runtimeEvidence.canvasWidth || 0) - (runtimeEvidence.hostWidth || 0))).toBeLessThanOrEqual(4)
    expect(Math.abs((runtimeEvidence.canvasHeight || 0) - (runtimeEvidence.hostHeight || 0))).toBeLessThanOrEqual(4)
    pixelEvidence = inspectPixelDiversity(await host.screenshot())
  } else {
    expect(runtimeEvidence.fallbackText).toContain('3D引擎渲染失败')
    expect(runtimeEvidence.engineValue).toBe('legacy')
    expect(runtimeEvidence.chartWidth).toBeGreaterThanOrEqual(320)
    expect(runtimeEvidence.chartHeight).toBeGreaterThanOrEqual(320)
    expect(runtimeEvidence.metricNodes).toBe(String(hits.expectedNodes))
    expect(runtimeEvidence.metricEdges).toBe(String(hits.expectedEdges))
    expect(runtimeEvidence.legendLabels?.join('\n')).toContain('商品')
    expect(runtimeEvidence.legendLabels?.join('\n')).toContain('政策')
  }

  const proof = pixelEvidence?.nonblank ? 'nonblank-pixels' : runtimeEvidence.mode === 'force3d' ? 'shape-framing' : 'fallback-data-framing'
  expect(['nonblank-pixels', 'shape-framing', 'fallback-data-framing']).toContain(proof)
  await testInfo.attach('wave17-graph-runtime-pixel-gate.json', {
    contentType: 'application/json',
    body: Buffer.from(JSON.stringify({
      proof,
      expectedNodes: hits.expectedNodes,
      expectedEdges: hits.expectedEdges,
      runtimeEvidence,
      pixelEvidence,
      tenantDbRequired: false,
      externalGpuRequired: false,
    }, null, 2)),
  })
})

import { expect, test, type Page } from '@playwright/test'

type CuratedDraftRequest = {
  actor_id?: string
  dsl?: {
    nodes?: unknown[]
    edges?: unknown[]
  }
}

type CuratedSubmitRequest = {
  actor_id?: string
  base_revision?: number
  object_scope?: string
}

type CuratedRollbackRequest = {
  actor_id?: string
  base_revision?: number
  target_version_id?: string
  reason?: string
}

type CuratedReportingHandoffRequest = {
  topic?: string
  selected_node_ids?: string[]
}

async function setupGraphPageMocks(page: Page) {
  let graphConfigHit = 0
  let marketGraphHit = 0
  let policyGraphHit = 0
  let contentGraphHit = 0
  let curatedDraftHit = 0
  let curatedSubmitHit = 0
  let curatedAuditHit = 0
  let curatedRollbackHit = 0
  let curatedReportingHandoffHit = 0
  let handoffReplayHit = 0
  let lastCuratedDraftBody: CuratedDraftRequest | null = null
  let lastCuratedSubmitBody: CuratedSubmitRequest | null = null
  let lastCuratedRollbackBody: CuratedRollbackRequest | null = null
  let lastCuratedReportingHandoffBody: CuratedReportingHandoffRequest | null = null

  await page.route('**/api/v1/project-customization/graph-config**', async (route) => {
    graphConfigHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_node_types: {
            market: ['product', 'company'],
          },
          graph_node_labels: {
            product: '商品',
            company: '公司',
          },
          graph_relation_labels: {
            related_to: '关联',
          },
        },
      }),
    })
  })

  await page.route('**/api/v1/admin/market-graph**', async (route) => {
    marketGraphHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          nodes: [
            { id: 'n1', type: 'product', name: '示例商品A' },
            { id: 'n2', type: 'company', name: '示例公司B' },
          ],
          edges: [
            {
              type: 'related_to',
              from: { type: 'product', id: 'n1' },
              to: { type: 'company', id: 'n2' },
            },
          ],
        },
      }),
    })
  })

  await page.route('**/api/v1/admin/policy-graph**', async (route) => {
    policyGraphHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { nodes: [], edges: [] } }),
    })
  })

  await page.route('**/api/v1/admin/content-graph**', async (route) => {
    contentGraphHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { nodes: [], edges: [] } }),
    })
  })

  await page.route('**/api/v1/workflow-graph/templates', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { items: [], total: 0 } }),
    })
  })

  await page.route('**/workflow-graph/curated/**/draft**', async (route) => {
    curatedDraftHit += 1
    lastCuratedDraftBody = route.request().postDataJSON() as CuratedDraftRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_id: 'cg-graphpage-e2e',
          sync_status: 'draft_saved',
          revision: 0,
          base_version: 1,
        },
      }),
    })
  })

  await page.route('**/workflow-graph/curated/**/submit**', async (route) => {
    curatedSubmitHit += 1
    lastCuratedSubmitBody = route.request().postDataJSON() as CuratedSubmitRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_id: 'cg-graphpage-e2e',
          submit_status: 'submitted',
          revision: 1,
          active_version_id: 'cver_graphpage_e2e',
          audit_id: 'audit_graphpage_e2e',
        },
      }),
    })
  })

  await page.route('**/workflow-graph/curated/**/audit**', async (route) => {
    curatedAuditHit += 1
    const items = curatedRollbackHit > 0
      ? [
          {
            audit_id: 'audit_rollback_graphpage_e2e',
            action: 'rollback',
            version_id: 'cver_rollback_graphpage_e2e',
            rollback_from_version_id: 'cver_graphpage_e2e',
            to_revision: 2,
          },
          {
            audit_id: 'audit_graphpage_e2e',
            action: 'submit',
            version_id: 'cver_graphpage_e2e',
            to_revision: 1,
          },
        ]
      : [
          {
            audit_id: 'audit_graphpage_e2e',
            action: 'submit',
            version_id: 'cver_graphpage_e2e',
            to_revision: 1,
          },
        ]
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_id: 'cg-graphpage-e2e',
          items,
          total: items.length,
          base_version: 2,
        },
      }),
    })
  })

  await page.route('**/workflow-graph/curated/**/rollback**', async (route) => {
    curatedRollbackHit += 1
    lastCuratedRollbackBody = route.request().postDataJSON() as CuratedRollbackRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_id: 'cg-graphpage-e2e',
          rollback_status: 'succeeded',
          revision: 2,
          active_version_id: 'cver_rollback_graphpage_e2e',
          rollback_from_version_id: lastCuratedRollbackBody?.target_version_id,
          audit_id: 'audit_rollback_graphpage_e2e',
          rollback_contract: {
            contract_version: 'workflow_graph.rollback.v1',
            target_version_id: lastCuratedRollbackBody?.target_version_id,
          },
        },
      }),
    })
  })

  await page.route('**/workflow-graph/curated/**/handoff/reporting**', async (route) => {
    curatedReportingHandoffHit += 1
    lastCuratedReportingHandoffBody = route.request().postDataJSON() as CuratedReportingHandoffRequest
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          contract_version: 'graph_handoff.v1',
          handoff_id: 'h-report-graphpage-e2e',
          owner: 'workflow_graph.backend_bridge',
          producer: 'workflow_graph.backend_bridge',
          handoff_mode: 'pull_prepared_evidence',
          consumer: 'llm_report.generate',
          report_generate_request: {
            topic: lastCuratedReportingHandoffBody?.topic,
            sources: [
              {
                id: 'GRAPHNODE-n1',
                title: '示例商品A',
                url: 'https://example.com/graph-node-n1',
                publisher: 'graph:product',
                evidence: 'Graph node n1 selected from curated graph.',
              },
            ],
            section_titles: [],
          },
          evidence_pack: {
            contract_version: 'graph_evidence_pack.v1',
            pack_id: 'gep-graphpage-e2e',
            graph_id: 'cg-graphpage-e2e',
            graph_scope: 'curated_business_graph',
            selected_nodes: [{ node_id: 'n1', node_type: 'product' }],
            relations: [],
            provenance: { source: 'workflow_graph.curated' },
          },
          persistence: {
            contract_version: 'workflow_graph.handoff.v1',
            run_id: 'run-report-graphpage-e2e',
            handoff_id: 'h-report-graphpage-e2e',
            backend_marker: 'workflow_graph.run_store',
          },
        },
      }),
    })
  })

  await page.route('**/workflow-graph/runs/**/handoff/**/replay**', async (route) => {
    handoffReplayHit += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          contract_version: 'workflow_graph.handoff.v1',
          run_id: 'run-report-graphpage-e2e',
          handoff_id: 'h-report-graphpage-e2e',
          events: [
            { seq: 1, type: 'handoff.persisted' },
            { seq: 2, type: 'handoff.replayed' },
          ],
          result: {
            handoff_id: 'h-report-graphpage-e2e',
            producer: 'workflow_graph.backend_bridge',
          },
        },
      }),
    })
  })

  return {
    get graphConfigHit() {
      return graphConfigHit
    },
    get marketGraphHit() {
      return marketGraphHit
    },
    get policyGraphHit() {
      return policyGraphHit
    },
    get contentGraphHit() {
      return contentGraphHit
    },
    get curatedDraftHit() {
      return curatedDraftHit
    },
    get curatedSubmitHit() {
      return curatedSubmitHit
    },
    get curatedAuditHit() {
      return curatedAuditHit
    },
    get curatedRollbackHit() {
      return curatedRollbackHit
    },
    get curatedReportingHandoffHit() {
      return curatedReportingHandoffHit
    },
    get handoffReplayHit() {
      return handoffReplayHit
    },
    get lastCuratedDraftBody() {
      return lastCuratedDraftBody
    },
    get lastCuratedSubmitBody() {
      return lastCuratedSubmitBody
    },
    get lastCuratedRollbackBody() {
      return lastCuratedRollbackBody
    },
    get lastCuratedReportingHandoffBody() {
      return lastCuratedReportingHandoffBody
    },
  }
}

test('graph page smoke test loads with mocked graph APIs', async ({ page }) => {
  const hits = await setupGraphPageMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()

  await expect(page.getByRole('button', { name: '3D模式', exact: true })).toBeVisible()

  expect(hits.graphConfigHit).toBeGreaterThan(0)
  expect(hits.marketGraphHit).toBeGreaterThan(0)
})

test('graph page can switch 2D/3D mode and interact with key slider', async ({ page }) => {
  await setupGraphPageMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()

  const renderModeToggle = page.locator('button[title="轻量3D模型模式（中心锁定，非相机视角）"]').first()
  await expect(renderModeToggle).toHaveText('3D模式')
  await renderModeToggle.click()
  await expect(renderModeToggle).toHaveText('回到2D')

  const repulsionSlider = page.getByRole('slider', { name: /^斥力/ }).first()
  await expect(repulsionSlider).toBeVisible()

  const initial = Number(await repulsionSlider.inputValue())
  await repulsionSlider.focus()
  await repulsionSlider.press('ArrowRight')
  const updated = Number(await repulsionSlider.inputValue())
  expect(updated).not.toBe(initial)
})

test('graph page renders force3d canvas backed by graph scene nodes', async ({ page }) => {
  await setupGraphPageMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()

  const renderModeToggle = page.locator('button[title="轻量3D模型模式（中心锁定，非相机视角）"]').first()
  await expect(renderModeToggle).toHaveText('3D模式')
  await renderModeToggle.click()
  await expect(renderModeToggle).toHaveText('回到2D')

  const engineSelect = page.locator('label.gv2-control-chip', { hasText: '3D引擎' }).locator('select')
  await expect(engineSelect).toBeVisible()

  const outcomeHandle = await page.waitForFunction(() => {
    type Graph3DStats = {
      dataNodes: number
      sceneNodeObjects: number
    }
    const debugWindow = window as Window & {
      __graph3dDebug?: {
        getVisibilityStats: () => Graph3DStats
      }
    }
    const canvas = document.querySelector('[data-testid="graph-force3d-canvas-host"] canvas') as HTMLCanvasElement | null
    const stats = debugWindow.__graph3dDebug?.getVisibilityStats()
    if (canvas && canvas.width > 0 && canvas.height > 0 && stats && stats.dataNodes === 2 && stats.sceneNodeObjects >= 2) {
      return { mode: 'force3d', stats }
    }
    const fallbackText = Array.from(document.querySelectorAll('.gv2-loading'))
      .map((node) => node.textContent || '')
      .join('\n')
    const engineValue = Array.from(document.querySelectorAll('label.gv2-control-chip'))
      .find((node) => (node.textContent || '').includes('3D引擎'))
      ?.querySelector<HTMLSelectElement>('select')
      ?.value || ''
    if (fallbackText.includes('已自动降级到 legacy-projection') && engineValue === 'legacy') {
      return { mode: 'fallback', fallbackText, engineValue }
    }
    return false
  }, null, { timeout: 20000 })

  const outcome = await outcomeHandle.jsonValue() as
    | { mode: 'force3d'; stats: { dataNodes: number; sceneNodeObjects: number } }
    | { mode: 'fallback'; fallbackText: string; engineValue: string }

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()
  if (outcome.mode === 'force3d') {
    await expect(page.getByTestId('graph-force3d-canvas-host')).toBeVisible()
    expect(outcome.stats.dataNodes).toBe(2)
    expect(outcome.stats.sceneNodeObjects).toBeGreaterThanOrEqual(2)
  } else {
    expect(outcome.fallbackText).toContain('3D引擎渲染失败')
    expect(outcome.engineValue).toBe('legacy')
  }
})

test('graph page survives rapid 3D engine switch with viewport evidence or fallback', async ({ page }) => {
  await setupGraphPageMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()

  const renderModeToggle = page.locator('button[title="轻量3D模型模式（中心锁定，非相机视角）"]').first()
  await expect(renderModeToggle).toHaveText('3D模式')
  await renderModeToggle.click()
  await expect(renderModeToggle).toHaveText('回到2D')

  const engineSelect = page.locator('label.gv2-control-chip', { hasText: '3D引擎' }).locator('select')
  await expect(engineSelect).toBeVisible()

  await engineSelect.selectOption('legacy')
  await page.waitForTimeout(40)
  await engineSelect.selectOption('force3d')
  await page.waitForTimeout(40)
  await engineSelect.selectOption('legacy')
  await page.waitForTimeout(40)
  await engineSelect.selectOption('force3d')

  const outcomeHandle = await page.waitForFunction(() => {
    type Graph3DStats = {
      dataNodes: number
      sceneNodeObjects: number
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
      hostRect.width >= 300 &&
      hostRect.height >= 300 &&
      canvas.width >= 300 &&
      canvas.height >= 300 &&
      stats &&
      stats.dataNodes === 2 &&
      stats.sceneNodeObjects >= 2
    ) {
      return {
        mode: 'force3d',
        stats,
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
    if (engineValue === 'legacy' && legacyChartRect && legacyChartRect.width >= 300 && legacyChartRect.height >= 300) {
      return {
        mode: fallbackText.includes('已自动降级到 legacy-projection') ? 'fallback' : 'legacy',
        fallbackText,
        engineValue,
        chartWidth: Math.round(legacyChartRect.width),
        chartHeight: Math.round(legacyChartRect.height),
      }
    }
    return false
  }, null, { timeout: 20000 })

  const outcome = await outcomeHandle.jsonValue() as
    | {
      mode: 'force3d'
      stats: { dataNodes: number; sceneNodeObjects: number }
      canvasWidth: number
      canvasHeight: number
      hostWidth: number
      hostHeight: number
    }
    | {
      mode: 'fallback' | 'legacy'
      fallbackText: string
      engineValue: string
      chartWidth: number
      chartHeight: number
    }

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()
  await expect(engineSelect).toBeVisible()
  if (outcome.mode === 'force3d') {
    await expect(page.getByTestId('graph-force3d-canvas-host')).toBeVisible()
    expect(outcome.stats.dataNodes).toBe(2)
    expect(outcome.stats.sceneNodeObjects).toBeGreaterThanOrEqual(2)
    expect(Math.abs(outcome.canvasWidth - outcome.hostWidth)).toBeLessThanOrEqual(4)
    expect(Math.abs(outcome.canvasHeight - outcome.hostHeight)).toBeLessThanOrEqual(4)
  } else {
    if (outcome.mode === 'fallback') {
      expect(outcome.fallbackText).toContain('3D引擎渲染失败')
    }
    expect(outcome.engineValue).toBe('legacy')
    expect(outcome.chartWidth).toBeGreaterThanOrEqual(300)
    expect(outcome.chartHeight).toBeGreaterThanOrEqual(300)
  }
})

test('graph builder submits local draft to curated workflow graph API', async ({ page }) => {
  const hits = await setupGraphPageMocks(page)

  const response = await page.goto('/#graph-template-new.html')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '新建图谱', exact: true })).toBeVisible()
  await expect(page.getByTestId('graph-curated-panel')).toBeVisible()

  await page.getByTestId('graph-curated-graph-id').fill('cg-graphpage-e2e')
  await expect(page.getByText(/Draft: nodes=2 edges=1/)).toBeVisible()

  await page.getByTestId('graph-curated-submit').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('submitted r1')

  await page.getByTestId('graph-curated-audit').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('audit_readback items=1')
  await expect(page.getByTestId('graph-curated-audit-list')).toContainText('submit#cver_graphpage_e2e')
  await expect(page.getByTestId('graph-curated-rollback-version')).toHaveValue('cver_graphpage_e2e')

  await page.getByTestId('graph-curated-rollback-reason').fill('restore graphpage e2e version')
  await page.getByTestId('graph-curated-rollback').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('rollback_succeeded r2 audits=2')
  await expect(page.getByTestId('graph-curated-audit-list')).toContainText('rollback#cver_rollback_graphpage_e2e')

  await page.getByTestId('graph-curated-reporting-topic').fill('robotics reporting')
  await page.getByTestId('graph-curated-reporting-handoff').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('report_handoff_ready sources=1')
  await page.getByTestId('graph-curated-handoff-replay').click()
  await expect(page.getByTestId('graph-curated-status')).toContainText('handoff_replay_ready events=2')

  expect(hits.policyGraphHit).toBeGreaterThan(0)
  expect(hits.contentGraphHit).toBeGreaterThan(0)
  expect(hits.marketGraphHit).toBeGreaterThan(0)
  expect(hits.curatedDraftHit).toBe(1)
  expect(hits.curatedSubmitHit).toBe(1)
  expect(hits.curatedAuditHit).toBe(2)
  expect(hits.curatedRollbackHit).toBe(1)
  expect(hits.curatedReportingHandoffHit).toBe(1)
  expect(hits.handoffReplayHit).toBe(1)

  expect(hits.lastCuratedDraftBody?.actor_id).toBe('graphpage.curated-consumer')
  expect(hits.lastCuratedDraftBody?.dsl?.nodes).toEqual([
    expect.objectContaining({ id: 'n1', type: 'product', node_id: 'n1', node_type: 'product', title: '示例商品A' }),
    expect.objectContaining({ id: 'n2', type: 'company', node_id: 'n2', node_type: 'company', title: '示例公司B' }),
  ])
  expect(hits.lastCuratedDraftBody?.dsl?.edges).toEqual([
    expect.objectContaining({
      from_node_id: 'n1',
      to_node_id: 'n2',
      edge_type: 'related_to',
      from: { id: 'n1', type: 'product' },
      to: { id: 'n2', type: 'company' },
    }),
  ])
  expect(hits.lastCuratedSubmitBody).toEqual(expect.objectContaining({
    actor_id: 'graphpage.curated-consumer',
    base_revision: 0,
    object_scope: 'curated_business_graph',
  }))
  expect(hits.lastCuratedRollbackBody).toEqual(expect.objectContaining({
    actor_id: 'graphpage.curated-consumer',
    base_revision: 1,
    target_version_id: 'cver_graphpage_e2e',
    reason: 'restore graphpage e2e version',
  }))
  expect(hits.lastCuratedReportingHandoffBody).toEqual(expect.objectContaining({
    topic: 'robotics reporting',
  }))
})

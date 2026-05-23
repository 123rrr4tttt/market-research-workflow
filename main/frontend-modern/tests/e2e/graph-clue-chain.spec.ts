import { expect, test, type Page } from '@playwright/test'

type ClueChainDecisionRequest = {
  action?: string
  decided_by?: string
}

type ClueChainCreateRequest = {
  root_node_ids?: string[]
  metadata?: {
    seed_nodes?: Array<{ node_id?: string; label?: string }>
    graph_context?: {
      selected_count?: number
      visible_nodes?: number
    }
  }
}

type ClueChainExpandRequest = {
  mode?: string
  frontier_node_ids?: string[]
}

type GraphFixture = {
  nodes: Array<Record<string, unknown>>
  edges: Array<Record<string, unknown>>
}

const baseChain = {
  chain_id: 'chain-graph-e2e',
  title: '市场图谱 · 示例商品A',
  status: 'open',
  graph_type: 'market',
  seed_nodes: [
    { node_id: 'n1', node_type: 'MarketData', label: '示例商品A', entry_id: 'n1' },
    { node_id: 'n2', node_type: 'Segment', label: '示例公司B', entry_id: 'n2' },
  ],
  frontier: [
    { node_id: 'n1', node_type: 'product', label: '示例商品A', reason: 'seed' },
  ],
  hops: [],
  candidates: [
    {
      candidate_id: 'candidate-1',
      label: '渠道价差线索',
      node_type: 'MarketData',
      status: 'pending',
      confidence: 0.82,
      reason: 'source-library fixture matched a recurring price-spread clue',
      evidence_ids: ['evidence-1'],
    },
  ],
  evidence: [
    {
      evidence_id: 'evidence-1',
      title: 'Filed contract source',
      source_type: 'source_library',
      url: 'https://example.test/contracts',
      summary: 'Distributor filings describe a contract chain tied to 示例商品A.',
      node_ids: ['n1'],
      candidate_ids: ['candidate-1'],
      created_at: '2026-05-22T12:00:00Z',
    },
  ],
  blockers: [],
}

function chainFixture(overrides: Partial<typeof baseChain> = {}): typeof baseChain {
  return {
    ...JSON.parse(JSON.stringify(baseChain)),
    ...overrides,
  }
}

function denseGraphFixture(): GraphFixture {
  const nodes = Array.from({ length: 24 }, (_, index) => {
    const id = `n${index + 1}`
    return {
      id,
      type: index % 2 === 0 ? 'MarketData' : 'Segment',
      name: `密集图谱节点 ${index + 1}`,
    }
  })
  const edges = Array.from({ length: 36 }, (_, index) => {
    const from = (index % nodes.length) + 1
    const to = ((index + 3) % nodes.length) + 1
    return {
      type: 'related_to',
      from: { type: from % 2 === 1 ? 'MarketData' : 'Segment', id: `n${from}` },
      to: { type: to % 2 === 1 ? 'MarketData' : 'Segment', id: `n${to}` },
    }
  })
  return { nodes, edges }
}

async function setupGraphMocks(
  page: Page,
  options: {
    createdChain?: typeof baseChain
    expandedChain?: typeof baseChain
    graphData?: GraphFixture
    reviewedChain?: typeof baseChain
  } = {},
) {
  let createBody: ClueChainCreateRequest | null = null
  let decisionBody: ClueChainDecisionRequest | null = null
  let expandBody: ClueChainExpandRequest | null = null
  let expandHit = 0
  const createdChain = options.createdChain || chainFixture()
  const expandedChain = options.expandedChain || chainFixture({
    hops: [
      {
        hop_id: 'hop-1',
        mode: 'external_search',
        status: 'blocked',
        query: 'external provider expansion',
        evidence_ids: ['evidence-1'],
        candidate_ids: ['candidate-1'],
        blockers: ['provider_credentials_missing'],
      },
    ],
    blockers: [
      {
        blocker_id: 'blocker-1',
        severity: 'warning',
        message: 'External search provider is blocked until credentials are present.',
        source: 'search_provider',
      },
    ],
  })
  const reviewedChain = options.reviewedChain || chainFixture({
    candidates: [
      {
        ...baseChain.candidates[0],
        status: 'promoted',
      },
    ],
  })
  const graphData = options.graphData || {
    nodes: [
      { id: 'n1', type: 'MarketData', name: '示例商品A' },
      { id: 'n2', type: 'Segment', name: '示例公司B' },
    ],
    edges: [
      {
        type: 'related_to',
        from: { type: 'MarketData', id: 'n1' },
        to: { type: 'Segment', id: 'n2' },
      },
    ],
  }

  await page.route('**/api/v1/project-customization/graph-config**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: {
          graph_node_types: { market: ['MarketData', 'Segment'] },
          graph_node_labels: { MarketData: '市场数据', Segment: '细分市场' },
          graph_relation_labels: { related_to: '关联' },
        },
      }),
    })
  })

  await page.route('**/api/v1/admin/market-graph**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok',
        data: graphData,
      }),
    })
  })

  await page.route('**/api/v1/clue-chains**', async (route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()
    if (url.pathname === '/api/v1/clue-chains' && method === 'POST') {
      createBody = route.request().postDataJSON() as ClueChainCreateRequest
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok', data: { chain: createdChain } }),
      })
      return
    }
    if (url.pathname === '/api/v1/clue-chains/chain-graph-e2e/expand' && method === 'POST') {
      expandHit += 1
      expandBody = route.request().postDataJSON() as ClueChainExpandRequest
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: { chain: expandedChain },
        }),
      })
      return
    }
    if (url.pathname === '/api/v1/clue-chains/chain-graph-e2e/candidates/candidate-1/decision' && method === 'POST') {
      decisionBody = route.request().postDataJSON() as ClueChainDecisionRequest
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: { chain: reviewedChain },
        }),
      })
      return
    }
    await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ status: 'error' }) })
  })

  return {
    get createBody() {
      return createBody
    },
    get decisionBody() {
      return decisionBody
    },
    get expandBody() {
      return expandBody
    },
    get expandHit() {
      return expandHit
    },
  }
}

async function gotoGraphPage(page: Page) {
  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()
  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()
}

async function selectGraphNode(page: Page, nodeId: string) {
  await expect(page.getByTestId('graph-chart-2d')).toBeVisible()
  const selected = await page.waitForFunction((id) => window.__graphPageE2E?.selectNode(id) === true, nodeId)
  expect(await selected.jsonValue()).toBe(true)
}

test('graph page creates a clue chain from selected graph node seeds', async ({ page }) => {
  const hits = await setupGraphMocks(page)
  await gotoGraphPage(page)

  await selectGraphNode(page, 'n1')
  await expect(page.getByTestId('graph-selected-node-card')).toContainText('示例商品A')
  await expect(page.getByTestId('graph-create-clue-chain')).toContainText('Chain（1）')

  const createChainButton = page.getByTestId('graph-create-clue-chain')
  await expect(createChainButton).toBeEnabled()
  await createChainButton.click()

  await expect(page.getByTestId('clue-chain-inspector')).toBeVisible()
  await expect(page.getByTestId('clue-chain-candidate-queue')).toContainText('渠道价差线索')
  expect(hits.createBody?.root_node_ids).toEqual(['n1'])
  expect(hits.createBody?.metadata?.seed_nodes?.map((node) => node.node_id)).toEqual(['n1'])
  expect(hits.createBody?.metadata?.graph_context?.selected_count).toBe(1)
  expect(hits.createBody?.metadata?.graph_context?.visible_nodes).toBe(2)
})

test('graph page keeps clue chain creation stable on a dense graph route', async ({ page }) => {
  const graphData = denseGraphFixture()
  const hits = await setupGraphMocks(page, { graphData })
  await gotoGraphPage(page)

  await expect(page.getByTestId('graph-create-clue-chain')).toContainText('Chain（3）')
  await page.getByTestId('graph-create-clue-chain').click()
  await expect(page.getByTestId('clue-chain-inspector')).toBeVisible()

  expect(hits.createBody?.root_node_ids).toEqual(['n1', 'n2', 'n3'])
  expect(hits.createBody?.metadata?.seed_nodes?.map((node) => node.node_id)).toEqual(['n1', 'n2', 'n3'])
  expect(hits.createBody?.metadata?.graph_context?.selected_count).toBe(0)
  expect(hits.createBody?.metadata?.graph_context?.visible_nodes).toBe(graphData.nodes.length)
})

test('graph page surfaces blocked provider hops and evidence drawer details', async ({ page }) => {
  const hits = await setupGraphMocks(page)
  await gotoGraphPage(page)

  await page.getByTestId('graph-create-clue-chain').click()
  await expect(page.getByTestId('clue-chain-inspector')).toBeVisible()

  await page.getByRole('button', { name: /Search Hop/ }).click()
  await expect(page.getByTestId('clue-chain-hop-list')).toContainText('External Search')
  await expect(page.getByTestId('clue-chain-hop-list')).toContainText('external provider expansion')
  await expect(page.getByTestId('clue-chain-inspector')).toContainText('External search provider is blocked')
  await expect(page.getByTestId('clue-chain-inspector')).toContainText('search_provider')
  expect(hits.expandHit).toBe(1)
  expect(hits.expandBody).toEqual(expect.objectContaining({
    mode: 'external_search',
    frontier_node_ids: ['n1'],
  }))

  await page.getByTestId('clue-chain-evidence-evidence-1').first().click()
  await expect(page.getByTestId('clue-chain-evidence-drawer')).toContainText('Filed contract source')
  await expect(page.getByTestId('clue-chain-evidence-drawer')).toContainText('Distributor filings describe')
})

test('graph page renders reviewed candidate decisions as non-pending state', async ({ page }) => {
  const hits = await setupGraphMocks(page)
  await gotoGraphPage(page)

  await page.getByTestId('graph-create-clue-chain').click()
  await expect(page.getByTestId('clue-chain-candidate-queue')).toContainText('待审核')

  await page.getByTestId('clue-chain-promote-candidate-1').click()
  await expect(page.getByTestId('clue-chain-candidate-queue')).toContainText('已提升')
  await expect(page.getByTestId('clue-chain-promote-candidate-1')).toBeDisabled()
  await expect(page.getByTestId('clue-chain-reject-candidate-1')).toBeDisabled()
  expect(hits.decisionBody).toEqual(expect.objectContaining({
    action: 'promote',
    decided_by: 'graphpage.clue-chain-ui',
  }))
})

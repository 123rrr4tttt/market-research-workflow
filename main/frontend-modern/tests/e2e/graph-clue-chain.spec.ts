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

async function setupGraphMocks(page: Page) {
  let createBody: ClueChainCreateRequest | null = null
  let decisionBody: ClueChainDecisionRequest | null = null
  let expandHit = 0

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
        data: {
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
        },
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
        body: JSON.stringify({ status: 'ok', data: { chain: baseChain } }),
      })
      return
    }
    if (url.pathname === '/api/v1/clue-chains/chain-graph-e2e/expand' && method === 'POST') {
      expandHit += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok',
          data: {
            chain: {
              ...baseChain,
              hops: [
                {
                  hop_id: 'hop-1',
                  mode: 'source_library',
                  status: 'completed',
                  query: 'commodity margin expansion',
                  evidence_ids: ['evidence-1'],
                  candidate_ids: ['candidate-1'],
                  finished_at: '2026-05-22T12:03:00Z',
                },
              ],
              blockers: [
                {
                  blocker_id: 'blocker-1',
                  severity: 'warning',
                  message: 'External search is fixture-gated until provider credentials are present.',
                  source: 'search_provider',
                },
              ],
            },
          },
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
          data: {
            chain: {
              ...baseChain,
              hops: [
                {
                  hop_id: 'hop-1',
                  mode: 'source_library',
                  status: 'completed',
                  query: 'commodity margin expansion',
                  evidence_ids: ['evidence-1'],
                  candidate_ids: ['candidate-1'],
                },
              ],
              candidates: [
                {
                  ...baseChain.candidates[0],
                  status: 'promoted',
                },
              ],
            },
          },
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
    get expandHit() {
      return expandHit
    },
  }
}

test('graph page can create and review a clue chain with mocked APIs', async ({ page }) => {
  const hits = await setupGraphMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()
  const createChainButton = page.getByTestId('graph-create-clue-chain')
  await expect(createChainButton).toBeEnabled()
  await createChainButton.click()

  await expect(page.getByTestId('clue-chain-inspector')).toBeVisible()
  await expect(page.getByTestId('clue-chain-candidate-queue')).toContainText('渠道价差线索')
  expect(hits.createBody?.root_node_ids).toEqual(['n1', 'n2'])
  expect(hits.createBody?.metadata?.seed_nodes?.map((node) => node.node_id)).toEqual(['n1', 'n2'])
  expect(hits.createBody?.metadata?.graph_context?.visible_nodes).toBe(2)

  await page.getByRole('button', { name: /Source Hop/ }).click()
  await expect(page.getByTestId('clue-chain-hop-list')).toContainText('commodity margin expansion')
  await expect(page.getByTestId('clue-chain-inspector')).toContainText('External search is fixture-gated')
  expect(hits.expandHit).toBe(1)

  await page.getByRole('button', { name: /Filed contract source/ }).first().click()
  await expect(page.getByTestId('clue-chain-evidence-drawer')).toContainText('Distributor filings describe')

  await page.getByTestId('clue-chain-promote-candidate-1').click()
  await expect(page.getByTestId('clue-chain-candidate-queue')).toContainText('已提升')
  expect(hits.decisionBody).toEqual(expect.objectContaining({
    action: 'promote',
    decided_by: 'graphpage.clue-chain-ui',
  }))
})

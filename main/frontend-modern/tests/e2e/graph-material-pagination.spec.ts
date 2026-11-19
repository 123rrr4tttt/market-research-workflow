import { expect, test } from '@playwright/test'

for (const scenario of [
  { name: 'limit 150 reads distinct rows across two fixed pages', total: 200, emptySecond: false, expected: 150 },
  { name: 'total ends the final page', total: 140, emptySecond: false, expected: 140 },
  { name: 'empty page ends an incomplete source', total: 200, emptySecond: true, expected: 100 },
]) {
  test(scenario.name, async ({ page }) => {
    const requests: Array<{ page: number; size: number }> = []
    await page.addInitScript(() => localStorage.setItem('market_project_key', 'pagination_test'))
    await page.route('**/api/v1/**', async (route) => {
      const url = new URL(route.request().url())
      const ok = (data: unknown) => route.fulfill({
        status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok', data }),
      })
      if (url.pathname === '/api/v1/information-topology/topologies') return ok({ items: [], total: 0 })
      if (url.pathname === '/api/v1/admin/materials/list') {
        const input = route.request().postDataJSON() as { page: number; page_size: number }
        const pageIndex = input.page
        const size = input.page_size
        requests.push({ page: pageIndex, size })
        const offset = (pageIndex - 1) * size
        const count = scenario.emptySecond && pageIndex === 2 ? 0 : Math.min(size, scenario.total - offset)
        return ok({
          items: Array.from({ length: count }, (_, index) => ({
            material_id: offset + index + 1, title: `Material ${offset + index + 1}`, material_type: 'market_info',
          })), total: scenario.total, page: pageIndex, page_size: size,
        })
      }
      if (url.pathname === '/api/v1/admin/market-graph') return ok({
        graph_schema_version: 'v1', nodes: [{ type: 'MarketData', id: '1', properties: {} }], edges: [],
      })
      return ok({ items: [], total: 0 })
    })
    await page.goto('/')
    const snapshot = await page.evaluate(async () => {
      const adapterPath = '/src/pages/graph/realizer/sourceAdapter.ts'
      const definitionPath = '/src/pages/graph/realizer/definitions.ts'
      const { readGraphProjection } = await import(adapterPath) as typeof import('../../src/pages/graph/realizer/sourceAdapter')
      const { GRAPH_PROJECTIONS } = await import(definitionPath) as typeof import('../../src/pages/graph/realizer/definitions')
      const graph = await readGraphProjection('pagination_test', GRAPH_PROJECTIONS.graphMarket, {
        startDate: '', endDate: '', state: '', policyType: '', platform: '', topic: '', game: '', limit: 150,
      })
      return {
        materialIds: graph.nodes.filter((node) => node.type === 'material').map((node) => node.material_id),
        roleTypes: graph.nodes.filter((node) => node.type !== 'material').map((node) => node.type),
      }
    })
    expect(requests).toEqual([{ page: 1, size: 100 }, { page: 2, size: 100 }])
    expect(snapshot.materialIds).toEqual(Array.from({ length: scenario.expected }, (_, index) => index + 1))
    expect(snapshot.roleTypes).toContain('MarketData')
  })
}

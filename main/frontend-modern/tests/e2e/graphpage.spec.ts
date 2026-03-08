import { expect, test, type Page } from '@playwright/test'

async function setupGraphPageMocks(page: Page) {
  let graphConfigHit = 0
  let marketGraphHit = 0

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

  return {
    get graphConfigHit() {
      return graphConfigHit
    },
    get marketGraphHit() {
      return marketGraphHit
    },
  }
}

test('graph page smoke test loads with mocked graph APIs', async ({ page }) => {
  const hits = await setupGraphPageMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 2, name: '市场图谱', exact: true })).toBeVisible()

  await expect(page.getByRole('button', { name: '3D模式', exact: true })).toBeVisible()

  expect(hits.graphConfigHit).toBeGreaterThan(0)
  expect(hits.marketGraphHit).toBeGreaterThan(0)
})

test('graph page can switch 2D/3D mode and interact with key slider', async ({ page }) => {
  await setupGraphPageMocks(page)

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await expect(page.getByRole('heading', { level: 2, name: '市场图谱', exact: true })).toBeVisible()

  const renderModeToggle = page.locator('button[title="轻量3D模型模式（中心锁定，非相机视角）"]').first()
  await expect(renderModeToggle).toHaveText('3D模式')
  await renderModeToggle.click()
  await expect(renderModeToggle).toHaveText('回到2D')

  const repulsionSlider = page.locator('label:has-text("斥力") input[type="range"]').first()
  await expect(repulsionSlider).toBeVisible()

  const initial = Number(await repulsionSlider.inputValue())
  await repulsionSlider.focus()
  await repulsionSlider.press('ArrowRight')
  const updated = Number(await repulsionSlider.inputValue())
  expect(updated).not.toBe(initial)
})

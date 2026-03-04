import { expect, test, type Page } from '@playwright/test'

type VisibilityStats = {
  dataNodes: number
  sceneNodeObjects: number
  emptyDataNodes: number
  emptySceneNodeObjects: number
}

async function waitForGraphReady(page: Page) {
  await expect(page.getByRole('button', { name: '3D模式' }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '刷新' }).first()).toBeEnabled()
  await expect(page.locator('.gv2-loading')).toHaveCount(0)
}

async function clickStable(page: Page, name: string) {
  const locator = page.getByRole('button', { name }).first()
  await locator.waitFor({ state: 'visible' })
  await locator.click({ force: true })
}

async function switchTo3D(page: Page) {
  const to3D = page.getByRole('button', { name: '3D模式' }).first()
  if (await to3D.isVisible()) {
    await to3D.click({ force: true })
  }
  await expect(page.getByRole('button', { name: '回到2D' }).first()).toBeVisible()
}

async function enableFocusMode(page: Page) {
  await clickStable(page, '聚焦隐没')
}

async function readStats(page: Page) {
  return page.evaluate(() => {
    const api = window.__graph3dDebug
    if (!api?.getVisibilityStats) return null
    return api.getVisibilityStats() as VisibilityStats
  })
}

async function assertVisibilityContract(page: Page, graphType: 'product' | 'operation') {
  await page.goto(`/#graph.html?type=${graphType}`)
  await waitForGraphReady(page)
  await switchTo3D(page)
  await enableFocusMode(page)
  await page.waitForTimeout(1200)

  const stats = await readStats(page)
  expect(stats).toBeTruthy()
  if (!stats) return

  expect(stats.dataNodes).toBeGreaterThan(0)
  expect(stats.sceneNodeObjects).toBeGreaterThan(0)
  expect(stats.sceneNodeObjects).toBeGreaterThanOrEqual(Math.floor(stats.dataNodes * 0.95))
  expect(stats.emptySceneNodeObjects).toBeGreaterThanOrEqual(Math.floor(stats.emptyDataNodes * 0.95))
}

test('graph visibility contract for product and operation in 3d focus mode', async ({ page }) => {
  await assertVisibilityContract(page, 'product')
  await assertVisibilityContract(page, 'operation')
})

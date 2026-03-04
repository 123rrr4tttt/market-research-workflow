import { expect, test, type Page } from '@playwright/test'

type VisibilityStats = {
  dataNodes: number
  sceneNodeObjects: number
  emptyDataNodes: number
  emptySceneNodeObjects: number
}

const GRAPH_CASES = [
  { name: 'product', navLabel: '商品图谱' },
  { name: 'operation', navLabel: '电商/经营图谱' },
]

async function openGraphByNav(page: Page, navLabel: string) {
  await page.goto('/')
  await page.getByRole('button', { name: navLabel, exact: true }).click()
}

async function ensureProjection3D(page: Page) {
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button')) as HTMLButtonElement[]
    const backTo2D = buttons.find((button) => button.textContent?.trim() === '回到2D')
    if (backTo2D) return
    const to3D = buttons.find((button) => button.textContent?.trim() === '3D模式')
    if (!to3D) throw new Error('3D mode button is unavailable')
    to3D.click()
  })
  await expect(page.getByRole('button', { name: '回到2D' })).toBeVisible()
}

async function ensureAutoFocusDimEnabled(page: Page) {
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button')) as HTMLButtonElement[]
    const autoFocus = buttons.find((button) => button.textContent?.trim() === '聚焦隐没')
    if (!autoFocus) throw new Error('auto-focus button is unavailable')
    if (!autoFocus.className.includes('is-off')) return
    autoFocus.click()
  })
  await expect
    .poll(async () => {
      return page.evaluate(() => {
        const buttons = Array.from(document.querySelectorAll('button')) as HTMLButtonElement[]
        const autoFocus = buttons.find((button) => button.textContent?.trim() === '聚焦隐没')
        if (!autoFocus) return false
        return !autoFocus.className.includes('is-off')
      })
    })
    .toBeTruthy()
}

async function readVisibilityStats(page: Page) {
  const stats = await page.evaluate(() => {
    const api = window.__graph3dDebug?.getVisibilityStats
    if (typeof api !== 'function') return null
    return api()
  })
  return stats as VisibilityStats | null
}

function assertCoverage(stats: VisibilityStats, graphName: string) {
  expect(stats.sceneNodeObjects, `${graphName}: sceneNodeObjects`).toBeGreaterThanOrEqual(stats.dataNodes * 0.95)
  expect(stats.emptySceneNodeObjects, `${graphName}: emptySceneNodeObjects`).toBeGreaterThanOrEqual(stats.emptyDataNodes * 0.95)
}

test.describe('graph 3d visibility contract', () => {
  for (const graphCase of GRAPH_CASES) {
    test(`${graphCase.name} graph keeps visible node-object coverage`, async ({ page }) => {
      await openGraphByNav(page, graphCase.navLabel)

      await expect
        .poll(async () => {
          const hasDebugApi = await page.evaluate(() => typeof window.__graph3dDebug?.getVisibilityStats === 'function')
          return hasDebugApi
        }, {
          timeout: 30000,
          message: `${graphCase.name}: waiting for window.__graph3dDebug.getVisibilityStats`,
        })
        .toBeTruthy()

      await ensureProjection3D(page)
      await ensureAutoFocusDimEnabled(page)

      await expect
        .poll(async () => {
          const stats = await readVisibilityStats(page)
          if (!stats) return null
          const ok = (
            stats.sceneNodeObjects >= stats.dataNodes * 0.95
            && stats.emptySceneNodeObjects >= stats.emptyDataNodes * 0.95
          )
          return ok ? stats : null
        }, {
          timeout: 30000,
          intervals: [400, 800, 1200],
          message: `${graphCase.name}: waiting for 3D visibility stats coverage`,
        })
        .not.toBeNull()

      const stats = await readVisibilityStats(page)
      if (!stats) {
        throw new Error(`${graphCase.name}: window.__graph3dDebug.getVisibilityStats is unavailable`)
      }
      assertCoverage(stats, graphCase.name)
    })
  }
})

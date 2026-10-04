import { expect, test } from '@playwright/test'

test('management surface renders the functorial business-chain guide', async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'default')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })

  await page.goto('/#/admin/projects')

  const guide = page.getByRole('region', { name: 'MRW 业务链条说明' })
  await expect(guide).toBeVisible()
  await expect(guide.locator('svg.business-chain-guide__graph')).toBeHidden()
  await guide.getByRole('button', { name: '展开说明' }).click()
  await expect(guide.getByText('把同一条业务运动投影为入口、变换、效果、证据与观察结果。').first()).toBeVisible()
  await expect(guide.locator('svg.business-chain-guide__graph')).toBeVisible()
  await expect(guide.getByText('采集与原始入库').first()).toBeVisible()
  await expect(guide.getByText('运行态与 Successor').first()).toBeVisible()

  await guide.getByRole('button', { name: '收起说明' }).click()
  await expect(guide.getByRole('button', { name: '展开说明' })).toBeVisible()
  await expect(guide.locator('svg.business-chain-guide__graph')).toBeHidden()
})

test('root management page embeds the business-chain graph in the current page', async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'default')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })

  await page.goto('/')

  const guide = page.getByRole('region', { name: 'MRW 业务链条说明' })
  await expect(guide).toBeVisible()
  await expect(guide.locator('svg.business-chain-guide__graph')).toBeHidden()
  await guide.getByRole('button', { name: '展开说明' }).click()
  await expect(guide.locator('svg.business-chain-guide__graph')).toBeVisible()
  await expect(guide.getByText('采集与原始入库').first()).toBeVisible()
})

test('mobile admin navigation keeps the selected route and title in sync', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.addInitScript(() => window.localStorage.setItem('app_locale_v1', 'zh-CN'))
  await page.goto('/#/admin/process')

  const menu = page.getByRole('button', { name: '管理导航' })
  await expect(menu).toHaveAttribute('aria-expanded', 'false')
  await menu.click()
  await expect(menu).toHaveAttribute('aria-expanded', 'true')
  await page.getByRole('button', { name: '项目与模板' }).click()

  await expect(page).toHaveURL(/#\/admin\/projects$/)
  await expect(page.locator('.kernel-admin__title-row h1')).toHaveText('项目与模板')
  await expect(menu).toHaveAttribute('aria-expanded', 'false')
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

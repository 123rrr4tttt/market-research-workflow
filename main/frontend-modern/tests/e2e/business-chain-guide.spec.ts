import { expect, test } from '@playwright/test'

test('management navigation opens the independent business guide', async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'default')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })

  await page.goto('/#/admin/projects')

  const guide = page.getByRole('region', { name: 'MRW 业务链条说明' })
  await expect(guide).toHaveCount(0)
  await page.getByRole('navigation', { name: '管理导航' }).getByRole('button', { name: '业务说明', exact: true }).click()
  await expect(page).toHaveURL(/#\/admin\/guide$/)
  await expect(guide).toBeVisible()
  await expect(guide.locator('svg.business-chain-guide__graph')).toBeHidden()
  await expect(guide.getByText('把同一条业务运动投影为入口、变换、效果、证据与观察结果。').first()).toBeVisible()
  await expect(guide.getByText('采集与原始入库').first()).toBeVisible()
  await expect(guide.getByText('运行态与 Successor').first()).toBeVisible()

  await guide.locator('.business-chain-guide__map > summary').click()
  await expect(guide.locator('svg.business-chain-guide__graph')).toBeVisible()
  await guide.locator('.business-chain-guide__map > summary').click()
  await expect(guide.locator('svg.business-chain-guide__graph')).toBeHidden()
  const technical = guide.locator('.business-chain-guide__technical').first()
  await expect(technical).not.toHaveAttribute('open')
  await technical.locator('summary').click()
  await expect(technical.locator('dl')).toBeVisible()
})

test('root management navigation exposes every responsibility without a more menu', async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'default')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })

  await page.goto('/')

  await expect(page.getByRole('region', { name: 'MRW 业务链条说明' })).toHaveCount(0)
  const navigation = page.getByRole('navigation', { name: '管理导航' })
  await expect(navigation.locator('.kernel-admin__section')).toHaveCount(3)
  await expect(navigation.locator('details')).toHaveCount(0)
  await expect(navigation.getByRole('button')).toHaveCount(12)
  for (const label of ['资料与来源', '任务与运行', '设置与帮助']) {
    await expect(navigation.getByText(label, { exact: true })).toBeVisible()
  }
})

test('guide and retained admin routes are directly addressable', async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem('app_locale_v1', 'zh-CN'))
  for (const route of ['/admin/process/processing', '/admin/resources/extract', '/admin/settings/llm', '/admin/guide']) {
    await page.goto(`/#${route}`)
    await expect(page).toHaveURL(new RegExp(`#${route}$`))
    await expect(page.locator('.kernel-admin__nav [aria-current="page"]')).toHaveCount(1)
  }
  await expect(page.getByRole('region', { name: 'MRW 业务链条说明' })).toBeVisible()
  await page.goto('/#business-guide.html')
  await expect(page.getByRole('region', { name: 'MRW 业务链条说明' })).toBeVisible()
  await expect(page.locator('.kernel-admin__title-row h1')).toHaveText('业务说明')
  await expect(page.locator('.kernel-admin__nav [aria-current="page"]')).toHaveText('业务说明')
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

  await menu.click()
  await page.getByRole('navigation', { name: '管理导航' }).getByRole('button', { name: '业务说明', exact: true }).click()
  await expect(page).toHaveURL(/#\/admin\/guide$/)
  await expect(menu).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByRole('region', { name: 'MRW 业务链条说明' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

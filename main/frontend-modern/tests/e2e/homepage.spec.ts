import { expect, test } from '@playwright/test'

test('homepage is reachable', async ({ page }) => {
  const response = await page.goto('/')
  expect(response?.ok()).toBeTruthy()
  await expect(page).toHaveTitle(/frontend-modern/i)
})

test('core shell elements are visible', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1, name: '运行记录', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: '目标项目', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '运行记录', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '项目与模板' })).toBeVisible()
})

test('LLM designer route mounts the current workflow manager', async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'default')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })
  await page.route('**/api/v1/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'ok', data: { items: [] } }),
    })
  })

  await page.goto('/#/workbench/designer/llm')

  await expect(page).toHaveURL(/#\/workbench\/designer\/llm$/)
  await expect(page.getByText('Workflow & Motif 管理器', { exact: true })).toBeVisible()
  await expect(page.locator('.llm-designer-page')).toHaveCount(0)
})

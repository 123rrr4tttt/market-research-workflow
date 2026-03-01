import { expect, test } from '@playwright/test'

test('homepage is reachable', async ({ page }) => {
  const response = await page.goto('/')
  expect(response?.ok()).toBeTruthy()
  await expect(page).toHaveTitle(/frontend-modern/i)
})

test('core shell elements are visible', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { level: 2, name: '任务' })).toBeVisible()
  await expect(page.getByRole('button', { name: '确认切换项目' })).toBeVisible()
  await expect(page.getByRole('button', { name: '数据仪表盘' })).toBeVisible()
})

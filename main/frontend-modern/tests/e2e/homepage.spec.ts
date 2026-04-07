import { expect, test } from '@playwright/test'

test('homepage is reachable', async ({ page }) => {
  const response = await page.goto('/')
  expect(response?.ok()).toBeTruthy()
  await expect(page).toHaveTitle(/frontend-modern/i)
})

test('core shell elements are visible', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { level: 1, name: '任务', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'target project' })).toBeVisible()
  await expect(page.getByRole('button', { name: '任务', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '项目管理' })).toBeVisible()
})

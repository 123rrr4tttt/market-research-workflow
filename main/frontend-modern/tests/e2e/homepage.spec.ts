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

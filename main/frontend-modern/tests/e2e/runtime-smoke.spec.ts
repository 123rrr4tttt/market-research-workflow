import { expect, test } from '@playwright/test'

test('homepage runtime smoke uses live backend', async ({ page }) => {
  const projectsResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/projects') && response.status() === 200
  })

  const response = await page.goto('/')
  expect(response?.ok()).toBeTruthy()
  await projectsResponse

  await expect(page.getByRole('heading', { level: 1, name: '任务', exact: true })).toBeVisible()
  await expect(page.getByRole('combobox', { name: 'target project' })).toBeVisible()
})

test('graph runtime smoke loads against live graph endpoints', async ({ page }) => {
  const graphConfigResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/project-customization/graph-config') && response.status() === 200
  })
  const marketGraphResponse = page.waitForResponse((response) => {
    return response.url().includes('/api/v1/admin/market-graph') && response.status() === 200
  })

  const response = await page.goto('/#graph.html?type=market')
  expect(response?.ok()).toBeTruthy()

  await graphConfigResponse
  await marketGraphResponse

  await expect(page.getByRole('heading', { level: 1, name: '市场图谱', exact: true })).toBeVisible()
  await expect(page.getByText('节点总数', { exact: true })).toBeVisible()
  await expect(page.getByText('边总数', { exact: true })).toBeVisible()
})

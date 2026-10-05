import { expect, test, type Page } from '@playwright/test'
import type { CellSnapshot } from '../../src/pages/agent-cell/model'

const snapshot: CellSnapshot = {
  environment_digest: '0123456789abcdef',
  environment: {
    contract_version: 'agent_macro.environment.resolved.v1', project_key: 'cell_test', package: null,
    definition: {
      cell_id: 'agent.macro.base', version: '1', owner: 'host', core_binding_ref: 'agent.macro.base', core_mode: 'native-agent',
      conceptual_rule_refs: ['agent_macro_architecture.section.2'], skill_contents: [{ skill_id: 'project-wiring', applicability_ref: 'project#method' }],
      tool_refs: ['project.read'], facility_refs: ['facility.project.read'], readback_refs: ['facility.project.read'], relations: [],
      operation: { inputs: { ports: [{ name: 'message' }] }, outputs: { ports: [{ name: 'observation' }] }, authority_ref: 'host_authorization', stop_ref: 'agent.macro.base', failure_refs: [], effect_refs: [] },
    },
    skills: [{ skill_id: 'project-wiring', relative_path: 'project-wiring/SKILL.md', content_digest: 'abc123' }],
    tools: [
      { name: 'project.read', description_for_model: 'Read project state', permission: 'allow', risk: 'read_only', input_schema: { type: 'object' } },
      { name: 'project.long_registered_tool_with_a_very_long_name_that_must_wrap_without_overflow', description_for_model: 'A host registration', permission: 'ask' },
    ],
    declared_tool_names: ['project.read'],
    facilities: [{ binding_id: 'facility.project.read', readback_semantics: 'project scoped readback', executor_ref: 'project.owner.read' }],
  },
}

async function shell(page: Page) {
  await page.addInitScript(() => localStorage.setItem('market_project_key', 'cell_test'))
  await page.route('**/api/v1/**', (route) => {
    const path = new URL(route.request().url()).pathname
    const data = path.endsWith('/projects') ? [{ project_key: 'cell_test', name: 'Cell Test', enabled: true, is_active: true }] : {}
    return route.fulfill({ json: { status: 'ok', data, error: null } })
  })
}

async function loaded(page: Page) {
  await shell(page)
  await page.route('**/api/v1/agent-cell**', (route) => route.fulfill({ json: { status: 'ok', data: snapshot, error: null } }))
  await page.goto('/#/workbench/cell')
  await expect(page.getByRole('group', { name: '胞腔分层圆环' })).toBeVisible()
}

test('ring and index select real descriptor entries; inspect, search, and empty sections', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await loaded(page)
  await page.getByRole('button', { name: '06 Tools，2 项', exact: true }).locator('.cell-ring__label').click()
  await expect(page.getByRole('heading', { name: 'Tools', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'project.read 胞腔声明引用', exact: true }).click()
  await expect(page.getByText('Read project state', { exact: true })).toBeVisible()
  await expect(page.getByText('read_only', { exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: '检索当前分区' }).fill('no-such-record')
  await expect(page.getByText('没有匹配的内容')).toBeVisible()
  await page.getByRole('button', { name: '清除检索' }).click()
  await page.getByRole('navigation', { name: '胞腔分区索引' }).getByRole('button', { name: /08 关系/ }).click()
  await expect(page.getByText('本环境未声明此类条目')).toBeVisible()
  await page.getByRole('button', { name: '00 原生 Core' }).press('Enter')
  await expect(page.getByRole('heading', { name: '原生 Core' })).toBeVisible()
  expect(errors).toEqual([])
})

test('layer separation, motion pause and reduced motion are supported', async ({ page }) => {
  await loaded(page)
  const orbit = page.locator('.cell-ring__orbit').first()
  await expect.poll(() => orbit.evaluate((e) => getComputedStyle(e).animationPlayState)).toBe('running')
  await page.getByRole('button', { name: '分层', exact: true }).click()
  await expect(page.locator('.cell-ring')).toHaveClass(/is-layered/)
  await page.getByRole('button', { name: '暂停结构动画' }).click()
  await expect.poll(() => orbit.evaluate((e) => getComputedStyle(e).animationPlayState)).toBe('paused')
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect.poll(() => orbit.evaluate((e) => getComputedStyle(e).animationName)).toBe('none')
})

test('ambiguous packages require explicit selection and preserve identity', async ({ page }) => {
  await shell(page)
  const requests: string[] = []
  await page.route('**/api/v1/agent-cell**', (route) => {
    const url = new URL(route.request().url())
    requests.push(url.search)
    if (url.searchParams.get('package_id') === 'cell-two' && url.searchParams.get('package_version') === '2') {
      return route.fulfill({ json: { status: 'ok', data: { ...snapshot, environment: { ...snapshot.environment, package: { package_id: 'cell-two', package_version: '2' } } } } })
    }
    return route.fulfill({ status: 409, json: { detail: { status: 'error', error: { message: 'Multiple activated packages', details: { activated: [['cell-one', '1'], ['cell-two', '2']] } } } } })
  })
  await page.goto('/#/workbench/cell')
  await expect(page.getByRole('heading', { name: '选择注册包' })).toBeVisible()
  await page.getByRole('combobox', { name: '注册包', exact: true }).selectOption(JSON.stringify(['cell-two', '2']))
  await expect(page.locator('.cell-atlas__context')).toContainText('cell-two @ 2')
  await expect(page.getByRole('combobox', { name: '当前注册包' })).toHaveValue(JSON.stringify(['cell-two', '2']))
  await expect(page.locator('.cell-ring')).toBeVisible()
  expect(requests).toHaveLength(2)
})

test('failed refresh hides stale data and can recover; never writes', async ({ page }) => {
  await loaded(page)
  const writes: string[] = []
  page.on('request', (request) => { if (request.method() !== 'GET') writes.push(request.url()) })
  await page.route('**/api/v1/agent-cell**', (route) => route.fulfill({ status: 503, json: { error: { message: 'Registration source unavailable' } } }))
  await page.getByRole('button', { name: '刷新胞腔' }).click()
  await expect(page.getByRole('alert')).toContainText('Registration source unavailable')
  await expect(page.locator('.cell-ring')).toHaveCount(0)
  await page.route('**/api/v1/agent-cell**', (route) => route.fulfill({ json: { status: 'ok', data: snapshot } }))
  await page.getByRole('button', { name: '刷新胞腔' }).click()
  await expect(page.locator('.cell-ring')).toBeVisible()
  expect(writes).toEqual([])
})

for (const viewport of [{ width: 1440, height: 1060 }, { width: 390, height: 844 }]) {
  test(`poster stays within viewport at ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport)
    await loaded(page)
    await page.getByRole('button', { name: '暂停结构动画' }).click()
    const atlas = page.getByTestId('agent-cell-page')
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    const ring = await page.locator('.cell-ring').boundingBox()
    expect(ring?.width).toBeGreaterThan(280)
    expect(await page.locator('.cell-ring__segment').count()).toBe(9)
    await atlas.screenshot({ path: testInfo.outputPath(`cell-${viewport.width}.png`) })
    await page.getByRole('button', { name: '06 Tools，2 项', exact: true }).locator('.cell-ring__label').click()
    await page.getByRole('button', { name: /project.long_registered_tool/ }).click()
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.getByRole('button', { name: '分层', exact: true }).click()
    for (const label of await page.locator('.cell-ring__label').all()) {
      await label.click()
      await expect(page.locator('.cell-atlas__section-title h2')).toHaveText(await label.textContent() ?? '')
    }
    await atlas.screenshot({ path: testInfo.outputPath(`cell-layered-${viewport.width}.png`) })
  })
}

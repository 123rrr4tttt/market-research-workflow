import { expect, test, type Page, type Route } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

type Box = {
  x: number
  y: number
  width: number
  height: number
}

type LayoutProbe = {
  viewport: { width: number; height: number }
  boxes: Record<string, Box>
  theme: string | null
  backgroundToken: string
  surfaceToken: string
  activeLayer: string
}

const evidenceDir = path.resolve(
  process.cwd(),
  '../../development/latest-dev-docs/automation-runs/frontend-runtime-visual/2026-05-22',
)

function apiEnvelope(data: unknown) {
  return {
    status: 'success',
    data,
    error: null,
    meta: { trace_id: 'frontend-runtime-visual-mock' },
  }
}

async function fulfillJson(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(apiEnvelope(data)),
  })
}

async function mockKernelRuntimeApi(page: Page) {
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const pathname = url.pathname

    if (pathname === '/api/v1/health') {
      await fulfillJson(route, {
        status: 'ok',
        provider: 'mock',
        env: 'runtime-visual',
      })
      return
    }

    if (pathname === '/api/v1/health/deep') {
      await fulfillJson(route, {
        database: 'ok',
        elasticsearch: 'degraded',
      })
      return
    }

    if (pathname === '/api/v1/config/env') {
      await fulfillJson(route, {
        DATABASE_URL: 'postgresql://runtime-visual.example/mrw',
        LLM_PROVIDER: 'openai',
        OPENAI_API_KEY: 'configured-for-runtime-visual',
        SERPAPI_KEY: '',
        NEWS_API_KEY: '',
      })
      return
    }

    if (pathname === '/api/v1/projects') {
      await fulfillJson(route, {
        items: [
          { project_key: 'runtime_visual', name: 'Runtime Visual', enabled: true },
          { project_key: 'default', name: 'Default', enabled: true },
        ],
      })
      return
    }

    if (pathname.endsWith('/activate')) {
      await fulfillJson(route, { project_key: pathname.split('/').at(-2) || 'runtime_visual' })
      return
    }

    if (pathname === '/api/v1/codex-auth/status') {
      await fulfillJson(route, {
        authenticated: true,
        token_sink_authenticated: true,
        codex_oauth_enabled: true,
      })
      return
    }

    if (pathname.includes('/llm-config/projects/')) {
      await fulfillJson(route, {
        project_key: 'runtime_visual',
        items: [
          {
            service_name: 'summary',
            model: 'gpt-4.1-mini',
            temperature: 0.2,
            max_tokens: 1200,
            enabled: true,
          },
        ],
      })
      return
    }

    if (pathname === '/api/v1/process/list') {
      await fulfillJson(route, { items: [], total: 0 })
      return
    }

    if (pathname === '/api/v1/process/stats') {
      await fulfillJson(route, { running: 0, pending: 0, failed: 0, completed: 0 })
      return
    }

    if (pathname === '/api/v1/dashboard/stats') {
      await fulfillJson(route, { totals: {}, series: [] })
      return
    }

    await fulfillJson(route, { items: [], total: 0 })
  })
}

async function bootstrapPage(page: Page) {
  await mockKernelRuntimeApi(page)
  await page.addInitScript(() => {
    window.localStorage.setItem('market_project_key', 'runtime_visual')
    window.localStorage.setItem('app_theme_v1', 'dark')
    window.localStorage.setItem('app_locale_v1', 'zh-CN')
  })
}

async function readLayoutProbe(page: Page, selectors: Record<string, string>, activeLayer: string): Promise<LayoutProbe> {
  return page.evaluate(
    ({ activeLayer: layer, selectors: selectorMap }) => {
      const boxes: Record<string, Box> = {}
      for (const [name, selector] of Object.entries(selectorMap)) {
        const element = document.querySelector(selector)
        const rect = element?.getBoundingClientRect()
        if (rect) {
          boxes[name] = {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
          }
        }
      }

      const style = window.getComputedStyle(document.documentElement)
      return {
        viewport: { width: window.innerWidth, height: window.innerHeight },
        boxes,
        theme: document.documentElement.getAttribute('data-app-theme'),
        backgroundToken: style.getPropertyValue('--app-background-app').trim(),
        surfaceToken: style.getPropertyValue('--app-surface-base').trim(),
        activeLayer: layer,
      }
    },
    { activeLayer, selectors },
  )
}

function assertBox(name: string, box: Box | undefined, minWidth = 120, minHeight = 40) {
  expect(box, `${name} should be present`).toBeTruthy()
  expect(box?.width, `${name} width`).toBeGreaterThan(minWidth)
  expect(box?.height, `${name} height`).toBeGreaterThan(minHeight)
}

function overlapArea(first: Box, second: Box) {
  const width = Math.max(0, Math.min(first.x + first.width, second.x + second.width) - Math.max(first.x, second.x))
  const height = Math.max(0, Math.min(first.y + first.height, second.y + second.height) - Math.max(first.y, second.y))
  return width * height
}

function assertStageDoesNotOverlapNav(probe: LayoutProbe, navKey: string, stageKey: string) {
  const nav = probe.boxes[navKey]
  const stage = probe.boxes[stageKey]
  assertBox(navKey, nav)
  assertBox(stageKey, stage)
  if (!nav || !stage) return

  const overlap = overlapArea(nav, stage)
  const stageArea = stage.width * stage.height
  expect(overlap / stageArea, `${stageKey} overlap with ${navKey}`).toBeLessThan(0.05)
}

test('frontend runtime visual shell contract covers theme, locale, and A/B/C topology', async ({ page }) => {
  fs.mkdirSync(evidenceDir, { recursive: true })
  await bootstrapPage(page)
  await page.setViewportSize({ width: 1440, height: 960 })

  await page.goto('/#/admin/settings')
  await expect(page.getByRole('heading', { level: 1, name: '系统设置' })).toBeVisible()
  await expect(page.getByText('界面语言', { exact: true })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-app-theme', 'dark')

  await page.locator('.settings-page label').filter({ hasText: '界面主题' }).locator('select').selectOption('brand')
  await expect(page.locator('html')).toHaveAttribute('data-app-theme', 'brand')
  await page.locator('.settings-page label').filter({ hasText: '界面语言' }).locator('select').selectOption('en-US')
  await expect(page.getByRole('heading', { level: 1, name: 'System Settings' })).toBeVisible()
  await expect(page.getByText('UI Language', { exact: true })).toBeVisible()

  const adminProbe = await readLayoutProbe(
    page,
    {
      topbar: '.kernel-admin__topbar',
      nav: '.kernel-admin__sidebar',
      stage: '.kernel-admin__stage',
      layerSwitch: '.kernel-layer-switch',
    },
    'C',
  )
  expect(adminProbe.theme).toBe('brand')
  expect(adminProbe.backgroundToken).toBe('#f5f8ff')
  assertStageDoesNotOverlapNav(adminProbe, 'nav', 'stage')
  await page.screenshot({
    path: path.join(evidenceDir, 'admin-settings-brand-en.png'),
    fullPage: true,
  })

  await page.getByRole('button', { name: /A\s+Workbench/i }).click()
  await expect(page).toHaveURL(/#\/workbench\/writing$/)
  await expect(page.locator('.kernel-workbench')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Writing Workbench' })).toHaveClass(/is-active/)
  const workbenchProbe = await readLayoutProbe(
    page,
    {
      nav: '.kernel-workbench__rail',
      stage: '.kernel-workbench__stage',
      layerSwitch: '.kernel-layer-switch',
    },
    'A',
  )
  expect(workbenchProbe.theme).toBe('brand')
  assertStageDoesNotOverlapNav(workbenchProbe, 'nav', 'stage')
  await page.screenshot({
    path: path.join(evidenceDir, 'workbench-writing-brand-en.png'),
    fullPage: true,
  })

  await page.getByRole('button', { name: /B\s+Visual/i }).click()
  await expect(page).toHaveURL(/#\/visual\/dashboard$/)
  await expect(page.locator('.kernel-visual')).toBeVisible()
  await expect(page.getByRole('heading', { level: 1, name: 'Data Dashboard' })).toBeVisible()
  const visualProbe = await readLayoutProbe(
    page,
    {
      masthead: '.kernel-visual__masthead',
      nav: '.kernel-visual__sidebar',
      stage: '.kernel-visual__stage',
      layerSwitch: '.kernel-layer-switch',
    },
    'B',
  )
  expect(visualProbe.theme).toBe('brand')
  assertStageDoesNotOverlapNav(visualProbe, 'nav', 'stage')
  await page.screenshot({
    path: path.join(evidenceDir, 'visual-dashboard-brand-en.png'),
    fullPage: true,
  })

  const result = {
    status: 'ok',
    date: '2026-05-22',
    gate: 'npm --prefix main/frontend-modern run check:runtime-visual',
    mocked_backend: true,
    coverage: [
      'runtime theme token application',
      'settings-driven locale and theme switch',
      'Layer C admin shell layout',
      'Layer A workbench shell layout',
      'Layer B visualization shell layout',
      'cross-layer route navigation',
    ],
    probes: {
      admin: adminProbe,
      workbench: workbenchProbe,
      visual: visualProbe,
    },
    screenshots: [
      'admin-settings-brand-en.png',
      'workbench-writing-brand-en.png',
      'visual-dashboard-brand-en.png',
    ],
  }
  fs.writeFileSync(path.join(evidenceDir, 'runtime_visual_contract.json'), `${JSON.stringify(result, null, 2)}\n`)
})

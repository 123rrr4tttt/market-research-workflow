import { expect, test, type Page } from '@playwright/test'

type HarnessConfig = {
  resourceKey: string
  enabled: boolean
  mountEpoch: number
  width: number
  height: number
}

type HarnessSnapshot = {
  lease: { ready: boolean; epoch: number; width: number; height: number }
  viewport: { width: number; height: number }
  pauses: number
  pendingFrames: number
  canceledFrames: number
  acquired: Array<{ key: string; epoch: number }>
}

type LifecycleHarness = {
  snapshot: () => HarnessSnapshot
  render: (patch: Partial<HarnessConfig>) => Promise<void>
  frame: () => Promise<void>
  replayCanceledFrames: () => Promise<void>
}

declare global {
  interface Window {
    graphLifecycleHarness: LifecycleHarness
  }
}

async function mountHarness(page: Page, strict = false) {
  // Read Vite's resolved dependency URLs so this harness shares React with the
  // real hooks, without loading the application or copying hook implementations.
  const entryResponse = await page.request.get('/src/main.tsx')
  expect(entryResponse.ok()).toBeTruthy()
  const entry = await entryResponse.text()
  const dependencyUrl = (name: string) => {
    const imports = Array.from(entry.matchAll(/from\s+["']([^"']+)["']/g), (match) => match[1])
    const url = imports.find((value) => value.split('?')[0].endsWith(`/${name}.js`))
    if (!url) throw new Error(`Vite did not resolve ${name} in /src/main.tsx`)
    return url
  }
  await page.route('**/__graph-renderer-lifecycle__', (route) => route.fulfill({
    contentType: 'text/html',
    body: '<!doctype html><html><body><div id="root"></div></body></html>',
  }))
  await page.goto('/__graph-renderer-lifecycle__')
  await page.evaluate(async ({ reactUrl, clientUrl, strictMode }) => {
    const React = (await import(reactUrl)).default as typeof import('react')
    const { createRoot } = (await import(clientUrl)).default as typeof import('react-dom/client')
    const schedulerUrl = '/src/pages/graph/hooks/useGraphDisplayResourceScheduler.ts'
    const viewportUrl = '/src/pages/graph/hooks/useForceGraphViewport.ts'
    const { useGraphDisplayResourceScheduler } = await import(schedulerUrl) as typeof import('../../src/pages/graph/hooks/useGraphDisplayResourceScheduler')
    const { useForceGraphViewport } = await import(viewportUrl) as typeof import('../../src/pages/graph/hooks/useForceGraphViewport')
    Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

    let nextFrame = 0
    let pauses = 0
    const frames = new Map<number, FrameRequestCallback>()
    const canceledFrames: FrameRequestCallback[] = []
    const acquired: HarnessSnapshot['acquired'] = []
    window.requestAnimationFrame = (callback) => {
      frames.set(++nextFrame, callback)
      return nextFrame
    }
    window.cancelAnimationFrame = (id) => {
      const callback = frames.get(id)
      if (callback) canceledFrames.push(callback)
      frames.delete(id)
    }

    let config: HarnessConfig = {
      resourceKey: 'a', enabled: true, mountEpoch: 0, width: 320, height: 180,
    }
    let latest: Pick<HarnessSnapshot, 'lease' | 'viewport'>
    function Harness(props: HarnessConfig) {
      const hostRef = React.useRef<HTMLDivElement | null>(null)
      const viewportRef = React.useRef<HTMLDivElement | null>(null)
      const engineRef = React.useRef({ pauseAnimation: () => { pauses += 1 } })
      const lease = useGraphDisplayResourceScheduler(props.resourceKey, props.enabled, hostRef, engineRef)
      const viewport = useForceGraphViewport(props.enabled, viewportRef, props.mountEpoch)
      React.useLayoutEffect(() => { latest = { lease, viewport } })
      React.useEffect(() => {
        if (lease.ready) acquired.push({ key: props.resourceKey, epoch: lease.epoch })
      }, [lease.ready, lease.epoch, props.resourceKey])
      return React.createElement('div', { ref: hostRef, style: { width: 640, height: 360 } },
        React.createElement('div', {
          key: props.mountEpoch,
          ref: viewportRef,
          'data-testid': 'viewport-host',
          style: { width: props.width, height: props.height },
        }),
      )
    }

    const root = createRoot(document.getElementById('root')!)
    const render = async (patch: Partial<HarnessConfig>) => {
      config = { ...config, ...patch }
      await React.act(async () => {
        const child = React.createElement(Harness, config)
        root.render(strictMode ? React.createElement(React.StrictMode, null, child) : child)
      })
    }
    window.graphLifecycleHarness = {
      snapshot: () => ({
        ...latest, pauses, pendingFrames: frames.size, canceledFrames: canceledFrames.length,
        acquired: [...acquired],
      }),
      render,
      frame: async () => {
        const callbacks = [...frames.values()]
        frames.clear()
        await React.act(async () => { callbacks.forEach((callback) => callback(performance.now())) })
      },
      replayCanceledFrames: async () => {
        const callbacks = canceledFrames.splice(0)
        await React.act(async () => { callbacks.forEach((callback) => callback(performance.now())) })
      },
    }
    await render({})
  }, { reactUrl: dependencyUrl('react'), clientUrl: dependencyUrl('react-dom_client'), strictMode: strict })
}

const snapshot = (page: Page) => page.evaluate(() => window.graphLifecycleHarness.snapshot())
const render = (page: Page, patch: Partial<HarnessConfig>) => page.evaluate((next) => window.graphLifecycleHarness.render(next), patch)
async function acquire(page: Page) {
  await page.evaluate(() => window.graphLifecycleHarness.frame())
  await page.evaluate(() => window.graphLifecycleHarness.frame())
  return snapshot(page)
}

test('acquiring a display lease does not pause its engine through self-cleanup', async ({ page }) => {
  await mountHarness(page)
  const before = await snapshot(page)
  expect(before.lease.ready).toBe(false)
  const after = await acquire(page)
  expect(after.lease).toEqual({ ready: true, epoch: 1, width: 640, height: 360 })
  expect(after.pauses).toBe(before.pauses)
  expect(after.pendingFrames).toBe(0)
})

test('disabling and re-enabling the same resource acquires a fresh lease', async ({ page }) => {
  await mountHarness(page)
  const first = await acquire(page)
  await render(page, { enabled: false })
  expect((await snapshot(page)).lease.ready).toBe(false)
  await render(page, { enabled: true })
  expect((await snapshot(page)).lease.ready).toBe(false)
  const second = await acquire(page)
  expect(second.lease.ready).toBe(true)
  expect(second.lease.epoch).toBeGreaterThan(first.lease.epoch)
})

test('StrictMode and resource changes discard obsolete animation frame callbacks', async ({ page }) => {
  await mountHarness(page, true)
  expect((await snapshot(page)).canceledFrames).toBeGreaterThan(0)
  await render(page, { resourceKey: 'b' })
  await page.evaluate(() => window.graphLifecycleHarness.replayCanceledFrames())
  expect((await snapshot(page)).lease.ready).toBe(false)
  const first = await acquire(page)
  expect(first.lease.ready).toBe(true)
  expect(first.acquired).toEqual([{ key: 'b', epoch: first.lease.epoch }])

  await render(page, { resourceKey: 'c' })
  await page.evaluate(() => window.graphLifecycleHarness.frame())
  await render(page, { resourceKey: 'd' })
  await page.evaluate(() => window.graphLifecycleHarness.replayCanceledFrames())
  expect((await snapshot(page)).lease.ready).toBe(false)
  const last = await acquire(page)
  expect(last.lease.epoch).toBeGreaterThan(first.lease.epoch)
  expect(last.acquired.map((item) => item.key)).toEqual(['b', 'd'])
  expect(last.pendingFrames).toBe(0)
})

test('viewport mount epochs subscribe to the replacement DOM container', async ({ page }) => {
  await mountHarness(page)
  expect((await snapshot(page)).viewport).toEqual({ width: 320, height: 180 })
  const previousHost = await page.getByTestId('viewport-host').elementHandle()
  await render(page, { mountEpoch: 1, width: 510, height: 270 })
  expect(await previousHost!.evaluate((element) => element.isConnected)).toBe(false)
  expect((await snapshot(page)).viewport).toEqual({ width: 510, height: 270 })
  await page.getByTestId('viewport-host').evaluate((element) => {
    element.style.width = '555px'
    element.style.height = '310px'
  })
  await expect.poll(async () => (await snapshot(page)).viewport).toEqual({ width: 555, height: 310 })
})

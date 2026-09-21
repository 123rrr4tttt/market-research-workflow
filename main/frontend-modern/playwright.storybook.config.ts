import { defineConfig, devices } from '@playwright/test'

const DEFAULT_STORYBOOK_E2E_PORT = 6007

function readStorybookE2ePort() {
  const raw = process.env.FRONTEND_STORYBOOK_E2E_PORT
  if (!raw) return DEFAULT_STORYBOOK_E2E_PORT
  const value = Number(raw)
  if (!Number.isInteger(value) || value < 1 || value > 65_535) {
    throw new Error(`FRONTEND_STORYBOOK_E2E_PORT must be an integer from 1 to 65535; received ${JSON.stringify(raw)}`)
  }
  return value
}

const storybookE2ePort = readStorybookE2ePort()
const storybookOrigin = `http://127.0.0.1:${storybookE2ePort}`

export default defineConfig({
  testDir: './tests/storybook',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: storybookOrigin,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `pnpm storybook --ci --no-open --disable-telemetry --no-version-updates --host 127.0.0.1 --port ${storybookE2ePort} --exact-port`,
    url: `${storybookOrigin}/index.json`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})

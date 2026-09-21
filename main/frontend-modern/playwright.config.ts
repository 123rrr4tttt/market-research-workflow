import { defineConfig, devices } from '@playwright/test'

const DEFAULT_FRONTEND_E2E_PORT = 4173
const FAIL_CLOSED_PROXY_TARGET = 'http://127.0.0.1:1'

function readFrontendE2ePort() {
  const raw = process.env.FRONTEND_E2E_PORT
  if (!raw) return DEFAULT_FRONTEND_E2E_PORT
  const value = Number(raw)
  if (!Number.isInteger(value) || value < 1 || value > 65_535) {
    throw new Error(`FRONTEND_E2E_PORT must be an integer from 1 to 65535; received ${JSON.stringify(raw)}`)
  }
  return value
}

const frontendE2ePort = readFrontendE2ePort()
const frontendE2eOrigin = `http://127.0.0.1:${frontendE2ePort}`

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: frontendE2eOrigin,
    trace: 'on-first-retry',
  },
  webServer: {
    command: `pnpm dev --host 127.0.0.1 --port ${frontendE2ePort} --strictPort`,
    url: frontendE2eOrigin,
    // E2E never inherits the normal developer defaults for user-owned services.
    // Real-backend runs must inject both targets explicitly; mock-only runs stay
    // fail-closed at an unused loopback port for every request they do not mock.
    env: {
      FRONTEND_E2E_ISOLATED: '1',
      VITE_API_PROXY_TARGET: process.env.VITE_API_PROXY_TARGET || FAIL_CLOSED_PROXY_TARGET,
      VITE_CODEX_PROXY_TARGET: process.env.VITE_CODEX_PROXY_TARGET || FAIL_CLOSED_PROXY_TARGET,
    },
    reuseExistingServer: false,
    timeout: 120000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})

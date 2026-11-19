import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.CODEX_AUTH_PROXY_BASE_URL

if (!baseURL) {
  throw new Error('CODEX_AUTH_PROXY_BASE_URL is required for the Codex auth proxy configuration')
}

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'codex-auth-proxy.spec.ts',
  reporter: 'line',
  outputDir: '/tmp/mrw-codex-auth-proxy-playwright-output',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
  },
})

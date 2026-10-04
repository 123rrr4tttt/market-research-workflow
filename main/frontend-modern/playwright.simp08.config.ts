import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.SIMPO8_CODEX_PROXY_BASE_URL

if (!baseURL) {
  throw new Error('SIMPO8_CODEX_PROXY_BASE_URL is required for the SIMP08 proxy config')
}

export default defineConfig({
  testDir: './tests/e2e',
  reporter: 'line',
  outputDir: '/tmp/mrw-simp08-playwright-output',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
  },
})

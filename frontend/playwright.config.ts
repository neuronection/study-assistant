import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  globalTeardown: './e2e/global-teardown.ts',
  timeout: 60_000,
  workers: 1,
  retries: 0,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8971',
    trace: 'retain-on-failure',
  },
  reporter: [['list']],
})

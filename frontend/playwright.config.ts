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
    // Session cookies from the service account bootstrapped in
    // global-setup (S4b enforces sessions on /api/*). Cookies only —
    // localStorage stays per-context so the wizard's dismissal flag is
    // always fresh.
    storageState: './e2e/.auth-state.json',
    trace: 'retain-on-failure',
  },
  reporter: [['list']],
})

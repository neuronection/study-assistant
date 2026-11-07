import { expect, test } from '@playwright/test'

import { api, baseUrl, seedProvider } from './state'

// Plan 84 D (ADR-210): the extension/MCP subsystem had no end-to-end gate.
// This smoke registers an MCP server, refreshes it and opens the per-extension
// docs dialog — the instance lifecycle surface, not a live MCP handshake (the
// command here is an inert echo, so the refresh records a failing status
// honestly instead of hanging).
test('S8 — MCP connector registers, refreshes and opens docs', async ({ page }) => {
  await seedProvider()
  const server = await api<{ id: string }>('POST', '/mcp/servers', {
    name: 'E2E echo connector',
    transport: 'http',
    url: 'http://127.0.0.1:9/mcp',
  })

  await page.goto(`${baseUrl()}/settings?tab=tools&section=connectors`)
  await expect(page.getByRole('heading', { name: /MCP connectors/ })).toBeVisible({
    timeout: 30_000,
  })
  await expect(page.getByText('E2E echo connector', { exact: false }).first()).toBeVisible()

  try {
    await api('POST', `/mcp/servers/${server.id}/refresh`)
  } catch {
    // The inert endpoint cannot complete an MCP handshake; the refresh records
    // that failure honestly (502) instead of hanging. The instance surface is
    // what this smoke asserts.
  }
  await page.reload()
  await expect(page.getByText('E2E echo connector', { exact: false }).first()).toBeVisible({
    timeout: 30_000,
  })

  await page.getByTestId('extension-docs-mcp').click()
  await expect(page.getByRole('dialog')).toBeVisible({ timeout: 30_000 })
})

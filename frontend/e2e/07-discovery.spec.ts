import { expect, test } from '@playwright/test'

import { api, baseUrl, seedProvider } from './state'

// Plan 84 D (ADR-210): discovery had no end-to-end gate. This smoke drives the
// link-material → library → Discover-dialog path against the real backend. The
// provider search half needs a web-search provider (not the mock LLM), so the
// spec asserts the surface and the link material, not live web results.
test('S7 — link material renders and the Discover dialog opens', async ({ page }) => {
  await seedProvider()
  const course = await api<{ id: string }>('POST', '/courses', { title: 'DiscoverySmoke' })
  await api('POST', '/materials/link', {
    course_id: course.id,
    url: 'https://example.com/chain-rule',
    title: 'Chain rule reference',
  })

  await page.goto(`${baseUrl()}/library?course=${course.id}`)
  await expect(page.getByText('Chain rule reference', { exact: false }).first()).toBeVisible({
    timeout: 30_000,
  })

  await page.getByRole('button', { name: /^new/i }).first().click()
  await page.getByText('Discover material', { exact: true }).click()

  const dialog = page.getByRole('dialog', { name: 'Discover material' })
  await expect(dialog).toBeVisible({ timeout: 30_000 })
  await expect(dialog.getByPlaceholder('Search topic…')).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Search' })).toBeVisible()
  await expect(dialog.getByText('Web', { exact: true })).toBeVisible()
})

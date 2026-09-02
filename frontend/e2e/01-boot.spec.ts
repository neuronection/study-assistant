import { expect, test } from '@playwright/test'

import { baseUrl } from './state'

test('S1 — fresh boot shows the wizard, skipping lands on the shell', async ({ page }) => {
  await page.goto(baseUrl())
  await expect(page.getByText('Welcome to Study Assistant')).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'Skip for now' }).click()
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible()
  await page.goto(`${baseUrl()}/courses`)
  await expect(page.getByRole('button', { name: 'New course' })).toBeVisible()
})

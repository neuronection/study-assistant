import { expect, test } from '@playwright/test'

import { baseUrl } from './state'

test('S1 — fresh boot shows the wizard, skipping lands on the shell', async ({ page }) => {
  await page.goto(baseUrl())
  const welcome = page.getByText('Welcome to Study Assistant')
  for (let attempt = 0; attempt < 6 && !(await welcome.isVisible().catch(() => false)); attempt++) {
    await page.waitForTimeout(2_500)
    await page.reload()
  }
  await expect(welcome).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'Skip for now' }).click()
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible()
  await page.goto(`${baseUrl()}/courses`)
  await expect(page.getByRole('button', { name: 'New course' })).toBeVisible()
})

import { expect, test } from '@playwright/test'

import { api, baseUrl, seedProvider } from './state'

test('S2 — create course, upload material, search finds it', async ({ page }) => {
  await seedProvider()
  await page.goto(`${baseUrl()}/courses`)
  await page.getByRole('button', { name: 'New course' }).click()
  await page.getByPlaceholder('Course title').fill('E2E Calculus')
  await page.getByRole('button', { name: /^add$/i }).click()
  await expect(page.getByText('E2E Calculus', { exact: true })).toBeVisible()

  const courses = await api<Array<{ id: number; title: string }>>('GET', '/courses')
  const course = courses.find((entry) => entry.title === 'E2E Calculus')
  if (!course) throw new Error('created course not found')

  await page.goto(`${baseUrl()}/library?course=${course.id}`)
  const fileInput = page.locator('input[aria-label="Upload files"]')
  await fileInput.setInputFiles({
    name: 'chain-rule.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from(
      '# Chain rule notes\n\nThe chain rule states that dy/dx = dy/du * du/dx for composite functions.'
    ),
  })
  await expect(page.getByText('chain-rule', { exact: false }).first()).toBeVisible({
    timeout: 30_000,
  })

  await page.goto(`${baseUrl()}/library?course=${course.id}`)
  await page.getByRole('button', { name: 'Search', exact: true }).click()
  await page.getByPlaceholder('Search all materials…').fill('chain rule')
  await expect(page.getByText('chain-rule', { exact: false }).first()).toBeVisible({
    timeout: 30_000,
  })
})

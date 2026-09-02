import { expect, test } from '@playwright/test'

import { baseUrl, seedProvider } from './state'

test('S4 — chat turn streams a fixed answer with a tool card', async ({ page }) => {
  await seedProvider()
  await page.goto(baseUrl())
  await page.evaluate(() => window.localStorage.removeItem('ca-course-id'))
  await page.reload()
  await page.getByRole('button', { name: 'Open chat' }).click()
  const composer = page.getByPlaceholder('Ask about your material…')
  await composer.fill('What is 2+2?')
  await composer.press('Enter')

  await expect(
    page.getByText('The tool says the result is 4', { exact: false }).first()
  ).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole('button', { name: /Calculate/ }).first()).toBeVisible()
})

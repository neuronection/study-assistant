import { expect, test } from '@playwright/test'

import { api, baseUrl, seedProvider } from './state'

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
  await expect(
    page.getByRole('button', { name: /CALC/ }).first()
  ).toBeVisible()
})

test('S5 — full-page tutor shows thinking status and streams across session creation', async ({
  page,
}) => {
  await seedProvider()
  await page.goto(baseUrl())
  await page.evaluate(() => window.localStorage.removeItem('ca-course-id'))
  await page.reload()
  await page.getByRole('button', { name: 'Tutor' }).click()
  const composer = page.getByPlaceholder('Ask about your material…')
  await composer.fill('What is 2+2?')
  await composer.press('Enter')

  await expect(page.getByText('Thinking…').first()).toBeVisible({
    timeout: 30_000,
  })
  await expect(page).toHaveURL(/\/chat\/[^/]+$/)
  await expect(
    page.getByText('The tool says the result is 4', { exact: false }).first()
  ).toBeVisible({ timeout: 60_000 })
})

test('S9 — tutor history scrolls in its panel while the page stays fixed', async ({ page }) => {
  await seedProvider()
  await api<unknown>('POST', '/chat/sessions', { title: 'History 01' })
  await api<unknown>('POST', '/chat/sessions', { title: 'History 02' })
  for (let index = 3; index <= 30; index += 1) {
    await api<unknown>('POST', '/chat/sessions', {
      title: `History ${String(index).padStart(2, '0')}`,
    })
  }

  await page.goto(`${baseUrl()}/chat`)
  const list = page.locator('main aside .overflow-y-auto').first()
  await expect(list).toBeVisible()
  await expect(page.getByText('History 30', { exact: true })).toBeVisible()

  await expect
    .poll(
      async () =>
        list.evaluate(
          (element) => element.scrollHeight - element.clientHeight,
        ),
      { timeout: 10_000 },
    )
    .toBeGreaterThan(0)

  await list.evaluate((element) =>
    element.scrollTo({ top: element.scrollHeight }),
  )
  const pageScroll = await page.evaluate(() => {
    const scroller = document.querySelector('main')
    return {
      pageCanScroll:
        (scroller?.scrollHeight ?? 0) > (scroller?.clientHeight ?? 0) + 1,
      scrollTop: scroller?.scrollTop ?? 0,
    }
  })
  expect(pageScroll.pageCanScroll, 'the tutor page itself must not scroll').toBe(
    false,
  )
})

import { expect, test } from '@playwright/test'

import { api, baseUrl, seedProvider } from './state'

test('S6 — reading-view Ask AI opens the sidepanel and the turn is visible live', async ({
  page,
}) => {
  await seedProvider()
  await page.goto(`${baseUrl()}/courses`)
  await page.getByRole('button', { name: 'New course' }).click()
  await page.getByPlaceholder('Course title').fill('Ask Flow')
  await page.getByRole('button', { name: /^add$/i }).click()
  await expect(page.getByText('Ask Flow', { exact: true })).toBeVisible()

  const courses = await api<Array<{ id: number; title: string }>>('GET', '/courses')
  const course = courses.find((entry) => entry.title === 'Ask Flow')
  if (!course) throw new Error('created course not found')

  await page.goto(`${baseUrl()}/library?course=${course.id}`)
  const fileInput = page.locator('input[aria-label="Upload files"]')
  await fileInput.setInputFiles({
    name: 'ask-flow.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from('# Ask flow\n\nMaterial used by the ask-AI e2e spec.'),
  })
  await expect(page.getByText('ask-flow', { exact: false }).first()).toBeVisible({
    timeout: 30_000,
  })

  const materials = await api<Array<{ id: number; title: string }>>(
    'GET',
    `/materials?course_id=${course.id}`,
  )
  const material = materials.find((entry) => entry.title.startsWith('ask-flow'))
  if (!material) throw new Error('material not found')
  await page.goto(`${baseUrl()}/library/${material.id}`)
  await page.waitForTimeout(1500)

  await page.getByRole('button', { name: 'Ask the AI about this material' }).click()
  const askInput = page.getByRole('textbox', { name: 'Ask the AI about this material' }).last()
  await askInput.fill('What is this material about?')
  await askInput.press('Enter')

  await expect(page.getByText('Thinking…').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('What is this material about?').first()).toBeVisible({
    timeout: 30_000,
  })
  await expect(
    page.getByText('The tool says the result is 4', { exact: false }).first()
  ).toBeVisible({ timeout: 60_000 })
})

test('S7 — a second Ask AI with the sidepanel already open stays visible', async ({ page }) => {
  await seedProvider()
  await page.goto(`${baseUrl()}/courses`)
  await page.getByRole('button', { name: 'New course' }).click()
  await page.getByPlaceholder('Course title').fill('Ask Flow 2')
  await page.getByRole('button', { name: /^add$/i }).click()
  await expect(page.getByText('Ask Flow 2', { exact: true })).toBeVisible()

  const courses = await api<Array<{ id: number; title: string }>>('GET', '/courses')
  const course = courses.find((entry) => entry.title === 'Ask Flow 2')
  if (!course) throw new Error('created course not found')

  await page.goto(`${baseUrl()}/library?course=${course.id}`)
  const fileInput = page.locator('input[aria-label="Upload files"]')
  await fileInput.setInputFiles({
    name: 'ask-two.md',
    mimeType: 'text/markdown',
    buffer: Buffer.from('# Ask two\n\nSecond material for the sidepanel-open ask spec.'),
  })
  await expect(page.getByText('ask-two', { exact: false }).first()).toBeVisible({
    timeout: 30_000,
  })

  const materials = await api<Array<{ id: number; title: string }>>(
    'GET',
    `/materials?course_id=${course.id}`,
  )
  const material = materials.find((entry) => entry.title.startsWith('ask-two'))
  if (!material) throw new Error('material not found')

  await page.getByRole('button', { name: 'Open chat' }).click()
  await page.getByPlaceholder('Ask about your material…').fill('warmup')
  await page.getByPlaceholder('Ask about your material…').press('Enter')
  await expect(
    page.getByText('The tool says the result is 4', { exact: false }).first()
  ).toBeVisible({ timeout: 60_000 })

  await page.goto(`${baseUrl()}/library/${material.id}`)
  await page.waitForTimeout(1500)
  await page.getByRole('button', { name: 'Ask the AI about this material' }).click()
  const askInput = page.getByRole('textbox', { name: 'Ask the AI about this material' }).last()
  await askInput.fill('Summarize this')
  await askInput.press('Enter')

  await expect(page.getByText('Thinking…').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('Summarize this').first()).toBeVisible({ timeout: 30_000 })
  await expect(
    page.getByText('The tool says the result is 4', { exact: false }).first()
  ).toBeVisible({ timeout: 60_000 })
})

async function uploadMaterial(
  page: import('@playwright/test').Page,
  courseId: number,
  name: string,
  body: string,
): Promise<void> {
  await page.goto(`${baseUrl()}/library?course=${courseId}`)
  const fileInput = page.locator('input[aria-label="Upload files"]')
  await fileInput.setInputFiles({
    name,
    mimeType: 'text/markdown',
    buffer: Buffer.from(body),
  })
  await expect(page.getByText(name.replace(/\.md$/, ''), { exact: false }).first()).toBeVisible({
    timeout: 30_000,
  })
}

test('S8 — multi-material context-menu ask attaches the selection', async ({ page }) => {
  await seedProvider()
  await page.goto(`${baseUrl()}/courses`)
  await page.getByRole('button', { name: 'New course' }).click()
  await page.getByPlaceholder('Course title').fill('Ask Multi')
  await page.getByRole('button', { name: /^add$/i }).click()
  await expect(page.getByText('Ask Multi', { exact: true })).toBeVisible()

  const courses = await api<Array<{ id: number; title: string }>>('GET', '/courses')
  const course = courses.find((entry) => entry.title === 'Ask Multi')
  if (!course) throw new Error('created course not found')

  await uploadMaterial(page, course.id, 'limits.md', '# Limits\n\nLimit intuition notes.')
  await uploadMaterial(page, course.id, 'derivatives.md', '# Derivatives\n\nDerivative rules.')

  await page.goto(`${baseUrl()}/library?course=${course.id}`)
  const materialRow = (name: string) =>
    page
      .locator('[data-selectable-id^="m"]')
      .filter({ hasText: name })
      .first()
  const first = materialRow('limits')
  const second = materialRow('derivatives')
  await first.click()
  await second.click({ modifiers: ['Control'] })
  await second.click({ button: 'right' })

  await page.getByRole('menuitem', { name: 'Ask AI about 2 materials…' }).click()
  await expect(page.getByText('Attached materials (2)', { exact: false })).toBeVisible()
  await expect(page.getByText('limits', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('derivatives', { exact: true }).first()).toBeVisible()

  const question = page.getByRole('textbox', { name: 'Your question' })
  await question.fill('Compare the two attached materials.')
  await page.getByRole('button', { name: 'Ask', exact: true }).click()

  await expect(page.getByText('Thinking…').first()).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('Compare the two attached materials.').first()).toBeVisible({
    timeout: 30_000,
  })
  await expect(
    page.getByText('The tool says the result is 4', { exact: false }).first()
  ).toBeVisible({ timeout: 60_000 })
})

import { expect, test } from '@playwright/test'

import { api, baseUrl } from './state'

test('S6 — course structure sidebar renders visible on the course workspace', async ({
  page,
}) => {
  await page.goto(baseUrl())
  const skip = page.getByRole('button', { name: 'Skip for now' })
  try {
    await skip.click({ timeout: 15_000 })
  } catch {
    // already onboarded
  }
  const course = await api<{ id: number }>('POST', '/courses', { title: 'TreeSidebar' })
  await page.goto(`${baseUrl()}/courses/${course.id}`)
  await expect(
    page.getByRole('heading', { name: 'TreeSidebar', exact: true })
  ).toBeVisible({
    timeout: 30_000,
  })

  const tree = page.getByRole('tree')
  await expect(tree).toBeVisible()
  const box = await tree.boundingBox()
  expect(box?.width ?? 0).toBeGreaterThan(100)
  await expect(tree.getByText('TreeSidebar')).toBeVisible()
})

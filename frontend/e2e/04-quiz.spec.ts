import { expect, test } from '@playwright/test'

import { api, baseUrl, seedProvider } from './state'

test('S3 — generate a quiz from the mock provider, answer it, score recorded', async ({
  page,
}) => {
  await seedProvider()
  const course = await api<{ id: number }>('POST', '/courses', { title: 'E2E Quiz course' })
  const activity = await api<{ id: number }>('POST', '/quiz/generate', {
    course_id: course.id,
    count: 1,
  })

  await page.goto(`${baseUrl()}/quiz/${activity.id}`)
  await expect(page.getByText('What is 2 + 2?')).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'B 4' }).click()
  await page.getByRole('button', { name: 'Submit' }).click()
  await expect(page.getByText('Correct').first()).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: 'Finish' }).click()
  await expect(page.getByText('You scored 100%.')).toBeVisible({ timeout: 30_000 })
})

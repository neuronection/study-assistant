import type { components } from '@/lib/api-schema'

import { json, apiFetch } from './client'

type Schemas = components['schemas']

export type DueCourseGroup = Schemas['DueCourseGroupOut']
export type ReviewDue = Schemas['ReviewDueOut']

export async function getReviewDue(perCourse = 20): Promise<ReviewDue> {
  const response = await apiFetch(`/api/v1/review/due?per_course=${perCourse}`)
  return json<ReviewDue>(response)
}

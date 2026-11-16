import type { components } from '@/lib/api-schema'

import { json, apiFetch } from './client'

type Schemas = components['schemas']

export type DueCourseGroup = Schemas['DueCourseGroupOut']
export type ReviewDue = Schemas['ReviewDueOut']
export type ReviewFilter = Schemas['ReviewFilterOut']
export type ReviewFilterInput = Schemas['ReviewFilterIn']

export interface ReviewQuery {
  perCourse?: number
  courseId?: string
  nodeId?: string
  includeNotDue?: boolean
  dueWindowDays?: number
  limit?: number
  sortOrder?: 'due' | 'oldest' | 'mixed'
  filterId?: string
  respectCaps?: boolean
}

export async function getReviewDue(
  query: ReviewQuery | number = 20
): Promise<ReviewDue> {
  const options: ReviewQuery =
    typeof query === 'number' ? { perCourse: query } : query
  const params = new URLSearchParams()
  if (options.perCourse !== undefined) {
    params.set('per_course', String(options.perCourse))
  }
  if (options.courseId !== undefined) {
    params.set('course_id', options.courseId)
  }
  if (options.nodeId !== undefined) {
    params.set('node_id', options.nodeId)
  }
  if (options.includeNotDue) {
    params.set('include_not_due', 'true')
  }
  if (options.dueWindowDays !== undefined) {
    params.set('due_window_days', String(options.dueWindowDays))
  }
  if (options.limit !== undefined) {
    params.set('limit', String(options.limit))
  }
  if (options.sortOrder !== undefined) {
    params.set('sort_order', options.sortOrder)
  }
  if (options.filterId !== undefined) {
    params.set('filter_id', options.filterId)
  }
  if (options.respectCaps === false) {
    params.set('respect_caps', 'false')
  }
  const response = await apiFetch(`/api/v1/review/due?${params.toString()}`)
  return json<ReviewDue>(response)
}

export async function listReviewFilters(): Promise<ReviewFilter[]> {
  const response = await apiFetch('/api/v1/review/filters')
  return json<ReviewFilter[]>(response)
}

export async function createReviewFilter(
  body: ReviewFilterInput
): Promise<ReviewFilter> {
  const response = await apiFetch('/api/v1/review/filters', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ReviewFilter>(response)
}

export async function deleteReviewFilter(filterId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/review/filters/${filterId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(`delete filter failed: ${response.status}`)
  }
}

export async function previewReview(cardId: string, rating: number): Promise<void> {
  const response = await apiFetch(`/api/v1/review/preview/${cardId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rating }),
  })
  await json<{ logged: boolean }>(response)
}

import type { components } from '@/lib/api-schema'
import { json, apiFetch } from './client'

type Schemas = components['schemas']

export type PlanItem = Schemas['PlanItemOut']
export type PlanItemKind = Schemas['PlanItemKind']
export type UpcomingItem = Schemas['UpcomingItemOut']

export async function listPlanItems(courseId: number): Promise<PlanItem[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/plan`)
  return json<PlanItem[]>(response)
}

export async function createPlanItem(
  courseId: number,
  body: { title: string; kind: string; due_date: string; node_id?: number | null }
): Promise<PlanItem> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<PlanItem>(response)
}

export async function updatePlanItem(
  courseId: number,
  itemId: number,
  body: { title?: string; due_date?: string; done?: boolean; kind?: string }
): Promise<PlanItem> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/plan/${itemId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<PlanItem>(response)
}

export async function deletePlanItem(courseId: number, itemId: number): Promise<void> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/plan/${itemId}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed (${response.status})`)
  }
}

export async function generatePlan(courseId: number): Promise<{
  created: number
  items: PlanItem[]
}> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/plan/generate`, {
    method: 'POST',
  })
  return json(response)
}

export async function listUpcomingItems(days = 7): Promise<UpcomingItem[]> {
  const response = await apiFetch(`/api/v1/plan/upcoming?days=${days}`)
  return json<UpcomingItem[]>(response)
}

export function planIcsUrl(courseId: number): string {
  return `/api/v1/courses/${courseId}/plan.ics`
}

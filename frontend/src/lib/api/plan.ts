import type { components } from '@/lib/api-schema'
import { json, apiFetch } from './client'

type Schemas = components['schemas']

export type PlanItem = Schemas['PlanItemOut']
export type PlanItemKind = Schemas['PlanItemKind']
export type UpcomingItem = Schemas['UpcomingItemOut']

export async function listPlanItems(courseId: string): Promise<PlanItem[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/plan`)
  return json<PlanItem[]>(response)
}

export async function createPlanItem(
  courseId: string,
  body: { title: string; kind: string; due_date: string; node_id?: string | null }
): Promise<PlanItem> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/plan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<PlanItem>(response)
}

export async function updatePlanItem(
  courseId: string,
  itemId: string,
  body: { title?: string; due_date?: string; done?: boolean; kind?: string }
): Promise<PlanItem> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/plan/${itemId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<PlanItem>(response)
}

export async function deletePlanItem(courseId: string, itemId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/plan/${itemId}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed (${response.status})`)
  }
}

export async function generatePlan(courseId: string): Promise<{
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

export function planIcsUrl(courseId: string): string {
  return `/api/v1/courses/${courseId}/plan.ics`
}

export type IcsPreview = Schemas['IcsPreviewOut']
export type IcsImportResult = Schemas['IcsImportOut']

export async function previewIcsImport(
  courseId: string,
  file: File
): Promise<IcsPreview> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiFetch(`/api/v1/courses/${courseId}/plan/import-ics/preview`, {
    method: 'POST',
    body: form,
  })
  return json<IcsPreview>(response)
}

export async function importIcs(
  courseId: string,
  file: File,
  confirmExam: boolean
): Promise<IcsImportResult> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiFetch(
    `/api/v1/courses/${courseId}/plan/import-ics?confirm_exam=${confirmExam}`,
    { method: 'POST', body: form }
  )
  return json<IcsImportResult>(response)
}

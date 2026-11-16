import type { components } from '@/lib/api-schema'

import { apiFetch, json } from './client'

type Schemas = components['schemas']

export type Paper = Schemas['PaperOut']
export type PaperSection = Schemas['PaperSectionOut']
export type PaperReport = Schemas['PaperReportOut']
export type PaperReportSection = Schemas['PaperReportSectionOut']
export type PaperTopic = Schemas['PaperTopicOut']
export type PaperCreate = Schemas['PaperIn']
export type PaperSectionCreate = Schemas['PaperSectionIn']

export async function listPapers(courseId: string): Promise<Paper[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/papers`)
  return json<Paper[]>(response)
}

export async function createPaper(courseId: string, body: PaperCreate): Promise<Paper> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/papers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<Paper>(response)
}

export async function getPaper(paperId: string): Promise<Paper> {
  const response = await apiFetch(`/api/v1/papers/${paperId}`)
  return json<Paper>(response)
}

export async function deletePaper(paperId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/papers/${paperId}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed (${response.status})`)
  }
}

export async function paperReport(
  paperId: string,
  attemptId?: string | null
): Promise<PaperReport> {
  const params = new URLSearchParams()
  if (attemptId) {
    params.set('attempt_id', attemptId)
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/papers/${paperId}/report${suffix}`)
  return json<PaperReport>(response)
}

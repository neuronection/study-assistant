import { json, apiFetch } from './client'
import type { BlockDto } from './materials'
import type { GenerateContext } from './ai'

export interface FlashcardInfo {
  id: number
  kind: string
  front: BlockDto[]
  back: BlockDto[]
  source: string
  source_ref: string | null
  node_id: number | null
  due_at: string | null
  state: string | null
}

export interface ReviewResult {
  interval_days: number
  due_at: string
  state: string
}

export async function listFlashcards(
  courseId?: number,
  nodeId?: number,
  includeChildren = true
): Promise<FlashcardInfo[]> {
  const params = new URLSearchParams()
  if (courseId !== undefined) {
    params.set('course_id', String(courseId))
  }
  if (nodeId !== undefined) {
    params.set('node_id', String(nodeId))
    params.set('include_children', String(includeChildren))
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/flashcards${suffix}`)
  return json<FlashcardInfo[]>(response)
}

export async function dueFlashcards(
  limit = 20,
  courseId?: number,
  nodeId?: number
): Promise<FlashcardInfo[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (courseId !== undefined) {
    params.set('course_id', String(courseId))
  }
  if (nodeId !== undefined) {
    params.set('node_id', String(nodeId))
    params.set('include_children', 'true')
  }
  const response = await apiFetch(`/api/v1/flashcards/due?${params.toString()}`)
  return json<FlashcardInfo[]>(response)
}

export async function reviewFlashcard(cardId: number, rating: number): Promise<ReviewResult> {
  const response = await apiFetch(`/api/v1/flashcards/${cardId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rating }),
  })
  return json<ReviewResult>(response)
}

export async function generateFlashcards(body: {
  source: string
  note_id?: number | null
  material_id?: number | null
  course_id: number
  node_id?: number | null
  count?: number
} & GenerateContext): Promise<FlashcardInfo[]> {
  const response = await apiFetch('/api/v1/flashcards/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<FlashcardInfo[]>(response)
}

export async function importAnkiDeck(
  file: File,
  courseId: number
): Promise<{ imported: number; skipped: number }> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ course_id: String(courseId) })
  const response = await apiFetch(`/api/v1/flashcards/import-anki?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
  return json<{ imported: number; skipped: number }>(response)
}

export function ankiExportUrl(courseId?: number): string {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  return `/api/v1/flashcards/export-anki${params}`
}

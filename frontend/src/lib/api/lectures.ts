import type { components } from '@/lib/api-schema'

import { apiFetch, json } from './client'

type Schemas = components['schemas']

export type Lecture = Schemas['LectureOut']
export type LectureChunk = Schemas['LectureChunkOut']

export async function createLecture(body: {
  course_id: string
  node_id?: string | null
  title?: string
  consent_confirmed: boolean
  retention?: string
  mime?: string
}): Promise<Lecture> {
  const response = await apiFetch('/api/v1/lectures', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<Lecture>(response)
}

export async function listLectures(courseId?: string): Promise<Lecture[]> {
  const query = courseId ? `?course_id=${encodeURIComponent(courseId)}` : ''
  const response = await apiFetch(`/api/v1/lectures${query}`)
  return json<Lecture[]>(response)
}

export async function getLecture(id: string): Promise<Lecture> {
  const response = await apiFetch(`/api/v1/lectures/${id}`)
  return json<Lecture>(response)
}

export async function patchLecture(
  id: string,
  body: { title?: string; status?: string; retention?: string }
): Promise<Lecture> {
  const response = await apiFetch(`/api/v1/lectures/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<Lecture>(response)
}

export async function uploadLectureChunk(
  id: string,
  seq: number,
  data: ArrayBuffer,
  sha256: string
): Promise<LectureChunk> {
  const response = await apiFetch(`/api/v1/lectures/${id}/chunks/${seq}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/octet-stream',
      'X-Chunk-Sha256': sha256,
    },
    body: data,
  })
  return json<LectureChunk>(response)
}

export async function finalizeLecture(id: string): Promise<{ material_id: string; status: string }> {
  const response = await apiFetch(`/api/v1/lectures/${id}/finalize`, { method: 'POST' })
  return json<{ material_id: string; status: string }>(response)
}

export async function cancelLecture(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/lectures/${id}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`cancel failed (${response.status})`)
  }
}

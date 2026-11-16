import type { components } from '@/lib/api-schema'

import { apiFetch, json } from './client'
import type { StudioSpecView } from './hand-types'

type Schemas = components['schemas']

export type StudioArtifact = Omit<Schemas['StudioOut'], 'spec'> & {
  spec: StudioSpecView
}
export type StudioCreate = Schemas['StudioCreateIn']
export type StudioUpdate = Schemas['StudioUpdateIn']
export type StudioMarkdown = Schemas['StudioMarkdownOut']

export async function listStudioArtifacts(courseId?: string): Promise<StudioArtifact[]> {
  const query = courseId ? `?course_id=${encodeURIComponent(courseId)}` : ''
  const response = await apiFetch(`/api/v1/studio/artifacts${query}`)
  return json<StudioArtifact[]>(response)
}

export async function createStudioArtifact(body: StudioCreate): Promise<StudioArtifact> {
  const response = await apiFetch('/api/v1/studio/artifacts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<StudioArtifact>(response)
}

export async function getStudioArtifact(id: string): Promise<StudioArtifact> {
  const response = await apiFetch(`/api/v1/studio/artifacts/${id}`)
  return json<StudioArtifact>(response)
}

export async function updateStudioArtifact(
  id: string,
  body: StudioUpdate
): Promise<StudioArtifact> {
  const response = await apiFetch(`/api/v1/studio/artifacts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<StudioArtifact>(response)
}

export async function deleteStudioArtifact(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/studio/artifacts/${id}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed (${response.status})`)
  }
}

export async function studioMarkdown(id: string): Promise<StudioMarkdown> {
  const response = await apiFetch(`/api/v1/studio/artifacts/${id}/markdown`)
  return json<StudioMarkdown>(response)
}

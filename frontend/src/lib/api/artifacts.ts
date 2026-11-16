import type { components } from '@/lib/api-schema'

import { apiFetch, json } from './client'
import type { ArtifactSpecView } from './hand-types'

type Schemas = components['schemas']

export type Artifact = Omit<Schemas['ArtifactOut'], 'spec'> & {
  spec: ArtifactSpecView
}
export type NarrationCreate = Schemas['NarrationIn']

export async function createNarration(body: NarrationCreate): Promise<Artifact> {
  const response = await apiFetch('/api/v1/artifacts/narrate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<Artifact>(response)
}

export async function listArtifacts(courseId?: string): Promise<Artifact[]> {
  const query = courseId ? `?course_id=${encodeURIComponent(courseId)}` : ''
  const response = await apiFetch(`/api/v1/artifacts${query}`)
  return json<Artifact[]>(response)
}

export async function getArtifact(id: string): Promise<Artifact> {
  const response = await apiFetch(`/api/v1/artifacts/${id}`)
  return json<Artifact>(response)
}

export async function retryArtifact(id: string): Promise<Artifact> {
  const response = await apiFetch(`/api/v1/artifacts/${id}/retry`, { method: 'POST' })
  return json<Artifact>(response)
}

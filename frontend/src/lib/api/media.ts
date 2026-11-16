import type { components } from '@/lib/api-schema'

import { apiFetch, json } from './client'

type Schemas = components['schemas']

export type MediaInfo = Schemas['MediaOut']
export type MediaSegment = Schemas['MediaSegmentOut']

export async function getMaterialMedia(materialId: string): Promise<MediaInfo> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/media`)
  return json<MediaInfo>(response)
}

export async function patchMediaSegment(
  segmentId: string,
  body: { text?: string; speaker?: string | null }
): Promise<MediaSegment> {
  const response = await apiFetch(`/api/v1/media/segments/${segmentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<MediaSegment>(response)
}

export async function createMediaSegment(
  materialId: string,
  body: { start_ms: number; end_ms: number; text: string; speaker?: string | null; order_idx?: number }
): Promise<MediaSegment> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/media/segments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<MediaSegment>(response)
}

export async function splitMediaSegment(
  segmentId: string,
  atMs: number
): Promise<MediaSegment> {
  const response = await apiFetch(`/api/v1/media/segments/${segmentId}/split`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ at_ms: Math.round(atMs) }),
  })
  return json<MediaSegment>(response)
}

export async function mergeMediaSegments(
  firstId: string,
  secondId: string
): Promise<MediaSegment> {
  const response = await apiFetch('/api/v1/media/segments/merge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ first_id: firstId, second_id: secondId }),
  })
  return json<MediaSegment>(response)
}

export async function deleteMediaSegment(segmentId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/media/segments/${segmentId}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed (${response.status})`)
  }
}

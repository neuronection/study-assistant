import type { components } from '@/lib/api-schema'
import { apiFetch, json } from './client'

export type ExternalSourceRow = components['schemas']['ExternalSourceOut']
export type ExternalSourceKind =
  | 'rss'
  | 'youtube_channel'
  | 'youtube_playlist'
  | 'site_search'

export async function listExternalSources(
  courseId?: number | null
): Promise<ExternalSourceRow[]> {
  const suffix = courseId != null ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/external-sources${suffix}`)
  return json<ExternalSourceRow[]>(response)
}

export async function createExternalSource(body: {
  course_id: number
  kind: ExternalSourceKind
  url: string
  label?: string | null
  options?: Record<string, unknown> | null
  enabled?: boolean
  scan_interval_sec?: number | null
}): Promise<ExternalSourceRow> {
  const response = await apiFetch('/api/v1/external-sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ExternalSourceRow>(response)
}

export async function updateExternalSource(
  id: number,
  body: {
    label?: string | null
    enabled?: boolean
    options?: Record<string, unknown> | null
    scan_interval_sec?: number | null
  }
): Promise<ExternalSourceRow> {
  const response = await apiFetch(`/api/v1/external-sources/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ExternalSourceRow>(response)
}

export async function deleteExternalSource(id: number): Promise<void> {
  const response = await apiFetch(`/api/v1/external-sources/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export async function scanExternalSource(
  id: number
): Promise<{ new: number; updated: number }> {
  const response = await apiFetch(`/api/v1/external-sources/${id}/scan`, {
    method: 'POST',
  })
  return json<{ new: number; updated: number }>(response)
}

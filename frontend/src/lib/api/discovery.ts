import type { components } from '@/lib/api-schema'
import { apiFetch, json } from './client'

export type DiscoveryResultRow = components['schemas']['DiscoveryResultOut']
export type DiscoverySearchResponse = components['schemas']['DiscoverySearchOut']
export type DiscoverySuggestion = components['schemas']['SuggestionOut']
export type DiscoverySuggestionList = components['schemas']['SuggestionListOut']
export type DiscoveryKinds = components['schemas']['DiscoverySitePreset']
export type DiscoveryPrefs = components['schemas']['DiscoveryPrefsOut']

export interface DiscoverySearchRequest {
  query: string
  providers?: string[] | null
  cap?: number
}

export async function searchDiscovery(
  body: DiscoverySearchRequest
): Promise<DiscoverySearchResponse> {
  const response = await apiFetch('/api/v1/discovery/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<DiscoverySearchResponse>(response)
}

export async function listDiscoverySuggestions(params: {
  course_id?: number | null
  node_id?: number | null
  status?: string | null
  kind?: string | null
  limit?: number
  cursor?: number | null
}): Promise<DiscoverySuggestionList> {
  const query = new URLSearchParams()
  if (params.course_id != null) query.set('course_id', String(params.course_id))
  if (params.node_id != null) query.set('node_id', String(params.node_id))
  if (params.status) query.set('status', params.status)
  if (params.kind) query.set('kind', params.kind)
  if (params.limit != null) query.set('limit', String(params.limit))
  if (params.cursor != null) query.set('cursor', String(params.cursor))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const response = await apiFetch(`/api/v1/discovery/suggestions${suffix}`)
  return json<DiscoverySuggestionList>(response)
}

export async function saveDiscoverySuggestion(body: {
  provider: string
  url: string
  title: string
  snippet?: string | null
  kind?: string | null
  meta?: Record<string, unknown> | null
  course_id?: number | null
  node_id?: number | null
}): Promise<{ suggestion: DiscoverySuggestion; created: boolean }> {
  const response = await apiFetch('/api/v1/discovery/suggestions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<{ suggestion: DiscoverySuggestion; created: boolean }>(response)
}

export async function patchDiscoverySuggestion(
  id: number,
  body: { status?: string | null; material_id?: number | null; node_id?: number | null }
): Promise<DiscoverySuggestion> {
  const response = await apiFetch(`/api/v1/discovery/suggestions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<DiscoverySuggestion>(response)
}

export async function deleteDiscoverySuggestion(id: number): Promise<void> {
  const response = await apiFetch(`/api/v1/discovery/suggestions/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

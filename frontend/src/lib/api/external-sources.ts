import type { components } from '@/lib/api-schema'
import { apiFetch, json } from './client'
import type { ExternalSourceKind } from './hand-types'

export type ExternalSourceRow = components['schemas']['ExternalSourceOut']
export type SourceProvider = components['schemas']['SourceProviderOut']
export type SourceProviderCatalog = components['schemas']['SourceProviderCatalogOut']
export type SourceSecretStatus = components['schemas']['SecretStatusOut']
export type SourceOAuthStatus = components['schemas']['OAuthStatusOut']
export type SourceRemoteBackup = components['schemas']['RemoteBackupOut']
export type SourceRemoteBackupList = components['schemas']['RemoteBackupListOut']
export type SourceBackupUpload = components['schemas']['BackupUploadOut']
export type SourceAcceptResult = components['schemas']['AcceptOut']
export { type ExternalSourceKind } from './hand-types'

export async function listSourceProviders(): Promise<SourceProviderCatalog> {
  const response = await apiFetch('/api/v1/external-sources/providers')
  return json<SourceProviderCatalog>(response)
}

export async function listExternalSources(
  courseId?: string | null
): Promise<ExternalSourceRow[]> {
  const suffix = courseId != null ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/external-sources${suffix}`)
  return json<ExternalSourceRow[]>(response)
}

export async function createExternalSource(body: {
  course_id: string
  provider: string
  kind: ExternalSourceKind
  url?: string
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
  id: string,
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

export async function deleteExternalSource(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/external-sources/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export async function scanExternalSource(id: string): Promise<Record<string, number>> {
  const response = await apiFetch(`/api/v1/external-sources/${id}/scan`, {
    method: 'POST',
  })
  return json<Record<string, number>>(response)
}

export async function setExternalSourceSecret(
  id: string,
  slot: string,
  value: string
): Promise<SourceSecretStatus> {
  const response = await apiFetch(`/api/v1/external-sources/${id}/secret`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slot, value }),
  })
  return json<SourceSecretStatus>(response)
}

export async function deleteExternalSourceSecret(
  id: string,
  slot: string
): Promise<SourceSecretStatus> {
  const response = await apiFetch(`/api/v1/external-sources/${id}/secret/${slot}`, {
    method: 'DELETE',
  })
  return json<SourceSecretStatus>(response)
}

export async function connectExternalSource(id: string): Promise<SourceOAuthStatus> {
  const response = await apiFetch(`/api/v1/external-sources/${id}/oauth/connect`, {
    method: 'POST',
  })
  return json<SourceOAuthStatus>(response)
}

export async function disconnectExternalSource(id: string): Promise<SourceOAuthStatus> {
  const response = await apiFetch(`/api/v1/external-sources/${id}/oauth/disconnect`, {
    method: 'POST',
  })
  return json<SourceOAuthStatus>(response)
}

export async function uploadExternalBackup(id: string): Promise<SourceBackupUpload> {
  const response = await apiFetch(`/api/v1/external-sources/${id}/backup`, {
    method: 'POST',
  })
  return json<SourceBackupUpload>(response)
}

export async function listExternalBackups(id: string): Promise<SourceRemoteBackupList> {
  const response = await apiFetch(`/api/v1/external-sources/${id}/backups`)
  return json<SourceRemoteBackupList>(response)
}

export async function restoreExternalBackup(
  id: string,
  name: string
): Promise<{ status: string; materials: number; blobs: number }> {
  const response = await apiFetch(
    `/api/v1/external-sources/${id}/backups/${encodeURIComponent(name)}/restore`,
    { method: 'POST' }
  )
  return json<{ status: string; materials: number; blobs: number }>(response)
}

export async function acceptExternalSuggestion(
  id: string,
  suggestionId: string
): Promise<SourceAcceptResult> {
  const response = await apiFetch(`/api/v1/external-sources/${id}/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ suggestion_id: suggestionId }),
  })
  return json<SourceAcceptResult>(response)
}

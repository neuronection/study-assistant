import type { components } from '@/lib/api-schema'

import { json, apiFetch } from './client'
import type { ImportResult } from './quiz'

type Schemas = components['schemas']

export type BrowseEntry = Schemas['SourceSubdirOut']
export type BrowseMaterial = Schemas['SourceMaterialOut']
export type BrowsePending = Schemas['UningestedFileOut']
export type BrowseResult = Schemas['SourceBrowseOut']
export type LinkedSource = Schemas['SourceOut']
export type ScanResult = Schemas['ScanResult']
export type InboxEntryInfo = Schemas['InboxEntryOut']

export async function browseSource(
  sourceId: string,
  subdir = ''
): Promise<BrowseResult> {
  const params = subdir ? `?subdir=${encodeURIComponent(subdir)}` : ''
  const response = await apiFetch(`/api/v1/sources/${sourceId}/browse${params}`)
  return json<BrowseResult>(response)
}

export async function ingestSourceFile(
  sourceId: string,
  relpath: string
): Promise<{ material_id: string; job_id: string | null; deduped: boolean }> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ relpath }),
  })
  return json<{ material_id: string; job_id: string | null; deduped: boolean }>(response)
}

export async function relinkSource(sourceId: string, path: string): Promise<LinkedSource> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  return json<LinkedSource>(response)
}

export async function revealSource(sourceId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}/reveal`, {
    method: 'POST',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`reveal failed: ${response.status}`)
  }
}

export async function listSources(): Promise<LinkedSource[]> {
  const response = await apiFetch('/api/v1/sources')
  return json<LinkedSource[]>(response)
}

export async function addSource(body: {
  label: string
  path: string
  course_id: string
  recursive?: boolean
  preset?: 'folder' | 'vault'
}): Promise<LinkedSource> {
  const response = await apiFetch('/api/v1/sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<LinkedSource>(response)
}

export async function scanSource(sourceId: string): Promise<ScanResult> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}/scan`, { method: 'POST' })
  return json<ScanResult>(response)
}

export async function setSourceMirror(
  sourceId: string,
  mirrorSubdirs: boolean
): Promise<LinkedSource> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}/mirror`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mirror_subdirs: mirrorSubdirs }),
  })
  return json<LinkedSource>(response)
}

export async function mirrorBackfillSource(sourceId: string): Promise<ScanResult> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}/mirror-backfill`, {
    method: 'POST',
  })
  return json<ScanResult>(response)
}

export async function deleteSource(sourceId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export async function scanInbox(): Promise<InboxEntryInfo[]> {
  const response = await apiFetch('/api/v1/quiz/inbox')
  return json<InboxEntryInfo[]>(response)
}

export async function inboxPath(): Promise<string> {
  const response = await apiFetch('/api/v1/quiz/inbox/path')
  return (await json<{ path: string }>(response)).path
}

export async function importInboxFile(
  filename: string,
  courseId: string
): Promise<ImportResult> {
  const params = new URLSearchParams({ course_id: String(courseId) })
  const response = await apiFetch(
    `/api/v1/quiz/inbox/${encodeURIComponent(filename)}/import?${params.toString()}`,
    { method: 'POST' }
  )
  return json<ImportResult>(response)
}

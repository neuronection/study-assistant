import { json, apiFetch } from './client'
import type { ImportResult } from './quiz'

export interface BrowseEntry {
  name: string
}

export interface BrowseMaterial {
  id: number
  title: string
  kind: string
  status: string
  filename: string
  relpath: string
}

export interface BrowsePending {
  name: string
  relpath: string
  size_bytes: number
  mtime: number
}

export interface BrowseResult {
  source_id: number
  label: string
  path: string
  subdir: string
  missing_target: boolean
  enabled: boolean
  scan_interval_sec: number | null
  last_scan_error: string | null
  last_scanned_at: string | null
  subdirs: BrowseEntry[]
  materials: BrowseMaterial[]
  uningested: BrowsePending[]
}

export async function browseSource(
  sourceId: number,
  subdir = ''
): Promise<BrowseResult> {
  const params = subdir ? `?subdir=${encodeURIComponent(subdir)}` : ''
  const response = await apiFetch(`/api/v1/sources/${sourceId}/browse${params}`)
  return json<BrowseResult>(response)
}

export async function ingestSourceFile(
  sourceId: number,
  relpath: string
): Promise<{ material_id: number; job_id: number | null; deduped: boolean }> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ relpath }),
  })
  return json<{ material_id: number; job_id: number | null; deduped: boolean }>(response)
}

export async function relinkSource(sourceId: number, path: string): Promise<LinkedSource> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  return json<LinkedSource>(response)
}

export async function revealSource(sourceId: number): Promise<void> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}/reveal`, {
    method: 'POST',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`reveal failed: ${response.status}`)
  }
}

export interface LinkedSource {
  id: number
  label: string
  path: string
  recursive: boolean
  include_globs: string[] | null
  course_id: number
  enabled: boolean
  material_count: number
  last_scanned_at: string | null
}

export interface ScanResult {
  stats: { new: number; updated: number; unchanged: number; missing: number }
  queued_jobs: number
}

export async function listSources(): Promise<LinkedSource[]> {
  const response = await apiFetch('/api/v1/sources')
  return json<LinkedSource[]>(response)
}

export async function addSource(body: {
  label: string
  path: string
  course_id: number
  recursive?: boolean
}): Promise<LinkedSource> {
  const response = await apiFetch('/api/v1/sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<LinkedSource>(response)
}

export async function scanSource(sourceId: number): Promise<ScanResult> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}/scan`, { method: 'POST' })
  return json<ScanResult>(response)
}

export async function deleteSource(sourceId: number): Promise<void> {
  const response = await apiFetch(`/api/v1/sources/${sourceId}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export interface InboxEntryInfo {
  filename: string
  kind: string
  title: string
  ok: boolean
  problems: string[]
  question_count: number
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
  courseId: number
): Promise<ImportResult> {
  const params = new URLSearchParams({ course_id: String(courseId) })
  const response = await apiFetch(
    `/api/v1/quiz/inbox/${encodeURIComponent(filename)}/import?${params.toString()}`,
    { method: 'POST' }
  )
  return json<ImportResult>(response)
}

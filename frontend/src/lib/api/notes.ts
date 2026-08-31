import { json, apiFetch } from './client'
import type { BlockDto } from './materials'

export async function saveSessionSummaryNote(
  sessionId: number
): Promise<{ note_id: number; node_title: string | null }> {
  const response = await apiFetch(`/api/v1/exercises/sessions/${sessionId}/summary-note`, {
    method: 'POST',
  })
  return json(response)
}

export interface NoteInfo {
  id: number
  title: string
  course_id: number | null
  node_id: number | null
  owner_type: string
  owner_id: number | null
  tags: string[]
  pinned: boolean
  updated_at: string
}

export interface NoteDrawingInfo {
  id: number
  png_sha: string | null
  strokes: unknown[]
  view?: { x: number; y: number; width: number; height: number } | null
  ocr_version: number
  ocr_markdown: string | null
  ocr_job_id?: number | null
  created_at: string
}

export interface NoteDetailInfo extends NoteInfo {
  body: BlockDto[]
  drawings: NoteDrawingInfo[]
}

export interface NotesPage {
  items: NoteInfo[]
  next_cursor: string | null
}

export async function listNotes(
  query?: string,
  courseId?: number,
  options?: { tag?: string; limit?: number; cursor?: string; node_id?: number; include_children?: boolean }
): Promise<NotesPage> {
  const params = new URLSearchParams()
  if (query) {
    params.set('q', query)
  }
  if (options?.node_id !== undefined) {
    params.set('node_id', String(options.node_id))
    params.set('include_children', String(options.include_children ?? true))
  } else if (courseId !== undefined) {
    params.set('course_id', String(courseId))
  }
  if (options?.tag) {
    params.set('tag', options.tag)
  }
  if (options?.limit !== undefined) {
    params.set('limit', String(options.limit))
  }
  if (options?.cursor) {
    params.set('cursor', options.cursor)
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/notes${suffix}`)
  return json<NotesPage>(response)
}

export interface NoteTagSummary {
  tag: string
  count: number
}

export async function listNoteTags(courseId?: number): Promise<NoteTagSummary[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/notes/tags/list${params}`)
  return json<NoteTagSummary[]>(response)
}

export async function createNote(body: {
  title: string
  body_md?: string
  course_id: number
  node_id?: number | null
  owner_type?: string
  owner_id?: number | null
  tags?: string[]
}): Promise<NoteDetailInfo> {
  const response = await apiFetch('/api/v1/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<NoteDetailInfo>(response)
}

export async function getNote(id: number): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${id}`)
  return json<NoteDetailInfo>(response)
}

export async function composeNote(body: {
  course_id: number
  node_id?: number | null
  scope?: string
  title?: string | null
  instructions?: string | null
  include_material_ids?: number[]
  exclude_material_ids?: number[]
  note_ids?: number[]
  concept_ids?: number[]
  context_hint?: string | null
}): Promise<NoteDetailInfo> {
  const response = await apiFetch('/api/v1/notes/compose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<NoteDetailInfo>(response)
}

export async function updateNote(
  id: number,
  body: {
    title?: string
    body_md?: string
    pinned?: boolean
    tags?: string[]
    base_updated_at?: string
    force_version?: boolean
  }
): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<NoteDetailInfo>(response)
}

export async function moveNote(
  id: number,
  nodeId: number | null
): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${id}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  })
  return json<NoteDetailInfo>(response)
}

export interface NoteVersionInfo {
  version_id: number
  cause: string
  title: string
  chars: number
  created_at: string
}

export interface NoteVersionDetailInfo extends NoteVersionInfo {
  body_md: string
}

export async function listNoteVersions(id: number): Promise<NoteVersionInfo[]> {
  const response = await apiFetch(`/api/v1/notes/${id}/versions`)
  return json<NoteVersionInfo[]>(response)
}

export async function getNoteVersion(
  noteId: number,
  versionId: number
): Promise<NoteVersionDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/versions/${versionId}`)
  return json<NoteVersionDetailInfo>(response)
}

export async function restoreNoteVersion(
  noteId: number,
  versionId: number
): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/restore`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version_id: versionId }),
  })
  return json<NoteDetailInfo>(response)
}

export async function deleteNote(id: number): Promise<{ deleted_item_id: number }> {
  const response = await apiFetch(`/api/v1/notes/${id}`, { method: 'DELETE' })
  return json<{ deleted_item_id: number }>(response)
}

export async function addDrawing(
  noteId: number,
  strokes: unknown[],
  pngBase64: string,
  ocr = true,
  view?: { x: number; y: number; width: number; height: number } | null
): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/drawings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strokes, png_base64: pngBase64, ocr, view }),
  })
  return json<NoteDetailInfo>(response)
}

export async function reocrDrawing(noteId: number, drawingId: number): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/drawings/${drawingId}/reocr`, {
    method: 'POST',
  })
  return json<NoteDetailInfo>(response)
}

export async function updateDrawing(
  noteId: number,
  drawingId: number,
  strokes: unknown[],
  pngBase64: string,
  ocr: boolean,
  view?: { x: number; y: number; width: number; height: number } | null
): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/drawings/${drawingId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strokes, png_base64: pngBase64, ocr, view }),
  })
  return json<NoteDetailInfo>(response)
}

export async function deleteDrawing(noteId: number, drawingId: number): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/drawings/${drawingId}`, {
    method: 'DELETE',
  })
  return json<NoteDetailInfo>(response)
}

export interface NoteActionResult {
  action: string
  markdown: string
  violations: string | null
}

export async function runNoteAction(
  noteId: number,
  action: 'summarize' | 'cleanup' | 'explain' | 'expand'
): Promise<NoteActionResult> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/actions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  return json<NoteActionResult>(response)
}

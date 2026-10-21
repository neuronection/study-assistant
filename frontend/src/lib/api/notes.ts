import type { components } from '@/lib/api-schema'

import { json, apiFetch } from './client'
import type { BlockDto } from './hand-types'

type Schemas = components['schemas']

export type NoteInfo = Schemas['NoteOut']
export type NoteDrawingInfo = Schemas['DrawingOut']
export type NoteDetailInfo = Omit<Schemas['NoteDetail'], 'body' | 'drawings'> & {
  body: BlockDto[]
  drawings: NoteDrawingInfo[]
}
export type NotesPage = Schemas['NotesPage']
export type NoteTagSummary = Schemas['NoteTagCountOut']
export type NoteVersionInfo = Schemas['NoteVersionOut']
export type NoteVersionDetailInfo = Schemas['NoteVersionDetail']
export type NoteActionResult = Schemas['ActionOut']
export type NoteVersionDiffInfo = Schemas['NoteVersionDiffOut']

export async function saveSessionSummaryNote(
  sessionId: string
): Promise<{ note_id: string; node_title: string | null }> {
  const response = await apiFetch(`/api/v1/exercises/sessions/${sessionId}/summary-note`, {
    method: 'POST',
  })
  return json(response)
}

export async function listNotes(
  query?: string,
  courseId?: string,
  options?: { tag?: string; limit?: number; cursor?: string; node_id?: string; include_children?: boolean }
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

export async function listNoteTags(courseId?: string): Promise<NoteTagSummary[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/notes/tags/list${params}`)
  return json<NoteTagSummary[]>(response)
}

export async function createNote(body: {
  title: string
  body_md?: string
  course_id: string
  node_id?: string | null
  owner_type?: string
  owner_id?: string | null
  tags?: string[]
}): Promise<NoteDetailInfo> {
  const response = await apiFetch('/api/v1/notes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<NoteDetailInfo>(response)
}

export async function getNote(id: string): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${id}`)
  return json<NoteDetailInfo>(response)
}

export async function composeNote(body: {
  course_id: string
  node_id?: string | null
  scope?: string
  title?: string | null
  instructions?: string | null
  include_material_ids?: string[]
  exclude_material_ids?: string[]
  note_ids?: string[]
  concept_ids?: string[]
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
  id: string,
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
  id: string,
  nodeId: string | null
): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${id}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  })
  return json<NoteDetailInfo>(response)
}

export async function listNoteVersions(id: string): Promise<NoteVersionInfo[]> {
  const response = await apiFetch(`/api/v1/notes/${id}/versions`)
  return json<NoteVersionInfo[]>(response)
}

export async function getNoteVersion(
  noteId: string,
  versionId: string
): Promise<NoteVersionDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/versions/${versionId}`)
  return json<NoteVersionDetailInfo>(response)
}

export async function restoreNoteVersion(
  noteId: string,
  versionId: string
): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/restore`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version_id: versionId }),
  })
  return json<NoteDetailInfo>(response)
}

export async function deleteNote(id: string): Promise<{ deleted_item_id: string }> {
  const response = await apiFetch(`/api/v1/notes/${id}`, { method: 'DELETE' })
  return json<{ deleted_item_id: string }>(response)
}

export async function addDrawing(
  noteId: string,
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

export async function reocrDrawing(noteId: string, drawingId: string): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/drawings/${drawingId}/reocr`, {
    method: 'POST',
  })
  return json<NoteDetailInfo>(response)
}

export async function updateDrawing(
  noteId: string,
  drawingId: string,
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

export async function deleteDrawing(noteId: string, drawingId: string): Promise<NoteDetailInfo> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/drawings/${drawingId}`, {
    method: 'DELETE',
  })
  return json<NoteDetailInfo>(response)
}

export async function runNoteAction(
  noteId: string,
  action: 'summarize' | 'cleanup' | 'explain' | 'expand'
): Promise<NoteActionResult> {
  const response = await apiFetch(`/api/v1/notes/${noteId}/actions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  return json<NoteActionResult>(response)
}

export async function diffNoteVersions(
  noteId: string,
  from: string,
  to: string
): Promise<NoteVersionDiffInfo> {
  const response = await apiFetch(
    `/api/v1/notes/${noteId}/versions/diff?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`
  )
  return json<NoteVersionDiffInfo>(response)
}

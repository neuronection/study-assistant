import type { components } from '@/lib/api-schema'
import { ApiError, json, expectOk, apiFetch } from './client'

type Schemas = components['schemas']

export type AcceptedTypes = Schemas['AcceptedTypesOut']
import type { NoteDrawingInfo } from './notes'

export interface Material {
  id: number
  title: string
  kind: string
  status: string
  filename: string
  mime: string | null
  pages: number | null
  course_id: number
  group_id: number | null
  folder_id: number | null
  blob_sha: string | null
  provenance?: { source?: string; kind?: string; model?: string | null } | null
  created_at: string
}

export interface Extraction {
  id: number
  material_id: number
  version: number
  extractor: string
  markdown: string
  blocks: BlockDto[]
}

export interface BlockDto {
  type: string
  md?: string
  [key: string]: unknown
}

export interface IndexCard {
  reading_minutes: number | null
  summary: string | null
  topics: string[]
  key_terms: string[] | null
  difficulty: number | null
}

export interface MaterialDetail {
  material: Material
  extraction: Extraction | null
  index_card: IndexCard | null
  drawings: NoteDrawingInfo[]
}

export interface UploadResult {
  material: Material
  job_id: number | null
  deduped: boolean
}

export interface SearchHitDto {
  material_id: number
  title: string
  snippet: string
  score?: number
}

export async function uploadMaterial(
  file: File,
  courseId: number,
  folderId: number | null = null
): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ course_id: String(courseId) })
  if (folderId !== null) {
    params.set('folder_id', String(folderId))
  }
  const response = await apiFetch(`/api/v1/materials?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
  return json<UploadResult>(response)
}

export async function listMaterials(
  folderId?: number,
  courseId?: number,
  unfiled?: boolean
): Promise<Material[]> {
  const params = new URLSearchParams()
  if (folderId !== undefined) {
    params.set('folder_id', String(folderId))
  }
  if (courseId !== undefined) {
    params.set('course_id', String(courseId))
  }
  if (unfiled) {
    params.set('unfiled', 'true')
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/materials${suffix}`)
  return json<Material[]>(response)
}

export interface MaterialLinkInfo {
  node_id: number
  owner_title: string
  breadcrumb: { id: number; title: string }[]
  is_course_level: boolean
  course_id: number | null
  course_title: string | null
  auto_assigned: boolean
  rationale: string | null
  via_folder: { id: number; name: string } | null
}

export async function getMaterialLinks(materialId: number): Promise<MaterialLinkInfo[]> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/links`)
  return json<MaterialLinkInfo[]>(response)
}

export async function createTextFile(body: {
  course_id: number
  folder_id?: number | null
  filename: string
  content: string
}): Promise<UploadResult> {
  const response = await apiFetch('/api/v1/materials/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<UploadResult>(response)
}

export interface PendingDrawing {
  ref: number
  strokes: unknown[]
  png_base64: string
  ocr: boolean
  view?: { x: number; y: number; width: number; height: number } | null
}

export function remapDrawingRefsInMarkdown(
  markdown: string,
  mapping: Record<number, number>
): string {
  return markdown.replace(/!\[[^\]]*\]\(ca-drawing:\/\/(-?\d+)\)/g, (full, idStr: string) => {
    const old = Number(idStr)
    const next = mapping[old] ?? old
    const alt = full.split('](')[0].slice(2)
    return `![${alt}](ca-drawing://${next})`
  })
}

async function waitForMaterialReady(materialId: number, timeoutMs = 15000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const detail = await getMaterial(materialId)
    if (detail.material.status === 'ready') {
      return
    }
    if (detail.material.status === 'failed') {
      throw new ApiError('material ingest failed', 502)
    }
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  throw new ApiError('material ingest timed out', 504)
}

export interface TextFileEditState {
  materialId: number
  content: string
  refToReal: Record<number, number>
  jobId: number | null
}

export async function createTextMaterial(params: {
  course_id: number
  folder_id?: number | null
  filename: string
  content: string
  drawings: PendingDrawing[]
}): Promise<TextFileEditState | null> {
  const created = await createTextFile({
    course_id: params.course_id,
    folder_id: params.folder_id,
    filename: params.filename,
    content: params.content,
  })
  if (created.deduped) {
    return null
  }
  const materialId = created.material.id
  if (params.drawings.length === 0) {
    return { materialId, content: params.content, refToReal: {}, jobId: created.job_id }
  }
  await waitForMaterialReady(materialId)
  const refToReal = await commitNewDrawings(materialId, params.drawings)
  const content = remapDrawingRefsInMarkdown(params.content, refToReal)
  await editExtraction(materialId, content)
  return { materialId, content, refToReal, jobId: created.job_id }
}

export async function updateTextMaterial(params: {
  materialId: number
  content: string
  drawings: PendingDrawing[]
}): Promise<TextFileEditState> {
  const refToReal = await commitNewDrawings(params.materialId, params.drawings)
  const content = remapDrawingRefsInMarkdown(params.content, refToReal)
  await editExtraction(params.materialId, content)
  return { materialId: params.materialId, content, refToReal, jobId: null }
}

export async function reingestMaterial(materialId: number): Promise<UploadResult> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/reingest`, {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error(`re-ingest failed (${response.status})`)
  }
  return json<UploadResult>(response)
}

async function commitNewDrawings(
  materialId: number,
  drawings: PendingDrawing[]
): Promise<Record<number, number>> {
  const known = new Set<number>()
  const refToReal: Record<number, number> = {}
  for (const pending of drawings) {
    if (pending.ref > 0) {
      known.add(pending.ref)
      continue
    }
    const detail = await addMaterialDrawing(
      materialId,
      pending.strokes,
      pending.png_base64,
      pending.ocr,
      pending.view
    )
    const real = detail.drawings.find((entry) => !known.has(entry.id))
    if (real !== undefined) {
      known.add(real.id)
      refToReal[pending.ref] = real.id
    }
  }
  return refToReal
}

export async function renameMaterial(id: number, title: string): Promise<Material> {
  const response = await apiFetch(`/api/v1/materials/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return json<Material>(response)
}

export async function moveMaterial(
  id: number,
  folderId: number | null
): Promise<Material> {
  const response = await apiFetch(`/api/v1/materials/${id}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId }),
  })
  return json<Material>(response)
}

export async function copyMaterial(
  id: number,
  folderId: number | null
): Promise<Material> {
  const response = await apiFetch(`/api/v1/materials/${id}/copy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId }),
  })
  return json<Material>(response)
}

export async function deriveMaterial(
  id: number,
  options?: { folderId?: number | null; nodeId?: number | null }
): Promise<UploadResult> {
  const response = await apiFetch(`/api/v1/materials/${id}/derive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      folder_id: options?.folderId ?? null,
      node_id: options?.nodeId ?? null,
    }),
  })
  return json<UploadResult>(response)
}

export async function deleteMaterial(id: number): Promise<void> {
  const response = await apiFetch(`/api/v1/materials/${id}`, { method: 'DELETE' })
  await expectOk(response)
}

export async function getMaterial(id: number): Promise<MaterialDetail> {
  const response = await apiFetch(`/api/v1/materials/${id}`)
  return json<MaterialDetail>(response)
}

export async function search(
  query: string,
  courseId?: number
): Promise<{ query: string; hits: SearchHitDto[] }> {
  const course = courseId !== undefined ? `&course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/search?q=${encodeURIComponent(query)}${course}`)
  return json<{ query: string; hits: SearchHitDto[] }>(response)
}

export async function editExtraction(
  materialId: number,
  markdown: string
): Promise<Extraction> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/extraction`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ markdown }),
  })
  return json<Extraction>(response)
}

export interface MindmapEditResult {
  markdown: string
}

export interface ExtractionVersionInfo {
  version: number
  extractor: string
  created_at: string
}

export async function listExtractionVersions(
  materialId: number
): Promise<ExtractionVersionInfo[]> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/extractions`)
  return json<ExtractionVersionInfo[]>(response)
}

export async function getExtractionVersion(
  materialId: number,
  version: number
): Promise<Extraction> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/extractions/${version}`)
  return json<Extraction>(response)
}

export async function mindmapEdit(
  materialId: number,
  body: { mode?: string; instruction?: string | null; focus_node?: string | null }
): Promise<MindmapEditResult> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/mindmap-edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<MindmapEditResult>(response)
}

export interface WorkspaceConcept {
  id: number
  name: string
  direct: boolean
  node_ids: number[]
}

export interface CourseMaterialLink {
  node_id: number
  node_title: string
  node_is_root: boolean
  material_id: number
  title: string
  rationale: string | null
  auto_assigned: boolean
  confidence: number | null
}

export async function listCourseMaterials(courseId: number): Promise<CourseMaterialLink[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/materials`)
  return json<CourseMaterialLink[]>(response)
}

export async function assignCourseMaterial(
  courseId: number,
  materialId: number
): Promise<void> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/materials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ material_id: materialId }),
  })
  await json<unknown>(response)
}

export async function unassignCourseMaterial(
  courseId: number,
  materialId: number
): Promise<void> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/materials/${materialId}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export async function allocateMaterial(
  nodeId: number,
  materialId: number
): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/materials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ material_id: materialId }),
  })
  await json<unknown>(response)
}

export async function deallocateMaterial(
  nodeId: number,
  materialId: number
): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/materials/${materialId}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export async function allocateNodeFolder(
  nodeId: number,
  folderId: number,
  rationale?: string
): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/folder-materials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId, rationale }),
  })
  await json<unknown>(response)
}

export async function deallocateNodeFolder(
  nodeId: number,
  folderId: number
): Promise<void> {
  const response = await apiFetch(
    `/api/v1/nodes/${nodeId}/folder-materials/${folderId}`,
    { method: 'DELETE' }
  )
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export const COMPOSE_KINDS = [
  'study_guide',
  'summary_sheet',
  'practice_set',
  'error_recap',
  'mindmap',
  'formula_sheet',
  'cheat_sheet',
] as const

export type ComposeKind = (typeof COMPOSE_KINDS)[number]

export interface ComposedMaterial {
  material: Material
  job_id: number | null
  deduped: boolean
}

export async function composeMaterial(body: {
  course_id: number
  node_id?: number | null
  kind: ComposeKind
  title?: string | null
  instructions?: string | null
  extra_md?: string | null
  scope?: string
  include_material_ids?: number[]
  exclude_material_ids?: number[]
  note_ids?: number[]
  concept_ids?: number[]
  context_hint?: string | null
  regenerate?: boolean
}): Promise<ComposedMaterial> {
  const response = await apiFetch('/api/v1/materials/compose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ComposedMaterial>(response)
}

export async function addMaterialDrawing(
  materialId: number,
  strokes: unknown[],
  pngBase64: string,
  ocr = true,
  view?: { x: number; y: number; width: number; height: number } | null
): Promise<MaterialDetail> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/drawings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strokes, png_base64: pngBase64, ocr, view }),
  })
  return json<MaterialDetail>(response)
}

export async function updateMaterialDrawing(
  materialId: number,
  drawingId: number,
  strokes: unknown[],
  pngBase64: string,
  ocr: boolean,
  view?: { x: number; y: number; width: number; height: number } | null
): Promise<MaterialDetail> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/drawings/${drawingId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ strokes, png_base64: pngBase64, ocr, view }),
  })
  return json<MaterialDetail>(response)
}

export async function reocrMaterialDrawing(
  materialId: number,
  drawingId: number
): Promise<MaterialDetail> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/drawings/${drawingId}/reocr`, {
    method: 'POST',
  })
  return json<MaterialDetail>(response)
}

export async function deleteMaterialDrawing(
  materialId: number,
  drawingId: number
): Promise<MaterialDetail> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/drawings/${drawingId}`, {
    method: 'DELETE',
  })
  return json<MaterialDetail>(response)
}

export async function getAcceptedTypes(): Promise<AcceptedTypes> {
  const response = await apiFetch('/api/v1/materials/accepted')
  return json<AcceptedTypes>(response)
}

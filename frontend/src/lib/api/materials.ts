import type { components } from '@/lib/api-schema'
import { ApiError, json, expectOk, apiFetch } from './client'

type Schemas = components['schemas']

export type AcceptedTypes = Schemas['AcceptedTypesOut']
import type { NoteDrawingInfo } from './notes'

export interface Material {
  id: string
  title: string
  description?: string | null
  kind: string
  status: string
  filename: string
  mime: string | null
  pages: number | null
  course_id: string
  folder_id: string | null
  blob_sha: string | null
  provenance?: {
    source?: string
    kind?: string
    model?: string | null
    coverage?: { total: number; covered: number; missing_ids: string[] } | null
    needs_review?: boolean
    video_id?: string
    channel?: string
    duration_sec?: number
    parse_note?: string
  } | null
  source_url?: string | null
  created_at: string
  has_extraction?: boolean
  tags?: string[]
  starred?: boolean
  link_count?: number
  reextract_modes?: string[]
}

export interface Extraction {
  id: string
  material_id: string
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

export interface MaterialImageInfo {
  id: string
  position: number
  blob_sha: string | null
  mime: string | null
  ocr_version: number
  ocr_markdown: string | null
  ocr_job_id: string | null
  created_at: string
}

export interface MaterialDetail {
  material: Material
  extraction: Extraction | null
  index_card: IndexCard | null
  drawings: NoteDrawingInfo[]
  images: MaterialImageInfo[]
}

export interface UploadWarning {
  code: string
  limit_mb: number | null
  file_mb: number | null
}

export interface UploadResult {
  material: Material
  job_id: string | null
  deduped: boolean
  node_id?: string | null
  warnings?: UploadWarning[]
}

export interface SearchHitNodeDto {
  course_id: string
  node_id: string
  node_title: string
}

export interface SearchHitDto {
  material_id: string
  title: string
  snippet: string
  score?: number
  nodes: SearchHitNodeDto[]
}

export async function uploadMaterial(
  file: File,
  courseId: string,
  folderId: string | null = null,
  nodeId: string | null = null
): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ course_id: String(courseId) })
  if (folderId !== null) {
    params.set('folder_id', String(folderId))
  }
  if (nodeId !== null) {
    params.set('node_id', String(nodeId))
  }
  const response = await apiFetch(`/api/v1/materials?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
  return json<UploadResult>(response)
}

export async function listMaterials(
  folderId?: string,
  courseId?: string,
  unfiled?: boolean,
  filters?: { tag?: string; starred?: boolean }
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
  if (filters?.tag) {
    params.set('tag', filters.tag)
  }
  if (filters?.starred) {
    params.set('starred', 'true')
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/materials${suffix}`)
  return json<Material[]>(response)
}

export async function importUrlMaterial(
  courseId: string,
  url: string,
  nodeId?: string | null,
): Promise<UploadResult> {
  const response = await apiFetch('/api/v1/materials/import-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, url, node_id: nodeId ?? null }),
  })
  return json<UploadResult>(response)
}

export async function patchMaterial(
  materialId: string,
  body: { title?: string; description?: string; tags?: string[]; starred?: boolean },
): Promise<Material> {
  const response = await apiFetch(`/api/v1/materials/${materialId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  await expectOk(response)
  return json<Material>(response)
}

export interface MaterialLinkInfo {
  node_id: string
  owner_title: string
  breadcrumb: { id: string; title: string }[]
  is_course_level: boolean
  course_id: string | null
  course_title: string | null
  auto_assigned: boolean
  rationale: string | null
  via_folder: { id: string; name: string } | null
}

export async function getMaterialLinks(materialId: string): Promise<MaterialLinkInfo[]> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/links`)
  return json<MaterialLinkInfo[]>(response)
}

export interface UnassignedMaterial {
  id: string
  title: string
}

export interface UnassignedMaterials {
  count: number
  materials: UnassignedMaterial[]
}

export async function getUnassignedMaterials(courseId: string): Promise<UnassignedMaterials> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/materials/unassigned`)
  return json<UnassignedMaterials>(response)
}

export interface PlacementCandidate {
  node_id: string
  node_title: string
  breadcrumb: { id: string; title: string }[]
  score: number
  matched_on: string[]
}

export interface PlacementSuggestion {
  material_id: string
  candidates: PlacementCandidate[]
}

export async function getPlacementSuggestions(
  courseId: string,
  materialIds: string[]
): Promise<{ suggestions: PlacementSuggestion[] }> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/placement-suggestions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ material_ids: materialIds }),
  })
  return json<{ suggestions: PlacementSuggestion[] }>(response)
}

export async function createTextFile(body: {
  course_id: string
  folder_id?: string | null
  filename: string
  content: string
  description?: string | null
}): Promise<UploadResult> {
  const response = await apiFetch('/api/v1/materials/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<UploadResult>(response)
}

export interface PendingDrawing {
  ref: number | string
  strokes: unknown[]
  png_base64: string
  ocr: boolean
  view?: { x: number; y: number; width: number; height: number } | null
}

export function remapDrawingRefsInMarkdown(
  markdown: string,
  mapping: Record<number, string>
): string {
  return markdown.replace(/!\[[^\]]*\]\(sa-drawing:\/\/(-?\d+)\)/g, (full, idStr: string) => {
    const old = Number(idStr)
    const next = mapping[old] ?? old
    const alt = full.split('](')[0].slice(2)
    return `![${alt}](sa-drawing://${next})`
  })
}

async function waitForMaterialReady(materialId: string, timeoutMs = 15000): Promise<void> {
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
  materialId: string
  content: string
  refToReal: Record<number, string>
  jobId: string | null
}

export async function createTextMaterial(params: {
  course_id: string
  folder_id?: string | null
  filename: string
  content: string
  description?: string | null
  drawings: PendingDrawing[]
}): Promise<TextFileEditState | null> {
  const created = await createTextFile({
    course_id: params.course_id,
    folder_id: params.folder_id,
    filename: params.filename,
    content: params.content,
    description: params.description,
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
  materialId: string
  content: string
  description?: string | null
  drawings: PendingDrawing[]
}): Promise<TextFileEditState> {
  const refToReal = await commitNewDrawings(params.materialId, params.drawings)
  const content = remapDrawingRefsInMarkdown(params.content, refToReal)
  await editExtraction(params.materialId, content)
  if (params.description !== undefined) {
    await setMaterialDescription(params.materialId, params.description)
  }
  return { materialId: params.materialId, content, refToReal, jobId: null }
}

export async function reingestMaterial(
  materialId: string,
  options?: { mode: components['schemas']['ExtractionMode'] },
): Promise<UploadResult> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/reingest`, {
    method: 'POST',
    headers: options ? { 'Content-Type': 'application/json' } : undefined,
    body: options ? JSON.stringify(options) : undefined,
  })
  if (!response.ok) {
    throw new Error(`re-ingest failed (${response.status})`)
  }
  return json<UploadResult>(response)
}

async function commitNewDrawings(
  materialId: string,
  drawings: PendingDrawing[]
): Promise<Record<number, string>> {
  const known = new Set<string>()
  const refToReal: Record<number, string> = {}
  for (const pending of drawings) {
    if (typeof pending.ref !== 'number' || pending.ref > 0) {
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

export async function renameMaterial(id: string, title: string): Promise<Material> {
  const response = await apiFetch(`/api/v1/materials/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return json<Material>(response)
}

export async function setMaterialDescription(
  id: string,
  description: string | null
): Promise<Material> {
  const response = await apiFetch(`/api/v1/materials/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
  })
  return json<Material>(response)
}

export async function moveMaterial(
  id: string,
  folderId: string | null
): Promise<Material> {
  const response = await apiFetch(`/api/v1/materials/${id}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId }),
  })
  return json<Material>(response)
}

export async function copyMaterial(
  id: string,
  folderId: string | null
): Promise<Material> {
  const response = await apiFetch(`/api/v1/materials/${id}/copy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId }),
  })
  return json<Material>(response)
}

export async function deriveMaterial(
  id: string,
  options?: { folderId?: string | null; nodeId?: string | null }
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

export type DeriveBatchResult = Schemas['MaterialBatchDeriveOut']

export async function deriveMaterials(ids: string[]): Promise<DeriveBatchResult> {
  const response = await apiFetch('/api/v1/materials/derive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ material_ids: ids }),
  })
  return json<DeriveBatchResult>(response)
}

export async function deleteMaterial(id: string): Promise<{ deleted_item_id: string }> {
  const response = await apiFetch(`/api/v1/materials/${id}`, { method: 'DELETE' })
  return json<{ deleted_item_id: string }>(response)
}

export async function getMaterial(id: string): Promise<MaterialDetail> {
  const response = await apiFetch(`/api/v1/materials/${id}`)
  return json<MaterialDetail>(response)
}

export async function search(
  query: string,
  courseId?: string
): Promise<{ query: string; hits: SearchHitDto[] }> {
  const course = courseId !== undefined ? `&course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/search?q=${encodeURIComponent(query)}${course}`)
  return json<{ query: string; hits: SearchHitDto[] }>(response)
}

export async function editExtraction(
  materialId: string,
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
  materialId: string
): Promise<ExtractionVersionInfo[]> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/extractions`)
  return json<ExtractionVersionInfo[]>(response)
}

export async function getExtractionVersion(
  materialId: string,
  version: number
): Promise<Extraction> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/extractions/${version}`)
  return json<Extraction>(response)
}

export async function mindmapEdit(
  materialId: string,
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
  id: string
  name: string
  direct: boolean
  node_ids: string[]
}

export interface CourseMaterialLink {
  node_id: string
  node_title: string
  node_is_root: boolean
  material_id: string
  title: string
  rationale: string | null
  auto_assigned: boolean
  confidence: number | null
}

export async function listCourseMaterials(courseId: string): Promise<CourseMaterialLink[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/materials`)
  return json<CourseMaterialLink[]>(response)
}

export async function assignCourseMaterial(
  courseId: string,
  materialId: string
): Promise<void> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/materials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ material_id: materialId }),
  })
  await json<unknown>(response)
}

export async function unassignCourseMaterial(
  courseId: string,
  materialId: string
): Promise<void> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/materials/${materialId}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export async function allocateMaterial(
  nodeId: string,
  materialId: string
): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/materials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ material_id: materialId }),
  })
  await json<unknown>(response)
}

export async function deallocateMaterial(
  nodeId: string,
  materialId: string
): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/materials/${materialId}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export async function allocateNodeFolder(
  nodeId: string,
  folderId: string,
  rationale?: string
): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/folder-materials`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId, rationale }),
  })
  await json<unknown>(response)
}

export interface MirrorFolderResult {
  created_nodes: number
  reused_nodes: number
  folder_links: number
  skipped_folders: string[]
}

export async function mirrorFolder(
  nodeId: string,
  folderId: string,
  recursive = true
): Promise<MirrorFolderResult> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/mirror-folder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder_id: folderId, recursive }),
  })
  return json<MirrorFolderResult>(response)
}

export async function deallocateNodeFolder(
  nodeId: string,
  folderId: string
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
  'lesson',
] as const

export type ComposeKind = (typeof COMPOSE_KINDS)[number]

export interface ComposedMaterial {
  material: Material
  job_id: string | null
  deduped: boolean
}

export async function composeMaterial(body: {
  course_id: string
  node_id?: string | null
  kind: ComposeKind
  title?: string | null
  instructions?: string | null
  extra_md?: string | null
  scope?: string
  include_material_ids?: string[]
  exclude_material_ids?: string[]
  note_ids?: string[]
  concept_ids?: string[]
  context_hint?: string | null
  regenerate?: boolean
  include_unassigned?: boolean
}): Promise<ComposedMaterial> {
  const response = await apiFetch('/api/v1/materials/compose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ComposedMaterial>(response)
}

export async function composeMaterialAsync(body: Parameters<typeof composeMaterial>[0]): Promise<{ job_id: string }> {  const response = await apiFetch('/api/v1/materials/compose/async', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<{ job_id: string }>(response)
}

export interface LinkMaterialBody {
  course_id: string
  url: string
  title?: string | null
  node_id?: string | null
  folder_id?: string | null
}

export async function createLinkMaterial(
  body: LinkMaterialBody,
): Promise<ComposedMaterial> {
  const response = await apiFetch('/api/v1/materials/link', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ComposedMaterial>(response)
}

export async function parseLinkMaterial(materialId: string): Promise<{ job_id: string }> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/parse`, {
    method: 'POST',
  })
  return json<{ job_id: string }>(response)
}

export async function transcribeLinkAudio(
  materialId: string,
): Promise<{ job_id: string }> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/transcribe-audio`, {
    method: 'POST',
  })
  return json<{ job_id: string }>(response)
}

export async function addMaterialDrawing(
  materialId: string,
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
  materialId: string,
  drawingId: string,
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
  materialId: string,
  drawingId: string
): Promise<MaterialDetail> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/drawings/${drawingId}/reocr`, {
    method: 'POST',
  })
  return json<MaterialDetail>(response)
}

export async function deleteMaterialDrawing(
  materialId: string,
  drawingId: string
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

export interface ExtractionDiffInfo {
  base: string
  target: string
  additions: number
  deletions: number
  diff: string
}

export async function diffExtractionVersions(
  materialId: string,
  from: string,
  to: string
): Promise<ExtractionDiffInfo> {
  const response = await apiFetch(
    `/api/v1/materials/${materialId}/extractions/diff?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`
  )
  return json<ExtractionDiffInfo>(response)
}

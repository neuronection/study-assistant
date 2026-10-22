import type { components } from '@/lib/api-schema'
import { ApiError, json, expectOk, apiFetch } from './client'
import type { BlockDto, PendingDrawing, TextFileEditState } from './hand-types'

type Schemas = components['schemas']

export type AcceptedTypes = Schemas['AcceptedTypesOut']
export type Material = Schemas['MaterialOut']
export type Extraction = Omit<Schemas['ExtractionOut'], 'blocks'> & { blocks: BlockDto[] }
export type IndexCard = Schemas['IndexCardOut']
export type MaterialImageInfo = Schemas['MaterialImageOut']
export type MaterialDetail = Omit<
  Schemas['MaterialDetailOut'],
  'drawings' | 'images'
> & {
  drawings: Schemas['DrawingOut'][]
  images: Schemas['MaterialImageOut'][]
}
export type UploadWarning = Schemas['UploadWarningOut']
export type UploadResult = Schemas['MaterialUploadOut']
export type SearchHitNodeDto = Schemas['SearchHitNode']
export type SearchHitDto = Schemas['SearchHit']
export type MaterialLinkInfo = Schemas['MaterialLinkInfoOut']
export type UnassignedMaterial = Schemas['UnassignedMaterialOut']
export type UnassignedMaterials = Schemas['UnassignedOut']
export type PlacementCandidate = Schemas['PlacementCandidateOut']
export type PlacementSuggestion = Schemas['PlacementSuggestionOut']
export type MindmapEditResult = Schemas['MindmapEditOut']
export type ExtractionVersionInfo = Schemas['ExtractionVersionOut']
export type WorkspaceConcept = Schemas['WorkspaceConceptOut']
export type CourseMaterialLink = Schemas['CourseMaterialsEntryOut']
export type MirrorFolderResult = Schemas['MirrorFolderOut']
export type ComposedMaterial = Schemas['MaterialUploadOut']
export type LinkMaterialBody = Schemas['LinkIn']
export type ExtractionDiffInfo = Schemas['ExtractionDiffOut']
export type { BlockDto, PendingDrawing, TextFileEditState } from './hand-types'


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

export async function getMaterialLinks(materialId: string): Promise<MaterialLinkInfo[]> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/links`)
  return json<MaterialLinkInfo[]>(response)
}

export async function getUnassignedMaterials(courseId: string): Promise<UnassignedMaterials> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/materials/unassigned`)
  return json<UnassignedMaterials>(response)
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

export async function importBibliography(
  courseId: string,
  file: File,
  nodeId?: string | null
): Promise<Schemas['BibliographyImportOut']> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ course_id: courseId })
  if (nodeId) params.set('node_id', nodeId)
  const response = await apiFetch(`/api/v1/materials/import-bibliography?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
  return json<Schemas['BibliographyImportOut']>(response)
}

export async function downloadBibliography(materialIds: string[]): Promise<void> {
  const params = new URLSearchParams()
  for (const id of materialIds) params.append('ids', id)
  const response = await apiFetch(`/api/v1/materials/bibliography.bib?${params.toString()}`)
  if (!response.ok) {
    throw new Error(`export failed: ${response.status}`)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'citations.bib'
  anchor.click()
  URL.revokeObjectURL(url)
}

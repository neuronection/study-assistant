export interface Health {
  status: string
  version: string
  db: string
}

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

export async function getHealth(fetchFn: typeof fetch = fetch): Promise<Health> {
  const response = await fetchFn('/api/v1/health')
  if (!response.ok) {
    throw new Error(`health check failed: ${response.status}`)
  }
  return (await response.json()) as Health
}

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export function apiDetailMessage(detail: unknown): string | null {
  if (typeof detail === 'string') {
    return detail.trim() ? detail : null
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((entry) => {
        if (entry === null || typeof entry !== 'object') {
          return String(entry)
        }
        const record = entry as { loc?: unknown; msg?: unknown }
        const loc = Array.isArray(record.loc)
          ? record.loc.filter((part) => part !== 'body').join('.')
          : ''
        const msg =
          typeof record.msg === 'string' ? record.msg : String(record.msg ?? '')
        return loc ? `${loc}: ${msg}` : msg
      })
      .filter((part) => part.length > 0)
    return parts.length > 0 ? parts.join('; ') : null
  }
  if (detail !== null && detail !== undefined) {
    return String(detail)
  }
  return null
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
    throw new ApiError(
      apiDetailMessage(body?.detail) ?? `request failed: ${response.status}`,
      response.status,
    )
  }
  return (await response.json()) as T
}

async function expectOk(response: Response): Promise<void> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
    throw new ApiError(
      apiDetailMessage(body?.detail) ?? `request failed: ${response.status}`,
      response.status,
    )
  }
}

let activeProfileId: number | null = null

export function setActiveProfile(profileId: number | null): void {
  activeProfileId = profileId
}

export function getActiveProfile(): number | null {
  return activeProfileId
}

export function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  if (activeProfileId !== null) {
    headers.set('X-Profile-Id', String(activeProfileId))
  }
  return fetch(url, { ...init, headers })
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

export interface FsDirEntry {
  name: string
  path: string
}

export interface FsDirs {
  path: string
  parent: string | null
  home: string
  dirs: FsDirEntry[]
}

export async function listFsDirs(path?: string): Promise<FsDirs> {
  const params = path !== undefined ? `?path=${encodeURIComponent(path)}` : ''
  const response = await apiFetch(`/api/v1/fs/dirs${params}`)
  return json<FsDirs>(response)
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

export interface Folder {
  id: number
  name: string
  path: string
  course_id: number
  parent_id: number | null
  source_id: number | null
  created_at: string
}

export async function listFolders(courseId?: number): Promise<Folder[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/folders${params}`)
  return json<Folder[]>(response)
}

export async function createFolder(
  name: string,
  parentId: number | null,
  courseId: number
): Promise<Folder> {
  const response = await apiFetch('/api/v1/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, parent_id: parentId, course_id: courseId }),
  })
  return json<Folder>(response)
}

export async function renameFolder(id: number, name: string): Promise<Folder> {
  const response = await apiFetch(`/api/v1/folders/${id}/rename`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return json<Folder>(response)
}

export async function moveFolder(
  id: number,
  parentId: number | null
): Promise<Folder> {
  const response = await apiFetch(`/api/v1/folders/${id}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent_id: parentId }),
  })
  return json<Folder>(response)
}

export interface FolderDeleteInfoNodeLink {
  node_id: number
  owner_title: string
  breadcrumb: { id: number; title: string }[]
  is_course_level: boolean
  course_title: string
  folder_count: number
  material_count: number
}

export interface FolderDeleteInfo {
  subfolders: number
  materials: number
  node_links: FolderDeleteInfoNodeLink[]
}

export async function getFolderDeleteInfo(id: number): Promise<FolderDeleteInfo> {
  const response = await apiFetch(`/api/v1/folders/${id}/delete-info`)
  return json<FolderDeleteInfo>(response)
}

export async function unlinkFolder(id: number): Promise<void> {
  const response = await apiFetch(`/api/v1/folders/${id}/unlink`, { method: 'POST' })
  await expectOk(response)
}

export async function deleteFolder(id: number, force = false): Promise<void> {
  const suffix = force ? '?force=true' : ''
  const response = await apiFetch(`/api/v1/folders/${id}${suffix}`, { method: 'DELETE' })
  await expectOk(response)
}

export interface Provider {
  id: number
  name: string
  type: string
  base_url: string
  enabled: boolean
  masked_key: string | null
  status: { last_tested_at?: string; ok?: boolean; error?: string | null; model_count?: number | null } | null
  created_at: string
}

export interface ProviderPreset {
  name: string
  type: string
  base_url: string
}

export async function listProviders(): Promise<Provider[]> {
  const response = await apiFetch('/api/v1/providers')
  return json<Provider[]>(response)
}

export async function listPresets(): Promise<Record<string, ProviderPreset>> {
  const response = await apiFetch('/api/v1/providers/presets')
  return json<Record<string, ProviderPreset>>(response)
}

export async function createProvider(body: {
  name: string
  type: string
  base_url?: string | null
  api_key?: string | null
}): Promise<Provider> {
  const response = await apiFetch('/api/v1/providers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<Provider>(response)
}

export async function testProvider(id: number): Promise<Provider> {
  const response = await apiFetch(`/api/v1/providers/${id}/test`, { method: 'POST' })
  return json<Provider>(response)
}

export async function updateProvider(
  id: number,
  body: {
    name?: string
    base_url?: string | null
    enabled?: boolean
    api_key?: string | null
  }
): Promise<Provider> {
  const response = await apiFetch(`/api/v1/providers/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<Provider>(response)
}

export async function deleteProvider(id: number): Promise<void> {
  const response = await apiFetch(`/api/v1/providers/${id}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export interface AiModel {
  id: number
  provider_id: number
  external_id: string
  label: string
  caps: string[]
  enabled: boolean
  missing: boolean
  reasoning_effort: string | null
}

export async function listModels(): Promise<AiModel[]> {
  const response = await apiFetch('/api/v1/models')
  return json<AiModel[]>(response)
}

export async function discoverModels(providerId: number): Promise<AiModel[]> {
  const response = await apiFetch(`/api/v1/providers/${providerId}/models`, { method: 'POST' })
  return json<AiModel[]>(response)
}

export interface RemoteModelInfo {
  external_id: string
  caps: string[]
}

export async function listRemoteModels(providerId: number): Promise<RemoteModelInfo[]> {
  const response = await apiFetch(`/api/v1/providers/${providerId}/remote-models`)
  return json<RemoteModelInfo[]>(response)
}

export async function createModel(body: {
  provider_id: number
  external_id: string
  label?: string | null
  caps?: string[] | null
  enabled?: boolean
  reasoning_effort?: string | null
}): Promise<AiModel> {
  const response = await apiFetch('/api/v1/models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<AiModel>(response)
}

export async function updateModel(
  id: number,
  body: { enabled?: boolean; label?: string; caps?: string[]; reasoning_effort?: string | null }
): Promise<AiModel> {
  const response = await apiFetch(`/api/v1/models/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<AiModel>(response)
}

export async function deleteModel(id: number): Promise<void> {
  const response = await apiFetch(`/api/v1/models/${id}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export interface TaskInfo {
  task: string
  description: string
  requires: string
  model_id: number | null
  fallback_model_id: number | null
  model_label: string | null
  fallback_model_label: string | null
  inherits_default: boolean
  default_model_label: string | null
  default_fallback_model_label: string | null
  monthly_cap_usd?: number | null
}

export interface DefaultTaskInfo {
  requires: string
  model_id: number | null
  fallback_model_id: number | null
  model_label: string | null
  fallback_model_label: string | null
}

export async function listTasks(): Promise<TaskInfo[]> {
  const response = await apiFetch('/api/v1/tasks')
  return json<TaskInfo[]>(response)
}

export async function assignTask(
  task: string,
  modelId: number | null,
  fallbackModelId: number | null = null
): Promise<TaskInfo> {
  const response = await apiFetch(`/api/v1/tasks/${task}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, fallback_model_id: fallbackModelId }),
  })
  return json<TaskInfo>(response)
}

export async function listTaskDefaults(): Promise<DefaultTaskInfo[]> {
  const response = await apiFetch('/api/v1/tasks/defaults')
  return json<DefaultTaskInfo[]>(response)
}

export async function assignTaskDefault(
  requires: string,
  modelId: number | null,
  fallbackModelId: number | null = null
): Promise<DefaultTaskInfo> {
  const response = await apiFetch(`/api/v1/tasks/defaults/${requires}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, fallback_model_id: fallbackModelId }),
  })
  return json<DefaultTaskInfo>(response)
}

export interface CourseTaskInfo {
  task: string
  description: string
  requires: string
  model_id: number | null
  fallback_model_id: number | null
  model_label: string | null
  fallback_model_label: string | null
  global_model_label: string | null
  global_fallback_model_label: string | null
}

export interface CourseDefaultTaskInfo {
  requires: string
  model_id: number | null
  fallback_model_id: number | null
  model_label: string | null
  fallback_model_label: string | null
  global_model_label: string | null
  global_fallback_model_label: string | null
}

export async function listCourseTasks(courseId: number): Promise<CourseTaskInfo[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/tasks`)
  return json<CourseTaskInfo[]>(response)
}

export async function assignCourseTask(
  courseId: number,
  task: string,
  modelId: number | null,
  fallbackModelId: number | null = null
): Promise<CourseTaskInfo> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/tasks/${task}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, fallback_model_id: fallbackModelId }),
  })
  return json<CourseTaskInfo>(response)
}

export async function listCourseTaskDefaults(
  courseId: number
): Promise<CourseDefaultTaskInfo[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/tasks/defaults`)
  return json<CourseDefaultTaskInfo[]>(response)
}

export async function assignCourseTaskDefault(
  courseId: number,
  requires: string,
  modelId: number | null,
  fallbackModelId: number | null = null
): Promise<CourseDefaultTaskInfo> {
  const response = await apiFetch(
    `/api/v1/courses/${courseId}/tasks/defaults/${requires}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId, fallback_model_id: fallbackModelId }),
    }
  )
  return json<CourseDefaultTaskInfo>(response)
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

export function blobUrl(sha: string): string {
  return `/api/v1/blobs/${sha}`
}

export interface Course {
  id: number
  title: string
  subject: string | null
  level: string | null
  description: string | null
  color: string | null
  archived_at: string | null
  exam_date?: string | null
  material_count: number
}

export async function listCourses(): Promise<Course[]> {
  const response = await apiFetch('/api/v1/courses')
  return json<Course[]>(response)
}

export async function createCourse(body: {
  title: string
  subject?: string | null;
  level?: string | null;
  description?: string | null;
}): Promise<Course> {
  const response = await apiFetch('/api/v1/courses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<Course>(response)
}

export async function deleteCourse(id: number, confirmedBackup: boolean): Promise<void> {
  const response = await apiFetch(
    `/api/v1/courses/${id}?confirmed_backup=${confirmedBackup}`,
    { method: 'DELETE' }
  )
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export function courseExportUrl(courseId: number): string {
  return `/api/v1/courses/${courseId}/export`
}

export interface CourseBundlePreview {
  title: string | null
  counts: Record<string, number>
  warnings: string[]
}

export async function importCourseBundle(
  file: File,
  dryRun: boolean
): Promise<
  | { dry_run: true; preview: CourseBundlePreview }
  | { dry_run: false; imported: { course_id: number; title: string } }
> {
  const response = await apiFetch(
    `/api/v1/courses/import?dry_run=${dryRun}`,
    { method: 'POST', body: file }
  )
  return json(response)
}

export interface DeletedItemInfo {
  id: number
  entity_type: string
  title: string
  deleted_at: string
  purge_after: string
}

export async function listDeletedItems(): Promise<DeletedItemInfo[]> {
  const response = await apiFetch('/api/v1/deleted-items')
  return json<DeletedItemInfo[]>(response)
}

export async function restoreDeletedItem(
  id: number
): Promise<{ status: string; entity_type: string; title: string }> {
  const response = await apiFetch(`/api/v1/deleted-items/${id}/restore`, {
    method: 'POST',
  })
  return json<{ status: string; entity_type: string; title: string }>(response)
}

export async function purgeDeletedItem(id: number): Promise<void> {
  const response = await apiFetch(`/api/v1/deleted-items/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export interface AllocationInfo {
  material_id: number
  title: string
  rationale: string | null
  auto_assigned: boolean
  confidence: number | null
}

export interface NodeCounts {
  materials: number
  notes: number
  quizzes: number
  exercises: number
  flashcards: number
  studied?: number
  cards_due?: number
}

export interface NodeFolderLink {
  folder_id: number
  name: string
  source_id: number | null
}

export interface NodeInfo {
  id: number
  title: string
  summary: string | null
  objectives: string[]
  ai_hint?: string | null
  order_idx: number
  depth: number
  is_root: boolean
  children: NodeInfo[]
  counts?: NodeCounts
  materials: AllocationInfo[]
  folder_links?: NodeFolderLink[]
}

export async function courseTree(courseId: number): Promise<NodeInfo[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/tree`)
  return json<NodeInfo[]>(response)
}

export interface NodeDetail {
  id: number
  course_id: number
  parent_id: number | null
  title: string
  summary: string | null
  objectives: string[]
  depth: number
  is_root: boolean
  order_idx: number
}

export async function getNode(nodeId: number): Promise<NodeDetail> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}`)
  return json<NodeDetail>(response)
}

export async function addNode(
  courseId: number,
  parentId: number,
  title: string
): Promise<{ id: number; title: string; order_idx: number; depth: number }> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/nodes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, parent_id: parentId, title }),
  })
  return json<{ id: number; title: string; order_idx: number; depth: number }>(response)
}

export async function renameNode(id: number, title: string): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  await json<unknown>(response)
}

export async function updateNode(
  id: number,
  body: { title?: string; summary?: string; ai_hint?: string }
): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  await json<unknown>(response)
}

export async function updateCourse(
  id: number,
  body: {
    title?: string
    subject?: string
    level?: string
    description?: string
    color?: string
    exam_date?: string | null
  }
): Promise<void> {
  const response = await apiFetch(`/api/v1/courses/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  await json<unknown>(response)
}

export async function moveNode(
  id: number,
  parentId: number,
  position: number
): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${id}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent_id: parentId, position }),
  })
  await json<unknown>(response)
}

export async function deleteNode(id: number): Promise<string | null> {
  const response = await apiFetch(`/api/v1/nodes/${id}`, { method: 'DELETE' })
  return json<{ undo_token: string | null }>(response).then((body) => body.undo_token)
}

export async function restoreNode(undoToken: string): Promise<{ id: number }> {
  const response = await apiFetch('/api/v1/nodes/restore', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ undo_token: undoToken }),
  })
  return json<{ id: number }>(response)
}

export interface WorkspaceMaterial {
  material_id: number
  title: string
  kind: string
  status: string
  read_status: string
  progress: number
  rationale: string | null
  auto_assigned: boolean | null
  confidence: number | null
  provenance?: { source?: string } | null
  via_folder_id: number | null
  via_folder_name: string | null
}

export interface WorkspaceFolder {
  folder_id: number
  name: string
  source_id: number | null
  member_count: number
  rationale: string | null
  auto_assigned: boolean
}

export interface WorkspaceChild {
  id: number
  title: string
  depth: number
  order_idx: number
  objectives: string[]
  summary: string | null
}

export interface WorkspaceNote {
  id: number
  title: string
  node_id: number | null
  owner_type: string
  owner_id: number | null
  pinned: boolean
  updated_at: string | null
}

export interface ScopeCounts {
  direct: number
  with_children: number
}

export interface WorkspaceConcept {
  id: number
  name: string
  direct: boolean
  node_ids: number[]
}

export interface NodeWorkspace {
  node: {
    id: number
    course_id: number
    course_title: string | null
    title: string
    summary: string | null
    objectives: string[]
    ai_hint: string | null
    depth: number
    is_root: boolean
    parent_id: number | null
    breadcrumb: { id: number; title: string; depth: number }[]
  }
  children: WorkspaceChild[]
  folders: WorkspaceFolder[]
  materials: WorkspaceMaterial[]
  folder_material_ids: number[]
  child_materials: Record<string, WorkspaceMaterial[]>
  notes: WorkspaceNote[]
  counts: {
    notes: ScopeCounts
    quizzes: ScopeCounts
    exercises: ScopeCounts
    flashcards: ScopeCounts
    child_nodes: number
  }
  concepts: WorkspaceConcept[]
}

export async function nodeWorkspace(nodeId: number): Promise<NodeWorkspace> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/workspace`)
  return json<NodeWorkspace>(response)
}

export async function addNodeConcept(
  nodeId: number,
  conceptId: number
): Promise<{ node_id: number; concept_id: number }> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/concepts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ concept_id: conceptId }),
  })
  return json<{ node_id: number; concept_id: number }>(response)
}

export async function removeNodeConcept(
  nodeId: number,
  conceptId: number
): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/concepts/${conceptId}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export interface ConceptDraftEntry {
  name: string
  description: string | null
  aliases: string[]
}

export interface ConceptLinkDraft {
  from: string
  to: string
  relation: 'prereq-of' | 'part-of' | 'related-to'
}

export interface ConceptNodeDraft {
  node_title: string
  concepts: string[]
}

export interface ConceptDraft {
  concepts: ConceptDraftEntry[]
  links: ConceptLinkDraft[]
  nodes: ConceptNodeDraft[]
}

export interface ConceptNode {
  id: number
  name: string
  description: string | null
  aliases: string[]
  nodes: { node_id: number; node_title: string }[]
}

export interface ConceptGraph {
  concepts: ConceptNode[]
  links: { from: string; to: string; relation: string }[]
}

export async function extractConcepts(courseId: number): Promise<ConceptDraft> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/concepts/extract`, {
    method: 'POST',
  })
  return json<ConceptDraft>(response)
}

export async function commitConcepts(
  courseId: number,
  draft: ConceptDraft
): Promise<{ concepts: number; created: number; links: number; nodes: number }> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/concepts/commit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draft),
  })
  return json<{ concepts: number; created: number; links: number; nodes: number }>(
    response
  )
}

export async function conceptGraph(courseId: number): Promise<ConceptGraph> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/concepts`)
  return json<ConceptGraph>(response)
}

export interface OrganizerFinding {
  kind: 'gap' | 'ordering' | 'orphan' | 'coverage'
  title: string
  detail: string | null
  suggestion: string | null
}

export interface NodeReview {
  node_id: number
  node_title: string
  findings: OrganizerFinding[]
  material_id: number
}

export async function reviewNode(nodeId: number): Promise<NodeReview> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/review`, {
    method: 'POST',
  })
  return json<NodeReview>(response)
}

export interface NodeArtifacts {
  cheat_sheet: { material_id: number; title: string } | null
  reviews: { material_id: number; title: string }[]
  artifact?: { material_id: number; title: string } | null
}

export async function getNodeArtifacts(
  nodeId: number,
  kind?: string
): Promise<NodeArtifacts> {
  const suffix = kind ? `?kind=${encodeURIComponent(kind)}` : ''
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/artifacts${suffix}`)
  return json<NodeArtifacts>(response)
}

export async function draftNodeNote(
  nodeId: number
): Promise<{ note_id: number; markdown: string; existing: boolean }> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/draft-note`, {
    method: 'POST',
  })
  return json<{ note_id: number; markdown: string; existing: boolean }>(response)
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

export interface OutlineDraftSection {
  title: string
  objectives: string[]
  material_ids: number[]
  rationale: string | null
  confidence: number
}

export interface OutlineDraftChapter {
  title: string
  summary: string | null
  sections: OutlineDraftSection[]
}

export interface OutlineDraft {
  chapters: OutlineDraftChapter[]
}

export async function outlineDraft(courseId: number): Promise<OutlineDraft> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/outline/draft`, {
    method: 'POST',
  })
  return json<OutlineDraft>(response)
}

export async function outlineCommit(
  courseId: number,
  chapters: OutlineDraftChapter[]
): Promise<{ chapters: number; sections: number; allocations: number }> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/outline/commit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chapters }),
  })
  return json<{ chapters: number; sections: number; allocations: number }>(response)
}

export async function setStudyState(
  materialId: number,
  status: 'unread' | 'reading' | 'studied',
  progress?: number
): Promise<{ status: string; progress: number }> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/study-state`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, progress }),
  })
  return json<{ status: string; progress: number }>(response)
}

export async function listStudyStates(): Promise<Record<string, { status: string; progress: number }>> {
  const response = await apiFetch('/api/v1/study-states')
  return json<Record<string, { status: string; progress: number }>>(response)
}

export interface ChatSession {
  id: number
  public_id: string
  course_id: number | null
  node_id: number | null
  title: string
  use_embeddings: boolean | null
  created_at: string
}

export interface ChatCitation {
  index: number
  chunk_id: number
  material_id: number
  title: string
  quote: string
}

export type MentionKind = 'material' | 'note' | 'concept' | 'node' | 'quiz' | 'exercise'

export interface MentionRef {
  ref: string
  kind: MentionKind
  id: number
  title: string
  course_id?: number | null
  summary?: string | null
}

export interface ChatRead {
  ref: string
  kind: MentionKind
  id: number
  title: string
  course_id?: number | null
  chars: number
}

export interface ChatToolCall {
  name: string
  argument: string
  phase?: string | null
  result?: string | null
  title?: string | null
  status?: string | null
  start_ms?: number | null
  duration_ms?: number | null
}

export interface ChatTraceRound {
  index: number
  streamed: boolean
  start_ms: number
  duration_ms: number
  phase: string
}

export interface ChatTrace {
  run_id: string
  model: string | null
  latency_ms: number
  input_tokens: number | null
  output_tokens: number | null
  repair_rounds: number
  rounds: ChatTraceRound[]
  thinking?: string
}

export interface ChatContextData {
  session_id: number
  course_id: number | null
  node: { id: number; title: string } | null
  registry: MentionRef[]
  latest_notes: { id: number; title: string }[]
}

export interface ChatProposal {
  id: number
  action: string
  payload: Record<string, unknown>
  status: 'proposed' | 'approved' | 'dismissed' | 'executed' | 'stale'
  result?:
    | { note_id?: number; open_dialog?: Record<string, unknown>; error?: string }
    | null
}

export interface ChatMessage {
  id: number
  role: string
  markdown: string
  blocks?: BlockDto[]
  citations: ChatCitation[]
  mentions: MentionRef[]
  reads: ChatRead[]
  tool_calls: ChatToolCall[]
  proposals: ChatProposal[]
  grounded: boolean | null
  trace?: ChatTrace | null
  warnings?: string[]
  parent_id?: number | null
  variant_index?: number
  variant_count?: number
  sibling_ids?: number[]
}

export async function listChatSessions(nodeId?: number): Promise<ChatSession[]> {
  const params = nodeId !== undefined ? `?node_id=${nodeId}` : ''
  const response = await apiFetch(`/api/v1/chat/sessions${params}`)
  return json<ChatSession[]>(response)
}

export async function renameChatSession(sessionId: number, title: string): Promise<ChatSession> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return json<ChatSession>(response)
}

export async function updateChatSessionEmbeddings(
  sessionId: number,
  useEmbeddings: boolean
): Promise<ChatSession> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ use_embeddings: useEmbeddings }),
  })
  return json<ChatSession>(response)
}

export async function deleteChatSession(
  sessionId: number
): Promise<{ deleted_item_id: number }> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: 'DELETE',
  })
  return json<{ deleted_item_id: number }>(response)
}

export async function createChatSession(
  courseId: number | null,
  nodeId?: number | null,
  title?: string
): Promise<ChatSession> {
  const response = await apiFetch('/api/v1/chat/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      course_id: courseId,
      node_id: nodeId ?? null,
      ...(title !== undefined ? { title } : {}),
    }),
  })
  return json<ChatSession>(response)
}

export async function listChatMessages(sessionId: number): Promise<ChatMessage[]> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/messages`)
  const messages = await json<ChatMessage[]>(response)
  return messages.map((message) => ({
    ...message,
    mentions: message.mentions ?? [],
    reads: message.reads ?? [],
    tool_calls: message.tool_calls ?? [],
    proposals: message.proposals ?? [],
  }))
}

export async function getChatContext(sessionId: number): Promise<ChatContextData> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/context`)
  return json<ChatContextData>(response)
}

export async function editChatMessage(
  messageId: number,
  content: string,
): Promise<{ user_message: ChatMessage; job_id: number }> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  return json<{ user_message: ChatMessage; job_id: number }>(response)
}

export async function regenerateChatMessage(
  messageId: number,
): Promise<{ user_message: ChatMessage; job_id: number }> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/regenerate`, {
    method: 'POST',
  })
  return json<{ user_message: ChatMessage; job_id: number }>(response)
}

export async function selectChatVariant(messageId: number): Promise<ChatMessage[]> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/select`, {
    method: 'POST',
  })
  return json<ChatMessage[]>(response)
}

export async function stopChatTurn(sessionId: number): Promise<{ stopped: boolean }> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/stop`, {
    method: 'POST',
  })
  return json<{ stopped: boolean }>(response)
}

export interface ChatBranchNode {
  id: number
  role: string
  excerpt: string
  parent_id: number | null
  children: number[]
  active_child_id: number | null
}

export interface ChatBranchTree {
  active_root_id: number | null
  nodes: ChatBranchNode[]
}

export async function getChatBranchTree(sessionId: number): Promise<ChatBranchTree> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/tree`)
  return json<ChatBranchTree>(response)
}

export async function approveChatProposal(proposalId: number): Promise<ChatProposal> {  const response = await apiFetch(`/api/v1/chat/proposals/${proposalId}/approve`, {
    method: 'POST',
  })
  return json<ChatProposal>(response)
}

export async function dismissChatProposal(proposalId: number): Promise<ChatProposal> {
  const response = await apiFetch(`/api/v1/chat/proposals/${proposalId}/dismiss`, {
    method: 'POST',
  })
  return json<ChatProposal>(response)
}

export type ChatAttachmentKind =
  | 'material'
  | 'note'
  | 'quiz'
  | 'exercise'
  | 'node'
  | 'course'

export interface ChatAttachmentInput {
  kind: ChatAttachmentKind
  id: number
}

export async function sendChatMessage(
  sessionId: number,
  content: string,
  attachments?: ChatAttachmentInput[]
): Promise<{ user_message: ChatMessage; job_id: number }> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content,
      ...(attachments !== undefined && attachments.length > 0 ? { attachments } : {}),
    }),
  })
  return json<{ user_message: ChatMessage; job_id: number }>(response)
}

export async function patchChatMessageState(
  messageId: number,
  delta: { op: 'add' | 'replace' | 'remove'; path: string; value?: unknown }[],
): Promise<{ state: Record<string, unknown> }> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/state`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ delta }),
  })
  return json<{ state: Record<string, unknown> }>(response)
}

export interface QuizQuestion {
  id: number
  type: string
  stem: BlockDto[]
  options: BlockDto[] | null
  difficulty: number | null
  bloom: string | null
  skill: string | null
  expected_time_sec: number | null
  flag: string
}

export interface QuizActivity {
  id: number
  title: string
  type: string
  course_id: number | null
  node_id: number | null
  question_count: number
}

export type GenerateScope = 'node' | 'subtree' | 'course'

export interface GenerateContext {
  scope?: GenerateScope
  include_material_ids?: number[]
  exclude_material_ids?: number[]
  note_ids?: number[]
  concept_ids?: number[]
  context_hint?: string | null
}

export interface AiContextPreview {
  stats: {
    materials: { id: number; title: string }[]
    chunks: { material_id: number; title: string }[]
    notes: { id: number; title: string }[]
    concepts: { id: number; name: string }[]
    hints: number
    approx_chars: number
    retrieval_query: string | null
  }
  rendered: string
}

export async function previewAiContext(
  courseId: number,
  spec: GenerateContext & { node_id?: number | null; query?: string | null }
): Promise<AiContextPreview> {
  const response = await apiFetch('/api/v1/ai/context/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, ...spec }),
  })
  return json<AiContextPreview>(response)
}

export interface AiToolArgument {
  name: string
  type: string
  required: boolean
  description: string | null
}

export interface AiToolInfo {
  name: string
  description: string
  example: string | null
  arguments: AiToolArgument[]
  response: string
  scope: string
}

export interface McpToolInfo {
  name: string
  description: string
  arguments: AiToolArgument[]
}

export interface McpInfo {
  command: string
  instructions: string
  tools: McpToolInfo[]
}

export async function listAiTools(): Promise<AiToolInfo[]> {
  const response = await apiFetch('/api/v1/ai/tools')
  const body = await json<{ tools: AiToolInfo[] }>(response)
  return body.tools
}

export async function listMcpInfo(): Promise<McpInfo> {
  const response = await apiFetch('/api/v1/ai/mcp')
  return json<McpInfo>(response)
}

export async function generateQuiz(body: {
  course_id: number
  node_id?: number | null
  concept_id?: number | null
  count?: number
  difficulty?: number | null
  topic?: string | null
  skill?: string | null
  question_types?: string[]
  shuffle?: boolean
} & GenerateContext): Promise<QuizActivity> {
  const response = await apiFetch('/api/v1/quiz/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<QuizActivity>(response)
}

export function backupExportUrl(): string {
  return '/api/v1/backup/export'
}

export interface BackupSettingsInfo {
  auto: boolean
  interval_hours: number
  keep_daily: number
  keep_weekly: number
  sync_dir: string | null
}

export interface BackupEntryInfo {
  name: string
  size: number
  created_at: string
}

export interface BackupRecoveryInfo {
  at: string
  from_backup: string | null
  quarantined?: string
}

export interface BackupStatus {
  settings: BackupSettingsInfo
  backups: BackupEntryInfo[]
  last_recovery: BackupRecoveryInfo | null
}

export async function getBackupStatus(): Promise<BackupStatus> {
  const response = await apiFetch('/api/v1/backup/status')
  return json<BackupStatus>(response)
}

export async function updateBackupSettings(
  body: Partial<BackupSettingsInfo>
): Promise<{ settings: BackupSettingsInfo }> {
  const response = await apiFetch('/api/v1/backup/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<{ settings: BackupSettingsInfo }>(response)
}

export async function createBackupNow(): Promise<BackupStatus> {
  const response = await apiFetch('/api/v1/backup/create', { method: 'POST' })
  return json<BackupStatus>(response)
}

export async function deleteBackup(name: string): Promise<BackupStatus> {
  const response = await apiFetch(`/api/v1/backup/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  return json<BackupStatus>(response)
}

export async function restoreBackupByName(
  name: string
): Promise<{ status: string; materials: number }> {
  const response = await apiFetch(
    `/api/v1/backup/${encodeURIComponent(name)}/restore`,
    { method: 'POST' }
  )
  return json<{ status: string; materials: number }>(response)
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

export interface ExamStatusEntry {
  course_id: number
  course_title: string
  exam_date: string
  days_left: number
  total_nodes: number
  engaged_nodes: number
  remaining_nodes: number
  nodes_per_day: number | null
  on_track: boolean
  most_behind_node: { id: number; title: string } | null
}

export async function getExamStatus(): Promise<ExamStatusEntry[]> {
  const response = await apiFetch('/api/v1/analytics/exams')
  return json<ExamStatusEntry[]>(response)
}

export async function restoreBackup(file: File): Promise<{ status: string; materials: number }> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiFetch('/api/v1/backup/restore', { method: 'POST', body: form })
  return json<{ status: string; materials: number }>(response)
}

export async function listQuizzes(
  courseId?: number,
  nodeId?: number,
  includeChildren = true
): Promise<QuizActivity[]> {
  const params = new URLSearchParams()
  if (courseId !== undefined) {
    params.set('course_id', String(courseId))
  }
  if (nodeId !== undefined) {
    params.set('node_id', String(nodeId))
    params.set('include_children', String(includeChildren))
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/quiz/activities${suffix}`)
  return json<QuizActivity[]>(response)
}

export async function quizQuestions(activityId: number): Promise<QuizQuestion[]> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}/questions`)
  return json<QuizQuestion[]>(response)
}

export async function getQuiz(activityId: number): Promise<QuizActivity> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}`)
  return json<QuizActivity>(response)
}

export async function renameQuiz(activityId: number, title: string): Promise<QuizActivity> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return json<QuizActivity>(response)
}

export async function moveQuiz(
  activityId: number,
  nodeId: number | null
): Promise<QuizActivity> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  })
  return json<QuizActivity>(response)
}

export async function deleteQuiz(
  activityId: number
): Promise<{ deleted_item_id: number }> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}`, {
    method: 'DELETE',
  })
  return json<{ deleted_item_id: number }>(response)
}

export interface QuizAttempt {
  id: number
  activity_id: number
  mode: string
  started_at: string
  finished_at: string | null
  score: number | null
}

export async function startQuizAttempt(activityId: number, mode = 'practice'): Promise<QuizAttempt> {
  const response = await apiFetch(
    `/api/v1/quiz/activities/${activityId}/attempts?mode=${mode}`,
    { method: 'POST' }
  )
  return json<QuizAttempt>(response)
}

export interface QuizFeedback {
  correct: boolean
  partial_credit: number
  graded_by: string | null
  feedback: BlockDto[]
  error_tags: string[]
  explanation: BlockDto[]
}

export async function submitQuizAnswer(
  attemptId: number,
  questionId: number,
  response: unknown,
  timeMs?: number,
  inputMode?: string,
  strokes?: unknown[]
): Promise<QuizFeedback> {
  const apiResponse = await apiFetch(`/api/v1/quiz/attempts/${attemptId}/answers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question_id: questionId,
      response,
      time_ms: timeMs,
      input_mode: inputMode,
      strokes,
    }),
  })
  return json<QuizFeedback>(apiResponse)
}

export async function finishQuizAttempt(attemptId: number): Promise<QuizAttempt> {
  const response = await apiFetch(`/api/v1/quiz/attempts/${attemptId}/finish`, { method: 'POST' })
  return json<QuizAttempt>(response)
}

export interface QuizAttemptRow {
  id: number
  activity_id: number
  title: string
  mode: string
  started_at: string
  finished_at: string | null
  score: number | null
}

export async function listQuizAttempts(courseId?: number): Promise<QuizAttemptRow[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/quiz/attempts${params}`)
  return json<QuizAttemptRow[]>(response)
}

export interface MistakeRow {
  id: number
  question_id: number
  activity_id: number
  activity_title: string
  stem_excerpt: string
  error_tags: string[]
  created_at: string
}

export async function listMistakes(courseId?: number): Promise<MistakeRow[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/quiz/mistakes${params}`)
  return json<MistakeRow[]>(response)
}

export function quizExportUrl(activityId: number): string {
  return `/api/v1/quiz/activities/${activityId}/export`
}

export interface ImportValidation {
  index: number
  ok: boolean
  problems: string[]
}

export interface ImportResult {
  dry_run: boolean
  results: ImportValidation[]
  valid: number
  total: number
  activity?: QuizActivity
}

export async function importQuiz(
  document: { title?: string; questions: unknown[] },
  dryRun: boolean,
  courseId: number
): Promise<ImportResult> {
  const params = new URLSearchParams({ dry_run: String(dryRun), course_id: String(courseId) })
  const response = await apiFetch(`/api/v1/quiz/import?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(document),
  })
  return json<ImportResult>(response)
}

export interface ExerciseInfo {
  id: number
  title: string
  course_id: number | null
  node_id: number | null
  difficulty: number | null
  step_count: number
}

export interface ExerciseStepInput {
  widget: 'matching' | 'ordering' | 'categorize' | 'fill_blank' | 'math' | 'essay' | 'lines'
  kind?: string
  lefts?: string[]
  rights?: { index: number; label: string }[]
  items?: unknown[]
  categories?: string[]
  prompt_md?: string
  blank_count?: number
  lines?: string[]
}

export interface ExerciseStepInfo {
  id: number
  order_idx: number
  prompt: BlockDto[]
  has_expected: boolean
  kind: string | null
  input: ExerciseStepInput | null
}

export interface ExerciseSessionInfo {
  id: number
  exercise_id: number
  current_step_idx: number
  status: string
  socratic: boolean
  independence_score: number | null
}

export async function listExercises(
  courseId?: number,
  nodeId?: number,
  includeChildren = true
): Promise<ExerciseInfo[]> {
  const params = new URLSearchParams()
  if (courseId !== undefined) {
    params.set('course_id', String(courseId))
  }
  if (nodeId !== undefined) {
    params.set('node_id', String(nodeId))
    params.set('include_children', String(includeChildren))
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/exercises${suffix}`)
  return json<ExerciseInfo[]>(response)
}

export async function createExercise(body: {
  course_id: number
  node_id?: number | null
  title: string
  steps: { prompt_md: string; expected?: { value: string } | null }[]
}): Promise<ExerciseInfo> {
  const response = await apiFetch('/api/v1/exercises', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ExerciseInfo>(response)
}

export async function saveSessionSummaryNote(
  sessionId: number
): Promise<{ note_id: number; node_title: string | null }> {
  const response = await apiFetch(`/api/v1/exercises/sessions/${sessionId}/summary-note`, {
    method: 'POST',
  })
  return json(response)
}

export async function getExercise(exerciseId: number): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}`)
  return json<ExerciseInfo>(response)
}

export async function renameExercise(
  exerciseId: number,
  title: string
): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return json<ExerciseInfo>(response)
}

export async function moveExercise(
  exerciseId: number,
  nodeId: number | null
): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  })
  return json<ExerciseInfo>(response)
}

export async function deleteExercise(
  exerciseId: number
): Promise<{ deleted_item_id: number }> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}`, { method: 'DELETE' })
  return json<{ deleted_item_id: number }>(response)
}

export async function exerciseSteps(exerciseId: number): Promise<ExerciseStepInfo[]> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}/steps`)
  return json<ExerciseStepInfo[]>(response)
}

export async function startExerciseSession(
  exerciseId: number,
  socratic = false
): Promise<ExerciseSessionInfo> {
  const response = await apiFetch(
    `/api/v1/exercises/${exerciseId}/sessions?socratic=${socratic}`,
    { method: 'POST' }
  )
  return json<ExerciseSessionInfo>(response)
}

export interface StepCheck {
  correct: boolean
  stage: string
  error_class: string
  advanced: boolean
  session: ExerciseSessionInfo
}

export async function submitStepAnswer(
  sessionId: number,
  response: string | unknown[],
  state?: Record<string, unknown> | null,
): Promise<StepCheck> {
  const apiResponse = await apiFetch(`/api/v1/exercises/sessions/${sessionId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ response, state }),
  })
  return json<StepCheck>(apiResponse)
}

export interface HintResult {
  level: number
  markdown: string
  violations: string | null
}

export async function requestHint(
  sessionId: number,
  level: number,
  lastResponse: string | null = null
): Promise<HintResult> {
  const response = await apiFetch(`/api/v1/exercises/sessions/${sessionId}/hint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level, last_response: lastResponse }),
  })
  return json<HintResult>(response)
}

export async function askAboutExerciseSession(
  sessionId: number,
  pendingAnswer: string | null = null
): Promise<{ chat_session_id: number; public_id: string }> {
  const response = await apiFetch(`/api/v1/exercises/sessions/${sessionId}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pending_answer: pendingAnswer }),
  })
  return json<{ chat_session_id: number; public_id: string }>(response)
}

export async function generateExercise(body: {
  course_id: number
  node_id?: number | null
  topic?: string | null
  difficulty?: number | null
  step_count?: number
  kind?: string
} & GenerateContext): Promise<ExerciseInfo> {
  const response = await apiFetch('/api/v1/exercises/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ExerciseInfo>(response)
}

export async function similarExercise(exerciseId: number): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}/similar`, { method: 'POST' })
  return json<ExerciseInfo>(response)
}

export interface DrillPattern {
  pattern: string
  name: string
  description: string
  example?: string | null
  source: 'seeded' | 'discovered'
  occurrences: number
}

export interface PatternProposal {
  key: string
  name: string
  description: string
  example?: string | null
}

export async function drillPatterns(courseId: number): Promise<DrillPattern[]> {
  const response = await apiFetch(
    `/api/v1/exercises/drills/patterns?course_id=${encodeURIComponent(courseId)}`
  )
  return json<DrillPattern[]>(response)
}

export async function proposePatterns(courseId: number): Promise<PatternProposal[]> {
  const response = await apiFetch('/api/v1/exercises/drills/propose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId }),
  })
  return json<PatternProposal[]>(response)
}

export async function createPattern(
  courseId: number,
  proposal: PatternProposal
): Promise<DrillPattern> {
  const response = await apiFetch('/api/v1/exercises/drills/patterns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, ...proposal }),
  })
  return json<DrillPattern>(response)
}

export async function startDrill(pattern: string, courseId: number): Promise<ExerciseInfo> {
  const response = await apiFetch('/api/v1/exercises/drills', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern, course_id: courseId }),
  })
  return json<ExerciseInfo>(response)
}

export async function requestQuizHint(
  attemptId: number,
  questionId: number,
  level: number,
  lastResponse: unknown = null
): Promise<HintResult> {
  const response = await apiFetch(
    `/api/v1/quiz/attempts/${attemptId}/questions/${questionId}/hint`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level, last_response: lastResponse }),
    }
  )
  return json<HintResult>(response)
}

export async function askAboutQuestion(
  attemptId: number,
  questionId: number
): Promise<{ chat_session_id: number; public_id: string }> {
  const response = await apiFetch(
    `/api/v1/quiz/attempts/${attemptId}/questions/${questionId}/ask`,
    { method: 'POST' }
  )
  return json<{ chat_session_id: number; public_id: string }>(response)
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

export interface FlashcardInfo {
  id: number
  kind: string
  front: BlockDto[]
  back: BlockDto[]
  source: string
  source_ref: string | null
  node_id: number | null
  due_at: string | null
  state: string | null
}

export interface ReviewResult {
  interval_days: number
  due_at: string
  state: string
}

export async function listFlashcards(
  courseId?: number,
  nodeId?: number,
  includeChildren = true
): Promise<FlashcardInfo[]> {
  const params = new URLSearchParams()
  if (courseId !== undefined) {
    params.set('course_id', String(courseId))
  }
  if (nodeId !== undefined) {
    params.set('node_id', String(nodeId))
    params.set('include_children', String(includeChildren))
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/flashcards${suffix}`)
  return json<FlashcardInfo[]>(response)
}

export async function dueFlashcards(
  limit = 20,
  courseId?: number,
  nodeId?: number
): Promise<FlashcardInfo[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (courseId !== undefined) {
    params.set('course_id', String(courseId))
  }
  if (nodeId !== undefined) {
    params.set('node_id', String(nodeId))
    params.set('include_children', 'true')
  }
  const response = await apiFetch(`/api/v1/flashcards/due?${params.toString()}`)
  return json<FlashcardInfo[]>(response)
}

export async function reviewFlashcard(cardId: number, rating: number): Promise<ReviewResult> {
  const response = await apiFetch(`/api/v1/flashcards/${cardId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rating }),
  })
  return json<ReviewResult>(response)
}

export async function generateFlashcards(body: {
  source: string
  note_id?: number | null
  material_id?: number | null
  course_id: number
  node_id?: number | null
  count?: number
} & GenerateContext): Promise<FlashcardInfo[]> {
  const response = await apiFetch('/api/v1/flashcards/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<FlashcardInfo[]>(response)
}

export async function importAnkiDeck(
  file: File,
  courseId: number
): Promise<{ imported: number; skipped: number }> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ course_id: String(courseId) })
  const response = await apiFetch(`/api/v1/flashcards/import-anki?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
  return json<{ imported: number; skipped: number }>(response)
}

export function ankiExportUrl(courseId?: number): string {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  return `/api/v1/flashcards/export-anki${params}`
}

export interface RecognitionResult {
  markdown: string
  latex_candidates: string[]
}

export async function recognizeHandwriting(pngBase64: string): Promise<RecognitionResult> {
  const response = await apiFetch('/api/v1/quiz/recognize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ png_base64: pngBase64 }),
  })
  return json<RecognitionResult>(response)
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

export type EditorTransformMode = 'transform' | 'write'

export interface EditorTransformRequest {
  text: string
  instruction?: string
  preset?: string | null
  mode: EditorTransformMode
  include_context?: boolean
  context_document?: string
  ground_in_material?: boolean
  course_id?: number | null
  node_id?: number | null
}

export interface EditorTransformJobOut {
  job_id: number
}

export type EditorTransformJobStatus =
  | 'queued'
  | 'running'
  | 'done'
  | 'error'
  | 'cancelled'

export interface EditorTransformJobState {
  status: EditorTransformJobStatus
  result_md: string
  error: string | null
  problems: string[]
  rounds: number
}

export async function startEditorTransform(
  body: EditorTransformRequest
): Promise<EditorTransformJobOut> {
  const response = await apiFetch(`/api/v1/ai/editor/transform`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<EditorTransformJobOut>(response)
}

export async function getEditorTransformJob(
  jobId: number
): Promise<EditorTransformJobState> {
  const response = await apiFetch(`/api/v1/ai/editor/jobs/${jobId}`)
  return json<EditorTransformJobState>(response)
}

export async function cancelEditorTransformJob(jobId: number): Promise<void> {
  const response = await apiFetch(`/api/v1/ai/editor/jobs/${jobId}/cancel`, {
    method: 'POST',
  })
  await expectOk(response)
}

export interface TranscriptionResult {
  text: string
  model: string
}

function audioFilename(blob: Blob): string {
  if (blob.type.includes('mp4')) return 'dictation.m4a'
  if (blob.type.includes('ogg')) return 'dictation.ogg'
  if (blob.type.includes('wav')) return 'dictation.wav'
  return 'dictation.webm'
}

export async function transcribeAudio(
  blob: Blob,
  language?: string | null
): Promise<TranscriptionResult> {
  const form = new FormData()
  form.append('file', blob, audioFilename(blob))
  if (language) {
    form.append('language', language)
  }
  const response = await apiFetch('/api/v1/ai/transcribe', {
    method: 'POST',
    body: form,
  })
  return json<TranscriptionResult>(response)
}

export interface MatrixCell {
  concept: string
  skill: string
  n: number
  accuracy: number
  avg_time_ratio: number | null
  last_seen_at: string
  weakness_score: number
  enough_data: boolean
}

export interface ErrorTagProfile {
  tag: string
  total: number
  recent_7d: number
  previous_7d: number
  trend: number
  last_seen_at: string
}

export interface SpeedAccuracyEntry {
  concept: string
  n: number
  accuracy: number
  avg_time_ratio: number
  speed: string
  quadrant: string
}

export interface Diagnostics {
  weakness_matrix: MatrixCell[]
  error_profile: ErrorTagProfile[]
  speed_accuracy: SpeedAccuracyEntry[]
  skills: string[]
}

export async function getDiagnostics(courseId?: number): Promise<Diagnostics> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/analytics/diagnostics${params}`)
  return json<Diagnostics>(response)
}

export interface Recommendation {
  kind: 'read' | 'drill' | 'review' | 'challenge'
  priority: number
  title_key?: string
  concept: string | null
  skill: string | null
  evidence: {
    misses?: number
    n?: number
    accuracy?: number
    due_cards?: number
    last_seen_at?: string
  }
}

export async function getRecommendations(courseId?: number): Promise<Recommendation[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/analytics/recommendations${params}`)
  return json<Recommendation[]>(response)
}

export interface DailyEntry {
  day: string
  answers_n: number
  correct_n: number
  cards_reviewed: number
  minutes: number
  xp: number
}

export interface Overview {
  today: DailyEntry
  goal: number
  streak: number
  total_xp: number
  level: number
  due_cards: number
  history: DailyEntry[]
}

export async function getOverview(): Promise<Overview> {
  const response = await apiFetch('/api/v1/analytics/overview')
  return json<Overview>(response)
}

export async function setDailyGoal(answersPerDay: number): Promise<{ answers_per_day: number }> {
  const response = await apiFetch('/api/v1/analytics/goal', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers_per_day: answersPerDay }),
  })
  return json<{ answers_per_day: number }>(response)
}

export interface ProfileInfo {
  id: number
  name: string
  color: string | null
}

export interface JobInfo {
  id: number
  type: string
  status: 'queued' | 'running' | 'done' | 'failed'
  progress: number
  stage: string | null
  error: string | null
  label: string
  material_id: number | null
  retriable: boolean
  stale: boolean
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export async function listJobs(params?: {
  status?: string
  type?: string
  sort?: string
  limit?: number
}): Promise<JobInfo[]> {
  const search = new URLSearchParams()
  if (params?.status) {
    search.set('status', params.status)
  }
  if (params?.type) {
    search.set('type', params.type)
  }
  if (params?.sort) {
    search.set('sort', params.sort)
  }
  if (params?.limit) {
    search.set('limit', String(params.limit))
  }
  const query = search.toString()
  const response = await apiFetch(`/api/v1/jobs${query ? `?${query}` : ''}`)
  return json<JobInfo[]>(response)
}

export interface JobsSummary {
  queued: number
  running: number
  failed: number
  done: number
  failed_retryable: number
  failed_stale: number
}

export async function getJobsSummary(): Promise<JobsSummary> {
  const response = await apiFetch('/api/v1/jobs/summary')
  return json<JobsSummary>(response)
}

export async function retryJob(jobId: number): Promise<JobInfo> {
  const response = await apiFetch(`/api/v1/jobs/${jobId}/retry`, { method: 'POST' })
  if (!response.ok) {
    throw new Error(`retry failed (${response.status})`)
  }
  return json<JobInfo>(response)
}

export async function retryFailedJobs(types?: string[]): Promise<{ retried: number }> {
  const response = await apiFetch('/api/v1/jobs/retry-failed', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ types }),
  })
  if (!response.ok) {
    throw new Error(`bulk retry failed (${response.status})`)
  }
  return json<{ retried: number }>(response)
}

export interface JobTypeInfo {
  type: string
  label: string
}

export async function listJobTypes(): Promise<JobTypeInfo[]> {
  const response = await apiFetch('/api/v1/jobs/types')
  return json<JobTypeInfo[]>(response)
}

export async function deleteJob(jobId: number): Promise<void> {
  const response = await apiFetch(`/api/v1/jobs/${jobId}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Failed to delete job (${response.status})`)
  }
}

export async function deleteFailedJobs(
  options?: { types?: string[]; staleOnly?: boolean }
): Promise<{ deleted: number }> {
  const response = await apiFetch('/api/v1/jobs/failed', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ types: options?.types, stale_only: options?.staleOnly }),
  })
  if (!response.ok) {
    throw new Error(`bulk delete failed (${response.status})`)
  }
  return json<{ deleted: number }>(response)
}

export async function listProfiles(): Promise<ProfileInfo[]> {
  const response = await apiFetch('/api/v1/profiles')
  return json<ProfileInfo[]>(response)
}

export async function createProfile(name: string): Promise<ProfileInfo> {
  const response = await apiFetch('/api/v1/profiles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return json<ProfileInfo>(response)
}

export async function deleteProfile(profileId: number): Promise<void> {
  const response = await apiFetch(`/api/v1/profiles/${profileId}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Failed to delete profile (${response.status})`)
  }
}

export interface ProfilePreferences {
  use_embeddings: boolean
}

export async function getProfilePreferences(): Promise<ProfilePreferences> {
  const response = await apiFetch('/api/v1/profiles/preferences')
  return json<ProfilePreferences>(response)
}

export async function updateProfilePreferences(
  preferences: ProfilePreferences
): Promise<ProfilePreferences> {
  const response = await apiFetch('/api/v1/profiles/preferences', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(preferences),
  })
  return json<ProfilePreferences>(response)
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

export function qpkgExportUrl(activityId: number): string {
  return `/api/v1/quiz/activities/${activityId}/export-qpkg`
}

export async function importQpkg(
  file: File,
  dryRun: boolean,
  courseId: number
): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ dry_run: String(dryRun), course_id: String(courseId) })
  const response = await apiFetch(`/api/v1/quiz/import-qpkg?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
  return json<ImportResult>(response)
}

export interface OnboardingState {
  has_provider: boolean
  has_enabled_model: boolean
  defaults_set: string[]
  has_course: boolean
  has_material: boolean
}

export async function getOnboardingState(): Promise<OnboardingState> {
  const response = await apiFetch('/api/v1/onboarding/state')
  return json<OnboardingState>(response)
}

export interface WorkingDirInfo {
  path: string
  default_path: string
  custom: boolean
  restart_pending: boolean
}

export interface WorkingDirValidation {
  valid: boolean
  reason: string | null
  exists: boolean
  empty: boolean
  has_app_db: boolean
}

export async function getWorkingDir(): Promise<WorkingDirInfo> {
  const response = await apiFetch('/api/v1/config/working-dir')
  return json<WorkingDirInfo>(response)
}

export async function validateWorkingDir(path: string): Promise<WorkingDirValidation> {
  const response = await apiFetch('/api/v1/config/working-dir/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  return json<WorkingDirValidation>(response)
}

export async function setWorkingDir(
  path: string
): Promise<{ path: string; restart_required: boolean }> {
  const response = await apiFetch('/api/v1/config/working-dir', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  return json<{ path: string; restart_required: boolean }>(response)
}

export async function resetWorkingDir(): Promise<{ restart_required: boolean }> {
  const response = await apiFetch('/api/v1/config/working-dir', { method: 'DELETE' })
  return json<{ restart_required: boolean }>(response)
}

export async function createSampleCourse(): Promise<{
  course_id: number
  materials: number
  created: boolean
}> {
  const response = await apiFetch('/api/v1/onboarding/sample', { method: 'POST' })
  return json<{ course_id: number; materials: number; created: boolean }>(response)
}

export async function setTaskBudget(
  task: string,
  monthlyCapUsd: number | null
): Promise<TaskInfo> {
  const response = await apiFetch(`/api/v1/tasks/${task}/budget`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ monthly_cap_usd: monthlyCapUsd }),
  })
  return json<TaskInfo>(response)
}

export interface TaskCost {
  task: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
  models: Record<string, number>
  monthly_cap_usd: number | null
}

export interface CostsSummary {
  month: string
  per_task: TaskCost[]
  total_usd: number
}

export async function getCosts(): Promise<CostsSummary> {
  const response = await apiFetch('/api/v1/analytics/costs')
  return json<CostsSummary>(response)
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

export interface CourseTypeInfo {
  id: number
  key: string
  name: string
  description: string | null
}

export interface SkillInfo {
  key: string
  task: string
  name: string
  description: string | null
  is_system: boolean
}

export interface SkillVersionInfo {
  id: number
  scope_type: string
  scope_ref: number | null
  version: number
  system_template: string
  user_template: string
  params: Record<string, unknown> | null
  contract: Record<string, unknown> | null
  is_active: boolean
  created_at: string
}

export async function listSkills(): Promise<SkillInfo[]> {
  const response = await apiFetch('/api/v1/skills')
  return json<SkillInfo[]>(response)
}

export async function listCourseTypes(): Promise<CourseTypeInfo[]> {
  const response = await apiFetch('/api/v1/skills/course-types')
  return json<CourseTypeInfo[]>(response)
}

export async function createCourseType(body: {
  key: string
  name: string
  description?: string | null
}): Promise<CourseTypeInfo> {
  const response = await apiFetch('/api/v1/skills/course-types', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<CourseTypeInfo>(response)
}

export async function skillVersions(skillKey: string): Promise<SkillVersionInfo[]> {
  const response = await apiFetch(`/api/v1/skills/${skillKey}/versions`)
  return json<SkillVersionInfo[]>(response)
}

export async function saveSkillVersion(
  skillKey: string,
  body: {
    scope_type: string
    scope_ref?: number | null
    system_template: string
    user_template?: string
    contract?: Record<string, unknown> | null
  }
): Promise<SkillVersionInfo> {
  const response = await apiFetch(`/api/v1/skills/${skillKey}/versions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<SkillVersionInfo>(response)
}

export async function activateSkillVersion(
  skillKey: string,
  versionId: number
): Promise<SkillVersionInfo> {
  const response = await apiFetch(
    `/api/v1/skills/${skillKey}/versions/${versionId}/activate`,
    { method: 'POST' }
  )
  return json<SkillVersionInfo>(response)
}

export async function restoreSkillDefault(skillKey: string): Promise<SkillVersionInfo> {
  const response = await apiFetch(`/api/v1/skills/${skillKey}/restore`, { method: 'POST' })
  return json<SkillVersionInfo>(response)
}

export async function skillResolution(
  skillKey: string,
  courseId?: number | null
): Promise<{ chain: Record<string, string>; active: SkillVersionInfo | null }> {
  const params = courseId ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/skills/${skillKey}/resolution${params}`)
  return json<{ chain: Record<string, string>; active: SkillVersionInfo | null }>(response)
}

export async function contextVars(): Promise<Record<string, { type: string; docs: string }>> {
  const response = await apiFetch('/api/v1/skills/context-vars')
  return json<Record<string, { type: string; docs: string }>>(response)
}

export async function skillTestRun(
  skillKey: string,
  context: Record<string, unknown>
): Promise<{
  system: string
  user: string
  constraints: { kind: string; params: Record<string, unknown> }[]
  skill_version_id: number
}> {
  const response = await apiFetch('/api/v1/skills/test-run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skill_key: skillKey, context }),
  })
  return json<{
    system: string
    user: string
    constraints: { kind: string; params: Record<string, unknown> }[]
    skill_version_id: number
  }>(response)
}

import type { components } from '@/lib/api-schema'
import { json, apiFetch } from './client'
import type { WorkspaceConcept } from './materials'

type Schemas = components['schemas']

export type GenesisDraft = Schemas['GenesisDraftOut']
export type GenesisCommitResult = Schemas['GenesisCommitOut']

export interface CourseTaskInfo {
  task: string
  description: string
  requires: string
  model_id: string | null
  fallback_model_id: string | null
  model_label: string | null
  fallback_model_label: string | null
  global_model_label: string | null
  global_fallback_model_label: string | null
}

export interface CourseDefaultTaskInfo {
  // ADR-0037: course capability defaults are single-slot.
  requires: string
  model_id: string | null
  model_label: string | null
  global_model_label: string | null
}

export async function listCourseTasks(courseId: string): Promise<CourseTaskInfo[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/tasks`)
  return json<CourseTaskInfo[]>(response)
}

export async function assignCourseTask(
  courseId: string,
  task: string,
  modelId: string | null,
  fallbackModelId: string | null = null
): Promise<CourseTaskInfo> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/tasks/${task}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: modelId, fallback_model_id: fallbackModelId }),
  })
  return json<CourseTaskInfo>(response)
}

export async function listCourseTaskDefaults(
  courseId: string
): Promise<CourseDefaultTaskInfo[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/tasks/defaults`)
  return json<CourseDefaultTaskInfo[]>(response)
}

export async function assignCourseTaskDefault(
  courseId: string,
  requires: string,
  modelId: string | null
): Promise<CourseDefaultTaskInfo> {
  // ADR-0037: course capability defaults are single-slot.
  const response = await apiFetch(
    `/api/v1/courses/${courseId}/tasks/defaults/${requires}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    }
  )
  return json<CourseDefaultTaskInfo>(response)
}

export interface Course {
  id: string
  title: string
  subject: string | null
  level: string | null
  description: string | null
  color: string | null
  archived_at: string | null
  exam_date?: string | null
  material_count: number
  origin?: 'manual' | 'genesis' | 'import' | 'scratch'
  hidden?: boolean
}

export interface ScratchpadInfo {
  course: Course
  content_count: number
}

export async function getScratchpad(): Promise<ScratchpadInfo> {
  const response = await apiFetch('/api/v1/courses/scratchpad')
  return json<ScratchpadInfo>(response)
}

export async function promoteNode(
  courseId: string,
  nodeId: string,
  body: { title: string; subject?: string | null; level?: string | null; color?: string | null }
): Promise<Course> {
  const response = await apiFetch(
    `/api/v1/courses/${courseId}/nodes/${nodeId}/promote`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }
  )
  return json<Course>(response)
}

export async function draftGenesis(body: {
  topic: string
  level?: string | null
  ground?: boolean
}): Promise<GenesisDraft> {
  const response = await apiFetch('/api/v1/courses/genesis/draft', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<GenesisDraft>(response)
}

export async function createGenesisCourse(body: {
  draft: GenesisDraft
  lessons: boolean
  quizzes: boolean
  flashcards: boolean
  sources?: string[]
}): Promise<GenesisCommitResult> {
  const response = await apiFetch('/api/v1/courses/genesis', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<GenesisCommitResult>(response)
}

export async function listCourses(): Promise<Course[]> {
  const response = await apiFetch('/api/v1/courses')
  return json<Course[]>(response)
}

export async function getCourse(id: string): Promise<Course> {
  const response = await apiFetch(`/api/v1/courses/${id}`)
  return json<Course>(response)
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

export async function deleteCourse(id: string, confirmedBackup: boolean): Promise<void> {
  const response = await apiFetch(
    `/api/v1/courses/${id}?confirmed_backup=${confirmedBackup}`,
    { method: 'DELETE' }
  )
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
}

export function courseExportUrl(courseId: string): string {
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
  | { dry_run: false; imported: { course_id: string; title: string } }
> {
  const response = await apiFetch(
    `/api/v1/courses/import?dry_run=${dryRun}`,
    { method: 'POST', body: file }
  )
  return json(response)
}

export interface AllocationInfo {
  material_id: string
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
  folder_id: string
  name: string
  source_id: string | null
}

export interface NodeInfo {
  id: string
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

export async function courseTree(courseId: string): Promise<NodeInfo[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/tree`)
  return json<NodeInfo[]>(response)
}

export interface NodeDetail {
  id: string
  course_id: string
  parent_id: string | null
  title: string
  summary: string | null
  objectives: string[]
  depth: number
  is_root: boolean
  order_idx: number
}

export async function getNode(nodeId: string): Promise<NodeDetail> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}`)
  return json<NodeDetail>(response)
}

export async function addNode(
  courseId: string,
  parentId: string,
  title: string
): Promise<{ id: string; title: string; order_idx: number; depth: number }> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/nodes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, parent_id: parentId, title }),
  })
  return json<{ id: string; title: string; order_idx: number; depth: number }>(response)
}

export async function renameNode(id: string, title: string): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  await json<unknown>(response)
}

export async function updateNode(
  id: string,
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
  id: string,
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
  id: string,
  parentId: string,
  position: number
): Promise<void> {
  const response = await apiFetch(`/api/v1/nodes/${id}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent_id: parentId, position }),
  })
  await json<unknown>(response)
}

export async function deleteNode(id: string): Promise<{ deleted_item_id: string }> {
  const response = await apiFetch(`/api/v1/nodes/${id}`, { method: 'DELETE' })
  return json<{ deleted_item_id: string }>(response)
}

export async function restoreNode(undoToken: string): Promise<{ id: string }> {
  const response = await apiFetch('/api/v1/nodes/restore', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ undo_token: undoToken }),
  })
  return json<{ id: string }>(response)
}

export interface WorkspaceMaterial {
  material_id: string
  title: string
  kind: string
  status: string
  read_status: string
  progress: number
  rationale: string | null
  auto_assigned: boolean | null
  confidence: number | null
  provenance?: { source?: string } | null
  reextract_modes?: string[]
  has_extraction: boolean
  via_folder_id: string | null
  via_folder_name: string | null
}

export interface WorkspaceFolder {
  folder_id: string
  name: string
  source_id: string | null
  member_count: number
  rationale: string | null
  auto_assigned: boolean
}

export interface WorkspaceChild {
  id: string
  title: string
  depth: number
  order_idx: number
  objectives: string[]
  summary: string | null
}

export interface WorkspaceNote {
  id: string
  title: string
  node_id: string | null
  owner_type: string
  owner_id: string | null
  pinned: boolean
  updated_at: string | null
}

export interface ScopeCounts {
  direct: number
  with_children: number
}

export interface NodeWorkspace {
  node: {
    id: string
    course_id: string
    course_title: string | null
    title: string
    summary: string | null
    objectives: string[]
    ai_hint: string | null
    depth: number
    is_root: boolean
    parent_id: string | null
    breadcrumb: { id: string; title: string; depth: number }[]
  }
  children: WorkspaceChild[]
  folders: WorkspaceFolder[]
  materials: WorkspaceMaterial[]
  folder_material_ids: string[]
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

export async function nodeWorkspace(nodeId: string): Promise<NodeWorkspace> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/workspace`)
  return json<NodeWorkspace>(response)
}

export async function addNodeConcept(
  nodeId: string,
  conceptId: string
): Promise<{ node_id: string; concept_id: string }> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/concepts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ concept_id: conceptId }),
  })
  return json<{ node_id: string; concept_id: string }>(response)
}

export async function removeNodeConcept(
  nodeId: string,
  conceptId: string
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

export type ConceptMastery = 'strong' | 'shaky' | 'weak' | null

export interface ConceptNode {
  id: string
  name: string
  description: string | null
  aliases: string[]
  nodes: { node_id: string; node_title: string }[]
  mastery?: ConceptMastery
}

export interface ConceptGraph {
  concepts: ConceptNode[]
  links: { from: string; to: string; relation: string }[]
}

export async function extractConcepts(courseId: string): Promise<ConceptDraft> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/concepts/extract`, {
    method: 'POST',
  })
  return json<ConceptDraft>(response)
}

export async function commitConcepts(
  courseId: string,
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

export async function conceptGraph(courseId: string): Promise<ConceptGraph> {
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
  node_id: string
  node_title: string
  findings: OrganizerFinding[]
  material_id: string
}

export async function reviewNode(nodeId: string): Promise<NodeReview> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/review`, {
    method: 'POST',
  })
  return json<NodeReview>(response)
}

export interface NodeArtifacts {
  cheat_sheet: { material_id: string; title: string } | null
  reviews: { material_id: string; title: string }[]
  artifact?: { material_id: string; title: string } | null
}

export async function getNodeArtifacts(
  nodeId: string,
  kind?: string
): Promise<NodeArtifacts> {
  const suffix = kind ? `?kind=${encodeURIComponent(kind)}` : ''
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/artifacts${suffix}`)
  return json<NodeArtifacts>(response)
}

export async function draftNodeNote(
  nodeId: string
): Promise<{ note_id: string; markdown: string; existing: boolean }> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/draft-note`, {
    method: 'POST',
  })
  return json<{ note_id: string; markdown: string; existing: boolean }>(response)
}

export interface OutlineDraftSection {
  title: string
  objectives: string[]
  material_ids: string[]
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

export async function outlineDraft(courseId: string): Promise<OutlineDraft> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/outline/draft`, {
    method: 'POST',
  })
  return json<OutlineDraft>(response)
}

export async function outlineCommit(
  courseId: string,
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
  materialId: string,
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

export interface CourseTypeInfo {
  id: string
  key: string
  name: string
  description: string | null
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

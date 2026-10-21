import type { components } from '@/lib/api-schema'
import { json, apiFetch } from './client'

type Schemas = components['schemas']

export type CourseTaskInfo = Schemas['CourseTaskOut']
export type CourseDefaultTaskInfo = Schemas['CourseDefaultTaskOut']
export type Course = Schemas['CourseOut']
export type ScratchpadInfo = Schemas['ScratchpadOut']
export type CourseBundlePreview = Schemas['BundlePreviewOut']
export type AllocationInfo = Schemas['TreeNodeMaterialLink']
export type NodeCounts = Schemas['TreeNodeCounts']
export type NodeFolderLink = Schemas['TreeNodeFolderLink']
export type NodeInfo = Schemas['TreeNodeOut']
export type NodeDetail = Schemas['NodeDetailOut']
export type WorkspaceMaterial = Schemas['WorkspaceMaterialOut']
export type WorkspaceFolder = Schemas['WorkspaceFolderOut']
export type WorkspaceChild = Schemas['WorkspaceChildOut']
export type WorkspaceNote = Schemas['WorkspaceNoteOut']
export type ScopeCounts = Schemas['ScopeCountsOut']
export type NodeWorkspace = Schemas['NodeWorkspaceOut']
export type ConceptDraftEntry = Schemas['ConceptDraftEntryOut']
export type ConceptLinkDraft = Schemas['ConceptLinkDraftOut']
export type ConceptNodeDraft = Schemas['ConceptNodeDraftOut']
export type ConceptDraft = Schemas['ConceptDraftOut']
export type ConceptNode = Schemas['ConceptGraphConceptOut']
export type ConceptGraph = Schemas['ConceptGraphOut']
export type OrganizerFinding = Schemas['ReviewFindingOut']
export type NodeReview = Schemas['NodeReviewOut']
export type NodeArtifacts = Schemas['NodeArtifactsOut']
export type OutlineDraftSection = Schemas['OutlineSectionOut']
export type OutlineDraftChapter = Schemas['OutlineChapterOut']
export type OutlineDraft = Schemas['OutlineDraftOut']
export type CourseTypeInfo = Schemas['CourseTypeOut']

export type GenesisDraft = Schemas['GenesisDraftOut']
export type GenesisCommitResult = Schemas['GenesisCommitOut']

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

export async function courseTree(courseId: string): Promise<NodeInfo[]> {
  const response = await apiFetch(`/api/v1/courses/${courseId}/tree`)
  return json<NodeInfo[]>(response)
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

export type ConceptMastery = Schemas['ConceptGraphConceptOut']['mastery']

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

export async function reviewNode(nodeId: string): Promise<NodeReview> {
  const response = await apiFetch(`/api/v1/nodes/${nodeId}/review`, {
    method: 'POST',
  })
  return json<NodeReview>(response)
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

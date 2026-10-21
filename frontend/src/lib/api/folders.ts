import { json, expectOk, apiFetch } from './client'

export interface Folder {
  id: string
  name: string
  path: string
  course_id: string
  parent_id: string | null
  source_id: string | null
  created_at: string
  node_link_count?: number
}

export interface FolderLinkInfo {
  node_id: string
  owner_title: string
  breadcrumb: { id: string; title: string }[]
  is_course_level: boolean
  course_id: string
  course_title: string
  auto_assigned: boolean
  rationale: string | null
}

export async function listFolders(courseId?: string): Promise<Folder[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/folders${params}`)
  return json<Folder[]>(response)
}

export async function createFolder(
  name: string,
  parentId: string | null,
  courseId: string
): Promise<Folder> {
  const response = await apiFetch('/api/v1/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, parent_id: parentId, course_id: courseId }),
  })
  return json<Folder>(response)
}

export async function renameFolder(id: string, name: string): Promise<Folder> {
  const response = await apiFetch(`/api/v1/folders/${id}/rename`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  return json<Folder>(response)
}

export async function moveFolder(
  id: string,
  parentId: string | null
): Promise<Folder> {
  const response = await apiFetch(`/api/v1/folders/${id}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent_id: parentId }),
  })
  return json<Folder>(response)
}

export interface FolderDeleteInfoNodeLink {
  node_id: string
  owner_title: string
  breadcrumb: { id: string; title: string }[]
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

export async function getFolderLinks(id: string): Promise<FolderLinkInfo[]> {
  const response = await apiFetch(`/api/v1/folders/${id}/links`)
  return json<FolderLinkInfo[]>(response)
}

export async function getFolderDeleteInfo(id: string): Promise<FolderDeleteInfo> {
  const response = await apiFetch(`/api/v1/folders/${id}/delete-info`)
  return json<FolderDeleteInfo>(response)
}

export async function unlinkFolder(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/folders/${id}/unlink`, { method: 'POST' })
  await expectOk(response)
}

export async function deleteFolder(id: string, force = false): Promise<void> {
  const suffix = force ? '?force=true' : ''
  const response = await apiFetch(`/api/v1/folders/${id}${suffix}`, { method: 'DELETE' })
  await expectOk(response)
}

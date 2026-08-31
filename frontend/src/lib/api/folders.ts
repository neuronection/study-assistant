import { json, expectOk, apiFetch } from './client'

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

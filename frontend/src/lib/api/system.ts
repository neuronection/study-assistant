import type { components } from '@/lib/api-schema'
import { json, apiFetch } from './client'

export type Health = components['schemas']['HealthResponse']

export async function getHealth(fetchFn: typeof fetch = fetch): Promise<Health> {
  const response = await fetchFn('/api/v1/health')
  if (!response.ok) {
    throw new Error(`health check failed: ${response.status}`)
  }
  return (await response.json()) as Health
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

export interface DesktopFileEntry {
  path: string
  rel: string
  size: number
  mtime: number
}

export interface DesktopFolderListing {
  path: string
  files: DesktopFileEntry[]
}

export async function listDesktopFolder(path: string): Promise<DesktopFolderListing> {
  const response = await apiFetch(`/api/v1/desktop/folder?path=${encodeURIComponent(path)}`)
  return json<DesktopFolderListing>(response)
}

export async function registerDesktopDrops(paths: string[]): Promise<DesktopFolderListing> {
  const response = await apiFetch('/api/v1/desktop/drops', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paths }),
  })
  return json<DesktopFolderListing>(response)
}

export function desktopFileUrl(path: string): string {
  return `/api/v1/desktop/file?path=${encodeURIComponent(path)}`
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

export interface ProfileInfo {
  id: number
  name: string
  color: string | null
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
  ocr_image_max_edge: number
}

export async function getProfilePreferences(): Promise<ProfilePreferences> {
  const response = await apiFetch('/api/v1/profiles/preferences')
  return json<ProfilePreferences>(response)
}

export async function updateProfilePreferences(
  preferences: Partial<ProfilePreferences>
): Promise<ProfilePreferences> {
  const response = await apiFetch('/api/v1/profiles/preferences', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(preferences),
  })
  return json<ProfilePreferences>(response)
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

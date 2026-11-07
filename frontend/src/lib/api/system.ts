import type { components } from '@/lib/api-schema'
import { json, apiFetch } from './client'
import type {
  DesktopFolderListing,
  SearchProviderCatalog,
} from './hand-types'

type Schemas = components['schemas']

export type Health = components['schemas']['HealthResponse']

export type FsDirEntry = Schemas['FsDir']
export type FsDirs = Schemas['FsDirsOut']
export type DeletedItemInfo = Schemas['DeletedItemOut']
export type ProfileInfo = Schemas['ProfileOut']
export type DiscoverySitePreset = Schemas['DiscoverySitePreset']
export type DiscoveryPrefs = Schemas['DiscoveryPrefsOut']
export type ProfilePreferences = Schemas['PreferencesOut']
export type ProfilePreferencesUpdate = Schemas['PreferencesIn']
export type SearchProvider = Schemas['SearchProviderOut']
export type SearchProviderProbe = Schemas['SearchProviderProbeOut']
export type OnboardingState = Schemas['OnboardingStateOut']
export type WorkingDirInfo = Schemas['WorkingDirOut']
export type WorkingDirValidation = Schemas['ValidateWorkingDirOut']
export type UpdateCheck = Schemas['UpdateCheckOut']

export async function getHealth(fetchFn: typeof fetch = fetch): Promise<Health> {
  const response = await fetchFn('/api/v1/health')
  if (!response.ok) {
    throw new Error(`health check failed: ${response.status}`)
  }
  return (await response.json()) as Health
}

export async function getUpdateCheck(): Promise<UpdateCheck> {
  const response = await apiFetch('/api/v1/instance/update-check')
  return json<UpdateCheck>(response)
}

export async function listFsDirs(path?: string): Promise<FsDirs> {
  const params = path !== undefined ? `?path=${encodeURIComponent(path)}` : ''
  const response = await apiFetch(`/api/v1/fs/dirs${params}`)
  return json<FsDirs>(response)
}

export type {
  DesktopFileEntry,
  DesktopFolderListing,
  SearchProviderCatalog,
  SearchProviderCatalogEntry,
  SearchProviderCatalogField,
} from './hand-types'

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

export async function listDeletedItems(): Promise<DeletedItemInfo[]> {
  const response = await apiFetch('/api/v1/deleted-items')
  return json<DeletedItemInfo[]>(response)
}

export async function restoreDeletedItem(
  id: string
): Promise<{ status: string; entity_type: string; title: string }> {
  const response = await apiFetch(`/api/v1/deleted-items/${id}/restore`, {
    method: 'POST',
  })
  return json<{ status: string; entity_type: string; title: string }>(response)
}

export async function purgeDeletedItem(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/deleted-items/${id}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed: ${response.status}`)
  }
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

export async function deleteProfile(profileId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/profiles/${profileId}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Failed to delete profile (${response.status})`)
  }
}

export async function patchProfile(
  profileId: string,
  body: { name?: string; color?: string | null; is_default?: boolean },
): Promise<ProfileInfo> {
  const response = await apiFetch(`/api/v1/profiles/${profileId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ProfileInfo>(response)
}

export async function getProfilePreferences(): Promise<ProfilePreferences> {
  const response = await apiFetch('/api/v1/profiles/preferences')
  return json<ProfilePreferences>(response)
}

export async function updateProfilePreferences(
  preferences: ProfilePreferencesUpdate
): Promise<ProfilePreferences> {
  const response = await apiFetch('/api/v1/profiles/preferences', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(preferences),
  })
  return json<ProfilePreferences>(response)
}

// Family web-search contract (ADR-0035 / plan 28): an ordered multi-provider
// list — the first enabled provider that answers wins.
export async function listSearchProviders(): Promise<SearchProvider[]> {
  const response = await apiFetch('/api/v1/search-providers')
  const body = (await json<{ providers: SearchProvider[] }>(response)).providers
  return body
}

export async function getSearchProviderCatalog(): Promise<SearchProviderCatalog> {
  const response = await apiFetch('/api/v1/search-providers/catalog')
  return json<SearchProviderCatalog>(response)
}

export async function createSearchProvider(body: Schemas['SearchProviderIn']): Promise<SearchProvider> {
  const response = await apiFetch('/api/v1/search-providers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<SearchProvider>(response)
}

export async function updateSearchProvider(
  providerId: string,
  body: Schemas['SearchProviderIn'],
): Promise<SearchProvider> {
  const response = await apiFetch(`/api/v1/search-providers/${providerId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<SearchProvider>(response)
}

export async function moveSearchProvider(
  providerId: string,
  direction: 'up' | 'down',
): Promise<SearchProvider[]> {
  const response = await apiFetch(`/api/v1/search-providers/${providerId}/move`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ direction }),
  })
  return (await json<{ providers: SearchProvider[] }>(response)).providers
}

export async function deleteSearchProvider(providerId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/search-providers/${providerId}`, {
    method: 'DELETE',
  })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed (${response.status})`)
  }
}

export async function testSearchProvider(providerId: string): Promise<SearchProviderProbe> {
  const response = await apiFetch(`/api/v1/search-providers/${providerId}/test`, {
    method: 'POST',
  })
  return json<SearchProviderProbe>(response)
}

export async function getOnboardingState(): Promise<OnboardingState> {
  const response = await apiFetch('/api/v1/onboarding/state')
  return json<OnboardingState>(response)
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
  course_id: string
  materials: number
  created: boolean
}> {
  const response = await apiFetch('/api/v1/onboarding/sample', { method: 'POST' })
  return json<{ course_id: string; materials: number; created: boolean }>(response)
}

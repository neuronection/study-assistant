import { json, apiFetch } from './client'

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

export async function restoreBackup(file: File): Promise<{ status: string; materials: number }> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiFetch('/api/v1/backup/restore', { method: 'POST', body: form })
  return json<{ status: string; materials: number }>(response)
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

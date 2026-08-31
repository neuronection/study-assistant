import { json, apiFetch } from './client'

export interface JobInfo {
  id: number
  type: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
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
  cancelled: number
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

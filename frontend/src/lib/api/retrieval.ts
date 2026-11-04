import type { components } from '@/lib/api-schema'

import { apiFetch, json } from './client'

type Schemas = components['schemas']

export type RetrievalOverview = Schemas['RetrievalOverviewOut']
export type RetrievalSpaces = Schemas['RetrievalSpacesOut']
export type RetrievalCoverageEnvelope = Schemas['RetrievalCoverageEnvelopeOut']
export type RetrievalRuns = Schemas['RetrievalRunsOut']
export type RetrievalReindexRequest = Schemas['RetrievalReindexIn']
export type RetrievalMaintenanceRequest = Schemas['RetrievalMaintenanceIn']
export type RetrievalSpaceBuildRequest = Schemas['RetrievalSpaceBuildIn']
export type RetrievalSpaceConfirmRequest = Schemas['RetrievalSpaceConfirmIn']
export type RetrievalCutoverRequest = Schemas['RetrievalCutoverIn']
export type RetrievalAction = Schemas['RetrievalActionOut']
export type RetrievalQuality = Schemas['RetrievalQualityEnvelopeOut']
export type RetrievalQualityCompareRequest = Schemas['RetrievalQualityCompareIn']
export type RetrievalQueryHealth = Schemas['RetrievalQueryHealthEnvelopeOut']
export type RetrievalUsage = Schemas['RetrievalUsageOut']

export async function getRetrievalOverview(
  window?: string
): Promise<RetrievalOverview> {
  const search = window ? `?window=${encodeURIComponent(window)}` : ''
  const response = await apiFetch(`/api/v1/admin/retrieval/overview${search}`)
  return json<RetrievalOverview>(response)
}

export async function getRetrievalSpaces(): Promise<RetrievalSpaces> {
  const response = await apiFetch('/api/v1/admin/retrieval/spaces')
  return json<RetrievalSpaces>(response)
}

export async function getRetrievalCoverage(
  space?: string
): Promise<RetrievalCoverageEnvelope> {
  const search = space ? `?space=${encodeURIComponent(space)}` : ''
  const response = await apiFetch(`/api/v1/admin/retrieval/coverage${search}`)
  return json<RetrievalCoverageEnvelope>(response)
}

export async function getRetrievalRuns(): Promise<RetrievalRuns> {
  const response = await apiFetch('/api/v1/admin/retrieval/runs')
  return json<RetrievalRuns>(response)
}

export async function getRetrievalQuality(
  space?: string
): Promise<RetrievalQuality> {
  const search = space ? `?space=${encodeURIComponent(space)}` : ''
  const response = await apiFetch(`/api/v1/admin/retrieval/quality${search}`)
  return json<RetrievalQuality>(response)
}

export async function getRetrievalQueryHealth(
  window?: string
): Promise<RetrievalQueryHealth> {
  const search = window ? `?window=${encodeURIComponent(window)}` : ''
  const response = await apiFetch(
    `/api/v1/admin/retrieval/query-health${search}`
  )
  return json<RetrievalQueryHealth>(response)
}

export async function getRetrievalUsage(
  window?: string
): Promise<RetrievalUsage> {
  const search = window ? `?window=${encodeURIComponent(window)}` : ''
  const response = await apiFetch(`/api/v1/admin/retrieval/usage${search}`)
  return json<RetrievalUsage>(response)
}

function actionHeaders(idempotencyKey?: string): Record<string, string> {
  const headers: Record<string, string> = { 'content-type': 'application/json' }
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
  return headers
}

export async function postRetrievalReindex(
  body: RetrievalReindexRequest,
  idempotencyKey: string
): Promise<RetrievalAction> {
  const response = await apiFetch('/api/v1/admin/retrieval/reindex', {
    method: 'POST',
    headers: actionHeaders(idempotencyKey),
    body: JSON.stringify(body),
  })
  return json<RetrievalAction>(response)
}

export async function postRetrievalMaintenance(
  body: RetrievalMaintenanceRequest,
  idempotencyKey: string
): Promise<RetrievalAction> {
  const response = await apiFetch('/api/v1/admin/retrieval/maintenance', {
    method: 'POST',
    headers: actionHeaders(idempotencyKey),
    body: JSON.stringify(body),
  })
  return json<RetrievalAction>(response)
}

export async function postRetrievalBuildSpace(
  body: RetrievalSpaceBuildRequest,
  idempotencyKey: string
): Promise<RetrievalAction> {
  const response = await apiFetch('/api/v1/admin/retrieval/spaces', {
    method: 'POST',
    headers: actionHeaders(idempotencyKey),
    body: JSON.stringify(body),
  })
  return json<RetrievalAction>(response)
}

export async function activateRetrievalSpace(
  spaceId: string,
  idempotencyKey: string
): Promise<RetrievalAction> {
  const response = await apiFetch(
    `/api/v1/admin/retrieval/spaces/${encodeURIComponent(spaceId)}/activate`,
    { method: 'POST', headers: actionHeaders(idempotencyKey) }
  )
  return json<RetrievalAction>(response)
}

export async function retireRetrievalSpace(
  spaceId: string,
  confirmSpaceName: string,
  idempotencyKey: string
): Promise<RetrievalAction> {
  const response = await apiFetch(
    `/api/v1/admin/retrieval/spaces/${encodeURIComponent(spaceId)}/retire`,
    {
      method: 'POST',
      headers: actionHeaders(idempotencyKey),
      body: JSON.stringify({ confirm_space_name: confirmSpaceName }),
    }
  )
  return json<RetrievalAction>(response)
}

export async function dropRetrievalSpace(
  spaceId: string,
  confirmSpaceName: string,
  idempotencyKey: string,
  force = false
): Promise<RetrievalAction> {
  const response = await apiFetch(
    `/api/v1/admin/retrieval/spaces/${encodeURIComponent(spaceId)}/drop`,
    {
      method: 'POST',
      headers: actionHeaders(idempotencyKey),
      body: JSON.stringify({ confirm_space_name: confirmSpaceName, force }),
    }
  )
  return json<RetrievalAction>(response)
}

export async function postRetrievalCutover(
  body: RetrievalCutoverRequest,
  idempotencyKey: string
): Promise<RetrievalAction> {
  const response = await apiFetch('/api/v1/admin/retrieval/cutover', {
    method: 'POST',
    headers: actionHeaders(idempotencyKey),
    body: JSON.stringify(body),
  })
  return json<RetrievalAction>(response)
}

export async function postRetrievalQualityCompare(
  body: RetrievalQualityCompareRequest,
  idempotencyKey: string
): Promise<RetrievalAction> {
  const response = await apiFetch('/api/v1/admin/retrieval/quality/compare', {
    method: 'POST',
    headers: actionHeaders(idempotencyKey),
    body: JSON.stringify(body),
  })
  return json<RetrievalAction>(response)
}

export async function cancelRetrievalRun(runId: string): Promise<RetrievalAction> {
  const response = await apiFetch(
    `/api/v1/admin/retrieval/runs/${encodeURIComponent(runId)}/cancel`,
    { method: 'POST' }
  )
  return json<RetrievalAction>(response)
}

export async function retryRetrievalRun(
  runId: string,
  idempotencyKey: string
): Promise<RetrievalAction> {
  const response = await apiFetch(
    `/api/v1/admin/retrieval/runs/${encodeURIComponent(runId)}/retry`,
    {
      method: 'POST',
      headers: actionHeaders(idempotencyKey),
    }
  )
  return json<RetrievalAction>(response)
}

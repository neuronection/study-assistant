import type { components } from '@/lib/api-schema'

import { apiFetch, json } from './client'

type Schemas = components['schemas']

export type RetrievalOverview = Schemas['RetrievalOverviewOut']
export type RetrievalSpaces = Schemas['RetrievalSpacesOut']
export type RetrievalCoverageEnvelope = Schemas['RetrievalCoverageEnvelopeOut']
export type RetrievalRuns = Schemas['RetrievalRunsOut']

export async function getRetrievalOverview(): Promise<RetrievalOverview> {
  const response = await apiFetch('/api/v1/admin/retrieval/overview')
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

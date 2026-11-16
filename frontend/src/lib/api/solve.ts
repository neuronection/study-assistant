import type { components } from '@/lib/api-schema'

import { apiFetch, json } from './client'
import type { SolveResultView } from './hand-types'

type Schemas = components['schemas']

export type SolveEntry = Omit<Schemas['SolveOut'], 'result'> & {
  result: SolveResultView
}
export type SolveVariant = Schemas['SolveVariantOut']
export type SolveCheck = Schemas['SolveCheckOut']
export type SolveRecognize = Schemas['SolveRecognizeOut']

export async function solveProblem(body: {
  input_text: string
  input_kind?: string
}): Promise<SolveEntry> {
  const response = await apiFetch('/api/v1/solve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<SolveEntry>(response)
}

export async function solveHistory(limit = 20): Promise<SolveEntry[]> {
  const response = await apiFetch(`/api/v1/solve/history?limit=${limit}`)
  return json<SolveEntry[]>(response)
}

export async function getSolve(id: string): Promise<SolveEntry> {
  const response = await apiFetch(`/api/v1/solve/${id}`)
  return json<SolveEntry>(response)
}

export async function deleteSolve(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/solve/${id}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed (${response.status})`)
  }
}

export async function saveSolveNote(id: string): Promise<{ note_id: string }> {
  const response = await apiFetch(`/api/v1/solve/${id}/note`, { method: 'POST' })
  return json<{ note_id: string }>(response)
}

export async function solveVariants(id: string): Promise<SolveVariant[]> {
  const response = await apiFetch(`/api/v1/solve/${id}/variants`, { method: 'POST' })
  return json<SolveVariant[]>(response)
}

export async function checkSolveVariant(
  id: string,
  index: number,
  responseText: string
): Promise<SolveCheck> {
  const response = await apiFetch(`/api/v1/solve/${id}/variants/check`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ index, response: responseText }),
  })
  return json<SolveCheck>(response)
}

export async function recognizeSolve(file: File): Promise<SolveRecognize> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiFetch('/api/v1/solve/recognize', {
    method: 'POST',
    body: form,
  })
  return json<SolveRecognize>(response)
}

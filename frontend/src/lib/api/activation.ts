import type { components } from '@/lib/api-schema'
import type { ActivationEvent, ActivationProps } from '@/lib/activation-vocab'

import { apiFetch, json } from './client'

type Schemas = components['schemas']

export type ActivationSummary = Schemas['ActivationSummaryOut']
export type ActivationExport = Schemas['ActivationExportOut']

export async function recordActivation(
  event: ActivationEvent,
  props?: ActivationProps | null
): Promise<void> {
  await apiFetch('/api/v1/activation/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event, props: props ?? null }),
  })
}

export async function getActivationSummary(): Promise<ActivationSummary> {
  const response = await apiFetch('/api/v1/activation/summary')
  return json<ActivationSummary>(response)
}

export async function exportActivation(): Promise<ActivationExport> {
  const response = await apiFetch('/api/v1/activation/export')
  return json<ActivationExport>(response)
}

export async function clearActivation(): Promise<void> {
  const response = await apiFetch('/api/v1/activation', { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`clear failed (${response.status})`)
  }
}

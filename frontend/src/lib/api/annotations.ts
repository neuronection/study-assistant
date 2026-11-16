import type { components } from '@/lib/api-schema'
import { apiFetch, json } from './client'

type Schemas = components['schemas']

export type Anchor = Schemas['AnchorOut']
export type AnchorCreate = Schemas['AnchorCreateIn']
export type AnchorPatch = Schemas['AnchorPatchIn']

export async function listMaterialAnchors(materialId: string): Promise<Anchor[]> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/anchors`)
  return json<Anchor[]>(response)
}

export async function createMaterialAnchor(
  materialId: string,
  body: AnchorCreate
): Promise<Anchor> {
  const response = await apiFetch(`/api/v1/materials/${materialId}/anchors`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<Anchor>(response)
}

export async function patchAnchor(anchorId: string, body: AnchorPatch): Promise<Anchor> {
  const response = await apiFetch(`/api/v1/anchors/${anchorId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<Anchor>(response)
}

export async function deleteAnchor(anchorId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/anchors/${anchorId}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`delete anchor failed: ${response.status}`)
  }
}

import type { components } from '@/lib/api-schema'
import { apiFetch, json } from './client'

export type ExtensionDocs = components['schemas']['ExtensionDocsOut']

export async function getExtensionDocumentation(
  extensionId: string,
  file?: string,
): Promise<ExtensionDocs> {
  const params = new URLSearchParams()
  if (file) {
    params.set('file', file)
  }
  const query = params.toString()
  const response = await apiFetch(
    `/api/v1/extensions/${extensionId}/documentation${query ? `?${query}` : ''}`,
  )
  return json<ExtensionDocs>(response)
}

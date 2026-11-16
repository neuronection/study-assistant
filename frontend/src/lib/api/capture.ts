import type { components } from '@/lib/api-schema'
import { json, apiFetch } from './client'

type Schemas = components['schemas']

export type CaptureStaging = Schemas['CaptureStagingOut']
export type CaptureCommit = Schemas['CaptureCommitOut']
export type CaptureSourceKind = 'upload' | 'camera' | 'clipboard' | 'drop'

export async function stageCaptures(
  files: File[],
  sourceKind: CaptureSourceKind = 'camera',
  clientOpId?: string
): Promise<CaptureStaging[]> {
  const form = new FormData()
  form.append('source_kind', sourceKind)
  if (clientOpId !== undefined) {
    form.append('client_op_id', clientOpId)
  }
  for (const file of files) {
    form.append('files', file, file.name)
  }
  const response = await apiFetch('/api/v1/capture', {
    method: 'POST',
    body: form,
  })
  return json<CaptureStaging[]>(response)
}

export async function listCaptures(): Promise<CaptureStaging[]> {
  const response = await apiFetch('/api/v1/capture')
  return json<CaptureStaging[]>(response)
}

export async function assembleCaptures(
  items: Array<{ captureId: string; rotation: number }>,
  title?: string
): Promise<CaptureStaging> {
  const response = await apiFetch('/api/v1/capture/assemble', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      items: items.map((item) => ({
        capture_id: item.captureId,
        rotation: item.rotation,
      })),
      title: title ?? null,
    }),
  })
  return json<CaptureStaging>(response)
}

export async function commitCapture(
  captureId: string,
  target: { courseId: string; folderId?: string | null; nodeId?: string | null; title?: string }
): Promise<CaptureCommit> {
  const response = await apiFetch(`/api/v1/capture/${captureId}/commit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      course_id: target.courseId,
      folder_id: target.folderId ?? null,
      node_id: target.nodeId ?? null,
      title: target.title ?? null,
    }),
  })
  return json<CaptureCommit>(response)
}

export async function discardCapture(captureId: string): Promise<CaptureStaging> {
  const response = await apiFetch(`/api/v1/capture/${captureId}`, { method: 'DELETE' })
  return json<CaptureStaging>(response)
}

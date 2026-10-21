import type { components } from '@/lib/api-schema'

import { json, expectOk, apiFetch, audioFilename } from './client'
import type { AiContextStats, GenerateContext } from './hand-types'

type Schemas = components['schemas']

export type { GenerateContext, GenerateScope } from './hand-types'
export type AiContextPreview = Omit<Schemas['PreviewOut'], 'stats'> & { stats: AiContextStats }
export type AiToolArgument = Schemas['ToolArgumentOut']
export type AiToolInfo = Schemas['ToolInfoOut']
export type McpToolInfo = Schemas['McpToolOut']
export type McpInfo = Schemas['McpInfoOut']
export type EditorTransformMode = NonNullable<Schemas['EditorTransformIn']['mode']>
export type EditorTransformRequest = Schemas['EditorTransformIn']
export type EditorTransformJobOut = Schemas['EditorTransformJobOut']
export type EditorTransformJobStatus = Schemas['EditorTransformStatusOut']['status']
export type EditorTransformJobState = Schemas['EditorTransformStatusOut']
export type TranscriptionResult = Schemas['TranscribeOut']

export async function previewAiContext(
  courseId: string,
  spec: GenerateContext & { node_id?: string | null; query?: string | null }
): Promise<AiContextPreview> {
  const response = await apiFetch('/api/v1/ai/context/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, ...spec }),
  })
  return json<AiContextPreview>(response)
}

export async function listAiTools(): Promise<AiToolInfo[]> {
  const response = await apiFetch('/api/v1/ai/tools')
  const body = await json<{ tools: AiToolInfo[] }>(response)
  return body.tools
}

export async function listMcpInfo(): Promise<McpInfo> {
  const response = await apiFetch('/api/v1/ai/mcp')
  return json<McpInfo>(response)
}

export async function startEditorTransform(
  body: EditorTransformRequest
): Promise<EditorTransformJobOut> {
  const response = await apiFetch(`/api/v1/ai/editor/transform`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<EditorTransformJobOut>(response)
}

export async function getEditorTransformJob(
  jobId: string
): Promise<EditorTransformJobState> {
  const response = await apiFetch(`/api/v1/ai/editor/jobs/${jobId}`)
  return json<EditorTransformJobState>(response)
}

export async function cancelEditorTransformJob(jobId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/ai/editor/jobs/${jobId}/cancel`, {
    method: 'POST',
  })
  await expectOk(response)
}

export async function transcribeAudio(
  blob: Blob,
  language?: string | null
): Promise<TranscriptionResult> {
  const form = new FormData()
  form.append('file', blob, audioFilename(blob))
  if (language) {
    form.append('language', language)
  }
  const response = await apiFetch('/api/v1/ai/transcribe', {
    method: 'POST',
    body: form,
  })
  return json<TranscriptionResult>(response)
}

export async function speakText(text: string): Promise<Blob> {
  const response = await apiFetch('/api/v1/ai/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  await expectOk(response)
  return await response.blob()
}

export async function contextVars(): Promise<Record<string, { type: string; docs: string }>> {
  const response = await apiFetch('/api/v1/skills/context-vars')
  return json<Record<string, { type: string; docs: string }>>(response)
}

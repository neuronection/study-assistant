import { json, expectOk, apiFetch, audioFilename } from './client'

export type GenerateScope = 'node' | 'subtree' | 'course'

export interface GenerateContext {
  scope?: GenerateScope
  include_material_ids?: number[]
  exclude_material_ids?: number[]
  note_ids?: number[]
  concept_ids?: number[]
  context_hint?: string | null
}

export interface AiContextPreview {
  stats: {
    materials: { id: number; title: string }[]
    chunks: { material_id: number; title: string }[]
    notes: { id: number; title: string }[]
    concepts: { id: number; name: string }[]
    hints: number
    approx_chars: number
    retrieval_query: string | null
  }
  rendered: string
}

export async function previewAiContext(
  courseId: number,
  spec: GenerateContext & { node_id?: number | null; query?: string | null }
): Promise<AiContextPreview> {
  const response = await apiFetch('/api/v1/ai/context/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, ...spec }),
  })
  return json<AiContextPreview>(response)
}

export interface AiToolArgument {
  name: string
  type: string
  required: boolean
  description: string | null
}

export interface AiToolInfo {
  name: string
  description: string
  example: string | null
  arguments: AiToolArgument[]
  response: string
  scope: string
}

export interface McpToolInfo {
  name: string
  description: string
  arguments: AiToolArgument[]
}

export interface McpInfo {
  command: string
  instructions: string
  tools: McpToolInfo[]
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

export type EditorTransformMode = 'transform' | 'write'

export interface EditorTransformRequest {
  text: string
  instruction?: string
  preset?: string | null
  mode: EditorTransformMode
  include_context?: boolean
  context_document?: string
  ground_in_material?: boolean
  course_id?: number | null
  node_id?: number | null
}

export interface EditorTransformJobOut {
  job_id: number
}

export type EditorTransformJobStatus =
  | 'queued'
  | 'running'
  | 'done'
  | 'error'
  | 'cancelled'

export interface EditorTransformJobState {
  status: EditorTransformJobStatus
  result_md: string
  error: string | null
  problems: string[]
  rounds: number
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
  jobId: number
): Promise<EditorTransformJobState> {
  const response = await apiFetch(`/api/v1/ai/editor/jobs/${jobId}`)
  return json<EditorTransformJobState>(response)
}

export async function cancelEditorTransformJob(jobId: number): Promise<void> {
  const response = await apiFetch(`/api/v1/ai/editor/jobs/${jobId}/cancel`, {
    method: 'POST',
  })
  await expectOk(response)
}

export interface TranscriptionResult {
  text: string
  model: string
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

export async function contextVars(): Promise<Record<string, { type: string; docs: string }>> {
  const response = await apiFetch('/api/v1/skills/context-vars')
  return json<Record<string, { type: string; docs: string }>>(response)
}

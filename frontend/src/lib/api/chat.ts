import { json, apiFetch } from './client'
import type { BlockDto } from './materials'

export interface ChatSession {
  id: number
  public_id: string
  course_id: number | null
  node_id: number | null
  title: string
  use_embeddings: boolean | null
  created_at: string
}

export interface ChatCitation {
  index: number
  chunk_id: number
  material_id: number
  title: string
  quote: string
}

export type MentionKind = 'material' | 'note' | 'concept' | 'node' | 'quiz' | 'exercise'

export interface MentionRef {
  ref: string
  kind: MentionKind
  id: number
  title: string
  course_id?: number | null
  summary?: string | null
}

export interface ChatRead {
  ref: string
  kind: MentionKind
  id: number
  title: string
  course_id?: number | null
  chars: number
}

export interface ChatToolCall {
  name: string
  argument: string
  phase?: string | null
  result?: string | null
  title?: string | null
  status?: string | null
  start_ms?: number | null
  duration_ms?: number | null
}

export interface ChatTraceRound {
  index: number
  streamed: boolean
  start_ms: number
  duration_ms: number
  phase: string
}

export interface ChatTrace {
  run_id: string
  model: string | null
  latency_ms: number
  input_tokens: number | null
  output_tokens: number | null
  repair_rounds: number
  rounds: ChatTraceRound[]
  thinking?: string
}

export interface ChatContextData {
  session_id: number
  course_id: number | null
  node: { id: number; title: string } | null
  registry: MentionRef[]
  latest_notes: { id: number; title: string }[]
}

export interface ChatProposal {
  id: number
  action: string
  payload: Record<string, unknown>
  status: 'proposed' | 'approved' | 'dismissed' | 'executed' | 'stale'
  result?:
    | { note_id?: number; open_dialog?: Record<string, unknown>; error?: string }
    | null
}

export interface ChatMessage {
  id: number
  role: string
  markdown: string
  blocks?: BlockDto[]
  citations: ChatCitation[]
  mentions: MentionRef[]
  reads: ChatRead[]
  tool_calls: ChatToolCall[]
  proposals: ChatProposal[]
  grounded: boolean | null
  trace?: ChatTrace | null
  warnings?: string[]
  parent_id?: number | null
  variant_index?: number
  variant_count?: number
  sibling_ids?: number[]
}

export async function listChatSessions(nodeId?: number): Promise<ChatSession[]> {
  const params = nodeId !== undefined ? `?node_id=${nodeId}` : ''
  const response = await apiFetch(`/api/v1/chat/sessions${params}`)
  return json<ChatSession[]>(response)
}

export async function renameChatSession(sessionId: number, title: string): Promise<ChatSession> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return json<ChatSession>(response)
}

export async function updateChatSessionEmbeddings(
  sessionId: number,
  useEmbeddings: boolean
): Promise<ChatSession> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ use_embeddings: useEmbeddings }),
  })
  return json<ChatSession>(response)
}

export async function deleteChatSession(
  sessionId: number
): Promise<{ deleted_item_id: number }> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: 'DELETE',
  })
  return json<{ deleted_item_id: number }>(response)
}

export async function createChatSession(
  courseId: number | null,
  nodeId?: number | null,
  title?: string
): Promise<ChatSession> {
  const response = await apiFetch('/api/v1/chat/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      course_id: courseId,
      node_id: nodeId ?? null,
      ...(title !== undefined ? { title } : {}),
    }),
  })
  return json<ChatSession>(response)
}

export async function listChatMessages(sessionId: number): Promise<ChatMessage[]> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/messages`)
  const messages = await json<ChatMessage[]>(response)
  return messages.map((message) => ({
    ...message,
    mentions: message.mentions ?? [],
    reads: message.reads ?? [],
    tool_calls: message.tool_calls ?? [],
    proposals: message.proposals ?? [],
  }))
}

export async function getChatContext(sessionId: number): Promise<ChatContextData> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/context`)
  return json<ChatContextData>(response)
}

export async function editChatMessage(
  messageId: number,
  content: string,
): Promise<{ user_message: ChatMessage; job_id: number }> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  return json<{ user_message: ChatMessage; job_id: number }>(response)
}

export async function regenerateChatMessage(
  messageId: number,
): Promise<{ user_message: ChatMessage; job_id: number }> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/regenerate`, {
    method: 'POST',
  })
  return json<{ user_message: ChatMessage; job_id: number }>(response)
}

export async function selectChatVariant(messageId: number): Promise<ChatMessage[]> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/select`, {
    method: 'POST',
  })
  return json<ChatMessage[]>(response)
}

export async function stopChatTurn(sessionId: number): Promise<{ stopped: boolean }> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/stop`, {
    method: 'POST',
  })
  return json<{ stopped: boolean }>(response)
}

export interface ChatBranchNode {
  id: number
  role: string
  excerpt: string
  parent_id: number | null
  children: number[]
  active_child_id: number | null
}

export interface ChatBranchTree {
  active_root_id: number | null
  nodes: ChatBranchNode[]
}

export async function getChatBranchTree(sessionId: number): Promise<ChatBranchTree> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/tree`)
  return json<ChatBranchTree>(response)
}

export async function approveChatProposal(proposalId: number): Promise<ChatProposal> {  const response = await apiFetch(`/api/v1/chat/proposals/${proposalId}/approve`, {
    method: 'POST',
  })
  return json<ChatProposal>(response)
}

export async function dismissChatProposal(proposalId: number): Promise<ChatProposal> {
  const response = await apiFetch(`/api/v1/chat/proposals/${proposalId}/dismiss`, {
    method: 'POST',
  })
  return json<ChatProposal>(response)
}

export type ChatAttachmentKind =
  | 'material'
  | 'note'
  | 'quiz'
  | 'exercise'
  | 'node'
  | 'course'

export interface ChatAttachmentInput {
  kind: ChatAttachmentKind
  id: number
}

export async function sendChatMessage(
  sessionId: number,
  content: string,
  attachments?: ChatAttachmentInput[]
): Promise<{ user_message: ChatMessage; job_id: number }> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content,
      ...(attachments !== undefined && attachments.length > 0 ? { attachments } : {}),
    }),
  })
  return json<{ user_message: ChatMessage; job_id: number }>(response)
}

export async function patchChatMessageState(
  messageId: number,
  delta: { op: 'add' | 'replace' | 'remove'; path: string; value?: unknown }[],
): Promise<{ state: Record<string, unknown> }> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/state`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ delta }),
  })
  return json<{ state: Record<string, unknown> }>(response)
}

export async function askAboutExerciseSession(
  sessionId: number,
  pendingAnswer: string | null = null
): Promise<{ chat_session_id: number; public_id: string }> {
  const response = await apiFetch(`/api/v1/exercises/sessions/${sessionId}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pending_answer: pendingAnswer }),
  })
  return json<{ chat_session_id: number; public_id: string }>(response)
}

export async function askAboutQuestion(
  attemptId: number,
  questionId: number
): Promise<{ chat_session_id: number; public_id: string }> {
  const response = await apiFetch(
    `/api/v1/quiz/attempts/${attemptId}/questions/${questionId}/ask`,
    { method: 'POST' }
  )
  return json<{ chat_session_id: number; public_id: string }>(response)
}

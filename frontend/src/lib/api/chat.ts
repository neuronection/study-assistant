import { json, apiFetch } from './client'
import type { BlockDto } from './materials'

export interface ChatSession {
  id: string
  public_id: string
  course_id: string | null
  node_id: string | null
  title: string
  use_embeddings: boolean | null
  quizme?: boolean
  quiz_pending?: {
    question?: string
    choices?: string[] | null
    answered?: boolean
    verdict?: 'correct' | 'incorrect' | null
    verdict_detail?: string | null
    student_answer?: string | null
  } | null
  created_at: string
}

export interface ChatCitation {
  index: number
  chunk_id: string
  material_id: string
  title: string
  quote: string
}

export type MentionKind = 'material' | 'note' | 'concept' | 'node' | 'quiz' | 'exercise'

export interface MentionRef {
  ref: string
  kind: MentionKind
  id: string
  title: string
  course_id?: string | null
  summary?: string | null
}

export interface ChatRead {
  ref: string
  kind: MentionKind
  id: string
  title: string
  course_id?: string | null
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
  quiz?: {
    question?: string
    choices?: string[] | null
    answered?: boolean
    verdict?: string | null
    verdict_detail?: string | null
    student_answer?: string | null
    expected_display?: string | null
  } | null
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
  session_id: string
  course_id: string | null
  node: { id: string; title: string } | null
  registry: MentionRef[]
  latest_notes: { id: string; title: string }[]
}

export interface ChatProposal {
  id: string
  action: string
  payload: Record<string, unknown>
  status: 'proposed' | 'approved' | 'dismissed' | 'executed' | 'stale' | 'conflict'
  result?:
    | {
        note_id?: string
        material_id?: string
        open_dialog?: Record<string, unknown>
        error?: string
        conflict?: string
      }
    | null
  message_id?: string | null
  session_id?: string | null
}

export interface ChatProposalList {
  proposals: ChatProposal[]
  next_cursor: string | null
}

export async function listChatProposals(
  status?: ChatProposal['status']
): Promise<ChatProposalList> {
  const params = new URLSearchParams()
  if (status !== undefined) params.set('status', status)
  const query = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/chat/proposals${query}`)
  return json<ChatProposalList>(response)
}

export interface ChatMessage {
  id: string
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
  parent_id?: string | null
  /** Persisted turn-failure marker (uniform chat error display). */
  state?: { turn_failed?: { code: string; detail: string } } | null
  variant_index?: number
  variant_count?: number
  sibling_ids?: string[]
}

export async function listChatSessions(nodeId?: string): Promise<ChatSession[]> {
  const params = nodeId !== undefined ? `?node_id=${nodeId}` : ''
  const response = await apiFetch(`/api/v1/chat/sessions${params}`)
  return json<ChatSession[]>(response)
}

export async function renameChatSession(sessionId: string, title: string): Promise<ChatSession> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return json<ChatSession>(response)
}

export async function updateChatSessionEmbeddings(
  sessionId: string,
  useEmbeddings: boolean
): Promise<ChatSession> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ use_embeddings: useEmbeddings }),
  })
  return json<ChatSession>(response)
}

export async function updateChatSessionQuizme(
  sessionId: string,
  quizme: boolean
): Promise<ChatSession> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quizme }),
  })
  return json<ChatSession>(response)
}

export interface QuizAnswerResult {
  correct: boolean
  verdict_detail: string
  expected_display: string | null
  user_message_id: string
  job_id: string | null
}

export async function answerQuizQuestion(
  sessionId: string,
  answer: string | number
): Promise<QuizAnswerResult> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/quiz-answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer }),
  })
  return json<QuizAnswerResult>(response)
}

export async function deleteChatSession(
  sessionId: string
): Promise<{ deleted_item_id: string }> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, {
    method: 'DELETE',
  })
  return json<{ deleted_item_id: string }>(response)
}

export async function createChatSession(
  courseId: string | null,
  nodeId?: string | null,
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

export async function listChatMessages(sessionId: string): Promise<ChatMessage[]> {
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

export async function getChatContext(sessionId: string): Promise<ChatContextData> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/context`)
  return json<ChatContextData>(response)
}

export async function editChatMessage(
  messageId: string,
  content: string,
): Promise<{ user_message: ChatMessage; job_id: string }> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/edit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  return json<{ user_message: ChatMessage; job_id: string }>(response)
}

export async function regenerateChatMessage(
  messageId: string,
): Promise<{ user_message: ChatMessage; job_id: string }> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/regenerate`, {
    method: 'POST',
  })
  return json<{ user_message: ChatMessage; job_id: string }>(response)
}

export async function selectChatVariant(messageId: string): Promise<ChatMessage[]> {
  const response = await apiFetch(`/api/v1/chat/messages/${messageId}/select`, {
    method: 'POST',
  })
  return json<ChatMessage[]>(response)
}

export async function stopChatTurn(sessionId: string): Promise<{ stopped: boolean }> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/stop`, {
    method: 'POST',
  })
  return json<{ stopped: boolean }>(response)
}

export interface ChatBranchNode {
  id: string
  role: string
  excerpt: string
  parent_id: string | null
  children: number[]
  active_child_id: string | null
}

export interface ChatBranchTree {
  active_root_id: string | null
  nodes: ChatBranchNode[]
}

export async function getChatBranchTree(sessionId: string): Promise<ChatBranchTree> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/tree`)
  return json<ChatBranchTree>(response)
}

export async function approveChatProposal(proposalId: string): Promise<ChatProposal> {  const response = await apiFetch(`/api/v1/chat/proposals/${proposalId}/approve`, {
    method: 'POST',
  })
  return json<ChatProposal>(response)
}

export async function dismissChatProposal(proposalId: string): Promise<ChatProposal> {
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
  id: string
}

export async function sendChatMessage(
  sessionId: string,
  content: string,
  attachments?: ChatAttachmentInput[]
): Promise<{ user_message: ChatMessage; job_id: string }> {
  const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content,
      ...(attachments !== undefined && attachments.length > 0 ? { attachments } : {}),
    }),
  })
  return json<{ user_message: ChatMessage; job_id: string }>(response)
}

export async function patchChatMessageState(
  messageId: string,
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
  sessionId: string,
  pendingAnswer: string | null = null
): Promise<{ chat_session_id: string; public_id: string }> {
  const response = await apiFetch(`/api/v1/exercises/sessions/${sessionId}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pending_answer: pendingAnswer }),
  })
  return json<{ chat_session_id: string; public_id: string }>(response)
}

export async function askAboutQuestion(
  attemptId: string,
  questionId: string
): Promise<{ chat_session_id: string; public_id: string }> {
  const response = await apiFetch(
    `/api/v1/quiz/attempts/${attemptId}/questions/${questionId}/ask`,
    { method: 'POST' }
  )
  return json<{ chat_session_id: string; public_id: string }>(response)
}

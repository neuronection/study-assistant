import type { components } from '@/lib/api-schema'

import { json, apiFetch } from './client'

type Schemas = components['schemas']

export type ChatSession = Schemas['app__api__chat__SessionOut']
export type ChatCitation = Schemas['CitationOut']
export type MentionRef = Schemas['MentionRefOut']
export type MentionKind = Schemas['MentionRefOut']['kind']
export type ChatRead = Schemas['ReadOut']
export type ChatToolCall = Schemas['ToolCallOut']
export type ChatTraceRound = Schemas['ChatTraceRound']
export type ChatTrace = Schemas['ChatTrace']
export type ChatContextData = Schemas['SessionContextOut']
export type ChatProposal = Schemas['ProposalOut']
export type ChatProposalList = Schemas['ProposalListOut']
export type ChatMessage = Schemas['MessageOut']
export type QuizAnswerResult = Schemas['QuizAnswerOut']
export type ChatBranchNode = Schemas['BranchNodeOut']
export type ChatBranchTree = Schemas['BranchTreeOut']
export type ChatAttachmentKind = Schemas['AttachmentIn']['kind']
export type ChatAttachmentInput = Schemas['AttachmentIn']

export async function listChatProposals(
  status?: ChatProposal['status']
): Promise<ChatProposalList> {
  const params = new URLSearchParams()
  if (status !== undefined) params.set('status', status)
  const query = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/chat/proposals${query}`)
  return json<ChatProposalList>(response)
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

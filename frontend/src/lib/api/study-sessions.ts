import type { components } from '@/lib/api-schema'

import { json, apiFetch } from './client'

type Schemas = components['schemas']

export type StudySessionKind = Schemas['StudySessionKind']
export type StudySessionSource = Schemas['StudySessionSource']
export type StudySessionInfo = Schemas['StudySessionOut']
export type StudySessionDay = Schemas['StudySessionDayOut']
export type StudySessionSummary = Schemas['StudySessionSummaryOut']

export async function startStudySession(body: {
  kind: StudySessionKind
  source?: StudySessionSource
  course_id?: string | null
  node_id?: string | null
  entity_ref?: string | null
}): Promise<StudySessionInfo> {
  const response = await apiFetch('/api/v1/study-sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<StudySessionInfo>(response)
}

export async function beatStudySession(
  sessionId: string,
  action: 'heartbeat' | 'end'
): Promise<StudySessionInfo> {
  const response = await apiFetch(`/api/v1/study-sessions/${sessionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  return json<StudySessionInfo>(response)
}

export async function getStudySessionSummary(days = 7): Promise<StudySessionSummary> {
  const response = await apiFetch(`/api/v1/study-sessions/summary?days=${days}`)
  return json<StudySessionSummary>(response)
}

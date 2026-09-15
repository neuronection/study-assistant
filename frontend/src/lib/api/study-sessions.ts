import { json, apiFetch } from './client'

export type StudySessionKind = 'focus' | 'quiz' | 'exercise' | 'review' | 'read' | 'note'
export type StudySessionSource = 'timer' | 'auto' | 'manual'

export interface StudySessionInfo {
  id: number
  kind: StudySessionKind
  source: StudySessionSource
  course_id: number | null
  node_id: number | null
  entity_ref: string | null
  started_at: string
  ended_at: string | null
  duration_sec: number
}

export interface StudySessionDay {
  day: string
  total_sec: number
  by_kind: Record<string, number>
}

export interface StudySessionSummary {
  days: StudySessionDay[]
  today_sec: number
  week_sec: number
}

export async function startStudySession(body: {
  kind: StudySessionKind
  source?: StudySessionSource
  course_id?: number | null
  node_id?: number | null
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
  sessionId: number,
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

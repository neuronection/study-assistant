import { json, apiFetch } from './client'
import type { BlockDto } from './materials'
import type { GenerateContext } from './ai'
import type { HintResult } from './exercises'

export interface QuizQuestionCell {
  kind: string
  text?: string
}

export interface QuizQuestionPart {
  type: string
}

export interface QuizQuestionTest {
  call: string
  expected?: unknown
  expected_stdout?: string | null
}

export interface QuizQuestionInput {
  widget: string
  min?: number
  max?: number
  headers?: string[]
  row_labels?: string[]
  cells?: QuizQuestionCell[][]
  parts?: QuizQuestionPart[]
  starter_code?: string
  tests?: QuizQuestionTest[]
  mode?: string
}

export interface QuizQuestion {
  id: string
  type: string
  stem: BlockDto[]
  options: BlockDto[] | null
  difficulty: number | null
  bloom: string | null
  skill: string | null
  expected_time_sec: number | null
  flag: string
  input: QuizQuestionInput | null
}

export interface QuizActivity {
  id: string
  title: string
  type: string
  course_id: string | null
  node_id: string | null
  question_count: number
  time_limit_sec: number | null
}

export async function generateQuiz(body: {
  course_id: string
  node_id?: string | null
  concept_id?: string | null
  count?: number
  difficulty?: number | null
  topic?: string | null
  skill?: string | null
  question_types?: string[]
  shuffle?: boolean
  time_limit_sec?: number | null
} & GenerateContext): Promise<QuizActivity> {
  const response = await apiFetch('/api/v1/quiz/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<QuizActivity>(response)
}

export async function listQuizzes(
  courseId?: string,
  nodeId?: string,
  includeChildren = true
): Promise<QuizActivity[]> {
  const params = new URLSearchParams()
  if (courseId !== undefined) {
    params.set('course_id', String(courseId))
  }
  if (nodeId !== undefined) {
    params.set('node_id', String(nodeId))
    params.set('include_children', String(includeChildren))
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/quiz/activities${suffix}`)
  return json<QuizActivity[]>(response)
}

export async function quizQuestions(activityId: string): Promise<QuizQuestion[]> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}/questions`)
  return json<QuizQuestion[]>(response)
}

export interface QuizAnswerKeyEntry {
  question_id: string
  type: string
  key: string
}

export async function quizAnswerKey(activityId: string): Promise<QuizAnswerKeyEntry[]> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}/answer-key`)
  return json<QuizAnswerKeyEntry[]>(response)
}

export async function getQuiz(activityId: string): Promise<QuizActivity> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}`)
  return json<QuizActivity>(response)
}

export async function renameQuiz(activityId: string, title: string): Promise<QuizActivity> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return json<QuizActivity>(response)
}

export async function moveQuiz(
  activityId: string,
  nodeId: string | null
): Promise<QuizActivity> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  })
  return json<QuizActivity>(response)
}

export async function deleteQuiz(
  activityId: string
): Promise<{ deleted_item_id: string }> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}`, {
    method: 'DELETE',
  })
  return json<{ deleted_item_id: string }>(response)
}

export interface QuizAttempt {
  id: string
  activity_id: string
  mode: string
  started_at: string
  deadline_at: string | null
  finished_at: string | null
  score: number | null
}

export async function setQuizTimeLimit(
  activityId: string,
  timeLimitSec: number | null
): Promise<QuizActivity> {
  const response = await apiFetch(
    `/api/v1/quiz/activities/${activityId}/time-limit`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ time_limit_sec: timeLimitSec }),
    }
  )
  return json<QuizActivity>(response)
}

export async function startQuizAttempt(activityId: string, mode = 'practice'): Promise<QuizAttempt> {
  const response = await apiFetch(
    `/api/v1/quiz/activities/${activityId}/attempts?mode=${mode}`,
    { method: 'POST' }
  )
  return json<QuizAttempt>(response)
}

export interface QuizFeedback {
  correct: boolean
  partial_credit: number
  graded_by: string | null
  feedback: BlockDto[]
  error_tags: string[]
  explanation: BlockDto[]
}

export async function submitQuizAnswer(
  attemptId: string,
  questionId: string,
  response: unknown,
  timeMs?: number,
  inputMode?: string,
  strokes?: unknown[]
): Promise<QuizFeedback> {
  const apiResponse = await apiFetch(`/api/v1/quiz/attempts/${attemptId}/answers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question_id: questionId,
      response,
      time_ms: timeMs,
      input_mode: inputMode,
      strokes,
    }),
  })
  return json<QuizFeedback>(apiResponse)
}

export async function finishQuizAttempt(attemptId: string): Promise<QuizAttempt> {
  const response = await apiFetch(`/api/v1/quiz/attempts/${attemptId}/finish`, { method: 'POST' })
  return json<QuizAttempt>(response)
}

export interface QuizAttemptRow {
  id: string
  activity_id: string
  title: string
  mode: string
  started_at: string
  finished_at: string | null
  score: number | null
}

export async function listQuizAttempts(courseId?: string): Promise<QuizAttemptRow[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/quiz/attempts${params}`)
  return json<QuizAttemptRow[]>(response)
}

export interface MistakeRow {
  id: string
  question_id: string
  activity_id: string
  activity_title: string
  stem_excerpt: string
  error_tags: string[]
  created_at: string
}

export async function listMistakes(courseId?: string): Promise<MistakeRow[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/quiz/mistakes${params}`)
  return json<MistakeRow[]>(response)
}

export function quizExportUrl(activityId: string): string {
  return `/api/v1/quiz/activities/${activityId}/export`
}

export interface ImportValidation {
  index: number
  ok: boolean
  problems: string[]
}

export interface ImportResult {
  dry_run: boolean
  results: ImportValidation[]
  valid: number
  total: number
  activity?: QuizActivity
}

export async function importQuiz(
  document: { title?: string; questions: unknown[] },
  dryRun: boolean,
  courseId: string
): Promise<ImportResult> {
  const params = new URLSearchParams({ dry_run: String(dryRun), course_id: String(courseId) })
  const response = await apiFetch(`/api/v1/quiz/import?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(document),
  })
  return json<ImportResult>(response)
}

export async function requestQuizHint(
  attemptId: string,
  questionId: string,
  level: number,
  lastResponse: unknown = null
): Promise<HintResult> {
  const response = await apiFetch(
    `/api/v1/quiz/attempts/${attemptId}/questions/${questionId}/hint`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level, last_response: lastResponse }),
    }
  )
  return json<HintResult>(response)
}

export interface RecognitionResult {
  markdown: string
  latex_candidates: string[]
}

export async function recognizeHandwriting(pngBase64: string): Promise<RecognitionResult> {
  const response = await apiFetch('/api/v1/quiz/recognize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ png_base64: pngBase64 }),
  })
  return json<RecognitionResult>(response)
}

export function qpkgExportUrl(activityId: string): string {
  return `/api/v1/quiz/activities/${activityId}/export-qpkg`
}

export async function importQpkg(
  file: File,
  dryRun: boolean,
  courseId: string
): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ dry_run: String(dryRun), course_id: String(courseId) })
  const response = await apiFetch(`/api/v1/quiz/import-qpkg?${params.toString()}`, {
    method: 'POST',
    body: form,
  })
  return json<ImportResult>(response)
}

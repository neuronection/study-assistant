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

export interface QuizQuestionInput {
  widget: string
  min?: number
  max?: number
  headers?: string[]
  row_labels?: string[]
  cells?: QuizQuestionCell[][]
  parts?: QuizQuestionPart[]
}

export interface QuizQuestion {
  id: number
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
  id: number
  title: string
  type: string
  course_id: number | null
  node_id: number | null
  question_count: number
}

export async function generateQuiz(body: {
  course_id: number
  node_id?: number | null
  concept_id?: number | null
  count?: number
  difficulty?: number | null
  topic?: string | null
  skill?: string | null
  question_types?: string[]
  shuffle?: boolean
} & GenerateContext): Promise<QuizActivity> {
  const response = await apiFetch('/api/v1/quiz/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<QuizActivity>(response)
}

export async function listQuizzes(
  courseId?: number,
  nodeId?: number,
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

export async function quizQuestions(activityId: number): Promise<QuizQuestion[]> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}/questions`)
  return json<QuizQuestion[]>(response)
}

export async function getQuiz(activityId: number): Promise<QuizActivity> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}`)
  return json<QuizActivity>(response)
}

export async function renameQuiz(activityId: number, title: string): Promise<QuizActivity> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return json<QuizActivity>(response)
}

export async function moveQuiz(
  activityId: number,
  nodeId: number | null
): Promise<QuizActivity> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  })
  return json<QuizActivity>(response)
}

export async function deleteQuiz(
  activityId: number
): Promise<{ deleted_item_id: number }> {
  const response = await apiFetch(`/api/v1/quiz/activities/${activityId}`, {
    method: 'DELETE',
  })
  return json<{ deleted_item_id: number }>(response)
}

export interface QuizAttempt {
  id: number
  activity_id: number
  mode: string
  started_at: string
  finished_at: string | null
  score: number | null
}

export async function startQuizAttempt(activityId: number, mode = 'practice'): Promise<QuizAttempt> {
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
  attemptId: number,
  questionId: number,
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

export async function finishQuizAttempt(attemptId: number): Promise<QuizAttempt> {
  const response = await apiFetch(`/api/v1/quiz/attempts/${attemptId}/finish`, { method: 'POST' })
  return json<QuizAttempt>(response)
}

export interface QuizAttemptRow {
  id: number
  activity_id: number
  title: string
  mode: string
  started_at: string
  finished_at: string | null
  score: number | null
}

export async function listQuizAttempts(courseId?: number): Promise<QuizAttemptRow[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/quiz/attempts${params}`)
  return json<QuizAttemptRow[]>(response)
}

export interface MistakeRow {
  id: number
  question_id: number
  activity_id: number
  activity_title: string
  stem_excerpt: string
  error_tags: string[]
  created_at: string
}

export async function listMistakes(courseId?: number): Promise<MistakeRow[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/quiz/mistakes${params}`)
  return json<MistakeRow[]>(response)
}

export function quizExportUrl(activityId: number): string {
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
  courseId: number
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
  attemptId: number,
  questionId: number,
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

export function qpkgExportUrl(activityId: number): string {
  return `/api/v1/quiz/activities/${activityId}/export-qpkg`
}

export async function importQpkg(
  file: File,
  dryRun: boolean,
  courseId: number
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

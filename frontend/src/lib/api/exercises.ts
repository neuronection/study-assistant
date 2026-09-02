import { json, apiFetch } from './client'
import type { BlockDto } from './materials'
import type { GenerateContext } from './ai'

export interface ExerciseInfo {
  id: number
  title: string
  course_id: number | null
  node_id: number | null
  difficulty: number | null
  step_count: number
}

export interface ExerciseStepInput {
  widget:
    | 'matching'
    | 'ordering'
    | 'categorize'
    | 'fill_blank'
    | 'math'
    | 'essay'
    | 'lines'
    | 'numberline'
  kind?: string
  lefts?: string[]
  rights?: { index: number; label: string }[]
  items?: unknown[]
  categories?: string[]
  prompt_md?: string
  blank_count?: number
  lines?: string[]
  requires_fix?: boolean
  min?: number
  max?: number
}

export interface ExerciseStepInfo {
  id: number
  order_idx: number
  prompt: BlockDto[]
  has_expected: boolean
  kind: string | null
  input: ExerciseStepInput | null
}

export interface ExerciseSessionInfo {
  id: number
  exercise_id: number
  current_step_idx: number
  status: string
  socratic: boolean
  independence_score: number | null
}

export async function listExercises(
  courseId?: number,
  nodeId?: number,
  includeChildren = true
): Promise<ExerciseInfo[]> {
  const params = new URLSearchParams()
  if (courseId !== undefined) {
    params.set('course_id', String(courseId))
  }
  if (nodeId !== undefined) {
    params.set('node_id', String(nodeId))
    params.set('include_children', String(includeChildren))
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : ''
  const response = await apiFetch(`/api/v1/exercises${suffix}`)
  return json<ExerciseInfo[]>(response)
}

export async function createExercise(body: {
  course_id: number
  node_id?: number | null
  title: string
  steps: { prompt_md: string; expected?: { value: string } | null }[]
}): Promise<ExerciseInfo> {
  const response = await apiFetch('/api/v1/exercises', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ExerciseInfo>(response)
}

export async function getExercise(exerciseId: number): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}`)
  return json<ExerciseInfo>(response)
}

export async function renameExercise(
  exerciseId: number,
  title: string
): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  return json<ExerciseInfo>(response)
}

export async function moveExercise(
  exerciseId: number,
  nodeId: number | null
): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  })
  return json<ExerciseInfo>(response)
}

export async function deleteExercise(
  exerciseId: number
): Promise<{ deleted_item_id: number }> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}`, { method: 'DELETE' })
  return json<{ deleted_item_id: number }>(response)
}

export async function exerciseSteps(exerciseId: number): Promise<ExerciseStepInfo[]> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}/steps`)
  return json<ExerciseStepInfo[]>(response)
}

export async function startExerciseSession(
  exerciseId: number,
  socratic = false
): Promise<ExerciseSessionInfo> {
  const response = await apiFetch(
    `/api/v1/exercises/${exerciseId}/sessions?socratic=${socratic}`,
    { method: 'POST' }
  )
  return json<ExerciseSessionInfo>(response)
}

export interface StepCheck {
  correct: boolean
  stage: string
  error_class: string
  advanced: boolean
  session: ExerciseSessionInfo
}

export async function submitStepAnswer(
  sessionId: number,
  response: unknown,
  state?: Record<string, unknown> | null,
): Promise<StepCheck> {
  const apiResponse = await apiFetch(`/api/v1/exercises/sessions/${sessionId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ response, state }),
  })
  return json<StepCheck>(apiResponse)
}

export interface HintResult {
  level: number
  markdown: string
  violations: string | null
}

export async function requestHint(
  sessionId: number,
  level: number,
  lastResponse: string | null = null
): Promise<HintResult> {
  const response = await apiFetch(`/api/v1/exercises/sessions/${sessionId}/hint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level, last_response: lastResponse }),
  })
  return json<HintResult>(response)
}

export async function generateExercise(body: {
  course_id: number
  node_id?: number | null
  topic?: string | null
  difficulty?: number | null
  step_count?: number
  kind?: string
} & GenerateContext): Promise<ExerciseInfo> {
  const response = await apiFetch('/api/v1/exercises/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ExerciseInfo>(response)
}

export async function similarExercise(exerciseId: number): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}/similar`, { method: 'POST' })
  return json<ExerciseInfo>(response)
}

export interface DrillPattern {
  pattern: string
  name: string
  description: string
  example?: string | null
  source: 'seeded' | 'discovered'
  occurrences: number
  spotted?: number
}

export interface PatternProposal {
  key: string
  name: string
  description: string
  example?: string | null
}

export async function drillPatterns(courseId: number): Promise<DrillPattern[]> {
  const response = await apiFetch(
    `/api/v1/exercises/drills/patterns?course_id=${encodeURIComponent(courseId)}`
  )
  return json<DrillPattern[]>(response)
}

export async function proposePatterns(courseId: number): Promise<PatternProposal[]> {
  const response = await apiFetch('/api/v1/exercises/drills/propose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId }),
  })
  return json<PatternProposal[]>(response)
}

export async function createPattern(
  courseId: number,
  proposal: PatternProposal
): Promise<DrillPattern> {
  const response = await apiFetch('/api/v1/exercises/drills/patterns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, ...proposal }),
  })
  return json<DrillPattern>(response)
}

export async function startDrill(pattern: string, courseId: number): Promise<ExerciseInfo> {
  const response = await apiFetch('/api/v1/exercises/drills', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern, course_id: courseId }),
  })
  return json<ExerciseInfo>(response)
}

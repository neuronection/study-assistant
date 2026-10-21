import type { components } from '@/lib/api-schema'

import { json, apiFetch } from './client'
import type { GenerateContext } from './ai'
import type { ExerciseStepInput } from './hand-types'

type Schemas = components['schemas']

export type { ExerciseStepInput } from './hand-types'
export type ExerciseInfo = Schemas['ExerciseOut']
export type ExerciseStepInfo = Omit<Schemas['StepOut'], 'input'> & {
  input?: ExerciseStepInput | null
}
export type ExerciseSessionInfo = Schemas['app__api__exercises__SessionOut']
export type StepCheck = Schemas['CheckOut']
export type HintResult = Schemas['HintOut']
export type DrillPattern = Schemas['PatternOut']
export type PatternProposal = Schemas['PatternProposalOut']

export async function listExercises(
  courseId?: string,
  nodeId?: string,
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
  course_id: string
  node_id?: string | null
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

export async function createTeachBack(body: {
  course_id: string
  node_id?: string | null
  concept?: string | null
  concept_id?: string | null
}): Promise<ExerciseInfo> {
  const response = await apiFetch('/api/v1/exercises/teach-back', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<ExerciseInfo>(response)
}

export async function getExercise(exerciseId: string): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}`)
  return json<ExerciseInfo>(response)
}

export async function renameExercise(
  exerciseId: string,
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
  exerciseId: string,
  nodeId: string | null
): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}/move`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  })
  return json<ExerciseInfo>(response)
}

export async function deleteExercise(
  exerciseId: string
): Promise<{ deleted_item_id: string }> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}`, { method: 'DELETE' })
  return json<{ deleted_item_id: string }>(response)
}

export async function exerciseSteps(exerciseId: string): Promise<ExerciseStepInfo[]> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}/steps`)
  return json<ExerciseStepInfo[]>(response)
}

export async function startExerciseSession(
  exerciseId: string,
  socratic = false
): Promise<ExerciseSessionInfo> {
  const response = await apiFetch(
    `/api/v1/exercises/${exerciseId}/sessions?socratic=${socratic}`,
    { method: 'POST' }
  )
  return json<ExerciseSessionInfo>(response)
}

export async function submitStepAnswer(
  sessionId: string,
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

export async function requestHint(
  sessionId: string,
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
  course_id: string
  node_id?: string | null
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

export async function similarExercise(exerciseId: string): Promise<ExerciseInfo> {
  const response = await apiFetch(`/api/v1/exercises/${exerciseId}/similar`, { method: 'POST' })
  return json<ExerciseInfo>(response)
}

export async function drillPatterns(courseId: string): Promise<DrillPattern[]> {
  const response = await apiFetch(
    `/api/v1/exercises/drills/patterns?course_id=${encodeURIComponent(courseId)}`
  )
  return json<DrillPattern[]>(response)
}

export async function proposePatterns(courseId: string): Promise<PatternProposal[]> {
  const response = await apiFetch('/api/v1/exercises/drills/propose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId }),
  })
  return json<PatternProposal[]>(response)
}

export async function createPattern(
  courseId: string,
  proposal: PatternProposal
): Promise<DrillPattern> {
  const response = await apiFetch('/api/v1/exercises/drills/patterns', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: courseId, ...proposal }),
  })
  return json<DrillPattern>(response)
}

export async function startDrill(pattern: string, courseId: string): Promise<ExerciseInfo> {
  const response = await apiFetch('/api/v1/exercises/drills', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern, course_id: courseId }),
  })
  return json<ExerciseInfo>(response)
}

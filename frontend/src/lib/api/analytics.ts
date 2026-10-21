import type { components } from '@/lib/api-schema'

import { json, apiFetch } from './client'

type Schemas = components['schemas']

export type ExamStatusEntry = Schemas['ExamStatusOut']
export type MatrixCell = Schemas['WeaknessCellOut']
export type ErrorTagProfile = Schemas['ErrorTagStatOut']
export type SpeedAccuracyEntry = Schemas['SpeedAccuracyCellOut']
export type Diagnostics = Schemas['DiagnosticsOut']
export type Recommendation = Schemas['RecommendationOut']
export type DailyEntry = Schemas['DayActivityOut']
export type GoalUnit = Schemas['GoalUnit']
export type Overview = Schemas['OverviewOut']
export type DailyGoal = Schemas['GoalOut']
export type TaskCost = Schemas['CostTaskOut']
export type CostsSummary = Schemas['CostsOut']

export async function getExamStatus(): Promise<ExamStatusEntry[]> {
  const response = await apiFetch('/api/v1/analytics/exams')
  return json<ExamStatusEntry[]>(response)
}

export async function getDiagnostics(courseId?: string): Promise<Diagnostics> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/analytics/diagnostics${params}`)
  return json<Diagnostics>(response)
}

export async function getRecommendations(courseId?: string): Promise<Recommendation[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/analytics/recommendations${params}`)
  return json<Recommendation[]>(response)
}

export async function getOverview(): Promise<Overview> {
  const response = await apiFetch('/api/v1/analytics/overview')
  return json<Overview>(response)
}

export async function setDailyGoal(body: {
  unit?: GoalUnit
  answers_per_day?: number
  minutes_per_day?: number
}): Promise<DailyGoal> {
  const response = await apiFetch('/api/v1/analytics/goal', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<DailyGoal>(response)
}

export async function getCosts(): Promise<CostsSummary> {
  const response = await apiFetch('/api/v1/analytics/costs')
  return json<CostsSummary>(response)
}

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
export type ItemStat = Schemas['ItemStatOut']
export type AnalyticsExport = Schemas['AnalyticsExportOut']
export type RetentionReport = Schemas['RetentionOut']
export type WorkloadReport = Schemas['WorkloadOut']
export type PriceOverride = Schemas['PriceOverrideOut']
export type PriceOverrideInput = Schemas['PriceOverrideIn']
export type PricesResponse = Schemas['PricesOut']
export type EffectivePrice = Schemas['EffectivePriceOut']
export type CostCall = Schemas['CostCallOut']

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

export async function getItems(courseId?: string): Promise<ItemStat[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/analytics/items${params}`)
  return json<ItemStat[]>(response)
}

export function analyticsExportUrl(
  format: 'csv' | 'json',
  courseId?: string
): string {
  const params = new URLSearchParams({ format })
  if (courseId !== undefined) {
    params.set('course_id', courseId)
  }
  return `/api/v1/analytics/export?${params.toString()}`
}

export async function getCosts(): Promise<CostsSummary> {
  const response = await apiFetch('/api/v1/analytics/costs')
  return json<CostsSummary>(response)
}

export async function getPrices(): Promise<PricesResponse> {
  const response = await apiFetch('/api/v1/ai/prices')
  return json<PricesResponse>(response)
}

export async function savePrice(body: PriceOverrideInput): Promise<PriceOverride> {
  const response = await apiFetch('/api/v1/ai/prices', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider_key: body.provider_key ?? null,
      provider_ref: body.provider_ref ?? null,
      model: body.model,
      match: body.match,
      input_micros_per_million: body.input_micros_per_million,
      output_micros_per_million: body.output_micros_per_million,
      metering: body.metering,
    }),
  })
  return json<PriceOverride>(response)
}

export async function deletePrice(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/ai/prices/${id}`, { method: 'DELETE' })
  if (!response.ok) {
    throw new Error(`Could not delete price (${response.status})`)
  }
}


export async function getRetention(days = 90): Promise<RetentionReport> {
  const response = await apiFetch(`/api/v1/analytics/retention?days=${days}`)
  return json<RetentionReport>(response)
}

export async function getWorkload(days = 30): Promise<WorkloadReport> {
  const response = await apiFetch(`/api/v1/analytics/workload?days=${days}`)
  return json<WorkloadReport>(response)
}

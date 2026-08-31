import { json, apiFetch } from './client'

export interface ExamStatusEntry {
  course_id: number
  course_title: string
  exam_date: string
  days_left: number
  total_nodes: number
  engaged_nodes: number
  remaining_nodes: number
  nodes_per_day: number | null
  on_track: boolean
  most_behind_node: { id: number; title: string } | null
}

export async function getExamStatus(): Promise<ExamStatusEntry[]> {
  const response = await apiFetch('/api/v1/analytics/exams')
  return json<ExamStatusEntry[]>(response)
}

export interface MatrixCell {
  concept: string
  skill: string
  n: number
  accuracy: number
  avg_time_ratio: number | null
  last_seen_at: string
  weakness_score: number
  enough_data: boolean
}

export interface ErrorTagProfile {
  tag: string
  total: number
  recent_7d: number
  previous_7d: number
  trend: number
  last_seen_at: string
}

export interface SpeedAccuracyEntry {
  concept: string
  n: number
  accuracy: number
  avg_time_ratio: number
  speed: string
  quadrant: string
}

export interface Diagnostics {
  weakness_matrix: MatrixCell[]
  error_profile: ErrorTagProfile[]
  speed_accuracy: SpeedAccuracyEntry[]
  skills: string[]
}

export async function getDiagnostics(courseId?: number): Promise<Diagnostics> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/analytics/diagnostics${params}`)
  return json<Diagnostics>(response)
}

export interface Recommendation {
  kind: 'read' | 'drill' | 'review' | 'challenge'
  priority: number
  title_key?: string
  concept: string | null
  skill: string | null
  evidence: {
    misses?: number
    n?: number
    accuracy?: number
    due_cards?: number
    last_seen_at?: string
  }
}

export async function getRecommendations(courseId?: number): Promise<Recommendation[]> {
  const params = courseId !== undefined ? `?course_id=${courseId}` : ''
  const response = await apiFetch(`/api/v1/analytics/recommendations${params}`)
  return json<Recommendation[]>(response)
}

export interface DailyEntry {
  day: string
  answers_n: number
  correct_n: number
  cards_reviewed: number
  minutes: number
  xp: number
}

export interface Overview {
  today: DailyEntry
  goal: number
  streak: number
  total_xp: number
  level: number
  due_cards: number
  history: DailyEntry[]
}

export async function getOverview(): Promise<Overview> {
  const response = await apiFetch('/api/v1/analytics/overview')
  return json<Overview>(response)
}

export async function setDailyGoal(answersPerDay: number): Promise<{ answers_per_day: number }> {
  const response = await apiFetch('/api/v1/analytics/goal', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answers_per_day: answersPerDay }),
  })
  return json<{ answers_per_day: number }>(response)
}

export interface TaskCost {
  task: string
  calls: number
  tokens_in: number
  tokens_out: number
  cost_usd: number
  models: Record<string, number>
  monthly_cap_usd: number | null
}

export interface CostsSummary {
  month: string
  per_task: TaskCost[]
  total_usd: number
}

export async function getCosts(): Promise<CostsSummary> {
  const response = await apiFetch('/api/v1/analytics/costs')
  return json<CostsSummary>(response)
}

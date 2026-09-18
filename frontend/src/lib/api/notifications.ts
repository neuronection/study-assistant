import { json, apiFetch } from './client'

export interface DueReviewEntry {
  card_id: number
  kind: string
  course_id: number
  course_title: string
}

export interface PlanEntry {
  item_id: number
  title: string
  kind: string
  course_id: number
  course_title: string
  due_date: string
  overdue: boolean
}

export interface ExamEntry {
  course_id: number
  course_title: string
  exam_date: string
  days_left: number
}

export interface Notifications {
  due_cards: number
  due_reviews: DueReviewEntry[]
  plan_today: PlanEntry[]
  plan_overdue_count: number
  exams: ExamEntry[]
  pending_proposals: number
  generated_at: string
}

export async function getNotifications(): Promise<Notifications> {
  const response = await apiFetch('/api/v1/notifications')
  return json<Notifications>(response)
}

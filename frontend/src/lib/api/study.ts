import { apiFetch, json } from './client'

export interface StudyPlanRow {
  item_id: string
  title: string
  course_id: string
  course_title: string
  due_date: string
  overdue: boolean
}

export interface StudyWeakCell {
  course_id: string
  course_title: string
  concept: string
  skill: string
  n: number
  accuracy: number
  weakness_score: number
}

export interface StudyNext {
  due_cards: number
  review_courses: string[]
  plan_rows: StudyPlanRow[]
  weak_cells: StudyWeakCell[]
  goal_unit: 'answers' | 'minutes'
  goal_done: number
  goal_target: number
  streak: number
}

export async function getStudyNext(courseId?: string): Promise<StudyNext> {
  const query = courseId !== undefined ? `?course=${courseId}` : ''
  const response = await apiFetch(`/api/v1/study/next${query}`)
  return json<StudyNext>(response)
}

import { json, apiFetch } from './client'
import type { FlashcardInfo } from './flashcards'

export interface DueCourseGroup {
  course_id: number
  course_title: string
  course_color: string | null
  due_count: number
  cards: FlashcardInfo[]
}

export interface ReviewDue {
  total_due: number
  groups: DueCourseGroup[]
}

export async function getReviewDue(perCourse = 20): Promise<ReviewDue> {
  const response = await apiFetch(`/api/v1/review/due?per_course=${perCourse}`)
  return json<ReviewDue>(response)
}

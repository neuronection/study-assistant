import type { components } from '@/lib/api-schema'

import { apiFetch, json } from './client'

type Schemas = components['schemas']

export type StudyPlanRow = Schemas['StudyPlanRowOut']
export type StudyWeakCell = Schemas['StudyWeakCellOut']
export type StudyNext = Schemas['StudyNextOut']

export async function getStudyNext(courseId?: string): Promise<StudyNext> {
  const query = courseId !== undefined ? `?course=${courseId}` : ''
  const response = await apiFetch(`/api/v1/study/next${query}`)
  return json<StudyNext>(response)
}

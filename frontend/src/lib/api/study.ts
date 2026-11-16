import type { components } from '@/lib/api-schema'

import { apiFetch, json } from './client'

type Schemas = components['schemas']

export type StudyPlanRow = Schemas['StudyPlanRowOut']
export type StudyWeakCell = Schemas['StudyWeakCellOut']
export type StudyNext = Schemas['StudyNextOut']
export type FsrsSettings = Schemas['FsrsSettingsOut']
export type FsrsSettingsInput = Schemas['FsrsSettingsIn']

export async function getStudyNext(courseId?: string): Promise<StudyNext> {
  const query = courseId !== undefined ? `?course=${courseId}` : ''
  const response = await apiFetch(`/api/v1/study/next${query}`)
  return json<StudyNext>(response)
}


export async function getFsrsSettings(): Promise<FsrsSettings> {
  const response = await apiFetch('/api/v1/study/fsrs')
  return json<FsrsSettings>(response)
}

export async function updateFsrsSettings(body: FsrsSettingsInput): Promise<FsrsSettings> {
  const response = await apiFetch('/api/v1/study/fsrs', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<FsrsSettings>(response)
}

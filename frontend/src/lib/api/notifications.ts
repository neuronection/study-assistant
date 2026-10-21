import type { components } from '@/lib/api-schema'

import { json, apiFetch } from './client'

type Schemas = components['schemas']

export type DueReviewEntry = Schemas['DueReviewEntryOut']
export type PlanEntry = Schemas['PlanEntryOut']
export type ExamEntry = Schemas['ExamEntryOut']
export type Notifications = Schemas['NotificationsOut']

export async function getNotifications(): Promise<Notifications> {
  const response = await apiFetch('/api/v1/notifications')
  return json<Notifications>(response)
}

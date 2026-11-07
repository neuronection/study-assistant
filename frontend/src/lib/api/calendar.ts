import type { components } from '@/lib/api-schema'
import { apiFetch, json } from './client'

// Cloud-calendar API (ADR-0052 / plan 52). Every provider, scope string,
// destination and setup field comes from the backend catalog — nothing here
// is hand-curated, and the bind form renders from `setup_fields` (Rev 4).
type Schemas = components['schemas']

export type CalendarProvider = Schemas['CalendarProviderOut']
export type CalendarCatalog = Schemas['CalendarCatalogOut']
export type CalendarLink = Schemas['CalendarLinkOut']
export type CalendarLinkInput = Schemas['CalendarLinkIn']
export type CalendarSyncReport = Schemas['SyncReportOut']
export type CalendarOAuthStart = Schemas['OAuthStartOut']
export type CalendarSetupField = Schemas['SetupFieldOut']
export type DiscoveredCalendar = Schemas['CalendarDiscoveredOut']
export type CalendarDiscoverInput = Schemas['CalendarDiscoverIn']

export async function listCalendarProviders(): Promise<CalendarCatalog> {
  const response = await apiFetch('/api/v1/calendar/providers')
  return json<CalendarCatalog>(response)
}

export async function listCalendarLinks(courseId?: string): Promise<CalendarLink[]> {
  const query = courseId ? `?course_id=${encodeURIComponent(courseId)}` : ''
  const response = await apiFetch(`/api/v1/calendar/links${query}`)
  return json<CalendarLink[]>(response)
}

export async function createCalendarLink(body: CalendarLinkInput): Promise<CalendarLink> {
  const response = await apiFetch('/api/v1/calendar/links', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<CalendarLink>(response)
}

export async function updateCalendarLink(
  linkId: string,
  body: {
    label?: string
    direction?: string
    calendar_id?: string | null
    calendar_url?: string | null
    enabled?: boolean
    options?: Record<string, unknown> | null
  }
): Promise<CalendarLink> {
  const response = await apiFetch(`/api/v1/calendar/links/${linkId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<CalendarLink>(response)
}

export async function deleteCalendarLink(linkId: string): Promise<void> {
  const response = await apiFetch(`/api/v1/calendar/links/${linkId}`, { method: 'DELETE' })
  if (!response.ok && response.status !== 204) {
    throw new Error(`delete failed (${response.status})`)
  }
}

export async function setCalendarLinkSecret(
  linkId: string,
  value: string
): Promise<CalendarLink> {
  const response = await apiFetch(`/api/v1/calendar/links/${linkId}/secret`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  })
  return json<CalendarLink>(response)
}

export async function startCalendarOAuth(linkId: string): Promise<CalendarOAuthStart> {
  const response = await apiFetch(`/api/v1/calendar/links/${linkId}/oauth/start`, {
    method: 'POST',
  })
  return json<CalendarOAuthStart>(response)
}

export async function completeCalendarOAuth(
  linkId: string,
  code: string,
  state: string
): Promise<CalendarLink> {
  const response = await apiFetch(`/api/v1/calendar/links/${linkId}/oauth/complete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, state }),
  })
  return json<CalendarLink>(response)
}

export async function discoverCalendars(
  body: CalendarDiscoverInput
): Promise<{ calendars: DiscoveredCalendar[] }> {
  const response = await apiFetch('/api/v1/calendar/links/discover', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return json<{ calendars: DiscoveredCalendar[] }>(response)
}

export async function testCalendarLink(linkId: string): Promise<CalendarSyncReport> {
  const response = await apiFetch(`/api/v1/calendar/links/${linkId}/test`, { method: 'POST' })
  return json<CalendarSyncReport>(response)
}

export async function syncCalendarLink(linkId: string): Promise<CalendarSyncReport> {
  const response = await apiFetch(`/api/v1/calendar/links/${linkId}/sync`, { method: 'POST' })
  return json<CalendarSyncReport>(response)
}

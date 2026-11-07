import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { CalendarCard } from './CalendarCard'

const listCalendarProviders = vi.fn()
const listCalendarLinks = vi.fn()
const syncCalendarLink = vi.fn()
const testCalendarLink = vi.fn()
const deleteCalendarLink = vi.fn()
const createCalendarLink = vi.fn()
const discoverCalendars = vi.fn()
const listCourses = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listCalendarProviders: () => listCalendarProviders(),
    listCalendarLinks: () => listCalendarLinks(),
    syncCalendarLink: (id: string) => syncCalendarLink(id),
    testCalendarLink: (id: string) => testCalendarLink(id),
    deleteCalendarLink: (id: string) => deleteCalendarLink(id),
    createCalendarLink: (body: unknown) => createCalendarLink(body),
    discoverCalendars: (body: unknown) => discoverCalendars(body),
  }
})

vi.mock('@/lib/api/courses', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/courses')>()
  return {
    ...actual,
    listCourses: () => listCourses(),
  }
})

// The catalog row IS the contract (plan 52 §12): the form renders from
// setup_fields, never from a provider name.
const PROVIDER = {
  id: 'google',
  label: 'Google',
  auth_kinds: ['oauth2'],
  base_url_required: false,
  protocol: 'google-calendar',
  writable: true,
  supports_delta: true,
  scope_presets: { read: ['https://www.googleapis.com/auth/calendar.readonly'], write: [] },
  consent_notice: 'You are delegating your own Google account to this app.',
  domains: ['www.googleapis.com'],
  setup_fields: [{ key: 'calendar', kind: 'calendar', required: false, label_key: 'calendar', placeholder: null, autocomplete: null, auth_kind: null, manual_key: null }],
  supports_discovery: true,
}

const CALDAV = {
  id: 'caldav',
  label: 'CalDAV',
  auth_kinds: ['app-password', 'token'],
  base_url_required: true,
  protocol: 'caldav',
  writable: true,
  supports_delta: false,
  scope_presets: { read: [], write: [] },
  consent_notice: 'This app stores an app-specific password you create at CalDAV.',
  domains: [],
  setup_fields: [
    { key: 'base_url', kind: 'url', required: true, label_key: 'baseUrl', placeholder: 'https://cloud.example.com', autocomplete: null, auth_kind: null, manual_key: null },
    { key: 'username', kind: 'text', required: false, label_key: 'username', placeholder: null, autocomplete: 'username', auth_kind: 'app-password', manual_key: null },
    { key: 'secret', kind: 'secret', required: true, label_key: 'appPassword', placeholder: null, autocomplete: 'new-password', auth_kind: 'app-password', manual_key: null },
    { key: 'secret', kind: 'secret', required: true, label_key: 'token', placeholder: null, autocomplete: 'new-password', auth_kind: 'token', manual_key: null },
    { key: 'calendar', kind: 'calendar', required: true, label_key: 'calendar', placeholder: null, autocomplete: null, auth_kind: null, manual_key: 'calendar_url' },
  ],
  supports_discovery: true,
}

const LINK = {
  id: 'link-1',
  course_id: '7',
  provider: 'google',
  auth_kind: 'oauth2',
  label: 'My calendar',
  account_label: null,
  calendar_id: null,
  calendar_url: null,
  direction: 'push',
  enabled: true,
  status: 'needs-auth',
  last_error: null,
  last_synced_at: null,
  consecutive_failures: 0,
  scopes: [],
  options: {},
  secret_configured: false,
  created_at: null,
  updated_at: null,
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <CalendarCard />
    </QueryClientProvider>,
  )
}

async function openAddForm() {
  renderCard()
  const button = await screen.findByRole('button', { name: /bind a calendar/i })
  fireEvent.click(button)
}

beforeEach(() => {
  listCalendarProviders.mockReset().mockResolvedValue({
    providers: [PROVIDER, CALDAV],
    secret_disclosure: 'Credentials live only in your OS keyring.',
  })
  listCalendarLinks.mockReset().mockResolvedValue([LINK])
  listCourses.mockReset().mockResolvedValue([{ id: '7', title: 'Calculus I' }])
  syncCalendarLink.mockReset().mockResolvedValue({ status: 'ok' })
  testCalendarLink.mockReset().mockResolvedValue({ status: 'ok' })
  deleteCalendarLink.mockReset().mockResolvedValue(undefined)
  createCalendarLink.mockReset().mockResolvedValue(LINK)
  discoverCalendars.mockReset().mockResolvedValue({
    calendars: [
      { id: 'personal', name: 'Personal', url: 'https://cloud.example.com/cal/personal/', primary: false },
    ],
  })
})

describe('CalendarCard', () => {
  test('renders the bound account with its course, provider and status', async () => {
    renderCard()
    expect(await screen.findByText(/My calendar/)).toBeTruthy()
    expect(screen.getByText(/Calculus I/)).toBeTruthy()
    expect(screen.getByText(/needs-auth/)).toBeTruthy()
  })

  test('sync runs through the API', async () => {
    renderCard()
    await screen.findByText(/My calendar/)
    fireEvent.click(screen.getByRole('button', { name: /sync now/i }))
    await waitFor(() => expect(syncCalendarLink).toHaveBeenCalledWith('link-1'))
  })

  test('bind form renders fields from the catalog descriptor, not provider names', async () => {
    await openAddForm()
    // Google (oauth2): no credential fields at all — only the picker.
    expect(await screen.findByRole('button', { name: /find calendars/i })).toBeTruthy()
    expect(screen.queryByLabelText('Base URL')).toBeNull()
    expect(screen.queryByLabelText('App password')).toBeNull()
    expect(screen.queryByLabelText('Username')).toBeNull()
  })

  test('switching to the CalDAV provider reveals its descriptor fields', async () => {
    await openAddForm()
    const providerSelect = await screen.findByDisplayValue('Google')
    fireEvent.change(providerSelect, { target: { value: 'caldav' } })
    expect(await screen.findByLabelText('Base URL')).toBeTruthy()
    expect(screen.getByLabelText('Username')).toBeTruthy()
    expect(screen.getByLabelText('App password')).toBeTruthy()
    // The token credential field stays hidden until the auth kind switches.
    expect(screen.queryByLabelText('Access token')).toBeNull()
  })

  test('the auth-kind selector swaps credential fields without provider logic', async () => {
    await openAddForm()
    fireEvent.change(await screen.findByDisplayValue('Google'), {
      target: { value: 'caldav' },
    })
    const kindSelect = await screen.findByDisplayValue(/app password/i)
    fireEvent.change(kindSelect, { target: { value: 'token' } })
    expect(await screen.findByLabelText('Access token')).toBeTruthy()
    expect(screen.queryByLabelText('App password')).toBeNull()
    expect(screen.queryByLabelText('Username')).toBeNull()
  })

  test('the picker discovers calendars and binds the picked one', async () => {
    await openAddForm()
    fireEvent.change(await screen.findByDisplayValue('Google'), {
      target: { value: 'caldav' },
    })
    fireEvent.change(await screen.findByLabelText('Base URL'), {
      target: { value: 'https://cloud.example.com' },
    })
    fireEvent.change(screen.getByLabelText('Username'), {
      target: { value: 'ilias' },
    })
    fireEvent.change(screen.getByLabelText('App password'), {
      target: { value: 'app-secret-value' },
    })
    fireEvent.click(await screen.findByRole('button', { name: /find calendars/i }))
    const select = await screen.findByDisplayValue(/pick a calendar/i)
    fireEvent.change(select, { target: { value: 'personal' } })
    expect(await screen.findByText(/Bound: Personal/)).toBeTruthy()

    fireEvent.change(screen.getByDisplayValue(/pick a course/i), {
      target: { value: '7' },
    })
    fireEvent.click(screen.getByRole('button', { name: /add calendar/i }))

    await waitFor(() => expect(createCalendarLink).toHaveBeenCalled())
    const body = createCalendarLink.mock.calls[0][0] as Record<string, unknown>
    expect(body.calendar_id).toBe('personal')
    expect(body.calendar_url).toBe('https://cloud.example.com/cal/personal/')
    expect(body.secret).toBe('app-secret-value')
  })

  test('discovery in the bind form sends transient credentials only', async () => {
    await openAddForm()
    fireEvent.change(await screen.findByDisplayValue('Google'), {
      target: { value: 'caldav' },
    })
    fireEvent.change(await screen.findByPlaceholderText('https://cloud.example.com'), {
      target: { value: 'https://cloud.example.com' },
    })
    fireEvent.change(screen.getByLabelText('Username'), {
      target: { value: 'ilias' },
    })
    fireEvent.change(screen.getByLabelText('App password'), {
      target: { value: 'app-secret-value' },
    })
    fireEvent.click(screen.getByRole('button', { name: /find calendars/i }))
    await waitFor(() => expect(discoverCalendars).toHaveBeenCalled())
    const body = discoverCalendars.mock.calls[0][0] as Record<string, unknown>
    expect(body.provider).toBe('caldav')
    expect(body.auth_kind).toBe('app-password')
    expect(body.secret).toBe('app-secret-value')
    expect(body.link_id).toBeUndefined()
  })
})

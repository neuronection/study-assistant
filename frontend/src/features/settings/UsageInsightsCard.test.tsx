import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { UsageInsightsCard } from './UsageInsightsCard'
import { rememberSessionScope, resetSessionScopeForTests } from '@/lib/session-scope'

const getActivationSummary = vi.fn()
const clearActivation = vi.fn()
const exportActivation = vi.fn()
const instance = vi.hoisted(() => ({
  identityMode: 'server' as string | undefined,
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getActivationSummary: () => getActivationSummary(),
    clearActivation: () => clearActivation(),
    exportActivation: () => exportActivation(),
  }
})

vi.mock('@/components/layout/DemoBanner', () => ({
  loadInstanceConfig: () =>
    Promise.resolve({ identity_mode: instance.identityMode }),
}))

const SCOPE_A = 'u:user-1:p:profile-a'
const SCOPE_B = 'u:user-1:p:profile-b'

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <UsageInsightsCard />
    </QueryClientProvider>,
  )
}

describe('UsageInsightsCard', () => {
  beforeEach(() => {
    resetSessionScopeForTests()
    window.localStorage.clear()
    instance.identityMode = 'server'
    getActivationSummary.mockReset().mockResolvedValue({
      total: 2,
      first_at: '2026-11-12T08:00:00Z',
      last_at: '2026-11-12T08:10:00Z',
      counts: [
        { event: 'first_file_ingested', count: 1 },
        { event: 'solve_completed', count: 1 },
      ],
      recent: [],
    })
    clearActivation.mockReset().mockResolvedValue(undefined)
    exportActivation.mockReset().mockResolvedValue({ events: [], summary: {} })
  })

  test('shows recorded counts and can clear them', async () => {
    renderCard()
    expect(await screen.findByText('2 recorded events')).toBeInTheDocument()
    expect(screen.getByText('first_file_ingested')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    await waitFor(() => expect(clearActivation).toHaveBeenCalled())
  })

  test('uses instance storage wording in server mode', async () => {
    renderCard()
    expect(
      await screen.findByText(
        "Stored in this instance's database for your profile. Never sent to a third party.",
      ),
    ).toBeInTheDocument()
  })

  test('renders no disclosure until the instance mode resolves', async () => {
    instance.identityMode = undefined
    renderCard()
    expect(await screen.findByText('2 recorded events')).toBeInTheDocument()
    expect(
      screen.queryByText(
        "Stored in this instance's database for your profile. Never sent to a third party.",
      ),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByText(
        'Stored on this device only. Never sent to a third party.',
      ),
    ).not.toBeInTheDocument()
  })

  test('uses device storage wording on desktop', async () => {
    instance.identityMode = 'desktop'
    renderCard()
    expect(
      await screen.findByText(
        'Stored on this device only. Never sent to a third party.',
      ),
    ).toBeInTheDocument()
  })

  test('clear removes the captured scope client keys after the API clear', async () => {
    rememberSessionScope(SCOPE_A)
    window.localStorage.setItem(`sa-first-event.${SCOPE_A}.first_review`, '1')
    window.localStorage.setItem(`sa-first-event.${SCOPE_B}.first_review`, '1')
    window.localStorage.setItem('sa-first-event.local.first_capture', '1')
    let resolveClear: (() => void) | undefined
    clearActivation.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveClear = resolve
        }),
    )

    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: 'Clear' }))
    await waitFor(() => expect(clearActivation).toHaveBeenCalled())

    rememberSessionScope(SCOPE_B)
    resolveClear?.()

    await waitFor(() =>
      expect(
        window.localStorage.getItem(`sa-first-event.${SCOPE_A}.first_review`),
      ).toBeNull()
    )
    expect(
      window.localStorage.getItem(`sa-first-event.${SCOPE_B}.first_review`),
    ).toBe('1')
    expect(
      window.localStorage.getItem('sa-first-event.local.first_capture'),
    ).toBeNull()
  })
})

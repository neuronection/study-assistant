import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { UNAUTHENTICATED_EVENT } from '@/lib/api/client'
import { audioCacheName, audioStateKey } from '@/lib/audio-offline'
import { bootSession } from '@/lib/auth-session'
import { rememberSessionScope, resetSessionScopeForTests } from '@/lib/session-scope'
import { installFakeCaches } from '@/test/caches'

import { SessionGate } from './SessionGate'

vi.mock('@/lib/auth-session', () => ({
  bootSession: vi.fn(),
}))

const mockedBoot = vi.mocked(bootSession)

describe('SessionGate (shared AuthGate wiring)', () => {
  beforeEach(() => {
    mockedBoot.mockReset()
    resetSessionScopeForTests()
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders children once bootSession establishes a session', async () => {
    mockedBoot.mockResolvedValue(true)
    render(
      <SessionGate>
        <div data-testid="app" />
      </SessionGate>,
    )
    await waitFor(() => expect(screen.getByTestId('app')).toBeInTheDocument())
  })

  it('lands on the login surface when bootSession resolves anonymous', async () => {
    mockedBoot.mockResolvedValue(false)
    render(
      <SessionGate>
        <div data-testid="app" />
      </SessionGate>,
    )
    await waitFor(() =>
      expect(document.querySelector('input[type="email"]')).toBeInTheDocument(),
    )
    expect(screen.queryByTestId('app')).not.toBeInTheDocument()
  })

  it('re-runs the boot flow when a mid-session 401 dispatches the unauthenticated event', async () => {
    mockedBoot.mockResolvedValue(true)
    render(
      <SessionGate>
        <div data-testid="app" />
      </SessionGate>,
    )
    await waitFor(() => expect(screen.getByTestId('app')).toBeInTheDocument())

    mockedBoot.mockResolvedValue(false)
    window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT))
    await waitFor(() =>
      expect(document.querySelector('input[type="email"]')).toBeInTheDocument(),
    )
    expect(screen.queryByTestId('app')).not.toBeInTheDocument()
    expect(mockedBoot.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('purges the scoped audio cache when the session is lost', async () => {
    const scope = 'u:user-1:p:profile-a'
    const storage = installFakeCaches()
    rememberSessionScope(scope)
    await storage.open(audioCacheName(scope))
    window.localStorage.setItem(audioStateKey(scope), 'state')
    window.localStorage.setItem('sa-first-event.local.first_review', '1')
    mockedBoot.mockResolvedValue(true)

    render(
      <SessionGate>
        <div data-testid="app" />
      </SessionGate>,
    )
    await waitFor(() => expect(screen.getByTestId('app')).toBeInTheDocument())

    window.dispatchEvent(new Event(UNAUTHENTICATED_EVENT))

    await waitFor(async () =>
      expect(await caches.keys()).not.toContain(audioCacheName(scope))
    )
    expect(window.localStorage.getItem(audioStateKey(scope))).toBeNull()
    expect(
      window.localStorage.getItem('sa-first-event.local.first_review'),
    ).toBeNull()
  })
})

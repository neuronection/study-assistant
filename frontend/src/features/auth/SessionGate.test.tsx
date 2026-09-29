import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { UNAUTHENTICATED_EVENT } from '@/lib/api/client'
import { bootSession } from '@/lib/auth-session'

import { SessionGate } from './SessionGate'

vi.mock('@/lib/auth-session', () => ({
  bootSession: vi.fn(),
}))

const mockedBoot = vi.mocked(bootSession)

describe('SessionGate (shared AuthGate wiring)', () => {
  beforeEach(() => {
    mockedBoot.mockReset()
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
})

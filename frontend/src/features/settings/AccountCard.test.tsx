import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { AccountCard } from './AccountCard'
import { audioCacheName, audioStateKey } from '@/lib/audio-offline'
import { rememberSessionScope, resetSessionScopeForTests } from '@/lib/session-scope'
import { installFakeCaches } from '@/test/caches'

const listMySessions = vi.fn()
const revokeMySession = vi.fn()
const changeMyPassword = vi.fn()
const deleteMyAccount = vi.fn()
const setCurrentUser = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listMySessions: () => listMySessions(),
    revokeMySession: (...args: unknown[]) => revokeMySession(...(args as [string])),
    changeMyPassword: (...args: unknown[]) =>
      changeMyPassword(...(args as [string, string])),
    deleteMyAccount: (...args: unknown[]) => deleteMyAccount(...(args as [string])),
  }
})

vi.mock('@/lib/auth-session', () => ({
  getCurrentUser: vi.fn(),
  setCurrentUser: (...args: unknown[]) => setCurrentUser(...args),
}))

const SESSIONS = [
  {
    id: 'fam-1',
    client_label: 'Firefox on Linux',
    created_at: '2026-09-01T10:00:00Z',
    expires_at: '2026-10-01T10:00:00Z',
    revoked_at: null,
    current: true,
  },
  {
    id: 'fam-2',
    client_label: 'Phone',
    created_at: null,
    expires_at: '2026-10-01T10:00:00Z',
    revoked_at: null,
    current: false,
  },
  {
    id: 'fam-3',
    client_label: 'Old laptop',
    created_at: '2026-08-01T10:00:00Z',
    expires_at: '2026-09-01T10:00:00Z',
    revoked_at: '2026-08-15T10:00:00Z',
    current: false,
  },
]

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <AccountCard />
    </QueryClientProvider>,
  )
}

function sessionRows(): HTMLElement[] {
  return Array.from(
    document.querySelectorAll<HTMLElement>('[data-as="account-session-row"]'),
  )
}

describe('AccountCard', () => {
  beforeEach(() => {
    resetSessionScopeForTests()
    listMySessions.mockReset()
    revokeMySession.mockReset()
    changeMyPassword.mockReset()
    deleteMyAccount.mockReset()
    setCurrentUser.mockReset()
    listMySessions.mockResolvedValue(SESSIONS)
    revokeMySession.mockResolvedValue(undefined)
    changeMyPassword.mockResolvedValue({
      id: 'u-admin',
      email: 'ada@example.com',
      full_name: 'Ada Lovelace',
      is_admin: true,
      is_active: true,
    })
    deleteMyAccount.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('signing out the current session purges the scoped audio cache', async () => {
    const scope = 'u:user-1:p:profile-a'
    const storage = installFakeCaches()
    rememberSessionScope(scope)
    await storage.open(audioCacheName(scope))
    window.localStorage.setItem(audioStateKey(scope), 'state')

    renderCard()
    await screen.findByText('Firefox on Linux')
    const rows = sessionRows()
    fireEvent.click(within(rows[0]).getByRole('button', { name: /Sign out/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Sign out' }))

    await waitFor(() => expect(setCurrentUser).toHaveBeenCalledWith(null))
    await waitFor(async () =>
      expect(await caches.keys()).not.toContain(audioCacheName(scope))
    )
    expect(window.localStorage.getItem(audioStateKey(scope))).toBeNull()
  })

  test('lists sessions with the current marker and revoked state', async () => {
    renderCard()
    await screen.findByText('Firefox on Linux')
    const rows = sessionRows()
    expect(rows).toHaveLength(3)
    expect(screen.getByText('this device')).toBeInTheDocument()
    expect(rows[0]).toHaveAttribute('aria-current', 'true')
    expect(screen.getByText('Phone')).toBeInTheDocument()
    expect(screen.getByText('Old laptop')).toBeInTheDocument()
    const revokedBadge = rows[2].querySelector('[data-as="account-session-revoked"]')
    expect(revokedBadge).toHaveTextContent('Signed out')
    expect(rows[2].querySelector('[data-as="account-session-badges"]')).toBeNull()
    expect(rows[2]).toHaveAttribute('data-revoked', 'true')
    expect(within(rows[2]).queryByRole('button')).toBeNull()
    expect(screen.getAllByRole('button', { name: /Sign out/ })).toHaveLength(2)
  })

  test('a successful revoke announces the result and keeps focus on the list', async () => {
    listMySessions
      .mockResolvedValueOnce(SESSIONS)
      .mockResolvedValueOnce(
        SESSIONS.map((session) =>
          session.id === 'fam-2'
            ? { ...session, revoked_at: '2026-09-02T10:00:00Z' }
            : session,
        ),
      )
    renderCard()
    await screen.findByText('Phone')
    const rows = sessionRows()
    fireEvent.click(within(rows[1]).getByRole('button', { name: /Sign out/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Sign out' }))

    await waitFor(() =>
      expect(sessionRows()[1]).toHaveAttribute('data-revoked', 'true'),
    )
    expect(within(sessionRows()[1]).queryByRole('button')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('Session signed out.')
    expect(screen.getByRole('heading', { name: 'Sessions' })).toHaveFocus()
  })

  test('revoking a session asks for confirmation first', async () => {
    renderCard()
    await screen.findByText('Phone')
    const rows = sessionRows()
    fireEvent.click(within(rows[1]).getByRole('button', { name: /Sign out/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Sign out this session?')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(revokeMySession).toHaveBeenCalledWith('fam-2'))
  })

  test('marks the row whose revoke is in flight', async () => {
    let settle: () => void = () => {}
    revokeMySession.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          settle = resolve
        }),
    )
    renderCard()
    await screen.findByText('Phone')
    const rows = sessionRows()
    fireEvent.click(within(rows[1]).getByRole('button', { name: /Sign out/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Sign out' }))
    const busy = await within(rows[1]).findByRole('button', {
      name: 'Signing out… — Phone',
    })
    expect(busy).toBeDisabled()
    expect(busy).toHaveAttribute('aria-busy', 'true')
    expect(within(rows[0]).getByRole('button', { name: /Sign out/ })).toBeEnabled()
    settle()
    await waitFor(() => expect(revokeMySession).toHaveBeenCalledWith('fam-2'))
  })

  test('declining the confirm dialog revokes nothing', async () => {
    renderCard()
    await screen.findByText('Phone')
    const rows = sessionRows()
    fireEvent.click(within(rows[1]).getByRole('button', { name: /Sign out/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(revokeMySession).not.toHaveBeenCalled()
  })

  test('revoking the current session warns and signs the app out', async () => {
    renderCard()
    await screen.findByText('Firefox on Linux')
    const rows = sessionRows()
    fireEvent.click(within(rows[0]).getByRole('button', { name: /Sign out/ }))
    const dialog = await screen.findByRole('dialog')
    expect(
      within(dialog).getByText(/you will be signed out here/i),
    ).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(revokeMySession).toHaveBeenCalledWith('fam-1'))
    await waitFor(() => expect(setCurrentUser).toHaveBeenCalledWith(null))
  })

  test('a failed session listing shows the generic error', async () => {
    listMySessions.mockRejectedValue(new Error('boom'))
    renderCard()
    expect(
      await screen.findByText('Something went wrong — try again.'),
    ).toBeInTheDocument()
    expect(sessionRows()).toHaveLength(0)
  })

  test('a failed revoke surfaces the generic error', async () => {
    const { ApiError } = await import('@/lib/api')
    revokeMySession.mockRejectedValue(new ApiError('nope', 500))
    renderCard()
    await screen.findByText('Phone')
    const rows = sessionRows()
    fireEvent.click(within(rows[1]).getByRole('button', { name: /Sign out/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Sign out' }))
    expect(
      await screen.findByText('Something went wrong — try again.'),
    ).toBeInTheDocument()
  })

  test('password change gates below 10 characters and clears on success', async () => {
    renderCard()
    const current = screen.getByLabelText('Current password')
    const next = screen.getByLabelText('New password')
    const submit = screen.getByRole('button', { name: 'Change password' })
    expect(submit).toBeDisabled()
    fireEvent.change(next, { target: { value: 'short' } })
    expect(submit).toBeDisabled()
    fireEvent.change(current, { target: { value: 'old-secret-1' } })
    fireEvent.change(next, { target: { value: 'new-secret-12' } })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    await waitFor(() =>
      expect(changeMyPassword).toHaveBeenCalledWith('old-secret-1', 'new-secret-12'),
    )
    await waitFor(() => expect(current).toHaveValue(''))
    await waitFor(() => expect(next).toHaveValue(''))
    expect(await screen.findByText('Password changed.')).toBeInTheDocument()
    expect(setCurrentUser).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'ada@example.com' }),
    )
  })

  test('wrong current password surfaces a friendly error', async () => {
    const { ApiError } = await import('@/lib/api')
    changeMyPassword.mockRejectedValue(new ApiError('Invalid password', 403))
    renderCard()
    fireEvent.change(screen.getByLabelText('Current password'), {
      target: { value: 'wrong' },
    })
    fireEvent.change(screen.getByLabelText('New password'), {
      target: { value: 'new-secret-12' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText('Incorrect password.')).toBeInTheDocument()
  })

  test('delete account requires the password confirmation', async () => {
    renderCard()
    const del = screen.getByLabelText('Confirm with your password')
    const submit = screen.getByRole('button', { name: 'Delete account' })
    expect(submit).toBeDisabled()
    fireEvent.change(del, { target: { value: 'hunter2-long-enough' } })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    await waitFor(() =>
      expect(deleteMyAccount).toHaveBeenCalledWith('hunter2-long-enough'),
    )
    await waitFor(() => expect(setCurrentUser).toHaveBeenCalledWith(null))
  })
})

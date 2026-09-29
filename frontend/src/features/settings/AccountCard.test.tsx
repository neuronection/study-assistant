import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { AccountCard } from './AccountCard'

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

describe('AccountCard', () => {
  beforeEach(() => {
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

  test('lists sessions with the current marker and revoked state', async () => {
    renderCard()
    const rows = await screen.findAllByTestId('account-session')
    expect(rows).toHaveLength(3)
    expect(screen.getByText('Firefox on Linux')).toBeInTheDocument()
    expect(screen.getByText('(this device)')).toBeInTheDocument()
    expect(screen.getByText('Phone')).toBeInTheDocument()
    expect(screen.getByText('Old laptop')).toBeInTheDocument()
    expect(screen.getByText('Signed out')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Sign out/ })).toHaveLength(2)
  })

  test('revoking a session asks for confirmation first', async () => {
    renderCard()
    const rows = await screen.findAllByTestId('account-session')
    fireEvent.click(within(rows[1]).getByRole('button', { name: /Sign out/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Sign out this session?')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(revokeMySession).toHaveBeenCalledWith('fam-2'))
  })

  test('declining the confirm dialog revokes nothing', async () => {
    renderCard()
    const rows = await screen.findAllByTestId('account-session')
    fireEvent.click(within(rows[1]).getByRole('button', { name: /Sign out/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(revokeMySession).not.toHaveBeenCalled()
  })

  test('revoking the current session warns and signs the app out', async () => {
    renderCard()
    const rows = await screen.findAllByTestId('account-session')
    fireEvent.click(within(rows[0]).getByRole('button', { name: /Sign out/ }))
    const dialog = await screen.findByRole('dialog')
    expect(
      within(dialog).getByText(/you will be signed out here/i),
    ).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(revokeMySession).toHaveBeenCalledWith('fam-1'))
    await waitFor(() => expect(setCurrentUser).toHaveBeenCalledWith(null))
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

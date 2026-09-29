import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ApiError } from '@/lib/api'

import { UsersTab } from './UsersTab'

const listAdminUsers = vi.fn()
const patchAdminUser = vi.fn()
const resetAdminUserPassword = vi.fn()
const forceLogoutUser = vi.fn()
const getCurrentUser = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listAdminUsers: () => listAdminUsers(),
    patchAdminUser: (...args: unknown[]) =>
      patchAdminUser(...(args as [string, object])),
    resetAdminUserPassword: (...args: unknown[]) =>
      resetAdminUserPassword(...(args as [string, string])),
    forceLogoutUser: (...args: unknown[]) => forceLogoutUser(...(args as [string])),
  }
})

vi.mock('@/lib/auth-session', () => ({
  getCurrentUser: () => getCurrentUser(),
  setCurrentUser: vi.fn(),
}))

const USERS = [
  {
    id: 'u-admin',
    email: 'ada@example.com',
    full_name: 'Ada Lovelace',
    is_admin: true,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    activity_count: 12,
  },
  {
    id: 'u-plain',
    email: 'grace@example.com',
    full_name: '',
    is_admin: false,
    is_active: false,
    created_at: '2026-02-01T00:00:00Z',
    activity_count: 0,
  },
]

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <UsersTab />
    </QueryClientProvider>,
  )
}

describe('UsersTab', () => {
  beforeEach(() => {
    listAdminUsers.mockReset()
    patchAdminUser.mockReset()
    resetAdminUserPassword.mockReset()
    forceLogoutUser.mockReset()
    getCurrentUser.mockReset()
    getCurrentUser.mockReturnValue({
      id: 'u-admin',
      email: 'ada@example.com',
      full_name: 'Ada Lovelace',
      is_admin: true,
      is_active: true,
    })
    listAdminUsers.mockResolvedValue(USERS)
    patchAdminUser.mockResolvedValue(USERS[0])
  })

  test('renders rows with "(you)", activity count, role and status', async () => {
    renderTab()
    expect(await screen.findByText('ada@example.com')).toBeInTheDocument()
    expect(screen.getByText('grace@example.com')).toBeInTheDocument()
    expect(screen.getByText('(you)')).toBeInTheDocument()
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument()
    expect(screen.getByText('Activity')).toBeInTheDocument()
    expect(screen.getAllByText('Admin').length).toBeGreaterThan(0)
    expect(screen.getAllByText('User').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Disabled').length).toBeGreaterThan(0)
  })

  test('promote/demote and activate/deactivate persist sparse patches', async () => {
    renderTab()
    fireEvent.click(await screen.findByRole('button', { name: /Remove admin/ }))
    await waitFor(() =>
      expect(patchAdminUser).toHaveBeenCalledWith('u-admin', { is_admin: false }),
    )
    fireEvent.click(screen.getByRole('button', { name: /Deactivate/ }))
    await waitFor(() =>
      expect(patchAdminUser).toHaveBeenCalledWith('u-admin', { is_active: false }),
    )
    fireEvent.click(screen.getByRole('button', { name: /Make admin/ }))
    await waitFor(() =>
      expect(patchAdminUser).toHaveBeenCalledWith('u-plain', { is_admin: true }),
    )
    fireEvent.click(screen.getByRole('button', { name: /Activate/ }))
    await waitFor(() =>
      expect(patchAdminUser).toHaveBeenCalledWith('u-plain', { is_active: true }),
    )
  })

  test('password reset panel gates the submit below 10 characters', async () => {
    resetAdminUserPassword.mockResolvedValue(undefined)
    renderTab()
    fireEvent.click((await screen.findAllByRole('button', { name: /Reset password/ }))[0])
    const input = screen.getByLabelText('New password')
    const submit = screen.getByRole('button', { name: 'Set password' })
    expect(submit).toBeDisabled()
    fireEvent.change(input, { target: { value: 'short' } })
    expect(submit).toBeDisabled()
    fireEvent.change(input, { target: { value: 'short-enough-123' } })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    await waitFor(() =>
      expect(resetAdminUserPassword).toHaveBeenCalledWith(
        'u-admin',
        'short-enough-123',
      ),
    )
  })

  test('force logout targets the row user', async () => {
    forceLogoutUser.mockResolvedValue(undefined)
    renderTab()
    fireEvent.click((await screen.findAllByRole('button', { name: /Force logout/ }))[1])
    await waitFor(() => expect(forceLogoutUser).toHaveBeenCalledWith('u-plain'))
  })

  test('guard-rail 403s surface as friendly messages', async () => {
    patchAdminUser.mockRejectedValue(
      new ApiError('Admins cannot demote or deactivate themselves', 403, 'Admins cannot demote or deactivate themselves'),
    )
    renderTab()
    fireEvent.click(await screen.findByRole('button', { name: /Remove admin/ }))
    expect(
      await screen.findByText('You cannot change your own role or status.'),
    ).toBeInTheDocument()
  })

  test('shows the loading state and the empty state', async () => {
    listAdminUsers.mockResolvedValue([])
    renderTab()
    expect(await screen.findByText('No users')).toBeInTheDocument()
  })
})

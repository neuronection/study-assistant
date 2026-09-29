import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch } from '@/lib/api/client'

import { LoginOverlay } from './LoginOverlay'

vi.mock('@/lib/api/client', () => ({
  apiFetch: vi.fn(),
}))

const mockedFetch = vi.mocked(apiFetch)

function respond(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('LoginOverlay', () => {
  beforeEach(() => {
    mockedFetch.mockReset()
  })

  it('signs in and reports success', async () => {
    mockedFetch.mockResolvedValue(
      respond(200, { id: 'u1', email: 'a@b.c', is_admin: true }),
    )
    const onSignedIn = vi.fn()
    render(<LoginOverlay onSignedIn={onSignedIn} />)

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'a@b.c' },
    })
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: 'correct-horse-battery' },
    })
    fireEvent.click(screen.getByRole('button', { name: /sign in|anmelden/i }))

    await waitFor(() => expect(onSignedIn).toHaveBeenCalledTimes(1))
    expect(mockedFetch).toHaveBeenCalledWith(
      '/api/v1/auth/login',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('switches to register and posts the register payload', async () => {
    mockedFetch.mockResolvedValue(respond(201, { id: 'u2' }))
    const onSignedIn = vi.fn()
    render(<LoginOverlay onSignedIn={onSignedIn} />)

    fireEvent.click(screen.getByRole('button', { name: /create one|konto/i }))
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'new@example.com' },
    })
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: 'a-long-enough-password' },
    })
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: 'a-long-enough-password' },
    })
    const form = document.querySelector('form')
    expect(form).not.toBeNull()
    fireEvent.submit(form!)

    await waitFor(() => expect(onSignedIn).toHaveBeenCalledTimes(1))
    expect(mockedFetch).toHaveBeenCalledWith(
      '/api/v1/auth/register',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('shows the server error detail on failure', async () => {
    mockedFetch.mockResolvedValue(respond(401, { detail: 'Invalid email or password' }))
    render(<LoginOverlay onSignedIn={vi.fn()} />)

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'a@b.c' },
    })
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: 'wrong-password-123' },
    })
    fireEvent.click(screen.getByRole('button', { name: /sign in|anmelden/i }))

    await waitFor(() =>
      expect(screen.getByText('Invalid email or password')).toBeInTheDocument(),
    )
  })

  it('blocks register when the confirm password mismatches', async () => {
    render(<LoginOverlay onSignedIn={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /create one|konto/i }))
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'new@example.com' },
    })
    fireEvent.change(screen.getByLabelText(/^password$/i), {
      target: { value: 'a-long-enough-password' },
    })
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: 'a-different-password' },
    })
    fireEvent.click(screen.getByRole('button', { name: /create account/i }))

    expect(mockedFetch).not.toHaveBeenCalled()
    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
  })

  it('toggles password visibility from the login form', () => {
    render(<LoginOverlay onSignedIn={vi.fn()} />)

    const password = screen.getByLabelText(/^password$/i)
    expect(password).toHaveAttribute('type', 'password')
    fireEvent.click(screen.getByRole('button', { name: /show password/i }))
    expect(password).toHaveAttribute('type', 'text')
  })
})

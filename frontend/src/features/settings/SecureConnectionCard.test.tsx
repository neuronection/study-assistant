import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { SecureConnectionCard } from './SecureConnectionCard'
import type { SecureContextReport } from '@/lib/secure-context'

const detect = vi.hoisted(() => vi.fn())

vi.mock('@/lib/secure-context', () => ({
  detectSecureContext: detect,
}))

function report(overrides: Partial<SecureContextReport> = {}): SecureContextReport {
  return {
    secure: true,
    desktop: false,
    serviceWorker: true,
    install: true,
    shareTarget: true,
    mediaCapture: true,
    mediaRecorder: true,
    notifications: true,
    ...overrides,
  }
}

describe('SecureConnectionCard', () => {
  beforeEach(() => {
    detect.mockReset()
  })

  test('shows a secure connection and available capabilities', () => {
    detect.mockReturnValue(report())
    render(<SecureConnectionCard />)
    expect(screen.getByText('Secure connection')).toBeInTheDocument()
    expect(screen.getByLabelText('Install app: available')).toBeInTheDocument()
    expect(screen.getByLabelText('Microphone: available')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Install app/ })).toBeInTheDocument()
    expect(screen.queryByText('What needs HTTPS?')).not.toBeInTheDocument()
  })

  test('explains plain HTTP and what still works', () => {
    detect.mockReturnValue(
      report({
        secure: false,
        serviceWorker: false,
        install: false,
        shareTarget: false,
        mediaCapture: false,
        mediaRecorder: false,
        notifications: false,
      })
    )
    render(<SecureConnectionCard />)
    expect(screen.getByText('Plain HTTP')).toBeInTheDocument()
    expect(screen.getByLabelText('Install app: unavailable')).toBeInTheDocument()
    expect(screen.getByText('What needs HTTPS?')).toBeInTheDocument()
    expect(screen.getByText(/camera file picker/)).toBeInTheDocument()
  })

  test('desktop hides browser-only capabilities', () => {
    detect.mockReturnValue(report({ desktop: true, secure: false }))
    render(<SecureConnectionCard />)
    expect(screen.getByText('Desktop app')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Install app/)).not.toBeInTheDocument()
  })
})

import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ErrorBanner } from './error-banner'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a href="/settings">{children}</a>,
}))

describe('ErrorBanner', () => {
  test('renders nothing without a message', () => {
    const { container } = render(<ErrorBanner message={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  test('shows the message with an Open Settings link for unassigned tasks', () => {
    render(
      <ErrorBanner message="task 'quizgen' is unassigned — connect a provider and assign a model in Settings." />
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/quizgen/)
    const link = screen.getByRole('link', { name: /open settings/i })
    expect(link).toHaveAttribute('href', '/settings')
  })

  test('shows the message with an Open Settings link for provider errors', () => {
    render(<ErrorBanner message="provider test failed: connection refused" />)
    expect(screen.getByRole('link', { name: /open settings/i })).toBeInTheDocument()
  })

  test('no settings link for unrelated errors', () => {
    render(<ErrorBanner message="validation failed: stem is empty" />)
    expect(screen.getByRole('alert')).toHaveTextContent(/validation failed/)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})

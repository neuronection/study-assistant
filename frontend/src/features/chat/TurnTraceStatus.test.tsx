import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { TurnTraceStatus } from './TurnTraceStatus'

describe('TurnTraceStatus', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  test('renders the phase label and a ticking elapsed timer', () => {
    vi.useFakeTimers()
    const startedAt = Date.now()
    render(<TurnTraceStatus phase="computing" startedAt={startedAt} />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Computing…')
    expect(screen.getByText('Computing…')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    expect(screen.getByText('1.5 s')).toBeInTheDocument()
  })

  test('renders the thinking phase by default', () => {
    render(<TurnTraceStatus phase="thinking" startedAt={Date.now()} />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-label', 'Thinking…')
  })
})

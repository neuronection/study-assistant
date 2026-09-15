import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { CountdownChip } from './CountdownChip'

describe('CountdownChip', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-15T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  test('renders remaining time offset-corrected and ticks down', () => {
    const deadline = new Date('2026-09-15T12:20:00Z').toISOString()
    const skew = 5000
    render(<CountdownChip deadlineIso={deadline} offsetMs={-skew} />)
    expect(screen.getByRole('timer').textContent).toBe('20:05')
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(screen.getByRole('timer').textContent).toBe('20:03')
  })

  test('flags the last minute as low time', () => {
    const deadline = new Date('2026-09-15T12:00:45Z').toISOString()
    render(<CountdownChip deadlineIso={deadline} offsetMs={0} />)
    expect(screen.getByRole('timer').className).toContain('text-warning')
  })

  test('expiry renders time-up and fires onExpire once', () => {
    const onExpire = vi.fn()
    const deadline = new Date('2026-09-15T12:00:02Z').toISOString()
    render(<CountdownChip deadlineIso={deadline} offsetMs={0} onExpire={onExpire} />)
    act(() => {
      vi.advanceTimersByTime(2100)
    })
    expect(screen.getByRole('timer').textContent).toContain("Time's up")
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(onExpire).toHaveBeenCalledTimes(1)
  })

  test('a chip mounted already expired fires onExpire once', () => {
    const onExpire = vi.fn()
    const deadline = new Date('2026-09-15T11:00:00Z').toISOString()
    render(<CountdownChip deadlineIso={deadline} offsetMs={0} onExpire={onExpire} />)
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(screen.getByRole('timer').textContent).toContain("Time's up")
    expect(onExpire).toHaveBeenCalledTimes(1)
  })

  test('keyboard events do not leak into the timer', () => {
    const deadline = new Date('2026-09-15T12:10:00Z').toISOString()
    render(<CountdownChip deadlineIso={deadline} offsetMs={0} />)
    fireEvent.keyDown(window, { key: '1' })
    expect(screen.getByRole('timer').textContent).toBe('10:00')
  })
})

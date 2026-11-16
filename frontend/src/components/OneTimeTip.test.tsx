import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { OneTimeTip } from './OneTimeTip'

const recordActivation = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    recordActivation: (...args: unknown[]) => recordActivation(...args),
  }
})

describe('OneTimeTip', () => {
  beforeEach(() => {
    window.localStorage.clear()
    recordActivation.mockReset().mockResolvedValue(undefined)
  })

  test('shows once, persists dismissal, and records it locally', () => {
    const { rerender } = render(<OneTimeTip id="library-split-view">Try split view</OneTimeTip>)
    expect(screen.getByText('Try split view')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByText('Try split view')).not.toBeInTheDocument()
    expect(window.localStorage.getItem('sa-tip.library-split-view')).toBe('1')
    expect(recordActivation).toHaveBeenCalledWith('tip_dismissed', {
      surface: 'one_time_tip',
      step: 'library-split-view',
    })
    rerender(<OneTimeTip id="library-split-view">Try split view</OneTimeTip>)
    expect(screen.queryByText('Try split view')).not.toBeInTheDocument()
  })

  test('a dismissed tip stays hidden after remount', () => {
    window.localStorage.setItem('sa-tip.review-buttons', '1')
    render(<OneTimeTip id="review-buttons">Rate with 1–4</OneTimeTip>)
    expect(screen.queryByText('Rate with 1–4')).not.toBeInTheDocument()
  })
})

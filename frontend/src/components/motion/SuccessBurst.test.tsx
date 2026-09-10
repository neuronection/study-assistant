import { render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { motionState, rendersIdenticallyUnderReducedMotion } from '@/test/motion'

vi.mock('framer-motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('framer-motion')>()
  return {
    ...actual,
    useReducedMotion: () => motionState.reduced,
  }
})

import { SuccessBurst } from './SuccessBurst'

describe('SuccessBurst', () => {
  test('renders a one-shot check-draw svg', () => {
    render(<SuccessBurst />)
    const svg = screen.getByTestId('success-burst')
    expect(svg.tagName).toBe('svg')
    expect(svg.querySelectorAll('path, circle')).toHaveLength(2)
  })

  test('renders identically under prefers-reduced-motion', async () => {
    await rendersIdenticallyUnderReducedMotion(() => <SuccessBurst />)
    expect(motionState.reduced).toBe(false)
  })
})

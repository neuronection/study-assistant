import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, test, vi } from 'vitest'

import { motionState, rendersIdenticallyUnderReducedMotion } from '@/test/motion'

vi.mock('framer-motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('framer-motion')>()
  return {
    ...actual,
    useReducedMotion: () => motionState.reduced,
  }
})

import { Dumbbell, Layers } from 'lucide-react'

import { SegmentedControl } from './SegmentedControl'

function Harness() {
  const [value, setValue] = useState('a')
  return (
    <SegmentedControl
      items={[
        { value: 'a', label: 'Alpha', icon: Dumbbell },
        { value: 'b', label: 'Beta', icon: Layers },
      ]}
      value={value}
      onChange={setValue}
    />
  )
}

function UnderlineHarness() {
  const [value, setValue] = useState('a')
  return (
    <SegmentedControl
      variant="underline"
      items={[
        { value: 'a', label: 'Alpha', ariaCurrent: true },
        { value: 'b', label: 'Beta', ariaCurrent: true },
      ]}
      value={value}
      onChange={setValue}
    />
  )
}

describe('SegmentedControl', () => {
  test('marks the active tab and moves selection on click', () => {
    render(<Harness />)
    const alpha = screen.getByRole('tab', { name: 'Alpha' })
    const beta = screen.getByRole('tab', { name: 'Beta' })
    expect(alpha.getAttribute('aria-selected')).toBe('true')
    expect(beta.getAttribute('aria-selected')).toBe('false')
    expect(alpha.querySelector('[data-projection-id], span[aria-hidden]')).not.toBeNull()
    expect(beta.querySelector('span[aria-hidden]')).toBeNull()

    fireEvent.click(beta)
    expect(beta.getAttribute('aria-selected')).toBe('true')
    expect(alpha.getAttribute('aria-selected')).toBe('false')
  })

  test('underline variant exposes aria-current on the active tab', () => {
    render(<UnderlineHarness />)
    const alpha = screen.getByRole('tab', { name: 'Alpha' })
    expect(alpha.getAttribute('aria-current')).toBe('page')
    fireEvent.click(screen.getByRole('tab', { name: 'Beta' }))
    expect(screen.getByRole('tab', { name: 'Beta' }).getAttribute('aria-current')).toBe('page')
    expect(alpha.getAttribute('aria-current')).toBe(null)
  })

  test('renders identically under prefers-reduced-motion', async () => {
    await rendersIdenticallyUnderReducedMotion(() => <Harness />)
    expect(motionState.reduced).toBe(false)
  })
})

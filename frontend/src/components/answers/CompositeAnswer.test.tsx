import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, test, vi } from 'vitest'

import {
  CompositeAnswer,
  compositeResponseComplete,
  isCompositeInput,
  partLetter,
  type CompositeInput,
} from './CompositeAnswer'

const INPUT: CompositeInput = {
  parts: [{ type: 'numeric' }, { type: 'equation' }, { type: 'text' }],
}

describe('CompositeAnswer', () => {
  test('renders one labeled input per part (MathInput for equations)', async () => {
    render(<CompositeAnswer input={INPUT} value={null} onChange={vi.fn()} />)
    expect(screen.getByLabelText('Part (a) answer')).toBeInTheDocument()
    expect(screen.getByLabelText('Part (c) answer')).toBeInTheDocument()
    expect(
      await waitFor(() => {
        const element = document.querySelector('math-field')
        expect(element).not.toBeNull()
        return element
      }),
    ).not.toBeNull()
    expect(partLetter(2)).toBe('c')
  })

  test('typing updates only the edited part', () => {
    const onChange = vi.fn()
    render(<CompositeAnswer input={INPUT} value={null} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Part (a) answer'), {
      target: { value: '4' },
    })
    expect(onChange).toHaveBeenCalledWith(['4', '', ''])
  })

  test('response helpers', () => {
    expect(isCompositeInput({ widget: 'composite', parts: [] })).toBe(true)
    expect(isCompositeInput({ widget: 'math' })).toBe(false)
    expect(compositeResponseComplete(null, INPUT)).toBe(false)
    expect(compositeResponseComplete(['', '', ''], INPUT)).toBe(false)
    expect(compositeResponseComplete(['', 'x', ''], INPUT)).toBe(true)
  })
})

describe('CompositeAnswer controlled flow', () => {
  test('emitted response feeds back without losing other parts', () => {
    function Harness() {
      const [value, setValue] = useState<string[] | null>(null)
      return (
        <CompositeAnswer
          input={INPUT}
          value={value}
          onChange={(next) => setValue(next)}
        />
      )
    }
    render(<Harness />)
    const partA = screen.getByLabelText('Part (a) answer') as HTMLInputElement
    fireEvent.change(partA, { target: { value: '4' } })
    const partC = screen.getByLabelText('Part (c) answer') as HTMLInputElement
    fireEvent.change(partC, { target: { value: 'increasing' } })
    expect(partA.value).toBe('4')
    expect(partC.value).toBe('increasing')
  })
})

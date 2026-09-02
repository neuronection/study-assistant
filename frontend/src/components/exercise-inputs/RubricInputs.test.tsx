import { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import {
  RubricStepInput,
  rubricResponseComplete,
} from './RubricInputs'
import type { ExerciseStepInput } from '@/lib/api'

const LINES_INPUT: ExerciseStepInput = {
  widget: 'lines',
  kind: 'error_spot',
  lines: ['$d/dx(-3x^2) = 6x$', 'At $x=1$: $6$'],
  requires_fix: true,
}

const PLAIN_LINES_INPUT: ExerciseStepInput = {
  widget: 'lines',
  kind: 'error_spot',
  lines: ['$d/dx(-3x^2) = 6x$', 'At $x=1$: $6$'],
}

describe('RubricStepInput error-spot lines', () => {
  test('pick emits a spot response; fix completes it', async () => {
    const onChange = vi.fn()
    function Harness() {
      const [value, setValue] = useState('')
      return (
        <RubricStepInput
          input={LINES_INPUT}
          value={value}
          onChange={(next) => {
            onChange(next)
            setValue(next)
          }}
        />
      )
    }
    render(<Harness />)
    const radios = screen.getAllByRole('radio')
    fireEvent.click(radios[0])
    expect(onChange).toHaveBeenLastCalledWith(
      JSON.stringify({ picked: [0], fix: '' }),
    )
    const fixField = (await waitFor(() => {
      const element = document.querySelector('math-field')
      expect(element).not.toBeNull()
      return element!
    })) as HTMLElement & { value: string }
    fixField.value = '-6x'
    fixField.dispatchEvent(new Event('input', { bubbles: true }))
    await waitFor(() =>
      expect(onChange).toHaveBeenLastCalledWith(
        JSON.stringify({ picked: [0], fix: '-6x' }),
      ),
    )
  })

  test('pick again keeps the typed fix', () => {
    const onChange = vi.fn()
    render(
      <RubricStepInput
        input={LINES_INPUT}
        value={JSON.stringify({ picked: [0], fix: '-6x' })}
        onChange={onChange}
      />
    )
    const radios = screen.getAllByRole('radio')
    fireEvent.click(radios[1])
    expect(onChange).toHaveBeenLastCalledWith(
      JSON.stringify({ picked: [1], fix: '-6x' }),
    )
  })

  test('no fix field without requires_fix', () => {
    const onChange = vi.fn()
    render(<RubricStepInput input={PLAIN_LINES_INPUT} value="" onChange={onChange} />)
    expect(document.querySelector('math-field')).toBeNull()
    fireEvent.click(screen.getAllByRole('radio')[1])
    expect(onChange).toHaveBeenLastCalledWith(
      JSON.stringify({ picked: [1], fix: '' }),
    )
  })
})

describe('rubricResponseComplete', () => {
  test('requires a pick and, when flagged, the fix', () => {
    expect(rubricResponseComplete(LINES_INPUT, '')).toBe(false)
    expect(
      rubricResponseComplete(LINES_INPUT, JSON.stringify({ picked: [0], fix: '' })),
    ).toBe(false)
    expect(
      rubricResponseComplete(LINES_INPUT, JSON.stringify({ picked: [0], fix: '-6x' })),
    ).toBe(true)
    expect(
      rubricResponseComplete(PLAIN_LINES_INPUT, JSON.stringify({ picked: [1], fix: '' })),
    ).toBe(true)
  })
})

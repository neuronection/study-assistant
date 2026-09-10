import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import {
  ExerciseStructuralInput,
  isStructuralInput,
  structuralResponseComplete,
} from './ExerciseInput'
import type { ExerciseStepInput } from '@/lib/api'

vi.mock('@/components/blocks/BlockRenderer', () => ({
  BlockRenderer: ({ blocks }: { blocks?: { md?: string }[] }) => (
    <span>{(blocks ?? []).map((block) => block.md ?? '').join('')}</span>
  ),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, unknown>) => {
      if (!vars) {
        return key
      }
      const suffix = Object.values(vars).map((value) => ` ${value}`).join('')
      return `${key}${suffix}`
    },
  }),
}))

describe('ExerciseInput dispatch', () => {
  test('matching emits picks per left', () => {
    const input: ExerciseStepInput = {
      widget: 'matching',
      lefts: ['$x^2$', '$\\sin x$'],
      rights: [
        { index: 1, label: '$\\cos x$' },
        { index: 0, label: '$2x$' },
      ],
    }
    const onChange = vi.fn()
    render(<ExerciseStructuralInput input={input} value={null} onChange={onChange} />)
    const selects = screen.getAllByRole('combobox')
    expect(selects).toHaveLength(2)
    fireEvent.change(selects[0], { target: { value: '0' } })
    expect(onChange).toHaveBeenCalledWith([0, -1])
    expect(isStructuralInput(input)).toBe(true)
    expect(structuralResponseComplete(input, [0, -1])).toBe(false)
    expect(structuralResponseComplete(input, [0, 1])).toBe(true)
  })

  test('ordering reorders via move buttons', () => {
    const input: ExerciseStepInput = {
      widget: 'ordering',
      items: [
        { id: 2, label: 'C' },
        { id: 0, label: 'A' },
        { id: 1, label: 'B' },
      ],
    }
    const onChange = vi.fn()
    render(
      <ExerciseStructuralInput input={input} value={[2, 0, 1]} onChange={onChange} />
    )
    fireEvent.click(screen.getByRole('button', { name: 'exercises.moveDown 1' }))
    expect(onChange).toHaveBeenCalledWith([0, 2, 1])
    fireEvent.click(screen.getByRole('button', { name: 'exercises.moveUp 3' }))
    expect(onChange).toHaveBeenCalledWith([2, 1, 0])
    expect(structuralResponseComplete(input, [0, 1, 2])).toBe(true)
  })

  test('categorize emits category picks', () => {
    const input: ExerciseStepInput = {
      widget: 'categorize',
      categories: ['even', 'odd'],
      items: ['$x^2$', '$x^3$'],
    }
    const onChange = vi.fn()
    render(<ExerciseStructuralInput input={input} value={null} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'exercises.categorizeOption 2 odd' }))
    expect(onChange).toHaveBeenCalledWith([-1, 1])
    expect(structuralResponseComplete(input, [0, 1])).toBe(true)
  })

  test('fill_blank renders inputs per numbered blank', () => {
    const input: ExerciseStepInput = {
      widget: 'fill_blank',
      prompt_md: 'Derivative of $x^n$ is {{1}}; constant gives {{2}}.',
      blank_count: 2,
    }
    const onChange = vi.fn()
    render(<ExerciseStructuralInput input={input} value={null} onChange={onChange} />)
    const first = screen.getByRole('textbox', { name: 'exercises.blankLabel 1' })
    fireEvent.change(first, { target: { value: 'nx^{n-1}' } })
    expect(onChange).toHaveBeenCalledWith(['nx^{n-1}', ''])
    expect(structuralResponseComplete(input, ['a', ''])).toBe(false)
    expect(structuralResponseComplete(input, ['a', 'b'])).toBe(true)
    expect(isStructuralInput({ widget: 'math' })).toBe(false)
  })
})

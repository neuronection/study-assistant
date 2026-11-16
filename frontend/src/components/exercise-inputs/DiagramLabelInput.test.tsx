import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { DiagramLabelInput } from './DiagramLabelInput'
import type { ExerciseStepInput } from '@/lib/api'

const INPUT: ExerciseStepInput = {
  widget: 'diagram_label',
  image_sha: 'a'.repeat(64),
  hotspots: [
    { id: 'a', x: 0.1, y: 0.1, w: 0.2, h: 0.2 },
    { id: 'b', x: 0.5, y: 0.4, w: 0.2, h: 0.2 },
  ],
  labels: ['Nucleus', 'Membrane', 'Cytoplasm'],
  mode: 'click',
}

describe('DiagramLabelInput', () => {
  test('places a label on a hotspot', () => {
    const onChange = vi.fn()
    render(<DiagramLabelInput input={INPUT} value={[]} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Nucleus' }))
    fireEvent.click(screen.getByRole('button', { name: 'Region 1' }))
    expect(onChange).toHaveBeenCalledWith([{ hotspot_id: 'a', label: 'Nucleus' }])
  })

  test('marks placed labels and reassigns', () => {
    const onChange = vi.fn()
    render(
      <DiagramLabelInput
        input={INPUT}
        value={[{ hotspot_id: 'a', label: 'Nucleus' }]}
        onChange={onChange}
      />,
    )
    expect(
      screen.getByRole('button', { name: 'Region 1: Nucleus' }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Membrane' }))
    fireEvent.click(screen.getByRole('button', { name: 'Region 1: Nucleus' }))
    expect(onChange).toHaveBeenCalledWith([{ hotspot_id: 'a', label: 'Membrane' }])
  })

  test('is disabled after submission', () => {
    render(
      <DiagramLabelInput
        input={INPUT}
        value={[]}
        onChange={vi.fn()}
        disabled
      />,
    )
    expect(screen.getByRole('button', { name: 'Nucleus' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Region 1' })).toBeDisabled()
  })
})

import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, test, vi } from 'vitest'

import {
  GraphReadAnswer,
  chartFigureFromStem,
  chartXs,
  isGraphReadInput,
  nearestSampleIndex,
  type GraphReadInput,
  type GraphReadResponse,
} from './GraphReadAnswer'

const FIGURE: Record<string, unknown> = {
  data: [{ x: [0, 1, 2, 3], y: [0, 1, 0, -1], mode: 'lines', type: 'scatter' }],
}

const VALUE_INPUT: GraphReadInput = { mode: 'value' }
const POINT_INPUT: GraphReadInput = { mode: 'point' }

describe('GraphReadAnswer', () => {
  test('value mode renders a numeric input and emits parsed numbers', () => {
    const onChange = vi.fn()
    function Harness() {
      const [response, setResponse] = useState<GraphReadResponse | null>(null)
      return (
        <GraphReadAnswer
          figure={FIGURE}
          mode={VALUE_INPUT.mode}
          xs={chartXs(FIGURE)}
          response={response}
          onChange={(next) => {
            onChange(next)
            setResponse(next)
          }}
        />
      )
    }
    render(<Harness />)
    const input = screen.getByLabelText('Your reading') as HTMLInputElement
    fireEvent.change(input, { target: { value: '0.91' } })
    expect(onChange).toHaveBeenLastCalledWith({ value: 0.91 })
    fireEvent.change(input, { target: { value: '' } })
    expect(onChange).toHaveBeenLastCalledWith({})
  })

  test('point mode shows the click hint', () => {
    render(
      <GraphReadAnswer
        figure={FIGURE}
        mode={POINT_INPUT.mode}
        xs={chartXs(FIGURE)}
        response={null}
      />,
    )
    expect(screen.getByText('Click the point on the graph')).toBeInTheDocument()
  })

  test('helpers', () => {
    expect(isGraphReadInput({ widget: 'graph_read', mode: 'value' })).toBe(true)
    expect(isGraphReadInput({ widget: 'graph_read' })).toBe(false)
    expect(nearestSampleIndex([0, 1, 2, 3], 1.6)).toBe(2)
    expect(chartFigureFromStem([
      { type: 'text' },
      { type: 'chart', plotly: FIGURE },
    ])).toEqual(FIGURE)
    expect(chartXs(FIGURE)).toEqual([0, 1, 2, 3])
    expect(chartXs(null)).toEqual([])
  })
})

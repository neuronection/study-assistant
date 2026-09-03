import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import {
  TableFillAnswer,
  emptyTableGrid,
  isTableFillInput,
  tableGridComplete,
  type TableFillInput,
} from './TableFillAnswer'

const INPUT: TableFillInput = {
  headers: ['p', 'q', 'p and q'],
  row_labels: ['row 1', 'row 2'],
  cells: [
    [
      { kind: 'locked', text: 'true' },
      { kind: 'locked', text: 'true' },
      { kind: 'text' },
    ],
    [
      { kind: 'locked', text: 'true' },
      { kind: 'locked', text: 'false' },
      { kind: 'text' },
    ],
  ],
}

describe('TableFillAnswer', () => {
  test('renders headers, locked text and inputs for fillable cells', () => {
    render(<TableFillAnswer input={INPUT} value={null} onChange={vi.fn()} />)
    expect(screen.getByRole('columnheader', { name: 'p and q' })).toBeInTheDocument()
    expect(screen.getAllByText('true')).toHaveLength(3)
    const inputs = screen.getAllByRole('textbox')
    expect(inputs).toHaveLength(2)
  })

  test('typing updates only the edited cell', () => {
    const onChange = vi.fn()
    render(<TableFillAnswer input={INPUT} value={null} onChange={onChange} />)
    const inputs = screen.getAllByRole('textbox')
    fireEvent.change(inputs[1], { target: { value: 'false' } })
    expect(onChange).toHaveBeenCalledWith([
      ['', '', ''],
      ['', '', 'false'],
    ])
  })

  test('value flows back into the inputs', () => {
    render(
      <TableFillAnswer
        input={INPUT}
        value={[
          ['', '', 'true'],
          ['', '', ''],
        ]}
        onChange={vi.fn()}
      />,
    )
    const inputs = screen.getAllByRole('textbox') as HTMLInputElement[]
    expect(inputs[0].value).toBe('true')
    expect(inputs[1].value).toBe('')
  })

  test('grid helpers', () => {
    expect(isTableFillInput({ widget: 'table_fill' })).toBe(true)
    expect(isTableFillInput({ widget: 'math' })).toBe(false)
    expect(tableGridComplete(null, INPUT)).toBe(false)
    expect(tableGridComplete(emptyTableGrid(INPUT), INPUT)).toBe(false)
    const grid = emptyTableGrid(INPUT)
    grid[1][2] = 'false'
    expect(tableGridComplete(grid, INPUT)).toBe(true)
  })
})

describe('table submit gating in the runner', () => {
  test('complete grid keeps unchanged cells empty-safe', async () => {
    const onChange = vi.fn()
    render(<TableFillAnswer input={INPUT} value={null} onChange={onChange} />)
    const inputs = screen.getAllByRole('textbox')
    fireEvent.change(inputs[0], { target: { value: 'true' } })
    await waitFor(() => expect(onChange).toHaveBeenCalled())
    expect(tableGridComplete(onChange.mock.calls[0][0], INPUT)).toBe(true)
  })
})

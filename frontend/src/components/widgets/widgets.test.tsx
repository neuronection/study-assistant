import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import { getWidgetComponent } from '@/components/widgets/registry'

const visuals = vi.hoisted(() => ({
  newPlot: vi.fn(),
  purge: vi.fn(),
  initBoard: vi.fn(() => ({ jc: { parse: vi.fn() } })),
  freeBoard: vi.fn(),
}))

vi.mock('plotly.js-dist-min', () => ({
  default: { newPlot: visuals.newPlot, purge: visuals.purge },
}))
vi.mock('jsxgraph', () => ({
  JSXGraph: { initBoard: visuals.initBoard, freeBoard: visuals.freeBoard },
}))

describe('widget registry', () => {
  test('resolves known widget names and rejects unknown ones', () => {
    expect(getWidgetComponent('checklist')).toBeDefined()
    expect(getWidgetComponent('choice')).toBeDefined()
    expect(getWidgetComponent('slider')).toBeDefined()
    expect(getWidgetComponent('equation_input')).toBeDefined()
    expect(getWidgetComponent('numberline')).toBeDefined()
    expect(getWidgetComponent('chart')).toBeDefined()
    expect(getWidgetComponent('geo')).toBeDefined()
    expect(getWidgetComponent('hologram')).toBeUndefined()
  })
})

describe('chart and geo widgets', () => {
  test('renders a chart widget through PlotlyChart', async () => {
    render(
      <BlockRenderer
        blocks={[
          {
            type: 'widget',
            widget: 'chart',
            id: 'w7',
            props: { plotly: { data: [{ y: [1, 2] }] } },
          },
        ]}
      />,
    )
    await waitFor(() => expect(visuals.newPlot).toHaveBeenCalledTimes(1))
    expect(visuals.newPlot.mock.calls[0][1]).toEqual([{ y: [1, 2] }])
  })

  test('renders a geo widget through JsxGraphBoard', async () => {
    render(
      <BlockRenderer
        blocks={[
          { type: 'widget', widget: 'geo', id: 'w8', props: { jsxgraph: 'A:=point(0,0);' } },
        ]}
      />,
    )
    await waitFor(() => expect(visuals.initBoard).toHaveBeenCalledTimes(1))
  })
})

describe('widget blocks in BlockRenderer', () => {
  test('renders a checklist widget and toggles items', () => {
    render(
      <BlockRenderer
        blocks={[
          {
            type: 'widget',
            widget: 'checklist',
            id: 'w1',
            props: { prompt: 'Which steps did you apply?', items: ['factor', 'chain rule'] },
          },
        ]}
      />,
    )
    expect(screen.getByText('Which steps did you apply?')).toBeInTheDocument()
    const factor = screen.getByLabelText('factor') as HTMLInputElement
    expect(factor).not.toBeChecked()
    fireEvent.click(factor)
    expect(factor).toBeChecked()
  })

  test('emits widget state through onWidgetStateChange', () => {
    const onChange = vi.fn()
    render(
      <BlockRenderer
        blocks={[
          {
            type: 'widget',
            widget: 'checklist',
            id: 'w9',
            props: { prompt: 'Which?', items: ['a', 'b'] },
          },
        ]}
        onWidgetStateChange={onChange}
      />,
    )
    fireEvent.click(screen.getByLabelText('a'))
    expect(onChange).toHaveBeenCalledWith('w9', { checked: ['a'] })
  })

  test('renders a choice widget as a radio group', () => {
    render(
      <BlockRenderer
        blocks={[
          {
            type: 'widget',
            widget: 'choice',
            id: 'w2',
            props: { prompt: 'Pick one', options: ['a', 'b', 'c'] },
          },
        ]}
      />,
    )
    const option = screen.getByLabelText('b') as HTMLInputElement
    expect(option).toHaveAttribute('type', 'radio')
    fireEvent.click(option)
    expect(option).toBeChecked()
  })

  test('renders a slider widget with its initial value', () => {
    render(
      <BlockRenderer
        blocks={[
          {
            type: 'widget',
            widget: 'slider',
            id: 'w3',
            props: { prompt: 'Rate it', min: 0, max: 10, step: 1, unit: 'pts' },
          },
        ]}
      />,
    )
    expect(screen.getByText('Rate it')).toBeInTheDocument()
    expect(screen.getByText(/pts/)).toBeInTheDocument()
  })

  test('renders an equation input widget and captures typing', () => {
    render(
      <BlockRenderer
        blocks={[
          {
            type: 'widget',
            widget: 'equation_input',
            id: 'w4',
            props: { prompt: 'f(x) =', placeholder: '2x + 1' },
          },
        ]}
      />,
    )
    const input = screen.getByPlaceholderText('2x + 1') as HTMLInputElement
    fireEvent.change(input, { target: { value: '3x' } })
    expect(input.value).toBe('3x')
  })

  test('renders a numberline widget', () => {
    render(
      <BlockRenderer
        blocks={[
          { type: 'widget', widget: 'numberline', id: 'w5', props: { min: -5, max: 5 } },
        ]}
      />,
    )
    expect(screen.getByText('Click to mark points')).toBeInTheDocument()
    expect(document.querySelector('svg')).not.toBeNull()
  })

  test('renders unknown widget names as a fallback preserving the name', () => {
    render(
      <BlockRenderer
        blocks={[{ type: 'widget', widget: 'hologram', id: 'w6', props: {} }]}
      />,
    )
    expect(screen.getByText(/hologram/)).toBeInTheDocument()
  })
})

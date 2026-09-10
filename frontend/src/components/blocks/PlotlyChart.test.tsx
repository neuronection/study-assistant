import { render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { BlockRenderer } from './BlockRenderer'
import { PlotlyChart } from './PlotlyChart'

type PlotFn = (
  root: HTMLElement,
  data: unknown,
  layout?: Record<string, unknown>,
  config?: Record<string, unknown>,
) => Promise<unknown>

const { newPlot, purge, resize } = vi.hoisted(() => ({
  newPlot: vi.fn<PlotFn>(() => Promise.resolve()),
  purge: vi.fn<(root: HTMLElement) => void>(),
  resize: vi.fn<(root: HTMLElement) => void>(),
}))

vi.mock('plotly.js-dist-min', () => ({
  default: { newPlot, purge, Plots: { resize } },
}))

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe('PlotlyChart', () => {
  test('renders an interactive chart via a lazy plotly import', async () => {
    render(<PlotlyChart figure={{ data: [{ y: [1, 2, 3] }], layout: { title: 'T' } }} />)
    await waitFor(() => expect(newPlot).toHaveBeenCalledTimes(1))
    const [element, data, layout] = newPlot.mock.calls[0]
    expect(element).toBeInstanceOf(HTMLElement)
    expect(data).toEqual([{ y: [1, 2, 3] }])
    expect(layout).toMatchObject({ paper_bgcolor: 'rgba(0,0,0,0)', title: 'T' })
  })

  test('disables transitions when reduced motion is preferred', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    render(<PlotlyChart figure={{ data: [{ y: [1] }] }} />)
    await waitFor(() => expect(newPlot).toHaveBeenCalledTimes(1))
    const layout = newPlot.mock.calls[0][2] as Record<string, unknown>
    expect(layout.transition).toEqual({ duration: 0 })
  })

  test('reflows the plot when the container resizes', async () => {
    render(<PlotlyChart figure={{ data: [{ y: [1] }] }} />)
    await waitFor(() => expect(resize).toHaveBeenCalledTimes(1))
  })
})

describe('chart blocks', () => {
  test('render a chart block through the shared PlotlyChart', async () => {
    render(
      <BlockRenderer
        blocks={[{ type: 'chart', plotly: { data: [{ y: [5, 6] }] } }]}
      />,
    )
    await waitFor(() => expect(newPlot).toHaveBeenCalledTimes(1))
    expect(newPlot.mock.calls[0][1]).toEqual([{ y: [5, 6] }])
  })
})

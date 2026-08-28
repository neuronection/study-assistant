import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { BlockRenderer } from './BlockRenderer'
import { JsxGraphBoard } from './JsxGraphBoard'

const mocks = vi.hoisted(() => {
  const parse = vi.fn()
  return {
    initBoard: vi.fn(() => ({ jc: { parse } })),
    freeBoard: vi.fn(),
    parse,
  }
})

vi.mock('jsxgraph', () => ({
  JSXGraph: { initBoard: mocks.initBoard, freeBoard: mocks.freeBoard },
}))

afterEach(() => {
  vi.clearAllMocks()
})

describe('JsxGraphBoard', () => {
  test('initializes a board and parses the construction script', async () => {
    render(<JsxGraphBoard script="f(x):=sin(x);" />)
    await waitFor(() => expect(mocks.initBoard).toHaveBeenCalledTimes(1))
    expect(mocks.initBoard).toHaveBeenCalledWith(
      expect.stringMatching(/^jxg-/),
      expect.objectContaining({ axis: true, showCopyright: false }),
    )
    expect(mocks.parse).toHaveBeenCalledWith('f(x):=sin(x);')
  })

  test('frees the board on unmount', async () => {
    const { unmount } = render(<JsxGraphBoard script="f(x):=sin(x);" />)
    await waitFor(() => expect(mocks.initBoard).toHaveBeenCalledTimes(1))
    unmount()
    await waitFor(() => expect(mocks.freeBoard).toHaveBeenCalledTimes(1))
  })
})

describe('geo blocks', () => {
  test('render a geo block through the shared JsxGraphBoard', async () => {
    render(<BlockRenderer blocks={[{ type: 'geo', jsxgraph: 'A:=point(0,0);' }]} />)
    await waitFor(() => expect(mocks.initBoard).toHaveBeenCalledTimes(1))
  })

  test('render an empty geo block as a placeholder', () => {
    render(<BlockRenderer blocks={[{ type: 'geo', jsxgraph: '   ' }]} />)
    expect(screen.getByText('Geometry · JSXGraph')).toBeInTheDocument()
    expect(mocks.initBoard).not.toHaveBeenCalled()
  })
})

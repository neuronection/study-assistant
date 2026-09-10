import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import {
  DrawCanvas,
  exportDrawing,
  fitView,
  strokeBounds,
  strokesToPng,
  viewFromFocus,
  type Stroke,
  type ViewBox,
} from '@/components/canvas/DrawCanvas'

function drawStroke(canvas: HTMLElement, offsets: Array<[number, number]>) {
  const rect = canvas.getBoundingClientRect()
  fireEvent.pointerDown(canvas, {
    pointerId: 1,
    clientX: rect.left + offsets[0][0],
    clientY: rect.top + offsets[0][1],
    pressure: 0.5,
  })
  for (const [x, y] of offsets.slice(1)) {
    fireEvent.pointerMove(canvas, {
      pointerId: 1,
      clientX: rect.left + x,
      clientY: rect.top + y,
      pressure: 0.5,
    })
  }
  fireEvent.pointerUp(canvas, { pointerId: 1 })
}

describe('DrawCanvas', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  test('commits a stroke with the chosen color and width', () => {
    const onChange = vi.fn()
    render(<DrawCanvas strokes={[]} onChange={onChange} />)

    const colors = screen.getAllByRole('button', { name: 'Ink color' })
    fireEvent.click(colors[1])
    fireEvent.click(screen.getAllByRole('button', { name: /pen width/i })[0])
    const canvas = screen.getByLabelText('Handwriting canvas')
    drawStroke(canvas, [
      [10, 10],
      [40, 40],
    ])

    expect(onChange).toHaveBeenCalledTimes(1)
    const stroke: Stroke = onChange.mock.calls[0][0][0]
    expect(stroke.points.length).toBe(2)
    expect(stroke.tool).toBe('pen')
  })

  test('eraser removes intersecting strokes', () => {
    const initial: Stroke[] = [
      { points: [[50, 50], [120, 50]], color: '#1a1a1a', width: 4, tool: 'pen' },
      { points: [[400, 300], [420, 300]], color: '#1a1a1a', width: 4, tool: 'pen' },
    ]
    let strokes = initial
    const onChange = vi.fn((next: Stroke[]) => {
      strokes = next
    })
    const { rerender } = render(<DrawCanvas strokes={strokes} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'Eraser' }))
    const canvas = screen.getByLabelText('Handwriting canvas')
    canvas.getBoundingClientRect = () => new DOMRect(0, 0, 1024, 480)
    fireEvent.pointerDown(canvas, {
      pointerId: 2,
      clientX: 60,
      clientY: 50,
      pressure: 0.5,
    })
    fireEvent.pointerUp(canvas, { pointerId: 2 })

    expect(onChange).toHaveBeenCalled()
    rerender(<DrawCanvas strokes={strokes} onChange={onChange} />)
    expect(strokes.length).toBe(1)
    expect(strokes[0].points[0][0]).toBe(400)
  })

  test('undo pops the last stroke and redo restores it', () => {
    const initial: Stroke[] = [
      { points: [[10, 10]], color: '#1a1a1a', width: 2, tool: 'pen' },
    ]
    let strokes = initial
    const onChange = vi.fn((next: Stroke[]) => {
      strokes = next
    })
    const { rerender } = render(<DrawCanvas strokes={strokes} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    rerender(<DrawCanvas strokes={strokes} onChange={onChange} />)
    expect(strokes).toEqual([])

    fireEvent.click(screen.getByRole('button', { name: 'Redo stroke' }))
    rerender(<DrawCanvas strokes={strokes} onChange={onChange} />)
    expect(strokes).toEqual(initial)
  })

  test('clear asks for confirmation', async () => {
    const initial: Stroke[] = [{ points: [[10, 10]], color: '#1a1a1a', width: 2 }]
    const onChange = vi.fn()
    render(<DrawCanvas strokes={initial} onChange={onChange} />)

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    const dialog = await screen.findByRole('dialog', { name: 'Clear' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Clear' }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([]))
  })

  test('wheel over the canvas zooms and the bar reflects the percent', () => {
    render(<DrawCanvas strokes={[]} onChange={vi.fn()} />)
    const canvas = screen.getByLabelText('Handwriting canvas')
    const viewport = canvas.parentElement as HTMLElement
    viewport.getBoundingClientRect = () => new DOMRect(0, 0, 1024, 480)
    fireEvent.resize(window)
    expect(screen.getByTestId('canvas-zoom').textContent).toBe('100%')

    fireEvent.wheel(canvas, { deltaY: -240 })
    expect(Number(screen.getByTestId('canvas-zoom').textContent?.replace('%', ''))).toBeGreaterThan(100)
  })

  test('actual-size button returns the zoom to 100%', () => {
    render(<DrawCanvas strokes={[]} onChange={vi.fn()} />)
    const canvas = screen.getByLabelText('Handwriting canvas')
    ;(canvas.parentElement as HTMLElement).getBoundingClientRect = () =>
      new DOMRect(0, 0, 1024, 480)
    fireEvent.resize(window)

    fireEvent.wheel(canvas, { deltaY: -240 })
    fireEvent.click(screen.getByRole('button', { name: 'Actual size (100%)' }))
    expect(screen.getByTestId('canvas-zoom').textContent).toBe('100%')
  })

  test('middle-button drag pans the view so later strokes shift coordinates', () => {
    const onChange = vi.fn()
    render(<DrawCanvas strokes={[]} onChange={onChange} />)
    const canvas = screen.getByLabelText('Handwriting canvas')
    ;(canvas.parentElement as HTMLElement).getBoundingClientRect = () =>
      new DOMRect(0, 0, 1024, 480)
    fireEvent.resize(window)

    fireEvent.pointerDown(canvas, { pointerId: 3, button: 1, buttons: 4, clientX: 100, clientY: 100 })
    fireEvent.pointerMove(canvas, { pointerId: 3, buttons: 4, clientX: 160, clientY: 130 })
    fireEvent.pointerUp(canvas, { pointerId: 3, button: 1, buttons: 4, clientX: 160, clientY: 130 })

    drawStroke(canvas, [[10, 10], [20, 10]])
    expect(onChange).toHaveBeenCalled()
    const stroke: Stroke = onChange.mock.calls[0][0][0]
    expect(stroke.points[0][0]).toBeCloseTo(-50)
    expect(stroke.points[0][1]).toBeCloseTo(-20)
  })

  test('pan tool drag pans without drawing', () => {
    const onChange = vi.fn()
    render(<DrawCanvas strokes={[]} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Pan canvas (middle-drag or hold Space)' }))
    const canvas = screen.getByLabelText('Handwriting canvas')
    ;(canvas.parentElement as HTMLElement).getBoundingClientRect = () =>
      new DOMRect(0, 0, 1024, 480)
    fireEvent.resize(window)

    fireEvent.pointerDown(canvas, { pointerId: 4, button: 0, clientX: 50, clientY: 50 })
    fireEvent.pointerMove(canvas, { pointerId: 4, clientX: 90, clientY: 20 })
    fireEvent.pointerUp(canvas, { pointerId: 4, clientX: 90, clientY: 20 })
    expect(onChange).not.toHaveBeenCalled()
  })

  test('fit scales zoomed content back into the viewport', () => {
    const strokes: Stroke[] = [{ points: [[0, 0], [900, 10]], color: '#000', width: 2 }]
    render(<DrawCanvas strokes={strokes} onChange={vi.fn()} />)
    const canvas = screen.getByLabelText('Handwriting canvas')
    ;(canvas.parentElement as HTMLElement).getBoundingClientRect = () =>
      new DOMRect(0, 0, 1024, 480)
    fireEvent.resize(window)

    fireEvent.wheel(canvas, { deltaY: -400 })
    fireEvent.click(screen.getByRole('button', { name: 'Fit drawing' }))
    const percent = Number(screen.getByTestId('canvas-zoom').textContent?.replace('%', ''))
    expect(percent).toBeGreaterThan(100)
    expect(percent).toBeLessThanOrEqual(200)
  })

  test('fullscreen toggle button calls onToggleFullscreen', () => {
    const onToggle = vi.fn()
    render(
      <DrawCanvas strokes={[]} onChange={vi.fn()} fullscreen onToggleFullscreen={onToggle} />
    )
    fireEvent.click(screen.getByRole('button', { name: 'Exit fullscreen' }))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })
})

describe('view math', () => {
  test('strokeBounds expands by stroke width and padding', () => {
    const strokes: Stroke[] = [{ points: [[10, 10], [200, 700]], color: '#000', width: 2 }]
    const bounds = strokeBounds(strokes, 24)
    expect(bounds).toEqual({ x: -16, y: -16, width: 242, height: 742 })
    expect(strokeBounds([])).toBeNull()
  })

  test('fitView scales content into the viewport and centers it', () => {
    const bounds: ViewBox = { x: 0, y: 0, width: 500, height: 250 }
    const view = fitView(bounds, { width: 1000, height: 500 })
    expect(view.zoom).toBe(2)
    expect(view.x).toBe(0)
    expect(view.y).toBe(0)
  })

  test('viewFromFocus never exceeds 100% zoom', () => {
    const small = viewFromFocus({ x: 100, y: 50, width: 300, height: 200 }, { width: 1024, height: 480 })
    expect(small.zoom).toBe(1)
    const large = viewFromFocus({ x: 0, y: 0, width: 3000, height: 2000 }, { width: 600, height: 400 })
    expect(large.zoom).toBeLessThan(1)
  })
})

describe('exportDrawing', () => {
  const originalGetContext = HTMLCanvasElement.prototype.getContext
  const originalToDataURL = HTMLCanvasElement.prototype.toDataURL

  afterEach(() => {
    HTMLCanvasElement.prototype.getContext = originalGetContext
    HTMLCanvasElement.prototype.toDataURL = originalToDataURL
  })

  function fakeContext() {
    const calls = {
      fillRect: vi.fn(),
      translate: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
    }
    const context = {
      fillStyle: '',
      strokeStyle: '',
      lineWidth: 0,
      lineCap: '',
      lineJoin: '',
      ...calls,
    }
    HTMLCanvasElement.prototype.getContext = (() =>
      context as unknown as CanvasRenderingContext2D) as unknown as typeof HTMLCanvasElement.prototype.getContext
    HTMLCanvasElement.prototype.toDataURL = () => 'data:image/png;base64,AAA'
    return calls
  }

  test('crops the export to the stroke bounds plus padding', () => {
    const calls = fakeContext()
    const strokes: Stroke[] = [{ points: [[10, 10], [200, 700]], color: '#000', width: 2 }]
    const exported = exportDrawing(strokes)
    expect(exported).not.toBeNull()
    expect(exported!.view).toEqual({ x: -16, y: -16, width: 242, height: 742 })
    expect(calls.translate).toHaveBeenCalledWith(16, 16)
    expect(calls.moveTo).toHaveBeenCalledWith(10, 10)
  })

  test('returns null for empty strokes or when the context is unavailable', () => {
    expect(exportDrawing([])).toBeNull()
    HTMLCanvasElement.prototype.getContext = () => null
    expect(strokesToPng([{ points: [[0, 0]], color: '#000', width: 2 }])).toBeNull()
  })
})

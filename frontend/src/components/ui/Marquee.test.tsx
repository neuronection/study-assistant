import { render } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import {
  MarqueeBand,
  hitTestIds,
  marqueeRect,
  rectsIntersect,
  useMarquee,
} from './Marquee'

describe('rect math', () => {
  test('rectsIntersect detects overlap and non-overlap', () => {
    const a = { left: 0, top: 0, right: 10, bottom: 10 }
    expect(rectsIntersect(a, { left: 5, top: 5, right: 15, bottom: 15 })).toBe(true)
    expect(rectsIntersect(a, { left: 10, top: 0, right: 20, bottom: 10 })).toBe(
      false
    )
  })

  test('marqueeRect normalizes drag direction', () => {
    expect(marqueeRect(10, 10, 30, 40)).toEqual({
      left: 10,
      top: 10,
      right: 30,
      bottom: 40,
    })
    expect(marqueeRect(30, 40, 10, 10)).toEqual({
      left: 10,
      top: 10,
      right: 30,
      bottom: 40,
    })
  })
})

describe('hitTestIds', () => {
  test('returns ids of elements intersecting the band', () => {
    const container = document.createElement('div')
    for (const [id, left, top] of [
      ['one', 0, 0],
      ['two', 100, 0],
      ['three', 50, 50],
    ] as const) {
      const element = document.createElement('div')
      element.setAttribute('data-selectable-id', String(id))
      element.getBoundingClientRect = () =>
        ({
          left,
          top,
          right: left + 20,
          bottom: top + 20,
          width: 20,
          height: 20,
          x: left,
          y: top,
          toJSON: () => ({}),
        }) as DOMRect
      container.appendChild(element)
    }
    const hits = hitTestIds(container, { left: 0, top: 0, right: 60, bottom: 60 })
    expect(hits).toEqual(['one', 'three'])
  })
})

function MarqueeHost({
  onSelect,
  getBaseSelection,
}: {
  onSelect: (ids: string[], phase: 'start' | 'drag' | 'end') => void
  getBaseSelection?: () => Set<string>
}) {
  const ref = { current: null as HTMLElement | null }
  const { band } = useMarquee({
    enabled: true,
    containerRef: ref,
    getBaseSelection: getBaseSelection ?? (() => new Set<string>()),
    onSelect,
  })
  return (
    <div>
      <div ref={(node) => {
        ref.current = node
      }} data-testid="pane">
        <button type="button" data-selectable-id="one">
          one
        </button>
        <button type="button" data-selectable-id="two">
          two
        </button>
        <span data-testid="empty">padding</span>
      </div>
      <MarqueeBand band={band} />
    </div>
  )
}

function mouseEvent(type: string, x: number, y: number, extra: MouseEventInit = {}) {
  return new MouseEvent(type, {
    bubbles: true,
    clientX: x,
    clientY: y,
    button: 0,
    ...extra,
  })
}

describe('useMarquee', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Element.prototype.getBoundingClientRect = () =>
      ({
        left: 0,
        top: 0,
        right: 100,
        bottom: 30,
        width: 100,
        height: 30,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }) as DOMRect
  })

  test('drag over empty background selects intersecting items', () => {
    const onSelect = vi.fn()
    const { getByTestId } = render(<MarqueeHost onSelect={onSelect} />)
    const pane = getByTestId('pane')

    pane.dispatchEvent(mouseEvent('mousedown', 0, 0))
    window.dispatchEvent(mouseEvent('mousemove', 50, 10))
    window.dispatchEvent(mouseEvent('mouseup', 50, 10))

    expect(onSelect).toHaveBeenCalledWith([], 'start')
    expect(onSelect).toHaveBeenCalledWith(['one', 'two'], 'drag')
    expect(onSelect).toHaveBeenCalledWith(['one', 'two'], 'end')
  })

  test('a click without drag clears the selection', () => {
    const onSelect = vi.fn()
    const { getByTestId } = render(<MarqueeHost onSelect={onSelect} />)
    const pane = getByTestId('pane')

    pane.dispatchEvent(mouseEvent('mousedown', 5, 5))
    window.dispatchEvent(mouseEvent('mouseup', 5, 5))

    expect(onSelect).toHaveBeenCalledWith([], 'end')
  })

  test('mousedown on an item does not start a marquee', () => {
    const onSelect = vi.fn()
    const { getByText } = render(<MarqueeHost onSelect={onSelect} />)
    const item = getByText('one')

    item.dispatchEvent(mouseEvent('mousedown', 0, 0))
    window.dispatchEvent(mouseEvent('mousemove', 50, 10))
    window.dispatchEvent(mouseEvent('mouseup', 50, 10))

    expect(onSelect).not.toHaveBeenCalled()
  })

  test('sub-threshold movement never arms the marquee', () => {
    const onSelect = vi.fn()
    const { getByTestId } = render(<MarqueeHost onSelect={onSelect} />)
    const pane = getByTestId('pane')

    pane.dispatchEvent(mouseEvent('mousedown', 0, 0))
    window.dispatchEvent(mouseEvent('mousemove', 2, 2))
    window.dispatchEvent(mouseEvent('mouseup', 2, 2))

    expect(onSelect).not.toHaveBeenCalledWith(expect.anything(), 'start')
  })

  test('ctrl drag unions with the base selection', () => {
    const onSelect = vi.fn()
    const { getByTestId } = render(
      <MarqueeHost onSelect={onSelect} getBaseSelection={() => new Set(['base'])} />
    )
    const pane = getByTestId('pane')

    pane.dispatchEvent(
      mouseEvent('mousedown', 0, 0, { ctrlKey: true })
    )
    window.dispatchEvent(mouseEvent('mousemove', 50, 10))
    window.dispatchEvent(mouseEvent('mouseup', 50, 10))

    expect(onSelect).toHaveBeenCalledWith(['base', 'one', 'two'], 'drag')
    expect(onSelect).toHaveBeenCalledWith(['base', 'one', 'two'], 'end')
  })
})

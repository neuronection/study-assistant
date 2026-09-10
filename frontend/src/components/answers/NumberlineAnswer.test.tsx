import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, afterAll, describe, expect, test, vi } from 'vitest'

import {
  NumberlineAnswer,
  emptyNumberlinePayload,
  numberlinePayloadComplete,
  type NumberlinePayload,
} from './NumberlineAnswer'

beforeAll(() => {
  vi.spyOn(SVGElement.prototype, 'getBoundingClientRect').mockReturnValue({
    left: 0,
    right: 560,
    top: 0,
    bottom: 92,
    width: 560,
    height: 92,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect)
})

afterAll(() => {
  vi.mocked(SVGElement.prototype.getBoundingClientRect).mockRestore()
})

function clickAt(clientX: number) {
  const svg = document.querySelector('svg[role="img"]')
  expect(svg).not.toBeNull()
  fireEvent.click(svg!, { clientX, clientY: 46 })
}

describe('NumberlineAnswer', () => {
  test('click places a snapped point in points mode', () => {
    const onChange = vi.fn()
    render(
      <NumberlineAnswer min={0} max={10} value={emptyNumberlinePayload()} onChange={onChange} />,
    )
    clickAt(26 + 0.3 * 508)
    expect(onChange).toHaveBeenCalledWith({ points: [{ value: 3 }], intervals: [] })
  })

  test('interval mode creates an interval from two clicks', () => {
    const onChange = vi.fn()
    render(
      <NumberlineAnswer min={0} max={10} value={emptyNumberlinePayload()} onChange={onChange} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Interval' }))
    clickAt(26 + 0.3 * 508)
    clickAt(26 + 0.5 * 508)
    expect(onChange).toHaveBeenLastCalledWith({
      points: [],
      intervals: [{ lo: 3, hi: 5, lo_closed: true, hi_closed: true }],
    })
  })

  test('clicking an existing point removes it', () => {
    const onChange = vi.fn()
    render(
      <NumberlineAnswer
        min={0}
        max={10}
        value={{ points: [{ value: 3 }], intervals: [] }}
        onChange={onChange}
      />,
    )
    clickAt(26 + 0.3 * 508)
    expect(onChange).toHaveBeenCalledWith({ points: [], intervals: [] })
  })

  test('readonly mode hides interactive controls', () => {
    render(
      <NumberlineAnswer
        min={0}
        max={10}
        value={{ points: [{ value: 3 }], intervals: [] }}
      />,
    )
    expect(screen.queryByRole('button', { name: 'Interval' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Clear' })).toBeNull()
  })

  test('clear resets the payload', () => {
    const onChange = vi.fn()
    render(
      <NumberlineAnswer
        min={0}
        max={10}
        value={{ points: [{ value: 3 }], intervals: [] }}
        onChange={onChange}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(onChange).toHaveBeenCalledWith(emptyNumberlinePayload())
  })

  test('numberlinePayloadComplete requires at least one marker', () => {
    expect(numberlinePayloadComplete(null)).toBe(false)
    expect(numberlinePayloadComplete(emptyNumberlinePayload())).toBe(false)
    const payload: NumberlinePayload = { points: [{ value: 1 }], intervals: [] }
    expect(numberlinePayloadComplete(payload)).toBe(true)
  })
})

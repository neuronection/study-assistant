import { act, renderHook } from '@testing-library/react'
import { describe, expect, test } from 'vitest'

import { isKeyboardClick, nextSelection, useSelection } from './useSelection'

const ORDER = ['a', 'b', 'c', 'd', 'e']

describe('nextSelection', () => {
  test('plain click selects only the item and moves the anchor', () => {
    const result = nextSelection(new Set(['a', 'b']), ORDER, 'b', 'd', {
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
    })
    expect(result.selected).toEqual(new Set(['d']))
    expect(result.anchor).toBe('d')
  })

  test('plain click on an already-selected item keeps the whole selection', () => {
    const result = nextSelection(new Set(['a', 'b', 'c']), ORDER, 'c', 'b', {
      ctrlKey: false,
      metaKey: false,
      shiftKey: false,
    })
    expect(result.selected).toEqual(new Set(['a', 'b', 'c']))
    expect(result.anchor).toBe('b')
  })

  test('ctrl click toggles membership', () => {
    const result = nextSelection(new Set(['b']), ORDER, 'b', 'c', {
      ctrlKey: true,
      metaKey: false,
      shiftKey: false,
    })
    expect(result.selected).toEqual(new Set(['b', 'c']))
    expect(result.anchor).toBe('c')

    const off = nextSelection(new Set(['b', 'c']), ORDER, 'c', 'b', {
      ctrlKey: true,
      metaKey: false,
      shiftKey: false,
    })
    expect(off.selected).toEqual(new Set(['c']))
  })

  test('meta click behaves like ctrl click', () => {
    const result = nextSelection(new Set<string>(), ORDER, null, 'a', {
      ctrlKey: false,
      metaKey: true,
      shiftKey: false,
    })
    expect(result.selected).toEqual(new Set(['a']))
  })

  test('shift click selects the inclusive range from the anchor', () => {
    const result = nextSelection(new Set(['a']), ORDER, 'a', 'd', {
      ctrlKey: false,
      metaKey: false,
      shiftKey: true,
    })
    expect(result.selected).toEqual(new Set(['a', 'b', 'c', 'd']))
    expect(result.anchor).toBe('a')
  })

  test('shift click ranges work in reverse order', () => {
    const result = nextSelection(new Set(['e']), ORDER, 'e', 'b', {
      ctrlKey: false,
      metaKey: false,
      shiftKey: true,
    })
    expect(result.selected).toEqual(new Set(['b', 'c', 'd', 'e']))
  })

  test('shift click without an anchor falls back to a plain select', () => {
    const result = nextSelection(new Set(['a']), ORDER, null, 'c', {
      ctrlKey: false,
      metaKey: false,
      shiftKey: true,
    })
    expect(result.selected).toEqual(new Set(['c']))
    expect(result.anchor).toBe('c')
  })
})

describe('useSelection', () => {
  test('pointer down drives the selection model and clear resets', () => {
    const { result } = renderHook(() => useSelection(ORDER))
    act(() => {
      result.current.pointerDown('b', {
        ctrlKey: false,
        metaKey: false,
        shiftKey: false,
      })
    })
    expect(result.current.selected).toEqual(new Set(['b']))

    act(() => {
      result.current.pointerDown('d', {
        ctrlKey: false,
        metaKey: false,
        shiftKey: true,
      })
    })
    expect(result.current.selected).toEqual(new Set(['b', 'c', 'd']))

    act(() => {
      result.current.clear()
    })
    expect(result.current.selected).toEqual(new Set())
  })

  test('right-click (button 2) never changes the selection', () => {
    const { result } = renderHook(() => useSelection(ORDER))
    act(() => {
      result.current.set(['a', 'c'])
    })
    act(() => {
      result.current.pointerDown('c', {
        ctrlKey: false,
        metaKey: false,
        shiftKey: false,
        button: 2,
      })
    })
    expect(result.current.selected).toEqual(new Set(['a', 'c']))
  })

  test('set replaces the selection wholesale (marquee end)', () => {
    const { result } = renderHook(() => useSelection(ORDER))
    act(() => {
      result.current.set(['a', 'c', 'e'])
    })
    expect(result.current.selected).toEqual(new Set(['a', 'c', 'e']))
  })

  test('union merges into the live selection (marquee drag)', () => {
    const { result } = renderHook(() => useSelection(ORDER))
    act(() => {
      result.current.set(['b'])
    })
    act(() => {
      result.current.union(['d'])
    })
    expect(result.current.selected).toEqual(new Set(['b', 'd']))
  })
})

describe('isKeyboardClick', () => {
  test('detail 0 means keyboard-synthesized click, detail > 0 means mouse', () => {
    expect(isKeyboardClick({ detail: 0 })).toBe(true)
    expect(isKeyboardClick({ detail: 1 })).toBe(false)
    expect(isKeyboardClick({ detail: 2 })).toBe(false)
  })
})

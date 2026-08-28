import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { useStreamBuffer } from './useStreamBuffer'

describe('useStreamBuffer', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  test('batches many deltas into one flush', () => {
    vi.useFakeTimers()
    vi.stubGlobal('requestAnimationFrame', undefined)
    const { result } = renderHook(() => useStreamBuffer())
    act(() => {
      result.current.append('a')
      result.current.append('b')
      result.current.append('c')
    })
    expect(result.current.text).toBeNull()
    act(() => {
      vi.advanceTimersByTime(33)
    })
    expect(result.current.text).toBe('abc')
  })

  test('flushes the tail of a batch on the next tick', () => {
    vi.useFakeTimers()
    vi.stubGlobal('requestAnimationFrame', undefined)
    const { result } = renderHook(() => useStreamBuffer())
    act(() => {
      result.current.append('hello')
    })
    act(() => {
      vi.advanceTimersByTime(33)
    })
    expect(result.current.text).toBe('hello')
    act(() => {
      result.current.append(' world')
    })
    act(() => {
      vi.advanceTimersByTime(33)
    })
    expect(result.current.text).toBe('hello world')
  })

  test('reset clears the text and cancels a pending flush', () => {
    vi.useFakeTimers()
    vi.stubGlobal('requestAnimationFrame', undefined)
    const { result } = renderHook(() => useStreamBuffer())
    act(() => {
      result.current.append('x')
    })
    act(() => {
      result.current.reset()
    })
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(result.current.text).toBeNull()
  })
})

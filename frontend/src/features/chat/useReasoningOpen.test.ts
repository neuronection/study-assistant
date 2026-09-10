import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, test } from 'vitest'

import { useReasoningOpen } from './useReasoningOpen'
import { storageKeys } from '@/lib/constants'

describe('useReasoningOpen', () => {
  afterEach(() => {
    window.localStorage.clear()
  })

  test('defaults to open and persists toggles under the same key', () => {
    const { result } = renderHook(() => useReasoningOpen())
    expect(result.current[0]).toBe(true)
    act(() => {
      result.current[1](false)
    })
    expect(result.current[0]).toBe(false)
    expect(window.localStorage.getItem(storageKeys.chatReasoningOpen)).toBe('0')
    act(() => {
      result.current[1](true)
    })
    expect(window.localStorage.getItem(storageKeys.chatReasoningOpen)).toBe('1')
  })

  test('respects a persisted collapsed preference', () => {
    window.localStorage.setItem(storageKeys.chatReasoningOpen, '0')
    const { result } = renderHook(() => useReasoningOpen())
    expect(result.current[0]).toBe(false)
  })
})

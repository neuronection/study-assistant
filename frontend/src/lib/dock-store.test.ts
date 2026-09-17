import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, test } from 'vitest'

import { CHAT_WIDTH_BOUNDS } from './chat-store'
import {
  FILE_WIDTH_BOUNDS,
  resolveRailWidths,
  useDockStore,
} from './dock-store'

describe('resolveRailWidths', () => {
  test('closed rails resolve to null', () => {
    expect(
      resolveRailWidths({
        viewportWidth: 1400,
        fileOpen: false,
        chatOpen: false,
        fileWidth: 480,
        chatWidth: 384,
      })
    ).toEqual({ fileWidth: null, chatWidth: null, chatDeferred: false })
  })

  test('a single open rail keeps its width when it fits', () => {
    expect(
      resolveRailWidths({
        viewportWidth: 1400,
        fileOpen: true,
        chatOpen: false,
        fileWidth: 480,
        chatWidth: 384,
      })
    ).toMatchObject({ fileWidth: 480, chatWidth: null, chatDeferred: false })
    expect(
      resolveRailWidths({
        viewportWidth: 1400,
        fileOpen: false,
        chatOpen: true,
        fileWidth: 480,
        chatWidth: 384,
      })
    ).toMatchObject({ fileWidth: null, chatWidth: 384, chatDeferred: false })
  })

  test('a single open rail clamps to the budget but never below its minimum', () => {
    expect(
      resolveRailWidths({
        viewportWidth: 920,
        fileOpen: true,
        chatOpen: false,
        fileWidth: 480,
        chatWidth: 384,
      }).fileWidth
    ).toBe(320)
    expect(
      resolveRailWidths({
        viewportWidth: 400,
        fileOpen: false,
        chatOpen: true,
        fileWidth: 480,
        chatWidth: 384,
      }).chatWidth
    ).toBe(CHAT_WIDTH_BOUNDS.min)
  })

  test('both rails fit untouched when the budget allows', () => {
    expect(
      resolveRailWidths({
        viewportWidth: 1600,
        fileOpen: true,
        chatOpen: true,
        fileWidth: 480,
        chatWidth: 384,
      })
    ).toEqual({ fileWidth: 480, chatWidth: 384, chatDeferred: false })
  })

  test('when both rails squeeze, chat yields first and file takes the remainder', () => {
    expect(
      resolveRailWidths({
        viewportWidth: 1260,
        fileOpen: true,
        chatOpen: true,
        fileWidth: 480,
        chatWidth: 384,
      })
    ).toEqual({ fileWidth: 320, chatWidth: 340, chatDeferred: false })
  })

  test('when both rails cannot fit at their minimums, chat defers to the file', () => {
    expect(
      resolveRailWidths({
        viewportWidth: 1024,
        fileOpen: true,
        chatOpen: true,
        fileWidth: 480,
        chatWidth: 384,
      })
    ).toEqual({ fileWidth: 424, chatWidth: null, chatDeferred: true })
  })

  test('clamps out-of-range stored widths', () => {
    expect(
      resolveRailWidths({
        viewportWidth: 1900,
        fileOpen: true,
        chatOpen: true,
        fileWidth: 5000,
        chatWidth: 10,
      })
    ).toEqual({
      fileWidth: FILE_WIDTH_BOUNDS.max,
      chatWidth: CHAT_WIDTH_BOUNDS.min,
      chatDeferred: false,
    })
    expect(
      resolveRailWidths({
        viewportWidth: 1600,
        fileOpen: true,
        chatOpen: true,
        fileWidth: 5000,
        chatWidth: 10,
      })
    ).toEqual({
      fileWidth: 680,
      chatWidth: CHAT_WIDTH_BOUNDS.min,
      chatDeferred: false,
    })
  })
})

describe('useDockStore', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useDockStore.setState({ fileWidth: FILE_WIDTH_BOUNDS.default })
  })

  test('setFileWidth clamps into the file bounds', () => {
    const { result } = renderHook(() => useDockStore())
    act(() => result.current.setFileWidth(2000))
    expect(result.current.fileWidth).toBe(FILE_WIDTH_BOUNDS.max)
    act(() => result.current.setFileWidth(50))
    expect(result.current.fileWidth).toBe(FILE_WIDTH_BOUNDS.min)
  })

  test('persistFileWidth stores the current width', () => {
    const { result } = renderHook(() => useDockStore())
    act(() => result.current.setFileWidth(560))
    act(() => result.current.persistFileWidth())
    expect(window.localStorage.getItem('ca-file-width')).toBe('560')
  })
})

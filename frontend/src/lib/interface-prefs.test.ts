import { beforeEach, describe, expect, test } from 'vitest'

import { storageKeys } from './constants'
import { readInterfacePrefs, useInterfacePrefsStore } from './interface-prefs'

beforeEach(() => {
  window.localStorage.removeItem(storageKeys.interfacePrefs)
  useInterfacePrefsStore.setState({ prefs: useInterfacePrefsStore.getState().prefs })
})

describe('interface-prefs store', () => {
  test('defaults are all enabled', () => {
    const prefs = useInterfacePrefsStore.getState().prefs
    expect(prefs).toEqual({
      homeContinue: true,
      paletteRecent: true,
      courseJumpBackIn: true,
      courseCardMeta: true,
    })
  })

  test('setPref flips one surface, persists, and keeps others', () => {
    useInterfacePrefsStore.getState().setPref('paletteRecent', false)
    const prefs = useInterfacePrefsStore.getState().prefs
    expect(prefs.paletteRecent).toBe(false)
    expect(prefs.homeContinue).toBe(true)
    const raw = JSON.parse(
      window.localStorage.getItem(storageKeys.interfacePrefs) ?? '{}'
    ) as Record<string, unknown>
    expect(raw.paletteRecent).toBe(false)
    expect(raw.homeContinue).toBe(true)
  })

  test('round-trips from localStorage on a fresh read', () => {
    window.localStorage.setItem(
      storageKeys.interfacePrefs,
      JSON.stringify({ homeContinue: false })
    )
    const prefs = readInterfacePrefs()
    expect(prefs.homeContinue).toBe(false)
    expect(prefs.paletteRecent).toBe(true)
  })

  test('tolerates corrupt and malformed storage, falling back to defaults', () => {
    window.localStorage.setItem(storageKeys.interfacePrefs, 'not json')
    expect(readInterfacePrefs()).toEqual({
      homeContinue: true,
      paletteRecent: true,
      courseJumpBackIn: true,
      courseCardMeta: true,
    })
    window.localStorage.setItem(
      storageKeys.interfacePrefs,
      JSON.stringify({ paletteRecent: 'yes', courseCardMeta: 3, homeContinue: false })
    )
    const prefs = readInterfacePrefs()
    expect(prefs.paletteRecent).toBe(true)
    expect(prefs.courseCardMeta).toBe(true)
    expect(prefs.homeContinue).toBe(false)
  })

  test('missing storage key reads as defaults', () => {
    expect(readInterfacePrefs()).toEqual({
      homeContinue: true,
      paletteRecent: true,
      courseJumpBackIn: true,
      courseCardMeta: true,
    })
  })
})

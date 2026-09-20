import { create } from 'zustand'

import { storageKeys } from './constants'

export interface InterfacePrefs {
  homeContinue: boolean
  paletteRecent: boolean
  courseJumpBackIn: boolean
  courseCardMeta: boolean
}

export type InterfacePrefKey = keyof InterfacePrefs

const DEFAULTS: InterfacePrefs = {
  homeContinue: true,
  paletteRecent: true,
  courseJumpBackIn: true,
  courseCardMeta: true,
}

function readPrefs(): InterfacePrefs {
  let raw: string
  try {
    raw = window.localStorage.getItem(storageKeys.interfacePrefs) ?? ''
  } catch {
    return { ...DEFAULTS }
  }
  if (raw === '') {
    return { ...DEFAULTS }
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { ...DEFAULTS }
  }
  const prefs = { ...DEFAULTS }
  if (typeof parsed === 'object' && parsed !== null) {
    for (const key of Object.keys(DEFAULTS) as InterfacePrefKey[]) {
      const value = (parsed as Record<string, unknown>)[key]
      if (typeof value === 'boolean') {
        prefs[key] = value
      }
    }
  }
  return prefs
}

export function readInterfacePrefs(): InterfacePrefs {
  return readPrefs()
}

interface InterfacePrefsState {
  prefs: InterfacePrefs
  setPref: (key: InterfacePrefKey, value: boolean) => void
}

export const useInterfacePrefsStore = create<InterfacePrefsState>((set) => ({
  prefs: readPrefs(),
  setPref: (key, value) => {
    const prefs = { ...useInterfacePrefsStore.getState().prefs, [key]: value }
    try {
      window.localStorage.setItem(storageKeys.interfacePrefs, JSON.stringify(prefs))
    } catch {
      return
    }
    set({ prefs })
  },
}))

export function useInterfacePrefs(): InterfacePrefs {
  return useInterfacePrefsStore((state) => state.prefs)
}

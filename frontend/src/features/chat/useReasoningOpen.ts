import { useCallback, useState } from 'react'

import { storageKeys } from '@/lib/constants'

function readPref(): boolean {
  try {
    return window.localStorage.getItem(storageKeys.chatReasoningOpen) !== '0'
  } catch {
    return true
  }
}

export function useReasoningOpen(): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(readPref)
  const change = useCallback((next: boolean) => {
    setOpen(next)
    try {
      window.localStorage.setItem(storageKeys.chatReasoningOpen, next ? '1' : '0')
    } catch {
      // persistence is best-effort
    }
  }, [])
  return [open, change]
}

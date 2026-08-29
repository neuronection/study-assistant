import { useEffect, useState } from 'react'

import type { LibraryView } from '@/components/ui/ViewToggle'

export function useStoredView(storageKey: string, fallback: LibraryView = 'grid') {
  const [view, setView] = useState<LibraryView>(() => {
    try {
      const stored = window.localStorage.getItem(storageKey)
      return stored === 'grid' || stored === 'list' ? stored : fallback
    } catch {
      return fallback
    }
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, view)
    } catch {
      return
    }
  }, [storageKey, view])
  return [view, setView] as const
}

import { LayoutGrid, List } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export type LibraryView = 'grid' | 'list'

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

export function ViewToggle({
  view,
  onChange,
}: {
  view: LibraryView
  onChange: (view: LibraryView) => void
}) {
  const { t } = useTranslation()
  const base = 'rounded-md p-1.5'
  return (
    <div className="border-border bg-surface flex overflow-hidden rounded-md border">
      <button
        type="button"
        title={t('library.gridView')}
        aria-label={t('library.gridView')}
        aria-pressed={view === 'grid'}
        className={cn(
          base,
          view === 'grid' ? 'bg-subtle text-foreground' : 'text-muted-foreground'
        )}
        onClick={() => onChange('grid')}
      >
        <LayoutGrid className="size-4" aria-hidden />
      </button>
      <button
        type="button"
        title={t('library.listView')}
        aria-label={t('library.listView')}
        aria-pressed={view === 'list'}
        className={cn(
          base,
          view === 'list' ? 'bg-subtle text-foreground' : 'text-muted-foreground'
        )}
        onClick={() => onChange('list')}
      >
        <List className="size-4" aria-hidden />
      </button>
    </div>
  )
}

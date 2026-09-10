import { useQuery } from '@tanstack/react-query'
import { ArrowUp, FolderClosed, Loader2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { listFsDirs } from '@/lib/api'

import { LibraryBreadcrumbs, type Crumb } from './LibraryBreadcrumbs'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function FolderPickerDialog({
  title,
  initialPath,
  onChoose,
  onCancel,
}: {
  title: string
  initialPath?: string
  onChoose: (path: string) => void
  onCancel: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const [current, setCurrent] = useState<string | undefined>(initialPath)
  const [manual, setManual] = useState(initialPath ?? '')

  const listing = useQuery({
    queryKey: ['fs-dirs', current ?? ''],
    queryFn: () => listFsDirs(current),
  })

  const enter = (path: string) => {
    setCurrent(path)
    setManual(path)
  }

  const data = listing.data
  const chosen = manual.trim() || current

  const crumbs: Crumb[] = useMemo(() => {
    const items: Crumb[] = [
      {
        key: 'filesystem',
        label: '/',
        onClick: () => enter('/'),
      },
    ]
    if (!data) {
      return items
    }
    const parts = data.path.split('/').filter(Boolean)
    let walker = ''
    parts.forEach((part) => {
      walker = `${walker}/${part}`
      const path = walker
      items.push({ key: path, label: part, onClick: () => enter(path) })
    })
    return items
  }, [data])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onCancel()
        }
      }}
    >
      <div className="bg-surface border-border flex max-h-[80vh] w-full max-w-2xl flex-col rounded-lg border shadow-xl">
        <header className="border-border flex items-center gap-2 border-b px-4 py-2">
          <h2 className="text-sm font-semibold">{title}</h2>
        </header>
        <div className="border-border flex items-center gap-2 border-b px-4 py-2">
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground rounded p-1 disabled:opacity-40"
            title={t('library.goUp')}
            disabled={!data?.parent}
            onClick={() => data?.parent && enter(data.parent)}
          >
            <ArrowUp className="size-4" aria-hidden />
          </button>
          <LibraryBreadcrumbs items={crumbs} />
          <span className="text-muted-foreground shrink-0 text-[11px]">
            {t('picker.current')}
          </span>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-1">
          {listing.isLoading ? (
            <Loader2 className="text-muted-foreground m-4 animate-spin" aria-label={t('library.loading')} />
          ) : null}
          {listing.isError ? (
            <p className="text-danger px-2 py-1 text-xs">
              {t('picker.cannotOpen', {
                message: (listing.error as Error).message,
              })}
            </p>
          ) : null}
          {(data?.dirs ?? []).map((entry) => (
            <button
              key={entry.path}
              type="button"
              className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm"
              onDoubleClick={() => enter(entry.path)}
              onClick={() => setManual(entry.path)}
            >
              <FolderClosed className="text-primary size-4 shrink-0" aria-hidden />
              <span className="truncate">{entry.name}</span>
            </button>
          ))}
          {data && data.dirs.length === 0 && !listing.isLoading ? (
            <p className="text-muted-foreground px-2 py-1 text-xs">
              {t('picker.emptyDir')}
            </p>
          ) : null}
        </div>
        <div className="border-border flex items-center gap-2 border-t px-4 py-2">
          <input
            className="bg-surface border-border flex-1 rounded-md border px-2 py-1 font-mono text-xs"
            placeholder={t('picker.manualPath')}
            value={manual}
            onChange={(event) => setManual(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                enter(manual.trim())
              }
            }}
            spellCheck={false}
          />
          <Button variant="outline" size="sm" onClick={() => enter(manual.trim())}>
            {t('picker.go')}
          </Button>
          <Button size="sm" disabled={!chosen} onClick={() => chosen && onChoose(chosen)}>
            {t('picker.choose')}
          </Button>
        </div>
      </div>
    </div>
  )
}

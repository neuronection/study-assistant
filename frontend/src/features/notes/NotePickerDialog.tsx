import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { Loader2, NotebookPen, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { CheckIndicator } from '@/components/ui/CheckIndicator'
import { ErrorBanner } from '@/components/ui/error-banner'
import { SearchInput } from '@/components/ui/SearchInput'
import { listNoteTags, listNotes, type NoteInfo } from '@/lib/api'
import { fuzzyFilter } from '@/lib/fuzzy'
import { cn } from '@/lib/utils'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function NotePickerDialog({
  courseId,
  nodeTitle,
  onSelect,
  onClose,
}: {
  courseId: number
  nodeTitle?: string
  onSelect: (entries: Array<{ id: number; title: string }>) => void
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const [selected, setSelected] = useState<Map<number, string>>(new Map())
  const [query, setQuery] = useState('')
  const [activeTag, setActiveTag] = useState<string | null>(null)
  const pageSize = 100

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const tags = useQuery({
    queryKey: ['note-tags', courseId],
    queryFn: () => listNoteTags(courseId),
  })

  const notes = useInfiniteQuery({
    queryKey: ['notes', 'picker', courseId],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      listNotes(undefined, courseId, { limit: pageSize, cursor: pageParam }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  })

  const flatNotes = useMemo(
    () => notes.data?.pages.flatMap((page) => page.items) ?? [],
    [notes.data]
  )

  const filtered = useMemo(() => {
    let list = flatNotes
    if (activeTag !== null) {
      list = list.filter((note) => note.tags.includes(activeTag))
    }
    return fuzzyFilter(list, query, (note) => note.title)
  }, [flatNotes, activeTag, query])

  const allTags = (tags.data ?? []).map((entry) => entry.tag)

  const toggle = (note: NoteInfo) =>
    setSelected((current) => {
      const next = new Map(current)
      if (next.has(note.id)) {
        next.delete(note.id)
      } else {
        next.set(note.id, note.title)
      }
      return next
    })

  const allShownSelected = filtered.length > 0 && filtered.every((note) => selected.has(note.id))
  const someShownSelected = filtered.some((note) => selected.has(note.id))

  const toggleAllShown = () =>
    setSelected((current) => {
      const next = new Map(current)
      const allSelected = filtered.every((note) => next.has(note.id))
      for (const note of filtered) {
        if (allSelected) {
          next.delete(note.id)
        } else {
          next.set(note.id, note.title)
        }
      }
      return next
    })

  const loading = notes.isLoading

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('notePicker.title')}
        className="bg-surface border-border flex h-[min(560px,90vh)] w-full max-w-2xl flex-col rounded-xl border shadow-xl"
      >
        <div className="border-border flex items-center gap-3 border-b px-5 py-3">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-sm font-semibold">{t('notePicker.title')}</h2>
            {nodeTitle ? (
              <p className="text-muted-foreground truncate text-xs">{nodeTitle}</p>
            ) : null}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label={t('settings.cancel')}>
            <X className="size-4" aria-hidden />
          </Button>
        </div>

        <div className="border-border flex items-center gap-2 border-b px-3 py-2">
          <div className="min-w-0 flex-1">
            <SearchInput
              value={query}
              onChange={setQuery}
              placeholder={t('notePicker.searchPlaceholder')}
              ariaLabel={t('notePicker.searchPlaceholder')}
              clearLabel={t('notes.clearSearch')}
            />
          </div>
          {filtered.length > 0 ? (
            <span className="text-muted-foreground flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1.5 text-xs">
              <CheckIndicator
                checked={allShownSelected}
                mixed={!allShownSelected && someShownSelected}
                label={t('notePicker.selectAllShown', { count: filtered.length })}
                onToggle={toggleAllShown}
              />
              {t('notePicker.selectAllShown', { count: filtered.length })}
            </span>
          ) : null}
        </div>

        {allTags.length > 0 ? (
          <div
            className="flex flex-wrap items-center gap-1 px-3 py-2"
            role="group"
            aria-label={t('notes.tagFilter')}
          >
            <button
              type="button"
              className={cn(
                'rounded-full px-2 py-0.5 text-[11px]',
                activeTag === null
                  ? 'bg-primary/15 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-subtle'
              )}
              onClick={() => setActiveTag(null)}
            >
              {t('notes.allTags')}
            </button>
            {allTags.map((tag) => (
              <button
                key={tag}
                type="button"
                className={cn(
                  'rounded-full px-2 py-0.5 text-[11px]',
                  activeTag === tag
                    ? 'bg-primary/15 text-primary font-medium'
                    : 'text-muted-foreground hover:bg-subtle'
                )}
                onClick={() => setActiveTag(activeTag === tag ? null : tag)}
              >
                {tag}
              </button>
            ))}
          </div>
        ) : null}

        <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
          {loading ? (
            <Loader2
              className="text-muted-foreground m-6 size-5 animate-spin"
              aria-label={t('library.loading')}
            />
          ) : null}
          {!loading
            ? filtered.map((note) => (
                <div
                  key={note.id}
                  className={cn(
                    'hover:bg-subtle flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
                    selected.has(note.id) && 'bg-primary/5'
                  )}
                >
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    onClick={() => toggle(note)}
                  >
                    <NotebookPen className="text-muted-foreground size-4 shrink-0" aria-hidden />
                    <span
                      className={cn(
                        'min-w-0 flex-1',
                        selected.has(note.id) ? 'line-clamp-2' : 'truncate'
                      )}
                    >
                      {note.title}
                    </span>
                    {note.tags.length > 0 ? (
                      <span className="hidden shrink-0 gap-0.5 md:flex">
                        {note.tags.map((tag) => (
                          <span
                            key={tag}
                            className="bg-subtle text-muted-foreground rounded-full px-1.5 py-0.5 text-[9px]"
                          >
                            {tag}
                          </span>
                        ))}
                      </span>
                    ) : null}
                    <span className="text-muted-foreground shrink-0 text-[10px]">
                      {new Date(note.updated_at).toLocaleDateString()}
                    </span>
                  </button>
                  <CheckIndicator
                    checked={selected.has(note.id)}
                    label={note.title}
                    onToggle={() => toggle(note)}
                  />
                </div>
              ))
            : null}
          {!loading && flatNotes.length === 0 ? (
            <p className="text-muted-foreground p-6 text-center text-sm">
              {t('notePicker.empty')}
            </p>
          ) : null}
          {!loading && flatNotes.length > 0 && filtered.length === 0 ? (
            <p className="text-muted-foreground p-6 text-center text-sm">
              {t('notePicker.emptyFilter')}
            </p>
          ) : null}
        </div>

        <div className="border-border space-y-2 border-t px-5 py-3">
          <ErrorBanner message={notes.isError ? (notes.error as Error).message : null} />
          <div className="flex items-center justify-between gap-2">
            <span className="text-muted-foreground text-xs">
              {t('notePicker.selectedCount', { count: selected.size })}
            </span>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" onClick={onClose}>
                {t('settings.cancel')}
              </Button>
              <Button
                size="sm"
                disabled={selected.size === 0}
                onClick={() => onSelect(Array.from(selected.entries()).map(([id, title]) => ({ id, title })))}
              >
                {t('notePicker.add', { count: selected.size })}
              </Button>
            </div>
          </div>
          {notes.hasNextPage ? (
            <div className="flex justify-center">
              <Button
                variant="outline"
                size="sm"
                disabled={notes.isFetchingNextPage}
                onClick={() => void notes.fetchNextPage()}
              >
                {notes.isFetchingNextPage ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : null}
                {t('notes.loadMore')}
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}
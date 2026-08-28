import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2, Quote, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  courseTree,
  createNote,
  getMaterial,
  getMaterialLinks,
} from '@/lib/api'

import { MaterialDetailBody, type DetailTab } from './MaterialDetailBody'
import { MaterialDetailDrawer } from './MaterialDetailDrawer'
import { LazyNoteEditor } from '../notes/LazyNoteEditor'

export type StudyTarget = number | 'new'

export interface StudyQuoteSource {
  title: string
  materialId: number
}

export type StudyInsertApi = {
  insertQuote: (text: string, source: StudyQuoteSource | null) => void
}

const MIN_PCT = 30
const MAX_PCT = 70

function splitKey(courseId: number): string {
  return `ca-study-split:${courseId}`
}

function readSplit(courseId: number): number | null {
  try {
    const raw = localStorage.getItem(splitKey(courseId))
    const value = raw === null ? null : Number(raw)
    if (value === null || Number.isNaN(value)) {
      return null
    }
    return Math.min(MAX_PCT, Math.max(MIN_PCT, value))
  } catch {
    return null
  }
}

export function useWideLayout(): boolean {
  const [wide, setWide] = useState(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return true
    }
    try {
      return window.matchMedia('(min-width: 1024px)').matches
    } catch {
      return true
    }
  })
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return
    }
    let query: MediaQueryList
    try {
      query = window.matchMedia('(min-width: 1024px)')
    } catch {
      return
    }
    const listener = (event: MediaQueryListEvent) => setWide(event.matches)
    query.addEventListener('change', listener)
    return () => query.removeEventListener('change', listener)
  }, [])
  return wide
}

function SelectionQuoteButton({
  rect,
  onQuote,
}: {
  rect: { top: number; left: number }
  onQuote: () => void
}) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      className="bg-surface border-border text-foreground fixed z-[60] flex items-center gap-1 rounded-md border px-2 py-1 text-xs shadow-lg"
      style={{ top: rect.top, left: rect.left }}
      onClick={onQuote}
    >
      <Quote className="size-3.5" aria-hidden />
      {t('study.quoteIntoNote')}
    </button>
  )
}

export function SplitStudyPane({
  courseId,
  materialId,
  study,
  onNoteCreated,
  onClose,
}: {
  courseId: number
  materialId: number
  study: StudyTarget
  onNoteCreated: (noteId: number) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const wide = useWideLayout()
  const [tab, setTab] = useState<DetailTab>('extraction')
  const [noteId, setNoteId] = useState<number | null>(typeof study === 'number' ? study : null)
  const [pct, setPct] = useState<number>(() => readSplit(courseId) ?? 50)
  const [quote, setQuote] = useState<{ text: string; top: number; left: number } | null>(null)
  const insertRef = useRef<StudyInsertApi | null>(null)
  const leftRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const detail = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
  })
  const links = useQuery({
    queryKey: ['material-links', materialId],
    queryFn: () => getMaterialLinks(materialId),
  })
  const tree = useQuery({
    queryKey: ['tree', String(courseId)],
    queryFn: () => courseTree(courseId),
  })

  const create = useMutation({
    mutationFn: async () => {
      const material = detail.data?.material
      const rootId = tree.data?.[0]?.id ?? null
      const nodeId =
        links.data?.find((link) => !link.is_course_level)?.node_id ??
        links.data?.[0]?.node_id ??
        rootId
      return createNote({
        title: t('study.noteTitle', { title: material?.title ?? '' }),
        body_md: '',
        course_id: courseId,
        node_id: nodeId,
      })
    },
    onSuccess: (created) => {
      setNoteId(created.id)
      onNoteCreated(created.id)
    },
  })

  useEffect(() => {
    if (study === 'new' && noteId === null && detail.data !== undefined && !create.isPending) {
      create.mutate()
    }
  }, [study, noteId, detail.data, create])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const persist = useCallback(
    (value: number) => {
      try {
        localStorage.setItem(splitKey(courseId), String(Math.round(value)))
      } catch {
        return
      }
    },
    [courseId]
  )

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      if (!dragging.current || containerRef.current === null) {
        return
      }
      const rect = containerRef.current.getBoundingClientRect()
      const next = ((event.clientX - rect.left) / rect.width) * 100
      setPct(Math.min(MAX_PCT, Math.max(MIN_PCT, next)))
    }
    const onUp = () => {
      if (dragging.current) {
        dragging.current = false
        setPct((current) => {
          persist(current)
          return current
        })
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [persist])

  const captureSelection = () => {
    if (leftRef.current === null) {
      return
    }
    const selection = window.getSelection()
    const text = selection?.toString().trim() ?? ''
    if (
      selection === null ||
      selection.isCollapsed ||
      text.length === 0 ||
      selection.rangeCount === 0
    ) {
      setQuote(null)
      return
    }
    const range = selection.getRangeAt(0)
    const node = range.commonAncestorContainer
    const element = node.nodeType === Node.TEXT_NODE ? node.parentElement : (node as Element)
    if (element === null || !leftRef.current.contains(element)) {
      setQuote(null)
      return
    }
    let top: number
    let left: number
    if (typeof range.getBoundingClientRect === 'function') {
      const rect = range.getBoundingClientRect()
      top = rect.bottom + 6
      left = rect.left
    } else {
      const hostRect = leftRef.current.getBoundingClientRect()
      top = hostRect.top + 40
      left = hostRect.left + 40
    }
    setQuote({ text, top, left })
  }

  const quoteIntoNote = () => {
    if (quote === null) {
      return
    }
    insertRef.current?.insertQuote(quote.text, {
      title: detail.data?.material.title ?? '',
      materialId,
    })
    window.getSelection()?.removeAllRanges()
    setQuote(null)
  }

  if (!wide) {
    return <MaterialDetailDrawer materialId={materialId} onClose={onClose} />
  }

  const material = detail.data?.material

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-label={t('study.paneLabel')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="bg-surface flex h-full w-full flex-col p-4">
        <header className="border-border mb-3 flex items-center justify-between gap-2 border-b pb-2">
          <h1 className="truncate text-lg font-semibold">
            {t('study.paneTitle', { title: material?.title ?? '' })}
          </h1>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            title={t('common.close')}
            aria-label={t('common.close')}
          >
            <X className="size-4" aria-hidden />
          </Button>
        </header>

        <div ref={containerRef} className="flex min-h-0 flex-1 gap-0">
          <div
            ref={leftRef}
            className="border-border min-w-0 overflow-y-auto border-r pr-2"
            style={{ width: `${pct}%` }}
            onMouseUp={captureSelection}
          >
            <MaterialDetailBody
              materialId={materialId}
              activeTab={tab}
              onTabChange={setTab}
              showTitle={false}
            />
          </div>

          <div
            role="separator"
            aria-orientation="vertical"
            aria-label={t('study.resize')}
            className="hover:bg-primary/40 w-1.5 shrink-0 cursor-col-resize bg-transparent"
            onMouseDown={(event) => {
              event.preventDefault()
              dragging.current = true
            }}
          />

          <div className="min-w-0 flex-1 overflow-y-auto pl-2">
            {noteId === null ? (
              <div className="text-muted-foreground flex items-center gap-2 p-8 text-sm">
                {create.isPending ? (
                  <>
                    <Loader2 className="animate-spin" aria-hidden />
                    {t('study.creatingNote')}
                  </>
                ) : create.isError ? (
                  <span className="text-danger">{create.error.message}</span>
                ) : null}
              </div>
            ) : (
              <LazyNoteEditor noteId={noteId} insertRef={insertRef} />
            )}
          </div>
        </div>
      </div>

      {quote !== null ? (
        <SelectionQuoteButton rect={{ top: quote.top, left: quote.left }} onQuote={quoteIntoNote} />
      ) : null}
    </div>
  )
}

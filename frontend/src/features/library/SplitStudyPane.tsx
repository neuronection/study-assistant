import { useMutation, useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'

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

export function SplitStudyPane({
  courseId,
  materialId,
  study,
  onNoteCreated,
  onClose,
  onCloseNotes,
}: {
  courseId: number
  materialId: number
  study: StudyTarget
  onNoteCreated: (noteId: number) => void
  onClose: () => void
  onCloseNotes: () => void
}) {
  const { t } = useTranslation()
  const wide = useWideLayout()
  const [tab, setTab] = useState<DetailTab>('extraction')
  const [noteId, setNoteId] = useState<number | null>(typeof study === 'number' ? study : null)
  const [pct, setPct] = useState<number>(() => readSplit(courseId) ?? 50)
  const insertRef = useRef<StudyInsertApi | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

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

  const clampPct = useCallback(
    (value: number) => Math.min(MAX_PCT, Math.max(MIN_PCT, value)),
    []
  )

  const resetSplit = useCallback(() => {
    try {
      localStorage.removeItem(splitKey(courseId))
    } catch {
      return
    }
    setPct(50)
  }, [courseId])

  const onDividerKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      const step = event.key === 'ArrowLeft' ? -5 : event.key === 'ArrowRight' ? 5 : 0
      if (step === 0) {
        return
      }
      event.preventDefault()
      setPct((current) => {
        const next = clampPct(current + step)
        persist(next)
        return next
      })
    },
    [clampPct, persist]
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

  if (!wide) {
    return <MaterialDetailDrawer materialId={materialId} onClose={onClose} />
  }

  const quoteIntoNote = (text: string) => {
    insertRef.current?.insertQuote(text, {
      title: detail.data?.material.title ?? '',
      materialId,
    })
  }

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
        <div ref={containerRef} className="flex min-h-0 flex-1 gap-0">
          <div
            className="border-border flex h-full min-h-0 flex-col border-r pr-2"
            style={{ width: `${pct}%` }}
          >
            <MaterialDetailBody
              materialId={materialId}
              activeTab={tab}
              onTabChange={setTab}
              onClose={onClose}
              closeLabel={t('common.close')}
              onQuoteSelection={quoteIntoNote}
            />
          </div>

          <div
            role="separator"
            aria-orientation="vertical"
            aria-label={t('study.resize')}
            title={t('study.resetSplit')}
            aria-valuenow={Math.round(pct)}
            aria-valuemin={MIN_PCT}
            aria-valuemax={MAX_PCT}
            tabIndex={0}
            className="group/divider hover:bg-primary/40 focus-visible:bg-primary/40 relative w-1.5 shrink-0 cursor-col-resize rounded-full outline-none"
            onKeyDown={onDividerKeyDown}
            onDoubleClick={resetSplit}
            onMouseDown={(event) => {
              event.preventDefault()
              dragging.current = true
            }}
          >
            <span
              className="bg-border group-hover/divider:bg-primary/60 group-focus-visible/divider:bg-primary/60 pointer-events-none absolute top-1/2 left-1/2 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1"
              aria-hidden
            >
              <span className="bg-border group-hover/divider:bg-primary/60 size-0.5 rounded-full" />
              <span className="bg-border group-hover/divider:bg-primary/60 size-0.5 rounded-full" />
              <span className="bg-border group-hover/divider:bg-primary/60 size-0.5 rounded-full" />
            </span>
          </div>

          <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col pl-2">
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
              <LazyNoteEditor
                noteId={noteId}
                onRequestClose={onCloseNotes}
                closeLabel={t('study.closeNotes')}
                insertRef={insertRef}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

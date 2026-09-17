import { useNavigate } from '@tanstack/react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { NotebookPen } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { UndoNotice } from '@/components/ui/undo-notice'
import { createNote, deleteNote, getScratchpad } from '@/lib/api'
import { useCaptureStore } from '@/lib/capture-store'
import { useMotionPresets } from '@/lib/motion'

const TITLE_MAX = 80

function captureTitle(body: string): string {
  const firstLine = body
    .split('\n')
    .map((line) => line.replace(/^#+\s*/, '').trim())
    .find((line) => line.length > 0)
  if (!firstLine) {
    return ''
  }
  return firstLine.length > TITLE_MAX ? `${firstLine.slice(0, TITLE_MAX - 1)}…` : firstLine
}

export function QuickCapture() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const open = useCaptureStore((state) => state.open)
  const closeCapture = useCaptureStore((state) => state.closeCapture)
  const presets = useMotionPresets()
  const queryClient = useQueryClient()
  const [body, setBody] = useState('')
  const [savedTitle, setSavedTitle] = useState<string | null>(null)
  const [savedNoteId, setSavedNoteId] = useState<number | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const scratchpad = useQuery({
    queryKey: ['scratchpad'],
    queryFn: getScratchpad,
    enabled: open,
  })

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        useCaptureStore.getState().openCapture()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) {
      setBody('')
      requestAnimationFrame(() => textareaRef.current?.focus())
    }
  }, [open])

  const save = useMutation({
    mutationFn: async () => {
      const course = scratchpad.data?.course
      if (!course) {
        throw new Error('scratchpad unavailable')
      }
      const trimmed = body.trim()
      if (!trimmed) {
        throw new Error('empty capture')
      }
      return createNote({
        title: captureTitle(trimmed) || t('capture.fallbackTitle'),
        body_md: trimmed,
        course_id: course.id,
        tags: ['quick-capture'],
      })
    },
    onSuccess: (note) => {
      setSavedNoteId(note.id)
      setSavedTitle(note.title)
      setBody('')
      closeCapture()
      void queryClient.invalidateQueries({ queryKey: ['notes'] })
      void queryClient.invalidateQueries({ queryKey: ['scratchpad'] })
    },
    onError: () => {
      textareaRef.current?.focus()
    },
  })

  const undo = useMutation({
    mutationFn: async () => {
      if (savedNoteId === null) {
        return
      }
      await deleteNote(savedNoteId)
    },
    onSuccess: () => {
      setSavedNoteId(null)
      setSavedTitle(null)
      void queryClient.invalidateQueries({ queryKey: ['notes'] })
      void queryClient.invalidateQueries({ queryKey: ['scratchpad'] })
    },
  })

  return (
    <>
      <AnimatePresence>
        {open ? (
          <motion.div
            key="capture-backdrop"
            className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 pb-[12vh] sm:items-end"
            role="dialog"
            aria-modal="true"
            aria-label={t('capture.title')}
            initial={presets.backdrop.initial}
            animate={presets.backdrop.animate}
            exit={presets.backdrop.exit}
            transition={presets.backdrop.transition}
            onClick={(event) => {
              if (event.target === event.currentTarget) {
                closeCapture()
              }
            }}
          >
            <motion.div
              className="bg-surface border-border w-full max-w-xl overflow-hidden rounded-xl border shadow-[var(--as-shadow-3)]"
              initial={{ opacity: 0, y: 24, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 16, scale: 0.98 }}
              transition={presets.panel.transition}
            >
              <div className="border-border flex items-center gap-2 border-b px-3 py-2">
                <NotebookPen className="text-muted-foreground size-4 shrink-0" aria-hidden />
                <p className="flex-1 truncate text-xs font-medium">{t('capture.title')}</p>
                <kbd className="text-muted-foreground border-border rounded border px-1.5 py-0.5 text-[10px]">
                  {t('capture.escKey')}
                </kbd>
              </div>
              <textarea
                ref={textareaRef}
                value={body}
                onChange={(event) => setBody(event.target.value)}
                onKeyDown={(event) => {
                  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                    event.preventDefault()
                    save.mutate()
                  } else if (event.key === 'Escape') {
                    event.preventDefault()
                    closeCapture()
                  }
                }}
                placeholder={t('capture.placeholder')}
                aria-label={t('capture.placeholder')}
                rows={5}
                className="min-h-28 w-full resize-none bg-transparent px-3 py-2.5 text-sm outline-none"
              />
              <div className="border-border text-muted-foreground flex items-center justify-between border-t px-3 py-1.5 text-[10px]">
                <span>{t('capture.targetHint')}</span>
                <span className="flex items-center gap-2">
                  {save.isError ? <span className="text-warning">{t('capture.saveFailed')}</span> : null}
                  <kbd className="border-border rounded border px-1.5 py-0.5">
                    {t('capture.saveKey')}
                  </kbd>
                </span>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      <AnimatePresence>
        {savedNoteId !== null ? (
          <motion.div
            key="capture-saved"
            className="fixed right-4 bottom-4 z-50"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={presets.panel.transition}
          >
            <div className="flex flex-col gap-2">
              <Button
                variant="outline"
                size="sm"
                className="justify-start"
                onClick={() => {
                  const noteId = savedNoteId
                  setSavedNoteId(null)
                  setSavedTitle(null)
                  if (noteId !== null) {
                    void navigate({
                      to: '/note/$noteId',
                      params: { noteId: String(noteId) },
                    })
                  }
                }}
              >
                <NotebookPen aria-hidden />
                {t('capture.open')}
              </Button>
              <UndoNotice
                message={t('capture.savedMessage', { title: savedTitle ?? '' })}
                actionLabel={t('capture.undo')}
                onUndo={() => undo.mutate()}
                undoing={undo.isPending}
                duration={8000}
                onDismiss={() => {
                  setSavedNoteId(null)
                  setSavedTitle(null)
                }}
              />
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  )
}

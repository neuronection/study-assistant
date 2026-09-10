import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { Camera, Loader2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { RegionCrop } from '@/components/capture/RegionCrop'
import { Button } from '@/components/ui/button'
import { UndoNotice } from '@/components/ui/undo-notice'
import { addDrawing, createNote, deleteDrawing, getScratchpad, updateNote } from '@/lib/api'
import { useCaptureStore } from '@/lib/capture-store'
import { useMotionPresets } from '@/lib/motion'
import { useWorkspaceStore } from '@/lib/workspace-store'

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('read-failed'))
    reader.readAsDataURL(file)
  })
}

interface InsertOutcome {
  noteId: number
  title: string
  drawingId: number
  remove: (drawingId: number) => Promise<void>
}

export function SnapIntoNote() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const presets = useMotionPresets()
  const open = useCaptureStore((state) => state.snapOpen)
  const closeSnap = useCaptureStore((state) => state.closeSnap)
  const courseId = useWorkspaceStore((state) => state.courseId)
  const [shot, setShot] = useState<{ pngBase64: string; previewUrl: string } | null>(null)
  const [saved, setSaved] = useState<InsertOutcome | null>(null)
  const [failed, setFailed] = useState(false)

  const scratchpad = useQuery({
    queryKey: ['scratchpad'],
    queryFn: getScratchpad,
    enabled: open,
  })

  useEffect(() => {
    if (open) {
      setShot(null)
      setFailed(false)
    }
  }, [open])

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['notes'] })
    await queryClient.invalidateQueries({ queryKey: ['scratchpad'] })
  }

  const capture = async (file: File) => {
    const dataUrl = await fileToDataUrl(file)
    setShot({ pngBase64: dataUrl.split(',')[1] ?? '', previewUrl: dataUrl })
  }

  const insert = useMutation({
    mutationFn: async (): Promise<InsertOutcome> => {
      if (shot === null) {
        throw new Error('no capture')
      }
      const target = useCaptureStore.getState().snapTarget
      if (target !== null) {
        const drawingId = await target.insert(shot.pngBase64)
        if (drawingId === null) {
          throw new Error('insert failed')
        }
        return {
          noteId: target.noteId,
          title: target.title,
          drawingId,
          remove: target.remove,
        }
      }
      const course = courseId !== null ? { id: courseId } : scratchpad.data?.course
      if (!course) {
        throw new Error('scratchpad unavailable')
      }
      const note = await createNote({
        title: t('capture.snapNoteTitle'),
        body_md: '',
        course_id: course.id,
      })
      const updated = await addDrawing(note.id, [], shot.pngBase64, false, null)
      const drawingId = updated.drawings[0]?.id
      if (drawingId === undefined) {
        throw new Error('insert failed')
      }
      await updateNote(note.id, { body_md: `![screenshot](ca-drawing://${drawingId})` })
      await invalidate()
      return {
        noteId: note.id,
        title: note.title,
        drawingId,
        remove: async (id) => {
          await deleteDrawing(note.id, id)
          await invalidate()
        },
      }
    },
    onSuccess: (outcome) => {
      setSaved(outcome)
      setShot(null)
      setFailed(false)
      closeSnap()
    },
    onError: () => setFailed(true),
  })

  const undo = useMutation({
    mutationFn: async () => {
      if (saved === null) {
        return
      }
      await saved.remove(saved.drawingId)
    },
    onSuccess: () => {
      setSaved(null)
    },
  })

  return (
    <>
      <RegionCrop
        open={open && shot === null}
        title={t('capture.snapTitle')}
        confirmLabel={t('capture.snapConfirm')}
        onCapture={capture}
        onClose={closeSnap}
      />
      <AnimatePresence>
        {open && shot !== null ? (
          <motion.div
            key="snap-review"
            className="bg-surface border-border fixed top-1/2 left-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border p-4 shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-label={t('capture.snapReviewTitle')}
            initial={presets.panel.initial}
            animate={presets.panel.animate}
            exit={presets.panel.exit}
            transition={presets.panel.transition}
          >
            <div className="mb-2 flex items-center gap-2">
              <Camera className="text-muted-foreground size-4 shrink-0" aria-hidden />
              <p className="flex-1 truncate text-sm font-semibold">
                {t('capture.snapReviewTitle')}
              </p>
            </div>
            <img
              src={shot.previewUrl}
              alt={t('capture.snapReviewTitle')}
              className="border-border max-h-[45vh] w-full rounded-md border object-contain"
            />
            {failed ? (
              <p className="text-warning mt-2 text-xs" role="alert">
                {t('capture.snapInsertFailed')}
              </p>
            ) : null}
            <div className="border-border mt-3 flex justify-end gap-2 border-t pt-3">
              <Button
                variant="outline"
                size="sm"
                disabled={insert.isPending}
                onClick={() => {
                  setShot(null)
                  closeSnap()
                }}
              >
                {t('common.cancel')}
              </Button>
              <Button size="sm" disabled={insert.isPending} onClick={() => insert.mutate()}>
                {insert.isPending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
                {t('capture.snapInsert')}
              </Button>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      <AnimatePresence>
        {saved !== null ? (
          <motion.div
            key="snap-saved"
            className="fixed right-4 bottom-4 z-50"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={presets.panel.transition}
          >
            <UndoNotice
              message={t('capture.snapSavedMessage', { title: saved.title })}
              actionLabel={t('capture.undo')}
              onUndo={() => undo.mutate()}
              undoing={undo.isPending}
              duration={8000}
              onDismiss={() => setSaved(null)}
            />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  )
}

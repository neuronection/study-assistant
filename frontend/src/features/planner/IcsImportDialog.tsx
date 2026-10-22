import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarPlus, Loader2 } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  Modal,
  ModalContent,
  ModalDescription,
  ModalHeader,
  ModalTitle,
} from '@neuronection/assistant-ui'
import { importIcs, previewIcsImport, type IcsPreview } from '@/lib/api'

type IcsImportDialogProps = {
  open: boolean
  courseId: string
  onClose: () => void
}

export function IcsImportDialog({ open, courseId, onClose }: IcsImportDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<IcsPreview | null>(null)
  const [confirmExam, setConfirmExam] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ created: number; updated: number } | null>(null)

  const reset = () => {
    setFile(null)
    setPreview(null)
    setConfirmExam(false)
    setError(null)
    setResult(null)
    if (input.current) input.current.value = ''
  }

  const close = () => {
    reset()
    onClose()
  }

  const stage = useMutation({
    mutationFn: async (chosen: File) => previewIcsImport(courseId, chosen),
    onSuccess: (body) => {
      setPreview(body)
      setError(null)
      setConfirmExam(false)
    },
    onError: (err: Error) => setError(err.message),
  })

  const commit = useMutation({
    mutationFn: async () => {
      if (file === null) throw new Error(t('planner.icsChoose'))
      return importIcs(courseId, file, confirmExam)
    },
    onSuccess: async (body) => {
      setResult({ created: body.created, updated: body.updated })
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['plan', courseId] })
      await queryClient.invalidateQueries({ queryKey: ['plan-upcoming'] })
      await queryClient.invalidateQueries({ queryKey: ['exam-status'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const examCandidate = preview?.exam_candidates[0] ?? null

  return (
    <Modal open={open} onOpenChange={(next) => !next && close()}>
      <ModalContent size="lg" closeLabel={t('common.close')}>
        <ModalHeader>
          <ModalTitle className="text-base">{t('planner.icsTitle')}</ModalTitle>
          <ModalDescription>{t('planner.icsHint')}</ModalDescription>
        </ModalHeader>
        <div className="space-y-3 px-6 pb-6" data-testid="ics-import-dialog">
          <input
            ref={input}
            type="file"
            accept=".ics,text/calendar"
            aria-label={t('planner.icsChoose')}
            onChange={(event) => {
              const chosen = event.target.files?.[0] ?? null
              setFile(chosen)
              setPreview(null)
              setResult(null)
              setError(null)
              if (chosen) stage.mutate(chosen)
            }}
          />
          {stage.isPending ? (
            <p className="text-muted-foreground text-xs" role="status">
              <Loader2 className="mr-1 inline animate-spin" aria-hidden />
              {t('planner.icsReading')}
            </p>
          ) : null}
          {preview !== null ? (
            <div className="space-y-2">
              <p className="text-muted-foreground text-xs">
                {t('planner.icsPreviewSummary', {
                  count: preview.events.length,
                  skipped: preview.skipped,
                })}
              </p>
              <ul className="border-border max-h-64 space-y-1 overflow-y-auto rounded-md border p-2 text-xs">
                {preview.events.map((event) => (
                  <li key={event.uid} className="flex items-center justify-between gap-2">
                    <span className="truncate" title={event.title}>
                      {event.title}
                    </span>
                    <span className="text-muted-foreground shrink-0">
                      {event.date}
                      {event.time ? ` · ${event.time}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
              {examCandidate !== null ? (
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={confirmExam}
                    onChange={(event) => setConfirmExam(event.target.checked)}
                  />
                  {t('planner.icsConfirmExam', {
                    title: examCandidate.title,
                    date: examCandidate.date,
                  })}
                </label>
              ) : null}
            </div>
          ) : null}
          {result !== null ? (
            <p className="text-sm" role="status">
              {t('planner.icsResult', { created: result.created, updated: result.updated })}
            </p>
          ) : null}
          {error !== null ? (
            <p className="text-destructive text-xs" role="alert">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={close}>
              {t('common.close')}
            </Button>
            <Button
              size="sm"
              disabled={file === null || preview === null || commit.isPending}
              onClick={() => commit.mutate()}
            >
              {commit.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <CalendarPlus aria-hidden />
              )}
              {t('planner.icsImport')}
            </Button>
          </div>
        </div>
      </ModalContent>
    </Modal>
  )
}

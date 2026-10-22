import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FileUp, Loader2 } from 'lucide-react'
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
import { importBibliography } from '@/lib/api'

type BibliographyImportDialogProps = {
  open: boolean
  courseId: string | null
  nodeId?: string | null
  onClose: () => void
}

export function BibliographyImportDialog({
  open,
  courseId,
  nodeId,
  onClose,
}: BibliographyImportDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ created: number; deduped: number } | null>(null)

  const reset = () => {
    setFile(null)
    setError(null)
    setResult(null)
    if (input.current) input.current.value = ''
  }

  const close = () => {
    reset()
    onClose()
  }

  const run = useMutation({
    mutationFn: async () => {
      if (courseId === null) throw new Error(t('workspace.openCourseFirst'))
      if (file === null) throw new Error(t('library.bibliographyChoose'))
      return importBibliography(courseId, file, nodeId)
    },
    onSuccess: async (body) => {
      setError(null)
      setResult({ created: body.created, deduped: body.deduped })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <Modal open={open} onOpenChange={(next) => !next && close()}>
      <ModalContent size="md" closeLabel={t('common.close')}>
        <ModalHeader>
          <ModalTitle className="text-base">{t('library.bibliographyTitle')}</ModalTitle>
          <ModalDescription>{t('library.bibliographyHint')}</ModalDescription>
        </ModalHeader>
        <div className="space-y-3 px-6 pb-6" data-testid="bibliography-import-dialog">
          <input
            ref={input}
            type="file"
            accept=".bib,.ris,text/plain"
            aria-label={t('library.bibliographyChoose')}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null)
              setResult(null)
              setError(null)
            }}
          />
          {result !== null ? (
            <p className="text-sm" role="status">
              {t('library.bibliographyResult', {
                created: result.created,
                deduped: result.deduped,
              })}
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
              disabled={file === null || run.isPending || courseId === null}
              onClick={() => run.mutate()}
            >
              {run.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <FileUp aria-hidden />
              )}
              {t('library.bibliographyImport')}
            </Button>
          </div>
        </div>
      </ModalContent>
    </Modal>
  )
}

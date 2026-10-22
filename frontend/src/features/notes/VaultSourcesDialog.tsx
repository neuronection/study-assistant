import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FolderPlus, Loader2, RefreshCw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  Modal,
  ModalContent,
  ModalDescription,
  ModalHeader,
  ModalTitle,
} from '@neuronection/assistant-ui'
import { FolderPickerDialog } from '@/features/library/FolderPickerDialog'
import {
  addSource,
  deleteSource,
  listSources,
  scanSource,
  vaultExportUrl,
} from '@/lib/api'

type VaultSourcesDialogProps = {
  open: boolean
  courseId: string
  onClose: () => void
}

export function VaultSourcesDialog({ open, courseId, onClose }: VaultSourcesDialogProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [picking, setPicking] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const sources = useQuery({
    queryKey: ['sources'],
    queryFn: listSources,
    enabled: open,
  })
  const vaults = (sources.data ?? []).filter(
    (source) => source.preset === 'vault' && source.course_id === courseId
  )

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['sources'] })
    await queryClient.invalidateQueries({ queryKey: ['notes'] })
    await queryClient.invalidateQueries({ queryKey: ['note-tags'] })
  }

  const add = useMutation({
    mutationFn: (path: string) =>
      addSource({
        label: path.split('/').filter(Boolean).pop() ?? 'vault',
        path,
        course_id: courseId,
        preset: 'vault',
      }),
    onSuccess: async (source) => {
      setPicking(false)
      setNotice(null)
      await refresh()
      await scanSource(source.id)
      await refresh()
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const scan = useMutation({
    mutationFn: (sourceId: string) => scanSource(sourceId),
    onSuccess: async () => {
      setNotice(null)
      await refresh()
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const remove = useMutation({
    mutationFn: (sourceId: string) => deleteSource(sourceId),
    onSuccess: async () => {
      await refresh()
    },
    onError: (error: Error) => setNotice(error.message),
  })

  return (
    <>
      <Modal open={open && !picking} onOpenChange={(next) => !next && onClose()}>
        <ModalContent size="md" closeLabel={t('common.close')}>
          <ModalHeader>
            <ModalTitle className="text-base">{t('notes.vaultTitle')}</ModalTitle>
            <ModalDescription>{t('notes.vaultHint')}</ModalDescription>
          </ModalHeader>
          <div className="space-y-3 px-6 pb-6" data-testid="vault-sources-dialog">
            {vaults.length === 0 ? (
              <p className="text-muted-foreground text-xs">{t('notes.vaultEmpty')}</p>
            ) : (
              <ul className="space-y-2">
                {vaults.map((source) => (
                  <li
                    key={source.id}
                    className="border-border flex items-center justify-between gap-2 rounded-md border p-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm" title={source.path}>
                        {source.label}
                      </p>
                      <p className="text-muted-foreground truncate text-[11px]">
                        {t('notes.vaultNoteCount', { count: source.note_count ?? 0 })}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        title={t('notes.vaultRescan')}
                        disabled={scan.isPending}
                        onClick={() => scan.mutate(source.id)}
                      >
                        {scan.isPending ? (
                          <Loader2 className="animate-spin" aria-hidden />
                        ) : (
                          <RefreshCw aria-hidden />
                        )}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        title={t('notes.vaultUnlink')}
                        onClick={() => remove.mutate(source.id)}
                      >
                        <Trash2 aria-hidden />
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {notice !== null ? (
              <p className="text-destructive text-xs" role="alert">
                {notice}
              </p>
            ) : null}
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => window.open(vaultExportUrl(courseId), '_blank')}
              >
                <Download aria-hidden />
                {t('notes.vaultExport')}
              </Button>
              <Button size="sm" onClick={() => setPicking(true)}>
                <FolderPlus aria-hidden />
                {t('notes.vaultAdd')}
              </Button>
            </div>
          </div>
        </ModalContent>
      </Modal>
      {picking ? (
        <FolderPickerDialog
          title={t('notes.vaultPick')}
          onChoose={(path) => add.mutate(path)}
          onCancel={() => setPicking(false)}
        />
      ) : null}
    </>
  )
}

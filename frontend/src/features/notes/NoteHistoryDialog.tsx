import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ErrorBanner'
import { getNoteVersion, listNoteVersions, restoreNoteVersion } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

const CAUSE_KEYS: Record<string, string> = {
  'autosave-coalesced': 'notes.versionCause.autosave',
  manual: 'notes.versionCause.manual',
  restore: 'notes.versionCause.restore',
}

export function NoteHistoryDialog({
  noteId,
  dirty,
  onSaveVersion,
  onRestored,
  onClose,
}: {
  noteId: number
  dirty: boolean
  onSaveVersion: () => Promise<unknown>
  onRestored: () => void
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [picked, setPicked] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const versions = useQuery({
    queryKey: ['note', noteId, 'versions'],
    queryFn: () => listNoteVersions(noteId),
  })

  const selectedVersion = useQuery({
    queryKey: ['note', noteId, 'versions', picked],
    queryFn: () => getNoteVersion(noteId, picked as number),
    enabled: picked !== null,
  })

  const restore = useMutation({
    mutationFn: () => restoreNoteVersion(noteId, picked as number),
    onSuccess: async () => {
      onRestored()
      await queryClient.invalidateQueries({ queryKey: ['note', noteId] })
      await queryClient.invalidateQueries({ queryKey: ['notes'] })
      await queryClient.invalidateQueries({ queryKey: ['note', noteId, 'versions'] })
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  const saveVersion = useMutation({
    mutationFn: () => onSaveVersion(),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['note', noteId, 'versions'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[85vh] w-full max-w-2xl overflow-y-auto">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="size-4" aria-hidden />
            {t('notes.historyTitle')}
          </CardTitle>
          <CardDescription>{t('notes.historyHint')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {versions.isLoading ? (
            <Loader2
              className="text-muted-foreground animate-spin"
              aria-label={t('library.loading')}
            />
          ) : (
            <ul className="max-h-40 space-y-1 overflow-y-auto">
              {(versions.data ?? []).map((entry) => (
                <li key={entry.version_id}>
                  <button
                    type="button"
                    className={
                      picked === entry.version_id
                        ? 'bg-primary/10 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs'
                        : 'hover:bg-subtle flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs'
                    }
                    onClick={() => setPicked(entry.version_id)}
                  >
                    <span className="font-medium">#{entry.version_id}</span>
                    <span className="bg-subtle rounded px-1.5 py-0.5 font-medium">
                      {t(CAUSE_KEYS[entry.cause] ?? 'notes.versionCause.autosave')}
                    </span>
                    <span className="text-muted-foreground">
                      {t('notes.historyChars', { chars: entry.chars })}
                    </span>
                    <span className="text-muted-foreground ml-auto shrink-0">
                      {new Date(entry.created_at).toLocaleString()}
                    </span>
                  </button>
                </li>
              ))}
              {(versions.data ?? []).length === 0 ? (
                <li className="text-muted-foreground p-2 text-xs">
                  {t('notes.historyEmpty')}
                </li>
              ) : null}
            </ul>
          )}
          {selectedVersion.data ? (
            <div className="border-border h-64 overflow-y-auto rounded-md border p-3">
              <BlockRenderer
                blocks={[{ type: 'text', md: selectedVersion.data.body_md }] as Block[]}
              />
            </div>
          ) : null}
          {dirty ? (
            <p className="text-warning text-xs">{t('notes.historyDirtyWarning')}</p>
          ) : null}
          <ErrorBanner message={error} />
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
            >
              {t('settings.cancel')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={saveVersion.isPending}
              onClick={() => saveVersion.mutate()}
            >
              {saveVersion.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : null}
              {t('notes.saveVersionNow')}
            </Button>
            <Button
              size="sm"
              disabled={picked === null || !selectedVersion.data || restore.isPending}
              onClick={() => restore.mutate()}
            >
              {restore.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('notes.restore')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

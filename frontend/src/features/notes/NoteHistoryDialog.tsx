import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Loader2, Scale } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DiffView } from '@/components/diff/DiffView'
import { ErrorBanner } from '@/components/ErrorBanner'
import {
  diffNoteVersions,
  getNoteVersion,
  listNoteVersions,
  restoreNoteVersion,
} from '@/lib/api'
import { formatDateTime } from '@/lib/format'
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
  const [compareBase, setCompareBase] = useState<string>('')
  const [compareTarget, setCompareTarget] = useState<string>('current')

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

  const fromRef = compareBase || (picked !== null ? String(picked) : '')
  const canCompare = fromRef !== ''
  const diff = useQuery({
    queryKey: ['note', noteId, 'versions', 'diff', fromRef, compareTarget],
    queryFn: () => diffNoteVersions(noteId, fromRef, compareTarget),
    enabled: canCompare,
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
                      {formatDateTime(entry.created_at)}
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
          {picked !== null ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs">
                <Scale className="text-muted-foreground size-3.5" aria-hidden />
                <span className="text-muted-foreground">{t('notes.compareLabel')}</span>
                <select
                  aria-label={t('notes.compareBase')}
                  className="border-border bg-surface rounded-md border px-2 py-1 text-xs"
                  value={compareBase}
                  onChange={(event) => setCompareBase(event.target.value)}
                >
                  <option value="">
                    {t('notes.comparePickVersion', { id: picked })}
                  </option>
                  {(versions.data ?? []).map((entry) => (
                    <option key={entry.version_id} value={String(entry.version_id)}>
                      #{entry.version_id}
                    </option>
                  ))}
                </select>
                <span className="text-muted-foreground">→</span>
                <select
                  aria-label={t('notes.compareTarget')}
                  className="border-border bg-surface rounded-md border px-2 py-1 text-xs"
                  value={compareTarget}
                  onChange={(event) => setCompareTarget(event.target.value)}
                >
                  <option value="current">{t('notes.compareCurrent')}</option>
                  {(versions.data ?? []).map((entry) => (
                    <option key={entry.version_id} value={String(entry.version_id)}>
                      #{entry.version_id}
                    </option>
                  ))}
                </select>
              </div>
              {diff.isLoading ? (
                <Loader2 className="text-muted-foreground animate-spin" aria-hidden />
              ) : diff.data ? (
                <div>
                  <p className="text-muted-foreground mb-1 text-[11px]">
                    {t('notes.compareStats', {
                      additions: diff.data.additions,
                      deletions: diff.data.deletions,
                    })}
                  </p>
                  <DiffView diff={diff.data.diff} className="max-h-72 overflow-y-auto" />
                </div>
              ) : null}
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

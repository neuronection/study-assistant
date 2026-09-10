import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Loader2, Scale } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DiffView } from '@/components/diff/DiffView'
import { ErrorBanner } from '@/components/ErrorBanner'
import {
  diffExtractionVersions,
  editExtraction,
  getExtractionVersion,
  listExtractionVersions,
} from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function ExtractionHistoryDialog({
  materialId,
  onClose,
}: {
  materialId: number
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [picked, setPicked] = useState<number | null>(null)
  const [compareBase, setCompareBase] = useState<string>('')
  const [compareTarget, setCompareTarget] = useState<string>('current')
  const [error, setError] = useState<string | null>(null)

  const versions = useQuery({
    queryKey: ['material', materialId, 'extractions'],
    queryFn: () => listExtractionVersions(materialId),
  })

  const fromRef = compareBase || (picked !== null ? String(picked) : '')
  const diff = useQuery({
    queryKey: ['material', materialId, 'extractions', 'diff', fromRef, compareTarget],
    queryFn: () => diffExtractionVersions(materialId, fromRef, compareTarget),
    enabled: fromRef !== '',
  })

  const restore = useMutation({
    mutationFn: async () => {
      const detail = await getExtractionVersion(materialId, picked as number)
      await editExtraction(materialId, detail.markdown)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      await queryClient.invalidateQueries({
        queryKey: ['material', materialId, 'extractions'],
      })
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[85vh] w-full max-w-2xl overflow-y-auto">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <History className="size-4" aria-hidden />
            {t('library.extractionHistoryTitle')}
          </CardTitle>
          <CardDescription>{t('library.extractionHistoryHint')}</CardDescription>
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
                <li key={entry.version}>
                  <button
                    type="button"
                    className={
                      picked === entry.version
                        ? 'bg-primary/10 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs'
                        : 'hover:bg-subtle flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs'
                    }
                    onClick={() => setPicked(entry.version)}
                  >
                    <span className="font-medium">{t('library.extractionVersionShort', { version: entry.version })}</span>
                    <span className="text-muted-foreground">{entry.extractor}</span>
                    <span className="text-muted-foreground ml-auto shrink-0">
                      {formatDateTime(entry.created_at)}
                    </span>
                  </button>
                </li>
              ))}
              {(versions.data ?? []).length === 0 ? (
                <li className="text-muted-foreground p-2 text-xs">
                  {t('library.extractionHistoryEmpty')}
                </li>
              ) : null}
            </ul>
          )}
          {picked !== null ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs">
                <Scale className="text-muted-foreground size-3.5" aria-hidden />
                <span className="text-muted-foreground">
                  {t('library.extractionCompareLabel')}
                </span>
                <select
                  aria-label={t('library.extractionCompareBase')}
                  className="border-border bg-surface rounded-md border px-2 py-1 text-xs"
                  value={compareBase}
                  onChange={(event) => setCompareBase(event.target.value)}
                >
                  <option value="">
                    {t('library.extractionComparePick', { version: picked })}
                  </option>
                  {(versions.data ?? []).map((entry) => (
                    <option key={entry.version} value={String(entry.version)}>
                      {t('library.extractionVersionShort', { version: entry.version })}
                    </option>
                  ))}
                </select>
                <span className="text-muted-foreground">→</span>
                <select
                  aria-label={t('library.extractionCompareTarget')}
                  className="border-border bg-surface rounded-md border px-2 py-1 text-xs"
                  value={compareTarget}
                  onChange={(event) => setCompareTarget(event.target.value)}
                >
                  <option value="current">{t('library.extractionCompareCurrent')}</option>
                  {(versions.data ?? []).map((entry) => (
                    <option key={entry.version} value={String(entry.version)}>
                      {t('library.extractionVersionShort', { version: entry.version })}
                    </option>
                  ))}
                </select>
              </div>
              {diff.isLoading ? (
                <Loader2 className="text-muted-foreground animate-spin" aria-hidden />
              ) : diff.data ? (
                <div>
                  <p className="text-muted-foreground mb-1 text-[11px]">
                    {t('library.extractionCompareStats', {
                      additions: diff.data.additions,
                      deletions: diff.data.deletions,
                    })}
                  </p>
                  <DiffView diff={diff.data.diff} className="max-h-72 overflow-y-auto" />
                </div>
              ) : null}
            </div>
          ) : null}
          <ErrorBanner message={error} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              {t('settings.cancel')}
            </Button>
            <Button
              size="sm"
              disabled={picked === null || restore.isPending}
              onClick={() => restore.mutate()}
            >
              {restore.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('library.extractionRestore')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

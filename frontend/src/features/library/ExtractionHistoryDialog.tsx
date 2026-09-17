import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Loader2, Scale } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DiffView } from '@/components/diff/DiffView'
import { MarkdownDiffView } from '@/components/ui/markdown-diff-view'
import { ErrorBanner } from '@/components/ErrorBanner'
import { cn } from '@/lib/utils'
import {
  diffExtractionVersions,
  editExtraction,
  getExtractionVersion,
  getMaterial,
  listExtractionVersions,
} from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { useCloseFloatings } from '@/lib/ui-overlays'

const FORMATTED_CAP = 100_000

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
  const [diffMode, setDiffMode] = useState<'formatted' | 'raw'>('formatted')
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

  const baseVersion = Number(fromRef)
  const baseIsNumeric = fromRef !== '' && Number.isFinite(baseVersion)
  const targetVersion = compareTarget !== 'current' ? Number(compareTarget) : null
  const baseMd = useQuery({
    queryKey: ['material', materialId, 'extractions', 'markdown', baseVersion],
    queryFn: () => getExtractionVersion(materialId, baseVersion),
    enabled: diffMode === 'formatted' && baseIsNumeric,
  })
  const currentMd = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
    enabled: diffMode === 'formatted' && targetVersion === null && compareTarget === 'current',
  })
  const targetMd = useQuery({
    queryKey: ['material', materialId, 'extractions', 'markdown', targetVersion ?? 0],
    queryFn: () => getExtractionVersion(materialId, targetVersion as number),
    enabled: diffMode === 'formatted' && targetVersion !== null,
  })
  const before = baseMd.data?.markdown ?? null
  const after =
    targetVersion === null
      ? (currentMd.data?.extraction?.markdown ?? null)
      : (targetMd.data?.markdown ?? null)
  const markdownsReady = before !== null && after !== null
  const withinCap =
    markdownsReady && before.length <= FORMATTED_CAP && (after?.length ?? 0) <= FORMATTED_CAP
  const showFormatted = diffMode === 'formatted' && markdownsReady && withinCap
  const overCap =
    diffMode === 'formatted' &&
    markdownsReady &&
    !withinCap

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
              {diff.isLoading ||
              (diffMode === 'formatted' && diff.data && (baseMd.fetchStatus === 'fetching' || currentMd.fetchStatus === 'fetching' || targetMd.fetchStatus === 'fetching')) ? (
                <Loader2 className="text-muted-foreground animate-spin" aria-hidden />
              ) : diff.data ? (
                <div>
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <p className="text-muted-foreground text-[11px]">
                      {t('library.extractionCompareStats', {
                        additions: diff.data.additions,
                        deletions: diff.data.deletions,
                      })}
                    </p>
                    <div className="border-border bg-subtle inline-flex overflow-hidden rounded-md border text-[10px] font-medium">
                      <button
                        type="button"
                        aria-pressed={diffMode === 'formatted'}
                        onClick={() => setDiffMode('formatted')}
                        className={cn(
                          'text-muted-foreground px-2 py-0.5',
                          diffMode === 'formatted' && 'bg-surface text-foreground',
                        )}
                      >
                        {t('diff.formatted')}
                      </button>
                      <button
                        type="button"
                        aria-pressed={diffMode === 'raw'}
                        onClick={() => setDiffMode('raw')}
                        className={cn(
                          'text-muted-foreground px-2 py-0.5',
                          diffMode === 'raw' && 'bg-surface text-foreground',
                        )}
                      >
                        {t('diff.raw')}
                      </button>
                    </div>
                  </div>
                  {showFormatted ? (
                    <div className="max-h-72 overflow-y-auto">
                      <MarkdownDiffView
                        original={before}
                        suggested={after}
                        className="w-full"
                        labels={{
                          original: t('diff.original'),
                          suggested: t('diff.suggested'),
                          unchangedBlocks: (count) =>
                            t('diff.unchangedBlocks', { count }),
                          showLess: t('diff.showLess'),
                          prevChange: t('diff.prevChange'),
                          nextChange: t('diff.nextChange'),
                          changePosition: (index, total) =>
                            t('diff.changePosition', { index, total }),
                          noChanges: t('diff.noChanges'),
                        }}
                      />
                    </div>
                  ) : (
                    <>
                      {overCap ? (
                        <p className="text-muted-foreground mb-1 text-[11px]">
                          {t('library.diffTooLarge')}
                        </p>
                      ) : null}
                      <DiffView diff={diff.data.diff} className="max-h-72 overflow-y-auto" />
                    </>
                  )}
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

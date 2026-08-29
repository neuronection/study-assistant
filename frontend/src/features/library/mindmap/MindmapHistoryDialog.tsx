import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { History, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ErrorBanner'
import { editExtraction, getExtractionVersion, listExtractionVersions } from '@/lib/api'
import { MindmapCanvas } from './MindmapCanvas'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function MindmapHistoryDialog({
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
  const [error, setError] = useState<string | null>(null)

  const versions = useQuery({
    queryKey: ['material', materialId, 'extractions'],
    queryFn: () => listExtractionVersions(materialId),
  })

  const selectedVersion = useQuery({
    queryKey: ['material', materialId, 'extractions', picked],
    queryFn: () => getExtractionVersion(materialId, picked as number),
    enabled: picked !== null,
  })

  const restore = useMutation({
    mutationFn: () => editExtraction(materialId, selectedVersion.data?.markdown ?? ''),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
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
            {t('mindmapEdit.historyTitle')}
          </CardTitle>
          <CardDescription>{t('mindmapEdit.historyHint')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {versions.isLoading ? (
            <Loader2 className="text-muted-foreground animate-spin" aria-label={t('library.loading')} />
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
                    <span className="font-medium">
                      {t('mindmapEdit.versionLabel', { version: entry.version })}
                    </span>
                    <span className="text-muted-foreground">{entry.extractor}</span>
                    <span className="text-muted-foreground ml-auto shrink-0">
                      {new Date(entry.created_at).toLocaleString()}
                    </span>
                  </button>
                </li>
              ))}
              {(versions.data ?? []).length === 0 ? (
                <li className="text-muted-foreground p-2 text-xs">
                  {t('mindmapEdit.historyEmpty')}
                </li>
              ) : null}
            </ul>
          )}
          {selectedVersion.data ? (
            <div className="border-border h-64 overflow-hidden rounded-md border">
              <MindmapCanvas
                markdown={selectedVersion.data.markdown}
                ariaLabel={t('mindmapEdit.historyTitle')}
                className="h-full w-full"
              />
            </div>
          ) : null}
          <ErrorBanner message={error} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              {t('settings.cancel')}
            </Button>
            <Button
              size="sm"
              disabled={picked === null || !selectedVersion.data || restore.isPending}
              onClick={() => restore.mutate()}
            >
              {restore.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
              {t('mindmapEdit.restore')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

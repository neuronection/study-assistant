import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Sparkles, Wand2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ErrorBanner'
import { editExtraction, mindmapEdit } from '@/lib/api'
import { MindmapCanvas } from './MindmapCanvas'
import { useCloseFloatings } from '@/lib/ui-overlays'

const MODES = ['expand', 'simplify', 'reorganize', 'examples', 'custom'] as const

export function MindmapEditDialog({
  materialId,
  focusNode,
  onClose,
  onApplied,
}: {
  materialId: number
  focusNode?: string
  onClose: () => void
  onApplied: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [mode, setMode] = useState<string>('expand')
  const [instruction, setInstruction] = useState('')
  const [preview, setPreview] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const generate = useMutation({
    mutationFn: () =>
      mindmapEdit(materialId, {
        mode,
        instruction: instruction.trim() || null,
        focus_node: focusNode ?? null,
      }),
    onSuccess: (result) => {
      setError(null)
      setPreview(result.markdown)
    },
    onError: (err: Error) => setError(err.message),
  })

  const apply = useMutation({
    mutationFn: () => editExtraction(materialId, preview as string),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['material', materialId] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
      onApplied()
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[85vh] w-full max-w-lg overflow-y-auto">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Wand2 className="size-4" aria-hidden />
            {t('mindmapEdit.title')}
          </CardTitle>
          <CardDescription>
            {focusNode
              ? t('mindmapEdit.focusNode', { node: focusNode })
              : t('mindmapEdit.hint')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {preview === null ? (
            <>
              <label className="flex flex-col gap-1 text-xs">
                {t('mindmapEdit.mode')}
                <select
                  className="bg-surface border-border rounded-md border px-2 py-1.5 text-xs"
                  value={mode}
                  onChange={(event) => setMode(event.target.value)}
                >
                  {MODES.map((entry) => (
                    <option key={entry} value={entry}>
                      {t(`mindmapEdit.mode_${entry}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs">
                {t('mindmapEdit.instruction')}
                <textarea
                  className="bg-surface border-border min-h-20 w-full rounded-md border px-2 py-1.5 text-xs"
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                  placeholder={t('mindmapEdit.instructionPlaceholder')}
                />
              </label>
            </>
          ) : (
            <div className="border-border h-72 overflow-hidden rounded-md border">
              <MindmapCanvas
                markdown={preview}
                ariaLabel={t('mindmapEdit.title')}
                className="h-full w-full"
              />
            </div>
          )}
          <ErrorBanner message={error} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              {t('settings.cancel')}
            </Button>
            {preview === null ? (
              <Button size="sm" disabled={generate.isPending} onClick={() => generate.mutate()}>
                {generate.isPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <Sparkles aria-hidden />
                )}
                {t('mindmapEdit.edit')}
              </Button>
            ) : (
              <>
                <Button variant="ghost" size="sm" onClick={() => setPreview(null)}>
                  {t('mindmapEdit.back')}
                </Button>
                <Button size="sm" disabled={apply.isPending} onClick={() => apply.mutate()}>
                  {apply.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                  {t('mindmapEdit.apply')}
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

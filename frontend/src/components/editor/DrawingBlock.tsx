import { useContext } from 'react'
import { Copy, Loader2, MoreHorizontal, Pencil, RefreshCw, Trash2, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type {
  DrawingActionHandler,
  DrawingMeta,
} from '@/components/editor/DrawingImage'
import { DrawingDiffContext } from '@/components/editor/drawingDiffContext'
import { PopoverMenu } from '@/components/ui/popover-menu'
import { TextDiffView } from '@/components/ui/text-diff-view'
import { cn } from '@/lib/utils'
import { useConfirm } from '@/lib/use-confirm'

export function DrawingBlock({
  drawingId,
  meta,
  onAction,
  menuVisible = true,
  selected = false,
}: {
  drawingId: number
  meta: DrawingMeta | undefined
  onAction: DrawingActionHandler
  menuVisible?: boolean
  selected?: boolean
}) {
  const { t } = useTranslation()
  const [confirm, confirmElement] = useConfirm()
  const diffStore = useContext(DrawingDiffContext)
  const ocrDiff = diffStore?.diffs.get(drawingId) ?? null
  return (
    <div className="space-y-1">
      {meta?.png_sha ? (
        <div
          data-drag-handle
          className={cn(
            'cursor-grab rounded-md active:cursor-grabbing',
            selected && 'ring-primary ring-2'
          )}
        >
          <img
            src={
              meta.png_sha.startsWith('data:')
                ? meta.png_sha
                : `/api/v1/blobs/${meta.png_sha}`
            }
            alt={t('notes.drawingAlt')}
            draggable={false}
            className="border-border bg-white h-auto max-w-full rounded-md border"
          />
        </div>
      ) : (
        <div className="border-border bg-subtle text-muted-foreground rounded-md border border-dashed p-3 text-xs">
          {t('notes.drawingMissing', { id: drawingId })}
        </div>
      )}
      {menuVisible ? (
        <div className="flex justify-end">
          <PopoverMenu
            label={t('notes.drawingMenu')}
            triggerClassName="size-7"
            trigger={<MoreHorizontal className="size-4" aria-hidden />}
            items={[
              {
                key: 'edit',
                label: t('notes.editDrawing'),
                icon: Pencil,
                onSelect: () => onAction(drawingId, 'edit'),
              },
              ...(meta?.png_sha && !meta.png_sha.startsWith('data:')
                ? [
                    {
                      key: 'reocr',
                      label: t('notes.reocrDrawing'),
                      icon: RefreshCw,
                      onSelect: () => onAction(drawingId, 'reocr'),
                    },
                  ]
                : []),
              ...(meta?.ocr_markdown
                ? [
                    {
                      key: 'copy',
                      label: t('notes.copyOcr'),
                      icon: Copy,
                      onSelect: () => onAction(drawingId, 'copy'),
                    },
                  ]
                : []),
              {
                key: 'delete',
                label: t('notes.deleteDrawing'),
                icon: Trash2,
                danger: true,
                onSelect: async () => {
                  const ok = await confirm({
                    title: t('notes.deleteDrawing'),
                    description: t('notes.confirmDeleteDrawing'),
                    confirmLabel: t('notes.deleteDrawing'),
                    cancelLabel: t('common.cancel'),
                    destructive: true,
                  })
                  if (ok) onAction(drawingId, 'delete')
                },
              },
            ]}
          />
        </div>
      ) : null}
      {meta?.ocr_job_id && !meta?.ocr_markdown ? (
        <p className="text-muted-foreground flex items-center gap-1.5 text-xs">
          <Loader2 className="size-3 animate-spin" aria-hidden />
          {t('notes.ocrPending')}
        </p>
      ) : null}
      {meta?.ocr_markdown ? (
        <details className="text-xs" open={ocrDiff !== null || undefined}>
          <summary
            className={cn(
              'text-muted-foreground flex cursor-pointer items-center gap-1.5',
              ocrDiff !== null && 'text-foreground'
            )}
          >
            {t('notes.transcript')}
            {ocrDiff !== null ? (
              <span className="bg-primary/10 text-primary border-primary/30 rounded-full border px-1.5 py-px text-[10px]">
                {t('notes.ocrDiffBadge')}
              </span>
            ) : null}
          </summary>
          {ocrDiff !== null ? (
            <div className="mt-1 space-y-1">
              <TextDiffView
                original={ocrDiff.before}
                suggested={ocrDiff.after}
                showHeader={false}
                showNav={false}
                contextLines={1}
                bodyClassName="max-h-64"
                labels={{ showLess: t('diff.showLess') }}
              />
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={() => diffStore?.dismiss(drawingId)}
                  className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-[11px] underline-offset-2 hover:underline"
                >
                  <X className="size-3" aria-hidden />
                  {t('notes.ocrDiffDismiss')}
                </button>
              </div>
            </div>
          ) : (
            <pre className="bg-subtle mt-1 rounded-md p-2 font-mono text-[11px] whitespace-pre-wrap">
              {meta.ocr_markdown}
            </pre>
          )}
        </details>
      ) : null}
      {confirmElement}
    </div>
  )
}

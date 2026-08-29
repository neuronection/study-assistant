import { Copy, Loader2, MoreHorizontal, Pencil, RefreshCw, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type {
  DrawingActionHandler,
  DrawingMeta,
} from '@/components/editor/DrawingImage'
import { PopoverMenu } from '@/components/ui/popover-menu'
import { cn } from '@/lib/utils'

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
                onSelect: () => {
                  if (window.confirm(t('notes.confirmDeleteDrawing'))) {
                    onAction(drawingId, 'delete')
                  }
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
        <details className="text-xs">
          <summary className="text-muted-foreground cursor-pointer">
            {t('notes.transcript')}
          </summary>
          <pre className="bg-subtle mt-1 rounded-md p-2 font-mono text-[11px] whitespace-pre-wrap">
            {meta.ocr_markdown}
          </pre>
        </details>
      ) : null}
    </div>
  )
}

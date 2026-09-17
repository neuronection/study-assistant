import { Loader2, Minimize2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { DrawCanvas, strokesToPng, type Stroke } from '@/components/canvas/DrawCanvas'
import { RegionCrop } from '@/components/capture/RegionCrop'
import { MathInput } from '@/components/math/MathInput'
import type { MaterialUploadController } from '@/components/materials/materialUpload'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

function dataUrlToFile(dataUrl: string, name: string): File {
  const [meta, base64] = dataUrl.split(',')
  const mime = meta.slice(meta.indexOf(':') + 1, meta.indexOf(';'))
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return new File([bytes], name, { type: mime })
}

function strokesFile(strokes: Stroke[]): File {
  const png = strokesToPng(strokes)
  if (png === null) {
    throw new Error('canvas-unavailable')
  }
  return dataUrlToFile(png, 'drawing.png')
}

export function EquationDialog({
  onInsert,
  onClose,
}: {
  onInsert: (latexBlock: string) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [latex, setLatex] = useState('')
  const [inline, setInline] = useState(true)
  const closeLabel = t('editor.close')
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-label={t('chat.composer.equation')}
        className="bg-surface border-border w-full max-w-lg rounded-xl border p-4 shadow-[var(--as-shadow-3)]"
      >
        <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
          {t('chat.composer.equation')}
          <button
            type="button"
            aria-label={closeLabel}
            title={closeLabel}
            className="text-muted-foreground hover:text-foreground ml-auto rounded p-1"
            onClick={onClose}
          >
            ×
          </button>
        </div>
        <p className="text-muted-foreground mb-2 text-xs">
          {t('chat.composer.equationHint')}
        </p>
        <MathInput value={latex} onChange={setLatex} />
        <label className="text-muted-foreground mt-2 flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={inline}
            onChange={(event) => setInline(event.target.checked)}
          />
          {t('chat.composer.inlineToggle')}
        </label>
        <div className="border-border mt-3 flex justify-end gap-2 border-t pt-3">
          <Button variant="outline" size="sm" onClick={onClose}>
            {t('notes.cancelDrawingEdit')}
          </Button>
          <Button
            size="sm"
            disabled={latex.trim().length === 0}
            onClick={() => {
              const content = latex.trim()
              onInsert(inline ? `$${content}$` : `$$\n${content}\n$$`)
              onClose()
            }}
          >
            {t('chat.composer.insert')}
          </Button>
        </div>
      </div>
    </div>
  )
}

export function ScreenshotDialog({
  upload,
  hint,
  onClose,
}: {
  upload: MaterialUploadController
  hint?: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  return (
    <RegionCrop
      open
      title={t('chat.composer.screenshotTitle')}
      hint={hint}
      confirmLabel={t('chat.composer.cropConfirm')}
      onCapture={async (file) => {
        await upload.uploadFiles([{ file, label: 'Screenshot' }])
        onClose()
      }}
    />
  )
}

export function DrawingDialog({
  upload,
  hint,
  onClose,
}: {
  upload: MaterialUploadController
  hint?: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [strokes, setStrokes] = useState<Stroke[]>([])
  const [fullscreen, setFullscreen] = useState(false)
  const [saving, setSaving] = useState(false)
  const save = async () => {
    if (strokes.length === 0 || saving || upload.uploading) {
      return
    }
    setSaving(true)
    try {
      await upload.uploadFiles([{ file: strokesFile(strokes), label: 'Drawing' }])
      onClose()
    } finally {
      setSaving(false)
    }
  }
  const savingDrawing = saving || upload.uploading
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-label={t('chat.composer.drawTitle')}
        className={cn(
          'bg-surface border-border flex flex-col shadow-[var(--as-shadow-3)]',
          fullscreen
            ? 'inset-0 fixed h-full max-h-full w-full rounded-none'
            : 'max-h-[90vh] w-full max-w-3xl rounded-xl border p-4'
        )}
      >
        <div className="mb-1 flex items-center justify-between gap-2">
          <p className="text-sm font-semibold">{t('chat.composer.drawTitle')}</p>
          {fullscreen ? (
            <Button
              variant="ghost"
              size="sm"
              aria-label={t('notes.exitFullscreen')}
              onClick={() => setFullscreen(false)}
            >
              <Minimize2 className="size-4" aria-hidden />
            </Button>
          ) : null}
        </div>
        {!fullscreen ? (
          <p className="text-muted-foreground mb-2 text-xs">
            {hint ?? t('chat.composer.drawHint')}
          </p>
        ) : null}
        <div className={fullscreen ? 'min-h-0 flex-1' : 'min-h-0 flex-1 overflow-y-auto'}>
          <DrawCanvas
            strokes={strokes}
            onChange={setStrokes}
            fullscreen={fullscreen}
            onToggleFullscreen={() => setFullscreen((value) => !value)}
            fillContainer={fullscreen}
          />
        </div>
        <div className="border-border mt-3 flex justify-end gap-2 border-t pt-3">
          {upload.uploading ? (
            <Loader2 className="size-4 self-center animate-spin" aria-hidden />
          ) : null}
          <Button variant="outline" size="sm" onClick={onClose}>
            {t('notes.cancelDrawingEdit')}
          </Button>
          <Button size="sm" disabled={strokes.length === 0 || savingDrawing} onClick={() => void save()}>
            {saving ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
            {t('chat.composer.saveDrawing')}
          </Button>
        </div>
      </div>
    </div>
  )
}


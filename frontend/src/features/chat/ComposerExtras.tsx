import { Loader2, Minimize2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { DrawCanvas, strokesToPng, type Stroke } from '@/components/canvas/DrawCanvas'
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
        className="bg-surface border-border w-full max-w-lg rounded-xl border p-4 shadow-xl"
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

interface CropRect {
  x: number
  y: number
  width: number
  height: number
}

function normalized(rect: CropRect): CropRect {
  return {
    x: rect.width < 0 ? rect.x + rect.width : rect.x,
    y: rect.height < 0 ? rect.y + rect.height : rect.y,
    width: Math.abs(rect.width),
    height: Math.abs(rect.height),
  }
}

async function captureScreen(): Promise<HTMLImageElement> {
  if (
    typeof navigator === 'undefined' ||
    typeof navigator.mediaDevices?.getDisplayMedia !== 'function'
  ) {
    throw new Error('unsupported')
  }
  const stream = await navigator.mediaDevices.getDisplayMedia({
    video: true,
    audio: false,
  })
  try {
    const video = document.createElement('video')
    video.srcObject = stream
    video.muted = true
    await new Promise<void>((resolve, reject) => {
      video.onloadedmetadata = () => resolve()
      video.onerror = () => reject(new Error('stream-failed'))
    })
    await video.play()
    await new Promise((resolve) => window.setTimeout(resolve, 150))
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    if (!canvas.width || !canvas.height) {
      throw new Error('empty-frame')
    }
    const context = canvas.getContext('2d')
    if (context === null) {
      throw new Error('no-context')
    }
    context.drawImage(video, 0, 0)
    const image = new Image()
    image.src = canvas.toDataURL('image/png')
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('decode-failed'))
    })
    return image
  } finally {
    for (const track of stream.getTracks()) track.stop()
  }
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
          'bg-surface border-border flex flex-col shadow-xl',
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
  const [frame, setFrame] = useState<HTMLImageElement | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)
  const [rect, setRect] = useState<CropRect | null>(null)
  const dragStart = useRef<{ x: number; y: number } | null>(null)

  const capture = useCallback(async () => {
    setBusy(true)
    setError(null)
    setRect(null)
    try {
      setFrame(await captureScreen())
    } catch {
      setFrame(null)
      setError(t('chat.composer.unsupported'))
    } finally {
      setBusy(false)
    }
  }, [t])

  useEffect(() => {
    void capture()
  }, [capture])

  const relativePoint = (event: React.PointerEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect()
    return {
      x: ((event.clientX - bounds.left) / bounds.width) * 100,
      y: ((event.clientY - bounds.top) / bounds.height) * 100,
    }
  }

  const attach = async () => {
    const image = frame
    const selection = rect !== null ? normalized(rect) : null
    if (image === null || busy || upload.uploading) {
      return
    }
    let file: File
    if (selection !== null && selection.width > 0 && selection.height > 0) {
      const scaleX = image.naturalWidth / 100
      const scaleY = image.naturalHeight / 100
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(1, Math.round(selection.width * scaleX))
      canvas.height = Math.max(1, Math.round(selection.height * scaleY))
      const context = canvas.getContext('2d')
      if (context === null) {
        return
      }
      context.drawImage(
        image,
        selection.x * scaleX,
        selection.y * scaleY,
        selection.width * scaleX,
        selection.height * scaleY,
        0,
        0,
        canvas.width,
        canvas.height,
      )
      file = dataUrlToFile(canvas.toDataURL('image/png'), 'screenshot.png')
    } else {
      file = dataUrlToFile(image.src, 'screenshot.png')
    }
    await upload.uploadFiles([{ file, label: 'Screenshot' }])
    onClose()
  }

  const cropUi = frame !== null && !busy
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-label={t('chat.composer.screenshotTitle')}
        className="bg-surface border-border flex max-h-[90vh] w-full max-w-3xl flex-col rounded-xl border p-4 shadow-xl"
      >
        <p className="mb-1 text-sm font-semibold">{t('chat.composer.screenshotTitle')}</p>
        <p className="text-muted-foreground mb-2 text-xs" role={error ? 'alert' : undefined}>
          {error ??
            (cropUi ? t('chat.composer.dragToSelect') : (hint ?? t('chat.composer.screenshotHint')))}
        </p>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {cropUi ? (
            <div
              className="relative touch-none select-none"
              onPointerDown={(event) => {
                event.currentTarget.setPointerCapture(event.pointerId)
                dragStart.current = relativePoint(event)
                setRect(null)
              }}
              onPointerMove={(event) => {
                const start = dragStart.current
                if (start === null) {
                  return
                }
                const point = relativePoint(event)
                setRect({
                  x: start.x,
                  y: start.y,
                  width: point.x - start.x,
                  height: point.y - start.y,
                })
              }}
              onPointerUp={() => {
                dragStart.current = null
              }}
              onPointerCancel={() => {
                dragStart.current = null
              }}
            >
              <img
                src={frame?.src}
                alt=""
                draggable={false}
                className="max-h-[55vh] w-full rounded-md object-contain"
              />
              {rect !== null ? (
                <div
                  aria-hidden
                  className="border-ring bg-primary/25 pointer-events-none absolute border-2"
                  style={{
                    left: `${normalized(rect).x}%`,
                    top: `${normalized(rect).y}%`,
                    width: `${normalized(rect).width}%`,
                    height: `${normalized(rect).height}%`,
                  }}
                />
              ) : null}
            </div>
          ) : (
            <Loader2 className="text-muted-foreground mx-auto my-8 size-6 animate-spin" aria-hidden />
          )}
        </div>
        <div className="border-border mt-3 flex justify-end gap-2 border-t pt-3">
          <Button variant="outline" size="sm" disabled={busy} onClick={() => void capture()}>
            {t('chat.composer.recapture')}
          </Button>
          <Button
            size="sm"
            disabled={busy || frame === null || upload.uploading}
            onClick={() => void attach()}
          >
            {upload.uploading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
            {t('chat.composer.cropConfirm')}
          </Button>
        </div>
      </div>
    </div>
  )
}

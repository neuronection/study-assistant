import { Loader2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'

export interface CropRect {
  x: number
  y: number
  width: number
  height: number
}

export function normalizedCrop(rect: CropRect): CropRect {
  return {
    x: rect.width < 0 ? rect.x + rect.width : rect.x,
    y: rect.height < 0 ? rect.y + rect.height : rect.y,
    width: Math.abs(rect.width),
    height: Math.abs(rect.height),
  }
}

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

export function RegionCrop({
  open,
  title,
  hint,
  confirmLabel,
  onCapture,
  onClose,
}: {
  open: boolean
  title: string
  hint?: string
  confirmLabel: string
  onCapture: (png: File, rect: CropRect | null) => void | Promise<void>
  onClose?: () => void
}) {
  const { t } = useTranslation()
  const [frame, setFrame] = useState<HTMLImageElement | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(true)
  const [pending, setPending] = useState(false)
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
      setError(t('capture.unsupported'))
    } finally {
      setBusy(false)
    }
  }, [t])

  useEffect(() => {
    if (!open) {
      return
    }
    setFrame(null)
    setRect(null)
    setError(null)
    setPending(false)
    void capture()
  }, [open, capture])

  const relativePoint = (event: React.PointerEvent<HTMLDivElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect()
    return {
      x: ((event.clientX - bounds.left) / bounds.width) * 100,
      y: ((event.clientY - bounds.top) / bounds.height) * 100,
    }
  }

  const confirm = async () => {
    const image = frame
    const selection = rect !== null ? normalizedCrop(rect) : null
    if (image === null || busy || pending) {
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
    setPending(true)
    try {
      await onCapture(file, selection)
    } finally {
      setPending(false)
    }
  }

  if (!open) {
    return null
  }
  const cropUi = frame !== null && !busy
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-label={title}
        className="bg-surface border-border flex max-h-[90vh] w-full max-w-3xl flex-col rounded-xl border p-4 shadow-[var(--as-shadow-3)]"
      >
        <p className="mb-1 text-sm font-semibold">{title}</p>
        <p className="text-muted-foreground mb-2 text-xs" role={error ? 'alert' : undefined}>
          {error ??
            (cropUi ? t('capture.dragToSelect') : (hint ?? t('capture.hint')))}
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
                    left: `${normalizedCrop(rect).x}%`,
                    top: `${normalizedCrop(rect).y}%`,
                    width: `${normalizedCrop(rect).width}%`,
                    height: `${normalizedCrop(rect).height}%`,
                  }}
                />
              ) : null}
            </div>
          ) : (
            <Loader2 className="text-muted-foreground mx-auto my-8 size-6 animate-spin" aria-hidden />
          )}
        </div>
        <div className="border-border mt-3 flex justify-end gap-2 border-t pt-3">
          {onClose ? (
            <Button variant="outline" size="sm" disabled={pending} onClick={onClose}>
              {t('notes.cancelDrawingEdit')}
            </Button>
          ) : null}
          <Button variant="outline" size="sm" disabled={busy || pending} onClick={() => void capture()}>
            {t('capture.recapture')}
          </Button>
          <Button size="sm" disabled={busy || pending || frame === null} onClick={() => void confirm()}>
            {pending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}

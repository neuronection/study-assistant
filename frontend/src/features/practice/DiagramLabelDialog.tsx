import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ImagePlus, Trash2, X } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { blobUrl, createExercise, listMaterials, type Material } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

interface Region {
  id: string
  x: number
  y: number
  w: number
  h: number
  label: string
}

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

function normalized(event: React.PointerEvent<HTMLDivElement>): { x: number; y: number } {
  const rect = event.currentTarget.getBoundingClientRect()
  return {
    x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)),
    y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)),
  }
}

export function DiagramLabelDialog({
  courseId,
  nodeId,
  onClose,
  onCreated,
}: {
  courseId: string
  nodeId: string | null
  onClose: () => void
  onCreated: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const materials = useQuery({
    queryKey: ['materials', courseId],
    queryFn: () => listMaterials(undefined, courseId),
  })
  const images = useMemo(
    () => (materials.data ?? []).filter((entry) => entry.kind === 'image' && entry.blob_sha),
    [materials.data]
  )
  const [image, setImage] = useState<Material | null>(null)
  const [title, setTitle] = useState('')
  const [regions, setRegions] = useState<Region[]>([])
  const [start, setStart] = useState<{ x: number; y: number } | null>(null)
  const [preview, setPreview] = useState<Rect | null>(null)
  const counter = useRef(1)

  const save = useMutation({
    mutationFn: () =>
      createExercise({
        course_id: courseId,
        node_id: nodeId,
        title: title.trim() || t('exercises.diagramDefaultTitle'),
        kind: 'diagram_label',
        steps: [
          {
            prompt_md: t('exercises.diagramPrompt'),
            expected: {
              kind: 'diagram_label',
              image_sha: image?.blob_sha,
              hotspots: regions.map((region) => ({
                id: region.id,
                x: region.x,
                y: region.y,
                w: region.w,
                h: region.h,
                label: region.label.trim(),
              })),
              labels: regions.map((region) => region.label.trim()),
              mode: 'click',
            },
          },
        ],
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['exercises'] })
      onCreated()
      onClose()
    },
  })

  const onDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) {
      return
    }
    const point = normalized(event)
    setStart(point)
    setPreview({ x: point.x, y: point.y, w: 0, h: 0 })
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const onMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (start === null) {
      return
    }
    const point = normalized(event)
    setPreview({
      x: Math.min(start.x, point.x),
      y: Math.min(start.y, point.y),
      w: Math.abs(point.x - start.x),
      h: Math.abs(point.y - start.y),
    })
  }
  const onUp = () => {
    if (preview !== null && preview.w > 0.02 && preview.h > 0.02) {
      const index = counter.current
      counter.current += 1
      setRegions((previous) => [
        ...previous,
        { id: `r${index}`, ...preview, label: t('exercises.diagramRegionLabel', { n: index }) },
      ])
    }
    setStart(null)
    setPreview(null)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('exercises.diagramTitle')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="bg-surface border-border flex max-h-[88vh] w-full max-w-2xl flex-col rounded-lg border shadow-[var(--as-shadow-3)]">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <ImagePlus className="text-primary size-4" aria-hidden />
            {t('exercises.diagramTitle')}
          </h2>
          <button
            type="button"
            aria-label={t('chat.close')}
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground rounded p-1"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {image === null ? (
            <>
              <p className="text-muted-foreground text-xs">{t('exercises.diagramPickImage')}</p>
              {materials.isLoading ? <Spinner /> : null}
              <div className="grid grid-cols-3 gap-2">
                {images.map((entry) => (
                  <button
                    key={entry.id}
                    type="button"
                    className="border-border hover:border-primary overflow-hidden rounded-md border text-left"
                    onClick={() => setImage(entry)}
                  >
                    <img
                      src={blobUrl(entry.blob_sha ?? '')}
                      alt=""
                      className="bg-subtle h-24 w-full object-cover"
                    />
                    <span className="block truncate px-2 py-1 text-[11px]">{entry.title}</span>
                  </button>
                ))}
              </div>
              {!materials.isLoading && images.length === 0 ? (
                <p className="text-muted-foreground text-xs">{t('exercises.diagramNoImages')}</p>
              ) : null}
            </>
          ) : (
            <>
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder={t('exercises.diagramTitlePlaceholder')}
                aria-label={t('exercises.diagramTitlePlaceholder')}
                className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-sm"
              />
              <div
                className="relative cursor-crosshair touch-none overflow-hidden rounded-md border border-border bg-subtle"
                onPointerDown={onDown}
                onPointerMove={onMove}
                onPointerUp={onUp}
              >
                <img
                  src={blobUrl(image.blob_sha ?? '')}
                  alt={image.title}
                  className="block w-full select-none"
                  draggable={false}
                />
                {regions.map((region, index) => (
                  <span
                    key={region.id}
                    className="border-primary/70 bg-primary/10 text-primary pointer-events-none absolute flex items-center justify-center rounded-sm border-2 text-[11px] font-semibold"
                    style={{
                      left: `${region.x * 100}%`,
                      top: `${region.y * 100}%`,
                      width: `${region.w * 100}%`,
                      height: `${region.h * 100}%`,
                    }}
                  >
                    {index + 1}
                  </span>
                ))}
                {preview !== null ? (
                  <span
                    className="border-primary bg-primary/20 pointer-events-none absolute rounded-sm border-2 border-dashed"
                    style={{
                      left: `${preview.x * 100}%`,
                      top: `${preview.y * 100}%`,
                      width: `${preview.w * 100}%`,
                      height: `${preview.h * 100}%`,
                    }}
                  />
                ) : null}
              </div>
              <p className="text-muted-foreground text-xs">{t('exercises.diagramDrawHint')}</p>
              <ul className="space-y-1.5">
                {regions.map((region, index) => (
                  <li key={region.id} className="flex items-center gap-2">
                    <span className="bg-subtle flex size-6 items-center justify-center rounded text-[11px]">
                      {index + 1}
                    </span>
                    <input
                      value={region.label}
                      onChange={(event) =>
                        setRegions((previous) =>
                          previous.map((entry) =>
                            entry.id === region.id
                              ? { ...entry, label: event.target.value }
                              : entry
                          )
                        )
                      }
                      aria-label={t('exercises.diagramRegionLabelInput', { n: index + 1 })}
                      className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1 text-xs"
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={t('exercises.diagramRemoveRegion', { n: index + 1 })}
                      onClick={() =>
                        setRegions((previous) =>
                          previous.filter((entry) => entry.id !== region.id)
                        )
                      }
                    >
                      <Trash2 className="size-3.5" aria-hidden />
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {save.isError ? (
            <p className="text-danger text-xs" role="alert">
              {(save.error as Error).message}
            </p>
          ) : null}
        </div>
        <footer className="border-border flex items-center justify-end gap-2 border-t px-4 py-2">
          {image !== null ? (
            <Button variant="ghost" size="sm" onClick={() => setImage(null)}>
              {t('exercises.diagramChangeImage')}
            </Button>
          ) : null}
          <Button
            size="sm"
            disabled={image === null || regions.length === 0 || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Spinner /> : null}
            {t('exercises.diagramSave')}
          </Button>
        </footer>
      </div>
    </div>
  )
}

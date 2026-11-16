import { ArrowDown, ArrowUp, FileText, RotateCw, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { blobUrl, type CaptureStaging } from '@/lib/api'

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(0)} KB`
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

export function ScanPages({
  items,
  busy,
  onAssemble,
  onDiscard,
}: {
  items: CaptureStaging[]
  busy: boolean
  onAssemble: (
    pages: Array<{ captureId: string; rotation: number }>,
    title: string
  ) => Promise<void>
  onDiscard: (captureId: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const ids = useMemo(() => items.map((item) => item.id), [items])
  const [order, setOrder] = useState<string[]>(ids)
  const [rotations, setRotations] = useState<Record<string, number>>({})
  const [title, setTitle] = useState('')

  useEffect(() => {
    setOrder((previous) => [
      ...previous.filter((id) => ids.includes(id)),
      ...ids.filter((id) => !previous.includes(id)),
    ])
  }, [ids])

  const byId = new Map(items.map((item) => [item.id, item]))
  const move = (index: number, delta: number) => {
    setOrder((previous) => {
      const next = [...previous]
      const target = index + delta
      if (target < 0 || target >= next.length) {
        return previous
      }
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  return (
    <section className="border-border bg-subtle/40 flex flex-col gap-2 rounded-md border p-2">
      <div className="flex items-center gap-2">
        <FileText className="text-primary size-4" aria-hidden />
        <p className="text-xs font-medium">{t('captureInbox.pagesTitle', { count: items.length })}</p>
        <span className="text-muted-foreground ml-auto text-[11px]">
          {t('captureInbox.pagesHint')}
        </span>
      </div>
      <ul className="flex flex-col gap-1.5">
        {order.map((id, index) => {
          const item = byId.get(id)
          if (item === undefined) {
            return null
          }
          const rotation = rotations[id] ?? 0
          return (
            <li
              key={id}
              className="border-border bg-surface flex items-center gap-2 rounded-md border p-1.5"
            >
              <span className="text-muted-foreground w-4 text-center text-[11px] tabular-nums">
                {index + 1}
              </span>
              <img
                src={blobUrl(item.blob_sha)}
                alt=""
                className="bg-subtle size-10 shrink-0 rounded object-cover"
                style={{ transform: `rotate(${rotation}deg)` }}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium">{item.filename}</p>
                <p className="text-muted-foreground text-[11px]">{formatBytes(item.byte_size)}</p>
              </div>
              <Button
                size="icon"
                variant="ghost"
                aria-label={t('captureInbox.moveUp')}
                disabled={busy || index === 0}
                onClick={() => move(index, -1)}
              >
                <ArrowUp className="size-3.5" aria-hidden />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                aria-label={t('captureInbox.moveDown')}
                disabled={busy || index === order.length - 1}
                onClick={() => move(index, 1)}
              >
                <ArrowDown className="size-3.5" aria-hidden />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                aria-label={t('captureInbox.rotate')}
                disabled={busy}
                onClick={() =>
                  setRotations((previous) => ({
                    ...previous,
                    [id]: (rotation + 90) % 360,
                  }))
                }
              >
                <RotateCw className="size-3.5" aria-hidden />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                aria-label={t('captureInbox.removePage')}
                disabled={busy}
                onClick={() => void onDiscard(id)}
              >
                <Trash2 className="size-3.5" aria-hidden />
              </Button>
            </li>
          )
        })}
      </ul>
      <div className="flex items-center gap-2">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder={t('captureInbox.scanTitle')}
          aria-label={t('captureInbox.scanTitle')}
          className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1 text-xs"
        />
        <Button
          size="sm"
          disabled={busy || order.length < 2}
          onClick={() =>
            void onAssemble(
              order.map((id) => ({ captureId: id, rotation: rotations[id] ?? 0 })),
              title
            )
          }
        >
          {t('captureInbox.combine', { count: order.length })}
        </Button>
      </div>
    </section>
  )
}

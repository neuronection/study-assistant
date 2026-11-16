import { Camera, Check, ExternalLink, RefreshCw, Trash2, WifiOff, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { blobUrl } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'
import type { CaptureInboxState } from './useCaptureInbox'
import { ScanPages } from './ScanPages'

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(0)} KB`
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

export function CaptureInboxDialog({
  state,
  courseId,
}: {
  state: CaptureInboxState
  courseId: string | null
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  if (!state.open) {
    return null
  }
  const staged = state.items.filter((item) => item.status === 'staged')
  const stagedImages = staged.filter((item) => item.mime?.startsWith('image/'))
  const scanMode = stagedImages.length > 1
  const scanIds = new Set(scanMode ? stagedImages.map((item) => item.id) : [])
  const visibleItems = state.items.filter((item) => !scanIds.has(item.id))
  const hasContent = state.queued.length > 0 || state.items.length > 0
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('captureInbox.inboxTitle')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          state.close()
        }
      }}
    >
      <div className="bg-surface border-border flex w-full max-w-lg flex-col rounded-lg border shadow-[var(--as-shadow-3)]">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Camera className="text-primary size-4" aria-hidden />
            {t('captureInbox.inboxTitle')}
          </h2>
          <button
            type="button"
            aria-label={t('chat.close')}
            onClick={state.close}
            className="text-muted-foreground hover:text-foreground rounded p-1"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>
        <div className="flex max-h-[60vh] flex-col gap-2 overflow-y-auto p-4">
          {!hasContent ? (
            <p className="text-muted-foreground text-sm">{t('captureInbox.inboxEmpty')}</p>
          ) : null}
          {scanMode ? (
            <ScanPages
              items={stagedImages}
              busy={state.busy}
              onAssemble={state.assemble}
              onDiscard={state.discard}
            />
          ) : null}
          {state.queued.length > 0 ? (
            <div className="border-warning/40 bg-warning/5 flex flex-col gap-2 rounded-md border p-2">
              <div className="flex items-center gap-2">
                <WifiOff className="text-warning size-4 shrink-0" aria-hidden />
                <p className="text-xs font-medium">
                  {t('captureInbox.queuedTitle', { count: state.queued.length })}
                </p>
                <span className="text-muted-foreground ml-auto text-[11px]">
                  {state.durable
                    ? t('captureInbox.queuedSaved')
                    : t('captureInbox.queuedSession')}
                </span>
              </div>
              {state.queued.map((op) => (
                <div
                  key={op.id}
                  className="border-border bg-surface flex items-center gap-3 rounded-md border p-2"
                >
                  <div className="bg-subtle text-muted-foreground flex size-10 shrink-0 items-center justify-center rounded">
                    <WifiOff className="size-4" aria-hidden />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{op.payload.filename}</p>
                    <p className="text-muted-foreground text-xs">
                      {formatBytes(op.payload.size)}
                      {op.failed
                        ? ` · ${op.lastError ?? t('captureInbox.queuedFailed')}`
                        : ` · ${t('captureInbox.queuedWaiting')}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={t('captureInbox.retry')}
                      disabled={state.busy}
                      onClick={() => void state.retryQueued(op.id)}
                    >
                      <RefreshCw className="size-4" aria-hidden />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={t('captureInbox.removeQueued')}
                      disabled={state.busy}
                      onClick={() => void state.removeQueued(op.id)}
                    >
                      <Trash2 className="size-4" aria-hidden />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {visibleItems.map((item) => (
            <div
              key={item.id}
              className="border-border flex items-center gap-3 rounded-md border p-2"
            >
              {item.mime?.startsWith('image/') ? (
                <img
                  src={blobUrl(item.blob_sha)}
                  alt=""
                  className="bg-subtle size-12 shrink-0 rounded object-cover"
                />
              ) : (
                <div className="bg-subtle text-muted-foreground flex size-12 shrink-0 items-center justify-center rounded">
                  <Camera className="size-5" aria-hidden />
                </div>
              )}
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{item.filename}</p>
                <p className="text-muted-foreground text-xs">
                  {formatBytes(item.byte_size)} ·{' '}
                  {t(`capture.status.${item.status}`, { defaultValue: item.status })}
                </p>
              </div>
              {item.status === 'staged' ? (
                <div className="flex items-center gap-1">
                  <Button
                    size="sm"
                    disabled={state.busy || courseId === null}
                    onClick={() => void state.commit(item.id)}
                  >
                    {t('captureInbox.add')}
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label={t('captureInbox.discard')}
                    disabled={state.busy}
                    onClick={() => void state.discard(item.id)}
                  >
                    <Trash2 className="size-4" aria-hidden />
                  </Button>
                </div>
              ) : null}
              {item.status === 'committed' && item.material_id !== null ? (
                <a
                  href={`/library/${item.material_id}`}
                  className="text-primary inline-flex items-center gap-1 text-xs underline"
                >
                  <Check className="size-3.5" aria-hidden />
                  {t('captureInbox.open')}
                  <ExternalLink className="size-3" aria-hidden />
                </a>
              ) : null}
            </div>
          ))}
          {state.error !== null ? (
            <p className="text-danger text-xs" role="alert">
              {state.error}
            </p>
          ) : null}
          {courseId === null ? (
            <p className="text-muted-foreground text-xs">{t('captureInbox.needCourse')}</p>
          ) : null}
        </div>
        <footer className="border-border flex items-center justify-end gap-2 border-t px-4 py-2">
          {scanMode ? (
            <ScanPages
              items={stagedImages}
              busy={state.busy}
              onAssemble={state.assemble}
              onDiscard={state.discard}
            />
          ) : null}
          {state.queued.length > 0 ? (
            <Button
              variant="outline"
              size="sm"
              disabled={state.busy}
              onClick={() => void state.retryAllQueued()}
            >
              <RefreshCw className="size-3.5" aria-hidden />
              {t('captureInbox.retryAll')}
            </Button>
          ) : null}
          {staged.length > 1 ? (
            <Button
              variant="outline"
              size="sm"
              disabled={state.busy || courseId === null}
              onClick={() => {
                for (const item of staged) {
                  void state.commit(item.id)
                }
              }}
            >
              {t('captureInbox.addAll', { count: staged.length })}
            </Button>
          ) : null}
          <Button size="sm" onClick={state.close}>
            {t('captureInbox.close')}
          </Button>
        </footer>
      </div>
    </div>
  )
}

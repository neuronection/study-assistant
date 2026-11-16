import { useQueryClient } from '@tanstack/react-query'
import { CloudOff, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { isReviewOp, offlineJournal } from '@/lib/offline/journal'
import { drainReviewQueue } from '@/lib/review-submit'

export function useReviewSync(): {
  queued: number
  busy: boolean
  sync: () => Promise<void>
} {
  const queryClient = useQueryClient()
  const snapshot = useSyncExternalStore(
    offlineJournal.subscribe,
    offlineJournal.getSnapshot,
    offlineJournal.getSnapshot
  )
  const [busy, setBusy] = useState(false)
  const queued = snapshot.ops.filter(isReviewOp).length

  const sync = useCallback(async () => {
    setBusy(true)
    try {
      const completed = await drainReviewQueue()
      if (completed > 0) {
        await queryClient.invalidateQueries({ queryKey: ['review-due'] })
        await queryClient.invalidateQueries({ queryKey: ['cards-due'] })
        await queryClient.invalidateQueries({ queryKey: ['cards'] })
      }
    } finally {
      setBusy(false)
    }
  }, [queryClient])

  useEffect(() => {
    const onOnline = () => {
      void sync()
    }
    window.addEventListener('online', onOnline)
    if (navigator.onLine && queued > 0) {
      void sync()
    }
    return () => window.removeEventListener('online', onOnline)
  }, [queued, sync])

  return { queued, busy, sync }
}

export function PendingSyncNotice({
  count,
  busy,
  onSync,
}: {
  count: number
  busy: boolean
  onSync: () => void
}) {
  const { t } = useTranslation()
  if (count === 0) {
    return null
  }
  return (
    <div
      role="status"
      className="border-warning/40 bg-surface fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] left-4 z-30 flex max-w-[calc(100vw-2rem)] items-center gap-2 rounded-full border px-3 py-1.5 text-xs shadow-[var(--as-shadow-2)] md:bottom-4"
    >
      <CloudOff className="text-warning size-4 shrink-0" aria-hidden />
      <span className="truncate">{t('review.queuedRatings', { count })}</span>
      <Button size="sm" variant="ghost" disabled={busy} onClick={onSync}>
        <RefreshCw className={`size-3.5 ${busy ? 'animate-spin' : ''}`} aria-hidden />
        {t('review.syncNow')}
      </Button>
    </div>
  )
}

export function ReviewSyncNotice() {
  const { queued, busy, sync } = useReviewSync()
  return <PendingSyncNotice count={queued} busy={busy} onSync={() => void sync()} />
}

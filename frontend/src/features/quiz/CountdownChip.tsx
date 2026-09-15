import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TimerReset } from 'lucide-react'

import { cn } from '@/lib/utils'

function formatRemaining(totalSec: number): string {
  const minutes = Math.floor(totalSec / 60)
  const seconds = totalSec % 60
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60)
    return `${hours}:${String(minutes % 60).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

/**
 * Server-deadline countdown: renders remaining time from
 * `deadline_at − server_now`, ticked locally. `offsetMs` is the
 * client-vs-server clock offset captured at attempt start
 * (`Date.parse(started_at) − Date.now()`), so a skewed client clock
 * cannot extend the run.
 */
export function CountdownChip({
  deadlineIso,
  offsetMs = 0,
  onExpire,
}: {
  deadlineIso: string
  offsetMs?: number
  onExpire?: () => void
}) {
  const { t } = useTranslation()
  const deadlineMs = Date.parse(deadlineIso)
  const [remainingSec, setRemainingSec] = useState(() =>
    Math.max(0, Math.round((deadlineMs - (Date.now() + offsetMs)) / 1000))
  )
  const expiredRef = useRef(false)

  useEffect(() => {
    const compute = () => {
      const next = Math.max(0, Math.round((deadlineMs - (Date.now() + offsetMs)) / 1000))
      if (next === 0 && !expiredRef.current) {
        expiredRef.current = true
        onExpire?.()
      }
      setRemainingSec(next)
    }
    compute()
    const interval = window.setInterval(compute, 1000)
    return () => window.clearInterval(interval)
  }, [deadlineMs, offsetMs, onExpire])

  const low = remainingSec <= 60
  const expired = remainingSec === 0

  return (
    <span
      role="timer"
      aria-label={t('quiz.timeRemaining')}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold tabular-nums transition-colors',
        expired
          ? 'border-danger/40 bg-danger/10 text-danger'
          : low
            ? 'border-warning/40 bg-warning/10 text-warning'
            : 'border-border bg-surface text-foreground'
      )}
    >
      <TimerReset className={cn('size-3.5', expired && 'text-danger')} aria-hidden />
      {expired ? t('quiz.timeUp') : formatRemaining(remainingSec)}
    </span>
  )
}

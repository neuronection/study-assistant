import { Loader2, Mic, Square, X } from 'lucide-react'
import { useEffect, useRef, type RefObject } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

import type { DictationError, DictationStatus } from './useDictation'

const BAR_WEIGHTS = [0.45, 0.62, 0.8, 0.92, 1.05]

export function DictationMicButton({
  status,
  onStart,
  label,
  className,
}: {
  status: DictationStatus
  onStart: () => void
  label: string
  className?: string
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={status === 'recording'}
      disabled={status === 'transcribing'}
      className={cn(
        'rounded p-1.5 transition-colors',
        status === 'recording'
          ? 'bg-danger/10 animate-pulse text-danger'
          : 'text-muted-foreground hover:text-foreground',
        className,
      )}
      onClick={onStart}
    >
      <Mic className="size-4" aria-hidden />
    </button>
  )
}

function LevelBars({
  levelRef,
  active,
}: {
  levelRef: RefObject<number>
  active: boolean
}) {
  const barsRef = useRef<Array<HTMLSpanElement | null>>([])
  useEffect(() => {
    if (!active) {
      return
    }
    let frame = requestAnimationFrame(function tick() {
      const level = Math.min(1, levelRef.current ?? 0)
      barsRef.current.forEach((bar, index) => {
        if (bar) {
          const height = Math.max(0.15, Math.min(1, level * BAR_WEIGHTS[index]))
          bar.style.transform = `scaleY(${height})`
        }
      })
      frame = requestAnimationFrame(tick)
    })
    return () => cancelAnimationFrame(frame)
  }, [active, levelRef])
  return (
    <span className="flex h-4 items-end gap-0.5" aria-hidden>
      {BAR_WEIGHTS.map((_, index) => (
        <span
          key={index}
          ref={(element) => {
            barsRef.current[index] = element
          }}
          className="bg-danger h-4 w-1 origin-bottom rounded-full opacity-40"
        />
      ))}
    </span>
  )
}

function errorMessage(
  error: DictationError,
  t: ReturnType<typeof useTranslation>['t'],
) {
  if (error.kind === 'unsupported') {
    return t('dictation.unsupported')
  }
  if (error.kind === 'denied') {
    return t('dictation.denied')
  }
  if (error.kind === 'unassigned') {
    return t('dictation.unassigned')
  }
  return t('dictation.failedHint', { detail: error.detail ?? '' })
}

export function DictationStrip({
  status,
  seconds,
  levelRef,
  error,
  stopLabel,
  cancelLabel,
  onStop,
  onCancel,
  onDismissError,
  className,
}: {
  status: DictationStatus
  seconds: number
  levelRef: RefObject<number>
  error: DictationError | null
  stopLabel: string
  cancelLabel: string
  onStop: () => void
  onCancel: () => void
  onDismissError: () => void
  className?: string
}) {
  const { t } = useTranslation()
  if (error !== null) {
    return (
      <div
        className={cn(
          'bg-surface border-warning text-warning flex items-center gap-2 rounded-md border border-dashed px-2.5 py-1.5 text-xs',
          className,
        )}
        role="alert"
      >
        <span className="min-w-0 flex-1 break-words">{errorMessage(error, t)}</span>
        <button
          type="button"
          aria-label={t('dictation.dismissError')}
          title={t('dictation.dismissError')}
          className="rounded-full p-0.5 hover:opacity-70"
          onClick={onDismissError}
        >
          <X className="size-3.5" aria-hidden />
        </button>
      </div>
    )
  }
  if (status === 'idle') {
    return null
  }
  const formatTime = (total: number) => {
    const minutes = Math.floor(total / 60)
    const padded = String(total % 60).padStart(2, '0')
    return `${String(minutes).padStart(2, '0')}:${padded}`
  }
  return (
    <div
      className={cn(
        'bg-surface border-border flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs',
        className,
      )}
      role="status"
      aria-label={t('dictation.recording')}
    >
      {status === 'recording' ? (
        <>
          <span className="bg-danger size-2 shrink-0 animate-pulse rounded-full" aria-hidden />
          <span className="text-foreground font-medium tabular-nums">
            {formatTime(seconds)}
          </span>
          <LevelBars levelRef={levelRef} active />
          <span className="text-muted-foreground min-w-0 flex-1 truncate">
            {t('dictation.recording')}
          </span>
          <button
            type="button"
            aria-label={cancelLabel}
            title={cancelLabel}
            className="text-muted-foreground hover:text-foreground rounded p-1"
            onClick={onCancel}
          >
            <X className="size-3.5" aria-hidden />
          </button>
          <button
            type="button"
            title={stopLabel}
            aria-label={stopLabel}
            className="bg-danger flex items-center gap-1 rounded px-2 py-1 font-medium text-white"
            onClick={onStop}
          >
            <Square className="size-3" aria-hidden />
            {stopLabel}
          </button>
        </>
      ) : (
        <>
          <Loader2 className="text-muted-foreground size-3.5 shrink-0 animate-spin" aria-hidden />
          <span className="text-muted-foreground min-w-0 flex-1">
            {t('dictation.transcribing')}
          </span>
        </>
      )}
    </div>
  )
}

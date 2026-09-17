import { AnimatePresence, motion } from 'framer-motion'
import { useMotionPresets } from '@/lib/motion'
import { Check, Coffee, Pause, Play, Sparkles, Square, Timer } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import {
  FOCUS_PRESETS,
  formatFocusRemaining,
  useFocusTimerStore,
  type FocusPreset,
} from '@/lib/focus-timer-store'
import { cn } from '@/lib/utils'

function useRouteStudyContext(): { courseId: number | null; nodeId: number | null } {
  const pathname = useLocation({ select: (location) => location.pathname })
  const match = pathname.match(/^\/courses\/(\d+)(?:\/n\/(\d+))?/)
  if (match === null) {
    return { courseId: null, nodeId: null }
  }
  return {
    courseId: Number(match[1]),
    nodeId: match[2] === undefined ? null : Number(match[2]),
  }
}

function ProgressRing({
  progress,
  phase,
  children,
}: {
  progress: number
  phase: 'focus' | 'paused' | 'break' | 'done'
  children: ReactNode
}) {
  const color =
    phase === 'break'
      ? 'var(--color-success, var(--success, #22c55e))'
      : phase === 'paused'
        ? 'var(--color-warning, var(--warning, #f59e0b))'
        : 'var(--primary)'
  return (
    <div className="relative flex size-11 items-center justify-center">
      <svg viewBox="0 0 40 40" className="absolute inset-0 size-full -rotate-90" aria-hidden>
        <circle cx="20" cy="20" r="17" fill="none" stroke="var(--border)" strokeWidth="3" />
        <motion.circle
          cx="20"
          cy="20"
          r="17"
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={2 * Math.PI * 17}
          animate={{ strokeDashoffset: 2 * Math.PI * 17 * (1 - progress) }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
        />
      </svg>
      <motion.span
        key={String(phase)}
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className={cn(
          'relative flex items-center justify-center',
          phase === 'focus' && 'text-primary',
          phase === 'break' && 'text-success',
          phase === 'paused' && 'text-warning'
        )}
      >
        {children}
      </motion.span>
    </div>
  )
}

export function FocusTimer() {
  const { t } = useTranslation()
  const presets = useMotionPresets()
  const context = useRouteStudyContext()
  const phase = useFocusTimerStore((state) => state.phase)
  const remainingSec = useFocusTimerStore((state) => state.remainingSec)
  const focusMin = useFocusTimerStore((state) => state.focusMin)
  const breakMin = useFocusTimerStore((state) => state.breakMin)
  const start = useFocusTimerStore((state) => state.start)
  const startCustom = useFocusTimerStore((state) => state.startCustom)
  const pause = useFocusTimerStore((state) => state.pause)
  const resume = useFocusTimerStore((state) => state.resume)
  const giveUp = useFocusTimerStore((state) => state.giveUp)
  const tick = useFocusTimerStore((state) => state.tick)
  const beginBreak = useFocusTimerStore((state) => state.beginBreak)
  const dismiss = useFocusTimerStore((state) => state.dismiss)
  const [expanded, setExpanded] = useState(false)
  const [customFocus, setCustomFocus] = useState(35)
  const [customBreak, setCustomBreak] = useState(7)
  const panelRef = useRef<HTMLDivElement>(null)

  const active = phase !== 'idle'
  useEffect(() => {
    if (phase !== 'focus' && phase !== 'break') {
      return
    }
    const interval = window.setInterval(() => tick(), 1000)
    return () => window.clearInterval(interval)
  }, [phase, tick])

  useEffect(() => {
    if (!expanded) {
      return
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setExpanded(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [expanded])

  const totalSec =
    phase === 'break' ? Math.max(60, breakMin * 60) : Math.max(60, focusMin * 60)
  const progress =
    active && totalSec > 0
      ? Math.min(1, Math.max(0, 1 - remainingSec / totalSec))
      : 0

  const launch = (preset: FocusPreset) => {
    start(preset, context)
    setExpanded(false)
  }

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-40 flex flex-col items-end gap-2 print:hidden">
      <AnimatePresence>
        {expanded ? (
          <motion.div
            ref={panelRef}
            {...presets.panel}
            className={cn(
              'border-border bg-surface pointer-events-auto w-64 rounded-xl border p-3 shadow-[var(--as-shadow-3)]'
            )}
            role="dialog"
            aria-label={t('focusTimer.pickerLabel')}
          >
            <p className="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs font-medium">
              <Sparkles className="text-primary size-3.5" aria-hidden />
              {t('focusTimer.pickPreset')}
            </p>
            <div className="grid grid-cols-2 gap-2">
              {FOCUS_PRESETS.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  className="border-border hover:border-primary/50 hover:bg-subtle rounded-lg border px-2 py-2.5 text-center transition-colors"
                  onClick={() => launch(preset)}
                >
                  <span className="text-foreground block text-sm font-semibold">
                    {preset.focusMin}
                  </span>
                  <span className="text-muted-foreground block text-[10px]">
                    {t('focusTimer.presetPair', {
                      focus: preset.focusMin,
                      brk: preset.breakMin,
                    })}
                  </span>
                </button>
              ))}
            </div>
            <div className="border-border mt-2 border-t pt-2">
              <p className="text-muted-foreground mb-1.5 text-[11px] font-medium">
                {t('focusTimer.custom')}
              </p>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  min={1}
                  max={180}
                  value={customFocus}
                  onChange={(event) =>
                    setCustomFocus(Math.min(180, Math.max(1, Number(event.target.value) || 1)))
                  }
                  aria-label={t('focusTimer.customFocus')}
                  className="border-border bg-surface w-14 rounded-md border px-1.5 py-1 text-center text-xs"
                />
                <span className="text-muted-foreground text-xs">/</span>
                <input
                  type="number"
                  min={1}
                  max={60}
                  value={customBreak}
                  onChange={(event) =>
                    setCustomBreak(Math.min(60, Math.max(1, Number(event.target.value) || 1)))
                  }
                  aria-label={t('focusTimer.customBreak')}
                  className="border-border bg-surface w-14 rounded-md border px-1.5 py-1 text-center text-xs"
                />
                <Button
                  size="sm"
                  className="ml-auto"
                  onClick={() => {
                    startCustom(customFocus, customBreak, context)
                    setExpanded(false)
                  }}
                >
                  {t('focusTimer.start')}
                </Button>
              </div>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {phase === 'idle' ? (
          <motion.button
            key="idle"
            {...presets.enter}
            type="button"
            className={cn(
              'border-border bg-surface text-muted-foreground hover:text-foreground hover:border-primary/40 pointer-events-auto flex items-center gap-2 rounded-full border px-3.5 py-2 text-xs font-medium shadow-[var(--as-shadow-2)] transition-colors'
            )}
            aria-expanded={expanded}
            aria-label={t('focusTimer.open')}
            onClick={() => setExpanded((value) => !value)}
          >
            <Timer className="size-4" aria-hidden />
            {t('focusTimer.focus')}
          </motion.button>
        ) : phase === 'done' ? (
          <motion.div
            key="done"
            {...presets.panel}
            className="border-success/40 bg-surface pointer-events-auto flex items-center gap-2.5 rounded-full border py-1.5 pl-3 pr-1.5 shadow-[var(--as-shadow-2)]"
            role="status"
          >
            <span className="text-success flex items-center gap-1.5 text-xs font-semibold">
              <Check className="size-4" aria-hidden />
              {t('focusTimer.focusDone', { minutes: focusMin })}
            </span>
            <Button size="sm" className="rounded-full" onClick={() => beginBreak()}>
              <Coffee aria-hidden />
              {t('focusTimer.takeBreak', { minutes: breakMin })}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="rounded-full"
              aria-label={t('focusTimer.dismiss')}
              onClick={() => dismiss()}
            >
              <Square className="size-3.5" aria-hidden />
            </Button>
          </motion.div>
        ) : (
          <motion.div
            key="running"
            {...presets.enter}
            className="border-border bg-surface pointer-events-auto flex items-center gap-2 rounded-full border py-1.5 pl-1.5 pr-2 shadow-[var(--as-shadow-2)]"
          >
            <button
              type="button"
              className="shrink-0"
              aria-label={
                phase === 'paused'
                  ? t('focusTimer.details')
                  : phase === 'break'
                    ? t('focusTimer.breakRunning')
                    : t('focusTimer.running')
              }
              onClick={() => setExpanded((value) => !value)}
            >
              <ProgressRing progress={progress} phase={phase === 'break' ? 'break' : phase === 'paused' ? 'paused' : 'focus'}>
                {phase === 'break' ? (
                  <Coffee className="size-4" aria-hidden />
                ) : phase === 'paused' ? (
                  <Pause className="size-4" aria-hidden />
                ) : (
                  <motion.span
                    className="bg-primary size-2 rounded-full"
                    animate={presets.reduced ? undefined : { opacity: [1, 0.35, 1] }}
                    transition={
                      presets.reduced
                        ? undefined
                        : { duration: 2, repeat: Infinity, ease: 'easeInOut' }
                    }
                  />
                )}
              </ProgressRing>
            </button>
            <div className="mr-1 leading-tight">
              <p className="text-foreground text-sm font-semibold tabular-nums" role="timer">
                {formatFocusRemaining(remainingSec)}
              </p>
              <p className="text-muted-foreground text-[10px]">
                {phase === 'break'
                  ? t('focusTimer.breakOf', { minutes: breakMin })
                  : phase === 'paused'
                    ? t('focusTimer.pausedLabel')
                    : t('focusTimer.presetPair', { focus: focusMin, brk: breakMin })}
              </p>
            </div>
            {phase === 'paused' ? (
              <Button
                size="icon"
                className="rounded-full"
                aria-label={t('focusTimer.resume')}
                onClick={() => resume()}
              >
                <Play className="size-4" aria-hidden />
              </Button>
            ) : phase === 'focus' ? (
              <Button
                size="icon"
                variant="outline"
                className="rounded-full"
                aria-label={t('focusTimer.pause')}
                onClick={() => pause()}
              >
                <Pause className="size-4" aria-hidden />
              </Button>
            ) : null}
            <Button
              size="icon"
              variant="ghost"
              className="rounded-full"
              aria-label={t('focusTimer.giveUp')}
              title={t('focusTimer.giveUp')}
              onClick={() => giveUp()}
            >
              <Square className="size-3.5" aria-hidden />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

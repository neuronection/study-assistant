import { AnimatePresence, motion } from 'framer-motion'
import { Brain, ChevronDown, Timer } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { formatDuration } from '@/features/chat/tools/registry'
import type { ChatToolCall, ChatTrace } from '@/lib/api'
import { cn } from '@/lib/utils'

type TimelineItem =
  | { kind: 'round'; phase: string; start_ms: number; duration_ms: number }
  | {
      kind: 'tool'
      name: string
      argument: string
      start_ms: number
      duration_ms: number
    }

function TimelineRow({ item, totalMs }: { item: TimelineItem; totalMs: number }) {
  const { t } = useTranslation()
  const width = Math.max(2, Math.min(100, (item.duration_ms / totalMs) * 100))
  const label =
    item.kind === 'round'
      ? t(item.phase === 'repairing' ? 'chat.trace.roundRepair' : 'chat.trace.roundThinking')
      : item.name
  const detail = item.kind === 'tool' ? item.argument : null
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span
        className="text-muted-foreground w-16 shrink-0 truncate"
        title={detail ?? undefined}
      >
        {label}
      </span>
      <div className="bg-subtle h-1.5 min-w-0 flex-1 overflow-hidden rounded-full">
        <div
          className={cn(
            'h-full rounded-full',
            item.kind === 'round' ? 'bg-primary' : 'bg-warning',
          )}
          style={{ width: `${width}%` }}
        />
      </div>
      <span className="text-muted-foreground w-12 shrink-0 text-right font-mono text-[10px]">
        {formatDuration(item.duration_ms)}
      </span>
    </div>
  )
}

function ReasoningDisclosure({ thinking }: { thinking: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <div className="border-border/60 bg-surface/40 rounded-md border">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="text-muted-foreground hover:text-foreground flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-[11px] transition-colors"
      >
        <Brain className="size-3.5 shrink-0" aria-hidden />
        <span className="flex-1 text-left">{t('chat.trace.reasoning')}</span>
        <ChevronDown
          className={cn(
            'size-3.5 shrink-0 transition-transform duration-150',
            open && 'rotate-180',
          )}
          aria-hidden
        />
      </button>
      {open ? (
        <p className="text-muted-foreground px-2.5 pb-2 text-[11px] whitespace-pre-wrap">
          {thinking}
        </p>
      ) : null}
    </div>
  )
}

export function TraceTimeline({
  trace,
  toolCalls,
}: {
  trace: ChatTrace
  toolCalls: ChatToolCall[]
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const totalMs = Math.max(1, trace.latency_ms)
  const duration = formatDuration(trace.latency_ms)
  const items: TimelineItem[] = [
    ...trace.rounds.map((round) => ({
      kind: 'round' as const,
      phase: round.phase,
      start_ms: round.start_ms,
      duration_ms: round.duration_ms,
    })),
    ...toolCalls
      .filter((tool) => tool.start_ms !== null && tool.start_ms !== undefined)
      .map((tool) => ({
        kind: 'tool' as const,
        name: tool.name,
        argument: tool.argument,
        start_ms: tool.start_ms ?? 0,
        duration_ms: tool.duration_ms ?? 0,
      })),
  ].sort((a, b) => a.start_ms - b.start_ms)

  return (
    <div className="mt-1 w-full max-w-[92%]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={t('chat.trace.toggle')}
        className="text-muted-foreground hover:text-foreground flex items-center gap-1.5 text-[11px] transition-colors"
      >
        <Timer className="size-3.5 shrink-0" aria-hidden />
        <span>
          {t('chat.trace.summary', { duration: duration ?? '0 ms', count: toolCalls.length })}
        </span>
        {trace.model ? (
          <span className="font-mono text-[10px]">· {trace.model}</span>
        ) : null}
        <ChevronDown
          className={cn(
            'size-3.5 shrink-0 transition-transform duration-150',
            open && 'rotate-180',
          )}
          aria-hidden
        />
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="mt-2 space-y-1.5">
              <div className="text-muted-foreground flex items-center justify-between text-[11px]">
                <span>{t('chat.trace.total', { duration: duration ?? '0 ms' })}</span>
                <span>
                  {t('chat.trace.tokens', { count: trace.output_tokens ?? 0 })}
                </span>
              </div>
              {items.map((item, index) => (
                <TimelineRow key={`${item.kind}-${index}`} item={item} totalMs={totalMs} />
              ))}
              {trace.thinking ? <ReasoningDisclosure thinking={trace.thinking} /> : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}

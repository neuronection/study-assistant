import { useTranslation } from 'react-i18next'

import {
  ChatTraceTimeline,
  type ChatTraceTimelineEntry,
} from '@/components/ui/chat-trace-timeline'
import type { ChatToolCall, ChatTrace } from '@/lib/api'

/**
 * Per-turn response trace on the shared library `ChatTraceTimeline`:
 * study maps its persisted `trace` + `tool_calls` rows onto the
 * library's trace/entries view model (phase labels translated here).
 */
export function TraceTimeline({
  trace,
  toolCalls,
}: {
  trace: ChatTrace
  toolCalls: ChatToolCall[]
}) {
  const { t } = useTranslation()
  const entries: ChatTraceTimelineEntry[] = [
    ...trace.rounds.map((round) => ({
      kind: 'phase' as const,
      label: t(round.phase === 'repairing' ? 'chat.trace.roundRepair' : 'chat.trace.roundThinking'),
      startMs: round.start_ms,
      durationMs: round.duration_ms,
    })),
    ...toolCalls
      .filter((tool) => tool.start_ms !== null && tool.start_ms !== undefined)
      .map((tool) => ({
        kind: 'tool' as const,
        label: tool.name,
        detail: tool.argument,
        startMs: tool.start_ms ?? null,
        durationMs: tool.duration_ms ?? null,
      })),
  ]
  return (
    <div className="mt-1 w-full max-w-[92%]">
      <ChatTraceTimeline
        trace={{
          model: trace.model,
          latencyMs: trace.latency_ms,
          outputTokens: trace.output_tokens,
          thinking: trace.thinking ?? null,
        }}
        entries={entries}
        labels={{
          toggle: t('chat.trace.toggle'),
          tools: 'tools',
          total: 'Total',
          tokens: 'tokens',
          reasoning: t('chat.trace.reasoning'),
        }}
      />
    </div>
  )
}

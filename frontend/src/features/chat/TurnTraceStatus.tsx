import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { formatDuration } from '@/features/chat/tools/registry'

const TICK_MS = 100

export function TurnTraceStatus({
  phase,
  startedAt,
}: {
  phase: string
  startedAt: number
}) {
  const { t } = useTranslation()
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), TICK_MS)
    return () => window.clearInterval(id)
  }, [])

  const label = `${t(`chat.phase.${phase}`)}…`
  const elapsed = Math.max(0, now - startedAt)

  return (
    <div
      role="status"
      aria-label={label}
      className="text-muted-foreground flex items-center gap-2 px-1 py-0.5"
    >
      <span className="flex items-center gap-1" aria-hidden>
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="chat-dot bg-muted-foreground size-1.5 rounded-full"
            style={{ animationDelay: `${index * 0.16}s` }}
          />
        ))}
      </span>
      <span className="text-xs">{label}</span>
      <span className="font-mono text-[10px] tabular-nums">{formatDuration(elapsed)}</span>
    </div>
  )
}

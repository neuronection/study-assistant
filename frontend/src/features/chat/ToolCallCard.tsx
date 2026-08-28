import { AnimatePresence, motion } from 'framer-motion'
import { Check, ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { formatDuration, getToolMeta, getToolView } from '@/features/chat/tools/registry'
import type { ChatToolCall } from '@/lib/api'
import { cn } from '@/lib/utils'

export function ToolCallCard({ tool }: { tool: ChatToolCall }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const meta = getToolMeta(tool.name)
  const Icon = meta.icon
  const label = meta.labelKey ? t(meta.labelKey) : tool.name
  const summary = tool.title ?? tool.argument
  const duration = formatDuration(tool.duration_ms)
  const ResultView = getToolView(tool.name)
  const showResult =
    (tool.result !== null && tool.result !== undefined) || tool.name === 'STATE'

  return (
    <div className="border-border/70 bg-surface/60 w-full rounded-lg border">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={t('chat.tool.toggle', { label })}
        className="hover:bg-subtle flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors"
      >
        <Icon className="text-primary size-3.5 shrink-0" aria-hidden />
        <span className="text-foreground font-mono text-[11px] font-semibold">
          {tool.name}
        </span>
        <span className="text-muted-foreground min-w-0 flex-1 truncate font-mono text-[11px]">
          {summary}
        </span>
        {duration ? (
          <span className="text-muted-foreground shrink-0 font-mono text-[10px]">
            {duration}
          </span>
        ) : null}
        {tool.status === 'done' ? (
          <Check className="text-success size-3.5 shrink-0" aria-hidden />
        ) : null}
        <ChevronDown
          className={cn(
            'text-muted-foreground size-3.5 shrink-0 transition-transform duration-150',
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
            <div className="space-y-2 px-2.5 pb-2.5">
              <div>
                <h4 className="text-muted-foreground mb-1 text-[10px] font-semibold uppercase tracking-wide">
                  {t('chat.tool.argument')}
                </h4>
                <pre className="bg-subtle border-border overflow-x-auto rounded-md border p-2 font-mono text-[11px] whitespace-pre-wrap break-all">
                  {tool.argument}
                </pre>
              </div>
              {showResult ? (
                <div>
                  <h4 className="text-muted-foreground mb-1 text-[10px] font-semibold uppercase tracking-wide">
                    {t('chat.tool.result')}
                  </h4>
                  <ResultView tool={tool} />
                </div>
              ) : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}

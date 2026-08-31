import { AnimatePresence, motion } from 'framer-motion'
import { Brain, ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import { storageKeys } from '@/lib/constants'

const REASONING_OPEN_KEY = storageKeys.chatReasoningOpen

function readPref(): boolean {
  try {
    return window.localStorage.getItem(REASONING_OPEN_KEY) !== '0'
  } catch {
    return true
  }
}

export function ReasoningBubble({ text }: { text: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(readPref)

  const toggle = () => {
    setOpen((value) => {
      const next = !value
      try {
        window.localStorage.setItem(REASONING_OPEN_KEY, next ? '1' : '0')
      } catch {
        // persistence is best-effort
      }
      return next
    })
  }

  return (
    <div className="flex w-full max-w-[92%] flex-col items-start">
      <div className="border-border/70 bg-surface/50 w-full rounded-lg border">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          aria-label={t('chat.reasoningToggle')}
          className="text-muted-foreground hover:text-foreground flex w-full items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors"
        >
          <Brain className="size-3.5 shrink-0" aria-hidden />
          <span className="flex-1">{t('chat.reasoning')}…</span>
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
              <p className="text-muted-foreground px-2.5 pb-2 text-[11px] leading-relaxed whitespace-pre-wrap">
                {text}
              </p>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  )
}

import { Quote, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import type { SelectionCapture } from '@/lib/useTextSelection'

export function SelectionToolbar({
  capture,
  onAsk,
  onQuote,
}: {
  capture: SelectionCapture
  onAsk: () => void
  onQuote?: () => void
}) {
  const { t } = useTranslation()
  return (
    <div
      role="toolbar"
      aria-label={t('library.selectionToolbar')}
      className="bg-surface border-border text-foreground animate-in fade-in fixed z-[60] flex items-center gap-0.5 rounded-md border p-0.5 shadow-lg duration-150 motion-reduce:animate-none"
      style={{ top: capture.top, left: capture.left }}
    >
      <button
        type="button"
        className="hover:bg-subtle flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors"
        onClick={onAsk}
      >
        <Sparkles className="size-3.5" aria-hidden />
        {t('library.askSelection')}
      </button>
      {onQuote !== undefined ? (
        <button
          type="button"
          className="hover:bg-subtle flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors"
          onClick={onQuote}
        >
          <Quote className="size-3.5" aria-hidden />
          {t('study.quoteIntoNote')}
        </button>
      ) : null}
    </div>
  )
}

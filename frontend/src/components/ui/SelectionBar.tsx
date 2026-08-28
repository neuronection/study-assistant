import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { X } from 'lucide-react'

export function SelectionBar({
  count,
  onClear,
  children,
}: {
  count: number
  onClear: () => void
  children?: ReactNode
}) {
  const { t } = useTranslation()
  if (count === 0) {
    return null
  }
  return (
    <div className="bg-primary/10 border-primary/30 flex flex-wrap items-center gap-2 rounded-md border px-3 py-1.5 text-sm">
      <span className="text-primary font-medium">
        {t('selection.count', { count })}
      </span>
      {children}
      <button
        type="button"
        className="text-muted-foreground hover:text-foreground ml-auto rounded-md p-1"
        aria-label={t('selection.clear')}
        onClick={onClear}
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  )
}

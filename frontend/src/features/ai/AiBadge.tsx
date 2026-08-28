import { Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export function AiBadge({ className }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <span
      className={cn(
        'border-border bg-subtle text-muted-foreground inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
        className,
      )}
      title={t('ai.badge.aiGenerated')}
    >
      <Sparkles className="size-3" aria-hidden />
      {t('ai.badge.label')}
    </span>
  )
}

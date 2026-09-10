import { Link2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export function LinkRefBadge({
  count,
  className,
}: {
  count: number | undefined
  className?: string
}) {
  const { t } = useTranslation()
  if (!count || count <= 0) {
    return null
  }
  return (
    <span
      className={cn(
        'bg-subtle text-muted-foreground hover:text-foreground inline-flex shrink-0 items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[10px]',
        className
      )}
      title={t('library.placements', { count })}
    >
      <Link2 className="size-3" aria-hidden />
      {count}
    </span>
  )
}

import { Info } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Popover } from '@/components/ui/popover'

import { cn } from '@/lib/utils'

export function InfoButton({
  title,
  children,
  showOnHover = true,
  openOnHover = true,
}: {
  title?: ReactNode
  children: ReactNode
  showOnHover?: boolean
  openOnHover?: boolean
}) {
  const { t } = useTranslation()
  return (
    <span
      className={cn(
        'shrink-0',
        showOnHover &&
          'opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100'
      )}
      onMouseDown={(event) => event.stopPropagation()}
      onClick={(event) => event.stopPropagation()}
      onDoubleClick={(event) => event.stopPropagation()}
    >
      <Popover
        trigger={<Info className="size-4" aria-hidden />}
        label={t('common.info')}
        triggerClassName="text-muted-foreground hover:text-foreground size-6"
        openOnHover={openOnHover}
      >
        <div className="max-w-xs space-y-1.5">
          {title ? <p className="text-sm font-medium">{title}</p> : null}
          <div className="text-muted-foreground text-xs">{children}</div>
        </div>
      </Popover>
    </span>
  )
}
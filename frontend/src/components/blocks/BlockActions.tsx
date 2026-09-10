import { MoreHorizontal } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { PopoverMenu } from '@/components/ui/popover-menu'
import { cn } from '@/lib/utils'
import { blockActionItems } from './blockCopy'
import type { Block } from './types'

export function BlockActions({ block, className }: { block: Block; className?: string }) {
  const { t } = useTranslation()
  const items = blockActionItems(block, t)
  if (items === null) {
    return null
  }
  return (
    <PopoverMenu
      label={t('blocks.copyMenu')}
      trigger={<MoreHorizontal aria-hidden />}
      align="end"
      panelClassName="w-44"
      triggerClassName={cn(
        'bg-surface absolute top-1.5 z-10 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100',
        className ?? 'right-1.5'
      )}
      items={items}
    />
  )
}

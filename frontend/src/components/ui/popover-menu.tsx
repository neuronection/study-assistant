import { Loader2, type LucideIcon } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { Popover } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

export interface PopoverMenuItem {
  key: string
  label: string
  icon?: LucideIcon
  danger?: boolean
  disabled?: boolean
  pending?: boolean
  onSelect: () => void
}

export function menuItemClassName(danger: boolean): string {
  return cn(
    'hover:bg-subtle flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm',
    danger && 'text-danger'
  )
}

export function PopoverMenu({
  label,
  trigger,
  triggerClassName,
  panelClassName,
  items,
}: {
  label: string
  trigger: ReactNode
  triggerClassName?: string
  panelClassName?: string
  items: PopoverMenuItem[]
}) {
  const [closeSignal, setCloseSignal] = useState(0)
  return (
    <Popover
      label={label}
      closeSignal={closeSignal}
      triggerClassName={triggerClassName}
      panelClassName={cn('w-52 p-1', panelClassName)}
      trigger={trigger}
    >
      <div className="flex flex-col" role="menu">
        {items.map((item) => {
          const Icon = item.pending ? Loader2 : item.icon
          return (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              disabled={item.disabled || item.pending}
              className={menuItemClassName(item.danger ?? false)}
              onClick={() => {
                setCloseSignal((current) => current + 1)
                item.onSelect()
              }}
            >
              {Icon ? (
                <Icon
                  className={cn('size-4 shrink-0', item.pending && 'animate-spin')}
                  aria-hidden
                />
              ) : null}
              {item.label}
            </button>
          )
        })}
      </div>
    </Popover>
  )
}

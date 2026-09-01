import { ChevronDown, Loader2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { PopoverMenu, type PopoverMenuItem } from '@/components/ui/popover-menu'
import { cn } from '@/lib/utils'

export type TabAction = {
  label: string
  icon?: LucideIcon
  onAction?: () => void
  menu?: PopoverMenuItem[]
  pending?: boolean
  disabled?: boolean
  title?: string
  primary?: boolean
}

export function TabActionBar({ actions, info }: { actions: TabAction[]; info?: ReactNode }) {
  const ordered = [...actions].sort((a, b) => Number(b.primary ?? false) - Number(a.primary ?? false))
  return (
    <div className="flex flex-wrap items-center gap-2">
      {ordered.map((action) => {
        if (action.menu) {
          const Icon = action.icon
          return (
            <PopoverMenu
              key={action.label}
              label={action.label}
              panelClassName="w-48"
              triggerClassName={cn(
                'h-8 gap-1.5 rounded-sm px-3 text-xs',
                action.primary
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                  : 'text-muted-foreground hover:bg-subtle hover:text-foreground'
              )}
              trigger={
                <>
                  {Icon ? <Icon aria-hidden /> : null}
                  {action.label}
                  <ChevronDown className="size-3.5" aria-hidden />
                </>
              }
              items={action.menu}
            />
          )
        }
        const Icon = action.pending ? Loader2 : action.icon
        return (
          <Button
            key={action.label}
            variant={action.primary ? 'default' : 'ghost'}
            size="sm"
            className={action.primary ? undefined : 'text-muted-foreground hover:text-foreground'}
            disabled={action.pending || action.disabled}
            title={action.title}
            onClick={() => action.onAction?.()}
          >
            {Icon ? <Icon className={action.pending ? 'animate-spin' : undefined} aria-hidden /> : null}
            {action.label}
          </Button>
        )
      })}
      {info ? <div className="text-muted-foreground ml-auto self-center text-xs">{info}</div> : null}
    </div>
  )
}
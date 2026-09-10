import { useId } from 'react'
import type { ComponentType, ReactNode } from 'react'
import { motion } from 'framer-motion'

import { useMotionPresets } from '@/lib/motion'
import { cn } from '@/lib/utils'

export interface SegmentedItem {
  value: string
  label: string
  icon?: ComponentType<{ className?: string }>
  badge?: ReactNode
  ariaCurrent?: boolean
}

interface SegmentedControlProps {
  items: SegmentedItem[]
  value: string
  onChange: (value: string) => void
  variant?: 'pill' | 'underline'
  ariaLabel?: string
  className?: string
}

export function SegmentedControl({
  items,
  value,
  onChange,
  variant = 'pill',
  ariaLabel,
  className,
}: SegmentedControlProps) {
  const { reduced } = useMotionPresets()
  const layoutId = useId()

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        variant === 'pill'
          ? '-mt-4 flex w-fit items-center gap-1 rounded-lg bg-subtle p-1'
          : 'border-border flex flex-wrap items-center gap-x-1 border-b',
        className,
      )}
    >
      {items.map((item) => {
        const active = item.value === value
        const Icon = item.icon
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            aria-current={item.ariaCurrent && active ? 'page' : undefined}
            className={cn(
              'relative flex items-center gap-1.5 transition-colors',
              variant === 'pill'
                ? 'rounded-md px-3 py-1 text-xs'
                : '-mb-px border-b-2 border-transparent px-3 py-2 text-sm',
              active
                ? variant === 'pill'
                  ? 'text-foreground font-medium'
                  : 'text-primary font-medium'
                : 'text-muted-foreground hover:text-foreground',
            )}
            onClick={() => onChange(item.value)}
          >
            {active ? (
              <motion.span
                layoutId={layoutId}
                aria-hidden
                className={cn(
                  'absolute inset-0',
                  variant === 'pill'
                    ? 'bg-surface shadow-sm'
                    : 'inset-x-0 bottom-0 border-primary border-b-2',
                )}
                transition={
                  reduced ? { duration: 0 } : { type: 'spring', stiffness: 500, damping: 40 }
                }
              />
            ) : null}
            <span className="relative flex items-center gap-1.5">
              {Icon ? <Icon className={variant === 'pill' ? 'size-3.5' : 'size-4'} aria-hidden /> : null}
              {item.label}
              {item.badge}
            </span>
          </button>
        )
      })}
    </div>
  )
}

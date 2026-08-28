import { Check, Minus } from 'lucide-react'

import { cn } from '@/lib/utils'

export function CheckIndicator({
  checked,
  label,
  onToggle,
  mixed = false,
  className,
}: {
  checked: boolean
  label: string
  onToggle: () => void
  mixed?: boolean
  className?: string
}) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={mixed ? 'mixed' : checked}
      aria-label={label}
      onClick={(event) => {
        event.stopPropagation()
        onToggle()
      }}
      className={cn(
        'flex size-4 shrink-0 items-center justify-center rounded',
        checked || mixed
          ? 'bg-primary text-primary-foreground'
          : 'border-border text-muted-foreground border hover:border-foreground/40',
        className
      )}
    >
      {mixed ? (
        <Minus className="size-3" aria-hidden />
      ) : checked ? (
        <Check className="size-3" aria-hidden />
      ) : null}
    </button>
  )
}
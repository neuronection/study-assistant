import { useEffect, useRef } from 'react'

import { cn } from '@/lib/utils'

export function NameEditor({
  value,
  onChange,
  onCancel,
  ariaLabel,
  className,
}: {
  value: string
  onChange: (next: string) => void
  onCancel: () => void
  ariaLabel: string
  className?: string
}) {
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = ref.current
    if (el === null) {
      return
    }
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [value])

  return (
    <textarea
      ref={ref}
      autoFocus
      rows={1}
      aria-label={ariaLabel}
      className={cn(
        'bg-surface border-border leading-snug w-full resize-none overflow-hidden rounded-md border px-2 py-1 text-sm',
        className
      )}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onBlur={onCancel}
      onKeyDown={(event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
          event.preventDefault()
          event.currentTarget.form?.requestSubmit()
        } else if (event.key === 'Escape') {
          event.preventDefault()
          onCancel()
        }
      }}
    />
  )
}

export function normalizeName(name: string): string {
  return name.replace(/\s*\n\s*/g, ' ').trim()
}

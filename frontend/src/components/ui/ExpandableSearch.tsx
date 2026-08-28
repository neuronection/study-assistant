import { Search, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export function ExpandableSearch({
  value,
  onChange,
  onSubmit,
  onClear,
  placeholder,
  ariaLabel,
  clearLabel,
  expandLabel,
}: {
  value: string
  onChange: (value: string) => void
  onSubmit?: (value: string) => void
  onClear?: () => void
  placeholder: string
  ariaLabel: string
  clearLabel?: string
  expandLabel?: string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(value !== '')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      inputRef.current?.focus()
    }
  }, [open])

  const clear = () => {
    onChange('')
    onClear?.()
  }

  return (
    <form
      className={cn(
        'border-border bg-surface flex h-9 items-center overflow-hidden rounded-md border transition-[width] duration-300 ease-out',
        open ? 'w-64' : 'w-9'
      )}
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit?.(value)
      }}
    >
      <button
        type="button"
        className="text-muted-foreground hover:bg-subtle hover:text-foreground flex size-9 shrink-0 items-center justify-center"
        aria-label={open ? undefined : (expandLabel ?? t('common.search'))}
        title={open ? undefined : (expandLabel ?? t('common.search'))}
        onClick={() => {
          if (!open) {
            setOpen(true)
          } else {
            inputRef.current?.focus()
          }
        }}
      >
        <Search className="size-4" aria-hidden />
      </button>
      <input
        ref={inputRef}
        className={cn(
          'min-w-0 flex-1 bg-transparent text-sm outline-none transition-opacity duration-200',
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        )}
        placeholder={placeholder}
        aria-label={ariaLabel}
        aria-hidden={!open}
        tabIndex={open ? 0 : -1}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            if (value) {
              clear()
            } else {
              setOpen(false)
            }
          }
        }}
        onBlur={() => {
          if (!value) {
            setOpen(false)
          }
        }}
      />
      {open && value ? (
        <button
          type="button"
          className="text-muted-foreground hover:text-foreground mr-2 shrink-0"
          aria-label={clearLabel ?? t('common.clearSearch')}
          onClick={clear}
        >
          <X className="size-4" aria-hidden />
        </button>
      ) : null}
    </form>
  )
}

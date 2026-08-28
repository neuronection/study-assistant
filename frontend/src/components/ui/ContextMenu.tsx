import { useEffect, useRef } from 'react'

import { menuItemClassName } from '@/components/ui/popover-menu'

export interface ContextMenuItem {
  key: string
  label: string
  onSelect?: () => void
  danger?: boolean
  disabled?: boolean
  hint?: string
}

export function ContextMenu({
  x,
  y,
  items,
  onClose,
}: {
  x: number
  y: number
  items: ContextMenuItem[]
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onClose()
      }
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  const top = Math.min(y, window.innerHeight - items.length * 32 - 16)
  const left = Math.min(x, window.innerWidth - 180)

  return (
    <div
      ref={ref}
      className="border-border bg-surface fixed z-50 min-w-40 overflow-hidden rounded-md border shadow-lg"
      style={{ top, left }}
      role="menu"
    >
      {items.map((item) =>
        item.disabled === true ? (
          <span
            key={item.key}
            role="menuitem"
            aria-disabled="true"
            title={item.hint}
            className={menuItemClassName(item.danger ?? false) +
              ' text-muted-foreground/50 pointer-events-none'}
          >
            {item.label}
          </span>
        ) : (
          <button
            key={item.key}
            type="button"
            role="menuitem"
            title={item.hint}
            className={menuItemClassName(item.danger ?? false)}
            onClick={() => {
              onClose()
              item.onSelect?.()
            }}
          >
            {item.label}
          </button>
        )
      )}
    </div>
  )
}

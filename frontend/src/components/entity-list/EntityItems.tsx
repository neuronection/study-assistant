import { MoreHorizontal } from 'lucide-react'
import { useState, type ComponentType, type MouseEvent, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { ContextMenu, type ContextMenuItem } from '@/components/ui/ContextMenu'
import { InfoButton } from '@/components/ui/InfoButton'
import type { LibraryView } from '@/components/ui/ViewToggle'
import { isKeyboardClick } from '@/lib/useSelection'

import { cn } from '@/lib/utils'

export interface EntityItemEntry {
  key: string
  title: string
  icon: ComponentType<{ className?: string }>
  iconClassName?: string
  meta?: string | null
  onClick?: () => void
  trailing?: ReactNode
  info?: ReactNode
  infoTitle?: ReactNode
}

export interface EntitySelection {
  isSelected: (key: string) => boolean
  onPointerDown: (
    key: string,
    event: { ctrlKey: boolean; metaKey: boolean; shiftKey: boolean }
  ) => void
}

export function EntityItems<T>({
  items,
  layout,
  menuItems,
  emptyLabel,
  selection,
  onDragStart,
}: {
  items: Array<EntityItemEntry & T>
  layout: LibraryView
  menuItems?: (item: EntityItemEntry & T) => ContextMenuItem[]
  emptyLabel?: string
  selection?: EntitySelection
  onDragStart?: (event: React.DragEvent, item: EntityItemEntry & T) => void
}) {
  const { t } = useTranslation()
  const [menu, setMenu] = useState<{ x: number; y: number; item: EntityItemEntry & T } | null>(
    null,
  )

  if (items.length === 0) {
    return emptyLabel ? (
      <p className="text-muted-foreground py-8 text-center text-sm">{emptyLabel}</p>
    ) : null
  }

  const openMenu = (event: MouseEvent, item: EntityItemEntry & T) => {
    if (!menuItems) {
      return
    }
    event.preventDefault()
    event.stopPropagation()
    setMenu({ x: event.clientX, y: event.clientY, item })
  }

  const openKebab = (event: MouseEvent<HTMLButtonElement>, item: EntityItemEntry & T) => {
    if (!menuItems) {
      return
    }
    event.stopPropagation()
    const rect = event.currentTarget.getBoundingClientRect()
    setMenu({ x: rect.left, y: rect.bottom + 4, item })
  }

  return (
    <>
      {layout === 'grid' ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-4 p-2">
          {items.map((item) => {
            const Icon = item.icon
            return (
              <div
                key={item.key}
                role="button"
                tabIndex={0}
                draggable={onDragStart !== undefined}
                data-selectable-id={selection === undefined ? undefined : item.key}
                className={cn(
                  'group relative flex min-h-28 cursor-pointer select-none flex-col items-center gap-2 rounded-lg border border-transparent p-3 text-center transition-colors hover:border-border hover:bg-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                  selection?.isSelected(item.key) && 'border-primary bg-primary/10 hover:bg-primary/10'
                )}
                onMouseDown={
                  selection === undefined
                    ? undefined
                    : (event) => selection.onPointerDown(item.key, event)
                }
                onDragStart={
                  onDragStart === undefined ? undefined : (event) => onDragStart(event, item)
                }
                onClick={(event) => {
                  if (selection !== undefined && !isKeyboardClick(event)) {
                    return
                  }
                  item.onClick?.()
                }}
                onDoubleClick={() => item.onClick?.()}
                onContextMenu={(event) => openMenu(event, item)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    item.onClick?.()
                  }
                }}
              >
                <Icon
                  className={cn('text-muted-foreground size-8 shrink-0', item.iconClassName)}
                  aria-hidden
                />
                <span className="flex w-full items-center justify-center gap-1">
                  <span className="line-clamp-2 text-xs">{item.title}</span>
                  {item.info ? (
                    <InfoButton title={item.infoTitle}>{item.info}</InfoButton>
                  ) : null}
                </span>
                {item.meta ? (
                  <span className="text-muted-foreground w-full truncate text-[10px]">
                    {item.meta}
                  </span>
                ) : null}
                {menuItems ? (
                  <span
                    className="bg-surface border-border absolute top-1.5 right-1.5 rounded-md border opacity-0 shadow-sm transition-opacity group-hover:opacity-100"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <KebabButton item={item} onOpen={openKebab} label={t('common.actions')} />
                  </span>
                ) : null}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="flex flex-col gap-2 p-2">
          {items.map((item) => {
            const Icon = item.icon
            return (
              <div
                key={item.key}
                className={cn(
                  'hover:bg-subtle group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm',
                  selection?.isSelected(item.key) && 'bg-primary/10'
                )}
                data-selectable-id={selection === undefined ? undefined : item.key}
                draggable={onDragStart !== undefined}
                onDragStart={
                  onDragStart === undefined ? undefined : (event) => onDragStart(event, item)
                }
                onMouseDown={
                  selection === undefined
                    ? undefined
                    : (event) => selection.onPointerDown(item.key, event)
                }
                onDoubleClick={() => item.onClick?.()}
                onContextMenu={(event) => openMenu(event, item)}
              >
<button
                  type="button"
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  onClick={(event) => {
                    if (selection !== undefined && !isKeyboardClick(event)) {
                      return
                    }
                    item.onClick?.()
                  }}
                >
                <Icon
                  className="text-muted-foreground size-4 shrink-0"
                  aria-hidden
                />
                <span className="flex-1 truncate">{item.title}</span>
                {item.meta ? (
                  <span className="text-muted-foreground shrink-0 text-xs">{item.meta}</span>
                ) : null}
                {item.trailing}
              </button>
                {item.info ? (
                  <InfoButton title={item.infoTitle}>{item.info}</InfoButton>
                ) : null}
                {menuItems ? (
                  <span className="opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                    <KebabButton item={item} onOpen={openKebab} label={t('common.actions')} />
                  </span>
                ) : null}
              </div>
            )
          })}
        </div>
      )}
      {menu !== null ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={menuItems?.(menu.item) ?? []}
          onClose={() => setMenu(null)}
        />
      ) : null}
    </>
  )
}

function KebabButton<T>({
  item,
  onOpen,
  label,
}: {
  item: EntityItemEntry & T
  onOpen: (event: MouseEvent<HTMLButtonElement>, item: EntityItemEntry & T) => void
  label: string
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className="text-muted-foreground hover:text-foreground rounded-md p-1"
      onClick={(event) => onOpen(event, item)}
    >
      <MoreHorizontal className="size-4" aria-hidden />
    </button>
  )
}

import type { MouseEvent } from 'react'

import { AiBadge } from '@/features/ai/AiBadge'
import { KindIcon } from '@/features/library/KindIcon'
import { cn } from '@/lib/utils'

import type { MaterialSummary } from './MaterialRow'

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={cn(
        'shrink-0 rounded-full px-2 py-0.5 text-[10px]',
        status === 'ready' && 'bg-success/15 text-success',
        status === 'failed' && 'bg-danger/15 text-danger',
        (status === 'pending' || status === 'processing') && 'bg-warning/15 text-warning'
      )}
    >
      {status}
    </span>
  )
}

export function MaterialTile({
  material,
  onClick,
  onDoubleClick,
  onMouseDown,
  onContextMenu,
  className,
  selectionState = 'none',
}: {
  material: MaterialSummary
  onClick?: (event: MouseEvent<HTMLButtonElement>) => void
  onDoubleClick?: (event: MouseEvent<HTMLButtonElement>) => void
  onMouseDown?: (event: MouseEvent<HTMLButtonElement>) => void
  onContextMenu?: (event: MouseEvent<HTMLButtonElement>) => void
  className?: string
  selectionState?: 'none' | 'selected' | 'cut'
}) {
  return (
    <button
      type="button"
      className={cn(
        'group flex cursor-pointer select-none flex-col items-center gap-2 rounded-lg border border-transparent p-3 text-center transition-colors hover:border-border hover:bg-subtle',
        selectionState === 'selected' && 'border-primary bg-primary/10 hover:bg-primary/10',
        selectionState === 'cut' && 'border-primary/50 bg-primary/5 opacity-50 hover:bg-primary/10',
        className
      )}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      onMouseDown={onMouseDown}
      onContextMenu={onContextMenu}
    >
      <KindIcon kind={material.kind ?? 'doc'} className="text-muted-foreground size-8 shrink-0" />
      <span
        className={cn(
          'line-clamp-3 text-xs',
          selectionState === 'selected' && 'line-clamp-4'
        )}
      >
        {material.title}
      </span>
      {material.aiComposed ? <AiBadge /> : null}
      {material.status ? <StatusPill status={material.status} /> : null}
    </button>
  )
}

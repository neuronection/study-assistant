import type { MouseEvent, ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { AiBadge } from '@/features/ai/AiBadge'
import { KindIcon } from '@/features/library/KindIcon'
import { CheckIndicator } from '@/components/ui/CheckIndicator'
import { isKeyboardClick } from '@/lib/useSelection'
import { cn } from '@/lib/utils'

export interface MaterialSummary {
  id: number
  title: string
  kind?: string
  status?: string
  aiComposed?: boolean
  readStatus?: string
  progress?: number
  rationale?: string
}

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

function ReadPill({ status, progress }: { status: string; progress: number }) {
  const { t } = useTranslation()
  return (
    <span
      className={cn(
        'shrink-0 rounded-full px-2 py-0.5 text-[10px]',
        status === 'studied' && 'bg-success/15 text-success',
        status === 'reading' && 'bg-warning/15 text-warning',
        status === 'unread' && 'bg-subtle text-muted-foreground'
      )}
      title={
        status === 'reading'
          ? t('chapter.progressAt', { percent: Math.round(progress * 100) })
          : undefined
      }
    >
      {t(`library.studyState_${status}`)}
    </span>
  )
}

export function MaterialRow({
  material,
  selected,
  onToggle,
  onOpen,
  action,
  locked,
  lockedLabel,
  draggable,
  onDragStart,
  title,
  className,
  compact,
  onContextMenu,
  selectionState = 'none',
  onMouseDown,
}: {
  material: MaterialSummary
  selected?: boolean
  onToggle?: () => void
  onOpen?: (event: MouseEvent<Element>) => void
  action?: ReactNode
  locked?: boolean
  lockedLabel?: ReactNode
  draggable?: boolean
  onDragStart?: (event: React.DragEvent<HTMLDivElement>) => void
  title?: string
  className?: string
  compact?: boolean
  onContextMenu?: (event: React.MouseEvent<HTMLDivElement>) => void
  selectionState?: 'none' | 'selected' | 'cut'
  onMouseDown?: (event: React.MouseEvent<HTMLDivElement>) => void
}) {
  if (locked) {
    return (
      <div
        className={cn(
          'bg-subtle/60 text-muted-foreground flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
          compact && 'text-xs',
          className
        )}
      >
        <span className="size-4 shrink-0" aria-hidden />
        {material.kind ? (
          <KindIcon kind={material.kind} className="text-muted-foreground/60 size-4 shrink-0" />
        ) : null}
        <span className="min-w-0 flex-1 truncate">{material.title}</span>
        {lockedLabel ? (
          <span className="bg-primary/10 text-primary shrink-0 rounded-full px-2 py-0.5 text-[10px]">
            {lockedLabel}
          </span>
        ) : null}
      </div>
    )
  }
  return (
    <div
      className={cn(
        'hover:bg-subtle group flex w-full items-center gap-2 rounded-md px-2 py-1.5',
        compact ? 'text-xs' : 'text-sm',
        selected !== undefined && onToggle && 'cursor-pointer',
        selectionState === 'selected' && 'bg-primary/10',
        selectionState === 'cut' && 'bg-primary/5 opacity-50',
        className
      )}
      draggable={draggable}
      onDragStart={onDragStart}
      onContextMenu={onContextMenu}
      onMouseDown={onMouseDown}
      onDoubleClick={onOpen}
      title={title}
    >
      {onToggle ? (
        <CheckIndicator
          checked={selected ?? false}
          label={material.title}
          onToggle={onToggle}
        />
      ) : null}
      {material.kind ? (
        <KindIcon kind={material.kind} className="text-muted-foreground size-4 shrink-0" />
      ) : null}
      {onOpen ? (
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
          onClick={(event) => {
            if (isKeyboardClick(event)) {
              onOpen(event)
            }
          }}
        >
          <span
            className={cn(
              'min-w-0 flex-1',
              selectionState === 'selected' ? 'line-clamp-2' : 'truncate'
            )}
          >
            {material.title}
          </span>
          {material.aiComposed ? <AiBadge /> : null}
          {material.rationale ? (
            <span
              className="text-muted-foreground hidden shrink-0 truncate text-[10px] italic md:inline"
              title={material.rationale}
            >
              {material.rationale}
            </span>
          ) : null}
        </button>
      ) : (
        <span
          className={cn(
            'min-w-0 flex-1',
            selectionState === 'selected' ? 'line-clamp-2' : 'truncate'
          )}
        >
          {material.title}
        </span>
      )}
      {!onOpen && material.aiComposed ? <AiBadge /> : null}
      {!onOpen && material.rationale ? (
        <span
          className="text-muted-foreground hidden shrink-0 truncate text-[10px] italic md:inline"
          title={material.rationale}
        >
          {material.rationale}
        </span>
      ) : null}
      {material.readStatus ? (
        <ReadPill status={material.readStatus} progress={material.progress ?? 0} />
      ) : null}
      {material.status ? <StatusPill status={material.status} /> : null}
      {action ?? null}
    </div>
  )
}

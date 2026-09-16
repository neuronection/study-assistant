import { FolderClosed, Link2 } from 'lucide-react'
import type {
  HTMLAttributes,
  MouseEventHandler,
  ReactNode,
} from 'react'

import { LibraryBreadcrumbs, type Crumb } from '@/features/library/LibraryBreadcrumbs'
import { isKeyboardClick } from '@/lib/useSelection'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const GRID_CLASSES = 'grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-4 p-2'
const LIST_CLASSES = 'flex flex-col gap-2 p-2'

export const folderTileClass =
  'group flex cursor-pointer select-none flex-col items-center gap-2 rounded-lg border border-transparent p-3 text-center transition-colors hover:border-border hover:bg-subtle'

export const folderRowClass =
  'hover:bg-subtle flex w-full cursor-pointer select-none items-center gap-2 rounded-md px-3 py-2 text-left text-sm'

function folderIcon(linked: boolean, compact: boolean) {
  const size = compact ? 'size-4' : 'size-8'
  if (!linked) {
    return <FolderClosed className={cn('text-primary shrink-0', size)} aria-hidden />
  }
  return (
    <span className="relative shrink-0">
      <FolderClosed className={cn('text-primary', size)} aria-hidden />
      <Link2 className="text-primary absolute right-0 bottom-0 size-3.5" aria-hidden />
    </span>
  )
}

export interface MaterialFolderSpec {
  key: string
  name: string
  linked?: boolean
  title?: string
  selectionState?: 'none' | 'selected' | 'cut'
  onPointerDown?: MouseEventHandler<HTMLElement>
  onOpen: () => void
  onContextMenu?: MouseEventHandler<HTMLElement>
  badge?: ReactNode
  trailing?: ReactNode
  gridMeta?: ReactNode
  dragProps?: HTMLAttributes<HTMLElement> & { draggable?: boolean }
  dropHighlighted?: boolean
  render?: ReactNode
}

function MaterialFolderItem({ folder, view }: { folder: MaterialFolderSpec; view: 'grid' | 'list' }) {
  if (folder.render !== undefined) {
    return <>{folder.render}</>
  }
  const selected = folder.selectionState === 'selected'
  const cut = folder.selectionState === 'cut'
  const selectionClass = (root: 'grid' | 'row') =>
    cut
      ? 'border-primary/50 bg-primary/5 opacity-50'
      : selected
        ? root === 'grid'
          ? 'border-primary bg-primary/10 hover:bg-primary/10'
          : 'bg-primary/10'
        : null
  const nameClasses =
    view === 'grid'
      ? cn('line-clamp-3 text-xs', selected && 'line-clamp-4')
      : cn('min-w-0 flex-1', selected ? 'line-clamp-2' : 'truncate')
  const openHandlers = {
    onMouseDown: folder.onPointerDown,
    onDoubleClick: folder.onOpen,
    onContextMenu: folder.onContextMenu,
    ...(folder.dragProps ?? {}),
  }
  if (view === 'grid') {
    return (
      <button
        type="button"
        data-selectable-id={folder.key}
        title={folder.title}
        className={cn(folderTileClass, selectionClass('grid'), folder.dropHighlighted && 'ring-primary ring-2')}
        onClick={(event) => {
          if (isKeyboardClick(event)) {
            folder.onOpen()
          }
        }}
        {...openHandlers}
      >
        {folderIcon(folder.linked === true, false)}
        <span className={nameClasses}>{folder.name}</span>
        {folder.badge ?? null}
        {folder.gridMeta ?? null}
      </button>
    )
  }
  return (
    <div
      data-selectable-id={folder.key}
      title={folder.title}
      className={cn(
        folderRowClass,
        selected && 'bg-primary/10',
        folder.dropHighlighted && 'ring-primary ring-2'
      )}
      {...openHandlers}
    >
      {folderIcon(folder.linked === true, true)}
      <button
        type="button"
        className={cn('flex min-w-0 flex-1 items-center gap-2 text-left', nameClasses)}
        onClick={(event) => {
          if (isKeyboardClick(event)) {
            folder.onOpen()
          }
        }}
      >
        {folder.name}
      </button>
      {folder.badge ?? null}
      {folder.trailing ?? null}
    </div>
  )
}

export function MaterialBrowserSkeleton({
  view,
  count = 8,
  className,
}: {
  view: 'grid' | 'list'
  count?: number
  className?: string
}) {
  return (
    <div
      aria-busy="true"
      className={cn(view === 'grid' ? GRID_CLASSES : LIST_CLASSES, className)}
    >
      {Array.from({ length: count }, (_, index) =>
        view === 'grid' ? (
          <div
            key={index}
            className="flex flex-col items-center gap-2 rounded-lg p-3 text-center"
          >
            <Skeleton className="size-8 rounded-md" />
            <Skeleton className="h-3 w-4/5" />
            <Skeleton className="h-3 w-3/5" />
          </div>
        ) : (
          <div key={index} className="flex w-full items-center gap-2 rounded-md px-3 py-2">
            <Skeleton className="size-4 rounded-sm" />
            <Skeleton className="h-4 min-w-0 flex-1" />
            <Skeleton className="h-3.5 w-14 shrink-0" />
          </div>
        ),
      )}
    </div>
  )
}

export function MaterialBrowser({
  view,
  folders,
  crumbs,
  crumbsExtra,
  children,
  className,
  containerProps,
}: {
  view: 'grid' | 'list'
  folders: MaterialFolderSpec[]
  crumbs?: Crumb[]
  crumbsExtra?: ReactNode
  children?: ReactNode
  className?: string
  containerProps?: Omit<HTMLAttributes<HTMLDivElement>, 'children'> & {
    'data-marquee-surface'?: string
  }
}) {
  return (
    <>
      {crumbs !== undefined || crumbsExtra !== undefined ? (
        <div className="flex min-w-0 items-center justify-between gap-2">
          {crumbs !== undefined ? <LibraryBreadcrumbs items={crumbs} /> : null}
          {crumbsExtra ?? null}
        </div>
      ) : null}
      <div
        className={cn(view === 'grid' ? GRID_CLASSES : LIST_CLASSES, className)}
        {...containerProps}
      >
        {folders.map((folder) => (
          <MaterialFolderItem key={folder.key} folder={folder} view={view} />
        ))}
        {children}
      </div>
    </>
  )
}

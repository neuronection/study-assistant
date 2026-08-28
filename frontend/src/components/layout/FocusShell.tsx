import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Maximize2, Minimize2, X } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import { courseTree, type NodeInfo } from '@/lib/api'
import { cn } from '@/lib/utils'

const MAXIMIZE_KEY = 'ca-focus-fullscreen'

function readMaximized(): boolean {
  try {
    return window.localStorage.getItem(MAXIMIZE_KEY) === '1'
  } catch {
    return false
  }
}

export interface FocusContextInfo {
  courseId: string
  nodeId: string | null
  courseTitle: string | undefined
  nodeTitle: string | undefined
  isRoot: boolean
}

function findNode(nodes: NodeInfo[], targetId: number): NodeInfo | null {
  for (const node of nodes) {
    if (node.id === targetId) {
      return node
    }
    const nested = findNode(node.children, targetId)
    if (nested !== null) {
      return nested
    }
  }
  return null
}

export function useFocusContext(
  courseId: number | null | undefined,
  nodeId: number | null | undefined
): FocusContextInfo | null {
  const tree = useQuery({
    queryKey: ['tree', String(courseId)],
    queryFn: () => courseTree(courseId!),
    enabled: courseId !== null && courseId !== undefined,
  })
  if (courseId === null || courseId === undefined) {
    return null
  }
  const root = tree.data?.[0]
  const node = nodeId !== null && nodeId !== undefined && root ? findNode([root], nodeId) : null
  return {
    courseId: String(courseId),
    nodeId: nodeId !== null && nodeId !== undefined ? String(nodeId) : null,
    courseTitle: root?.title,
    nodeTitle: node?.title ?? (root && root.id === nodeId ? root.title : undefined),
    isRoot: node === null || root?.id === nodeId,
  }
}

function ContextBreadcrumb({ context }: { context: FocusContextInfo }) {
  const { t } = useTranslation()
  return (
    <nav
      className="text-muted-foreground flex min-w-0 flex-wrap items-center gap-1 text-xs"
      aria-label={t('workspace.breadcrumb')}
    >
      <Link
        to="/courses/$courseId"
        params={{ courseId: context.courseId }}
        className="hover:text-foreground flex min-w-0 items-center gap-1 hover:underline"
      >
        <span className="bg-primary size-2 shrink-0 rounded-full" aria-hidden />
        <span className="truncate">{context.courseTitle ?? t('workspace.courseLabel')}</span>
      </Link>
      {context.nodeId !== null && context.nodeTitle !== undefined && !context.isRoot ? (
        <span className="flex min-w-0 items-center gap-1">
          <ChevronRight className="size-3 shrink-0" aria-hidden />
          <Link
            to="/courses/$courseId/n/$nodeId"
            params={{ courseId: context.courseId, nodeId: context.nodeId ?? '' }}
            className="hover:text-foreground truncate hover:underline"
          >
            {context.nodeTitle}
          </Link>
        </span>
      ) : null}
    </nav>
  )
}

export function FocusShell({
  title,
  ariaLabel,
  context,
  meta,
  onClose,
  overlay = false,
  contentClassName,
  children,
}: {
  title: ReactNode
  ariaLabel?: string
  context?: FocusContextInfo | null
  meta?: ReactNode
  onClose?: () => void
  overlay?: boolean
  contentClassName?: string
  children: ReactNode
}) {
  const { t } = useTranslation()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [maximized, setMaximized] = useState(readMaximized)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    try {
      window.localStorage.setItem(MAXIMIZE_KEY, maximized ? '1' : '0')
    } catch {
      return
    }
  }, [maximized])

  useEffect(() => {
    if (!overlay || !onClose) {
      return
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [overlay, onClose])

  useEffect(() => {
    if (overlay) {
      panelRef.current?.focus()
    }
  }, [overlay])

  const header = (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {context ? <ContextBreadcrumb context={context} /> : null}
          <h1 className="truncate text-lg font-semibold">{title}</h1>
        </div>
        {overlay ? (
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMaximized((value) => !value)}
            title={maximized ? t('focus.collapse') : t('focus.expand')}
            aria-label={maximized ? t('focus.collapse') : t('focus.expand')}
            aria-pressed={maximized}
          >
            {maximized ? (
              <Minimize2 className="size-4" aria-hidden />
            ) : (
              <Maximize2 className="size-4" aria-hidden />
            )}
          </Button>
        ) : null}
        {onClose ? (
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            title={t('common.close')}
            aria-label={t('common.close')}
          >
            <X className="size-4" aria-hidden />
          </Button>
        ) : null}
      </div>
      {meta ? (
        <div>
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground flex items-center gap-1 text-[11px]"
            aria-expanded={detailsOpen}
            onClick={() => setDetailsOpen((value) => !value)}
          >
            <ChevronDown
              className={cn('size-3.5 transition-transform', !detailsOpen && '-rotate-90')}
              aria-hidden
            />
            {detailsOpen ? t('focus.hideDetails') : t('focus.details')}
          </button>
          {detailsOpen ? (
            <div className="text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              {meta}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )

  if (overlay) {
    return (
      <div
        className="fixed inset-0 z-50 bg-black/40"
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            onClose?.()
          }
        }}
      >
        <div
          ref={panelRef}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          aria-label={ariaLabel ?? (typeof title === 'string' ? title : undefined)}
          className={cn(
            'bg-surface border-border absolute top-0 right-0 h-full overflow-y-auto border-l shadow-xl outline-none',
            maximized ? 'w-full' : 'w-[min(760px,100vw-2rem)]'
          )}
        >
          <div className="border-border bg-surface sticky top-0 z-10 border-b p-4">
            {header}
          </div>
          <div className="p-6">{children}</div>
        </div>
      </div>
    )
  }

  return (
    <div className={cn('mx-auto max-w-2xl p-8', contentClassName)}>
      <div className="mb-5">{header}</div>
      {children}
    </div>
  )
}

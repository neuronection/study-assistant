import { useQuery } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { courseTree, type NodeInfo } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useCloseFloatings } from '@/lib/ui-overlays'

function flattenNodes(nodes: NodeInfo[]): Array<{ node: NodeInfo; depth: number }> {
  const rows: Array<{ node: NodeInfo; depth: number }> = []
  const walk = (entries: NodeInfo[], depth: number) => {
    for (const entry of entries) {
      rows.push({ node: entry, depth })
      walk(entry.children, depth + 1)
    }
  }
  walk(nodes, 0)
  return rows
}

export function AssignToNodeDialog({
  courseId,
  title,
  countText,
  confirmLabel,
  onDone,
  onClose,
}: {
  courseId: number
  title: string
  countText: string
  confirmLabel: string
  onDone: (nodeId: number) => Promise<void> | void
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const [selected, setSelected] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  const tree = useQuery({
    queryKey: ['tree', String(courseId)],
    queryFn: () => courseTree(courseId),
  })
  const rows = flattenNodes(tree.data ?? [])

  const confirm = async () => {
    if (selected === null) {
      return
    }
    setPending(true)
    try {
      await onDone(selected)
    } finally {
      setPending(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="bg-surface border-border flex max-h-[70vh] w-full max-w-md flex-col rounded-lg border shadow-xl">
        <header className="border-border border-b px-4 py-2">
          <h2 className="text-sm font-semibold">
            {title}
            <span className="text-muted-foreground ml-2 font-normal">{countText}</span>
          </h2>
        </header>
        <div className="flex-1 overflow-y-auto p-2" role="tree">
          {rows.map(({ node, depth }) => (
            <button
              key={node.id}
              type="button"
              role="treeitem"
              aria-selected={selected === node.id}
              className={cn(
                'hover:bg-subtle flex w-full items-center gap-1 rounded-md px-2 py-1.5 text-left text-sm',
                selected === node.id && 'bg-primary/10'
              )}
              style={{ paddingLeft: `${depth * 16 + 8}px` }}
              onClick={() => setSelected(node.id)}
            >
              <ChevronRight
                className="text-muted-foreground size-3.5 shrink-0"
                aria-hidden
              />
              <span className="truncate">{node.title}</span>
              {node.is_root ? (
                <span className="text-muted-foreground ml-auto shrink-0 text-[10px]">
                  {t('assignToNode.courseLevel')}
                </span>
              ) : null}
            </button>
          ))}
          {tree.data && rows.length === 0 ? (
            <p className="text-muted-foreground p-4 text-sm">
              {t('assignToNode.empty')}
            </p>
          ) : null}
        </div>
        <footer className="border-border flex justify-end gap-2 border-t px-4 py-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t('library.cancelEdit')}
          </Button>
          <Button
            size="sm"
            disabled={selected === null || pending}
            onClick={() => void confirm()}
          >
            {confirmLabel}
          </Button>
        </footer>
      </div>
    </div>
  )
}

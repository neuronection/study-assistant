import { useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { type NodeInfo } from '@/lib/api'
import { formatRelativeTime } from '@/lib/format'
import { getRecentNodes, resolveRecentNodes } from '@/lib/recent-nodes'

export function NodeRecentStrip({
  courseId,
  tree,
}: {
  courseId: string
  tree: NodeInfo[] | undefined
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const rows = useMemo(() => {
    const rootId = tree?.[0]?.id
    const entries = getRecentNodes()
      .filter((entry) => entry.courseId === Number(courseId) && entry.nodeId !== rootId)
      .slice(0, 3)
    if (tree === undefined || tree.length === 0 || entries.length === 0) {
      return []
    }
    return resolveRecentNodes(entries, new Map([[Number(courseId), tree]]), new Map())
  }, [courseId, tree])
  if (rows.length === 0) {
    return null
  }
  return (
    <section className="space-y-1.5" aria-label={t('workspace.jumpBackIn')}>
      <p className="text-muted-foreground text-xs font-medium">{t('workspace.jumpBackIn')}</p>
      <div className="border-border bg-surface divide-border divide-y rounded-lg border">
        {rows.map((row) => (
          <button
            key={row.nodeId}
            type="button"
            className="hover:bg-subtle/60 flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm first:rounded-t-lg last:rounded-b-lg"
            title={row.breadcrumb}
            onClick={() =>
              void navigate({
                to: '/courses/$courseId/n/$nodeId',
                params: { courseId, nodeId: String(row.nodeId) },
              })
            }
          >
            <span className="min-w-0 flex-1 truncate font-medium">{row.title}</span>
            <span className="text-muted-foreground shrink-0 text-[10px]">
              {formatRelativeTime(row.at)}
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}

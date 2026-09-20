import { useNavigate } from '@tanstack/react-router'
import { History } from 'lucide-react'
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
    const entries = getRecentNodes()
      .filter((entry) => entry.courseId === Number(courseId))
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
    <section className="space-y-2" aria-label={t('workspace.jumpBackIn')}>
      <p className="text-muted-foreground flex items-center gap-1.5 text-xs font-medium">
        <History className="size-3.5" aria-hidden />
        {t('workspace.jumpBackIn')}
      </p>
      <div className="flex flex-wrap gap-2">
        {rows.map((row) => (
          <button
            key={row.nodeId}
            type="button"
            className="bg-subtle hover:bg-subtle/70 text-foreground flex max-w-full items-center gap-1.5 rounded-full px-3 py-1.5 text-xs"
            title={row.breadcrumb}
            onClick={() =>
              void navigate({
                to: '/courses/$courseId/n/$nodeId',
                params: { courseId, nodeId: String(row.nodeId) },
              })
            }
          >
            <span className="truncate">{row.title}</span>
            <span className="text-muted-foreground shrink-0 text-[10px]">
              {formatRelativeTime(row.at)}
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}

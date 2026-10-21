import type { components } from '@/lib/api-schema'
import {Link} from '@tanstack/react-router'
import {useTranslation} from 'react-i18next'

export function ScopeChip({
  nodeId,
  courseId,
  titles,
}: {
  nodeId: string | null
  courseId: string
  titles: Map<string, string>
}) {
  const { t } = useTranslation()
  if (nodeId === null) {
    return null
  }
  const label = titles.get(nodeId)
  return (
    <Link
      to="/courses/$courseId/n/$nodeId"
      params={{ courseId, nodeId: String(nodeId) }}
      className="bg-subtle text-muted-foreground hover:text-foreground shrink-0 rounded-full px-2 py-0.5 text-[10px] hover:underline"
      title={label ?? undefined}
    >
      {label ?? t('workspace.otherNode')}
    </Link>
  )
}


export type WorkspaceData = components['schemas']['NodeWorkspaceOut']

import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getFolderLinks, getMaterialLinks } from '@/lib/api'
import type { MaterialLinkInfo } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

export interface LinkedLocationsTarget {
  kind: 'material' | 'folder'
  id: number
  title: string
}

type LocationRow = {
  node_id: number
  owner_title: string
  breadcrumb: { id: number; title: string }[]
  is_course_level: boolean
  course_id: number
  auto_assigned: boolean
  rationale: string | null
  via_folder?: { id: number; name: string } | null
}

function dedupeByNode(entries: MaterialLinkInfo[]): MaterialLinkInfo[] {
  const byNode = new Map<number, MaterialLinkInfo>()
  for (const entry of entries) {
    const existing = byNode.get(entry.node_id)
    if (existing === undefined || (existing.via_folder !== null && entry.via_folder === null)) {
      byNode.set(entry.node_id, entry)
    }
  }
  return [...byNode.values()]
}

export function LinkedLocationsDialog({
  target,
  onClose,
}: {
  target: LinkedLocationsTarget
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const navigateTo = useNavigate()
  const locations = useQuery({
    queryKey: ['linked-locations', target.kind, target.id],
    queryFn: async (): Promise<LocationRow[]> => {
      if (target.kind === 'folder') {
        return getFolderLinks(target.id)
      }
      return dedupeByNode(await getMaterialLinks(target.id)).map((entry) => ({
        ...entry,
        course_id: entry.course_id ?? 0,
      }))
    },
  })
  const rows = locations.data ?? []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[85vh] w-full max-w-xl overflow-y-auto">
        <CardHeader>
          <CardTitle className="text-base">{t('library.linkedLocationsTitle')}</CardTitle>
          <CardDescription className="truncate">{target.title}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {locations.isLoading ? (
            <Loader2
              className="text-muted-foreground animate-spin"
              aria-label={t('library.loading')}
            />
          ) : rows.length === 0 ? (
            <p className="text-muted-foreground p-2 text-xs">
              {t('library.linkedLocationsEmpty')}
            </p>
          ) : (
            <ul className="space-y-1">
              {rows.map((entry) => (
                <li key={`${entry.course_id}-${entry.node_id}`}>
                  <Button
                    variant="ghost"
                    className="h-auto w-full flex-col items-start gap-0.5 px-2 py-1.5 text-left"
                    onClick={() => {
                      onClose()
                      if (entry.is_course_level) {
                        void navigateTo({
                          to: '/courses/$courseId',
                          params: { courseId: String(entry.course_id) },
                        })
                      } else {
                        void navigateTo({
                          to: '/courses/$courseId/n/$nodeId',
                          params: {
                            courseId: String(entry.course_id),
                            nodeId: String(entry.node_id),
                          },
                        })
                      }
                    }}
                  >
                    <span className="line-clamp-2 w-full text-xs">
                      {entry.breadcrumb.map((part) => part.title).join(' › ')}
                    </span>
                    <span className="flex w-full flex-wrap items-center gap-1">
                      {entry.auto_assigned ? (
                        <span className="bg-primary/10 text-primary rounded-full px-1.5 py-0.5 text-[10px]">
                          {t('library.linkedLocationsAuto')}
                        </span>
                      ) : null}
                      {entry.via_folder ? (
                        <span className="bg-subtle text-muted-foreground rounded-full px-1.5 py-0.5 text-[10px]">
                          {t('library.linkedLocationsViaFolder', { name: entry.via_folder.name })}
                        </span>
                      ) : null}
                      {entry.rationale ? (
                        <span
                          className="text-muted-foreground truncate text-[10px] italic"
                          title={entry.rationale}
                        >
                          {entry.rationale}
                        </span>
                      ) : null}
                    </span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex justify-end">
            <Button variant="outline" size="sm" onClick={onClose}>
              {t('common.close')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

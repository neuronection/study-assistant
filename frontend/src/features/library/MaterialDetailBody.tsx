import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { FileDown, Loader2, NotebookPen } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { exportMarkdownWithDrawings } from '@/components/materials/exportMarkdown'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import {
  getMaterial,
  getMaterialLinks,
  listCourses,
  listStudyStates,
  setStudyState,
} from '@/lib/api'

import { ExtractionView } from './ExtractionView'
import { OriginalView } from './OriginalView'

export type DetailTab = 'extraction' | 'original' | 'side-by-side'

export const DETAIL_TABS: DetailTab[] = ['extraction', 'original', 'side-by-side']

export function MaterialDetailBody({
  materialId,
  activeTab,
  onTabChange,
  showTitle = true,
  onTakeNotes,
}: {
  materialId: number
  activeTab: DetailTab
  onTabChange: (tab: DetailTab) => void
  showTitle?: boolean
  onTakeNotes?: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const detail = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
  })
  const links = useQuery({
    queryKey: ['material-links', materialId],
    queryFn: () => getMaterialLinks(materialId),
  })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const states = useQuery({ queryKey: ['study-states'], queryFn: listStudyStates })

  const material = detail.data?.material
  const course = (courses.data ?? []).find((entry) => entry.id === material?.course_id)
  const status = states.data?.[String(materialId)]?.status ?? 'unread'
  const scopeNodeId =
    links.data?.find((link) => !link.is_course_level)?.node_id ?? links.data?.[0]?.node_id

  const setState = useMutation({
    mutationFn: (next: 'unread' | 'reading' | 'studied') => setStudyState(materialId, next),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['study-states'] })
    },
  })

  const exportMd = useMutation({
    mutationFn: async () => {
      const current = detail.data
      if (current === undefined) {
        return
      }
      const extraction = current.extraction
      if (extraction === null) {
        return
      }
      const resolved = await exportMarkdownWithDrawings(extraction.markdown, current.drawings)
      const safeTitle =
        current.material.title.replace(/[^\w\s-]/g, '').trim() || 'material'
      const blob = new Blob([resolved], { type: 'text/markdown' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `${safeTitle}.md`
      anchor.click()
      URL.revokeObjectURL(url)
    },
  })

  if (detail.isLoading) {
    return (
      <p className="text-muted-foreground p-8 text-sm">{t('library.loading')}</p>
    )
  }
  if (!material) {
    return <p className="text-muted-foreground p-8 text-sm">{t('library.materialMissing')}</p>
  }

  return (
    <>
      <header className="flex flex-wrap items-center gap-2">
        {showTitle ? <h1 className="text-lg font-semibold">{material.title}</h1> : null}
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-[11px]',
            material.status === 'ready' && 'bg-success/15 text-success',
            material.status === 'failed' && 'bg-danger/15 text-danger',
            (material.status === 'pending' || material.status === 'processing') &&
              'bg-warning/15 text-warning'
          )}
        >
          {material.status}
        </span>
        {course ? (
          <span className="bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[11px]">
            {course.title}
          </span>
        ) : null}
        {(links.data ?? []).map((link) => {
          const where =
            link.breadcrumb
              .slice(1)
              .map((crumb) => crumb.title)
              .join(' · ') || link.owner_title
          const label = link.via_folder
            ? t('library.assignedViaFolderChip', {
                folder: link.via_folder.name,
                where,
              })
            : t('library.assignedChip', { where })
          const chipTitle = link.via_folder
            ? `${link.via_folder.name} › ${link.breadcrumb.map((crumb) => crumb.title).join(' › ')}`
            : (link.rationale ?? link.breadcrumb.map((crumb) => crumb.title).join(' › '))
          const key = `${link.node_id}-${link.via_folder?.id ?? 'direct'}`
          return link.is_course_level ? (
            <span
              key={key}
              className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-[11px]"
              title={chipTitle}
            >
              {label}
            </span>
          ) : (
            <Link
              key={key}
              to="/courses/$courseId/n/$nodeId"
              params={{
                courseId: String(material.course_id),
                nodeId: String(link.node_id),
              }}
              className="bg-primary/10 text-primary hover:bg-primary/20 rounded-full px-2 py-0.5 text-[11px]"
              title={chipTitle}
            >
              {label}
            </Link>
          )
        })}
        {onTakeNotes ? (
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={onTakeNotes}
          >
            <NotebookPen className="size-3.5" aria-hidden />
            {t('library.takeNotes')}
          </Button>
        ) : null}
        <Button
          variant="outline"
          size="sm"
          disabled={!detail.data?.extraction || exportMd.isPending}
          onClick={() => exportMd.mutate()}
        >
          {exportMd.isPending ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : (
            <FileDown aria-hidden />
          )}
          {t('library.exportMarkdown')}
        </Button>
        <div
          className={cn('flex items-center gap-1', onTakeNotes ? undefined : 'ml-auto')}
          role="group"
          aria-label={t('library.studyState')}
        >
          {(['unread', 'reading', 'studied'] as const).map((option) => (
            <button
              key={option}
              type="button"
              className={cn(
                'rounded-full px-2 py-0.5 text-[11px]',
                status === option
                  ? 'bg-primary/15 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-subtle'
              )}
              disabled={setState.isPending}
              onClick={() => setState.mutate(option)}
            >
              {t(`library.studyState_${option}`)}
            </button>
          ))}
        </div>
      </header>

      <div className="border-border flex gap-1 border-b" role="tablist">
        {DETAIL_TABS.map((entry) => (
          <button
            key={entry}
            type="button"
            role="tab"
            aria-selected={activeTab === entry}
            className={cn(
              'rounded-t-md px-3 py-1.5 text-sm',
              activeTab === entry
                ? 'text-foreground border-primary border-b-2 font-medium'
                : 'text-muted-foreground hover:text-foreground'
            )}
            onClick={() => onTabChange(entry)}
          >
            {t(`library.tab_${entry.replaceAll('-', '_')}`)}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {activeTab === 'extraction' ? (
          <ExtractionView materialId={materialId} scopeNodeId={scopeNodeId} />
        ) : null}
        {activeTab === 'original' ? <OriginalView materialId={materialId} /> : null}
        {activeTab === 'side-by-side' ? (
          <div className="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t('library.original')}</CardTitle>
              </CardHeader>
              <CardContent>
                <OriginalView materialId={materialId} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t('library.extraction')}</CardTitle>
              </CardHeader>
              <CardContent>
                <ExtractionView materialId={materialId} scopeNodeId={scopeNodeId} />
              </CardContent>
            </Card>
          </div>
        ) : null}
      </div>
    </>
  )
}

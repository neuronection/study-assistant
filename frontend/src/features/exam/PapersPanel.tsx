import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import {
  BarChart3,
  FileText,
  KeyRound,
  Play,
  Plus,
  Printer,
  Trash2,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EmptyState } from '@/components/ui/empty-state'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { deletePaper, listPapers, type Paper } from '@/lib/api'
import { useCurrentOrigin } from '@/lib/origin'
import { useConfirm } from '@/lib/use-confirm'

import { PaperBuilderDialog } from './PaperBuilderDialog'
import { PaperReportDialog } from './PaperReportDialog'

export function PapersPanel({
  courseId,
  nodeId,
}: {
  courseId: string
  nodeId: string | null
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const queryClient = useQueryClient()
  const [builderOpen, setBuilderOpen] = useState(false)
  const [reporting, setReporting] = useState<Paper | null>(null)
  const [confirm, confirmElement] = useConfirm()

  const papers = useQuery({
    queryKey: ['papers', courseId],
    queryFn: () => listPapers(courseId),
  })
  const remove = useMutation({
    mutationFn: (paperId: string) => deletePaper(paperId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['papers', courseId] })
    },
  })

  const sit = (paper: Paper) =>
    navigate({
      to: '/quiz/$activityId',
      params: { activityId: paper.activity_id },
      search: { from, mode: 'exam' },
    })
  const print = (paper: Paper, mode: 'paper' | 'key') =>
    navigate({
      to: '/quiz/$activityId',
      params: { activityId: paper.activity_id },
      search: { from, print: mode },
    })

  const removePaper = async (paper: Paper) => {
    const ok = await confirm({
      title: t('exams.deleteTitle'),
      description: t('exams.deleteBody', { title: paper.title }),
      confirmLabel: t('common.delete'),
      cancelLabel: t('common.cancel'),
      destructive: true,
    })
    if (ok) {
      remove.mutate(paper.id)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <FileText className="size-4" aria-hidden />
          {t('exams.title')}
        </h2>
        <Button size="sm" onClick={() => setBuilderOpen(true)}>
          <Plus className="size-3.5" aria-hidden />
          {t('exams.newPaper')}
        </Button>
      </div>
      <ErrorBanner message={papers.isError ? (papers.error as Error).message : null} />
      <ErrorBanner message={remove.isError ? (remove.error as Error).message : null} />
      {papers.isLoading ? <Spinner /> : null}
      {papers.data && papers.data.length === 0 ? (
        <EmptyState title={t('exams.empty')} />
      ) : (
        <ul className="space-y-2">
          {(papers.data ?? []).map((paper) => (
            <li
              key={paper.id}
              className="border-border bg-surface flex flex-col gap-2 rounded-lg border px-4 py-3 text-sm sm:flex-row sm:items-center"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{paper.title}</p>
                <p className="text-muted-foreground text-xs">
                  {t('exams.meta', {
                    duration: paper.duration_min,
                    marks: paper.total_marks,
                    sections: paper.sections.length,
                  })}
                  {paper.attempt_count > 0 && paper.latest_percent !== null
                    ? ` · ${t('exams.latest', {
                        value: Math.round(paper.latest_percent * 100),
                      })}`
                    : ''}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1">
                <Button variant="outline" size="sm" onClick={() => sit(paper)}>
                  <Play className="size-3.5" aria-hidden />
                  {t('exams.sit')}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={t('exams.reportFor', { title: paper.title })}
                  disabled={paper.latest_attempt_id === null}
                  onClick={() => setReporting(paper)}
                >
                  <BarChart3 className="size-3.5" aria-hidden />
                  {t('exams.report')}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('exams.printPaper')}
                  onClick={() => print(paper, 'paper')}
                >
                  <Printer className="size-3.5" aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('exams.printKey')}
                  onClick={() => print(paper, 'key')}
                >
                  <KeyRound className="size-3.5" aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('exams.deleteFor', { title: paper.title })}
                  disabled={remove.isPending}
                  onClick={() => void removePaper(paper)}
                >
                  <Trash2 className="size-3.5" aria-hidden />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {builderOpen ? (
        <PaperBuilderDialog
          courseId={courseId}
          nodeId={nodeId}
          onClose={() => setBuilderOpen(false)}
          onCreated={() => setBuilderOpen(false)}
        />
      ) : null}
      {reporting ? (
        <PaperReportDialog paper={reporting} onClose={() => setReporting(null)} />
      ) : null}
      {confirmElement}
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { paperReport, type Paper } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

export function PaperReportDialog({ paper, onClose }: { paper: Paper; onClose: () => void }) {
  useCloseFloatings()
  const { t } = useTranslation()
  const report = useQuery({
    queryKey: ['paper-report', paper.id, paper.latest_attempt_id],
    queryFn: () => paperReport(paper.id, paper.latest_attempt_id),
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('exams.reportTitle')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="bg-surface border-border flex max-h-[88vh] w-full max-w-xl flex-col rounded-lg border shadow-[var(--as-shadow-3)]">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="text-sm font-semibold">{t('exams.reportTitle')}</h2>
          <button
            type="button"
            aria-label={t('chat.close')}
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground rounded p-1"
          >
            <X className="size-4" aria-hidden />
          </button>
        </header>
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          <div>
            <p className="text-muted-foreground text-xs">{paper.title}</p>
            {report.isLoading ? <Spinner /> : null}
            {report.data ? (
              <>
                <p className="mt-1 text-2xl font-semibold">
                  {report.data.earned} / {report.data.total}
                  <span className="text-muted-foreground ml-2 text-sm">
                    {t('exams.percent', { value: Math.round(report.data.percent * 100) })}
                  </span>
                  {report.data.grade ? (
                    <span className="bg-primary/10 text-primary ml-2 rounded-full px-2 py-0.5 text-xs">
                      {t('exams.grade', { grade: report.data.grade })}
                    </span>
                  ) : null}
                </p>
                <p className="text-muted-foreground text-xs">
                  {t('exams.answeredOf', {
                    answered: report.data.answered,
                    total: report.data.question_count,
                  })}
                </p>
              </>
            ) : null}
          </div>

          {report.data ? (
            <div className="space-y-2">
              {report.data.sections.map((section) => (
                <div key={section.id ?? section.title ?? 'section'} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span>{section.title}</span>
                    <span className="text-muted-foreground">
                      {section.earned} / {section.marks}
                    </span>
                  </div>
                  <div className="bg-subtle h-1.5 overflow-hidden rounded-full">
                    <div
                      className="bg-primary h-full rounded-full"
                      style={{
                        width: `${
                          section.marks ? Math.min(100, (section.earned / section.marks) * 100) : 0
                        }%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {report.data && report.data.topics.length > 0 ? (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold">{t('exams.lostTopics')}</h3>
              <ul className="space-y-1">
                {report.data.topics.map((topic) => (
                  <li
                    key={topic.concept_id}
                    className="border-border flex items-center justify-between rounded-md border px-2 py-1.5 text-xs"
                  >
                    <span className="truncate">{topic.name}</span>
                    <span className="text-danger shrink-0">
                      {t('exams.lostMarks', { marks: topic.lost })}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="text-muted-foreground text-[11px]">{t('exams.topicsHint')}</p>
            </div>
          ) : null}

          {report.data && report.data.attempt_id === null ? (
            <p className="text-muted-foreground text-xs">{t('exams.noAttempt')}</p>
          ) : null}
        </div>
        <footer className="border-border flex items-center justify-end gap-2 border-t px-4 py-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            <ArrowLeft className="size-3.5" aria-hidden />
            {t('common.back')}
          </Button>
        </footer>
      </div>
    </div>
  )
}

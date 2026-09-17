import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { CalendarClock, Check, Layers, Sparkles, Target } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { GenerateDialog } from '@/features/ai/GenerateDialog'
import { ReviewQueue } from '@/features/review/ReviewQueue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { SuccessBurst } from '@/components/motion/SuccessBurst'
import { Skeleton, SkeletonText } from '@/components/ui/skeleton'
import {
  getReviewDue,
  getStudyNext,
  reviewFlashcard,
  updatePlanItem,
  type StudyNext,
  type StudyWeakCell,
} from '@/lib/api'
import { cn } from '@/lib/utils'

type Phase = 'review' | 'plan' | 'practice'

function phasesFor(data: StudyNext): Phase[] {
  const phases: Phase[] = []
  if (data.due_cards > 0) {
    phases.push('review')
  }
  if (data.plan_rows.length > 0) {
    phases.push('plan')
  }
  if (data.weak_cells.length > 0) {
    phases.push('practice')
  }
  return phases
}

export function StudySessionPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const next = useQuery({ queryKey: ['study-next'], queryFn: () => getStudyNext() })
  const [phaseIndex, setPhaseIndex] = useState(0)
  const [startedAt] = useState(() => Date.now())
  const [reviewedCount, setReviewedCount] = useState(0)
  const [planDoneCount, setPlanDoneCount] = useState(0)
  const [practiceCell, setPracticeCell] = useState<StudyWeakCell | null>(null)
  const [practiceLaunched, setPracticeLaunched] = useState(false)

  const data = next.data
  const phases = useMemo(() => (data ? phasesFor(data) : []), [data])
  const done = next.isSuccess && phases.length === 0
  const wrappedUp = !next.isLoading && data !== undefined && phaseIndex >= phases.length
  const elapsedMinutes = Math.max(0, Math.round((Date.now() - startedAt) / 60000))
  const goalMet = data !== undefined && data.goal_done >= data.goal_target

  if (next.isLoading) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 p-8" aria-busy="true">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-3.5 w-72" />
        <SkeletonText lines={4} />
      </div>
    )
  }
  if (data === undefined) {
    return <p className="text-muted-foreground p-8 text-sm">{t('session.loadFailed')}</p>
  }

  if (done) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('session.allClearTitle')}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground text-sm">{t('session.allClearBody')}</p>
            <Button className="mt-3" onClick={() => void navigate({ to: '/' })}>
              {t('session.backHome')}
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (wrappedUp) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        {goalMet ? <SuccessBurst size={48} /> : null}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('session.wrapUpTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <ul className="text-muted-foreground space-y-1 text-sm">
              <li>
                {t('session.wrapReviewed', { count: reviewedCount })}
              </li>
              <li>
                {t('session.wrapPlanned', { count: planDoneCount })}
              </li>
              <li>
                {t('session.wrapPractice', {
                  count: practiceLaunched ? 1 : 0,
                })}
              </li>
              <li>{t('session.wrapTime', { count: elapsedMinutes })}</li>
            </ul>
            <p className="text-xs">
              {t('session.goalProgress', {
                done: data.goal_done,
                target: data.goal_target,
              })}
            </p>
            <Button onClick={() => void navigate({ to: '/' })}>
              {t('session.backHome')}
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  const phase = phases[phaseIndex]
  const advance = () => setPhaseIndex((index) => index + 1)

  return (
    <div className="mx-auto max-w-2xl p-8">
      <header className="mb-5">
        <h1 className="text-2xl font-semibold">{t('session.title')}</h1>
        <ol className="text-muted-foreground mt-2 flex items-center gap-2 text-xs" aria-label={t('session.phases')}>
          {phases.map((entry, index) => (
            <li
              key={entry}
              className={cn(
                'rounded-full px-2 py-0.5',
                index === phaseIndex && 'bg-primary/10 text-primary font-medium',
                index < phaseIndex && 'line-through opacity-60',
              )}
            >
              {t(`session.phase.${entry}`)}
            </li>
          ))}
        </ol>
      </header>

      {phase === 'review' ? (
        <ReviewPhase
          onReviewed={(count) => setReviewedCount(count)}
          onComplete={advance}
        />
      ) : phase === 'plan' ? (
        <PlanPhase
          rows={data.plan_rows}
          onDone={() => setPlanDoneCount((count) => count + 1)}
          onComplete={advance}
        />
      ) : (
        <PracticePhase
          cells={data.weak_cells}
          cell={practiceCell}
          onOpen={(cell) => {
            setPracticeCell(cell)
            setPracticeLaunched(true)
          }}
          onClose={() => setPracticeCell(null)}
          onComplete={advance}
        />
      )}

      <div className="mt-5 flex justify-end">
        <Button variant="ghost" size="sm" onClick={advance}>
          {t('session.skip')}
        </Button>
      </div>
    </div>
  )
}

function ReviewPhase({
  onReviewed,
  onComplete,
}: {
  onReviewed: (count: number) => void
  onComplete: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const due = useQuery({ queryKey: ['review-due'], queryFn: () => getReviewDue() })
  const review = useMutation({
    mutationFn: ({ cardId, rating }: { cardId: number; rating: number }) =>
      reviewFlashcard(cardId, rating),
  })
  const [answered, setAnswered] = useState(0)

  const cards = useMemo(
    () => (due.data?.groups ?? []).flatMap((group) => group.cards),
    [due.data],
  )
  const totalDue = due.data?.total_due ?? 0

  if (due.isLoading) {
    return (
      <Card aria-busy="true">
        <CardContent className="p-6">
          <SkeletonText lines={3} />
        </CardContent>
      </Card>
    )
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Layers className="size-4" aria-hidden />
          {t('session.reviewTitle', { count: totalDue })}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ReviewQueue
          cards={cards}
          total={totalDue}
          busy={review.isPending}
          onRate={(card, rating) => {
            setAnswered((count) => count + 1)
            onReviewed(answered + 1)
            review.mutate({ cardId: card.id, rating })
          }}
          completion={
            <div className="py-6 text-center">
              <p className="text-muted-foreground mb-3 text-sm">{t('session.reviewDone')}</p>
              <Button
                onClick={() => {
                  void queryClient.invalidateQueries({ queryKey: ['study-next'] })
                  onComplete()
                }}
              >
                {t('session.continue')}
              </Button>
            </div>
          }
        />
      </CardContent>
    </Card>
  )
}

function PlanPhase({
  rows,
  onDone,
  onComplete,
}: {
  rows: StudyNext['plan_rows']
  onDone: () => void
  onComplete: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [doneIds, setDoneIds] = useState<number[]>([])
  const complete = useMutation({
    mutationFn: (row: StudyNext['plan_rows'][number]) =>
      updatePlanItem(row.course_id, row.item_id, { done: true }),
    onSuccess: async (_data, row) => {
      setDoneIds((ids) => [...ids, row.item_id])
      onDone()
      await queryClient.invalidateQueries({ queryKey: ['study-next'] })
      await queryClient.invalidateQueries({ queryKey: ['plan-upcoming'] })
    },
  })
  const snooze = useMutation({
    mutationFn: (row: StudyNext['plan_rows'][number]) => {
      const due = new Date(`${row.due_date}T00:00:00`)
      due.setDate(due.getDate() + 1)
      return updatePlanItem(row.course_id, row.item_id, {
        due_date: due.toISOString().slice(0, 10),
      })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['study-next'] })
    },
  })
  const remaining = rows.filter((row) => !doneIds.includes(row.item_id))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <CalendarClock className="size-4" aria-hidden />
          {t('session.planTitle', { count: remaining.length })}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {remaining.length === 0 ? (
          <div className="py-4 text-center">
            <p className="text-muted-foreground mb-3 text-sm">{t('session.planDone')}</p>
            <Button onClick={onComplete}>{t('session.continue')}</Button>
          </div>
        ) : (
          remaining.map((row) => (
            <div
              key={row.item_id}
              className="border-border flex items-center gap-2 rounded-lg border px-3 py-2"
            >
              <CalendarClock
                className={cn(
                  'size-3.5 shrink-0',
                  row.overdue ? 'text-danger' : 'text-muted-foreground',
                )}
                aria-hidden
              />
              <span className="text-muted-foreground shrink-0 text-xs">{row.due_date}</span>
              <span className="min-w-0 flex-1 truncate text-sm">{row.title}</span>
              <span className="text-muted-foreground hidden shrink-0 truncate text-xs sm:block">
                {row.course_title}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={complete.isPending}
                onClick={() => complete.mutate(row)}
              >
                <Check className="size-3.5" aria-hidden />
                {t('session.planCheck')}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={snooze.isPending}
                onClick={() => snooze.mutate(row)}
              >
                {t('session.planSnooze')}
              </Button>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  )
}

function PracticePhase({
  cells,
  cell,
  onOpen,
  onClose,
  onComplete,
}: {
  cells: StudyWeakCell[]
  cell: StudyWeakCell | null
  onOpen: (cell: StudyWeakCell) => void
  onClose: () => void
  onComplete: () => void
}) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Target className="size-4" aria-hidden />
          {t('session.practiceTitle', { count: cells.length })}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {cells.map((weak) => (
          <div
            key={`${weak.course_id}-${weak.concept}-${weak.skill}`}
            className="border-border flex items-center gap-3 rounded-lg border px-3 py-2.5"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {t('session.practiceCell', { concept: weak.concept })}
                <span className="text-muted-foreground font-normal"> · {weak.skill}</span>
              </p>
              <p className="text-muted-foreground text-xs">
                {t('session.practiceEvidence', {
                  n: weak.n,
                  percent: Math.round(weak.accuracy * 100),
                })}
                {weak.course_title ? ` · ${weak.course_title}` : ''}
              </p>
            </div>
            <Button size="sm" variant="outline" onClick={() => onOpen(weak)}>
              <Sparkles className="size-3.5" aria-hidden />
              {t('session.practiceOpen')}
            </Button>
          </div>
        ))}
        <div className="flex justify-center pt-2">
          <Button onClick={onComplete}>{t('session.continue')}</Button>
        </div>
        {cell !== null ? (
          <GenerateDialog
            task="quiz"
            courseId={cell.course_id}
            initial={{ topic: cell.concept, difficulty: 2 }}
            onClose={onClose}
            onSuccess={() => onClose()}
          />
        ) : null}
      </CardContent>
    </Card>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Loader2 } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Skeleton, SkeletonText } from '@/components/ui/skeleton'
import {
  getReviewDue,
  reviewFlashcard,
  type DueCourseGroup,
  type FlashcardInfo,
} from '@/lib/api'
import { useStudySession } from '@/lib/use-study-session'
import { cn } from '@/lib/utils'

import { ReviewQueue } from './ReviewQueue'

function CourseChip({ group }: { group: DueCourseGroup }) {
  return (
    <span
      className={cn(
        'text-muted-foreground bg-subtle inline-flex max-w-48 shrink-0 items-center gap-1.5 truncate rounded-full px-2 py-0.5 text-[11px] font-medium'
      )}
      style={
        group.course_color
          ? { color: group.course_color, backgroundColor: `${group.course_color}1a` }
          : undefined
      }
    >
      <span
        className="size-1.5 shrink-0 rounded-full"
        style={{ backgroundColor: group.course_color ?? 'currentColor' }}
        aria-hidden
      />
      <span className="truncate">{group.course_title}</span>
    </span>
  )
}

export function ReviewPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const due = useQuery({ queryKey: ['review-due'], queryFn: () => getReviewDue() })

  useStudySession({ kind: 'review', entityRef: 'review:page' })

  const review = useMutation({
    mutationFn: ({ cardId, rating }: { cardId: number; rating: number }) =>
      reviewFlashcard(cardId, rating),
  })

  const cards = useMemo(
    () => (due.data?.groups ?? []).flatMap((group) => group.cards),
    [due.data]
  )
  const groupByCardId = useMemo(() => {
    const map = new Map<number, DueCourseGroup>()
    for (const group of due.data?.groups ?? []) {
      for (const card of group.cards) {
        map.set(card.id, group)
      }
    }
    return map
  }, [due.data])

  const totalDue = due.data?.total_due ?? 0
  const allClear = due.isSuccess && totalDue === 0

  const loadNextBatch = () => {
    void queryClient.invalidateQueries({ queryKey: ['review-due'] })
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      <header className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">{t('review.title')}</h1>
          <p className="text-muted-foreground mt-0.5 text-sm">
            {due.isLoading
              ? t('review.loading')
              : allClear
                ? t('review.allClear')
                : t('review.subtitle', { count: totalDue })}
          </p>
        </div>
        {review.isPending ? (
          <Loader2 className="text-muted-foreground size-4 animate-spin" aria-hidden />
        ) : null}
      </header>

      {due.isLoading ? (
        <div aria-busy="true" className="space-y-3 py-4">
          <div className="border-border rounded-xl border p-6">
            <SkeletonText lines={2} />
            <div className="mt-4 flex justify-center gap-2">
              {[0, 1, 2, 3].map((index) => (
                <Skeleton key={index} className="h-8 w-14 rounded-md" />
              ))}
            </div>
          </div>
          <Skeleton className="h-1.5 w-full rounded-full" />
        </div>
      ) : allClear ? (
        <div className="border-success/40 bg-success/5 flex flex-col items-center gap-2 rounded-xl border p-10 text-center">
          <CheckCircle2 className="text-success size-10" aria-hidden />
          <p className="text-lg font-semibold">{t('review.allClearTitle')}</p>
          <p className="text-muted-foreground text-sm">{t('review.allClearBody')}</p>
        </div>
      ) : (
        <ReviewQueue
          key={cards.map((card) => card.id).join(',')}
          cards={cards}
          total={totalDue}
          busy={review.isPending}
          onRate={(card: FlashcardInfo, rating: number) =>
            review.mutate({ cardId: card.id, rating })
          }
          cardHeader={(card) => {
            const group = groupByCardId.get(card.id)
            return group ? <CourseChip group={group} /> : null
          }}
          completion={
            <div className="border-border flex flex-col items-center gap-3 rounded-xl border border-dashed p-10 text-center">
              <p className="text-muted-foreground text-sm">{t('review.batchDone')}</p>
              <Button variant="outline" size="sm" onClick={loadNextBatch}>
                {t('review.loadNext')}
              </Button>
            </div>
          }
        />
      )}
    </div>
  )
}

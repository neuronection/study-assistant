import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Filter, Loader2, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { OneTimeTip } from '@/components/OneTimeTip'
import { Skeleton, SkeletonText } from '@/components/ui/skeleton'
import {
  createReviewFilter,
  deleteReviewFilter,
  getReviewDue,
  listReviewFilters,
  previewReview,
  type DueCourseGroup,
  type FlashcardInfo,
} from '@/lib/api'
import { useStudySession } from '@/lib/use-study-session'
import { cn } from '@/lib/utils'
import { submitReview } from '@/lib/review-submit'
import { recordFirstActivation } from '@/lib/activation-events'

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
  const [filterId, setFilterId] = useState<string | null>(null)
  const [ahead, setAhead] = useState(false)
  const [days, setDays] = useState(7)
  const [reschedule, setReschedule] = useState(false)
  const [saveName, setSaveName] = useState('')
  const filters = useQuery({ queryKey: ['review-filters'], queryFn: listReviewFilters })
  const due = useQuery({
    queryKey: ['review-due', filterId, ahead, days],
    queryFn: () =>
      getReviewDue(
        filterId !== null
          ? { filterId }
          : { includeNotDue: ahead, dueWindowDays: days }
      ),
  })

  useStudySession({ kind: 'review', entityRef: 'review:page' })

  const preview = due.data?.preview === true
  const review = useMutation({
    mutationFn: async ({
      cardId,
      rating,
    }: {
      cardId: string
      rating: number
    }) => {
      if (preview && !reschedule) {
        await previewReview(cardId, rating)
        return 'preview'
      }
      return submitReview(cardId, rating)
    },
    onSuccess: async (result) => {
      recordFirstActivation('first_review', { surface: 'review' })
      if (result !== 'preview') {
        await queryClient.invalidateQueries({ queryKey: ['review-due'] })
      }
    },
  })
  const saveFilter = useMutation({
    mutationFn: () =>
      createReviewFilter({
        name: saveName.trim(),
        include_not_due: ahead,
        due_window_days: days,
        limit: 50,
        sort_order: 'due',
      }),
    onSuccess: async (created) => {
      setSaveName('')
      setFilterId(created.id)
      await queryClient.invalidateQueries({ queryKey: ['review-filters'] })
    },
  })
  const removeFilter = useMutation({
    mutationFn: (id: string) => deleteReviewFilter(id),
    onSuccess: async () => {
      setFilterId(null)
      await queryClient.invalidateQueries({ queryKey: ['review-filters'] })
    },
  })

  const cards = useMemo(
    () => (due.data?.groups ?? []).flatMap((group) => group.cards),
    [due.data]
  )
  const groupByCardId = useMemo(() => {
    const map = new Map<string, DueCourseGroup>()
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

      <OneTimeTip id="review-buttons">{t('tips.review')}</OneTimeTip>

      <div className="mb-4 flex flex-wrap items-center gap-1.5" role="group" aria-label={t('review.filters')}>
        <button
          type="button"
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs ${
            filterId === null && !ahead ? 'border-primary text-primary bg-primary/10' : 'border-border'
          }`}
          onClick={() => {
            setFilterId(null)
            setAhead(false)
          }}
        >
          <Filter className="size-3" aria-hidden />
          {t('review.filterDue')}
        </button>
        <button
          type="button"
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs ${
            filterId === null && ahead ? 'border-primary text-primary bg-primary/10' : 'border-border'
          }`}
          onClick={() => {
            setFilterId(null)
            setAhead(true)
          }}
        >
          <Sparkles className="size-3" aria-hidden />
          {t('review.filterAhead', { days })}
        </button>
        <label className="text-muted-foreground inline-flex items-center gap-1 text-xs">
          {t('review.days')}
          <input
            type="number"
            min={1}
            max={90}
            value={days}
            onChange={(event) => setDays(Math.max(1, Math.min(90, Number(event.target.value))))}
            className="bg-surface border-border w-14 rounded-md border px-1.5 py-0.5"
            aria-label={t('review.days')}
          />
        </label>
        {filters.data?.length ? (
          <select
            value={filterId ?? ''}
            onChange={(event) => setFilterId(event.target.value || null)}
            className="bg-surface border-border rounded-md border px-2 py-1 text-xs"
            aria-label={t('review.savedFilters')}
          >
            <option value="">{t('review.savedFiltersPlaceholder')}</option>
            {filters.data.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.name}
              </option>
            ))}
          </select>
        ) : null}
        <input
          value={saveName}
          onChange={(event) => setSaveName(event.target.value)}
          placeholder={t('review.saveFilterPlaceholder')}
          aria-label={t('review.saveFilterPlaceholder')}
          className="bg-surface border-border w-36 rounded-md border px-2 py-1 text-xs"
        />
        <button
          type="button"
          disabled={saveName.trim().length === 0 || saveFilter.isPending}
          onClick={() => saveFilter.mutate()}
          className="border-border rounded-md border px-2 py-1 text-xs disabled:opacity-50"
        >
          {t('review.saveFilter')}
        </button>
        {filterId !== null ? (
          <button
            type="button"
            onClick={() => removeFilter.mutate(filterId)}
            className="text-danger rounded-md border border-current/30 px-2 py-1 text-xs"
          >
            {t('review.deleteFilter')}
          </button>
        ) : null}
        {preview ? (
          <label className="text-muted-foreground ml-auto inline-flex items-center gap-1 text-xs">
            <input
              type="checkbox"
              checked={reschedule}
              onChange={(event) => setReschedule(event.target.checked)}
            />
            {t('review.reschedule')}
          </label>
        ) : null}
      </div>
      {preview ? (
        <p className="border-warning/40 bg-warning/5 text-warning mb-3 rounded-md border px-3 py-1.5 text-xs">
          {reschedule ? t('review.rescheduleOn') : t('review.previewChip')}
        </p>
      ) : null}
      {due.data?.capped ? (
        <p className="border-warning/40 bg-warning/5 text-warning mb-3 rounded-md border px-3 py-1.5 text-xs">
          {t('review.capped', { count: due.data.remaining_today ?? 0 })}
        </p>
      ) : null}

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

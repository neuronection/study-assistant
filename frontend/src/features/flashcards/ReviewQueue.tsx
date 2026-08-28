import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, RotateCcw, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { dueFlashcards, reviewFlashcard, type FlashcardInfo } from '@/lib/api'

const RATINGS = [
  { rating: 1, labelKey: 'cards.rateAgain' },
  { rating: 2, labelKey: 'cards.rateHard' },
  { rating: 3, labelKey: 'cards.rateGood' },
  { rating: 4, labelKey: 'cards.rateEasy' },
] as const

export function ReviewQueue({
  courseId,
  nodeId,
}: {
  courseId?: number
  nodeId?: number
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const due = useQuery({
    queryKey: ['cards-due', courseId ?? null, nodeId ?? null],
    queryFn: () => dueFlashcards(20, courseId, nodeId),
  })
  const [revealed, setRevealed] = useState<Record<number, boolean>>({})
  const [lastResult, setLastResult] = useState<string | null>(null)

  const review = useMutation({
    mutationFn: ({ cardId, rating }: { cardId: number; rating: number }) =>
      reviewFlashcard(cardId, rating),
    onSuccess: async (result) => {
      setLastResult(t('cards.nextIn', { days: result.interval_days }))
      await queryClient.invalidateQueries({ queryKey: ['cards-due'] })
      await queryClient.invalidateQueries({ queryKey: ['cards'] })
    },
  })

  const card: FlashcardInfo | undefined = (due.data ?? [])[0]

  if (due.isLoading) {
    return <Loader2 className="animate-spin" aria-label={t('library.loading')} />
  }
  if (!card) {
    return (
      <p className="text-muted-foreground py-8 text-center text-sm">{t('cards.queueEmpty')}</p>
    )
  }
  const isRevealed = revealed[card.id] ?? false

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div className="text-muted-foreground flex items-center justify-between text-xs">
          <span>{t('cards.dueCount', { count: (due.data ?? []).length })}</span>
          {card.state ? <span>{t(`cards.state.${card.state}`)}</span> : <span>{t('cards.state.new')}</span>}
        </div>
        <div className="min-h-16 text-base">
          <BlockRenderer blocks={card.front as Block[]} />
        </div>
        {isRevealed ? (
          <div className="border-primary/40 bg-primary/5 rounded-lg border p-3 text-sm">
            <BlockRenderer blocks={card.back as Block[]} />
          </div>
        ) : null}
        {lastResult ? <p className="text-muted-foreground text-xs">{lastResult}</p> : null}
        <div className="flex flex-wrap justify-between gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setRevealed((current) => ({ ...current, [card.id]: true }))}
          >
            <RotateCcw aria-hidden />
            {t('cards.reveal')}
          </Button>
          {isRevealed ? (
            <div className="flex gap-2">
              {RATINGS.map((entry) => (
                <Button
                  key={entry.rating}
                  variant={entry.rating === 1 ? 'outline' : 'default'}
                  size="sm"
                  disabled={review.isPending}
                  onClick={() =>
                    review.mutate({ cardId: card.id, rating: entry.rating })
                  }
                >
                  {entry.rating <= 2 ? <ThumbsDown aria-hidden /> : <ThumbsUp aria-hidden />}
                  {t(entry.labelKey)}
                </Button>
              ))}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

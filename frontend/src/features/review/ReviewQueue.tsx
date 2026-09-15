import { AnimatePresence, motion } from 'framer-motion'
import { useMotionPresets } from '@/lib/motion'
import { Loader2, RotateCcw, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import type { Block } from '@/components/blocks/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { FlashcardInfo } from '@/lib/api'

/** Visible hint for the spacebar reveal shortcut. */
const SPACE_HINT = '\u2423'

export const REVIEW_RATINGS = [
  { rating: 1, labelKey: 'cards.rateAgain' },
  { rating: 2, labelKey: 'cards.rateHard' },
  { rating: 3, labelKey: 'cards.rateGood' },
  { rating: 4, labelKey: 'cards.rateEasy' },
] as const

/**
 * Course-agnostic review flow: a queue of cards in, ratings out.
 * The Practice tab passes one course's due cards; the /review page passes the
 * cross-course aggregate (with a `cardHeader` course chip).
 */
export function ReviewQueue({
  cards,
  total,
  busy,
  onRate,
  cardHeader,
  toolbar,
  completion,
}: {
  cards: FlashcardInfo[]
  /** Total due across the scope (defaults to the queue length — used when `cards` is a first batch). */
  total?: number
  busy?: boolean
  onRate: (card: FlashcardInfo, rating: number) => void
  cardHeader?: (card: FlashcardInfo) => ReactNode
  toolbar?: ReactNode
  completion?: ReactNode
}) {
  const { t } = useTranslation()
  const presets = useMotionPresets()
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const [reviewed, setReviewed] = useState(0)

  const card: FlashcardInfo | undefined = cards[index]

  const rate = useCallback(
    (rating: number) => {
      if (!card || busy) {
        return
      }
      setReviewed((current) => current + 1)
      onRate(card, rating)
      setIndex((current) => current + 1)
      setRevealed(false)
    },
    [busy, card, onRate]
  )

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.isContentEditable ||
          ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) ||
          target.closest('button, a, [role="button"]') !== null)
      ) {
        return
      }
      if (!card) {
        return
      }
      if (event.key === ' ' || event.key === 'Enter') {
        event.preventDefault()
        setRevealed(true)
        return
      }
      const rating = Number(event.key)
      if (rating >= 1 && rating <= 4) {
        event.preventDefault()
        rate(rating)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [rate, card])

  if (cards.length === 0) {
    return completion ?? (
      <p className="text-muted-foreground py-8 text-center text-sm">
        {t('cards.queueEmpty')}
      </p>
    )
  }

  const scopeTotal = total ?? cards.length
  const progress = Math.min(100, Math.round((reviewed / Math.max(1, scopeTotal)) * 100))

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="bg-subtle h-1.5 flex-1 overflow-hidden rounded-full">
          <motion.div
            className="bg-primary h-full rounded-full"
            animate={{ width: `${progress}%` }}
            transition={presets.route.transition}
          />
        </div>
        <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
          {t('cards.progress', { reviewed, total: scopeTotal })}
        </span>
      </div>
      {toolbar ? <div className="flex justify-end">{toolbar}</div> : null}
      <AnimatePresence mode="popLayout" initial={false}>
        {card === undefined ? (
          completion ?? (
            <motion.p
              key="done"
              {...presets.enter}
              className="text-muted-foreground py-8 text-center text-sm"
            >
              {t('cards.batchDone')}
            </motion.p>
          )
        ) : (
          <motion.div
            key={card.id}
            {...presets.step}
            layout
          >
            <Card>
              <CardContent className="space-y-4 p-6">
                <div className="text-muted-foreground flex items-center justify-between text-xs">
                  {cardHeader ? <span className="min-w-0">{cardHeader(card)}</span> : <span />}
                  <span className="flex shrink-0 items-center gap-2">
                    {card.state ? (
                      <span>{t(`cards.state.${card.state}`)}</span>
                    ) : (
                      <span>{t('cards.state.new')}</span>
                    )}
                  </span>
                </div>
                <div className="min-h-16 text-base">
                  <BlockRenderer blocks={card.front as Block[]} />
                </div>
                <AnimatePresence initial={false}>
                  {revealed ? (
                    <motion.div
                      {...presets.collapse}
                      className="border-primary/40 bg-primary/5 overflow-hidden rounded-lg border p-3 text-sm"
                    >
                      <BlockRenderer blocks={card.back as Block[]} />
                    </motion.div>
                  ) : null}
                </AnimatePresence>
                <div className="flex flex-wrap justify-between gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setRevealed(true)}
                    disabled={revealed}
                  >
                    <RotateCcw aria-hidden />
                    {t('cards.reveal')}
                    <kbd className="text-muted-foreground ml-1 rounded border border-border px-1 text-[10px]">
                      {SPACE_HINT}
                    </kbd>
                  </Button>
                  {revealed ? (
                    <div className="flex gap-2">
                      {REVIEW_RATINGS.map((entry) => (
                        <Button
                          key={entry.rating}
                          variant={entry.rating === 1 ? 'outline' : 'default'}
                          size="sm"
                          disabled={busy}
                          onClick={() => rate(entry.rating)}
                          className={cn('relative')}
                        >
                          {entry.rating <= 2 ? (
                            <ThumbsDown aria-hidden />
                          ) : (
                            <ThumbsUp aria-hidden />
                          )}
                          {t(entry.labelKey)}
                          <kbd className="text-muted-foreground absolute -top-1.5 -right-1.5 rounded-full border border-border bg-surface px-1 text-[9px] leading-3">
                            {entry.rating}
                          </kbd>
                        </Button>
                      ))}
                    </div>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
      {busy ? (
        <Loader2 className="text-muted-foreground animate-spin" aria-hidden />
      ) : null}
    </div>
  )
}

import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { SkeletonText } from '@/components/ui/skeleton'
import { getMaterial } from '@/lib/api'
import { useMediaQuery } from '@/lib/use-media-query'

export function MaterialHoverCard({
  materialId,
  openDelay = 150,
  children,
}: {
  materialId: number
  openDelay?: number
  children: ReactNode
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const coarse = useMediaQuery('(pointer: coarse)')
  const detail = useQuery({
    queryKey: ['material', materialId],
    queryFn: () => getMaterial(materialId),
    enabled: open && !coarse,
    staleTime: 5 * 60_000,
  })

  if (coarse) {
    return <>{children}</>
  }
  const card = detail.data?.index_card ?? null
  return (
    <HoverCard openDelay={openDelay} open={open} onOpenChange={setOpen}>
      <HoverCardTrigger asChild>{children}</HoverCardTrigger>
      <HoverCardContent className="w-80">
        <p className="text-sm font-medium">{detail.data?.material.title}</p>
        {detail.isPending ? (
          <div className="mt-2" aria-busy="true">
            <SkeletonText lines={3} />
          </div>
        ) : card ? (
          <>
            {card.summary ? (
              <p className="text-muted-foreground mt-1 line-clamp-3 text-xs">
                {card.summary}
              </p>
            ) : null}
            {(card.topics ?? []).length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1">
                {card.topics.slice(0, 6).map((topic) => (
                  <span
                    key={topic}
                    className="bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[10px]"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            ) : null}
            {card.reading_minutes !== null || card.difficulty !== null ? (
              <p className="text-muted-foreground mt-2 text-[10px]">
                {card.reading_minutes !== null
                  ? t('library.previewReading', { count: card.reading_minutes })
                  : null}
                {card.reading_minutes !== null && card.difficulty !== null ? ' · ' : null}
                {card.difficulty !== null
                  ? t('library.previewDifficulty', { n: card.difficulty })
                  : null}
              </p>
            ) : null}
          </>
        ) : detail.isSuccess ? (
          <p className="text-muted-foreground mt-1 text-xs">
            {t('library.previewNoSummary')}
          </p>
        ) : null}
      </HoverCardContent>
    </HoverCard>
  )
}

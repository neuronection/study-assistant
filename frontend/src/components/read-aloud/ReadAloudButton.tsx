import { Pause, Play, Square } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { useReadAloud } from '@/lib/readAloud'

export function ReadAloudButton({
  markdown,
  className,
}: {
  markdown: string
  className?: string
}) {
  const { t } = useTranslation()
  const { engine, speaking, active, rate, play, stop, cycleRate } = useReadAloud(markdown)
  if (engine === null) return null
  return (
    <span className={`inline-flex items-center gap-1 ${className ?? ''}`}>
      <Button
        variant="ghost"
        size="icon"
        title={
          speaking ? t('readAloud.stop') : t('readAloud.play')
        }
        aria-label={
          speaking ? t('readAloud.stop') : t('readAloud.play')
        }
        onClick={play}
      >
        {speaking ? <Pause className="size-4" aria-hidden /> : <Play className="size-4" aria-hidden />}
      </Button>
      {active ? (
        <>
          <Button
            variant="ghost"
            size="icon"
            title={t('readAloud.stop')}
            aria-label={t('readAloud.stop')}
            onClick={stop}
          >
            <Square className="size-3.5" aria-hidden />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="px-2 text-xs"
            title={t('readAloud.speed')}
            aria-label={t('readAloud.speed')}
            onClick={cycleRate}
          >
            {rate}×
          </Button>
        </>
      ) : null}
    </span>
  )
}

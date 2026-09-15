import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { FormModal, Input } from '@neuronection/assistant-ui'
import { useCloseFloatings } from '@/lib/ui-overlays'
import { cn } from '@/lib/utils'

const PRESETS = [30, 60, 90, 120]

/**
 * Quiz time-limit editor (plan 49-C): presets 30/60/90/120 min, custom, or
 * no limit. The limit is what the quiz carries — exam mode is orthogonal.
 */
export function TimeLimitDialog({
  title,
  currentSec,
  onConfirm,
  onClose,
}: {
  title: string
  currentSec: number | null
  onConfirm: (timeLimitSec: number | null) => void
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const [minutes, setMinutes] = useState<number | null>(
    currentSec === null ? null : Math.round(currentSec / 60)
  )
  const [custom, setCustom] = useState<number | null>(
    currentSec !== null && !PRESETS.includes(Math.round(currentSec / 60))
      ? Math.max(1, Math.round(currentSec / 60))
      : null
  )

  useEffect(() => {
    setMinutes(currentSec === null ? null : Math.round(currentSec / 60))
  }, [currentSec])

  const pendingLabel = (() => {
    if (minutes === null) {
      return t('generate.timeLimitNone')
    }
    if (custom !== null) {
      return t('generate.timeLimitOption', { minutes: custom })
    }
    return t('generate.timeLimitOption', { minutes: minutes ?? 0 })
  })()

  return (
    <FormModal
      open
      onOpenChange={(next) => {
        if (!next) {
          onClose()
        }
      }}
      title={title}
      description={pendingLabel}
      submitLabel={t('common.apply')}
      cancelLabel={t('common.cancel')}
      onSubmit={() => onConfirm(minutes === null ? null : (minutes ?? 0) * 60)}
      size="sm"
    >
      <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label={title}>
        <button
          type="button"
          role="radio"
          aria-checked={minutes === null}
          className={cn(
            'border-border hover:border-primary/50 rounded-lg border px-2 py-2 text-xs transition-colors',
            minutes === null && 'border-primary bg-primary/10 font-medium'
          )}
          onClick={() => setMinutes(null)}
        >
          {t('generate.timeLimitNone')}
        </button>
        {PRESETS.map((preset) => (
          <button
            key={preset}
            type="button"
            role="radio"
            aria-checked={!custom && minutes === preset}
            className={cn(
              'border-border hover:border-primary/50 rounded-lg border px-2 py-2 text-xs transition-colors',
              !custom && minutes === preset && 'border-primary bg-primary/10 font-medium'
            )}
            onClick={() => {
              setCustom(null)
              setMinutes(preset)
            }}
          >
            {t('generate.timeLimitOption', { minutes: preset })}
          </button>
        ))}
        <div
          className={cn(
            'border-border col-span-2 flex items-center gap-2 rounded-lg border px-2 py-1.5',
            custom !== null && 'border-primary bg-primary/10'
          )}
        >
          <button
            type="button"
            role="radio"
            aria-checked={custom !== null}
            className="text-muted-foreground hover:text-foreground flex-1 text-left text-xs"
            onClick={() => {
              setCustom(custom ?? 25)
              setMinutes(custom ?? 25)
            }}
          >
            {t('generate.timeLimitCustom')}
          </button>
          {custom !== null ? (
            <Input
              type="number"
              min={1}
              max={240}
              value={custom}
              aria-label={t('generate.timeLimitCustom')}
              onChange={(event) => {
                const value = Math.min(240, Math.max(1, Number(event.target.value) || 1))
                setCustom(value)
                setMinutes(value)
              }}
              className="w-20 text-center"
            />
          ) : null}
        </div>
      </div>
    </FormModal>
  )
}

import { Check } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { blobUrl, type DiagramHotspot, type ExerciseStepInput } from '@/lib/api'
import { cn } from '@/lib/utils'

export interface DiagramPlacement {
  hotspot_id: string
  label: string
}

export function DiagramLabelInput({
  input,
  value,
  onChange,
  disabled,
}: {
  input: ExerciseStepInput
  value: DiagramPlacement[] | null
  onChange: (next: DiagramPlacement[]) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const [selected, setSelected] = useState<string | null>(null)
  const placements = value ?? []
  const placed = new Map(placements.map((entry) => [entry.hotspot_id, entry.label]))
  const allLabels = input.labels ?? []

  const assign = (hotspot: DiagramHotspot) => {
    if (disabled || selected === null) {
      return
    }
    onChange([
      ...placements.filter((entry) => entry.hotspot_id !== hotspot.id),
      { hotspot_id: hotspot.id, label: selected },
    ])
    setSelected(null)
  }

  return (
    <div className="space-y-3">
      <div className="relative overflow-hidden rounded-md border border-border bg-subtle">
        {input.image_sha ? (
          <img
            src={blobUrl(input.image_sha)}
            alt={t('exercises.diagramAlt')}
            className="block w-full select-none"
            draggable={false}
          />
        ) : null}
        {(input.hotspots ?? []).map((hotspot, index) => {
          const label = placed.get(hotspot.id)
          return (
            <button
              key={hotspot.id}
              type="button"
              disabled={disabled}
              aria-label={
                label
                  ? t('exercises.diagramPlaced', { number: index + 1, label })
                  : t('exercises.diagramHotspot', { number: index + 1 })
              }
              onClick={() => assign(hotspot)}
              className={cn(
                'absolute flex items-center justify-center rounded-sm border-2 text-[11px] font-semibold transition-colors',
                label
                  ? 'border-success/70 bg-success/15 text-success'
                  : 'border-primary/60 bg-primary/10 text-primary hover:bg-primary/20'
              )}
              style={{
                left: `${hotspot.x * 100}%`,
                top: `${hotspot.y * 100}%`,
                width: `${hotspot.w * 100}%`,
                height: `${hotspot.h * 100}%`,
              }}
            >
              {label ? <Check className="size-3.5" aria-hidden /> : index + 1}
            </button>
          )
        })}
      </div>
      <div className="flex flex-wrap gap-1.5" role="group" aria-label={t('exercises.diagramLabels')}>
        {allLabels.map((label) => {
          const used = placements.some((entry) => entry.label === label)
          return (
            <button
              key={label}
              type="button"
              disabled={disabled}
              aria-pressed={selected === label}
              onClick={() => setSelected(used ? null : label)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs transition-colors',
                selected === label
                  ? 'border-primary bg-primary text-primary-foreground'
                  : used
                    ? 'border-success/40 text-success bg-success/5'
                    : 'border-border hover:bg-subtle'
              )}
            >
              {label}
            </button>
          )
        })}
      </div>
      <p className="text-muted-foreground text-xs">
        {selected === null
          ? t('exercises.diagramPickLabel')
          : t('exercises.diagramPickHotspot', { label: selected })}
      </p>
    </div>
  )
}

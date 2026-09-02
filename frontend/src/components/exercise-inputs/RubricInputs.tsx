import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import type { ExerciseStepInput } from '@/lib/api'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import { MathInput } from '@/components/math/MathInput'
import type { Block } from '@/components/blocks/types'

export interface SpotResponse {
  picked: number[]
  fix: string
}

export function parseSpotResponse(value: string): SpotResponse | null {
  try {
    const parsed = JSON.parse(value) as unknown
    if (
      parsed !== null &&
      typeof parsed === 'object' &&
      Array.isArray((parsed as SpotResponse).picked)
    ) {
      const spot = parsed as SpotResponse
      return { picked: spot.picked, fix: typeof spot.fix === 'string' ? spot.fix : '' }
    }
  } catch {
    return null
  }
  return null
}

export function rubricResponseComplete(input: ExerciseStepInput, value: string): boolean {
  if (input.widget === 'lines') {
    const spot = parseSpotResponse(value)
    if (spot !== null) {
      return (
        spot.picked.length > 0 && (!input.requires_fix || spot.fix.trim().length > 0)
      )
    }
    return value.trim().length > 0
  }
  return value.trim().length > 0
}

export function RubricStepInput({
  input,
  value,
  onChange,
  disabled,
}: {
  input: ExerciseStepInput
  value: string
  onChange: (next: string) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  if (input.widget === 'lines') {
    const lines = input.lines ?? []
    const spot = parseSpotResponse(value)
    const picked = spot?.picked[0] ?? null
    const fix = spot?.fix ?? ''
    const emit = (nextPicked: number | null, nextFix: string) => {
      if (nextPicked === null) {
        onChange('')
        return
      }
      onChange(JSON.stringify({ picked: [nextPicked], fix: nextFix }))
    }
    return (
      <div className="space-y-2">
        <ol className="space-y-1.5">
          {lines.map((line, index) => (
            <li key={index}>
              <label
                className={cn(
                  'border-border flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-sm',
                  disabled && 'pointer-events-none opacity-70'
                )}
              >
                <input
                  type="radio"
                  name="error-spot-line"
                  className="mt-1"
                  disabled={disabled}
                  checked={picked === index}
                  onChange={() => emit(index, fix)}
                />
                <span className="flex-1">
                  <BlockRenderer blocks={[{ type: 'text', md: line }] as Block[]} />
                </span>
              </label>
            </li>
          ))}
        </ol>
        {input.requires_fix ? (
          <div className={cn('border-border rounded-md border p-2', disabled && 'opacity-70')}>
            <p className="text-muted-foreground mb-1 text-xs">{t('exercises.fixPrompt')}</p>
            <MathInput value={fix} onChange={(next) => emit(picked, next)} />
          </div>
        ) : null}
      </div>
    )
  }
  if (input.kind === 'correct_solution') {
    return (
      <div className={cn('border-border rounded-md border p-2', disabled && 'opacity-70')}>
        <MathInput value={value} onChange={onChange} />
      </div>
    )
  }
  return (
    <textarea
      className="bg-surface border-border focus:border-primary min-h-32 w-full rounded-md border px-3 py-2 text-sm"
      placeholder="…"
      disabled={disabled}
      value={value}
      onChange={(event) => onChange(event.target.value)}
    />
  )
}

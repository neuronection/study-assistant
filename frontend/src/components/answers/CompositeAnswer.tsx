import { useTranslation } from 'react-i18next'

import { MathInput } from '@/components/math/MathInput'
import { cn } from '@/lib/utils'

export interface CompositePartSpec {
  type: 'text' | 'numeric' | 'equation'
}

export interface CompositeInput {
  parts: CompositePartSpec[]
}

export function isCompositeInput(
  input: { widget: string; parts?: unknown } | null | undefined,
): input is CompositeInput & { widget: string } {
  return input?.widget === 'composite' && Array.isArray(input.parts)
}

export function partLetter(index: number): string {
  return String.fromCharCode(97 + index)
}

export function compositeResponseComplete(
  value: string[] | null,
  input: CompositeInput,
): boolean {
  if (value === null) return false
  return input.parts.some((_, index) => (value[index] ?? '').trim().length > 0)
}

export function emptyCompositeResponse(input: CompositeInput): string[] {
  return input.parts.map(() => '')
}

export function CompositeAnswer({
  input,
  value,
  onChange,
  disabled,
}: {
  input: CompositeInput
  value: string[] | null
  onChange?: (next: string[]) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const interactive = onChange !== undefined && disabled !== true
  const response: string[] = value ?? input.parts.map(() => '')

  const update = (index: number, next: string) => {
    if (!interactive) return
    onChange?.(response.map((entry, i) => (i === index ? next : entry)))
  }

  return (
    <div className="space-y-3">
      {input.parts.map((part, index) => (
        <div key={index} className="flex items-start gap-3">
          <span className="text-muted-foreground mt-2 w-8 shrink-0 text-sm font-medium">
            ({partLetter(index)})
          </span>
          <div className="min-w-0 flex-1">
            {part.type === 'equation' ? (
              <div
                className={cn(
                  'border-border rounded-md border p-2',
                  !interactive && 'opacity-70',
                )}
              >
                <MathInput
                  value={response[index] ?? ''}
                  onChange={(next) => update(index, next)}
                />
              </div>
            ) : (
              <input
                className={cn(
                  'bg-surface border-border w-full rounded-md border px-3 py-2 text-sm',
                  !interactive && 'opacity-70',
                )}
                inputMode={part.type === 'numeric' ? 'decimal' : undefined}
                aria-label={t('widgets.composite.part', { label: partLetter(index) })}
                disabled={!interactive}
                value={response[index] ?? ''}
                onChange={(event) => update(index, event.target.value)}
              />
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

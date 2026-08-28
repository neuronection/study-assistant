import { cn } from '@/lib/utils'
import type { ExerciseStepInput } from '@/lib/api'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import { MathInput } from '@/components/math/MathInput'
import type { Block } from '@/components/blocks/types'

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
  if (input.widget === 'lines') {
    const lines = input.lines ?? []
    return (
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
                checked={value === String(index)}
                onChange={() => onChange(String(index))}
              />
              <span className="flex-1">
                <BlockRenderer blocks={[{ type: 'text', md: line }] as Block[]} />
              </span>
            </label>
          </li>
        ))}
      </ol>
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

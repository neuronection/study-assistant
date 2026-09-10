import type { ExerciseStepInput } from '@/lib/api'

import {
  CategorizeInput,
  FillBlanksInput,
  MatchingInput,
  OrderingInput,
} from './StructuralInputs'

export type StructuralResponse = number[] | string[]

export function isStructuralInput(input: ExerciseStepInput | null | undefined): boolean {
  return (
    input != null &&
    ['matching', 'ordering', 'categorize', 'fill_blank'].includes(input.widget)
  )
}

export function structuralResponseComplete(
  input: ExerciseStepInput,
  value: StructuralResponse | null
): boolean {
  if (value === null) {
    return false
  }
  if (input.widget === 'fill_blank') {
    const values = value as string[]
    const count = input.blank_count ?? 0
    return values.length === count && values.every((entry) => entry.trim().length > 0)
  }
  const values = value as number[]
  const length =
    input.widget === 'matching'
      ? (input.lefts ?? []).length
      : input.widget === 'ordering'
        ? (input.items ?? []).length
        : (input.items ?? []).length
  return (
    values.length === length &&
    values.every((entry) => Number.isInteger(entry) && entry >= 0)
  )
}

export function ExerciseStructuralInput({
  input,
  value,
  onChange,
  disabled,
}: {
  input: ExerciseStepInput
  value: StructuralResponse | null
  onChange: (next: StructuralResponse) => void
  disabled?: boolean
}) {
  if (input.widget === 'fill_blank') {
    return (
      <FillBlanksInput
        input={input}
        value={value as string[] | null}
        onChange={onChange}
        disabled={disabled}
      />
    )
  }
  if (input.widget === 'matching') {
    return (
      <MatchingInput
        input={input}
        value={value as number[] | null}
        onChange={onChange}
        disabled={disabled}
      />
    )
  }
  if (input.widget === 'ordering') {
    return (
      <OrderingInput
        input={input}
        value={value as number[] | null}
        onChange={onChange}
        disabled={disabled}
      />
    )
  }
  return (
    <CategorizeInput
      input={input}
      value={value as number[] | null}
      onChange={onChange}
      disabled={disabled}
    />
  )
}

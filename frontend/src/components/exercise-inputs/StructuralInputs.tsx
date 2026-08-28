import { ArrowDown, ArrowUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import { Button } from '@/components/ui/button'
import type { Block } from '@/components/blocks/types'
import type { ExerciseStepInput } from '@/lib/api'

import { cn } from '@/lib/utils'

function asBlocks(label: string): Block[] {
  return [{ type: 'text', md: label }] as Block[]
}

export function MatchingInput({
  input,
  value,
  onChange,
  disabled,
}: {
  input: ExerciseStepInput
  value: number[] | null
  onChange: (next: number[]) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const lefts = input.lefts ?? []
  const rights = input.rights ?? []
  return (
    <div className="space-y-2">
      {lefts.map((left, index) => (
        <div key={index} className="flex items-center gap-2">
          <div
            className="border-border flex-1 rounded-md border px-3 py-2 text-sm"
            aria-label={t('exercises.matchingLeft', { n: index + 1 })}
          >
            <BlockRenderer blocks={asBlocks(left)} />
          </div>
          <select
            className="bg-surface border-border rounded-md border px-2 py-2 text-sm"
            aria-label={t('exercises.matchingPick', { n: index + 1 })}
            disabled={disabled}
            value={value?.[index] ?? ''}
            onChange={(event) => {
              const next = [...(value ?? Array(lefts.length).fill(null))]
              next[index] = Number(event.target.value)
              onChange(next.map((entry) => entry ?? -1))
            }}
          >
            <option value="" disabled>
              {t('exercises.matchingPickPlaceholder')}
            </option>
            {rights.map((right) => (
              <option key={right.index} value={right.index}>
                {right.label.replace(/\$+/g, '')}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  )
}

export function OrderingInput({
  input,
  value,
  onChange,
  disabled,
}: {
  input: ExerciseStepInput
  value: number[] | null
  onChange: (next: number[]) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const items = (input.items ?? []) as { id: number; label: string }[]
  const order = value ?? items.map((item) => item.id)
  const move = (from: number, to: number) => {
    if (to < 0 || to >= order.length) {
      return
    }
    const next = [...order]
    const [entry] = next.splice(from, 1)
    next.splice(to, 0, entry!)
    onChange(next)
  }
  return (
    <ol className="space-y-1.5">
      {order.map((id, position) => {
        const item = items.find((entry) => entry.id === id)
        return (
          <li
            key={id}
            className="border-border flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
          >
            <span className="text-muted-foreground w-5 text-xs font-medium">
              {position + 1}.
            </span>
            <div className="flex-1">
              <BlockRenderer blocks={asBlocks(item?.label ?? '')} />
            </div>
            <div className="flex gap-0.5">
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                disabled={disabled || position === 0}
                aria-label={t('exercises.moveUp', { n: position + 1 })}
                onClick={() => move(position, position - 1)}
              >
                <ArrowUp className="size-3.5" aria-hidden />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="size-7"
                disabled={disabled || position === order.length - 1}
                aria-label={t('exercises.moveDown', { n: position + 1 })}
                onClick={() => move(position, position + 1)}
              >
                <ArrowDown className="size-3.5" aria-hidden />
              </Button>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

export function CategorizeInput({
  input,
  value,
  onChange,
  disabled,
}: {
  input: ExerciseStepInput
  value: number[] | null
  onChange: (next: number[]) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const items = (input.items ?? []) as string[]
  const categories = input.categories ?? []
  return (
    <div className="space-y-2">
      {items.map((label, index) => (
        <div
          key={index}
          className="border-border flex flex-wrap items-center gap-2 rounded-md border px-3 py-2 text-sm"
        >
          <div className="min-w-40 flex-1">
            <BlockRenderer blocks={asBlocks(label)} />
          </div>
          <div
            className="flex flex-wrap gap-1"
            role="group"
            aria-label={t('exercises.categorizePickItem', { n: index + 1 })}
          >
            {categories.map((category, categoryIndex) => (
              <button
                key={categoryIndex}
                type="button"
                disabled={disabled}
                className={cn(
                  'rounded-full px-2.5 py-1 text-xs transition-colors',
                  value?.[index] === categoryIndex
                    ? 'bg-primary/15 text-primary font-medium'
                    : 'text-muted-foreground hover:bg-subtle'
                )}
                aria-pressed={value?.[index] === categoryIndex}
                aria-label={t('exercises.categorizeOption', {
                  n: index + 1,
                  category,
                })}
                onClick={() => {
                  const next = [...(value ?? Array(items.length).fill(null))]
                  next[index] = categoryIndex
                  onChange(next.map((entry) => entry ?? -1))
                }}
              >
                {category}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function FillBlanksInput({
  input,
  value,
  onChange,
  disabled,
}: {
  input: ExerciseStepInput
  value: string[] | null
  onChange: (next: string[]) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const prompt = input.prompt_md ?? ''
  const parts = prompt.split(/(\{\{\d+\}\})/g).filter(Boolean)
  return (
    <p className="text-foreground flex flex-wrap items-center gap-1 text-sm leading-relaxed">
      {parts.map((part, index) => {
        const match = part.match(/^\{\{(\d+)\}\}$/)
        if (!match) {
          return (
            <span key={index}>
              <BlockRenderer blocks={asBlocks(part)} />
            </span>
          )
        }
        const blankIndex = Number(match[1]) - 1
        return (
          <input
            key={index}
            className="bg-surface border-primary/50 w-28 rounded-md border-b-2 border px-2 py-0.5 text-center text-sm"
            aria-label={t('exercises.blankLabel', { n: blankIndex + 1 })}
            placeholder={t('exercises.blankPlaceholder', { n: blankIndex + 1 })}
            disabled={disabled}
            value={value?.[blankIndex] ?? ''}
            onChange={(event) => {
              const next = [...(value ?? Array(input.blank_count ?? 0).fill(''))]
              next[blankIndex] = event.target.value
              onChange(next)
            }}
          />
        )
      })}
    </p>
  )
}

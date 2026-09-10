import { useTranslation } from 'react-i18next'

import { PlotlyChart } from '@/components/blocks/PlotlyChart'

export interface GraphReadInput {
  mode: 'value' | 'point'
}

export interface GraphReadResponse {
  value?: number
  index?: number
}

export function isGraphReadInput(
  input: { widget: string; mode?: string } | null | undefined,
): input is GraphReadInput & { widget: string } {
  return input?.widget === 'graph_read' && (input.mode === 'value' || input.mode === 'point')
}

export function nearestSampleIndex(xs: number[], x: number): number {
  return xs.reduce(
    (best, candidate, index) =>
      Math.abs(candidate - x) < Math.abs(xs[best] - x) ? index : best,
    0,
  )
}

export function GraphReadAnswer({
  figure,
  mode,
  xs,
  response,
  onChange,
  disabled,
}: {
  figure: Record<string, unknown>
  mode: 'value' | 'point'
  xs: number[]
  response: GraphReadResponse | null
  onChange?: (next: GraphReadResponse) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const interactive = onChange !== undefined && disabled !== true

  if (mode === 'value') {
    return (
      <input
        className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
        inputMode="decimal"
        aria-label={t('widgets.graphread.valuePlaceholder')}
        disabled={!interactive}
        value={response?.value !== undefined ? String(response.value) : ''}
        onChange={(event) => {
          const raw = event.target.value.trim()
          if (raw === '') {
            onChange?.({})
            return
          }
          const parsed = Number(raw.replace(',', '.'))
          if (!Number.isNaN(parsed)) {
            onChange?.({ value: parsed })
          }
        }}
      />
    )
  }
  const selectedIndex = response?.index
  return (
    <div className="space-y-1">
      <PlotlyChart
        figure={figure}
        onPointClick={
          interactive
            ? (x) => {
                onChange?.({ index: nearestSampleIndex(xs, x) })
              }
            : undefined
        }
      />
      <p className="text-muted-foreground text-xs">
        {selectedIndex !== undefined && xs[selectedIndex] !== undefined
          ? t('widgets.graphread.selected', { x: xs[selectedIndex] })
          : t('widgets.graphread.clickHint')}
      </p>
    </div>
  )
}

export function chartFigureFromStem(
  stem: { type: string; plotly?: Record<string, unknown> }[] | null | undefined,
): Record<string, unknown> | null {
  const block = stem?.find((entry) => entry.type === 'chart')
  return block?.plotly ?? null
}

export function chartXs(figure: Record<string, unknown> | null): number[] {
  if (figure === null) return []
  const data = figure.data
  if (Array.isArray(data) && Array.isArray((data[0] as { x?: unknown })?.x)) {
    return (data[0] as { x: number[] }).x
  }
  return []
}

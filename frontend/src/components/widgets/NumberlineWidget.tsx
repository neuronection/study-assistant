import type { MouseEvent } from 'react'
import { useTranslation } from 'react-i18next'

import { useWidgetState } from './useWidgetState'
import type { WidgetComponentProps } from './types'

type NumberlineProps = {
  min: number
  max: number
  label?: string
}

type NumberlineState = {
  points: number[]
}

const WIDTH = 480
const HEIGHT = 60
const PAD = 20

export function NumberlineWidget({ props, state, onStateChange }: WidgetComponentProps) {
  const { t } = useTranslation()
  const config = props as NumberlineProps
  const seed = state as Partial<NumberlineState>
  const [value, update] = useWidgetState<NumberlineState>(
    { points: Array.isArray(seed.points) ? seed.points : [] },
    onStateChange,
  )
  const min = typeof config?.min === 'number' ? config.min : 0
  const max = typeof config?.max === 'number' && config.max > min ? config.max : min + 10
  const points = Array.isArray(value.points) ? value.points : []
  const toX = (number: number) => PAD + ((number - min) / (max - min)) * (WIDTH - 2 * PAD)
  const onClick = (event: MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    const fraction = (event.clientX - rect.left - PAD) / (WIDTH - 2 * PAD)
    const raw = min + fraction * (max - min)
    const snapped = Math.round(Math.min(max, Math.max(min, raw)) * 10) / 10
    const exists = points.some((point) => Math.abs(point - snapped) < 0.05)
    update({
      points: exists
        ? points.filter((point) => Math.abs(point - snapped) >= 0.05)
        : [...points, snapped],
    })
  }
  return (
    <div className="border-border bg-subtle rounded-md border p-3 text-sm">
      {config?.label ? <p className="mb-2 font-medium">{config.label}</p> : null}
      <p className="text-muted-foreground mb-1 text-xs">{t('widgets.numberlineHint')}</p>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        onClick={onClick}
        className="w-full cursor-pointer"
        role="img"
      >
        <line
          x1={PAD}
          y1={HEIGHT / 2}
          x2={WIDTH - PAD}
          y2={HEIGHT / 2}
          className="stroke-border"
          strokeWidth={2}
        />
        {[min, max].map((number) => (
          <g key={number}>
            <line
              x1={toX(number)}
              y1={HEIGHT / 2 - 6}
              x2={toX(number)}
              y2={HEIGHT / 2 + 6}
              className="stroke-border"
              strokeWidth={2}
            />
            <text
              x={toX(number)}
              y={HEIGHT / 2 + 20}
              textAnchor="middle"
              className="fill-muted-foreground text-[10px]"
            >
              {number}
            </text>
          </g>
        ))}
        {points.map((point) => (
          <circle key={point} cx={toX(point)} cy={HEIGHT / 2} r={6} className="fill-primary" />
        ))}
      </svg>
    </div>
  )
}

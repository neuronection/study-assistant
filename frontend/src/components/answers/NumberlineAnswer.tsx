import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export interface NumberlinePayload {
  points: { value: number }[]
  intervals: { lo: number; hi: number; lo_closed: boolean; hi_closed: boolean }[]
}

export function emptyNumberlinePayload(): NumberlinePayload {
  return { points: [], intervals: [] }
}

export function numberlinePayloadComplete(payload: NumberlinePayload | null): boolean {
  return (
    payload !== null && (payload.points.length > 0 || payload.intervals.length > 0)
  )
}

const WIDTH = 560
const HEIGHT = 92
const PAD = 26
const AXIS_Y = 46
const BAR_STROKE = 10
const END_RADIUS = 7
const POINT_RADIUS = 6

type DragState =
  | { kind: 'lo' | 'hi'; index: number; moved: boolean; startClientX: number }
  | { kind: 'body'; index: number; moved: boolean; startClientX: number; lo: number; hi: number }
  | null

function snapValue(raw: number, min: number, max: number): number {
  const step = (max - min) / 100
  const snapped = Math.round(raw / step) * step
  const fixed = Number(snapped.toFixed(3))
  return Math.min(max, Math.max(min, fixed))
}

function ticks(min: number, max: number): number[] {
  const candidates = [1, 2, 5, 10, 20, 25, 50, 100]
  const target = (max - min) / 8
  const stepSize = candidates.find((entry) => entry >= target) ?? 100
  const start = Math.ceil(min / stepSize) * stepSize
  const result: number[] = []
  for (let value = start; value <= max + 1e-9; value += stepSize) {
    result.push(Number(value.toFixed(6)))
  }
  return result
}

export function NumberlineAnswer({
  min,
  max,
  value,
  onChange,
  disabled,
}: {
  min: number
  max: number
  value: NumberlinePayload | null
  onChange?: (next: NumberlinePayload) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'points' | 'interval'>('points')
  const [pending, setPending] = useState<number | null>(null)
  const dragRef = useRef<DragState>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const suppressClickRef = useRef(false)
  const interactive = onChange !== undefined && disabled !== true
  const payload: NumberlinePayload = value ?? emptyNumberlinePayload()
  const span = max - min > 0 ? max - min : 10
  const minGap = span / 400

  const toX = (number: number) => PAD + ((number - min) / span) * (WIDTH - 2 * PAD)
  const fromClientX = (clientX: number) => {
    const svg = svgRef.current
    if (svg === null) return min
    const rect = svg.getBoundingClientRect()
    if (rect.width === 0) return min
    const axisFraction = ((clientX - rect.left) / rect.width * WIDTH - PAD) / (WIDTH - 2 * PAD)
    return snapValue(min + axisFraction * span, min, max)
  }

  const update = (next: NumberlinePayload) => {
    onChange?.(next)
  }

  const removePoint = (index: number) => {
    update({ ...payload, points: payload.points.filter((_, i) => i !== index) })
  }

  const removeInterval = (index: number) => {
    update({ ...payload, intervals: payload.intervals.filter((_, i) => i !== index) })
  }

  const toggleBoundary = (index: number, side: 'lo' | 'hi') => {
    update({
      ...payload,
      intervals: payload.intervals.map((interval, i) =>
        i === index
          ? side === 'lo'
            ? { ...interval, lo_closed: !interval.lo_closed }
            : { ...interval, hi_closed: !interval.hi_closed }
          : interval,
      ),
    })
  }

  const onSurfaceClick = (event: React.MouseEvent<SVGSVGElement>) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false
      return
    }
    if (!interactive) return
    const next = fromClientX(event.clientX)
    if (mode === 'points') {
      const existing = payload.points.findIndex(
        (point) => Math.abs(point.value - next) < minGap,
      )
      if (existing >= 0) {
        removePoint(existing)
      } else {
        update({ ...payload, points: [...payload.points, { value: next }] })
      }
      return
    }
    if (pending === null) {
      setPending(next)
      return
    }
    const lo = Math.min(pending, next)
    const hi = Math.max(pending, next)
    setPending(null)
    if (hi - lo < minGap) {
      return
    }
    update({
      ...payload,
      intervals: [...payload.intervals, { lo, hi, lo_closed: true, hi_closed: true }],
    })
  }

  const beginDrag = (state: NonNullable<DragState>, event: React.PointerEvent) => {
    if (!interactive) return
    event.stopPropagation()
    event.preventDefault()
    dragRef.current = state
    svgRef.current?.setPointerCapture?.(event.pointerId)
  }

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current
    if (drag === null || !interactive) return
    const moved = Math.abs(event.clientX - drag.startClientX) > 3
    if (!moved && !drag.moved) return
    dragRef.current = { ...drag, moved: true }
    const next = fromClientX(event.clientX)
    if (drag.kind === 'body') {
      const delta = next - fromClientX(drag.startClientX)
      const width = drag.hi - drag.lo
      const nextLo = Math.min(max - width, Math.max(min, drag.lo + delta))
      update({
        ...payload,
        intervals: payload.intervals.map((interval, i) =>
          i === drag.index ? { ...interval, lo: nextLo, hi: nextLo + width } : interval,
        ),
      })
      return
    }
    update({
      ...payload,
      intervals: payload.intervals.map((interval, i) => {
        if (i !== drag.index) return interval
        if (drag.kind === 'lo') {
          return { ...interval, lo: Math.min(next, interval.hi - minGap) }
        }
        return { ...interval, hi: Math.max(next, interval.lo + minGap) }
      }),
    })
  }

  const onPointerUp = () => {
    const drag = dragRef.current
    dragRef.current = null
    if (drag === null || !interactive) return
    suppressClickRef.current = true
    if (!drag.moved) {
      if (drag.kind === 'body') {
        removeInterval(drag.index)
      } else {
        toggleBoundary(drag.index, drag.kind)
      }
    }
  }

  return (
    <div className="border-border bg-subtle rounded-md border p-3 text-sm">
      {interactive ? (
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex gap-1" role="group" aria-label={t('widgets.numberline.mode')}>
            {(['points', 'interval'] as const).map((entry) => (
              <button
                key={entry}
                type="button"
                aria-pressed={mode === entry}
                onClick={() => {
                  setMode(entry)
                  setPending(null)
                }}
                className={cn(
                  'rounded-full border px-2.5 py-0.5 text-xs transition-colors',
                  mode === entry
                    ? 'border-primary bg-primary/10 text-primary font-medium'
                    : 'border-border text-muted-foreground hover:text-foreground',
                )}
              >
                {t(`widgets.numberline.mode_${entry}`)}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground text-xs hover:underline"
            onClick={() => {
              setPending(null)
              update(emptyNumberlinePayload())
            }}
          >
            {t('widgets.numberline.clear')}
          </button>
        </div>
      ) : null}
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className={cn('w-full', interactive && 'cursor-pointer touch-none select-none')}
        role="img"
        aria-label={t('widgets.numberline.aria')}
        onClick={onSurfaceClick}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => {
          dragRef.current = null
        }}
      >
        {pending !== null ? (
          <line
            x1={toX(pending)}
            y1={AXIS_Y - 26}
            x2={toX(pending)}
            y2={AXIS_Y + 26}
            className="stroke-primary/50"
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
        ) : null}
        <line
          x1={PAD}
          y1={AXIS_Y}
          x2={WIDTH - PAD}
          y2={AXIS_Y}
          className="stroke-border"
          strokeWidth={2}
        />
        {ticks(min, max).map((tick) => (
          <g key={tick}>
            <line
              x1={toX(tick)}
              y1={AXIS_Y - 5}
              x2={toX(tick)}
              y2={AXIS_Y + 5}
              className="stroke-border"
              strokeWidth={1.5}
            />
            <text
              x={toX(tick)}
              y={AXIS_Y + 24}
              textAnchor="middle"
              className="fill-muted-foreground text-[11px]"
            >
              {tick}
            </text>
          </g>
        ))}
        {payload.intervals.map((interval, index) => (
          <g key={`i${index}`}>
            <line
              x1={toX(interval.lo)}
              y1={AXIS_Y}
              x2={toX(interval.hi)}
              y2={AXIS_Y}
              className="stroke-primary"
              strokeWidth={BAR_STROKE}
              strokeLinecap="butt"
              opacity={interactive ? 0.85 : 0.9}
              style={{ cursor: interactive ? 'grab' : undefined }}
              onPointerDown={(event) =>
                beginDrag(
                  {
                    kind: 'body',
                    index,
                    moved: false,
                    startClientX: event.clientX,
                    lo: interval.lo,
                    hi: interval.hi,
                  },
                  event,
                )
              }
            />
            {(['lo', 'hi'] as const).map((side) => {
              const endValue = side === 'lo' ? interval.lo : interval.hi
              const closed = side === 'lo' ? interval.lo_closed : interval.hi_closed
              return (
                <circle
                  key={side}
                  cx={toX(endValue)}
                  cy={AXIS_Y}
                  r={END_RADIUS}
                  className={cn(
                    closed ? 'fill-primary stroke-primary' : 'fill-surface stroke-primary',
                  )}
                  strokeWidth={2.5}
                  style={{ cursor: interactive ? 'pointer' : undefined }}
                  onPointerDown={(event) =>
                    beginDrag(
                      { kind: side, index, moved: false, startClientX: event.clientX },
                      event,
                    )
                  }
                />
              )
            })}
          </g>
        ))}
        {payload.points.map((point, index) => (
          <circle
            key={`p${index}`}
            cx={toX(point.value)}
            cy={AXIS_Y}
            r={POINT_RADIUS}
            className="fill-primary stroke-surface"
            strokeWidth={2}
            style={{ cursor: interactive ? 'pointer' : undefined }}
            onClick={(event) => {
              event.stopPropagation()
              if (interactive) removePoint(index)
            }}
          />
        ))}
      </svg>
      {interactive ? (
        <p className="text-muted-foreground mt-1 text-xs">
          {mode === 'points'
            ? t('widgets.numberline.hint_points')
            : t('widgets.numberline.hint_interval')}
        </p>
      ) : null}
    </div>
  )
}

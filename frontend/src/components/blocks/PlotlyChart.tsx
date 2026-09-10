import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

export function PlotlyChart({
  figure,
  onPointClick,
}: {
  figure: Record<string, unknown>
  onPointClick?: (x: number, y: number) => void
}) {
  const { t } = useTranslation()
  const containerRef = useRef<HTMLDivElement>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    let purge: (() => void) | undefined
    let observer: ResizeObserver | undefined
    const element = containerRef.current
    if (!element) return
    const data = Array.isArray(figure.data) ? figure.data : [figure.data]
    const layout: Record<string, unknown> = {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      margin: { t: 32, r: 12, b: 32, l: 40 },
      autosize: true,
      ...(figure.layout && typeof figure.layout === 'object'
        ? (figure.layout as Record<string, unknown>)
        : {}),
    }
    if (prefersReducedMotion()) {
      layout.transition = { duration: 0 }
    }
    import('plotly.js-dist-min')
      .then(({ default: Plotly }) => {
        if (cancelled || !element) return
        purge = () => Plotly.purge(element)
        return Plotly.newPlot(element, data, layout, {
          displayModeBar: false,
          responsive: true,
        }).then(() => {
          if (cancelled) return
          if (onPointClick) {
            const plotlyElement = element as unknown as {
              on: (event: string, cb: (event: { points: { x: number; y: number }[] }) => void) => void
              removeAllListeners: (event: string) => void
            }
            plotlyElement.removeAllListeners?.('plotly_click')
            plotlyElement.on('plotly_click', (event) => {
              const point = event?.points?.[0]
              if (point) onPointClick(point.x, point.y)
            })
          }
          if (cancelled || typeof ResizeObserver === 'undefined') return
          observer = new ResizeObserver(() => Plotly.Plots.resize(element))
          observer.observe(element)
        })
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
      observer?.disconnect()
      purge?.()
    }
  }, [figure, onPointClick])

  if (failed) {
    return (
      <div className="border-border bg-subtle text-muted-foreground flex h-32 items-center justify-center rounded-md border border-dashed text-xs">
        {t('blocks.chartPlaceholder')}
      </div>
    )
  }
  return (
    <div className="min-w-0 overflow-hidden">
      <div ref={containerRef} className="h-72 w-full" />
    </div>
  )
}

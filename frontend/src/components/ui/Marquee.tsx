import {
  useEffect,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react'

import { cn } from '@/lib/utils'

export interface Rect {
  left: number
  top: number
  right: number
  bottom: number
}

export function rectsIntersect(a: Rect, b: Rect): boolean {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom
}

export function marqueeRect(
  startX: number,
  startY: number,
  currentX: number,
  currentY: number
): Rect {
  return {
    left: Math.min(startX, currentX),
    top: Math.min(startY, currentY),
    right: Math.max(startX, currentX),
    bottom: Math.max(startY, currentY),
  }
}

export function hitTestIds(
  container: HTMLElement,
  marquee: Rect
): string[] {
  const hits: string[] = []
  const elements = container.querySelectorAll<HTMLElement>('[data-selectable-id]')
  for (const element of elements) {
    const box = element.getBoundingClientRect()
    const itemRect: Rect = {
      left: box.left,
      top: box.top,
      right: box.right,
      bottom: box.bottom,
    }
    if (rectsIntersect(marquee, itemRect)) {
      const id = element.getAttribute('data-selectable-id')
      if (id !== null) {
        hits.push(id)
      }
    }
  }
  return hits
}

const DRAG_THRESHOLD = 4

const INTERACTIVE_SELECTOR =
  'button, input, textarea, select, a, [data-selectable-id], [data-no-marquee]'

export type MarqueePhase = 'start' | 'drag' | 'end'

export function useMarquee({
  enabled,
  containerRef,
  getBaseSelection,
  onSelect,
}: {
  enabled: boolean
  containerRef: { current: HTMLElement | null }
  getBaseSelection: () => Set<string>
  onSelect: (ids: string[], phase: MarqueePhase) => void
}): { band: Rect | null } {
  const [band, setBand] = useState<Rect | null>(null)
  const startRef = useRef<{ x: number; y: number; base: Set<string> } | null>(null)
  const armedRef = useRef(false)
  const getBaseRef = useRef(getBaseSelection)
  getBaseRef.current = getBaseSelection
  const onSelectRef = useRef(onSelect)
  onSelectRef.current = onSelect

  useEffect(() => {
    if (!enabled) {
      return
    }
    const container = containerRef.current
    if (container === null) {
      return
    }

    const onMouseDown = (event: MouseEvent) => {
      if (event.button !== 0) {
        return
      }
      const target = event.target as Element | null
      if (target !== null && target.closest(INTERACTIVE_SELECTOR) !== null) {
        return
      }
      const base =
        event.ctrlKey || event.metaKey
          ? new Set(getBaseRef.current())
          : new Set<string>()
      startRef.current = { x: event.clientX, y: event.clientY, base }
      armedRef.current = false
    }

    const onMouseMove = (event: MouseEvent) => {
      const start = startRef.current
      if (start === null) {
        return
      }
      const rect = marqueeRect(start.x, start.y, event.clientX, event.clientY)
      if (!armedRef.current) {
        if (
          rect.right - rect.left < DRAG_THRESHOLD &&
          rect.bottom - rect.top < DRAG_THRESHOLD
        ) {
          return
        }
        armedRef.current = true
        onSelectRef.current([...start.base], 'start')
      }
      setBand(rect)
      const containerNow = containerRef.current
      if (containerNow !== null) {
        const hits = hitTestIds(containerNow, rect)
        onSelectRef.current(
          [...new Set([...start.base, ...hits])],
          'drag'
        )
      }
    }

    const finish = (event: MouseEvent) => {
      const start = startRef.current
      if (start === null) {
        return
      }
      startRef.current = null
      setBand(null)
      if (armedRef.current) {
        const containerNow = containerRef.current
        if (containerNow !== null) {
          const rect = marqueeRect(
            start.x,
            start.y,
            event.clientX,
            event.clientY
          )
          const hits = hitTestIds(containerNow, rect)
          onSelectRef.current(
            [...new Set([...start.base, ...hits])],
            'end'
          )
        }
        return
      }
      if (!event.ctrlKey && !event.metaKey) {
        onSelectRef.current([], 'end')
      }
    }

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && startRef.current !== null) {
        const start = startRef.current
        startRef.current = null
        setBand(null)
        onSelectRef.current([...start.base], 'end')
      }
    }

    container.addEventListener('mousedown', onMouseDown)
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', finish)
    window.addEventListener('keydown', onKey)
    return () => {
      container.removeEventListener('mousedown', onMouseDown)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', finish)
      window.removeEventListener('keydown', onKey)
    }
  }, [enabled, containerRef])

  return { band }
}

export function MarqueeBand({ band }: { band: Rect | null }) {
  if (band === null) {
    return null
  }
  return (
    <div
      className={cn(
        'border-primary bg-primary/10 pointer-events-none fixed z-40 rounded-sm border'
      )}
      style={{
        left: band.left,
        top: band.top,
        width: band.right - band.left,
        height: band.bottom - band.top,
      }}
      aria-hidden
    />
  )
}

export interface MarqueeSelection {
  selected: Set<string>
  set: (ids: string[]) => void
  clear: () => void
}

export function MarqueeSurface({
  children,
  className,
  selection,
  clearBlocked,
  onContextMenu,
  onDragOver,
  onDrop,
}: {
  children: ReactNode
  className?: string
  selection: MarqueeSelection
  clearBlocked?: () => boolean
  onContextMenu?: (event: ReactMouseEvent<HTMLDivElement>) => void
  onDragOver?: (event: ReactDragEvent<HTMLDivElement>) => void
  onDrop?: (event: ReactDragEvent<HTMLDivElement>) => void
}) {
  const paneRef = useRef<HTMLDivElement>(null)
  const { band } = useMarquee({
    enabled: true,
    containerRef: paneRef,
    getBaseSelection: () => selection.selected,
    onSelect: (ids) => selection.set(ids),
  })
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (clearBlocked?.() ?? false) {
        return
      }
      const target = event.target
      if (
        target instanceof Element &&
        target.closest('input, textarea, select, [contenteditable="true"]') !== null
      ) {
        return
      }
      if (event.key === 'Escape') {
        selection.clear()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [clearBlocked, selection])
  return (
    <div
      ref={paneRef}
      data-marquee-surface=""
      className={className}
      onContextMenu={onContextMenu}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {children}
      <MarqueeBand band={band} />
    </div>
  )
}

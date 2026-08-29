import { GripHorizontal } from 'lucide-react'
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'

import { cn } from '@/lib/utils'
import { useOverlayStore } from '@/lib/ui-overlays'

const VIEWPORT_MARGIN = 8

type ResizeDir = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

const RESIZE_HANDLES: { dir: ResizeDir; className: string }[] = [
  { dir: 'n', className: '-top-0.5 left-2 right-2 h-1 cursor-ns-resize' },
  { dir: 's', className: '-bottom-0.5 left-2 right-2 h-1 cursor-ns-resize' },
  { dir: 'e', className: '-right-0.5 top-2 bottom-2 w-1 cursor-ew-resize' },
  { dir: 'w', className: '-left-0.5 top-2 bottom-2 w-1 cursor-ew-resize' },
  { dir: 'ne', className: '-top-0.5 -right-0.5 size-2.5 cursor-nesw-resize' },
  { dir: 'nw', className: '-top-0.5 -left-0.5 size-2.5 cursor-nwse-resize' },
  { dir: 'se', className: '-bottom-0.5 -right-0.5 size-2.5 cursor-nwse-resize' },
  { dir: 'sw', className: '-bottom-0.5 -left-0.5 size-2.5 cursor-nesw-resize' },
]

function clampWithinWindow(
  left: number,
  top: number,
  width: number,
  height: number
): { top: number; left: number } {
  const maxLeft = Math.max(VIEWPORT_MARGIN, window.innerWidth - width - VIEWPORT_MARGIN)
  const maxTop = Math.max(VIEWPORT_MARGIN, window.innerHeight - height - VIEWPORT_MARGIN)
  return {
    left: Math.min(Math.max(left, VIEWPORT_MARGIN), maxLeft),
    top: Math.min(Math.max(top, VIEWPORT_MARGIN), maxTop),
  }
}

export function FloatingPanel({
  trigger,
  children,
  align = 'end',
  side = 'bottom',
  panelClassName,
  label,
  closeSignal = 0,
  triggerClassName,
  focusOnOpen = true,
  preserveFocus = false,
  minWidth = 280,
  minHeight = 200,
}: {
  trigger: ReactNode
  children: ReactNode | (() => ReactNode)
  align?: 'start' | 'end'
  side?: 'top' | 'bottom'
  panelClassName?: string
  label: string
  closeSignal?: number
  triggerClassName?: string
  focusOnOpen?: boolean
  preserveFocus?: boolean
  minWidth?: number
  minHeight?: number
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const [size, setSize] = useState<{ width?: number; height?: number }>({})
  const manualRef = useRef(false)
  const rootRef = useRef<HTMLSpanElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{
    kind: 'move' | 'resize'
    dir?: ResizeDir
    pointerId: number
    startX: number
    startY: number
    left: number
    top: number
    width: number
    height: number
  } | null>(null)

  useEffect(() => {
    if (closeSignal > 0) {
      setOpen(false)
    }
  }, [closeSignal])

  const floatingsToken = useOverlayStore((state) => state.token)
  useEffect(() => {
    if (floatingsToken > 0) {
      setOpen(false)
    }
  }, [floatingsToken])

  const updatePosition = useCallback(() => {
    const triggerEl = rootRef.current
    if (triggerEl === null) {
      return
    }
    const panel = panelRef.current
    const width = panel?.offsetWidth ?? 0
    const height = panel?.offsetHeight ?? 0
    if (manualRef.current) {
      setPos((prev) =>
        prev === null ? prev : clampWithinWindow(prev.left, prev.top, width, height)
      )
      return
    }
    const rect = triggerEl.getBoundingClientRect()
    const left = align === 'end' ? rect.right - width : rect.left
    let top: number
    if (side === 'top') {
      top = rect.top - height - VIEWPORT_MARGIN
    } else {
      top = rect.bottom + VIEWPORT_MARGIN
      if (top + height > window.innerHeight - VIEWPORT_MARGIN && rect.top - height - VIEWPORT_MARGIN >= VIEWPORT_MARGIN) {
        top = rect.top - height - VIEWPORT_MARGIN
      }
    }
    const clamped = clampWithinWindow(left, top, width, height)
    setPos((prev) =>
      prev !== null && prev.top === clamped.top && prev.left === clamped.left ? prev : clamped
    )
  }, [align, side])

  useLayoutEffect(() => {
    if (open) {
      updatePosition()
    } else {
      setPos(null)
      setSize({})
      manualRef.current = false
    }
  }, [open, updatePosition])

  useEffect(() => {
    if (!open) {
      return
    }
    const panel = panelRef.current
    if (panel === null || typeof ResizeObserver === 'undefined') {
      return
    }
    const observer = new ResizeObserver(() => updatePosition())
    observer.observe(panel)
    return () => observer.disconnect()
  }, [open, updatePosition])

  useEffect(() => {
    if (!open) {
      return
    }
    const panel = panelRef.current
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (
        rootRef.current?.contains(target) === false &&
        panel?.contains(target) === false
      ) {
        setOpen(false)
      }
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }
    const onReposition = () => updatePosition()
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    window.addEventListener('resize', onReposition)
    window.addEventListener('scroll', onReposition, true)
    if (focusOnOpen) {
      panel?.focus()
    }
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('resize', onReposition)
      window.removeEventListener('scroll', onReposition, true)
    }
  }, [open, updatePosition, focusOnOpen])

  const beginDrag = (
    event: React.PointerEvent,
    kind: 'move' | 'resize',
    dir?: ResizeDir
  ) => {
    event.preventDefault()
    const panel = panelRef.current
    if (panel === null) {
      return
    }
    const rect = panel.getBoundingClientRect()
    dragRef.current = {
      kind,
      dir,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    }
    try {
      event.currentTarget.setPointerCapture(event.pointerId)
    } catch {
      void 0
    }
  }

  const onDragMove = (event: React.PointerEvent) => {
    const drag = dragRef.current
    if (drag === null || drag.pointerId !== event.pointerId) {
      return
    }
    const dx = event.clientX - drag.startX
    const dy = event.clientY - drag.startY
    if (dx === 0 && dy === 0) {
      return
    }
    manualRef.current = true
    if (drag.kind === 'move') {
      const clamped = clampWithinWindow(
        drag.left + dx,
        drag.top + dy,
        drag.width,
        drag.height
      )
      setPos(clamped)
      return
    }
    const dir = drag.dir!
    let left = drag.left
    let top = drag.top
    let width = drag.width
    let height = drag.height
    if (dir.includes('e')) width = drag.width + dx
    if (dir.includes('w')) width = drag.width - dx
    if (dir.includes('s')) height = drag.height + dy
    if (dir.includes('n')) height = drag.height - dy
    const maxWidth = Math.max(minWidth, window.innerWidth - 2 * VIEWPORT_MARGIN)
    const maxHeight = Math.max(minHeight, window.innerHeight - 2 * VIEWPORT_MARGIN)
    width = Math.max(minWidth, Math.min(width, maxWidth))
    height = Math.max(minHeight, Math.min(height, maxHeight))
    if (dir.includes('w')) left = drag.left + drag.width - width
    if (dir.includes('n')) top = drag.top + drag.height - height
    const clamped = clampWithinWindow(left, top, width, height)
    setSize({ width, height })
    setPos(clamped)
  }

  const endDrag = (event: React.PointerEvent) => {
    const drag = dragRef.current
    if (drag === null || drag.pointerId !== event.pointerId) {
      return
    }
    dragRef.current = null
    try {
      event.currentTarget.releasePointerCapture(event.pointerId)
    } catch {
      void 0
    }
  }

  const dragProps = {
    onPointerDown: (event: React.PointerEvent) => beginDrag(event, 'move'),
    onPointerMove: onDragMove,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
  }

  const resizeHandleProps = (dir: ResizeDir) => ({
    onPointerDown: (event: React.PointerEvent) => beginDrag(event, 'resize', dir),
    onPointerMove: onDragMove,
    onPointerUp: endDrag,
    onPointerCancel: endDrag,
  })

  const content = typeof children === 'function' ? children() : children

  return (
    <span className="relative inline-flex" ref={rootRef}>
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={label}
        className={cn(
          'hover:bg-subtle inline-flex items-center justify-center gap-1 rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
          triggerClassName ?? 'size-9'
        )}
        onMouseDown={
          preserveFocus ? (event) => event.preventDefault() : undefined
        }
        onClick={() => setOpen((current) => !current)}
      >
        {trigger}
      </button>
      {open
        ? createPortal(
            <div
              ref={panelRef}
              role="dialog"
              aria-label={label}
              tabIndex={-1}
              style={
                pos === null
                  ? { position: 'fixed', top: -9999, left: -9999, ...size }
                  : {
                      position: 'fixed',
                      top: pos.top,
                      left: pos.left,
                      maxHeight: window.innerHeight - 2 * VIEWPORT_MARGIN,
                      maxWidth: window.innerWidth - 2 * VIEWPORT_MARGIN,
                      ...size,
                    }
              }
              className={cn(
                'bg-surface border-border z-[60] w-80 rounded-lg border p-3 shadow-lg outline-none',
                panelClassName,
                'flex flex-col'
              )}
            >
              <div
                {...dragProps}
                data-popover-drag-handle
                className="mb-1 flex h-4 cursor-grab touch-none items-center justify-center rounded text-muted-foreground select-none hover:bg-subtle"
              >
                <GripHorizontal className="size-3.5" aria-hidden />
              </div>
              <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
                {content}
              </div>
              {RESIZE_HANDLES.map((handle) => (
                <div
                  key={handle.dir}
                  data-resize-dir={handle.dir}
                  {...resizeHandleProps(handle.dir)}
                  className={cn(
                    'absolute z-10 touch-none select-none',
                    handle.className
                  )}
                />
              ))}
            </div>,
            document.body
          )
        : null}
    </span>
  )
}

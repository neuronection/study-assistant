import {
  Eraser,
  Hand,
  Maximize2,
  Minimize2,
  Pen,
  Redo2,
  Scan,
  Trash2,
  Undo2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

export type StrokeTool = 'pen' | 'eraser' | 'pan'

export interface Stroke {
  points: number[][]
  color: string
  width: number
  tool?: StrokeTool
}

export interface ViewBox {
  x: number
  y: number
  width: number
  height: number
}

export interface ViewState {
  x: number
  y: number
  zoom: number
}

export const INK_COLORS = ['#1a1a1a', '#dc2626', '#2563eb', '#16a34a'] as const
export const PEN_WIDTHS = [2, 4, 7] as const

export const ZOOM_MIN = 0.2
export const ZOOM_MAX = 6
export const EXPORT_PADDING = 24
export const FIT_MAX_ZOOM = 2
const DEFAULT_VIEWPORT = { width: 1024, height: 480 }
const GRID_STEP = 50
const DPR =
  typeof window === 'undefined' ? 1 : Math.min(window.devicePixelRatio || 1, 2)

export function clampZoom(zoom: number): number {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom))
}

export function strokeBounds(strokes: Stroke[], padding = 0): ViewBox | null {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const stroke of strokes) {
    for (const point of stroke.points) {
      minX = Math.min(minX, point[0] - stroke.width)
      minY = Math.min(minY, point[1] - stroke.width)
      maxX = Math.max(maxX, point[0] + stroke.width)
      maxY = Math.max(maxY, point[1] + stroke.width)
    }
  }
  if (!Number.isFinite(minX) || !Number.isFinite(minY)) {
    return null
  }
  return {
    x: minX - padding,
    y: minY - padding,
    width: maxX - minX + padding * 2,
    height: maxY - minY + padding * 2,
  }
}

export function fitView(bounds: ViewBox, viewport: { width: number; height: number }): ViewState {
  const zoom = clampZoom(
    Math.min(viewport.width / bounds.width, viewport.height / bounds.height, FIT_MAX_ZOOM)
  )
  return {
    x: bounds.x + bounds.width / 2 - viewport.width / (2 * zoom),
    y: bounds.y + bounds.height / 2 - viewport.height / (2 * zoom),
    zoom,
  }
}

export function viewFromFocus(
  focus: ViewBox,
  viewport: { width: number; height: number }
): ViewState {
  const zoom = clampZoom(
    Math.min(viewport.width / focus.width, viewport.height / focus.height, 1)
  )
  return {
    x: focus.x + focus.width / 2 - viewport.width / (2 * zoom),
    y: focus.y + focus.height / 2 - viewport.height / (2 * zoom),
    zoom,
  }
}

function drawStrokeSegment(
  context: CanvasRenderingContext2D,
  stroke: Stroke
): void {
  context.lineCap = 'round'
  context.lineJoin = 'round'
  const base = stroke.width
  context.strokeStyle = stroke.color
  for (let index = 1; index < stroke.points.length; index += 1) {
    const previous = stroke.points[index - 1]
    const point = stroke.points[index]
    const pressure =
      point.length > 2 && point[2] > 0 && point[2] !== 0.5 ? point[2] : null
    context.lineWidth = pressure === null ? base : base * (0.5 + pressure)
    context.beginPath()
    context.moveTo(previous[0], previous[1])
    context.lineTo(point[0], point[1])
    context.stroke()
  }
  if (stroke.points.length === 1) {
    const point = stroke.points[0]
    context.lineWidth = base
    context.beginPath()
    context.moveTo(point[0], point[1])
    context.lineTo(point[0] + 0.5, point[1] + 0.5)
    context.stroke()
  }
}

function paintStrokes(context: CanvasRenderingContext2D, strokes: Stroke[]): void {
  for (const stroke of strokes) {
    if (stroke.points.length === 0) {
      continue
    }
    drawStrokeSegment(context, stroke)
  }
}

export function renderStrokes(
  canvas: HTMLCanvasElement,
  strokes: Stroke[],
  view: ViewState,
  viewport: { width: number; height: number }
): void {
  canvas.width = Math.max(1, Math.round(viewport.width * DPR))
  canvas.height = Math.max(1, Math.round(viewport.height * DPR))
  const context = canvas.getContext('2d')
  if (!context) {
    return
  }
  const scale = DPR * view.zoom
  context.setTransform(scale, 0, 0, scale, -view.x * scale, -view.y * scale)
  context.fillStyle = '#ffffff'
  context.fillRect(view.x, view.y, viewport.width / view.zoom, viewport.height / view.zoom)
  if (view.zoom >= 0.5) {
    context.fillStyle = '#d4d4d8'
    const startX = Math.ceil(view.x / GRID_STEP) * GRID_STEP
    const startY = Math.ceil(view.y / GRID_STEP) * GRID_STEP
    for (let gx = startX; gx < view.x + viewport.width / view.zoom; gx += GRID_STEP) {
      for (let gy = startY; gy < view.y + viewport.height / view.zoom; gy += GRID_STEP) {
        context.beginPath()
        context.arc(gx, gy, 1.25 / view.zoom, 0, Math.PI * 2)
        context.fill()
      }
    }
  }
  paintStrokes(context, strokes)
}

export function exportDrawing(
  strokes: Stroke[],
  padding = EXPORT_PADDING
): { dataUrl: string; view: ViewBox } | null {
  const bounds = strokeBounds(strokes, padding)
  if (bounds === null) {
    return null
  }
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.ceil(bounds.width))
  canvas.height = Math.max(1, Math.ceil(bounds.height))
  const context = canvas.getContext('2d')
  if (!context) {
    return null
  }
  context.fillStyle = '#ffffff'
  context.fillRect(0, 0, canvas.width, canvas.height)
  context.translate(-bounds.x, -bounds.y)
  paintStrokes(context, strokes)
  return { dataUrl: canvas.toDataURL('image/png'), view: bounds }
}

export function strokesToPng(strokes: Stroke[]): string | null {
  return exportDrawing(strokes)?.dataUrl ?? null
}

function strokeDistanceToSegment(
  point: number[],
  a: number[],
  b: number[]
): number {
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const lengthSquared = dx * dx + dy * dy
  if (lengthSquared === 0) {
    const ex = point[0] - a[0]
    const ey = point[1] - a[1]
    return Math.sqrt(ex * ex + ey * ey)
  }
  let t = ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / lengthSquared
  t = Math.max(0, Math.min(1, t))
  const px = a[0] + t * dx - point[0]
  const py = a[1] + t * dy - point[1]
  return Math.sqrt(px * px + py * py)
}

function strokeHit(stroke: Stroke, point: number[], radius: number): boolean {
  if (stroke.points.length === 1) {
    const target = stroke.points[0]
    const ex = point[0] - target[0]
    const ey = point[1] - target[1]
    return Math.sqrt(ex * ex + ey * ey) <= radius
  }
  for (let index = 1; index < stroke.points.length; index += 1) {
    if (strokeDistanceToSegment(point, stroke.points[index - 1], stroke.points[index]) <= radius) {
      return true
    }
  }
  return false
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false
  }
  return (
    target.isContentEditable ||
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)
  )
}

export function DrawCanvas({
  strokes,
  onChange,
  fullscreen,
  onToggleFullscreen,
  fillContainer = false,
  focus = null,
}: {
  strokes: Stroke[]
  onChange: (strokes: Stroke[]) => void
  fullscreen?: boolean
  onToggleFullscreen?: () => void
  fillContainer?: boolean
  focus?: ViewBox | null
}) {
  const { t } = useTranslation()
  const viewportRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const drawing = useRef(false)
  const [current, setCurrent] = useState<number[][] | null>(null)
  const [tool, setTool] = useState<StrokeTool>('pen')
  const [color, setColor] = useState<string>(INK_COLORS[0])
  const [penWidth, setPenWidth] = useState<number>(PEN_WIDTHS[1])
  const [redoStack, setRedoStack] = useState<Stroke[]>([])
  const [view, setView] = useState<ViewState>({ x: 0, y: 0, zoom: 1 })
  const [size, setSize] = useState(DEFAULT_VIEWPORT)
  const [panning, setPanning] = useState(false)
  const strokesRef = useRef(strokes)
  strokesRef.current = strokes
  const viewRef = useRef(view)
  viewRef.current = view
  const sizeRef = useRef(size)
  sizeRef.current = size
  const spaceRef = useRef(false)
  const panRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    viewX: number
    viewY: number
  } | null>(null)

  useEffect(() => {
    const element = viewportRef.current
    const measure = () => {
      if (!element) {
        return
      }
      const rect = element.getBoundingClientRect()
      if (rect.width > 0 && rect.height > 0) {
        setSize({ width: rect.width, height: rect.height })
      }
    }
    if (!element || typeof ResizeObserver === 'undefined') {
      return
    }
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    window.addEventListener('resize', measure)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [])

  useEffect(() => {
    if (focus === null) {
      return
    }
    setView(viewFromFocus(focus, sizeRef.current))
  }, [focus])

  const zoomAt = useCallback((factor: number, clientX: number, clientY: number) => {
    const element = viewportRef.current
    if (!element) {
      return
    }
    const rect = element.getBoundingClientRect()
    const currentView = viewRef.current
    const px = clientX - rect.left
    const py = clientY - rect.top
    const zoom = clampZoom(currentView.zoom * factor)
    if (zoom === currentView.zoom) {
      return
    }
    setView({
      x: currentView.x + px / currentView.zoom - px / zoom,
      y: currentView.y + py / currentView.zoom - py / zoom,
      zoom,
    })
  }, [])

  useEffect(() => {
    const element = viewportRef.current
    if (!element) {
      return
    }
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const dy = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY
      zoomAt(Math.exp(-dy * 0.002), event.clientX, event.clientY)
    }
    element.addEventListener('wheel', onWheel, { passive: false })
    return () => element.removeEventListener('wheel', onWheel)
  }, [zoomAt])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === ' ' && !event.repeat && !isEditableTarget(event.target)) {
        spaceRef.current = true
      }
    }
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key === ' ') {
        spaceRef.current = false
      }
    }
    const onBlur = () => {
      spaceRef.current = false
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    window.addEventListener('blur', onBlur)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
      window.removeEventListener('blur', onBlur)
    }
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) {
      return
    }
    renderStrokes(
      canvas,
      current ? [...strokes, { points: current, color, width: penWidth }] : strokes,
      view,
      size
    )
  }, [strokes, current, color, penWidth, view, size])

  const zoomBy = (factor: number) => {
    const rect = viewportRef.current?.getBoundingClientRect()
    zoomAt(factor, (rect?.left ?? 0) + size.width / 2, (rect?.top ?? 0) + size.height / 2)
  }

  const fitToContent = () => {
    const bounds = strokeBounds(strokesRef.current)
    if (bounds === null) {
      setView({ x: 0, y: 0, zoom: 1 })
      return
    }
    setView(fitView(bounds, sizeRef.current))
  }

  const resetToActualSize = () => {
    const bounds = strokeBounds(strokesRef.current)
    const viewport = sizeRef.current
    if (bounds === null) {
      setView({ x: 0, y: 0, zoom: 1 })
      return
    }
    setView({
      x: bounds.x + bounds.width / 2 - viewport.width / 2,
      y: bounds.y + bounds.height / 2 - viewport.height / 2,
      zoom: 1,
    })
  }

  const position = (event: React.PointerEvent<HTMLCanvasElement>): number[] => {
    const rect = event.currentTarget.getBoundingClientRect()
    const currentView = viewRef.current
    return [
      currentView.x + (event.clientX - rect.left) / currentView.zoom,
      currentView.y + (event.clientY - rect.top) / currentView.zoom,
      event.pressure,
    ]
  }

  const eraseAt = (point: number[]) => {
    const radius = penWidth + 12
    const kept = strokesRef.current.filter((stroke) => !strokeHit(stroke, point, radius))
    if (kept.length !== strokesRef.current.length) {
      setRedoStack((stack) => [
        ...stack,
        ...strokesRef.current.filter((stroke) => !kept.includes(stroke)),
      ])
      onChange(kept)
    }
  }

  const finishStroke = () => {
    if (current && current.length > 0) {
      setRedoStack([])
      onChange([...strokesRef.current, { points: current, color, width: penWidth, tool: 'pen' }])
    }
    setCurrent(null)
    drawing.current = false
  }

  const panToolActive = tool === 'pan' || spaceRef.current
  const spaceHeld = spaceRef.current

  const toolbarButton = (
    active: boolean
  ): string =>
    cn(
      'rounded p-1.5',
      active ? 'bg-subtle text-foreground' : 'text-muted-foreground hover:text-foreground'
    )

  return (
    <div
      className={
        fillContainer ? 'flex h-full min-h-0 flex-1 flex-col gap-2' : 'space-y-2'
      }
    >
      <div
        className="bg-surface border-border flex flex-wrap items-center gap-1 rounded-md border p-1"
        role="toolbar"
        aria-label={t('notes.canvasTools')}
      >
        <button
          type="button"
          title={t('notes.toolPen')}
          aria-label={t('notes.toolPen')}
          aria-pressed={tool === 'pen'}
          className={toolbarButton(tool === 'pen')}
          onClick={() => setTool('pen')}
        >
          <Pen className="size-4" aria-hidden />
        </button>
        <button
          type="button"
          title={t('notes.toolEraser')}
          aria-label={t('notes.toolEraser')}
          aria-pressed={tool === 'eraser'}
          className={toolbarButton(tool === 'eraser')}
          onClick={() => setTool('eraser')}
        >
          <Eraser className="size-4" aria-hidden />
        </button>
        <button
          type="button"
          title={t('notes.toolPan')}
          aria-label={t('notes.toolPan')}
          aria-pressed={tool === 'pan'}
          className={toolbarButton(tool === 'pan')}
          onClick={() => setTool('pan')}
        >
          <Hand className="size-4" aria-hidden />
        </button>
        <span className="bg-border mx-1 h-5 w-px" aria-hidden />
        {INK_COLORS.map((ink) => (
          <button
            key={ink}
            type="button"
            title={t('notes.toolColor')}
            aria-label={t('notes.toolColor')}
            aria-pressed={color === ink}
            className={cn(
              'rounded-full border-2 p-0.5',
              color === ink ? 'border-foreground' : 'border-transparent'
            )}
            onClick={() => {
              setColor(ink)
              setTool('pen')
            }}
          >
            <span
              className="block size-4 rounded-full"
              style={{ backgroundColor: ink }}
              aria-hidden
            />
          </button>
        ))}
        <span className="bg-border mx-1 h-5 w-px" aria-hidden />
        {PEN_WIDTHS.map((entry) => (
          <button
            key={entry}
            type="button"
            title={t('notes.toolWidth', { width: entry })}
            aria-label={t('notes.toolWidth', { width: entry })}
            aria-pressed={penWidth === entry}
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded',
              penWidth === entry
                ? 'bg-subtle text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            )}
            onClick={() => {
              setPenWidth(entry)
              setTool('pen')
            }}
          >
            <span
              className="block rounded-full bg-current"
              style={{ width: entry + 2, height: entry + 2 }}
              aria-hidden
            />
          </button>
        ))}
        <span className="bg-border mx-1 h-5 w-px" aria-hidden />
        <button
          type="button"
          title={t('notes.undoStroke')}
          aria-label={t('notes.undoStroke')}
          disabled={strokes.length === 0}
          className="text-muted-foreground hover:text-foreground rounded p-1.5 disabled:opacity-40"
          onClick={() => {
            const next = strokes.slice(0, -1)
            const removed = strokes[strokes.length - 1]
            if (removed) {
              setRedoStack((stack) => [...stack, removed])
            }
            onChange(next)
          }}
        >
          <Undo2 className="size-4" aria-hidden />
        </button>
        <button
          type="button"
          title={t('notes.redoStroke')}
          aria-label={t('notes.redoStroke')}
          disabled={redoStack.length === 0}
          className="text-muted-foreground hover:text-foreground rounded p-1.5 disabled:opacity-40"
          onClick={() => {
            const restored = redoStack[redoStack.length - 1]
            if (restored) {
              setRedoStack((stack) => stack.slice(0, -1))
              onChange([...strokes, restored])
            }
          }}
        >
          <Redo2 className="size-4" aria-hidden />
        </button>
        <button
          type="button"
          title={t('notes.clearCanvas')}
          aria-label={t('notes.clearCanvas')}
          disabled={strokes.length === 0}
          className="text-muted-foreground hover:text-foreground rounded p-1.5 disabled:opacity-40"
          onClick={() => {
            if (window.confirm(t('notes.confirmClearCanvas'))) {
              setRedoStack((stack) => [...stack, ...strokes])
              onChange([])
            }
          }}
        >
          <Trash2 className="size-4" aria-hidden />
        </button>
        {onToggleFullscreen ? (
          <button
            type="button"
            title={fullscreen ? t('notes.exitFullscreen') : t('notes.fullscreen')}
            aria-label={fullscreen ? t('notes.exitFullscreen') : t('notes.fullscreen')}
            aria-pressed={fullscreen === true}
            className={cn('ml-auto', toolbarButton(fullscreen === true))}
            onClick={onToggleFullscreen}
          >
            {fullscreen ? (
              <Minimize2 className="size-4" aria-hidden />
            ) : (
              <Maximize2 className="size-4" aria-hidden />
            )}
          </button>
        ) : null}
      </div>
      <div
        ref={viewportRef}
        className={cn(
          'bg-surface border-border relative touch-none overflow-hidden rounded-md border',
          fillContainer && 'min-h-0 w-full flex-1'
        )}
        style={fillContainer ? undefined : { height: '480px' }}
      >
        <canvas
          ref={canvasRef}
          className={cn(
            'absolute inset-0 block h-full w-full',
            panning || (spaceHeld && drawing.current)
              ? 'cursor-grabbing'
              : panToolActive
                ? 'cursor-grab'
                : 'cursor-crosshair'
          )}
          aria-label={t('notes.canvasLabel')}
          onPointerDown={(event) => {
            if (event.button === 1 || spaceRef.current || tool === 'pan') {
              event.preventDefault()
              try {
                event.currentTarget.setPointerCapture(event.pointerId)
              } catch {
                void 0
              }
              panRef.current = {
                pointerId: event.pointerId,
                startX: event.clientX,
                startY: event.clientY,
                viewX: viewRef.current.x,
                viewY: viewRef.current.y,
              }
              setPanning(true)
              return
            }
            if (event.button !== 0) {
              return
            }
            try {
              event.currentTarget.setPointerCapture(event.pointerId)
            } catch {
              void 0
            }
            drawing.current = true
            const point = position(event)
            if (tool === 'eraser') {
              eraseAt(point)
            } else {
              setCurrent([point])
            }
          }}
          onPointerMove={(event) => {
            const pan = panRef.current
            if (pan !== null && pan.pointerId === event.pointerId) {
              setView({
                ...viewRef.current,
                x: pan.viewX - (event.clientX - pan.startX) / viewRef.current.zoom,
                y: pan.viewY - (event.clientY - pan.startY) / viewRef.current.zoom,
              })
              return
            }
            if (!drawing.current) {
              return
            }
            const point = position(event)
            if (tool === 'eraser') {
              eraseAt(point)
            } else {
              setCurrent((points) => (points ? [...points, point] : [point]))
            }
          }}
          onPointerUp={(event) => {
            if (panRef.current !== null && panRef.current.pointerId === event.pointerId) {
              panRef.current = null
              setPanning(false)
              return
            }
            finishStroke()
          }}
          onPointerCancel={(event) => {
            if (panRef.current !== null && panRef.current.pointerId === event.pointerId) {
              panRef.current = null
              setPanning(false)
              return
            }
            finishStroke()
          }}
          onPointerLeave={() => {
            if (panRef.current === null) {
              finishStroke()
            }
          }}
          onAuxClick={(event) => {
            if (event.button === 1) {
              event.preventDefault()
            }
          }}
        />
        <div
          className="bg-surface/95 border-border absolute bottom-2 left-2 flex items-center gap-0.5 rounded-full border px-1 py-0.5 shadow-sm"
          role="toolbar"
          aria-label={t('notes.canvasNavigation')}
        >
          <button
            type="button"
            title={t('notes.zoomOut')}
            aria-label={t('notes.zoomOut')}
            className="text-muted-foreground hover:text-foreground rounded-full p-1.5"
            onClick={() => zoomBy(1 / 1.25)}
          >
            <ZoomOut className="size-4" aria-hidden />
          </button>
          <button
            type="button"
            title={t('notes.zoomActual')}
            aria-label={t('notes.zoomLevel')}
            data-testid="canvas-zoom"
            className="text-foreground hover:bg-subtle w-14 rounded-full py-0.5 text-center text-xs font-medium tabular-nums"
            onClick={resetToActualSize}
          >
            {Math.round(view.zoom * 100)}%
          </button>
          <button
            type="button"
            title={t('notes.zoomIn')}
            aria-label={t('notes.zoomIn')}
            className="text-muted-foreground hover:text-foreground rounded-full p-1.5"
            onClick={() => zoomBy(1.25)}
          >
            <ZoomIn className="size-4" aria-hidden />
          </button>
          <span className="bg-border mx-0.5 h-4 w-px" aria-hidden />
          <button
            type="button"
            title={t('notes.zoomFit')}
            aria-label={t('notes.zoomFit')}
            className="text-muted-foreground hover:text-foreground rounded-full p-1.5"
            onClick={fitToContent}
          >
            <Scan className="size-4" aria-hidden />
          </button>
          <button
            type="button"
            title={t('notes.zoomActual')}
            aria-label={t('notes.zoomActual')}
            className="text-muted-foreground hover:text-foreground rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
            onClick={resetToActualSize}
          >
            1:1
          </button>
        </div>
      </div>
    </div>
  )
}

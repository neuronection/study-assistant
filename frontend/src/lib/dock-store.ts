import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { create } from 'zustand'

import { CHAT_WIDTH_BOUNDS, useChatStore } from './chat-store'
import { storageKeys } from './constants'

export const FILE_WIDTH_BOUNDS = {
  min: 320,
  max: 760,
  default: 480,
} as const

export const RAIL_LAYOUT = {
  sidebarWidth: 240,
  mainMinWidth: 360,
} as const

const FILE_WIDTH_KEY = storageKeys.fileWidth

function readFileWidth(): number {
  try {
    const raw = window.localStorage.getItem(FILE_WIDTH_KEY)
    if (raw) {
      const value = Number(raw)
      if (
        Number.isFinite(value) &&
        value >= FILE_WIDTH_BOUNDS.min &&
        value <= FILE_WIDTH_BOUNDS.max
      ) {
        return value
      }
    }
  } catch {
    return FILE_WIDTH_BOUNDS.default
  }
  return FILE_WIDTH_BOUNDS.default
}

function saveFileWidth(width: number): void {
  try {
    window.localStorage.setItem(FILE_WIDTH_KEY, String(width))
  } catch {
    return
  }
}

function clampWidth(width: number, bounds: { min: number; max: number }): number {
  return Math.min(bounds.max, Math.max(bounds.min, Math.round(width)))
}

interface DockState {
  fileWidth: number
  setFileWidth: (width: number) => void
  persistFileWidth: () => void
}

export const useDockStore = create<DockState>((set, get) => ({
  fileWidth: readFileWidth(),
  setFileWidth: (width) => set({ fileWidth: clampWidth(width, FILE_WIDTH_BOUNDS) }),
  persistFileWidth: () => saveFileWidth(get().fileWidth),
}))

export interface RailLayout {
  fileWidth: number | null
  chatWidth: number | null
  chatDeferred: boolean
}

export function resolveRailWidths(input: {
  viewportWidth: number
  fileOpen: boolean
  chatOpen: boolean
  fileWidth: number
  chatWidth: number
}): RailLayout {
  const budget = Math.max(
    0,
    input.viewportWidth - RAIL_LAYOUT.sidebarWidth - RAIL_LAYOUT.mainMinWidth
  )
  const fileDesired = input.fileOpen
    ? clampWidth(input.fileWidth, FILE_WIDTH_BOUNDS)
    : null
  const chatDesired = input.chatOpen
    ? clampWidth(input.chatWidth, CHAT_WIDTH_BOUNDS)
    : null
  if (fileDesired !== null && chatDesired !== null) {
    if (FILE_WIDTH_BOUNDS.min + CHAT_WIDTH_BOUNDS.min > budget) {
      return {
        fileWidth: Math.min(fileDesired, Math.max(FILE_WIDTH_BOUNDS.min, budget)),
        chatWidth: null,
        chatDeferred: true,
      }
    }
    if (fileDesired + chatDesired > budget) {
      const chat = clampWidth(chatDesired, {
        min: CHAT_WIDTH_BOUNDS.min,
        max: budget - FILE_WIDTH_BOUNDS.min,
      })
      const file = clampWidth(fileDesired, {
        min: FILE_WIDTH_BOUNDS.min,
        max: budget - chat,
      })
      return { fileWidth: file, chatWidth: chat, chatDeferred: false }
    }
    return { fileWidth: fileDesired, chatWidth: chatDesired, chatDeferred: false }
  }
  return {
    fileWidth:
      fileDesired === null
        ? null
        : Math.min(fileDesired, Math.max(FILE_WIDTH_BOUNDS.min, budget)),
    chatWidth:
      chatDesired === null
        ? null
        : Math.min(chatDesired, Math.max(CHAT_WIDTH_BOUNDS.min, budget)),
    chatDeferred: false,
  }
}

export function useViewportWidth(): number {
  const [width, setWidth] = useState(() =>
    typeof window === 'undefined' ? 1280 : window.innerWidth
  )
  useEffect(() => {
    const onResize = () => setWidth(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return width
}

export function useRailLayout(fileOpen: boolean): RailLayout {
  const viewportWidth = useViewportWidth()
  const chatOpen = useChatStore((state) => state.open)
  const chatWidth = useChatStore((state) => state.width)
  const fileWidth = useDockStore((state) => state.fileWidth)
  return resolveRailWidths({
    viewportWidth,
    fileOpen,
    chatOpen,
    fileWidth,
    chatWidth,
  })
}

export function useChatFitsAlongsideFile(fileOpen: boolean): boolean {
  const viewportWidth = useViewportWidth()
  const chatWidth = useChatStore((state) => state.width)
  const fileWidth = useDockStore((state) => state.fileWidth)
  if (!fileOpen) {
    return true
  }
  return !resolveRailWidths({
    viewportWidth,
    fileOpen: true,
    chatOpen: true,
    fileWidth,
    chatWidth,
  }).chatDeferred
}

export function useRailResize(opts: {
  width: number
  setWidth: (width: number) => void
  persist: () => void
}): {
  onResizeStart: (event: ReactPointerEvent<HTMLDivElement>) => void
  onResizeMove: (event: ReactPointerEvent<HTMLDivElement>) => void
  onResizeEnd: () => void
} {
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null)
  const onResizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    dragRef.current = { startX: event.clientX, startWidth: opts.width }
    if (typeof event.currentTarget.setPointerCapture === 'function') {
      event.currentTarget.setPointerCapture(event.pointerId)
    }
  }
  const onResizeMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag) return
    opts.setWidth(drag.startWidth + (drag.startX - event.clientX))
  }
  const onResizeEnd = () => {
    if (!dragRef.current) return
    dragRef.current = null
    opts.persist()
  }
  return { onResizeStart, onResizeMove, onResizeEnd }
}

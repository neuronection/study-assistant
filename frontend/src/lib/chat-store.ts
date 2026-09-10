import { create } from 'zustand'

import type { ChatAttachmentInput } from '@/lib/api'
import { storageKeys } from '@/lib/constants'

export interface ChatSessionRef {
  id: number
  publicId: string
}

export type PendingAskAttachment = ChatAttachmentInput & { title?: string }

export interface PendingAsk {
  content: string
  attachments?: PendingAskAttachment[]
  mode: 'prefill' | 'send'
}

export const CHAT_WIDTH_BOUNDS = {
  min: 320,
  max: 720,
  default: 384,
} as const

const CHAT_WIDTH_KEY = storageKeys.chatWidth

function readChatWidth(): number {
  try {
    const raw = window.localStorage.getItem(CHAT_WIDTH_KEY)
    if (raw) {
      const value = Number(raw)
      if (
        Number.isFinite(value) &&
        value >= CHAT_WIDTH_BOUNDS.min &&
        value <= CHAT_WIDTH_BOUNDS.max
      ) {
        return value
      }
    }
  } catch {
    return CHAT_WIDTH_BOUNDS.default
  }
  return CHAT_WIDTH_BOUNDS.default
}

function saveChatWidth(width: number): void {
  try {
    window.localStorage.setItem(CHAT_WIDTH_KEY, String(width))
  } catch {
    return
  }
}

function clampChatWidth(width: number): number {
  return Math.min(
    CHAT_WIDTH_BOUNDS.max,
    Math.max(CHAT_WIDTH_BOUNDS.min, Math.round(width)),
  )
}

interface ChatState {
  open: boolean
  session: ChatSessionRef | null
  pendingSend: PendingAsk | null
  viewerAsks: Record<number, ChatSessionRef>
  selectionAsks: Record<string, ChatSessionRef>
  width: number
  setOpen: (open: boolean) => void
  openSession: (session: ChatSessionRef) => void
  setSession: (session: ChatSessionRef | null) => void
  queueSend: (ask: PendingAsk) => void
  clearPendingSend: () => void
  setViewerAsk: (materialId: number, session: ChatSessionRef) => void
  clearViewerAsk: (materialId?: number) => void
  setSelectionAsk: (key: string, session: ChatSessionRef) => void
  clearSelectionAsk: (key?: string) => void
  setChatWidth: (width: number) => void
  persistChatWidth: () => void
}

export const useChatStore = create<ChatState>((set, get) => ({
  open: false,
  session: null,
  pendingSend: null,
  viewerAsks: {},
  selectionAsks: {},
  width: readChatWidth(),
  setOpen: (open) => set(open ? { open } : { open: false, session: null }),
  openSession: (session) => set({ open: true, session }),
  setSession: (session) => set({ session }),
  queueSend: (ask) => set({ pendingSend: ask }),
  clearPendingSend: () => set({ pendingSend: null }),
  setViewerAsk: (materialId, session) =>
    set((state) => ({ viewerAsks: { ...state.viewerAsks, [materialId]: session } })),
  clearViewerAsk: (materialId) =>
    set((state) => {
      if (materialId === undefined) {
        return { viewerAsks: {} }
      }
      const next = { ...state.viewerAsks }
      delete next[materialId]
      return { viewerAsks: next }
    }),
  setSelectionAsk: (key, session) =>
    set((state) => ({ selectionAsks: { ...state.selectionAsks, [key]: session } })),
  clearSelectionAsk: (key) =>
    set((state) => {
      if (key === undefined) {
        return { selectionAsks: {} }
      }
      const next = { ...state.selectionAsks }
      delete next[key]
      return { selectionAsks: next }
    }),
  setChatWidth: (width) => set({ width: clampChatWidth(width) }),
  persistChatWidth: () => saveChatWidth(get().width),
}))

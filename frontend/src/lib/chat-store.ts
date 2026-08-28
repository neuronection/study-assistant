import { create } from 'zustand'

export interface ChatSessionRef {
  id: number
  publicId: string
}

interface ChatState {
  open: boolean
  session: ChatSessionRef | null
  setOpen: (open: boolean) => void
  openSession: (session: ChatSessionRef) => void
  setSession: (session: ChatSessionRef | null) => void
}

export const useChatStore = create<ChatState>((set) => ({
  open: false,
  session: null,
  setOpen: (open) => set(open ? { open } : { open: false, session: null }),
  openSession: (session) => set({ open: true, session }),
  setSession: (session) => set({ session }),
}))

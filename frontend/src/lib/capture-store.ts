import { create } from 'zustand'

export interface SnapTarget {
  noteId: number
  title: string
  insert: (pngBase64: string) => Promise<number | null>
  remove: (drawingId: number) => Promise<void>
}

interface CaptureState {
  open: boolean
  openCapture: () => void
  closeCapture: () => void
  snapOpen: boolean
  snapTarget: SnapTarget | null
  openSnap: () => void
  closeSnap: () => void
  setSnapTarget: (target: SnapTarget | null) => void
}

export const useCaptureStore = create<CaptureState>((set) => ({
  open: false,
  openCapture: () => set({ open: true }),
  closeCapture: () => set({ open: false }),
  snapOpen: false,
  snapTarget: null,
  openSnap: () => set({ snapOpen: true }),
  closeSnap: () => set({ snapOpen: false }),
  setSnapTarget: (target) => set({ snapTarget: target }),
}))

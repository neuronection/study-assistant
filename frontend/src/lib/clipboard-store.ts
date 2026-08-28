import { create } from 'zustand'

export type ClipboardMode = 'copy' | 'cut'

export interface LibraryClipboard {
  kind: 'library'
  courseId: number
  folderIds: number[]
  materialIds: number[]
  mode: ClipboardMode
}

interface ClipboardState {
  item: LibraryClipboard | null
  set: (item: LibraryClipboard) => void
  clear: () => void
}

export const useClipboardStore = create<ClipboardState>((set) => ({
  item: null,
  set: (item) => set({ item }),
  clear: () => set({ item: null }),
}))

import { create } from 'zustand'

export type ClipboardMode = 'copy' | 'cut'

export interface LibraryClipboard {
  kind: 'library'
  courseId: string
  folderIds: string[]
  materialIds: string[]
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

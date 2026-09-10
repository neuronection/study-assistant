import { create } from 'zustand'

interface ImportUrlState {
  open: boolean
  openImport: () => void
  closeImport: () => void
}

export const useImportUrlStore = create<ImportUrlState>((set) => ({
  open: false,
  openImport: () => set({ open: true }),
  closeImport: () => set({ open: false }),
}))

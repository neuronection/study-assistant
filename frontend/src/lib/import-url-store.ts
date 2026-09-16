import { create } from 'zustand'

interface ImportUrlState {
  open: boolean
  url: string
  nodeId: number | null
  openImport: (url?: string, nodeId?: number | null) => void
  closeImport: () => void
}

export const useImportUrlStore = create<ImportUrlState>((set) => ({
  open: false,
  url: '',
  nodeId: null,
  openImport: (url?: string, nodeId?: number | null) =>
    set({ open: true, url: url ?? '', nodeId: nodeId ?? null }),
  closeImport: () => set({ open: false, url: '', nodeId: null }),
}))

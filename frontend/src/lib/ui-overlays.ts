import { useEffect } from 'react'
import { create } from 'zustand'

interface OverlayState {
  token: number
  closeFloatings: () => void
}

export const useOverlayStore = create<OverlayState>((set) => ({
  token: 0,
  closeFloatings: () => set((state) => ({ token: state.token + 1 })),
}))

export function useCloseFloatings() {
  const closeFloatings = useOverlayStore((state) => state.closeFloatings)
  useEffect(() => {
    closeFloatings()
  }, [closeFloatings])
}

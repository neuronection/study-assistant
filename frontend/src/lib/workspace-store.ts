import { create } from 'zustand'
import { storageKeys } from '@/lib/constants'

const STORAGE_KEY = storageKeys.courseId

function readStoredCourse(): string | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw === null || raw.length === 0) {
      return null
    }
    return raw
  } catch {
    return null
  }
}

interface WorkspaceState {
  courseId: string | null
  hydrated: boolean
  hydrate: () => void
  setCourse: (courseId: string | null) => void
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  courseId: readStoredCourse(),
  hydrated: false,
  hydrate: () => set({ courseId: readStoredCourse(), hydrated: true }),
  setCourse: (courseId) => {
    set({ courseId, hydrated: true })
    try {
      if (courseId === null) {
        window.localStorage.removeItem(STORAGE_KEY)
      } else {
        window.localStorage.setItem(STORAGE_KEY, String(courseId))
      }
    } catch {
      // localStorage may be unavailable in some webview builds; in-memory switch still works
    }
  },
}))

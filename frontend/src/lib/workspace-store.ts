import { create } from 'zustand'

const STORAGE_KEY = 'ca-course-id'

function readStoredCourse(): number | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw === null) {
      return null
    }
    const value = Number(raw)
    return Number.isFinite(value) && value > 0 ? value : null
  } catch {
    return null
  }
}

interface WorkspaceState {
  courseId: number | null
  hydrated: boolean
  hydrate: () => void
  setCourse: (courseId: number | null) => void
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

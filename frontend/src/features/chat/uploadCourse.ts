import type { Course } from '@/lib/api'

export const UNSORTED_COURSE_TITLE = 'Unsorted'

export function resolveUploadCourse(courses: Course[]): Course | null {
  const active = courses.filter((course) => course.archived_at === null)
  const unsorted = active.find((course) => course.title === UNSORTED_COURSE_TITLE)
  if (unsorted !== undefined) {
    return unsorted
  }
  return active.length === 1 ? (active[0] ?? null) : null
}

export function sanitizeFolderTitle(title: string): string {
  const cleaned = title
    .replace(/[\\/:*?"<>|#]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 60)
    .trim()
  return cleaned.length > 0 ? cleaned : 'Chat'
}

export function chatUploadFolderName(title: string, sessionId: number): string {
  return `${sanitizeFolderTitle(title)} (#${sessionId})`
}

export function chatUploadFolderPattern(sessionId: number): RegExp {
  return new RegExp(` \\(#${sessionId}\\)$`)
}

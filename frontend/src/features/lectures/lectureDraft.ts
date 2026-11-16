export interface LectureDraft {
  sessionId: string
  courseId: string
  nodeId: string | null
  title: string
  mime: string
  retention: string
  nextSeq: number
  updatedAt: number
}

const KEY = 'sa-lecture-draft'

export function loadLectureDraft(): LectureDraft | null {
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) {
      return null
    }
    const value = JSON.parse(raw) as Partial<LectureDraft>
    if (
      typeof value.sessionId !== 'string' ||
      typeof value.courseId !== 'string' ||
      typeof value.title !== 'string' ||
      typeof value.mime !== 'string' ||
      typeof value.nextSeq !== 'number'
    ) {
      return null
    }
    return {
      sessionId: value.sessionId,
      courseId: value.courseId,
      nodeId: typeof value.nodeId === 'string' ? value.nodeId : null,
      title: value.title,
      mime: value.mime,
      retention: typeof value.retention === 'string' ? value.retention : 'audio_and_text',
      nextSeq: value.nextSeq,
      updatedAt: typeof value.updatedAt === 'number' ? value.updatedAt : 0,
    }
  } catch {
    return null
  }
}

export function saveLectureDraft(draft: LectureDraft): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(draft))
  } catch {
    // best-effort; the live upload still runs
  }
}

export function clearLectureDraft(): void {
  try {
    window.localStorage.removeItem(KEY)
  } catch {
    // ignore storage failures
  }
}

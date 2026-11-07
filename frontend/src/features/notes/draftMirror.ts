export interface DraftMirror {
  body_md: string
  savedAt: string
}

export function draftKey(noteId: string): string {
  return `sa-note-draft:${noteId}`
}

export function readMirror(noteId: string): DraftMirror | null {
  try {
    const raw = localStorage.getItem(draftKey(noteId))
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as Partial<DraftMirror>
    if (typeof parsed.body_md !== 'string' || typeof parsed.savedAt !== 'string') {
      return null
    }
    return { body_md: parsed.body_md, savedAt: parsed.savedAt }
  } catch {
    return null
  }
}

export function writeMirror(noteId: string, bodyMd: string): void {
  try {
    localStorage.setItem(
      draftKey(noteId),
      JSON.stringify({ body_md: bodyMd, savedAt: new Date().toISOString() })
    )
  } catch {
    return
  }
}

export function clearMirror(noteId: string): void {
  try {
    localStorage.removeItem(draftKey(noteId))
  } catch {
    return
  }
}

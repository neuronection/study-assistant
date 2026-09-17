export type WorkspaceSearch = { tab?: string; note?: number; material?: number }

export function openNote(noteId: number) {
  return (prev: WorkspaceSearch): WorkspaceSearch => ({ ...prev, note: noteId })
}

export function closeNote(prev: WorkspaceSearch): WorkspaceSearch {
  const rest: WorkspaceSearch = { ...prev }
  delete rest.note
  return rest
}

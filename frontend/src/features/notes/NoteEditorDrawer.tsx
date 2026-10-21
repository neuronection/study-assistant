export type WorkspaceSearch = { tab?: string; note?: string; material?: string }

export function openNote(noteId: string) {
  return (prev: WorkspaceSearch): WorkspaceSearch => ({ ...prev, note: noteId })
}

export function closeNote(prev: WorkspaceSearch): WorkspaceSearch {
  const rest: WorkspaceSearch = { ...prev }
  delete rest.note
  return rest
}

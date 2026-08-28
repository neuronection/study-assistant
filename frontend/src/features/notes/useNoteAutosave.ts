import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react'

import { ApiError, updateNote, type NoteDetailInfo } from '@/lib/api'

import { clearMirror, readMirror, writeMirror, type DraftMirror } from './draftMirror'

export const AUTOSAVE_DEBOUNCE_MS = 1500
export const AUTOSAVE_MAX_WAIT_MS = 10_000
export const AUTOSAVE_RETRY_MS = 5000

export type AutosaveStatus = 'idle' | 'pending' | 'saving' | 'saved' | 'error' | 'conflict'

export function noteBodyMd(note: NoteDetailInfo): string {
  let result = ''
  for (const block of note.body) {
    let part: string
    if (block.type === 'drawing' && typeof block.drawing_id === 'number') {
      part = `![drawing](ca-drawing://${block.drawing_id})`
    } else {
      part = block.md ?? ''
    }
    if (part === '') {
      continue
    }
    if (result === '') {
      result = part
    } else if (!(result.endsWith('\n') || part.startsWith('\n'))) {
      result += `\n\n${part}`
    } else {
      result += part
    }
  }
  return result
}

export function useNoteAutosave({
  noteId,
  note,
  draft,
  setDraft,
  onSaved,
  onError,
  reload,
}: {
  noteId: number
  note: NoteDetailInfo | undefined
  draft: string | null
  setDraft: Dispatch<SetStateAction<string | null>>
  onSaved: (updated: NoteDetailInfo) => void
  onError: (message: string) => void
  reload: () => void
}): {
  dirty: boolean
  status: AutosaveStatus
  conflict: boolean
  recovery: DraftMirror | null
  saveNow: (options?: { force?: boolean }) => void
  restoreRecovery: () => void
  discardRecovery: () => void
  resolveConflictReload: () => void
} {
  const [conflict, setConflict] = useState(false)
  const [saving, setSaving] = useState(false)
  const [failed, setFailed] = useState(false)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const [recovery, setRecovery] = useState<DraftMirror | null>(null)

  const savedBody = note === undefined ? '' : noteBodyMd(note)
  const dirty = draft !== null && draft !== savedBody

  const draftRef = useRef<string | null>(draft)
  draftRef.current = draft
  const noteRef = useRef<NoteDetailInfo | undefined>(note)
  noteRef.current = note
  const dirtyRef = useRef(dirty)
  dirtyRef.current = dirty
  const savingRef = useRef(saving)
  savingRef.current = saving
  const conflictRef = useRef(conflict)
  conflictRef.current = conflict
  const recoveryRef = useRef<DraftMirror | null>(recovery)
  recoveryRef.current = recovery
  const onSavedRef = useRef(onSaved)
  onSavedRef.current = onSaved
  const onErrorRef = useRef(onError)
  onErrorRef.current = onError

  const debounceTimer = useRef<number | null>(null)
  const maxTimer = useRef<number | null>(null)
  const retryTimer = useRef<number | null>(null)

  const clearTimers = useCallback(() => {
    if (debounceTimer.current !== null) {
      window.clearTimeout(debounceTimer.current)
      debounceTimer.current = null
    }
    if (maxTimer.current !== null) {
      window.clearTimeout(maxTimer.current)
      maxTimer.current = null
    }
    if (retryTimer.current !== null) {
      window.clearTimeout(retryTimer.current)
      retryTimer.current = null
    }
  }, [])

  const doSaveRef = useRef<(body: string, force: boolean) => void>(() => {})

  const doSave = useCallback(
    (body: string, force: boolean) => {
      const currentNote = noteRef.current
      writeMirror(noteId, body)
      setSaving(true)
      setFailed(false)
      void updateNote(
        noteId,
        force || currentNote === undefined
          ? { body_md: body }
          : { body_md: body, base_updated_at: currentNote.updated_at }
      )
        .then((updated) => {
          setSaving(false)
          setConflict(false)
          setSavedAt(Date.now())
          clearMirror(noteId)
          if (draftRef.current === body) {
            setDraft(null)
          }
          onSavedRef.current(updated)
        })
        .catch((error: unknown) => {
          setSaving(false)
          if (error instanceof ApiError && error.status === 409) {
            setConflict(true)
            return
          }
          setFailed(true)
          onErrorRef.current(error instanceof Error ? error.message : String(error))
          if (retryTimer.current === null) {
            retryTimer.current = window.setTimeout(() => {
              retryTimer.current = null
              const current = draftRef.current
              if (current !== null && dirtyRef.current && !conflictRef.current) {
                doSaveRef.current(current, false)
              }
            }, AUTOSAVE_RETRY_MS)
          }
        })
    },
    [noteId, setDraft]
  )

  doSaveRef.current = doSave

  useEffect(() => {
    if (!dirty || saving || conflict) {
      if (!dirty) {
        clearTimers()
      }
      return
    }
    const fire = () => {
      clearTimers()
      const body = draftRef.current
      if (body !== null) {
        doSaveRef.current(body, false)
      }
    }
    debounceTimer.current = window.setTimeout(fire, AUTOSAVE_DEBOUNCE_MS)
    if (maxTimer.current === null) {
      maxTimer.current = window.setTimeout(fire, AUTOSAVE_MAX_WAIT_MS)
    }
    return () => {
      if (debounceTimer.current !== null) {
        window.clearTimeout(debounceTimer.current)
        debounceTimer.current = null
      }
    }
  }, [dirty, saving, conflict, draft, noteId, clearTimers])

  useEffect(() => {
    const flush = () => {
      const body = draftRef.current
      if (body === null || !dirtyRef.current) {
        return
      }
      writeMirror(noteId, body)
      if (savingRef.current || conflictRef.current) {
        return
      }
      void updateNote(noteId, { body_md: body }).catch(() => {})
    }
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current) {
        return
      }
      event.preventDefault()
      flush()
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload)
      flush()
    }
  }, [noteId])

  useEffect(() => {
    if (note === undefined) {
      return
    }
    const mirror = readMirror(noteId)
    if (mirror !== null && Date.parse(mirror.savedAt) > Date.parse(note.updated_at)) {
      setRecovery(mirror)
      return
    }
    if (mirror !== null) {
      clearMirror(noteId)
    }
    setRecovery(null)
  }, [note, noteId])

  useEffect(() => clearTimers, [clearTimers])

  const saveNow = useCallback((options?: { force?: boolean }) => {
    const body = draftRef.current
    if (body === null || !dirtyRef.current) {
      return
    }
    doSaveRef.current(body, options?.force ?? false)
  }, [])

  const restoreRecovery = useCallback(() => {
    if (recoveryRef.current !== null) {
      setDraft(recoveryRef.current.body_md)
    }
    setRecovery(null)
  }, [setDraft])

  const discardRecovery = useCallback(() => {
    clearMirror(noteId)
    setRecovery(null)
  }, [noteId])

  const resolveConflictReload = useCallback(() => {
    clearMirror(noteId)
    setDraft(null)
    setConflict(false)
    reload()
  }, [noteId, setDraft, reload])

  const status: AutosaveStatus = conflict
    ? 'conflict'
    : saving
      ? 'saving'
      : dirty
        ? failed
          ? 'error'
          : 'pending'
        : savedAt !== null
          ? 'saved'
          : 'idle'

  return {
    dirty,
    status,
    conflict,
    recovery,
    saveNow,
    restoreRecovery,
    discardRecovery,
    resolveConflictReload,
  }
}

import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { act, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { useState } from 'react'

import type { MarkdownEditorApi } from '@/components/editor/MarkdownEditor'
import { MarkdownEditor } from '@/components/editor/MarkdownEditor'
import type { NoteDetailInfo } from '@/lib/api'
import {
  AUTOSAVE_DEBOUNCE_MS,
  noteBodyMd,
  useNoteAutosave,
} from '@/features/notes/useNoteAutosave'

const getNote = vi.fn()
const updateNote = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getNote: (id: number) => getNote(id),
    updateNote: (...args: unknown[]) =>
      updateNote(...(args as [number, object])),
  }
})

function NOTE(body: string): NoteDetailInfo {
  return {
    id: 3,
    title: 'Probe',
    course_id: null,
    node_id: null,
    owner_type: 'standalone',
    owner_id: null,
    tags: [],
    pinned: false,
    updated_at: '2026-08-21T10:00:00',
    body: [{ type: 'text', md: body }],
    drawings: [],
  }
}

function proseRoot(): HTMLElement {
  const node = document.querySelector('.ProseMirror')
  if (node === null) throw new Error('no root')
  return node as HTMLElement
}

function Harness({ apiRef }: { apiRef: { current: MarkdownEditorApi | null } }) {
  const client = useQueryClient()
  const note = useQuery({ queryKey: ['note', 3], queryFn: () => getNote(3) })
  const [draft, setDraft] = useState<string | null>(null)
  const autosave = useNoteAutosave({
    noteId: 3,
    note: note.data,
    draft,
    setDraft,
    onSaved: (updated) => {
      client.setQueryData(['note', 3], updated)
      void client.invalidateQueries({ queryKey: ['note', 3] })
      void client.invalidateQueries({ queryKey: ['notes'] })
    },
    onError: () => {},
    reload: () => void note.refetch(),
  })
  void autosave.status
  if (note.data === undefined) {
    return null
  }
  const markdown = draft ?? noteBodyMd(note.data)
  return (
    <MarkdownEditor
      value={markdown}
      onChange={setDraft}
      ariaLabel="Note body"
      apiRef={apiRef}
    />
  )
}

describe('autosave full loop', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.clear()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  test('save + invalidate-refetch never replaces the document or moves the caret', async () => {
    let serverBody = 'first para\n\n\n\nsecond para\n\nthird'
    getNote.mockImplementation(async () => NOTE(serverBody))
    updateNote.mockImplementation(async (_id: number, body: { body_md?: string }) => {
      serverBody = body.body_md ?? serverBody
      return NOTE(serverBody)
    })

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const apiRef: { current: MarkdownEditorApi | null } = { current: null }
    render(
      <QueryClientProvider client={client}>
        <Harness apiRef={apiRef} />
      </QueryClientProvider>
    )
    await waitFor(() => expect(proseRoot().textContent).toContain('third'))
    await waitFor(() => expect(apiRef.current).not.toBeNull())

    proseRoot().focus()
    const lastParagraphBefore = proseRoot().lastElementChild
    const activeBefore = document.activeElement
    expect(activeBefore).toBe(proseRoot())

    await act(async () => {
      apiRef.current?.insertQuote('typed line', null)
    })
    await act(async () => {
      vi.advanceTimersByTime(AUTOSAVE_DEBOUNCE_MS + 100)
    })
    await waitFor(() => expect(updateNote).toHaveBeenCalledTimes(1))
    const saved = updateNote.mock.calls[0][1] as { body_md?: string }
    expect(saved.body_md).toContain('first para\n\n\n\nsecond para')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    await waitFor(() => expect(getNote).toHaveBeenCalledTimes(2))

    expect(proseRoot().lastElementChild).toBe(lastParagraphBefore)
    expect(document.activeElement).toBe(activeBefore)
  })
})

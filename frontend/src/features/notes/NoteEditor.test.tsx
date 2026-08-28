import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { ApiError } from '@/lib/api'

import { NoteEditor } from './NoteEditor'
import { draftKey } from './draftMirror'

const getNote = vi.fn()
const updateNote = vi.fn()
const runNoteAction = vi.fn()
const courseTree = vi.fn()
const deleteNote = vi.fn()
const addDrawing = vi.fn()
const updateDrawing = vi.fn()
const deleteDrawing = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getNote: (id: number) => getNote(id),
    updateNote: (...args: unknown[]) => updateNote(...(args as [number, object])),
    runNoteAction: (...args: unknown[]) => runNoteAction(...(args as [number, string])),
    courseTree: (id: number) => courseTree(id),
    deleteNote: (id: number) => deleteNote(id),
    addDrawing: (...args: unknown[]) => addDrawing(...(args as [number, unknown[], string])),
    updateDrawing: (...args: unknown[]) =>
      updateDrawing(...(args as [number, number, unknown[], string, boolean])),
    deleteDrawing: (noteId: number, drawingId: number) =>
      deleteDrawing(noteId, drawingId),
  }
})

vi.mock('@/components/editor/MarkdownEditor', async () => {
  const React = await import('react')
  return {
    MarkdownEditor: ({
      value,
      onChange,
      ariaLabel,
      drawingAdapter,
      apiRef,
      aiHelper,
    }: {
      value: string
      onChange: (value: string) => void
      ariaLabel?: string
      drawingAdapter?: {
        create: (
          strokes: unknown[],
          pngBase64: string,
          ocr: boolean
        ) => Promise<number | null>
        remove: (drawingId: number) => Promise<void>
      }
      apiRef?: { current: { insertDrawing: (id: number) => void } | null }
      aiHelper?: { courseId?: number; nodeId?: number; title: string }
    }) => {
      const latest = React.useRef({ value, onChange })
      latest.current = { value, onChange }
      React.useEffect(() => {
        if (apiRef) {
          apiRef.current = {
            insertDrawing: (id: number) =>
              onChange(`${latest.current.value}\n\n![drawing](ca-drawing://${id})`),
          }
        }
        return () => {
          if (apiRef) {
            apiRef.current = null
          }
        }
      })
      return (
        <div>
          <textarea
            aria-label={ariaLabel ?? 'Body'}
            value={value}
            onChange={(event) => onChange(event.target.value)}
          />
          {drawingAdapter ? (
            <button
              type="button"
              onClick={() => void drawingAdapter.create([], 'AAA', true)}
            >
              editor-insert-drawing
            </button>
          ) : null}
          {drawingAdapter ? (
            <button
              type="button"
              onClick={() => void drawingAdapter.remove(7)}
            >
              editor-delete-drawing
            </button>
          ) : null}
          <button
            type="button"
            aria-label={`editor-ai-helper-${aiHelper?.courseId ?? 'none'}-${aiHelper?.nodeId ?? 'none'}`}
          >
            editor-ai-helper
          </button>
        </div>
      )
    },
  }
})

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    to,
    params,
  }: {
    children: React.ReactNode
    to: string
    params?: Record<string, string>
  }) => {
    let href = to
    for (const [key, value] of Object.entries(params ?? {})) {
      href = href.replace(`$${key}`, value)
    }
    return <a href={href}>{children}</a>
  },
}))

const NOTE = (overrides: Partial<Record<string, unknown>> = {}) => ({
  id: 3,
  title: 'Chain rule derivation',
  course_id: null,
  node_id: null,
  owner_type: 'standalone',
  owner_id: null,
  tags: ['calculus'],
  pinned: false,
  updated_at: '2026-08-19T10:00:00',
  body: [{ type: 'text', md: 'Original body' }],
  drawings: [],
  ...overrides,
})

const TREE = [
  {
    id: 1,
    title: 'Calculus I',
    summary: null,
    objectives: [],
    order_idx: 0,
    depth: 0,
    is_root: true,
    children: [
      {
        id: 5,
        title: 'Derivatives',
        summary: null,
        objectives: [],
        order_idx: 0,
        depth: 1,
        is_root: false,
        children: [
          {
            id: 11,
            title: 'Chain rule',
            summary: null,
            objectives: [],
            order_idx: 0,
            depth: 2,
            is_root: false,
            children: [],
            materials: [],
          },
        ],
        materials: [],
      },
    ],
    materials: [],
  },
]

function renderEditor(noteId = 3) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <NoteEditor noteId={noteId} />
    </QueryClientProvider>
  )
}

describe('NoteEditor', () => {
  beforeEach(() => {
    vi.useRealTimers()
    localStorage.clear()
    getNote.mockReset()
    updateNote.mockReset()
    runNoteAction.mockReset()
    courseTree.mockReset()
    deleteNote.mockReset()
    addDrawing.mockReset()
    deleteDrawing.mockReset()
    getNote.mockResolvedValue(NOTE())
    updateNote.mockImplementation(async (_id: number, body: { body_md?: string }) =>
      NOTE({
        body: [{ type: 'text', md: body.body_md ?? 'Original body' }],
        updated_at: '2026-08-19T12:00:00',
      })
    )
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  test('edits the title inline and saves on submit', async () => {
    renderEditor()
    const title = await screen.findByRole('textbox', { name: 'Note title' })
    fireEvent.change(title, { target: { value: 'Renamed note' } })
    fireEvent.submit(title.closest('form')!)
    await waitFor(() => expect(updateNote).toHaveBeenCalledWith(3, { title: 'Renamed note' }))
  })

  test('adds and removes tags via the chip editor', async () => {
    renderEditor()
    expect(await screen.findByRole('textbox', { name: 'Note title' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /add tag…/i }))
    const input = screen.getByPlaceholderText(/add tag…/i)
    fireEvent.change(input, { target: { value: 'exam' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() =>
      expect(updateNote).toHaveBeenCalledWith(3, { tags: ['calculus', 'exam'] })
    )

    fireEvent.click(screen.getByRole('button', { name: 'Remove tag' }))
    await waitFor(() => expect(updateNote).toHaveBeenCalledWith(3, { tags: [] }))
  })

  test('AI result is editable and appends the edited text into the saved body', async () => {
    runNoteAction.mockResolvedValue({ markdown: 'AI summary text' })
    renderEditor()
    await screen.findByRole('textbox', { name: 'Note title' })

    fireEvent.click(screen.getByRole('button', { name: 'AI actions' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Summarize' }))
    const result = await screen.findByRole('textbox', {
      name: /edit before appending/i,
    })
    expect(result).toHaveValue('AI summary text')

    fireEvent.change(result, { target: { value: 'Edited summary' } })
    fireEvent.click(screen.getByRole('button', { name: /append to note/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() =>
      expect(updateNote).toHaveBeenCalledWith(
        3,
        expect.objectContaining({
          body_md: expect.stringContaining('Edited summary'),
        })
      )
    )
    await waitFor(() =>
      expect(updateNote).toHaveBeenCalledWith(
        3,
        expect.objectContaining({
          body_md: expect.stringContaining('Original body'),
        })
      )
    )
  })

  test('AI result can be closed without appending', async () => {
    runNoteAction.mockResolvedValue({ markdown: 'Throwaway text' })
    renderEditor()
    await screen.findByRole('textbox', { name: 'Note title' })

    fireEvent.click(screen.getByRole('button', { name: 'AI actions' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Explain' }))
    expect(
      await screen.findByRole('textbox', { name: /edit before appending/i })
    ).toHaveValue('Throwaway text')

    fireEvent.click(screen.getAllByRole('button', { name: 'Close' })[0])
    expect(
      screen.queryByRole('textbox', { name: /edit before appending/i })
    ).not.toBeInTheDocument()
    expect(screen.queryByText('Throwaway text')).not.toBeInTheDocument()
  })

  test('autosaves the body after the debounce and clears the draft mirror', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    updateNote.mockClear()
    renderEditor()
    const body = await screen.findByRole('textbox', { name: /note body/i })
    await act(async () => {
      fireEvent.change(body, { target: { value: 'Typed derivation' } })
    })
    expect(screen.getByRole('status')).toHaveTextContent('Unsaved')
    await act(async () => {
      vi.advanceTimersByTime(1500)
    })
    await waitFor(() =>
      expect(updateNote).toHaveBeenCalledWith(
        3,
        expect.objectContaining({
          body_md: 'Typed derivation',
          base_updated_at: '2026-08-19T10:00:00',
        })
      )
    )
    expect(JSON.parse(localStorage.getItem(draftKey(3)) ?? 'null')).toBeNull()
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Saved'))
  })

  test('retries a failed autosave after the retry interval', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    updateNote.mockClear()
    let calls = 0
    updateNote.mockImplementation(async () => {
      calls += 1
      if (calls === 1) {
        throw new Error('server down')
      }
      return NOTE({ updated_at: '2026-08-19T12:00:00' })
    })
    renderEditor()
    const body = await screen.findByRole('textbox', { name: /note body/i })
    await act(async () => {
      fireEvent.change(body, { target: { value: 'Retry me' } })
    })
    await act(async () => {
      vi.advanceTimersByTime(1500)
    })
    await waitFor(() => expect(updateNote).toHaveBeenCalledTimes(1))
    await act(async () => {
      vi.advanceTimersByTime(5000)
    })
    await waitFor(() => expect(updateNote).toHaveBeenCalledTimes(2))
    await waitFor(() =>
      expect(updateNote).toHaveBeenLastCalledWith(
        3,
        expect.objectContaining({ body_md: 'Retry me' })
      )
    )
  })

  test('409 conflict offers reload or overwrite', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    updateNote.mockClear()
    updateNote.mockImplementation(async () => {
      throw new ApiError('note was modified elsewhere', 409)
    })
    renderEditor()
    const body = await screen.findByRole('textbox', { name: /note body/i })
    await act(async () => {
      fireEvent.change(body, { target: { value: 'Divergent edit' } })
    })
    await act(async () => {
      vi.advanceTimersByTime(1500)
    })
    expect(await screen.findByText(/changed in another window/i)).toBeInTheDocument()
    updateNote.mockClear()
    updateNote.mockImplementation(async () => NOTE({ updated_at: '2026-08-19T13:00:00' }))

    fireEvent.click(screen.getByRole('button', { name: 'Keep mine' }))
    await waitFor(() =>
      expect(updateNote).toHaveBeenCalledWith(3, { body_md: 'Divergent edit' })
    )
  })

  test('shows the recovery banner when the mirror is newer than the note', async () => {
    localStorage.setItem(
      draftKey(3),
      JSON.stringify({ body_md: 'Crashed draft', savedAt: '2026-08-19T11:00:00' })
    )
    renderEditor()
    expect(await screen.findByText(/previous session/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Restore' }))
    const body = await screen.findByRole('textbox', { name: /note body/i })
    expect(body).toHaveValue('Crashed draft')
  })

  test('discarding the recovery banner removes the mirror', async () => {
    localStorage.setItem(
      draftKey(3),
      JSON.stringify({ body_md: 'Crashed draft', savedAt: '2026-08-19T11:00:00' })
    )
    renderEditor()
    expect(await screen.findByText(/previous session/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }))
    await waitFor(() =>
      expect(localStorage.getItem(draftKey(3))).toBeNull()
    )
  })

  test('flushes pending changes on unmount', async () => {
    const view = renderEditor()
    const body = await screen.findByRole('textbox', { name: /note body/i })
    fireEvent.change(body, { target: { value: 'Last minute note' } })
    updateNote.mockClear()
    await act(async () => {
      view.unmount()
    })
    await waitFor(() =>
      expect(updateNote).toHaveBeenCalledWith(3, { body_md: 'Last minute note' })
    )
  })

  test('drawing blocks render as inline refs in the editable body', async () => {
    getNote.mockResolvedValue(
      NOTE({
        body: [
          { type: 'text', md: 'before' },
          { type: 'drawing', drawing_id: 4 },
          { type: 'text', md: 'after' },
        ],
        drawings: [
          {
            id: 4,
            png_sha: 'abc123',
            strokes: [],
            ocr_version: 1,
            ocr_markdown: '$2x$',
            created_at: '2026-08-19T10:00:00',
          },
        ],
      })
    )
    renderEditor()
    const body = await screen.findByRole('textbox', { name: /note body/i })
    expect(body).toHaveValue(
      'before\n\n![drawing](ca-drawing://4)\n\nafter'
    )
    expect(screen.queryByRole('button', { name: 'Insert inline' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'editor-insert-drawing' })).toBeInTheDocument()
  })

  test('the drawing adapter create wires through to addDrawing', async () => {
    getNote.mockResolvedValue(NOTE({ body: [{ type: 'text', md: 'plain' }] }))
    addDrawing.mockResolvedValue(
      NOTE({
        body: [{ type: 'text', md: 'plain' }],
        drawings: [
          {
            id: 11,
            png_sha: 'newsha',
            strokes: [],
            ocr_version: 1,
            ocr_markdown: 'fresh',
            created_at: '2026-08-19T10:00:00',
          },
        ],
      })
    )
    renderEditor()
    await screen.findByRole('textbox', { name: /note body/i })

    fireEvent.click(screen.getByRole('button', { name: 'editor-insert-drawing' }))
    await waitFor(() => expect(addDrawing).toHaveBeenCalledWith(3, [], 'AAA', true, undefined))
  })

  test('the drawing adapter remove wires through to deleteDrawing', async () => {
    getNote.mockResolvedValue(
      NOTE({
        body: [{ type: 'text', md: 'before\n\n![drawing](ca-drawing://7)\n\nafter' }],
        drawings: [
          {
            id: 7,
            png_sha: 'sha7',
            strokes: [],
            ocr_version: 1,
            ocr_markdown: 'text',
            created_at: '2026-08-19T10:00:00',
          },
        ],
      })
    )
    deleteDrawing.mockResolvedValue(
      NOTE({
        body: [{ type: 'text', md: 'before\n\nafter' }],
        drawings: [],
      })
    )
    renderEditor()
    await screen.findByRole('textbox', { name: /note body/i })

    fireEvent.click(screen.getByRole('button', { name: 'editor-delete-drawing' }))
    await waitFor(() => expect(deleteDrawing).toHaveBeenCalledWith(3, 7))
  })

  test('study-alongside button renders only with the callback and invokes it', async () => {
    const onStudyAlongside = vi.fn()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <NoteEditor noteId={3} onStudyAlongside={onStudyAlongside} />
      </QueryClientProvider>
    )
    const button = await screen.findByRole('button', { name: /study alongside/i })
    fireEvent.click(button)
    expect(onStudyAlongside).toHaveBeenCalled()
  })

  test('focus header links the course and the placement node', async () => {
    getNote.mockResolvedValue(NOTE({ course_id: 9, node_id: 11 }))
    courseTree.mockResolvedValue(TREE)
    renderEditor()
    const courseLink = await screen.findByRole('link', { name: 'Calculus I' })
    expect(courseLink).toHaveAttribute('href', '/courses/9')
    const nodeLink = screen.getByRole('link', { name: 'Chain rule' })
    expect(nodeLink).toHaveAttribute('href', '/courses/9/n/11')
  })

  test('root-placed note shows only the course crumb', async () => {
    getNote.mockResolvedValue(NOTE({ course_id: 9, node_id: 1 }))
    courseTree.mockResolvedValue(TREE)
    renderEditor()
    await screen.findByRole('textbox', { name: 'Note title' })
    expect(await screen.findAllByText('Calculus I')).toHaveLength(1)
    expect(screen.queryByRole('link', { name: 'Chain rule' })).not.toBeInTheDocument()
  })

  test('note editor passes course and node to the AI helper', async () => {
    getNote.mockResolvedValue(NOTE({ course_id: 9, node_id: 11 }))
    renderEditor()
    await screen.findByRole('textbox', { name: 'Note title' })
    expect(
      await screen.findByRole('button', { name: 'editor-ai-helper-9-11' })
    ).not.toBeNull()
  })

  test('close button renders only when onClose is provided', async () => {
    const onClose = vi.fn()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <NoteEditor noteId={3} onClose={onClose} />
      </QueryClientProvider>
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalled()
  })

  test('delete button removes the note and calls onClose', async () => {
    const onClose = vi.fn()
    deleteNote.mockResolvedValue(undefined)
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <NoteEditor noteId={3} onClose={onClose} />
      </QueryClientProvider>
    )
    fireEvent.click(await screen.findByRole('button', { name: 'More note actions' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    await waitFor(() => expect(deleteNote).toHaveBeenCalledWith(3))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
    confirmSpy.mockRestore()
  })

  test('delete is cancelled when not confirmed', async () => {
    const onClose = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <NoteEditor noteId={3} onClose={onClose} />
      </QueryClientProvider>
    )
    fireEvent.click(await screen.findByRole('button', { name: 'More note actions' }))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Delete' }))
    expect(deleteNote).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  test('rare actions live in the overflow menu', async () => {
    renderEditor()
    await screen.findByRole('textbox', { name: 'Note title' })

    expect(screen.queryByRole('button', { name: 'Print' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Export .md' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'History' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'More note actions' }))
    expect(await screen.findByRole('menuitem', { name: 'Print' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Export .md' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'History' })).toBeInTheDocument()
  })
})

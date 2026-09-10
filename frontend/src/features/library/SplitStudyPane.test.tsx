import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import type { StudyInsertApi } from './SplitStudyPane'
import { SplitStudyPane } from './SplitStudyPane'

const getMaterial = vi.fn()
const getMaterialLinks = vi.fn()
const courseTree = vi.fn()
const createNote = vi.fn()

let capturedInsertRef: { current: StudyInsertApi | null } | undefined
let capturedRequestClose: (() => void) | undefined

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMaterial: (id: number) => getMaterial(id),
    getMaterialLinks: (id: number) => getMaterialLinks(id),
    courseTree: (id: number) => courseTree(id),
    createNote: (body: unknown) => createNote(body),
  }
})

vi.mock('@/features/notes/LazyNoteEditor', () => ({
  LazyNoteEditor: ({
    noteId,
    insertRef,
    onRequestClose,
  }: {
    noteId: number
    insertRef?: { current: StudyInsertApi | null }
    onRequestClose?: () => void
  }) => {
    capturedInsertRef = insertRef
    capturedRequestClose = onRequestClose
    return (
      <div data-testid="study-note-editor">
        note:{noteId}
        <button
          type="button"
          data-testid="close-notes-probe"
          onClick={() => onRequestClose?.()}
        >
          close-notes-probe
        </button>
      </div>
    )
  },
}))

vi.mock('./MaterialDetailBody', () => ({
  DETAIL_TABS: ['extraction', 'original', 'side-by-side'],
  MaterialDetailBody: ({
    materialId,
    onQuoteSelection,
    onClose,
  }: {
    materialId: number
    onQuoteSelection?: (text: string) => void
    onClose?: () => void
  }) => (
    <div data-testid="study-material-body">
      <p data-testid="extracted-line">The chain rule states that $(fg)' = f'g + fg'$ holds.</p>
      material:{materialId}
      {onClose ? <span data-testid="pane-close-threaded" /> : null}
      <button
        type="button"
        data-testid="quote-wiring-probe"
        onClick={() => onQuoteSelection?.("$(fg)' = f'g + fg'$")}
      >
        quote-wiring-probe
      </button>
    </div>
  ),
}))

vi.mock('./MaterialDetailDrawer', () => ({
  MaterialDetailDrawer: () => <div data-testid="fallback-drawer" />,
}))

const MATERIAL = {
  material: {
    id: 5,
    course_id: 2,
    title: 'Chain rule worksheet',
    status: 'ready',
    course_id_ref: 2,
  },
}

function renderPane(props: Partial<Parameters<typeof SplitStudyPane>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SplitStudyPane
        courseId={2}
        materialId={5}
        study={42}
        onNoteCreated={vi.fn()}
        onClose={vi.fn()}
        onCloseNotes={vi.fn()}
        {...props}
      />
    </QueryClientProvider>
  )
}

describe('SplitStudyPane', () => {
  beforeEach(() => {
    localStorage.clear()
    capturedInsertRef = undefined
    capturedRequestClose = undefined
    getMaterial.mockReset()
    getMaterialLinks.mockReset()
    courseTree.mockReset()
    createNote.mockReset()
    getMaterial.mockResolvedValue(MATERIAL)
    getMaterialLinks.mockResolvedValue([
      { node_id: 9, is_course_level: false, node_title: 'Derivatives' },
    ])
    courseTree.mockResolvedValue([
      { id: 1, title: 'Calculus', children: [], materials: [] },
    ])
  })

  test('renders material on the left and the note on the right', async () => {
    renderPane()
    expect(await screen.findByTestId('study-material-body')).toBeInTheDocument()
    expect(await screen.findByTestId('study-note-editor')).toHaveTextContent('note:42')
    expect(screen.getByRole('separator')).toBeInTheDocument()
  })

  test('no pane-level title band — the material header is the pane header (plan 62-B)', async () => {
    renderPane()
    await screen.findByTestId('study-material-body')
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
    expect(screen.getByTestId('pane-close-threaded')).toBeInTheDocument()
  })

  test('study=new creates a note placed on the material node and reports it', async () => {
    const onNoteCreated = vi.fn()
    createNote.mockResolvedValue({ id: 77, title: 'Notes — Chain rule worksheet' })
    renderPane({ study: 'new', onNoteCreated })

    await waitFor(() => expect(createNote).toHaveBeenCalled())
    expect(createNote).toHaveBeenCalledWith(
      expect.objectContaining({ course_id: 2, node_id: 9 })
    )
    await waitFor(() => expect(onNoteCreated).toHaveBeenCalledWith(77))
    expect(await screen.findByTestId('study-note-editor')).toHaveTextContent('note:77')
  })

  test('selected text quotes into the note through the shared selection toolbar wiring (plan 61-D)', async () => {
    renderPane()
    await screen.findByTestId('study-material-body')

    const insert = vi.fn()
    expect(capturedInsertRef).toBeDefined()
    capturedInsertRef!.current = { insertQuote: insert }

    await waitFor(() => {
      fireEvent.click(screen.getByTestId('quote-wiring-probe'))
      expect(insert).toHaveBeenCalledWith(
        expect.stringContaining("$(fg)' = f'g + fg'$"),
        expect.objectContaining({ materialId: 5, title: 'Chain rule worksheet' })
      )
    })
  })

  test('dragging the divider resizes and persists the split', async () => {
    renderPane()
    await screen.findByTestId('study-material-body')

    const separator = screen.getByRole('separator')
    const container = separator.parentElement!.getBoundingClientRect
    separator.parentElement!.getBoundingClientRect = () =>
      ({ left: 0, width: 1000 } as DOMRect)

    fireEvent.mouseDown(separator)
    fireEvent.mouseMove(window, { clientX: 650 })
    fireEvent.mouseUp(window)

    expect(container).toBeDefined()
    expect(localStorage.getItem('ca-study-split:2')).not.toBeNull()
    const stored = Number(localStorage.getItem('ca-study-split:2'))
    expect(stored).toBeGreaterThanOrEqual(30)
    expect(stored).toBeLessThanOrEqual(70)
  })

  test('divider supports keyboard resize and double-click reset (plan 62-C)', async () => {
    renderPane()
    await screen.findByTestId('study-material-body')

    const separator = screen.getByRole('separator') as HTMLElement
    separator.parentElement!.getBoundingClientRect = () =>
      ({ left: 0, width: 1000 } as DOMRect)
    expect(separator.getAttribute('aria-valuenow')).toBe('50')

    fireEvent.keyDown(separator, { key: 'ArrowLeft' })
    await waitFor(() => expect(localStorage.getItem('ca-study-split:2')).toBe('45'))
    expect(separator.getAttribute('aria-valuenow')).toBe('45')

    fireEvent.keyDown(separator, { key: 'ArrowRight' })
    await waitFor(() => expect(localStorage.getItem('ca-study-split:2')).toBe('50'))

    fireEvent.doubleClick(separator)
    await waitFor(() => expect(localStorage.getItem('ca-study-split:2')).toBeNull())
    expect(separator.getAttribute('aria-valuenow')).toBe('50')
  })

  test('escape closes the pane', async () => {
    const onClose = vi.fn()
    renderPane({ onClose })
    await screen.findByTestId('study-material-body')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  test('per-pane close closes only the notes side, never the whole pane (plan 62-A)', async () => {
    const onClose = vi.fn()
    const onCloseNotes = vi.fn()
    renderPane({ onClose, onCloseNotes })
    await screen.findByTestId('study-note-editor')
    expect(capturedRequestClose).toBeDefined()
    fireEvent.click(screen.getByTestId('close-notes-probe'))
    expect(onCloseNotes).toHaveBeenCalledTimes(1)
    expect(onClose).not.toHaveBeenCalled()
  })

  test('escape never routes through the per-pane close (plan 62-A)', async () => {
    const onClose = vi.fn()
    const onCloseNotes = vi.fn()
    renderPane({ onClose, onCloseNotes })
    await screen.findByTestId('study-material-body')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onCloseNotes).not.toHaveBeenCalled()
  })
})

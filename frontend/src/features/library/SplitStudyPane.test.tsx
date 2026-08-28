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
  }: {
    noteId: number
    insertRef?: { current: StudyInsertApi | null }
  }) => {
    capturedInsertRef = insertRef
    return <div data-testid="study-note-editor">note:{noteId}</div>
  },
}))

vi.mock('./MaterialDetailBody', () => ({
  DETAIL_TABS: ['extraction', 'original', 'side-by-side'],
  MaterialDetailBody: ({ materialId }: { materialId: number }) => (
    <div data-testid="study-material-body">
      <p data-testid="extracted-line">The chain rule states that $(fg)' = f'g + fg'$ holds.</p>
      material:{materialId}
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
        {...props}
      />
    </QueryClientProvider>
  )
}

function selectLine() {
  const target = screen.getByTestId('extracted-line')
  const range = document.createRange()
  range.selectNodeContents(target)
  const selection = window.getSelection()
  selection?.removeAllRanges()
  selection?.addRange(range)
  return target
}

describe('SplitStudyPane', () => {
  beforeEach(() => {
    localStorage.clear()
    capturedInsertRef = undefined
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

  test('selection shows the quote button which inserts into the note', async () => {
    renderPane()
    await screen.findByTestId('study-material-body')

    selectLine()
    fireEvent.mouseUp(screen.getByTestId('study-material-body'))

    const quoteButton = await screen.findByRole('button', { name: /quote into note/i })
    expect(quoteButton).toBeInTheDocument()

    const insert = vi.fn()
    expect(capturedInsertRef).toBeDefined()
    capturedInsertRef!.current = { insertQuote: insert }

    fireEvent.click(quoteButton)
    expect(insert).toHaveBeenCalledWith(
      expect.stringContaining("$(fg)' = f'g + fg'$"),
      expect.objectContaining({ materialId: 5, title: 'Chain rule worksheet' })
    )
    expect(screen.queryByRole('button', { name: /quote into note/i })).not.toBeInTheDocument()
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

  test('escape closes the pane', async () => {
    const onClose = vi.fn()
    renderPane({ onClose })
    await screen.findByTestId('study-material-body')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})

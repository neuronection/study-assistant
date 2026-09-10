import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from '@tanstack/react-router'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { QuickCapture } from './QuickCapture'
import { useCaptureStore } from '@/lib/capture-store'

const createNote = vi.fn()
const deleteNote = vi.fn()
const getScratchpad = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    createNote: (body: Parameters<typeof actual.createNote>[0]) => createNote(body),
    deleteNote: (id: number) => deleteNote(id),
    getScratchpad: () => getScratchpad(),
  }
})

const SCRATCHPAD = {
  course: { id: 77, title: 'Scratchpad' },
  content_count: 0,
}

function renderCapture() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute()
  const indexRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/',
    component: () => <QuickCapture />,
  })
  const noteRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/note/$noteId',
    component: () => null,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([indexRoute, noteRoute]),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  })
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

async function openSheet() {
  await screen.findByRole('dialog')
}

describe('QuickCapture', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getScratchpad.mockResolvedValue(SCRATCHPAD)
    createNote.mockReset()
    deleteNote.mockReset()
    useCaptureStore.getState().closeCapture()
  })

  test('opens via the store, saves to the scratchpad course, and closes', async () => {
    createNote.mockResolvedValue({ id: 5, title: 'Chain rule idea' })
    renderCapture()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    useCaptureStore.getState().openCapture()
    await openSheet()
    const box = await screen.findByRole('textbox')
    fireEvent.change(box, { target: { value: 'Chain rule idea' } })
    fireEvent.keyDown(box, { key: 'Enter', ctrlKey: true })
    await waitFor(() =>
      expect(createNote).toHaveBeenCalledWith(
        expect.objectContaining({ course_id: 77, title: 'Chain rule idea', tags: ['quick-capture'] }),
      ),
    )
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(await screen.findByText(/Captured: Chain rule idea/)).toBeInTheDocument()
  })

  test('title falls back for empty first lines and truncates long ones', async () => {
    createNote.mockResolvedValue({ id: 6, title: 'T' })
    renderCapture()
    useCaptureStore.getState().openCapture()
    const box = await screen.findByRole('textbox')
    const long = 'x'.repeat(120)
    fireEvent.change(box, { target: { value: `\n\n## ${long}` } })
    fireEvent.keyDown(box, { key: 'Enter', ctrlKey: true })
    await waitFor(() => expect(createNote).toHaveBeenCalled())
    const title = createNote.mock.calls[0][0].title as string
    expect(title).toHaveLength(80)
    expect(title.endsWith('…')).toBe(true)
  })

  test('empty captures do not hit the API', async () => {
    renderCapture()
    useCaptureStore.getState().openCapture()
    const box = await screen.findByRole('textbox')
    fireEvent.change(box, { target: { value: '   ' } })
    fireEvent.keyDown(box, { key: 'Enter', ctrlKey: true })
    await waitFor(() => expect(saveFailedIndicator()).toBeInTheDocument())
    expect(createNote).not.toHaveBeenCalled()
  })

  test('undo deletes the created note and dismisses the toast', async () => {
    createNote.mockResolvedValue({ id: 9, title: 'temp' })
    deleteNote.mockResolvedValue({ deleted_item_id: 1 })
    renderCapture()
    useCaptureStore.getState().openCapture()
    const box = await screen.findByRole('textbox')
    fireEvent.change(box, { target: { value: 'temp' } })
    fireEvent.keyDown(box, { key: 'Enter', ctrlKey: true })
    fireEvent.click(await screen.findByRole('button', { name: /undo/i }))
    await waitFor(() => expect(deleteNote).toHaveBeenCalledWith(9))
    await waitFor(() => expect(screen.queryByText(/Captured:/)).not.toBeInTheDocument())
  })
})

function saveFailedIndicator() {
  return screen.getByText(/failed/i)
}

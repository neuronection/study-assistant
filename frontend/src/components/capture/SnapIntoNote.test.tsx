import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { SnapIntoNote } from './SnapIntoNote'
import { useCaptureStore, type SnapTarget } from '@/lib/capture-store'
import { useWorkspaceStore } from '@/lib/workspace-store'

const createNote = vi.fn()
const addDrawing = vi.fn()
const updateNote = vi.fn()
const deleteDrawing = vi.fn()
const getScratchpad = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    createNote: (body: Parameters<typeof actual.createNote>[0]) => createNote(body),
    addDrawing: (...args: unknown[]) => addDrawing(...(args as [number, unknown[], string])),
    updateNote: (...args: unknown[]) => updateNote(...(args as [number, object])),
    deleteDrawing: (noteId: number, drawingId: number) => deleteDrawing(noteId, drawingId),
    getScratchpad: () => getScratchpad(),
  }
})

vi.mock('./RegionCrop', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./RegionCrop')>()
  return {
    ...actual,
    RegionCrop: ({
      open,
      onCapture,
    }: {
      open: boolean
      onCapture: (file: File, rect: unknown) => void | Promise<void>
    }) =>
      open ? (
        <button
          type="button"
          onClick={() =>
            void onCapture(
              new File([new Uint8Array([1, 2, 3])], 'screenshot.png', {
                type: 'image/png',
              }),
              null
            )
          }
        >
          region-crop-capture
        </button>
      ) : null,
  }
})

function renderFlow() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <SnapIntoNote />
    </QueryClientProvider>
  )
}

async function captureShot() {
  useCaptureStore.getState().openSnap()
  fireEvent.click(await screen.findByRole('button', { name: 'region-crop-capture' }))
  await screen.findByRole('dialog', { name: 'Review capture' })
}

describe('SnapIntoNote', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useCaptureStore.getState().closeSnap()
    useCaptureStore.getState().setSnapTarget(null)
    useWorkspaceStore.getState().setCourse(null)
    getScratchpad.mockResolvedValue({
      course: { id: 77, title: 'Scratchpad' },
      content_count: 0,
    })
  })

  test('with no open note it creates a note containing the shot (plan 67 C)', async () => {
    useWorkspaceStore.getState().setCourse(3)
    createNote.mockResolvedValue({ id: 12, title: 'Screenshot' })
    addDrawing.mockResolvedValue({
      id: 12,
      title: 'Screenshot',
      drawings: [{ id: 9, strokes: [] }],
    })
    updateNote.mockResolvedValue({ id: 12, title: 'Screenshot', drawings: [{ id: 9 }] })

    renderFlow()
    await captureShot()

    fireEvent.click(screen.getByRole('button', { name: 'Insert into note' }))
    await waitFor(() =>
      expect(createNote).toHaveBeenCalledWith(
        expect.objectContaining({ course_id: 3, title: 'Screenshot' })
      )
    )
    await waitFor(() => expect(addDrawing).toHaveBeenCalledWith(12, [], 'AQID', false, null))
    await waitFor(() =>
      expect(updateNote).toHaveBeenCalledWith(12, {
        body_md: '![screenshot](ca-drawing://9)',
      })
    )
    await waitFor(() => expect(useCaptureStore.getState().snapOpen).toBe(false))
    expect(await screen.findByText(/Snapped into “Screenshot”/)).toBeInTheDocument()
  })

  test('falls back to the scratchpad course when no course is active', async () => {
    createNote.mockResolvedValue({ id: 13, title: 'Screenshot' })
    addDrawing.mockResolvedValue({
      id: 13,
      title: 'Screenshot',
      drawings: [{ id: 10, strokes: [] }],
    })
    updateNote.mockResolvedValue({ id: 13, title: 'Screenshot', drawings: [{ id: 10 }] })

    renderFlow()
    await captureShot()
    fireEvent.click(screen.getByRole('button', { name: 'Insert into note' }))

    await waitFor(() =>
      expect(createNote).toHaveBeenCalledWith(
        expect.objectContaining({ course_id: 77 })
      )
    )
  })

  test('with an open note editor it inserts through the registered target and undo removes (plan 67 C)', async () => {
    const insert = vi.fn().mockResolvedValue(11)
    const remove = vi.fn().mockResolvedValue(undefined)
    const target: SnapTarget = { noteId: 5, title: 'Chain rule', insert, remove }
    useCaptureStore.getState().setSnapTarget(target)

    renderFlow()
    await captureShot()

    fireEvent.click(screen.getByRole('button', { name: 'Insert into note' }))
    await waitFor(() => expect(insert).toHaveBeenCalledWith('AQID'))
    expect(createNote).not.toHaveBeenCalled()
    expect(await screen.findByText(/Snapped into “Chain rule”/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /undo/i }))
    await waitFor(() => expect(remove).toHaveBeenCalledWith(11))
  })

  test('cancel inserts nothing and closes the flow', async () => {
    renderFlow()
    await captureShot()

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(useCaptureStore.getState().snapOpen).toBe(false))
    expect(createNote).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: 'Review capture' })).not.toBeInTheDocument()
    )
  })

  test('a failed insert shows the inline failure hint and keeps the review open', async () => {
    const insert = vi.fn().mockResolvedValue(null)
    useCaptureStore.getState().setSnapTarget({
      noteId: 5,
      title: 'Chain rule',
      insert,
      remove: vi.fn(),
    })

    renderFlow()
    await captureShot()
    fireEvent.click(screen.getByRole('button', { name: 'Insert into note' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Insert failed — try again'
    )
    expect(screen.getByRole('dialog', { name: 'Review capture' })).toBeInTheDocument()
  })
})

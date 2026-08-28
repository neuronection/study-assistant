import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { NoteHistoryDialog } from './NoteHistoryDialog'

const listNoteVersions = vi.fn()
const getNoteVersion = vi.fn()
const restoreNoteVersion = vi.fn()

vi.mock('@/lib/api', () => ({
  listNoteVersions: (id: number) => listNoteVersions(id),
  getNoteVersion: (noteId: number, versionId: number) => getNoteVersion(noteId, versionId),
  restoreNoteVersion: (noteId: number, versionId: number) =>
    restoreNoteVersion(noteId, versionId),
}))

const VERSIONS = [
  {
    version_id: 12,
    cause: 'restore',
    title: 'Limits',
    chars: 220,
    created_at: '2026-08-21T10:00:00',
  },
  {
    version_id: 7,
    cause: 'autosave-coalesced',
    title: 'Limits',
    chars: 180,
    created_at: '2026-08-21T09:00:00',
  },
]

function renderDialog(props: Partial<Parameters<typeof NoteHistoryDialog>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <NoteHistoryDialog
        noteId={3}
        dirty={false}
        onSaveVersion={vi.fn().mockResolvedValue(undefined)}
        onRestored={vi.fn()}
        onClose={vi.fn()}
        {...props}
      />
    </QueryClientProvider>
  )
}

describe('NoteHistoryDialog', () => {
  beforeEach(() => {
    listNoteVersions.mockReset()
    getNoteVersion.mockReset()
    restoreNoteVersion.mockReset()
    listNoteVersions.mockResolvedValue(VERSIONS)
    getNoteVersion.mockImplementation(async (_noteId: number, versionId: number) => ({
      ...VERSIONS.find((entry) => entry.version_id === versionId)!,
      body_md: `Version ${versionId} content`,
    }))
    restoreNoteVersion.mockResolvedValue({ id: 3 })
  })

  test('lists versions with cause chips and previews a picked version', async () => {
    renderDialog()
    expect(await screen.findByText('restore')).toBeInTheDocument()
    expect(screen.getByText('autosave')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /#12/i }))
    await waitFor(() => expect(getNoteVersion).toHaveBeenCalledWith(3, 12))
    expect(await screen.findByText(/Version 12 content/i)).toBeInTheDocument()
  })

  test('restore calls the endpoint, notifies the parent and closes', async () => {
    const onRestored = vi.fn()
    const onClose = vi.fn()
    renderDialog({ onRestored, onClose })

    fireEvent.click(await screen.findByRole('button', { name: /#12/i }))
    await screen.findByText(/Version 12 content/i)
    fireEvent.click(screen.getByRole('button', { name: 'Restore' }))

    await waitFor(() => expect(restoreNoteVersion).toHaveBeenCalledWith(3, 12))
    await waitFor(() => expect(onRestored).toHaveBeenCalled())
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  test('save-version-now invokes the callback and keeps the dialog open', async () => {
    const onSaveVersion = vi.fn().mockResolvedValue(undefined)
    const onClose = vi.fn()
    renderDialog({ onSaveVersion, onClose })

    fireEvent.click(await screen.findByRole('button', { name: 'Save version now' }))
    await waitFor(() => expect(onSaveVersion).toHaveBeenCalled())
    expect(onClose).not.toHaveBeenCalled()
  })

  test('warns about unsaved edits when dirty', async () => {
    renderDialog({ dirty: true })
    expect(await screen.findByText(/unsaved edits/i)).toBeInTheDocument()
  })

  test('empty history shows the empty state', async () => {
    listNoteVersions.mockResolvedValue([])
    renderDialog()
    expect(await screen.findByText(/No versions yet/i)).toBeInTheDocument()
  })
})

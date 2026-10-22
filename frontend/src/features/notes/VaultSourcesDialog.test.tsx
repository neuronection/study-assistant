import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { VaultSourcesDialog } from './VaultSourcesDialog'

const listSources = vi.fn()
const addSource = vi.fn()
const scanSource = vi.fn()
const deleteSource = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listSources: () => listSources(),
    addSource: (body: unknown) => addSource(body),
    scanSource: (id: string) => scanSource(id),
    deleteSource: (id: string) => deleteSource(id),
    vaultExportUrl: (id: string) => `/api/v1/notes/vault.zip?course_id=${id}`,
  }
})

vi.mock('@/features/library/FolderPickerDialog', () => ({
  FolderPickerDialog: ({ onChoose }: { onChoose: (path: string) => void }) => (
    <button type="button" onClick={() => onChoose('/tmp/vault')}>
      pick-vault
    </button>
  ),
}))

const SOURCE = {
  id: 's1',
  label: 'Course vault',
  path: '/tmp/vault',
  recursive: true,
  include_globs: null,
  course_id: 'c1',
  enabled: true,
  mirror_subdirs: false,
  preset: 'vault',
  scan_interval_sec: null,
  last_scan_error: null,
  material_count: 0,
  note_count: 12,
  last_scanned_at: null,
}

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <VaultSourcesDialog open courseId="c1" onClose={() => undefined} />
    </QueryClientProvider>
  )
}

describe('VaultSourcesDialog', () => {
  test('lists vault sources and rescans on demand', async () => {
    listSources.mockResolvedValue([SOURCE])
    scanSource.mockResolvedValue({ stats: {}, queued_jobs: 0, skipped: [], new_relpaths: [] })
    renderDialog()
    expect(await screen.findByText('Course vault')).toBeInTheDocument()
    expect(screen.getByText('12 notes')).toBeInTheDocument()
    fireEvent.click(screen.getByTitle('Rescan vault'))
    await waitFor(() => expect(scanSource).toHaveBeenCalledWith('s1'))
  })

  test('links a new vault folder with the vault preset', async () => {
    listSources.mockResolvedValue([])
    addSource.mockResolvedValue({ ...SOURCE, id: 's2' })
    scanSource.mockResolvedValue({ stats: {}, queued_jobs: 0, skipped: [], new_relpaths: [] })
    renderDialog()
    fireEvent.click(screen.getByRole('button', { name: /Link vault folder/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'pick-vault' }))
    await waitFor(() =>
      expect(addSource).toHaveBeenCalledWith({
        label: 'vault',
        path: '/tmp/vault',
        course_id: 'c1',
        preset: 'vault',
      })
    )
    await waitFor(() => expect(scanSource).toHaveBeenCalledWith('s2'))
  })
})

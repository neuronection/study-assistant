import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { DiffView } from '@/components/diff/DiffView'
import { ExtractionHistoryDialog } from './ExtractionHistoryDialog'

const listExtractionVersions = vi.fn()
const getExtractionVersion = vi.fn()
const editExtraction = vi.fn()
const diffExtractionVersions = vi.fn()

vi.mock('@/lib/api', () => ({
  listExtractionVersions: (id: number) => listExtractionVersions(id),
  getExtractionVersion: (id: number, version: number) =>
    getExtractionVersion(id, version),
  editExtraction: (id: number, markdown: string) =>
    editExtraction(id, markdown),
  diffExtractionVersions: (id: number, from: string, to: string) =>
    diffExtractionVersions(id, from, to),
}))

const VERSIONS = [
  { version: 3, extractor: 'manual', created_at: '2026-09-04T10:00:00' },
  { version: 2, extractor: 'ocr', created_at: '2026-09-03T10:00:00' },
  { version: 1, extractor: 'ocr', created_at: '2026-09-02T10:00:00' },
]

function renderDialog(props: Partial<Parameters<typeof ExtractionHistoryDialog>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ExtractionHistoryDialog
        materialId={5}
        onClose={vi.fn()}
        {...props}
      />
    </QueryClientProvider>
  )
}

describe('ExtractionHistoryDialog', () => {
  beforeEach(() => {
    listExtractionVersions.mockReset().mockResolvedValue(VERSIONS)
    getExtractionVersion.mockReset().mockResolvedValue({
      version: 3,
      markdown: 'v3 content',
    })
    editExtraction.mockReset().mockResolvedValue({ version: 4 })
    diffExtractionVersions.mockReset()
  })

  test('lists versions with extractor and date', async () => {
    renderDialog()
    expect(await screen.findByText('manual')).toBeInTheDocument()
    expect(screen.getAllByText('ocr').length).toBe(2)
  })

  test('compare mode renders the unified diff between versions', async () => {
    diffExtractionVersions.mockResolvedValue({
      base: '1',
      target: 'current',
      additions: 1,
      deletions: 0,
      diff: '--- v1\n+++ v3\n@@ -1 +1,2 @@\noriginal body\n+edited line\n',
    })
    renderDialog()

    fireEvent.click(await screen.findByRole('button', { name: /v1/ }))
    const baseSelect = await screen.findByLabelText('Compare base version')
    fireEvent.change(baseSelect, { target: { value: '1' } })
    const targetSelect = await screen.findByLabelText('Compare target version')
    fireEvent.change(targetSelect, { target: { value: 'current' } })

    await waitFor(() =>
      expect(diffExtractionVersions).toHaveBeenCalledWith(5, '1', 'current')
    )
    const diff = await screen.findByTestId('diff-view')
    expect(diff).toHaveTextContent('+edited line')
  })

  test('restore re-saves the picked version as a new version and closes', async () => {
    const onClose = vi.fn()
    renderDialog({ onClose })

    fireEvent.click(await screen.findByRole('button', { name: /v2/ }))
    getExtractionVersion.mockResolvedValue({ version: 2, markdown: 'v2 content' })
    fireEvent.click(await screen.findByRole('button', { name: 'Restore this version' }))

    await waitFor(() =>
      expect(getExtractionVersion).toHaveBeenCalledWith(5, 2)
    )
    await waitFor(() => expect(editExtraction).toHaveBeenCalledWith(5, 'v2 content'))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  test('empty history shows the empty state', async () => {
    listExtractionVersions.mockResolvedValue([])
    renderDialog()
    expect(await screen.findByText(/No versions yet/i)).toBeInTheDocument()
  })
})

describe('DiffView', () => {
  function renderDiff(diff: string) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={client}>
        <DiffView diff={diff} />
      </QueryClientProvider>
    )
  }

  test('renders add, del, hunk and context lines', () => {
    renderDiff('--- a\n+++ b\n@@ -1,2 +1,2 @@\n-removed\n+added\n context')
    const diff = screen.getByTestId('diff-view')
    expect(diff).toHaveTextContent('-removed')
    expect(diff).toHaveTextContent('+added')
    expect(diff).toHaveTextContent('@@ -1,2 +1,2 @@')
    expect(diff).toHaveTextContent('context')
  })

  test('empty diff shows the no-changes state', () => {
    renderDiff('')
    expect(screen.getByText(/No changes/i)).toBeInTheDocument()
  })
})

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { DiffView } from '@/components/diff/DiffView'
import { ExtractionHistoryDialog } from './ExtractionHistoryDialog'

const listExtractionVersions = vi.fn()
const getExtractionVersion = vi.fn()
const editExtraction = vi.fn()
const diffExtractionVersions = vi.fn()
const getMaterial = vi.fn()

vi.mock('@/lib/api', () => ({
  listExtractionVersions: (id: number) => listExtractionVersions(id),
  getExtractionVersion: (id: number, version: number) =>
    getExtractionVersion(id, version),
  editExtraction: (id: number, markdown: string) =>
    editExtraction(id, markdown),
  diffExtractionVersions: (id: number, from: string, to: string) =>
    diffExtractionVersions(id, from, to),
  getMaterial: (id: number) => getMaterial(id),
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
    getExtractionVersion.mockReset().mockImplementation(
      (_id: number, version: number) =>
        Promise.resolve({ version, markdown: `v${version} content` })
    )
    getMaterial.mockReset().mockResolvedValue({
      material: { id: 5, title: 'notes' },
      extraction: { version: 3, markdown: 'current body content' },
      index_card: null,
      drawings: [],
      images: [],
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
    const formatted = await screen.findByText(/v1 content/)
    expect(formatted.closest('[data-as="markdown-diff-view"]')).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Raw' }))
    const diff = await screen.findByTestId('diff-view')
    expect(diff).toHaveTextContent('+edited line')
  })

  test('formatted default renders both sides with math kept rendered', async () => {
    getExtractionVersion.mockImplementation((_id: number, version: number) =>
      Promise.resolve({
        version,
        markdown:
          version === 2
            ? 'The derivative is $x^2$\n\nsame tail'
            : 'Fixed: the derivative is $x^3$\n\nsame tail',
      })
    )
    diffExtractionVersions.mockResolvedValue({
      base: '2',
      target: '3',
      additions: 1,
      deletions: 1,
      diff: '--- v2\n+++ v3\n',
    })
    renderDialog()

    fireEvent.click(await screen.findByRole('button', { name: /v2/ }))
    const baseSelect = await screen.findByLabelText('Compare base version')
    fireEvent.change(baseSelect, { target: { value: '2' } })
    const targetSelect = await screen.findByLabelText('Compare target version')
    fireEvent.change(targetSelect, { target: { value: '3' } })

    const formatted = await screen.findByText('Fixed: the derivative is')
    expect(formatted.closest('[data-as="markdown-diff-view"]')).not.toBeNull()
    expect(document.body.textContent).toContain('same tail')
  })

  test('oversized documents fall back to the raw diff with an honest note', async () => {
    getExtractionVersion.mockImplementation((_id: number, version: number) =>
      Promise.resolve({
        version,
        markdown: 'x'.repeat(100_001) + ` v${version}`,
      })
    )
    diffExtractionVersions.mockResolvedValue({
      base: '1',
      target: 'current',
      additions: 2,
      deletions: 1,
      diff: '--- v1\n+++ v3\n',
    })
    renderDialog()

    fireEvent.click(await screen.findByRole('button', { name: /v1/ }))
    const baseSelect = await screen.findByLabelText('Compare base version')
    fireEvent.change(baseSelect, { target: { value: '1' } })

    expect(await screen.findByText(/too large for the formatted view/i)).toBeInTheDocument()
    expect(await screen.findByTestId('diff-view')).toBeInTheDocument()
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

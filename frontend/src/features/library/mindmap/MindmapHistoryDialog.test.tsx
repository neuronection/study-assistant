import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MindmapHistoryDialog } from './MindmapHistoryDialog'

const listExtractionVersions = vi.fn()
const getExtractionVersion = vi.fn()
const editExtraction = vi.fn()
const transform = vi.fn()

vi.mock('markmap-lib', () => ({
  Transformer: class {
    transform(markdown: string) {
      transform(markdown)
      return { root: { content: 'Limits' } }
    }
  },
}))

vi.mock('markmap-view', () => ({
  Markmap: {
    create: () => ({ fit: vi.fn(), destroy: vi.fn(), state: { data: null }, findElement: () => undefined }),
  },
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listExtractionVersions: (id: number) => listExtractionVersions(id),
    getExtractionVersion: (id: number, version: number) => getExtractionVersion(id, version),
    editExtraction: (id: number, md: string) => editExtraction(id, md),
  }
})

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MindmapHistoryDialog materialId={7} onClose={() => undefined} />
    </QueryClientProvider>
  )
}

describe('MindmapHistoryDialog', () => {
  beforeEach(() => {
    transform.mockClear()
    listExtractionVersions.mockReset().mockResolvedValue([
      { version: 3, extractor: 'compose', created_at: '2026-08-20T12:00:00Z' },
      { version: 2, extractor: 'ocr', created_at: '2026-08-19T12:00:00Z' },
    ])
    getExtractionVersion.mockReset().mockResolvedValue({
      id: 1,
      material_id: 7,
      version: 2,
      extractor: 'ocr',
      markdown: '# Limits\n\n- old\n',
      blocks: [],
    })
    editExtraction.mockReset().mockResolvedValue({
      id: 1,
      material_id: 7,
      version: 4,
      extractor: 'compose',
      markdown: '# Limits\n\n- old\n',
      blocks: [],
    })
  })

  test('lists versions, previews a picked one, and restores it', async () => {
    renderDialog()
    expect(await screen.findByText('v3')).toBeInTheDocument()
    expect(screen.getByText('v2')).toBeInTheDocument()

    fireEvent.click(screen.getByText('v2'))
    await waitFor(() => expect(getExtractionVersion).toHaveBeenCalledWith(7, 2))
    await waitFor(() => expect(transform).toHaveBeenCalledWith('# Limits\n\n- old\n'))

    fireEvent.click(screen.getByRole('button', { name: /restore/i }))
    await waitFor(() => expect(editExtraction).toHaveBeenCalledWith(7, '# Limits\n\n- old\n'))
  })
})

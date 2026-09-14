import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ReExtractDialog } from './ReExtractDialog'
import type { Material } from '@/lib/api/materials'

const getMaterial = vi.fn()
const reingestMaterial = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMaterial: (...args: Parameters<typeof actual.getMaterial>) =>
      getMaterial(...args),
    reingestMaterial: (...args: Parameters<typeof actual.reingestMaterial>) =>
      reingestMaterial(...args),
  }
})

const PDF_MATERIAL: Material = {
  id: 42,
  title: 'Calculus II — Lecture 3',
  kind: 'pdf',
  status: 'ready',
  filename: 'calc3.pdf',
  mime: 'application/pdf',
  pages: 12,
  course_id: 3,
  group_id: null,
  folder_id: null,
  blob_sha: 'a'.repeat(64),
  created_at: '2026-09-01T00:00:00Z',
  reextract_modes: ['auto', 'text', 'ocr'],
}

function materialFixture(overrides: Partial<Material> = {}): Material {
  return { ...PDF_MATERIAL, ...overrides }
}

function renderDialog(materialId: number | null, props: { open?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ReExtractDialog
        materialId={materialId}
        open={props.open ?? true}
        onClose={onCloseMock}
      />
    </QueryClientProvider>,
  )
}

const onCloseMock = vi.fn()

beforeEach(() => {
  getMaterial.mockReset()
  reingestMaterial.mockReset()
  onCloseMock.mockReset()
})

describe('ReExtractDialog', () => {
  test('renders mode cards from the API-truth modes with the page cost line', async () => {
    getMaterial.mockResolvedValue({
      material: PDF_MATERIAL,
      extraction: null,
      index_card: null,
      drawings: [],
      images: [],
    })
    renderDialog(42)
    expect(await screen.findByTestId('reextract-mode-auto')).toBeInTheDocument()
    expect(await screen.findByTestId('reextract-mode-text')).toBeInTheDocument()
    expect(await screen.findByTestId('reextract-mode-ocr')).toBeInTheDocument()
    expect(await screen.findByText(/12 vision-model pages/)).toBeInTheDocument()
  })

  test('shows only applicable modes for a plain material', async () => {
    getMaterial.mockResolvedValue({
      material: materialFixture({ reextract_modes: ['auto'] }),
      extraction: null,
      index_card: null,
      drawings: [],
      images: [],
    })
    renderDialog(42)
    expect(await screen.findByTestId('reextract-mode-auto')).toBeInTheDocument()
    expect(screen.queryByTestId('reextract-mode-text')).toBeNull()
    expect(screen.queryByTestId('reextract-mode-ocr')).toBeNull()
  })

  test('selects OCR and confirms — posts the mode and invalidates', async () => {
    getMaterial.mockResolvedValue({
      material: PDF_MATERIAL,
      extraction: null,
      index_card: null,
      drawings: [],
      images: [],
    })
    reingestMaterial.mockResolvedValue({ job_id: 9, material_id: 42, deduped: false })
    renderDialog(42)
    fireEvent.click(await screen.findByTestId('reextract-mode-ocr'))
    fireEvent.click(screen.getByRole('button', { name: 'Re-extract' }))
    await waitFor(() => expect(reingestMaterial).toHaveBeenCalledWith(42, { mode: 'ocr' }))
    await waitFor(() => expect(onCloseMock).toHaveBeenCalled())
  })

  test('confirm is disabled while the material is processing', async () => {
    getMaterial.mockResolvedValue({
      material: materialFixture({ status: 'processing' }),
      extraction: null,
      index_card: null,
      drawings: [],
      images: [],
    })
    renderDialog(42)
    expect(
      await screen.findByText('Currently extracting — wait for the running extraction to finish first.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Re-extract' })).toBeDisabled()
    expect(reingestMaterial).not.toHaveBeenCalled()
  })

  test('surfaces errors honestly and keeps the dialog open', async () => {
    getMaterial.mockResolvedValue({
      material: PDF_MATERIAL,
      extraction: null,
      index_card: null,
      drawings: [],
      images: [],
    })
    reingestMaterial.mockRejectedValue(new Error('re-ingest failed (422)'))
    renderDialog(42)
    const confirm = await screen.findByRole('button', { name: 'Re-extract' })
    await waitFor(() => expect(confirm).toBeEnabled())
    fireEvent.click(confirm)
    expect(await screen.findByText(/re-ingest failed \(422\)/)).toBeInTheDocument()
    expect(screen.getByTestId('reextract-dialog')).toBeInTheDocument()
  })
})

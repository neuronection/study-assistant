import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { OriginalView } from './OriginalView'

const getMaterial = vi.fn()
const apiFetch = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getMaterial: (id: string) => getMaterial(id),
    apiFetch: (url: string, init?: RequestInit) => apiFetch(url, init),
  }
})

const createObjectURL = vi.fn(() => 'blob:pdf-object')
const revokeObjectURL = vi.fn()

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <OriginalView materialId="m1" />
    </QueryClientProvider>,
  )
}

const PDF_MATERIAL = {
  material: {
    id: 'm1',
    title: 'Derivatives handout',
    kind: 'pdf',
    mime: 'application/pdf',
    blob_sha: 'a'.repeat(64),
  },
}

describe('OriginalView', () => {
  beforeEach(() => {
    getMaterial.mockReset().mockResolvedValue(PDF_MATERIAL)
    apiFetch.mockReset()
    createObjectURL.mockReset().mockReturnValue('blob:pdf-object')
    revokeObjectURL.mockReset()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectURL,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectURL,
    })
  })

  test('renders a PDF through a fetched object URL and revokes it on unmount', async () => {
    apiFetch.mockResolvedValue(
      new Response(new Blob(['%PDF-1.7'], { type: 'application/pdf' }), { status: 200 }),
    )
    const view = renderView()

    const frame = await screen.findByTitle('Derivatives handout')
    expect(frame.tagName).toBe('IFRAME')
    expect(frame).toHaveAttribute('src', 'blob:pdf-object')
    expect(apiFetch).toHaveBeenCalledWith(`/api/v1/blobs/${'a'.repeat(64)}`, undefined)

    view.unmount()
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:pdf-object'))
  })

  test('falls back to the original-file link when the PDF fetch fails', async () => {
    apiFetch.mockResolvedValue(new Response(null, { status: 500 }))
    renderView()

    const link = await screen.findByRole('link', { name: /open original file/i })
    expect(link).toHaveAttribute('href', `/api/v1/blobs/${'a'.repeat(64)}`)
    expect(createObjectURL).not.toHaveBeenCalled()
  })
})

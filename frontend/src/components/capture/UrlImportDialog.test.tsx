import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { UrlImportDialog } from './UrlImportDialog'
import { useImportUrlStore } from '@/lib/import-url-store'

const importUrlMaterial = vi.fn()
const listCourses = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    importUrlMaterial: (...args: Parameters<typeof actual.importUrlMaterial>) =>
      importUrlMaterial(...args),
    listCourses: () => listCourses(),
  }
})

beforeEach(() => {
  listCourses.mockReset()
  listCourses.mockResolvedValue(COURSES)
  importUrlMaterial.mockReset()
})

const COURSES = [
  { id: 3, title: 'Calculus I', subject: null, level: null, description: null, material_count: 0, color: null },
]

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <UrlImportDialog />
    </QueryClientProvider>,
  )
}

describe('UrlImportDialog', () => {
  test('imports the URL into the selected course and navigates to the material', async () => {
    importUrlMaterial.mockResolvedValue({
      material: { id: 44, title: 'example.com - bayes' },
      job_id: 7,
      deduped: false,
    })
    renderDialog()
    useImportUrlStore.getState().openImport()
    const input = await screen.findByRole('textbox')
    fireEvent.change(input, { target: { value: 'https://example.com/wiki/bayes' } })
    fireEvent.click(screen.getByRole('button', { name: /import/i }))
    await waitFor(() =>
      expect(importUrlMaterial).toHaveBeenCalledWith(3, 'https://example.com/wiki/bayes'),
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('empty URL never calls the API', async () => {
    renderDialog()
    useImportUrlStore.getState().openImport()
    const input = await screen.findByRole('textbox')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: /import/i }))
    await waitFor(() => expect(importUrlMaterial).not.toHaveBeenCalled())
  })

  test('import failure shows the error inline and keeps the dialog open', async () => {
    importUrlMaterial.mockRejectedValue(new Error('fetch returned 404'))
    renderDialog()
    useImportUrlStore.getState().openImport()
    const input = await screen.findByRole('textbox')
    fireEvent.change(input, { target: { value: 'https://example.com/missing' } })
    fireEvent.click(screen.getByRole('button', { name: /import/i }))
    expect(await screen.findByText(/fetch returned 404/)).toBeInTheDocument()
  })
})

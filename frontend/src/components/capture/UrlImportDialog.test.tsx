import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { UrlImportDialog } from './UrlImportDialog'
import { useImportUrlStore } from '@/lib/import-url-store'

const importUrlMaterial = vi.fn()
const createLinkMaterial = vi.fn()
const listCourses = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    importUrlMaterial: (...args: Parameters<typeof actual.importUrlMaterial>) =>
      importUrlMaterial(...args),
    createLinkMaterial: (body: unknown) => createLinkMaterial(body),
    listCourses: () => listCourses(),
  }
})

beforeEach(() => {
  listCourses.mockReset()
  listCourses.mockResolvedValue(COURSES)
  importUrlMaterial.mockReset()
  createLinkMaterial.mockReset()
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

async function switchToImportMode() {
  fireEvent.click(screen.getByRole('tab', { name: /import & parse/i }))
}

describe('UrlImportDialog', () => {
  test('attach is the default mode and calls the link endpoint', async () => {
    createLinkMaterial.mockResolvedValue({
      material: { id: 44, title: 'example.com - bayes' },
      job_id: null,
      deduped: false,
    })
    renderDialog()
    useImportUrlStore.getState().openImport()
    const input = await screen.findByRole('textbox')
    fireEvent.change(input, { target: { value: 'https://example.com/wiki/bayes' } })
    expect(screen.getByRole('tab', { name: /attach as reference/i })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    fireEvent.click(screen.getByRole('button', { name: /attach link/i }))
    await waitFor(() =>
      expect(createLinkMaterial).toHaveBeenCalledWith({
        course_id: 3,
        url: 'https://example.com/wiki/bayes',
      }),
    )
    expect(importUrlMaterial).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('attach surfaces a duplicate as success and navigates to the existing material', async () => {
    createLinkMaterial.mockResolvedValue({
      material: { id: 44, title: 'example.com - bayes' },
      job_id: null,
      deduped: true,
    })
    renderDialog()
    useImportUrlStore.getState().openImport()
    const input = await screen.findByRole('textbox')
    fireEvent.change(input, { target: { value: 'https://example.com/wiki/bayes' } })
    fireEvent.click(screen.getByRole('button', { name: /attach link/i }))
    await waitFor(() => expect(createLinkMaterial).toHaveBeenCalled())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('import mode keeps the legacy parse behavior', async () => {
    importUrlMaterial.mockResolvedValue({
      material: { id: 44, title: 'example.com - bayes' },
      job_id: 7,
      deduped: false,
    })
    renderDialog()
    useImportUrlStore.getState().openImport()
    const input = await screen.findByRole('textbox')
    fireEvent.change(input, { target: { value: 'https://example.com/wiki/bayes' } })
    await switchToImportMode()
    fireEvent.click(screen.getByRole('button', { name: /^import$/i }))
    await waitFor(() =>
      expect(importUrlMaterial).toHaveBeenCalledWith(3, 'https://example.com/wiki/bayes'),
    )
    expect(createLinkMaterial).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('empty URL never calls the API', async () => {
    renderDialog()
    useImportUrlStore.getState().openImport()
    const input = await screen.findByRole('textbox')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: /attach link/i }))
    await waitFor(() => expect(createLinkMaterial).not.toHaveBeenCalled())
    expect(importUrlMaterial).not.toHaveBeenCalled()
  })

  test('import failure shows the error inline and keeps the dialog open', async () => {
    importUrlMaterial.mockRejectedValue(new Error('fetch returned 404'))
    renderDialog()
    useImportUrlStore.getState().openImport()
    const input = await screen.findByRole('textbox')
    fireEvent.change(input, { target: { value: 'https://example.com/missing' } })
    await switchToImportMode()
    fireEvent.click(screen.getByRole('button', { name: /^import$/i }))
    expect(await screen.findByText(/fetch returned 404/)).toBeInTheDocument()
  })

  test('a prefilled URL lands in the input', async () => {
    renderDialog()
    useImportUrlStore.getState().openImport('https://example.com/prefilled')
    const input = await screen.findByRole('textbox')
    await waitFor(() => expect(input).toHaveValue('https://example.com/prefilled'))
  })
})

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { BibliographyImportDialog } from './BibliographyImportDialog'

const importBibliography = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    importBibliography: (courseId: string, file: File, nodeId?: string | null) =>
      importBibliography(courseId, file, nodeId),
  }
})

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <BibliographyImportDialog open courseId="c1" onClose={() => undefined} />
    </QueryClientProvider>
  )
}

describe('BibliographyImportDialog', () => {
  test('imports the chosen file and reports created vs deduped', async () => {
    importBibliography.mockResolvedValue({ created: 30, deduped: 0, skipped: [], materials: [] })
    renderDialog()
    const input = screen.getByLabelText('Choose a BibTeX/RIS file')
    const file = new File(['@article{x, title={T}}'], 'library.bib', { type: 'text/plain' })
    fireEvent.change(input, { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: /^Import$/ }))
    expect(await screen.findByRole('status')).toHaveTextContent(
      '30 imported · 0 already in the library'
    )
    expect(importBibliography).toHaveBeenCalledWith('c1', file, undefined)
  })

  test('shows the typed backend error and keeps the dialog open', async () => {
    importBibliography.mockRejectedValue(new Error('unterminated @article entry'))
    renderDialog()
    const input = screen.getByLabelText('Choose a BibTeX/RIS file')
    fireEvent.change(input, {
      target: { files: [new File(['@article{x'], 'bad.bib', { type: 'text/plain' })] },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Import$/ }))
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('unterminated @article entry')
    )
    expect(screen.getByTestId('bibliography-import-dialog')).toBeInTheDocument()
  })
})

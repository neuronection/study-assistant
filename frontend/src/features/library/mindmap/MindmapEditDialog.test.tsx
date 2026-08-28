import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { MindmapEditDialog } from './MindmapEditDialog'

const mindmapEdit = vi.fn()
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
    mindmapEdit: (id: number, body: unknown) => mindmapEdit(id, body),
    editExtraction: (id: number, md: string) => editExtraction(id, md),
  }
})

function renderDialog(props: { focusNode?: string; onApplied?: () => void } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MindmapEditDialog
        materialId={7}
        focusNode={props.focusNode}
        onClose={() => undefined}
        onApplied={props.onApplied ?? (() => undefined)}
      />
    </QueryClientProvider>
  )
}

describe('MindmapEditDialog', () => {
  beforeEach(() => {
    mindmapEdit.mockReset().mockResolvedValue({ markdown: '# Limits\n\n- New\n' })
    editExtraction.mockReset().mockResolvedValue({
      id: 1,
      material_id: 7,
      version: 2,
      extractor: 'x',
      markdown: '# Limits\n\n- New\n',
      blocks: [],
    })
  })

  test('edits with mode + instruction, previews, then applies', async () => {
    const onApplied = vi.fn()
    renderDialog({ focusNode: 'Definition', onApplied })
    expect(await screen.findByText('Focusing on: Definition')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('How to edit'), { target: { value: 'simplify' } })
    fireEvent.change(screen.getByLabelText(/additional instructions/i), {
      target: { value: 'merge duplicates' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }))

    await waitFor(() =>
      expect(mindmapEdit).toHaveBeenCalledWith(7, {
        mode: 'simplify',
        instruction: 'merge duplicates',
        focus_node: 'Definition',
      })
    )
    await waitFor(() => expect(transform).toHaveBeenCalledWith('# Limits\n\n- New\n'))

    fireEvent.click(screen.getByRole('button', { name: /apply changes/i }))
    await waitFor(() =>
      expect(editExtraction).toHaveBeenCalledWith(7, '# Limits\n\n- New\n')
    )
    await waitFor(() => expect(onApplied).toHaveBeenCalled())
  })
})

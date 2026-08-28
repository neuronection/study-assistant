import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { NotePickerDialog } from './NotePickerDialog'

const listNotes = vi.fn()
const listNoteTags = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listNotes: (...args: unknown[]) => listNotes(...args),
    listNoteTags: (...args: unknown[]) => listNoteTags(...args),
  }
})

function note(id: number, title: string, tags: string[] = []) {
  return {
    id,
    title,
    course_id: 1,
    node_id: null,
    owner_type: 'profile',
    owner_id: null,
    tags,
    pinned: false,
    updated_at: '2026-08-01T00:00:00Z',
  }
}

function renderDialog(onSelect = vi.fn(), onClose = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    onSelect,
    onClose,
    ...render(
      <QueryClientProvider client={client}>
        <NotePickerDialog courseId={1} nodeTitle="Derivatives" onSelect={onSelect} onClose={onClose} />
      </QueryClientProvider>
    ),
  }
}

describe('NotePickerDialog', () => {
  beforeEach(() => {
    listNotes.mockReset()
    listNoteTags.mockReset()
    listNoteTags.mockResolvedValue([])
  })

  test('lists course notes and returns selected entries', async () => {
    listNotes.mockResolvedValue({
      items: [note(1, 'Derivative rules', ['limits']), note(2, 'Chain rule')],
      next_cursor: null,
    })
    const { onSelect } = renderDialog()
    expect(await screen.findByText('Derivative rules')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Derivative rules'))
    fireEvent.click(screen.getByText('Chain rule'))
    fireEvent.click(screen.getByRole('button', { name: /^add 2 notes$/i }))
    expect(onSelect).toHaveBeenCalledWith([
      { id: 1, title: 'Derivative rules' },
      { id: 2, title: 'Chain rule' },
    ])
  })

  test('fuzzy search filters the list', async () => {
    listNotes.mockResolvedValue({
      items: [note(1, 'Derivative rules'), note(2, 'Chain rule')],
      next_cursor: null,
    })
    renderDialog()
    expect(await screen.findByText('Derivative rules')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Filter notes…'), {
      target: { value: 'chain' },
    })
    await waitFor(() =>
      expect(screen.queryByText('Derivative rules')).not.toBeInTheDocument()
    )
    expect(screen.getByText('Chain rule')).toBeInTheDocument()
  })

  test('tag chips filter the list', async () => {
    listNotes.mockResolvedValue({
      items: [note(1, 'Derivative rules', ['limits']), note(2, 'Chain rule', ['algebra'])],
      next_cursor: null,
    })
    listNoteTags.mockResolvedValue([
      { tag: 'limits', count: 1 },
      { tag: 'algebra', count: 1 },
    ])
    renderDialog()
    expect(await screen.findByText('Derivative rules')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'limits' }))
    await waitFor(() =>
      expect(screen.queryByText('Chain rule')).not.toBeInTheDocument()
    )
    expect(screen.getByText('Derivative rules')).toBeInTheDocument()
  })

  test('select all shown toggles every visible note', async () => {
    listNotes.mockResolvedValue({
      items: [note(1, 'A'), note(2, 'B')],
      next_cursor: null,
    })
    const { onSelect } = renderDialog()
    await screen.findByText('A')

    fireEvent.click(screen.getByRole('checkbox', { name: /select shown \(2\)/i }))
    expect(screen.getByText('2 notes selected')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^add 2 notes$/i }))
    expect(onSelect).toHaveBeenCalledWith([
      { id: 1, title: 'A' },
      { id: 2, title: 'B' },
    ])
  })

  test('deselecting a row via its check indicator updates the count', async () => {
    listNotes.mockResolvedValue({
      items: [note(1, 'A'), note(2, 'B')],
      next_cursor: null,
    })
    renderDialog()
    await screen.findByText('A')

    fireEvent.click(screen.getByRole('checkbox', { name: 'A' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'B' }))
    expect(screen.getByText('2 notes selected')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: 'A' }))
    expect(screen.getByText('1 note selected')).toBeInTheDocument()
  })

  test('Escape closes the dialog', async () => {
    listNotes.mockResolvedValue({ items: [note(1, 'A')], next_cursor: null })
    const { onClose } = renderDialog()
    await screen.findByText('A')
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { LazyNoteEditor } from './LazyNoteEditor'

const getNote = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getNote: (id: number) => getNote(id),
  }
})

const NOTE = () => ({
  id: 3,
  title: 'Lazy loaded note',
  course_id: null,
  node_id: null,
  owner_type: 'standalone',
  owner_id: null,
  tags: [],
  pinned: false,
  updated_at: '2026-08-19T10:00:00',
  body: [{ type: 'text', md: 'Original body' }],
  drawings: [],
})

describe('LazyNoteEditor', () => {
  beforeEach(() => {
    getNote.mockReset()
    getNote.mockResolvedValue(NOTE())
  })

  test('renders the editor through the lazy boundary', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <LazyNoteEditor noteId={3} />
      </QueryClientProvider>
    )
    const title = await screen.findByRole('textbox', { name: 'Note title' }, { timeout: 5000 })
    expect(title).toHaveValue('Lazy loaded note')
  })

  test('passes onClose through to the mounted editor', async () => {
    const onClose = vi.fn()
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <LazyNoteEditor noteId={3} onClose={onClose} />
      </QueryClientProvider>
    )
    const close = await screen.findByRole('button', { name: 'Close' })
    close.click()
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})

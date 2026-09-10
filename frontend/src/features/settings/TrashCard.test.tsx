import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { TrashCard } from './TrashCard'

const listDeletedItems = vi.fn()
const restoreDeletedItem = vi.fn()
const purgeDeletedItem = vi.fn()

vi.mock('@/lib/api', () => ({
  listDeletedItems: () => listDeletedItems(),
  restoreDeletedItem: (id: number) => restoreDeletedItem(id),
  purgeDeletedItem: (id: number) => purgeDeletedItem(id),
}))

const ITEMS = [
  {
    id: 3,
    entity_type: 'quiz',
    title: 'Limits quiz',
    deleted_at: '2026-08-21T10:00:00',
    purge_after: '2026-08-28T10:00:00',
  },
]

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TrashCard />
    </QueryClientProvider>
  )
}

describe('TrashCard', () => {
  beforeEach(() => {
    listDeletedItems.mockReset()
    restoreDeletedItem.mockReset()
    purgeDeletedItem.mockReset()
    listDeletedItems.mockResolvedValue(ITEMS)
    restoreDeletedItem.mockResolvedValue({
      status: 'restored',
      entity_type: 'quiz',
      title: 'Limits quiz',
    })
    purgeDeletedItem.mockResolvedValue(undefined)
  })

  test('lists deleted items with their entity type', async () => {
    renderCard()
    expect(await screen.findByText('Limits quiz')).toBeInTheDocument()
    expect(screen.getByText('Quiz')).toBeInTheDocument()
  })

  test('restore calls the endpoint', async () => {
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: 'Restore' }))
    await waitFor(() => expect(restoreDeletedItem).toHaveBeenCalledWith(3))
  })

  test('delete forever purges the item', async () => {
    renderCard()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete forever' }))
    await waitFor(() => expect(purgeDeletedItem).toHaveBeenCalledWith(3))
  })

  test('empty state', async () => {
    listDeletedItems.mockResolvedValue([])
    renderCard()
    expect(await screen.findByText(/Nothing in the Trash/i)).toBeInTheDocument()
  })
})

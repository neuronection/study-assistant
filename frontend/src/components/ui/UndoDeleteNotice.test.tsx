import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { UndoDeleteNotice } from './UndoDeleteNotice'

const restoreDeletedItem = vi.fn()

vi.mock('@/lib/api', () => ({
  restoreDeletedItem: (id: number) => restoreDeletedItem(id),
}))

function renderNotice(props: Partial<Parameters<typeof UndoDeleteNotice>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <UndoDeleteNotice deletedItemId={null} onDismiss={vi.fn()} {...props} />
    </QueryClientProvider>
  )
}

describe('UndoDeleteNotice', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    restoreDeletedItem.mockReset()
    restoreDeletedItem.mockResolvedValue({ status: 'restored', entity_type: 'note', title: 'N' })
  })

  test('renders nothing without a deleted item', () => {
    const { container } = renderNotice()
    expect(container).toBeEmptyDOMElement()
  })

  test('shows the notice and Undo restores the item', async () => {
    const onDismiss = vi.fn()
    renderNotice({ deletedItemId: 7, onDismiss })
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    await waitFor(() => expect(restoreDeletedItem).toHaveBeenCalledWith(7))
    await waitFor(() => expect(onDismiss).toHaveBeenCalled())
  })

  test('auto-dismisses after the timeout', async () => {
    const onDismiss = vi.fn()
    renderNotice({ deletedItemId: 7, onDismiss })
    await vi.advanceTimersByTimeAsync(8100)
    expect(onDismiss).toHaveBeenCalled()
  })
})

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ReviewQueue } from './ReviewQueue'
import type { FlashcardInfo } from '@/lib/api'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, values?: Record<string, unknown>) =>
        values ? `${key}:${JSON.stringify(values)}` : key,
    }),
  }
})

function makeCard(id: number, frontMd: string): FlashcardInfo {
  return {
    id,
    kind: 'basic',
    front: [{ type: 'text', md: frontMd }],
    back: [{ type: 'text', md: `back ${id}` }],
    source: 'manual',
    source_ref: null,
    node_id: null,
    due_at: null,
    state: 'new',
  }
}

function renderQueue(ui: React.ReactElement) {
  const client = new QueryClient()
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('ReviewQueue (presentational)', () => {
  const onRate = vi.fn()

  beforeEach(() => {
    onRate.mockReset()
  })

  test('renders the first card, reveals on click, rates via keyboard 1-4', async () => {
    renderQueue(
      <ReviewQueue
        cards={[makeCard(1, 'front one'), makeCard(2, 'front two')]}
        onRate={onRate}
      />
    )
    expect(screen.getByText('front one')).toBeInTheDocument()
    expect(screen.queryByText('back 1')).not.toBeInTheDocument()

    const reveal = screen.getByRole('button', { name: /cards\.reveal/ })
    fireEvent.click(reveal)
    expect(await screen.findByText('back 1')).toBeInTheDocument()

    fireEvent.keyDown(document.body, { key: '3' })
    expect(onRate).toHaveBeenCalledTimes(1)
    expect(onRate).toHaveBeenCalledWith(
      expect.objectContaining({ id: 1 }),
      3
    )
    await waitFor(() => expect(screen.getByText('front two')).toBeInTheDocument())
  })

  test('progress counter advances and completion renders when the batch empties', () => {
    renderQueue(
      <ReviewQueue
        cards={[makeCard(1, 'front one')]}
        total={4}
        onRate={onRate}
        completion={<p>batch-complete-view</p>}
      />
    )
    fireEvent.keyDown(document.body, { key: '2' })
    expect(onRate).toHaveBeenCalledTimes(1)
    expect(
      screen.getByText(/batch-complete-view/)
    ).toBeInTheDocument()
  })

  test('empty queue renders the completion node directly', () => {
    renderQueue(
      <ReviewQueue cards={[]} onRate={onRate} completion={<p>all-clear-view</p>} />
    )
    expect(screen.getByText('all-clear-view')).toBeInTheDocument()
    expect(onRate).not.toHaveBeenCalled()
  })

  test('ratings are ignored while busy', () => {
    renderQueue(
      <ReviewQueue cards={[makeCard(1, 'front one')]} busy onRate={onRate} />
    )
    fireEvent.keyDown(document.body, { key: '4' })
    expect(onRate).not.toHaveBeenCalled()
  })
})

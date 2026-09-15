import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ReviewPage } from './ReviewPage'
import type { ReviewDue } from '@/lib/api'

const getReviewDue = vi.fn()
const reviewFlashcard = vi.fn()
const useStudySession = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getReviewDue: (perCourse?: number) => getReviewDue(perCourse),
    reviewFlashcard: (cardId: number, rating: number) =>
      reviewFlashcard(cardId, rating),
  }
})

vi.mock('@/lib/use-study-session', () => ({
  useStudySession: (options: unknown) => useStudySession(options),
}))

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

function makeCard(id: number, frontMd: string) {
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

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ReviewPage />
    </QueryClientProvider>
  )
}

const DUE: ReviewDue = {
  total_due: 3,
  groups: [
    {
      course_id: 1,
      course_title: 'Calculus',
      course_color: '#6366f1',
      due_count: 2,
      cards: [makeCard(11, 'derivative'), makeCard(12, 'integral')],
    },
    {
      course_id: 2,
      course_title: 'Algebra',
      course_color: null,
      due_count: 1,
      cards: [makeCard(21, 'eigenvalue')],
    },
  ],
}

describe('ReviewPage', () => {
  beforeEach(() => {
    getReviewDue.mockReset()
    reviewFlashcard.mockReset()
    reviewFlashcard.mockResolvedValue({ interval_days: 3, due_at: 'x', state: 'review' })
    useStudySession.mockReset()
  })

  test('aggregates courses, chips each card, and logs a review session', async () => {
    getReviewDue.mockResolvedValue(DUE)
    renderPage()
    expect(await screen.findByText('derivative')).toBeInTheDocument()
    expect(screen.getByText('Calculus')).toBeInTheDocument()
    expect(screen.queryByText('eigenvalue')).not.toBeInTheDocument()
    expect(useStudySession).toHaveBeenCalledWith(
      expect.objectContaining({ kind: 'review', entityRef: 'review:page' })
    )
  })

  test('all-clear state when nothing is due', async () => {
    getReviewDue.mockResolvedValue({ total_due: 0, groups: [] })
    renderPage()
    expect(await screen.findByText('review.allClearTitle')).toBeInTheDocument()
  })

  test('rating flows to the review endpoint', async () => {
    getReviewDue.mockResolvedValue(DUE)
    renderPage()
    await screen.findByText('derivative')
    await waitFor(() => {
      expect(useStudySession).toHaveBeenCalled()
    })
    expect(reviewFlashcard).not.toHaveBeenCalled()
  })
})

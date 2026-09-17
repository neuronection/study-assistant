import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { StudySessionPage } from './StudySessionFlow'
import type { ReviewDue } from '@/lib/api'

const getStudyNext = vi.fn()
const getReviewDue = vi.fn()
const reviewFlashcard = vi.fn()
const updatePlanItem = vi.fn()
const navigate = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getStudyNext: () => getStudyNext(),
    getReviewDue: () => getReviewDue(),
    reviewFlashcard: (cardId: number, rating: number) =>
      reviewFlashcard(cardId, rating),
    updatePlanItem: (...args: unknown[]) =>
      updatePlanItem(...(args as [number, number, { done?: boolean }])),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
  Link: ({ children }: { children: React.ReactNode }) => <a href="#">{children}</a>,
}))

vi.mock('@/features/ai/GenerateDialog', () => ({
  GenerateDialog: () => <div>generate-dialog</div>,
}))

function makeCard(id: number, front: string) {
  return {
    id,
    kind: 'basic',
    front: [{ type: 'text', md: front }],
    back: [{ type: 'text', md: `back ${front}` }],
    source: 'manual',
    source_ref: null,
    node_id: null,
    due_at: null,
    state: 'new',
  }
}

const DUE: ReviewDue = {
  total_due: 1,
  groups: [
    {
      course_id: 3,
      course_title: 'Calculus I',
      course_color: null,
      due_count: 1,
      cards: [makeCard(11, 'derivative of x^2')],
    },
  ],
}

function renderFlow() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <StudySessionPage />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('StudySessionPage', () => {
  test('shows an honest all-clear when nothing needs the student', async () => {
    getStudyNext.mockResolvedValue({
      due_cards: 0,
      review_courses: [],
      plan_rows: [],
      weak_cells: [],
      goal_unit: 'answers',
      goal_done: 5,
      goal_target: 20,
      streak: 0,
    })
    renderFlow()
    expect(await screen.findByText('Nothing to study right now')).toBeInTheDocument()
  })

  test('runs review and plan phases, then lands on the wrap-up', async () => {
    getStudyNext.mockResolvedValue({
      due_cards: 1,
      review_courses: ['Calculus I'],
      plan_rows: [
        {
          item_id: 77,
          title: 'Review limits',
          course_id: 3,
          course_title: 'Calculus I',
          due_date: '2026-09-16',
          overdue: true,
        },
      ],
      weak_cells: [],
      goal_unit: 'answers',
      goal_done: 2,
      goal_target: 20,
      streak: 3,
    })
    getReviewDue.mockResolvedValue(DUE)
    updatePlanItem.mockResolvedValue({ id: 77, done: true })

    renderFlow()
    expect(await screen.findByText('Review 1 due cards')).toBeInTheDocument()
    expect(screen.getByText('derivative of x^2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Skip this phase' }))
    expect(await screen.findByText('Plan triage — 1 open')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(updatePlanItem).toHaveBeenCalledWith(3, 77, { done: true }))
    fireEvent.click(await screen.findByRole('button', { name: 'Continue' }))

    expect(await screen.findByText('Session wrapped up')).toBeInTheDocument()
    expect(screen.getByText('1 plan item checked off')).toBeInTheDocument()
    expect(screen.getByText('0 cards reviewed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to Home' })).toBeInTheDocument()
  })

  test('practice phase offers prefilled generation for weak cells', async () => {
    getStudyNext.mockResolvedValue({
      due_cards: 0,
      review_courses: [],
      plan_rows: [],
      weak_cells: [
        {
          course_id: 3,
          course_title: 'Calculus I',
          concept: 'integration by parts',
          skill: 'compute',
          n: 9,
          accuracy: 0.33,
          weakness_score: 0.8,
        },
      ],
      goal_unit: 'answers',
      goal_done: 0,
      goal_target: 20,
      streak: 0,
    })
    renderFlow()
    expect(
      await screen.findByText('Practice: integration by parts'),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Practice this' }))
    expect(screen.getByText('generate-dialog')).toBeInTheDocument()
  })
})

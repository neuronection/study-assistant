import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { PapersPanel } from './PapersPanel'

const listPapers = vi.fn()
const createPaper = vi.fn()
const paperReport = vi.fn()
const deletePaper = vi.fn()
const navigate = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listPapers: (courseId: string) => listPapers(courseId),
    createPaper: (courseId: string, body: unknown) => createPaper(courseId, body),
    paperReport: (paperId: string, attemptId?: string | null) =>
      paperReport(paperId, attemptId),
    deletePaper: (paperId: string) => deletePaper(paperId),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) =>
    select({ location: { href: '/courses/c1/n/n1?tab=practice', search: {} } }),
}))

vi.mock('@/lib/ui-overlays', () => ({
  useCloseFloatings: () => {},
}))

const PAPER = {
  id: 'paper-1',
  course_id: 'c1',
  activity_id: 'act-1',
  node_id: 'n1',
  title: 'Calculus mock',
  instructions_md: null,
  duration_min: 90,
  total_marks: 30,
  source: 'bank',
  latest_attempt_id: 'attempt-1',
  latest_percent: 0.6667,
  attempt_count: 1,
  created_at: '2026-11-11T10:00:00Z',
  sections: [
    { id: 's1', title: 'Short answers', marks: 10, count: 3 },
    { id: 's2', title: 'Long answers', marks: 20, count: 2 },
  ],
}

const REPORT = {
  paper_id: 'paper-1',
  attempt_id: 'attempt-1',
  finished_at: '2026-11-11T11:30:00Z',
  earned: 20,
  total: 30,
  percent: 0.6667,
  grade: 'D',
  answered: 5,
  question_count: 5,
  sections: [
    { id: 's1', title: 'Short answers', marks: 10, earned: 10 },
    { id: 's2', title: 'Long answers', marks: 20, earned: 10 },
  ],
  topics: [
    { concept_id: 'concept-1', name: 'Integration by parts', lost: 10, marks: 20 },
  ],
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PapersPanel courseId="c1" nodeId="n1" />
    </QueryClientProvider>,
  )
}

describe('PapersPanel', () => {
  beforeEach(() => {
    listPapers.mockReset().mockResolvedValue([PAPER])
    createPaper.mockReset().mockResolvedValue(PAPER)
    paperReport.mockReset().mockResolvedValue(REPORT)
    deletePaper.mockReset().mockResolvedValue(undefined)
    navigate.mockReset()
  })

  test('lists a paper and starts it in exam mode', async () => {
    renderPanel()
    expect(await screen.findByText('Calculus mock')).toBeInTheDocument()
    expect(screen.getByText(/latest 67%/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Sit' }))

    expect(navigate).toHaveBeenCalledWith({
      to: '/quiz/$activityId',
      params: { activityId: 'act-1' },
      search: { from: '/courses/c1/n/n1?tab=practice', mode: 'exam' },
    })
  })

  test('opens the marked report with section and topic breakdown', async () => {
    renderPanel()
    fireEvent.click(
      await screen.findByRole('button', { name: 'Report for Calculus mock' }),
    )

    expect(await screen.findByText('20 / 30')).toBeInTheDocument()
    expect(screen.getByText('Grade D')).toBeInTheDocument()
    expect(screen.getByText('Integration by parts')).toBeInTheDocument()
    expect(screen.getByText('−10 marks')).toBeInTheDocument()
  })

  test('assembles a paper from the builder and sends the blueprint', async () => {
    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: 'New paper' }))
    expect(screen.getByRole('dialog', { name: 'Assemble a paper' })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Marks for section 1'), {
      target: { value: '30' },
    })
    expect(screen.getByText('30 marks total')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Assemble paper' }))

    await waitFor(() => expect(createPaper).toHaveBeenCalled())
    expect(createPaper).toHaveBeenCalledWith(
      'c1',
      expect.objectContaining({
        title: 'Mock exam',
        duration_min: 90,
        node_id: 'n1',
        sections: [
          expect.objectContaining({ title: 'Section A', count: 5, marks: 30 }),
        ],
      }),
    )
  })
})

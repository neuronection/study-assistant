import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, beforeEach, expect, test, vi } from 'vitest'

import { DrillsCard } from './DrillsCard'
import { useWorkspaceStore } from '@/lib/workspace-store'

const drillPatterns = vi.fn()
const startDrill = vi.fn()
const proposePatterns = vi.fn()
const createPattern = vi.fn()
const listCourses = vi.fn()
const navigate = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    drillPatterns: (courseId: number) => drillPatterns(courseId),
    startDrill: (pattern: string, courseId: number) => startDrill(pattern, courseId),
    proposePatterns: (courseId: number) => proposePatterns(courseId),
    createPattern: (courseId: number, proposal: unknown) => createPattern(courseId, proposal),
    listCourses: () => listCourses(),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) =>
    select({ location: { href: '/', search: {} } }),
}))

function renderCard(courseId?: number) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DrillsCard courseId={courseId} />
    </QueryClientProvider>
  )
}

const PATTERNS = [
  {
    pattern: 'sign_slip',
    name: 'Sign slip',
    description: 'dropping or flipping a minus sign mid-derivation',
    source: 'seeded',
    occurrences: 0,
  },
  {
    pattern: 'missing_chain_rule_factor',
    name: 'Missing chain-rule factor',
    description: 'forgetting the inner derivative',
    source: 'seeded',
    occurrences: 3,
  },
  {
    pattern: 'forgot_product_second_term',
    name: 'Forgot product second term',
    description: 'dropping the second term of the product rule',
    source: 'discovered',
    occurrences: 1,
  },
]

const COURSE = (id: number, title: string) => ({
  id,
  title,
  subject: null,
  level: null,
  description: null,
  color: null,
  archived_at: null,
  material_count: 0,
})

describe('DrillsCard', () => {
  beforeEach(() => {
    drillPatterns.mockReset()
    startDrill.mockReset()
    proposePatterns.mockReset()
    createPattern.mockReset()
    listCourses.mockReset()
    drillPatterns.mockResolvedValue(PATTERNS)
    listCourses.mockResolvedValue([COURSE(1, 'Calculus I'), COURSE(2, 'Linear Algebra')])
    useWorkspaceStore.setState({ courseId: null, hydrated: true })
  })

  test('lists seeded and discovered patterns with counts, drills against the bound course', async () => {
    startDrill.mockResolvedValue({ id: 7, step_count: 3 })
    renderCard(4)
    expect(await screen.findByText('Sign slip')).toBeInTheDocument()
    expect(screen.getByText('3 mistakes')).toBeInTheDocument()
    expect(screen.getByText('Discovered for this course type')).toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: /drill/i })[1])
    await waitFor(() =>
      expect(startDrill).toHaveBeenCalledWith('missing_chain_rule_factor', 4)
    )
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/exercises/$exerciseId',
        params: { exerciseId: '7' },
        search: { from: '/' },
      })
    )
  })

  test('without a course prop falls back to the workspace course', async () => {
    useWorkspaceStore.setState({ courseId: 12, hydrated: true })
    listCourses.mockResolvedValue([COURSE(12, 'Calculus I')])
    startDrill.mockResolvedValue({ id: 8, step_count: 2 })
    renderCard()
    const drillButtons = await screen.findAllByRole('button', { name: /drill/i })
    fireEvent.click(drillButtons[0])
    await waitFor(() => expect(startDrill).toHaveBeenCalledWith('sign_slip', 12))
  })

  test('proposes, approves and dismisses discovered patterns', async () => {
    drillPatterns.mockResolvedValue([PATTERNS[0]])
    proposePatterns.mockResolvedValue([
      {
        key: 'forgot_product_second_term',
        name: 'Forgot product second term',
        description: 'dropping the second term of the product rule',
        example: 'd/dx (fg) written as f\u2032g',
      },
    ])
    createPattern.mockResolvedValue({ ...PATTERNS[2], occurrences: 0 })
    renderCard(4)
    expect(
      screen.queryByText('No error patterns yet. Wrong answers from quizzes will build this list.')
    ).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /find more patterns/i }))
    expect(await screen.findByText('Forgot product second term')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /approve/i }))
    await waitFor(() =>
      expect(createPattern).toHaveBeenCalledWith(4, {
        key: 'forgot_product_second_term',
        name: 'Forgot product second term',
        description: 'dropping the second term of the product rule',
        example: 'd/dx (fg) written as f\u2032g',
      })
    )
    await waitFor(() =>
      expect(screen.queryByText('Forgot product second term')).not.toBeInTheDocument()
    )
  })

  test('dismiss removes a proposal without creating anything', async () => {
    drillPatterns.mockResolvedValue([PATTERNS[0]])
    proposePatterns.mockResolvedValue([
      {
        key: 'forgot_product_second_term',
        name: 'Forgot product second term',
        description: 'dropping the second term of the product rule',
      },
    ])
    renderCard(4)
    fireEvent.click(await screen.findByRole('button', { name: /find more patterns/i }))
    expect(await screen.findByText('Forgot product second term')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(createPattern).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(screen.queryByText('Forgot product second term')).not.toBeInTheDocument()
    )
  })

  test('empty state hides the list and find-more shows a no-proposals note', async () => {
    drillPatterns.mockResolvedValue([])
    proposePatterns.mockResolvedValue([])
    renderCard(4)
    expect(
      await screen.findByText('No error patterns yet. Wrong answers from quizzes will build this list.')
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /find more patterns/i }))
    expect(
      await screen.findByText('No new patterns found from your recent mistakes.')
    ).toBeInTheDocument()
  })
})
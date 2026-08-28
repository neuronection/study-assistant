import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { HomePage } from './HomePage'
import { useWorkspaceStore } from '@/lib/workspace-store'

const getOverview = vi.fn()
const getExamStatus = vi.fn()
const getRecommendations = vi.fn()
const listCourses = vi.fn()
const generateQuiz = vi.fn()
const createChatSession = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getOverview: () => getOverview(),
    getExamStatus: () => getExamStatus(),
    getRecommendations: () => getRecommendations(),
    listCourses: () => listCourses(),
    generateQuiz: (body: unknown) => generateQuiz(body),
    createChatSession: (courseId: number, nodeId: number | null, title?: string) =>
      createChatSession(courseId, nodeId, title),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) =>
      select({ location: { href: '/', search: {} } }),
  useNavigate: () => vi.fn(),
  Link: ({ children }: { children: React.ReactNode }) => <a href="#">{children}</a>,
}))

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <HomePage />
    </QueryClientProvider>
  )
}

const OVERVIEW = {
  today: { day: '2026-08-19', answers_n: 8, correct_n: 6, cards_reviewed: 3, minutes: 12, xp: 75 },
  goal: 10,
  streak: 4,
  total_xp: 1200,
  level: 4,
  due_cards: 6,
  history: [
    { day: '2026-08-18', answers_n: 5, correct_n: 4, cards_reviewed: 0, minutes: 6, xp: 48 },
    { day: '2026-08-19', answers_n: 8, correct_n: 6, cards_reviewed: 3, minutes: 12, xp: 75 },
  ],
}

describe('HomePage (Today screen)', () => {
  beforeEach(() => {
    getOverview.mockReset()
    getExamStatus.mockReset()
    getRecommendations.mockReset()
    listCourses.mockReset()
    generateQuiz.mockReset()
    createChatSession.mockReset()
    listCourses.mockResolvedValue([])
    getExamStatus.mockResolvedValue([])
    useWorkspaceStore.setState({ courseId: null, hydrated: true })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ status: 'ok', version: '9.9.9', db: 'ok' }), { status: 200 })
      )
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('shows backend version when health resolves', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([])
    renderHome()
    expect(await screen.findByText('Backend 9.9.9')).toBeInTheDocument()
  })

  test('shows offline badge when health rejects', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('down')
      })
    )
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([])
    renderHome()
    expect(await screen.findByText('Backend offline')).toBeInTheDocument()
  })

  test('renders streak, goal progress, due reviews, and heatmap days', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([])
    renderHome()
    expect(await screen.findByText('4')).toBeInTheDocument()
    expect(screen.getByText('days')).toBeInTheDocument()
    expect(screen.getByText('80%')).toBeInTheDocument()
    expect(screen.getByText('8/10')).toBeInTheDocument()
    expect(screen.getByText('6')).toBeInTheDocument()
  })

  test('lists next-best actions with evidence lines', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([
      {
        kind: 'review',
        priority: 110,
        concept: null,
        skill: null,
        evidence: { due_cards: 6 },
      },
      {
        kind: 'drill',
        priority: 30,
        concept: 'derivatives',
        skill: 'procedural',
        evidence: { misses: 4, n: 9, accuracy: 0.44 },
      },
    ])
    renderHome()
    expect(await screen.findByText(/Review due cards/)).toBeInTheDocument()
    expect(screen.getByText(/6 cards are due/)).toBeInTheDocument()
    expect(screen.getByText(/derivatives/)).toBeInTheDocument()
    expect(screen.getByText(/4 misses out of 9/)).toBeInTheDocument()
  })

  test('empty recommendations state', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([])
    renderHome()
    expect(
      await screen.findByText(/personalized suggestions will appear here/i)
    ).toBeInTheDocument()
  })

  test('drill button generates a weak-area quiz on the concept', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([
      {
        kind: 'drill',
        priority: 30,
        concept: 'u-substitution',
        skill: 'procedural',
        evidence: { misses: 5, n: 8, accuracy: 0.375 },
      },
    ])
    useWorkspaceStore.setState({ courseId: 5, hydrated: true })
    generateQuiz.mockResolvedValue({ id: 42, title: 'u-substitution', question_count: 8 })
    renderHome()
    const drillButton = await screen.findByRole('button', { name: /drill/i })
    fireEvent.click(drillButton)
    await waitFor(() =>
      expect(generateQuiz).toHaveBeenCalledWith({
        course_id: 5,
        topic: 'u-substitution',
        skill: 'procedural',
        count: 8,
        difficulty: 2,
      })
    )
  })

  test('drill button offers asking the tutor about the weak concept', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([
      {
        kind: 'drill',
        priority: 30,
        concept: 'u-substitution',
        skill: 'procedural',
        evidence: { misses: 5, n: 8, accuracy: 0.375 },
      },
    ])
    useWorkspaceStore.setState({ courseId: 5, hydrated: true })
    createChatSession.mockResolvedValue({ id: 99, course_id: 5, node_id: null, title: 'Ask about u-substitution' })
    renderHome()
    const askButton = await screen.findByRole('button', { name: /ask the tutor/i })
    fireEvent.click(askButton)
    await waitFor(() =>
      expect(createChatSession).toHaveBeenCalledWith(5, null, 'Ask about u-substitution')
    )
  })

  test('drill button falls back to the single course when all courses is active', async () => {    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([
      {
        kind: 'challenge',
        priority: 30,
        concept: 'u-substitution',
        skill: 'procedural',
        evidence: { misses: 5, n: 8, accuracy: 0.375 },
      },
    ])
    listCourses.mockResolvedValue([
      { id: 5, title: 'Calculus I', subject: null, level: null, description: null, color: null, archived_at: null, material_count: 0 },
    ])
    generateQuiz.mockResolvedValue({ id: 42, title: 'u-substitution', question_count: 8 })
    renderHome()
    const challengeButton = await screen.findByRole('button', { name: /challenge/i })
    fireEvent.click(challengeButton)
    await waitFor(() =>
      expect(generateQuiz).toHaveBeenCalledWith(
        expect.objectContaining({ course_id: 5, difficulty: 4 })
      )
    )
  })

  test('drill button asks for a course when several exist and none is selected', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([
      {
        kind: 'drill',
        priority: 30,
        concept: 'u-substitution',
        skill: 'procedural',
        evidence: { misses: 5, n: 8, accuracy: 0.375 },
      },
    ])
    listCourses.mockResolvedValue([
      { id: 5, title: 'Calculus I', subject: null, level: null, description: null, color: null, archived_at: null, material_count: 0 },
      { id: 6, title: 'Linear Algebra', subject: null, level: null, description: null, color: null, archived_at: null, material_count: 0 },
    ])
    renderHome()
    await screen.findByText(/u-substitution/)
    await screen.findByText(/Open a course first/i)
    expect(generateQuiz).not.toHaveBeenCalled()
  })
})

describe('HomePage exam card', () => {
  beforeEach(() => {
    getOverview.mockReset()
    getExamStatus.mockReset()
    getRecommendations.mockReset()
    listCourses.mockReset()
    generateQuiz.mockReset()
    createChatSession.mockReset()
    listCourses.mockResolvedValue([])
    getExamStatus.mockResolvedValue([])
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([])
    useWorkspaceStore.setState({ courseId: null, hydrated: true })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ status: 'ok', version: '9.9.9', db: 'ok' }), { status: 200 })
      )
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('hides the exam card without upcoming exams', async () => {
    renderHome()
    await screen.findByText('Backend 9.9.9')
    expect(screen.queryByText(/exam in/i)).not.toBeInTheDocument()
  })

  test('renders countdown, coverage and a jump to the most-behind node', async () => {
    getExamStatus.mockResolvedValue([
      {
        course_id: 3,
        course_title: 'Calculus I',
        exam_date: '2026-08-31',
        days_left: 10,
        total_nodes: 8,
        engaged_nodes: 5,
        remaining_nodes: 3,
        nodes_per_day: 0.3,
        on_track: true,
        most_behind_node: { id: 12, title: 'Integrals' },
      },
    ])
    renderHome()
    expect(
      await screen.findByText(/Calculus I — exam in 10 days/)
    ).toBeInTheDocument()
    expect(screen.getByText(/5\/8 nodes studied/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Go to Integrals/ })).toBeInTheDocument()
  })

  test('off-track exams render the danger pace line', async () => {
    getExamStatus.mockResolvedValue([
      {
        course_id: 4,
        course_title: 'Linear Algebra',
        exam_date: '2026-08-25',
        days_left: 4,
        total_nodes: 9,
        engaged_nodes: 1,
        remaining_nodes: 8,
        nodes_per_day: 2.0,
        on_track: false,
        most_behind_node: { id: 20, title: 'Eigenvalues' },
      },
    ])
    renderHome()
    expect(await screen.findByText(/Linear Algebra — exam in 4 days/)).toBeInTheDocument()
    expect(screen.getByText(/1\/9 nodes studied/).className).toContain('text-danger')
  })
})

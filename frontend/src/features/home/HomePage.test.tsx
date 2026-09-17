import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'

import { HomePage } from './HomePage'
import { useWorkspaceStore } from '@/lib/workspace-store'

const getOverview = vi.fn()
const getExamStatus = vi.fn()
const getStudyNext = vi.fn()
const getRecommendations = vi.fn()
const listCourses = vi.fn()
const generateQuiz = vi.fn()
const createChatSession = vi.fn()
const listUpcomingItems = vi.fn()
const setDailyGoal = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getOverview: () => getOverview(),
    getExamStatus: () => getExamStatus(),
    getStudyNext: () => getStudyNext(),
    getRecommendations: () => getRecommendations(),
    listCourses: () => listCourses(),
    generateQuiz: (body: unknown) => generateQuiz(body),
    createChatSession: (courseId: number, nodeId: number | null, title?: string) =>
      createChatSession(courseId, nodeId, title),
    listUpcomingItems: (days?: number) => listUpcomingItems(days),
    setDailyGoal: (body: unknown) => setDailyGoal(body),
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
  today: { day: '2026-08-19', answers_n: 8, correct_n: 6, cards_reviewed: 3, minutes: 12, study_seconds: 1320, xp: 75 },
  unit: 'answers',
  answers_per_day: 10,
  minutes_per_day: 30,
  streak: 4,
  total_xp: 1200,
  level: 4,
  due_cards: 6,
  study_seconds_week: 5400,
  history: [
    { day: '2026-08-18', answers_n: 5, correct_n: 4, cards_reviewed: 0, minutes: 6, study_seconds: 0, xp: 48 },
    { day: '2026-08-19', answers_n: 8, correct_n: 6, cards_reviewed: 3, minutes: 12, study_seconds: 1320, xp: 75 },
  ],
}

const MINUTES_OVERVIEW = {
  ...OVERVIEW,
  unit: 'minutes',
  today: { ...OVERVIEW.today, study_seconds: 900 },
}

describe('HomePage (Today screen)', () => {

  test('shows the readiness ring, trend and weakest concepts', async () => {
    getExamStatus.mockResolvedValue([
      {
        course_id: 5,
        course_title: 'Calculus',
        exam_date: '2030-01-01',
        days_left: 9,
        total_nodes: 4,
        engaged_nodes: 2,
        remaining_nodes: 2,
        nodes_per_day: 0.3,
        on_track: true,
        most_behind_node: null,
        readiness: 72,
        readiness_state: 'ok',
        trend: 'improving',
        weakest: ['integration by parts'],
        answers_in_scope: 12,
      },
    ])
    renderHome()
    expect(await screen.findByText('Readiness 72')).toBeInTheDocument()
    expect(await screen.findByText(/improving/)).toBeInTheDocument()
    expect(screen.getByText(/Weakest: integration by parts/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '72' })).toBeInTheDocument()
  })

  test('shows the honest not-enough-data state', async () => {
    getExamStatus.mockResolvedValue([
      {
        course_id: 5,
        course_title: 'Calculus',
        exam_date: '2030-01-01',
        days_left: 9,
        total_nodes: 4,
        engaged_nodes: 0,
        remaining_nodes: 4,
        nodes_per_day: 0.5,
        on_track: true,
        most_behind_node: null,
        readiness: null,
        readiness_state: 'not_enough_data',
        trend: null,
        weakest: [],
        answers_in_scope: 0,
      },
    ])
    renderHome()
    expect(
      await screen.findByText(/Readiness appears after a few answered questions/)
    ).toBeInTheDocument()
  })

  beforeEach(() => {
    getOverview.mockReset()
    getExamStatus.mockReset()
    getRecommendations.mockReset()
    listCourses.mockReset()
    generateQuiz.mockReset()
    createChatSession.mockReset()
    listUpcomingItems.mockReset()
    listUpcomingItems.mockResolvedValue([])
    setDailyGoal.mockReset()
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

  test('study-now card shows counts and links into the session', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getExamStatus.mockResolvedValue([])
    getRecommendations.mockResolvedValue([])
    listUpcomingItems.mockResolvedValue([])
    getStudyNext.mockResolvedValue({
      due_cards: 3,
      review_courses: ['Calculus I'],
      plan_rows: [
        {
          item_id: 1,
          title: 'Review limits',
          course_id: 3,
          course_title: 'Calculus I',
          due_date: '2026-09-16',
          overdue: true,
        },
      ],
      weak_cells: [],
      goal_unit: 'answers',
      goal_done: 0,
      goal_target: 20,
      streak: 1,
    })
    renderHome()
    expect(await screen.findByText('Study now')).toBeInTheDocument()
    expect(screen.getByText('3 cards due · 1 plan item')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start session' })).toBeEnabled()
  })

  test('study-now card is disabled with an all-clear at zero', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getExamStatus.mockResolvedValue([])
    getRecommendations.mockResolvedValue([])
    listUpcomingItems.mockResolvedValue([])
    getStudyNext.mockResolvedValue({
      due_cards: 0,
      review_courses: [],
      plan_rows: [],
      weak_cells: [],
      goal_unit: 'answers',
      goal_done: 20,
      goal_target: 20,
      streak: 5,
    })
    renderHome()
    expect(await screen.findByText(/Nothing needs you right now/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start session' })).toBeDisabled()
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

  test('renders the study-time card with today and this week', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([])
    renderHome()
    expect(await screen.findByText('Study time')).toBeInTheDocument()
    expect(await screen.findByText('22 min')).toBeInTheDocument()
    expect(screen.getByText('This week: 1 h 30 min')).toBeInTheDocument()
  })

  test('goal ring switches to minutes under the minutes unit', async () => {
    getOverview.mockResolvedValue(MINUTES_OVERVIEW)
    getRecommendations.mockResolvedValue([])
    renderHome()
    expect(await screen.findByText('15/30')).toBeInTheDocument()
    expect(screen.queryByText('80%')).not.toBeInTheDocument()
  })

  test('goal editor switches unit and saves the minutes goal', async () => {
    getOverview.mockResolvedValue(OVERVIEW)
    getRecommendations.mockResolvedValue([])
    setDailyGoal.mockResolvedValue({ unit: 'minutes', answers_per_day: 10, minutes_per_day: 45 })
    renderHome()
    fireEvent.click(await screen.findByText('change'))
    fireEvent.click(screen.getByRole('radio', { name: 'Minutes' }))
    const input = screen.getByRole('spinbutton', { name: 'Goal value' })
    fireEvent.change(input, { target: { value: '45' } })
    fireEvent.click(screen.getByText('save'))
    await waitFor(() =>
      expect(setDailyGoal).toHaveBeenCalledWith({ unit: 'minutes', minutes_per_day: 45 })
    )
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
    listUpcomingItems.mockReset()
    listUpcomingItems.mockResolvedValue([])
    setDailyGoal.mockReset()
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

  test('shows skeletons while the overview loads instead of zeroed stats', async () => {
    getOverview.mockReturnValue(new Promise(() => {}))
    getExamStatus.mockResolvedValue([])
    getRecommendations.mockResolvedValue([])
    listUpcomingItems.mockResolvedValue([])
    renderHome()
    await waitFor(() => {
      expect(document.querySelectorAll('[data-as="skeleton"]').length).toBeGreaterThan(0)
    })
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
    expect(screen.queryByText(/activity heatmap builds up/i)).not.toBeInTheDocument()
  })
})

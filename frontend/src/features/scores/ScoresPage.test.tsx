import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ScoresPage } from './ScoresPage'

const listQuizAttempts = vi.fn()
const listMistakes = vi.fn()
const getDiagnostics = vi.fn()
const getRecommendations = vi.fn()
const getItems = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listQuizAttempts: () => listQuizAttempts(),
    listMistakes: () => listMistakes(),
    getDiagnostics: () => getDiagnostics(),
    getRecommendations: () => getRecommendations(),
    getItems: () => getItems(),
  }
})

async function renderPage(initial = '/scores') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute({ component: () => <Outlet /> })
  const stub = (path: string) =>
    createRoute({ getParentRoute: () => rootRoute, path, component: () => null })
  const scoresRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/scores',
    validateSearch: (search: Record<string, unknown>) => ({
      tab: typeof search.tab === 'string' ? search.tab : undefined,
    }),
    component: () => <ScoresPage />,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([
      scoresRoute,
      stub('/quiz/$activityId'),
      stub('/courses'),
      stub('/library'),
    ]),
    history: createMemoryHistory({ initialEntries: [initial] }),
  })
  const result = render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  await screen.findByRole('heading', { name: /scores/i })
  return result
}

const DIAGNOSTICS = {
  weakness_matrix: [
    {
      concept: 'derivatives',
      skill: 'procedural',
      n: 6,
      accuracy: 0.4,
      avg_time_ratio: 0.8,
      last_seen_at: '2026-08-19T10:00:00',
      weakness_score: 0.5,
      enough_data: true,
    },
    {
      concept: 'limits',
      skill: 'conceptual',
      n: 1,
      accuracy: 1.0,
      avg_time_ratio: null,
      last_seen_at: '2026-08-19T10:00:00',
      weakness_score: 0.1,
      enough_data: false,
    },
  ],
  error_profile: [
    { tag: 'sign_slip', total: 7, recent_7d: 3, previous_7d: 5, trend: -2, last_seen_at: 'x' },
  ],
  speed_accuracy: [
    { concept: 'derivatives', n: 6, accuracy: 0.4, avg_time_ratio: 0.5, speed: 'rushing', quadrant: 'rushing' },
  ],
  skills: ['conceptual', 'procedural', 'applied', 'notation'],
}

describe('ScoresPage', () => {
  beforeEach(() => {
    listQuizAttempts.mockReset()
    listMistakes.mockReset()
    getDiagnostics.mockReset()
    getRecommendations.mockReset()
    getItems.mockReset()
    getItems.mockResolvedValue([])
    listQuizAttempts.mockResolvedValue([])
    listMistakes.mockResolvedValue([])
    getDiagnostics.mockResolvedValue(DIAGNOSTICS)
    getRecommendations.mockResolvedValue([])
  })

  test('history tab lists attempts with score coloring', async () => {
    listQuizAttempts.mockResolvedValue([
      {
        id: '1',
        activity_id: '2',
        title: 'Quiz · today',
        mode: 'practice',
        started_at: '2026-08-19T09:00:00',
        finished_at: '2026-08-19T09:05:00',
        score: 0.85,
      },
    ])
    await renderPage()
    expect(await screen.findByText('Quiz · today')).toBeInTheDocument()
    expect(screen.getByText('85%')).toBeInTheDocument()
  })

  test('diagnostics tab renders matrix, error profile and quadrants', async () => {
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: /diagnostics/i }))
    expect(await screen.findByText('40%')).toBeInTheDocument()
    expect(screen.getAllByText('derivatives').length).toBeGreaterThan(0)
    expect(screen.getByText('sign_slip')).toBeInTheDocument()
    expect(screen.getByText('7 total')).toBeInTheDocument()
    expect(screen.getByText(/↓ 2 this week/)).toBeInTheDocument()
    expect(screen.getByText('rushing')).toBeInTheDocument()
  })

  test('recommendations tab shows evidence-backed tips', async () => {
    getRecommendations.mockResolvedValue([
      {
        kind: 'drill',
        priority: 30,
        concept: 'derivatives',
        skill: 'procedural',
        evidence: { misses: 4, n: 9, accuracy: 0.44 },
      },
    ])
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: /tips/i }))
    expect(await screen.findByText(/derivatives/)).toBeInTheDocument()
    expect(screen.getByText(/4 misses out of 9/)).toBeInTheDocument()
  })
})

describe('ScoresPage item analysis (plan 87 C)', () => {
  test('renders difficulty, discrimination, distractor efficiency and flags', async () => {
    getItems.mockResolvedValue([
      {
        question_id: 'q1',
        activity_id: '2',
        n_attempts: 24,
        p_correct: 0.42,
        discrimination: 0.11,
        distractor_efficiency: 0.67,
        avg_time_ms: 42000,
        avg_time_ratio: 1.1,
        distractor_selection: { '1': 9 },
        flag: 'review',
        elo_outlier: false,
        stem_excerpt: 'Derivative of x^2?',
      },
      {
        question_id: 'q2',
        activity_id: '2',
        n_attempts: 24,
        p_correct: 0.8,
        discrimination: 0.55,
        distractor_efficiency: 1,
        avg_time_ms: 30000,
        avg_time_ratio: 0.9,
        distractor_selection: { '1': 3, '2': 2 },
        flag: 'elo_outlier',
        elo_outlier: true,
        stem_excerpt: 'Limit at a point?',
      },
    ])
    await renderPage('/scores?tab=diagnostics')
    expect(await screen.findByText('Item analysis')).toBeInTheDocument()
    expect(await screen.findByText('Derivative of x^2?')).toBeInTheDocument()
    expect(screen.getByText('0.11')).toBeInTheDocument()
    expect(screen.getByText('67%')).toBeInTheDocument()
    expect(screen.getByText('review')).toBeInTheDocument()
    expect(screen.getByText('Elo outlier')).toBeInTheDocument()
    const link = screen.getByText('Derivative of x^2?').closest('a')
    expect(link?.getAttribute('href')).toContain('/quiz/2')
  })

  test('exports the current scope as CSV and JSON', async () => {
    await renderPage()
    expect(screen.getByText('Export CSV').closest('a')?.getAttribute('href')).toBe(
      '/api/v1/analytics/export?format=csv'
    )
    expect(screen.getByText('Export JSON').closest('a')?.getAttribute('href')).toBe(
      '/api/v1/analytics/export?format=json'
    )
  })
})

describe('ScoresPage mistake notebook node links (plan 87 F)', () => {
  test('rows deep-link to the node that holds the question', async () => {
    listMistakes.mockResolvedValue([
      {
        id: 'm1',
        question_id: 'q1',
        activity_id: '2',
        activity_title: 'Derivatives quiz',
        course_id: '3',
        node_id: '4',
        node_title: 'Derivatives',
        stem_excerpt: 'Differentiate x^2',
        error_tags: ['sign_slip'],
        created_at: '2026-08-19T09:00:00',
      },
      {
        id: 'm2',
        question_id: 'q2',
        activity_id: '2',
        activity_title: 'Derivatives quiz',
        course_id: '3',
        node_id: null,
        node_title: null,
        stem_excerpt: 'Course-level warm-up',
        error_tags: [],
        created_at: '2026-08-19T09:00:00',
      },
    ])
    await renderPage('/scores?tab=mistakes')
    expect(await screen.findByText('Differentiate x^2')).toBeInTheDocument()
    expect(screen.getByText('Derivatives')).toBeInTheDocument()
    expect(
      screen.getByText('Differentiate x^2').closest('a')?.getAttribute('href')
    ).toContain('/courses/3/n/4')
    expect(
      screen.getByText('Course-level warm-up').closest('a')?.getAttribute('href')
    ).toContain('/courses/3')
  })
})

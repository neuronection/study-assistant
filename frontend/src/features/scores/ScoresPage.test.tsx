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

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listQuizAttempts: () => listQuizAttempts(),
    listMistakes: () => listMistakes(),
    getDiagnostics: () => getDiagnostics(),
    getRecommendations: () => getRecommendations(),
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
    listQuizAttempts.mockResolvedValue([])
    listMistakes.mockResolvedValue([])
    getDiagnostics.mockResolvedValue(DIAGNOSTICS)
    getRecommendations.mockResolvedValue([])
  })

  test('history tab lists attempts with score coloring', async () => {
    listQuizAttempts.mockResolvedValue([
      {
        id: 1,
        activity_id: 2,
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

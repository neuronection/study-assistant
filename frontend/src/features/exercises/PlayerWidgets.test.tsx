import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { Player } from './Player'

const exerciseSteps = vi.fn()
const getExercise = vi.fn()
const courseTree = vi.fn()
const startExerciseSession = vi.fn()
const submitStepAnswer = vi.fn()

const { routerState } = vi.hoisted(() => ({
  routerState: { location: { search: {} as Record<string, unknown> } },
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    exerciseSteps: (...args: unknown[]) => exerciseSteps(...(args as [number])),
    getExercise: (...args: unknown[]) => getExercise(...(args as [number])),
    courseTree: (...args: unknown[]) => courseTree(...(args as [number])),
    startExerciseSession: (...args: unknown[]) =>
      startExerciseSession(...(args as [number])),
    submitStepAnswer: (...args: unknown[]) =>
      submitStepAnswer(...(args as [number, unknown, unknown])),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ exerciseId: '1' }),
  useNavigate: () => vi.fn(),
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) => select(routerState),
  useRouter: () => ({ history: { push: () => {} } }),
  Link: ({ children }: { children: React.ReactNode }) => <a href="#">{children}</a>,
}))

vi.mock('@/components/math/MathInput', () => ({
  MathInput: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <textarea value={value} onChange={(event) => onChange(event.target.value)} />
  ),
}))

const EXERCISE = {
  id: 1,
  title: 'Squares',
  course_id: 9,
  node_id: 5,
  difficulty: 2,
  step_count: 1,
}

const TREE = [
  {
    id: 1,
    title: 'Calculus I',
    summary: null,
    objectives: [],
    order_idx: 0,
    depth: 0,
    is_root: true,
    children: [],
    materials: [],
  },
]

function renderPlayer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Player exerciseId={1} />
    </QueryClientProvider>
  )
}

describe('exercise Player widget state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routerState.location.search = {}
    exerciseSteps.mockResolvedValue([
      {
        id: 1,
        order_idx: 0,
        prompt: [
          { type: 'text', md: 'Which steps did you use?' },
          {
            type: 'widget',
            widget: 'checklist',
            id: 'w1',
            props: { prompt: 'Select all that apply', items: ['factor', 'chain rule'] },
          },
        ],
        has_expected: true,
      },
    ])
    getExercise.mockResolvedValue(EXERCISE)
    courseTree.mockResolvedValue(TREE)
    startExerciseSession.mockResolvedValue({
      id: 3,
      exercise_id: 1,
      current_step_idx: 0,
      status: 'active',
      socratic: false,
      independence_score: null,
    })
    submitStepAnswer.mockResolvedValue({
      correct: true,
      stage: 'correct',
      error_class: null,
      advanced: false,
      session: {
        id: 3,
        exercise_id: 1,
        current_step_idx: 0,
        status: 'active',
        socratic: false,
        independence_score: null,
      },
    })
  })

  test('renders the widget in the prompt and submits its state', async () => {
    renderPlayer()
    expect(await screen.findByText(/Which steps did you use/)).toBeInTheDocument()
    expect(screen.getByText('Select all that apply')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('factor'))
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '2x' } })
    fireEvent.click(screen.getByRole('button', { name: /check/i }))

    await waitFor(() =>
      expect(submitStepAnswer).toHaveBeenCalledWith(3, '2x', {
        w1: { checked: ['factor'] },
      })
    )
  })
})

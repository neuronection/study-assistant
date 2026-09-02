import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { Player } from './Player'

const exerciseSteps = vi.fn()
const getExercise = vi.fn()
const courseTree = vi.fn()
const startExerciseSession = vi.fn()
const submitStepAnswer = vi.fn()

const { routerState, pushed } = vi.hoisted(() => ({
  routerState: { location: { search: {} as Record<string, unknown> } },
  pushed: [] as string[],
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
      submitStepAnswer(...(args as [number, unknown])),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ exerciseId: '1' }),
  useNavigate: () => vi.fn(),
  useRouterState: ({ select }: { select: (state: unknown) => unknown }) => select(routerState),
  useRouter: () => ({
    history: {
      push: (href: string) => {
        pushed.push(href)
      },
    },
  }),
  Link: ({ children }: { children: React.ReactNode }) => <a href="#">{children}</a>,
}))

const EXERCISE = {
  id: 1,
  title: 'Squares',
  course_id: 9,
  node_id: 5,
  difficulty: 2,
  step_count: 2,
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
    children: [
      {
        id: 5,
        title: 'Derivatives',
        summary: null,
        objectives: [],
        order_idx: 0,
        depth: 1,
        is_root: false,
        children: [],
        materials: [],
      },
    ],
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

describe('exercise Player', () => {
  beforeEach(() => {
    exerciseSteps.mockReset()
    getExercise.mockReset()
    courseTree.mockReset()
    startExerciseSession.mockReset()
    routerState.location.search = {}
    pushed.length = 0
    exerciseSteps.mockResolvedValue([
      { id: 1, order_idx: 0, prompt: [{ type: 'text', md: 'Compute $\\frac{d}{dx} x^2$.' }], has_expected: true },
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
  })

  test('renders the shell with breadcrumb, step progress and meta', async () => {
    renderPlayer()
    expect(await screen.findByText(/Compute/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Squares' })).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Derivatives' })).toBeInTheDocument()
    expect(screen.getByText('Step 1 / 1')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(screen.getByText('1 step')).toBeInTheDocument()
    expect(screen.getByText('Difficulty: 2')).toBeInTheDocument()
    expect(screen.getByText('Guided mode')).toBeInTheDocument()
  })

  test('close returns to the encoded origin, else the placement workspace', async () => {
    routerState.location.search = { from: '/courses/9?tab=practice' }
    renderPlayer()
    await screen.findByText(/Compute/)
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(pushed).toEqual(['/courses/9?tab=practice'])
  })

  test('close falls back to the exercise node workspace', async () => {
    renderPlayer()
    await screen.findByText(/Compute/)
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(pushed).toEqual(['/courses/9/n/5?tab=practice'])
  })
})

describe('exercise Player structural kinds', () => {
  beforeEach(() => {
    exerciseSteps.mockReset()
    getExercise.mockReset()
    courseTree.mockReset()
    startExerciseSession.mockReset()
    submitStepAnswer.mockReset()
    routerState.location.search = {}
    pushed.length = 0
    exerciseSteps.mockResolvedValue([
      {
        id: 1,
        order_idx: 0,
        prompt: [{ type: 'text', md: 'Match each function to its derivative.' }],
        has_expected: true,
        kind: 'matching',
        input: {
          widget: 'matching',
          lefts: ['$x^2$', '$\\sin x$'],
          rights: [
            { index: 1, label: '$\\cos x$' },
            { index: 0, label: '$2x$' },
          ],
        },
      },
    ])
    getExercise.mockResolvedValue({ ...EXERCISE, kind: 'matching', step_count: 1 })
    courseTree.mockResolvedValue(TREE)
    startExerciseSession.mockResolvedValue({
      id: 3,
      exercise_id: 1,
      current_step_idx: 0,
      status: 'active',
      socratic: false,
      independence_score: null,
    })
  })

  test('renders the matching widget and submits the structured response', async () => {
    submitStepAnswer.mockResolvedValue({
      correct: true,
      stage: 'matching: correct',
      error_class: null,
      advanced: false,
      session: {
        id: 3,
        exercise_id: 1,
        current_step_idx: 0,
        status: 'completed',
        socratic: false,
        independence_score: 1,
      },
    })
    renderPlayer()
    expect(await screen.findByText(/Match each function/)).toBeInTheDocument()

    const submit = screen.getByRole('button', { name: /check/i }) as HTMLButtonElement
    expect(submit.disabled).toBe(true)

    const selects = screen.getAllByRole('combobox')
    fireEvent.change(selects[0], { target: { value: '0' } })
    fireEvent.change(selects[1], { target: { value: '1' } })
    expect((submit as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(submit)

    await waitFor(() => expect(submitStepAnswer).toHaveBeenCalledWith(3, [0, 1]))
    expect(await screen.findByText(/matching: correct/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /next/i }))
    expect(await screen.findByText(/Exercise completed/i)).toBeInTheDocument()
  })
})

describe('exercise Player rubric kinds', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    exerciseSteps.mockReset()
    getExercise.mockReset()
    courseTree.mockReset()
    startExerciseSession.mockReset()
    submitStepAnswer.mockReset()
    routerState.location.search = {}
    pushed.length = 0
  })

  test('error_spot renders radio lines and submits the picked index', async () => {
    exerciseSteps.mockResolvedValue([
      {
        id: 1,
        order_idx: 0,
        prompt: [{ type: 'text', md: 'One line below is flawed. Identify it.' }],
        has_expected: true,
        kind: 'error_spot',
        input: {
          widget: 'lines',
          kind: 'error_spot',
          lines: ['$d/dx (3x^2) = 6x$', '$d/dx (\\sin(2x)) = \\cos(2x)$', '$d/dx (e^x) = e^x$'],
        },
      },
    ])
    getExercise.mockResolvedValue({ ...EXERCISE, kind: 'error_spot', step_count: 1 })
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
      stage: 'error_spot: correct',
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
    renderPlayer()
    expect(await screen.findByText(/One line below is flawed/)).toBeInTheDocument()

    const radios = screen.getAllByRole('radio')
    expect(radios).toHaveLength(3)
    const submit = screen.getByRole('button', { name: /check/i }) as HTMLButtonElement
    expect(submit.disabled).toBe(true)
    fireEvent.click(radios[1])
    expect(submit.disabled).toBe(false)
    fireEvent.click(submit)
    await waitFor(() =>
      expect(submitStepAnswer).toHaveBeenCalledWith(
        3,
        JSON.stringify({ picked: [1], fix: '' }),
      ),
    )
    expect(await screen.findByText(/error_spot: correct/i)).toBeInTheDocument()
  })

  test('explain renders a textarea and submits free text', async () => {
    exerciseSteps.mockResolvedValue([
      {
        id: 1,
        order_idx: 0,
        prompt: [{ type: 'text', md: 'Explain the chain rule in your own words.' }],
        has_expected: true,
        kind: 'explain',
        input: { widget: 'essay', kind: 'explain' },
      },
    ])
    getExercise.mockResolvedValue({ ...EXERCISE, kind: 'explain', step_count: 1 })
    courseTree.mockResolvedValue(TREE)
    startExerciseSession.mockResolvedValue({
      id: 4,
      exercise_id: 1,
      current_step_idx: 0,
      status: 'active',
      socratic: false,
      independence_score: null,
    })
    submitStepAnswer.mockResolvedValue({
      correct: false,
      stage: 'explain: partial (AI-graded)',
      error_class: null,
      advanced: false,
      session: {
        id: 4,
        exercise_id: 1,
        current_step_idx: 0,
        status: 'active',
        socratic: false,
        independence_score: null,
      },
    })
    renderPlayer()
    expect(await screen.findByText(/Explain the chain rule/)).toBeInTheDocument()

    const area = screen.getByRole('textbox')
    fireEvent.change(area, { target: { value: 'outer times inner derivative' } })
    fireEvent.click(screen.getByRole('button', { name: /check/i }))
    await waitFor(() =>
      expect(submitStepAnswer).toHaveBeenCalledWith(4, 'outer times inner derivative')
    )
    expect(await screen.findByText(/AI-graded/i)).toBeInTheDocument()
  })
})

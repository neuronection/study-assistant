import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { QuizRunner } from './QuizRunner'
import { useChatStore } from '@/lib/chat-store'

const quizQuestions = vi.fn()
const getQuiz = vi.fn()
const courseTree = vi.fn()
const startQuizAttempt = vi.fn()
const submitQuizAnswer = vi.fn()
const finishQuizAttempt = vi.fn()
const requestQuizHint = vi.fn()
const askAboutQuestion = vi.fn()
const recognizeHandwriting = vi.fn()

const { routerState, pushed, navigate } = vi.hoisted(() => ({
  routerState: { location: { search: {} as Record<string, unknown> } },
  pushed: [] as string[],
  navigate: vi.fn(),
}))

vi.mock('@/components/canvas/DrawCanvas', () => ({
  DrawCanvas: ({
    onChange,
  }: {
    strokes: unknown[]
    onChange: (strokes: { points: number[][] }[]) => void
  }) => (
    <div
      data-testid="draw-canvas"
      onClick={() => onChange([{ points: [[0, 0], [1, 1]] }])}
    />
  ),
  strokesToPng: () => 'data:image/png;base64,ZmFrZQ==',
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    quizQuestions: (...args: unknown[]) => quizQuestions(...(args as [number])),
    getQuiz: (...args: unknown[]) => getQuiz(...(args as [number])),
    courseTree: (...args: unknown[]) => courseTree(...(args as [number])),
    startQuizAttempt: (...args: unknown[]) => startQuizAttempt(...(args as [number])),
    submitQuizAnswer: (...args: unknown[]) =>
      submitQuizAnswer(...(args as [number, number, unknown])),
    finishQuizAttempt: (...args: unknown[]) => finishQuizAttempt(...(args as [number])),
    requestQuizHint: (...args: unknown[]) =>
      requestQuizHint(...(args as [number, number, number])),
    askAboutQuestion: (...args: unknown[]) => askAboutQuestion(...(args as [number, number])),
    recognizeHandwriting: (png: string) => recognizeHandwriting(png),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
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

const QUESTIONS = [
  {
    id: 1,
    type: 'single',
    stem: [{ type: 'text', md: 'What is $2+2$?' }],
    options: [
      { type: 'text', md: '3' },
      { type: 'text', md: '4' },
    ],
    difficulty: 1,
    bloom: 'apply',
    skill: 'procedural',
    expected_time_sec: 30,
    flag: 'ok',
  },
  {
    id: 2,
    type: 'equation',
    stem: [{ type: 'text', md: 'Differentiate $x^2$.' }],
    options: null,
    difficulty: 2,
    bloom: 'apply',
    skill: 'procedural',
    expected_time_sec: 60,
    flag: 'ok',
  },
]

const QUIZ = (courseId: number | null = null, nodeId: number | null = null) => ({
  id: 1,
  title: 'Derivatives check',
  type: 'quiz',
  course_id: courseId,
  node_id: nodeId,
  question_count: 2,
})

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

function renderRunner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <QuizRunner activityId={1} />
    </QueryClientProvider>
  )
}

function getButton(name: RegExp): HTMLButtonElement {
  return screen.getByRole('button', { name }) as HTMLButtonElement
}

describe('QuizRunner', () => {
  beforeEach(() => {
    quizQuestions.mockReset()
    getQuiz.mockReset()
    courseTree.mockReset()
    startQuizAttempt.mockReset()
    submitQuizAnswer.mockReset()
    finishQuizAttempt.mockReset()
    requestQuizHint.mockReset()
    askAboutQuestion.mockReset()
    routerState.location.search = {}
    pushed.length = 0
    navigate.mockClear()
    getQuiz.mockResolvedValue(QUIZ())
    useChatStore.setState({ open: false })
  })

  test('answer flow: submit → verdict → next → summary', async () => {
    quizQuestions.mockResolvedValue(QUESTIONS)
    startQuizAttempt.mockResolvedValue({ id: 9, score: null })
    submitQuizAnswer.mockResolvedValueOnce({
      correct: true,
      partial_credit: 1,
      graded_by: 'deterministic',
      feedback: [],
      error_tags: [],
      explanation: [{ type: 'text', md: 'Power rule.' }],
    })
    submitQuizAnswer.mockResolvedValueOnce({
      correct: true,
      partial_credit: 1,
      graded_by: 'symPy',
      feedback: [],
      error_tags: [],
      explanation: [],
    })
    finishQuizAttempt.mockResolvedValue({ id: 9, score: 1 })

    const { container } = renderRunner()
    expect(await screen.findByText(/What is/)).toBeInTheDocument()
    await waitFor(() => expect(startQuizAttempt).toHaveBeenCalled())

    fireEvent.click(getButton(/B/))
    fireEvent.click(getButton(/submit/i))
    expect(await screen.findByText('Correct')).toBeInTheDocument()
    expect(screen.getByText('Power rule.')).toBeInTheDocument()

    fireEvent.click(getButton(/next/i))
    const mathField = (await waitFor(() => {
      const element = container.querySelector('math-field')
      expect(element).not.toBeNull()
      return element!
    })) as HTMLElement & { value: string }
    mathField.value = '2x'
    mathField.dispatchEvent(new Event('input', { bubbles: true }))
    const equationSubmit = getButton(/submit/i)
    await waitFor(() => expect(equationSubmit.disabled).toBe(false))
    fireEvent.click(equationSubmit)
    await screen.findByText('verified with SymPy')

    fireEvent.click(getButton(/finish/i))
    expect(await screen.findByText('100%')).toBeInTheDocument()
    expect(finishQuizAttempt).toHaveBeenCalledWith(9)
  })

  test('wrong answer shows incorrect verdict', async () => {
    quizQuestions.mockResolvedValue([QUESTIONS[0]])
    startQuizAttempt.mockResolvedValue({ id: 10, score: null })
    submitQuizAnswer.mockResolvedValue({
      correct: false,
      partial_credit: 0,
      graded_by: 'deterministic',
      feedback: [],
      error_tags: [],
      explanation: [{ type: 'text', md: 'It is 4.' }],
    })
    renderRunner()
    await waitFor(() => expect(startQuizAttempt).toHaveBeenCalled())
    const optionA = (await screen.findByText('A')).closest('button')
    fireEvent.click(optionA!)
    const submitButton = getButton(/submit/i)
    await waitFor(() => expect(submitButton.disabled).toBe(false))
    fireEvent.click(submitButton)
    expect(await screen.findByText('Incorrect')).toBeInTheDocument()
  })

  test('shuffle remaps displayed options to stored indices', async () => {
    window.localStorage.setItem('ca-quiz-shuffle', '1')
    quizQuestions.mockResolvedValue([QUESTIONS[0]])
    startQuizAttempt.mockResolvedValue({ id: 12, score: null })
    submitQuizAnswer.mockResolvedValue({
      correct: true,
      partial_credit: 1,
      graded_by: 'deterministic',
      feedback: [],
      error_tags: [],
      explanation: [{ type: 'text', md: 'Power rule.' }],
    })
    renderRunner()
    await waitFor(() => expect(startQuizAttempt).toHaveBeenCalled())
    const toggle = screen.getByRole('button', { name: /shuffle/i })
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
    const correctOption = (await screen.findByText('4')).closest('button')
    fireEvent.click(correctOption!)
    const submitButton = getButton(/submit/i)
    await waitFor(() => expect(submitButton.disabled).toBe(false))
    fireEvent.click(submitButton)
    await screen.findByText('Correct')
    const [, questionId, response] = submitQuizAnswer.mock.calls[0] as [
      number,
      number,
      unknown,
    ]
    expect(questionId).toBe(1)
    expect(QUESTIONS[0].options![response as number].md).toBe('4')
  })

  test('practice mode offers hint ladder and ask-in-chat', async () => {
    quizQuestions.mockResolvedValue([QUESTIONS[0]])
    startQuizAttempt.mockResolvedValue({ id: 11, mode: 'practice', score: null })
    requestQuizHint.mockResolvedValue({
      level: 1,
      markdown: 'Which arithmetic combines the terms?',
      violations: null,
    })
    askAboutQuestion.mockResolvedValue({ chat_session_id: 42, public_id: 'uuid-42' })
    renderRunner()
    await waitFor(() => expect(startQuizAttempt).toHaveBeenCalled())

    const hintButton = await screen.findByRole('button', { name: /hint \(level 1\)/i })
    fireEvent.click(hintButton)
    expect(await screen.findByText(/Which arithmetic combines/)).toBeInTheDocument()
    expect(requestQuizHint).toHaveBeenCalledWith(11, 1, 1, null)

    fireEvent.click(getButton(/ask about this question/i))
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/chat/$chatId',
        params: { chatId: 'uuid-42' },
      })
    )
  })

  test('exam mode hides help controls', async () => {
    quizQuestions.mockResolvedValue([QUESTIONS[0]])
    startQuizAttempt.mockResolvedValue({ id: 12, mode: 'exam', score: null })
    renderRunner()
    await waitFor(() => expect(startQuizAttempt).toHaveBeenCalled())
    await screen.findByText(/What is/)
    expect(screen.queryByRole('button', { name: /hint/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /ask about this question/i })).not.toBeInTheDocument()
  })

  test('handwriting: draw → recognize → confirm candidate → graded answer', async () => {
    quizQuestions.mockResolvedValue([QUESTIONS[1]])
    startQuizAttempt.mockResolvedValue({ id: 13, mode: 'practice', score: null })
    recognizeHandwriting.mockResolvedValue({
      markdown: 'The derivative is $2x$.',
      latex_candidates: ['2x'],
    })
    submitQuizAnswer.mockResolvedValue({
      correct: true,
      partial_credit: 1,
      graded_by: 'symPy',
      feedback: [],
      error_tags: [],
      explanation: [],
    })
    renderRunner()
    await waitFor(() => expect(startQuizAttempt).toHaveBeenCalled())
    await screen.findByText(/Differentiate/)

    fireEvent.click(screen.getByRole('button', { name: /write instead/i }))
    fireEvent.click(screen.getByTestId('draw-canvas'))
    fireEvent.click(screen.getByRole('button', { name: /recognize/i }))

    const chip = await screen.findByRole('button', { name: /2x/i })
    expect(chip).toBeInTheDocument()
    fireEvent.click(chip)

    const submitButton = getButton(/submit/i)
    await waitFor(() => expect(submitButton.disabled).toBe(false))
    fireEvent.click(submitButton)

    await waitFor(() =>
      expect(submitQuizAnswer).toHaveBeenCalledWith(
        13,
        2,
        '2x',
        expect.any(Number),
        'write',
        [{ points: [[0, 0], [1, 1]] }]
      )
    )
  })

  test('close returns to the encoded origin location', async () => {
    quizQuestions.mockResolvedValue([QUESTIONS[0]])
    startQuizAttempt.mockResolvedValue({ id: 14, mode: 'practice', score: null })
    routerState.location.search = { from: '/courses/3?tab=practice' }
    renderRunner()
    await screen.findByText(/What is/)
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(pushed).toEqual(['/courses/3?tab=practice'])
  })

  test('close falls back to the quiz placement workspace when no origin is known', async () => {
    quizQuestions.mockResolvedValue([QUESTIONS[0]])
    startQuizAttempt.mockResolvedValue({ id: 15, mode: 'practice', score: null })
    getQuiz.mockResolvedValue(QUIZ(9, 5))
    courseTree.mockResolvedValue(TREE)
    renderRunner()
    await screen.findByText(/What is/)
    const nodeLink = await screen.findByRole('link', { name: 'Derivatives' })
    expect(nodeLink).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(pushed).toEqual(['/courses/9/n/5?tab=practice'])
  })

  test('meta strip shows question count and mode behind the details toggle', async () => {
    quizQuestions.mockResolvedValue([QUESTIONS[0]])
    startQuizAttempt.mockResolvedValue({ id: 16, mode: 'exam', score: null })
    renderRunner()
    await screen.findByText(/What is/)
    expect(screen.getByRole('heading', { name: 'Derivatives check' })).toBeInTheDocument()
    expect(screen.queryByText('1 question')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(screen.getByText('1 question')).toBeInTheDocument()
    expect(screen.getByText('Exam')).toBeInTheDocument()
  })
})

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import i18next from 'i18next'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { toolCardProps } from './registry'
import { ChatToolCard } from '@/components/ui/chat-tool-card'
import { useChatStore } from '@/lib/chat-store'

const answerQuizQuestion = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    answerQuizQuestion: (session: number, answer: string | number) =>
      answerQuizQuestion(session, answer),
  }
})

const QUIZ_TOOL = {
  name: 'QUIZ',
  argument: 'limit question',
  phase: 'read',
  status: 'done',
  result: 'question presented — awaiting the student\'s answer',
  quiz: {
    question: 'Compute the limit of 1/x as x approaches infinity.',
    choices: ['0', '1'],
    answered: false,
    verdict: null,
    verdict_detail: null,
    student_answer: null,
    expected_display: null,
  },
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ChatToolCard {...toolCardProps(QUIZ_TOOL, i18next.t.bind(i18next))} />
    </QueryClientProvider>
  )
}

describe('QuizCardView through the library tool card', () => {
  beforeEach(() => {
    answerQuizQuestion.mockReset()
    useChatStore.setState({ session: { id: 9, publicId: 'p9' } })
  })

  test('quiz cards render expanded with the question and grade the pick', async () => {
    answerQuizQuestion.mockResolvedValue({
      correct: true,
      verdict_detail: 'exact choice match',
      expected_display: '0',
      user_message_id: 11,
      job_id: 3,
    })
    renderCard()

    expect(
      await screen.findByText(/Compute the limit of 1\/x/)
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /B\s*1/ }))

    await waitFor(() => expect(answerQuizQuestion).toHaveBeenCalledWith(9, 1))
    expect(await screen.findByText('Correct!')).toBeInTheDocument()
  })

  test('shows the verdict and expected answer after an incorrect pick', async () => {
    answerQuizQuestion.mockResolvedValue({
      correct: false,
      verdict_detail: 'exact choice match',
      expected_display: '0',
      user_message_id: 11,
      job_id: 3,
    })
    renderCard()

    fireEvent.click(await screen.findByRole('button', { name: /A\s*0/ }))
    expect(await screen.findByText(/Not quite/)).toBeInTheDocument()
    expect(screen.getByText(/Expected: 0/)).toBeInTheDocument()
  })
})

import { ArrowLeft, Printer } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { PrintOverlay, useAutoPrint } from '@/components/print/PrintDoc'
import { Button } from '@/components/ui/button'
import { getQuiz, quizQuestions, quizAnswerKey, type QuizQuestion } from '@/lib/api'

const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F'] as const

function stemText(question: QuizQuestion): string {
  return (question.stem ?? [])
    .map((block) => ('md' in block && typeof block.md === 'string' ? block.md : ''))
    .join('\n')
    .trim()
}

export function QuizPrintPaper({
  activityId,
  mode,
  autoPrint = true,
}: {
  activityId: number
  mode: 'paper' | 'key'
  autoPrint?: boolean
}) {
  const { t } = useTranslation()
  const activity = useQuery({
    queryKey: ['quiz-activity', activityId],
    queryFn: () => getQuiz(activityId),
  })
  const questions = useQuery({
    queryKey: ['quiz-questions', activityId],
    queryFn: () => quizQuestions(activityId),
  })
  const key = useQuery({
    queryKey: ['quiz-answer-key', activityId],
    queryFn: () => quizAnswerKey(activityId),
    enabled: mode === 'key',
  })
  useAutoPrint(autoPrint)

  const title = activity.data?.title ?? t('quiz.untitled')
  const contextLine = t(mode === 'paper' ? 'print.quizPaper' : 'print.quizKey', {
    count: questions.data?.length ?? 0,
  })

  return (
    <PrintOverlay title={title} contextLine={contextLine} autoPrint={false}
      toolbar={
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => window.history.back()}>
            <ArrowLeft aria-hidden />
            {t('common.back')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer aria-hidden />
            {t('library.printDoc')}
          </Button>
        </div>
      }
    >
      {mode === 'paper' ? (
        <ol>
          {(questions.data ?? []).map((question) => (
            <li key={question.id} className="print-question">
              <div>{stemText(question)}</div>
              {question.options != null && question.options.length > 0 ? (
                <ul className="list-none pl-0">
                  {question.options.map((option, optionIndex) => (
                    <li key={optionIndex}>
                      {LETTERS[optionIndex] ?? optionIndex + 1}.{' '}
                      {'md' in option && typeof option.md === 'string' ? option.md : ''}
                    </li>
                  ))}
                </ul>
              ) : null}
              <div className="print-answer-line" aria-hidden />
            </li>
          ))}
        </ol>
      ) : (
        <ol>
          {(questions.data ?? []).map((question) => {
            const entry = (key.data ?? []).find((item) => item.question_id === question.id)
            return (
              <li key={question.id} className="print-question">
                <strong>{entry?.key ?? '…'}</strong>
              </li>
            )
          })}
        </ol>
      )}
    </PrintOverlay>
  )
}

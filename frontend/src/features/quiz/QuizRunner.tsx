import { useMutation, useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight, Check, ClipboardList, HelpCircle, Loader2, MessageSquare, PenTool, Shuffle, Sparkles, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useRouterState } from '@tanstack/react-router'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import { DrawCanvas, strokesToPng, type Stroke } from '@/components/canvas/DrawCanvas'
import { FocusShell, useFocusContext } from '@/components/layout/FocusShell'
import { MathInput } from '@/components/math/MathInput'
import {
  NumberlineAnswer,
  numberlinePayloadComplete,
  type NumberlinePayload,
} from '@/components/answers/NumberlineAnswer'
import {
  TableFillAnswer,
  isTableFillInput,
  tableGridComplete,
} from '@/components/answers/TableFillAnswer'
import type { Block } from '@/components/blocks/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  askAboutQuestion,
  finishQuizAttempt,
  getQuiz,
  quizQuestions,
  recognizeHandwriting,
  requestQuizHint,
  startQuizAttempt,
  submitQuizAnswer,
  type HintResult,
  type QuizAttempt,
  type QuizFeedback,
  type QuizQuestion,
  type RecognitionResult,
} from '@/lib/api'
import { practiceFallback, useOriginBack } from '@/lib/origin'

import { cn } from '@/lib/utils'
import { storageKeys } from '@/lib/constants'

const LETTERS = ['A', 'B', 'C', 'D', 'E', 'F']

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000)
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

export function QuizRunner({ activityId }: { activityId: number }) {
  const { t } = useTranslation()
  const from = useRouterState({ select: (state) => (state.location.search as { from?: string }).from })
  const questions = useQuery({
    queryKey: ['quiz-questions', activityId],
    queryFn: () => quizQuestions(activityId),
  })
  const activity = useQuery({
    queryKey: ['quiz-activity', activityId],
    queryFn: () => getQuiz(activityId),
  })
  const context = useFocusContext(activity.data?.course_id, activity.data?.node_id)
  const fallbackHref = practiceFallback(activity.data?.course_id, activity.data?.node_id)
  const goBack = useOriginBack(from, fallbackHref)
  const openWorkspace = useOriginBack(undefined, fallbackHref)
  const [attempt, setAttempt] = useState<QuizAttempt | null>(null)
  const [index, setIndex] = useState(0)
  const [choice, setChoice] = useState<number | number[] | boolean | null>(null)
  const [typed, setTyped] = useState('')
  const [numberline, setNumberline] = useState<NumberlinePayload | null>(null)
  const [tableGrid, setTableGrid] = useState<string[][] | null>(null)
  const [feedback, setFeedback] = useState<QuizFeedback | null>(null)
  const [hints, setHints] = useState<HintResult[]>([])
  const [score, setScore] = useState<number | null>(null)
  const [startedAt, setStartedAt] = useState<number>(Date.now())
  const [elapsed, setElapsed] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [writeMode, setWriteMode] = useState(false)
  const [strokes, setStrokes] = useState<Stroke[]>([])
  const [recognition, setRecognition] = useState<RecognitionResult | null>(null)
  const [usedWrite, setUsedWrite] = useState(false)
  const navigate = useNavigate()
  const [shuffleOn, setShuffleOn] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(storageKeys.quizShuffle) === '1'
    } catch {
      return false
    }
  })
  useEffect(() => {
    try {
      window.localStorage.setItem(storageKeys.quizShuffle, shuffleOn ? '1' : '0')
    } catch {
      // preference persistence is best-effort only
    }
  }, [shuffleOn])
  const [shuffleNonce, setShuffleNonce] = useState(0)

  const questionsForAttempt = useMemo(() => {
    const list = questions.data ?? []
    if (!shuffleOn || list.length === 0) {
      return { order: list, optionMaps: new Map<number, number[]>() }
    }
    const seeded = (seed: number) => {
      let state = seed >>> 0
      return () => {
        state = (1664525 * state + 1013904223) >>> 0
        return state / 4294967296
      }
    }
    const rng = seeded(shuffleNonce + list.length)
    const order = [...list].sort(() => rng() - 0.5)
    const optionMaps = new Map<number, number[]>()
    for (const question of order) {
      if (question.options && (question.type === 'single' || question.type === 'multi')) {
        const indexed = question.options.map((_, index) => index)
        indexed.sort(() => rng() - 0.5)
        optionMaps.set(question.id, indexed)
      }
    }
    return { order, optionMaps }
  }, [questions.data, shuffleOn, shuffleNonce])

  useEffect(() => {
    if (score === null && !feedback) {
      const timer = window.setInterval(() => setElapsed(Date.now() - startedAt), 1000)
      return () => window.clearInterval(timer)
    }
  }, [score, feedback, startedAt])

  const currentResponse = (): unknown => {
    const current = questionsForAttempt.order[index]
    if (!current) {
      return null
    }
    if (current.type === 'numberline') {
      return numberline
    }
    if (current.type === 'table_fill') {
      return tableGrid
    }
    if (current.type === 'single' || current.type === 'truefalse' || current.type === 'multi') {
      if (current.type === 'multi' && Array.isArray(choice)) {
        const optionMap = questionsForAttempt.optionMaps.get(current.id)
        return optionMap ? choice.map((entry) => optionMap[entry]) : choice
      }
      const optionMap = questionsForAttempt.optionMaps.get(current.id)
      if (typeof choice === 'number' && optionMap) {
        return optionMap[choice]
      }
      return choice
    }
    return typed
  }

  const start = useMutation({
    mutationFn: () => startQuizAttempt(activityId),
    onSuccess: (started) => {
      setAttempt(started)
      setStartedAt(Date.now())
    },
  })

  useEffect(() => {
    if (questions.data && questions.data.length > 0 && attempt === null && !start.isPending) {
      start.mutate()
    }
  }, [questions.data, attempt, start])

  const submit = useMutation({
    mutationFn: (response: unknown) =>
      submitQuizAnswer(
        attempt!.id,
        questionsForAttempt.order[index].id,
        response,
        Date.now() - startedAt,
        usedWrite ? 'write' : undefined,
        usedWrite ? strokes : undefined
      ),
    onSuccess: (result) => setFeedback(result),
    onError: (err: Error) => setError(err.message),
  })

  const recognize = useMutation({
    mutationFn: () => {
      const dataUrl = strokesToPng(strokes)
      if (!dataUrl) {
        throw new Error(t('notes.canvasUnavailable'))
      }
      return recognizeHandwriting(dataUrl.split(',')[1] ?? '')
    },
    onSuccess: (result) => {
      setError(null)
      setRecognition(result)
      const best = result.latex_candidates[result.latex_candidates.length - 1]
      if (best) {
        setTyped(best)
        setUsedWrite(true)
      }
    },
    onError: (err: Error) => setError(err.message),
  })

  const finish = useMutation({
    mutationFn: () => finishQuizAttempt(attempt!.id),
    onSuccess: (finished) => setScore(finished.score ?? 0),
  })

  const hint = useMutation({
    mutationFn: (level: number) =>
      requestQuizHint(attempt!.id, questionsForAttempt.order[index].id, level, currentResponse()),
    onSuccess: (result) => setHints((current) => [...current, result]),
    onError: (err: Error) => setError(err.message),
  })

  const ask = useMutation({
    mutationFn: () => askAboutQuestion(attempt!.id, questionsForAttempt.order[index].id),
    onSuccess: (result) =>
      void navigate({ to: '/chat/$chatId', params: { chatId: result.public_id } }),
    onError: (err: Error) => setError(err.message),
  })

  if (questions.isLoading) {
    return <Loader2 className="animate-spin" aria-label={t('library.loading')} />
  }
  const list = questionsForAttempt.order

  if (score !== null) {
    const percent = Math.round(score * 100)
    return (
      <FocusShell title={activity.data?.title ?? t('quiz.summaryTitle')} context={context} onClose={goBack}>
        <Card>
          <CardHeader>
            <CardTitle className="text-center text-base">{t('quiz.summaryTitle')}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-center gap-4">
            <div className="relative flex size-36 items-center justify-center rounded-full border-8"
              style={{ borderColor: percent >= 70 ? 'var(--success)' : percent >= 40 ? 'var(--warning)' : 'var(--danger)' }}
            >
              <span className="text-3xl font-bold">{percent}%</span>
            </div>
            <p className="text-muted-foreground text-sm">
              {t('quiz.summaryScore', { score: percent })}
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="outline" size="sm" onClick={goBack}>
                {t('focus.back')}
              </Button>
              <Button size="sm" onClick={() => window.location.reload()}>
                <Sparkles aria-hidden />
                {t('quiz.trySimilar')}
              </Button>
            </div>
            <button
              type="button"
              className="text-primary text-xs hover:underline"
              onClick={openWorkspace}
            >
              {t('focus.openInWorkspace')}
            </button>
          </CardContent>
        </Card>
      </FocusShell>
    )
  }

  if (list.length === 0) {
    return (
      <p className="text-muted-foreground p-8 text-center text-sm">{t('quiz.empty')}</p>
    )
  }

  const question: QuizQuestion = list[index]
  const isLast = index === list.length - 1
  const usedLevels = hints.map((entry) => entry.level)
  const highestHint = usedLevels.length > 0 ? Math.max(...usedLevels) : 0
  const nextHintLevel = feedback === null ? Math.min(highestHint + 1, 4) : 5

  const canSubmit =
    attempt !== null &&
    !submit.isPending &&
    ((question.type === 'multi' && Array.isArray(choice) && choice.length > 0) ||
      ((question.type === 'single' || question.type === 'truefalse') && choice !== null) ||
      (question.type === 'numberline' && numberlinePayloadComplete(numberline)) ||
      (question.type === 'table_fill' &&
        isTableFillInput(question.input) &&
        tableGridComplete(tableGrid, question.input)) ||
      ((question.type === 'text' || question.type === 'numeric' || question.type === 'equation') &&
        typed.trim().length > 0))

  const toggleMulti = (originalIndex: number) => {
    setChoice((current) => {
      const selected = Array.isArray(current) ? [...current] : []
      const position = selected.indexOf(originalIndex)
      if (position >= 0) {
        selected.splice(position, 1)
      } else {
        selected.push(originalIndex)
      }
      return selected
    })
  }

  return (
    <FocusShell
      title={activity.data?.title ?? t('quiz.summaryTitle')}
      context={context}
      onClose={goBack}
      meta={
        <>
          <span>{t('quiz.metaQuestions', { count: list.length })}</span>
          {attempt ? (
            <span>
              {attempt.mode === 'exam' ? t('quiz.modeExam') : t('quiz.modePractice')}
            </span>
          ) : null}
          <span>
            {t('quiz.elapsed')}: {formatElapsed(elapsed)}
          </span>
        </>
      }
    >
      <div className="mb-6 space-y-2">
        <div className="text-muted-foreground flex items-center justify-between text-xs">
          <span>{t('quiz.progress', { current: index + 1, total: list.length })}</span>
          <button
            type="button"
            aria-pressed={shuffleOn}
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-colors',
              shuffleOn
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border text-muted-foreground hover:text-foreground'
            )}
            title={t('quiz.shuffleHint')}
            onClick={() => {
              setShuffleOn((value) => !value)
              setShuffleNonce((value) => value + 1)
            }}
          >
            <Shuffle className="size-3" aria-hidden />
            {t('quiz.shuffleLabel')}
          </button>
        </div>
        <div className="bg-border h-1.5 overflow-hidden rounded-full">
          <div
            className="bg-primary h-full transition-all"
            style={{ width: `${((index + (feedback ? 1 : 0)) / list.length) * 100}%` }}
          />
        </div>
        <div className="flex flex-wrap gap-1.5" aria-hidden>
          {list.map((_, dotIndex) => (
            <span
              key={dotIndex}
              className={cn(
                'h-1.5 min-w-2 flex-1 rounded-full transition-colors',
                dotIndex < index
                  ? 'bg-primary'
                  : dotIndex === index
                    ? feedback === null
                      ? 'bg-primary/40'
                      : feedback.correct
                        ? 'bg-primary'
                        : 'bg-danger'
                    : 'bg-border'
              )}
            />
          ))}
        </div>
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={question.id}
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -24 }}
          transition={{ duration: 0.18 }}
        >
          <Card>
            <CardContent className="space-y-4 p-6">
              <BlockRenderer blocks={question.stem as Block[]} />

              {question.options && (question.type === 'single' || question.type === 'multi') ? (
                <div className="flex flex-col gap-2">
                  {(question.options ?? []).map((option, displayIndex) => {
                    const optionMap = questionsForAttempt.optionMaps.get(question.id)
                    const originalIndex = optionMap
                      ? optionMap[displayIndex]
                      : displayIndex
                    const selected =
                      question.type === 'multi'
                        ? Array.isArray(choice) && choice.includes(originalIndex)
                        : choice === originalIndex
                    return (
                      <button
                        key={originalIndex}
                        type="button"
                        disabled={feedback !== null}
                        onClick={() =>
                          question.type === 'multi'
                            ? toggleMulti(originalIndex)
                            : setChoice(originalIndex)
                        }
                        className={cn(
                          'flex items-start gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors',
                          selected
                            ? 'border-primary bg-primary/10'
                            : 'border-border hover:bg-subtle'
                        )}
                      >
                        <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-medium"
                          style={{ borderColor: selected ? 'var(--primary)' : undefined }}
                        >
                          {LETTERS[displayIndex]}
                        </span>
                        <BlockRenderer blocks={[option] as Block[]} />
                      </button>
                    )
                  })}
                </div>
              ) : null}

              {question.type === 'truefalse' ? (
                <div className="flex gap-2">
                  {[true, false].map((value) => (
                    <button
                      key={String(value)}
                      type="button"
                      disabled={feedback !== null}
                      onClick={() => setChoice(value)}
                      className={cn(
                        'flex-1 rounded-lg border px-3 py-2.5 text-sm transition-colors',
                        choice === value
                          ? 'border-primary bg-primary/10 font-medium'
                          : 'border-border hover:bg-subtle'
                      )}
                    >
                      {value ? t('quiz.true') : t('quiz.false')}
                    </button>
                  ))}
                </div>
              ) : null}

              {question.type === 'numberline' && question.input?.widget === 'numberline' ? (
                <NumberlineAnswer
                  min={question.input.min ?? 0}
                  max={question.input.max ?? 10}
                  value={numberline}
                  onChange={setNumberline}
                  disabled={feedback !== null}
                />
              ) : null}

              {question.type === 'table_fill' && isTableFillInput(question.input) ? (
                <TableFillAnswer
                  input={question.input}
                  value={tableGrid}
                  onChange={setTableGrid}
                  disabled={feedback !== null}
                />
              ) : null}

              {question.type === 'equation' ? (
                <div
                  className={cn(
                    'border-border rounded-md border p-2',
                    feedback !== null && 'pointer-events-none opacity-70'
                  )}
                >
                  <MathInput value={typed} onChange={setTyped} />
                </div>
              ) : null}
              {['text', 'numeric'].includes(question.type) ? (
                <input
                  className="bg-surface border-border w-full rounded-md border px-3 py-2 text-sm"
                  placeholder={
                    question.type === 'numeric'
                      ? t('quiz.numericPlaceholder')
                      : t('quiz.textPlaceholder')
                  }
                  disabled={feedback !== null}
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && canSubmit) {
                      submit.mutate(currentResponse())
                    }
                  }}
                />
              ) : null}

              {['text', 'numeric', 'equation'].includes(question.type) && feedback === null ? (
                <div className="space-y-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setWriteMode((value) => !value)}
                  >
                    <PenTool aria-hidden />
                    {writeMode ? t('quiz.hideWriteMode') : t('quiz.writeMode')}
                  </Button>
                  {writeMode ? (
                    <div className="border-border space-y-2 rounded-md border p-3">
                      <DrawCanvas strokes={strokes} onChange={setStrokes} />
                      <div className="flex justify-end">
                        <Button
                          size="sm"
                          disabled={strokes.length === 0 || recognize.isPending}
                          onClick={() => recognize.mutate()}
                        >
                          {recognize.isPending ? (
                            <Loader2 className="animate-spin" aria-hidden />
                          ) : null}
                          {t('quiz.recognize')}
                        </Button>
                      </div>
                      {recognition ? (
                        <div className="bg-subtle rounded-md p-2">
                          <p className="text-muted-foreground mb-1 text-[11px]">
                            {t('quiz.interpretedAs')}
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {recognition.latex_candidates.length > 0 ? (
                              recognition.latex_candidates
                                .slice()
                                .reverse()
                                .map((candidate) => (
                                  <button
                                    key={candidate}
                                    type="button"
                                    className={cn(
                                      'rounded-full border px-2 py-0.5 text-xs',
                                      typed === candidate
                                        ? 'border-primary bg-primary/10'
                                        : 'border-border'
                                    )}
                                    onClick={() => {
                                      setTyped(candidate)
                                      setUsedWrite(true)
                                    }}
                                  >
                                    <BlockRenderer
                                      blocks={[{ type: 'text', md: `$${candidate}$` }] as Block[]}
                                    />
                                  </button>
                                ))
                            ) : (
                              <span className="text-muted-foreground text-xs">
                                {t('quiz.noMathFound')}
                              </span>
                            )}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {error ? <p className="text-danger text-xs">{error}</p> : null}

              {hints.map((hintResult, hintIndex) => (
                <div
                  key={hintIndex}
                  className="border-primary/40 bg-primary/5 rounded-lg border p-3"
                >
                  <p className="text-muted-foreground mb-1 text-[11px] font-medium">
                    {t('exercises.hintLevel', { level: hintResult.level })}
                  </p>
                  <div className="text-sm">
                    <BlockRenderer
                      blocks={[{ type: 'text', md: hintResult.markdown }] as Block[]}
                    />
                  </div>
                </div>
              ))}

              {feedback ? (
                <div
                  className={cn(
                    'rounded-lg border p-3',
                    feedback.correct
                      ? 'border-success/40 bg-success/10'
                      : 'border-danger/40 bg-danger/10'
                  )}
                >
                  <p className="mb-2 flex items-center gap-2 text-sm font-medium">
                    {feedback.correct ? (
                      <>
                        <Check className="text-success size-4" aria-hidden />
                        {t('quiz.correct')}
                      </>
                    ) : (
                      <>
                        <X className="text-danger size-4" aria-hidden />
                        {feedback.partial_credit > 0
                          ? t('quiz.partiallyCorrect', {
                              percent: Math.round(feedback.partial_credit * 100),
                            })
                          : t('quiz.incorrect')}
                      </>
                    )}
                    {feedback.graded_by === 'symPy' ? (
                      <span className="text-muted-foreground ml-auto text-[11px]">
                        {t('quiz.verifiedBySymPy')}
                      </span>
                    ) : null}
                  </p>
                  <div className="text-sm">
                    <BlockRenderer blocks={feedback.explanation as Block[]} />
                  </div>
                </div>
              ) : null}

              {attempt?.mode === 'practice' ? (
                <div className="flex items-center gap-2">
                  {(feedback === null ? hints.length < 4 : !usedLevels.includes(5)) ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={hint.isPending}
                      onClick={() => hint.mutate(nextHintLevel)}
                    >
                      {hint.isPending ? (
                        <Loader2 className="animate-spin" aria-hidden />
                      ) : (
                        <HelpCircle aria-hidden />
                      )}
                      {feedback === null
                        ? t('exercises.requestHint', { level: nextHintLevel })
                        : t('quiz.showFullSolution')}
                    </Button>
                  ) : null}
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={ask.isPending}
                    onClick={() => ask.mutate()}
                  >
                    {ask.isPending ? (
                      <Loader2 className="animate-spin" aria-hidden />
                    ) : (
                      <MessageSquare aria-hidden />
                    )}
                    {t('quiz.askAboutQuestion')}
                  </Button>
                </div>
              ) : null}

              <div className="flex justify-end">
                {feedback === null ? (
                  <Button disabled={!canSubmit} onClick={() => submit.mutate(currentResponse())}>
                    {submit.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                    {t('quiz.submit')}
                  </Button>
                ) : isLast ? (
                  <Button onClick={() => finish.mutate()} disabled={finish.isPending}>
                    {finish.isPending ? (
                      <Loader2 className="animate-spin" aria-hidden />
                    ) : (
                      <ClipboardList aria-hidden />
                    )}
                    {t('quiz.finish')}
                  </Button>
                ) : (
                  <Button
                    onClick={() => {
                      setIndex(index + 1)
                      setChoice(null)
                      setTyped('')
                      setNumberline(null)
                      setTableGrid(null)
                      setFeedback(null)
                      setHints([])
                      setStartedAt(Date.now())
                      setWriteMode(false)
                      setStrokes([])
                      setRecognition(null)
                      setUsedWrite(false)
                    }}
                  >
                    {t('quiz.next')}
                    <ArrowRight aria-hidden />
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </AnimatePresence>
    </FocusShell>
  )
}

import { useMutation, useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowRight, Check, HelpCircle, Loader2, MessageSquare, StickyNote, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useRouterState } from '@tanstack/react-router'

import { BlockRenderer } from '@/components/blocks/BlockRenderer'
import {
  ExerciseStructuralInput,
  isStructuralInput,
  structuralResponseComplete,
  type StructuralResponse,
} from '@/components/exercise-inputs/ExerciseInput'
import { RubricStepInput } from '@/components/exercise-inputs/RubricInputs'
import { FocusShell, useFocusContext } from '@/components/layout/FocusShell'
import { MathInput } from '@/components/math/MathInput'
import type { Block } from '@/components/blocks/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  askAboutExerciseSession,
  exerciseSteps,
  getExercise,
  requestHint,
  saveSessionSummaryNote,
  startExerciseSession,
  submitStepAnswer,
  type ExerciseSessionInfo,
  type HintResult,
  type StepCheck,
} from '@/lib/api'
import { practiceFallback, useOriginBack } from '@/lib/origin'

import { cn } from '@/lib/utils'

export function Player({ exerciseId }: { exerciseId: number }) {
  const { t } = useTranslation()
  const from = useRouterState({ select: (state) => (state.location.search as { from?: string }).from })
  const steps = useQuery({
    queryKey: ['exercise-steps', exerciseId],
    queryFn: () => exerciseSteps(exerciseId),
  })
  const exercise = useQuery({
    queryKey: ['exercise-info', exerciseId],
    queryFn: () => getExercise(exerciseId),
  })
  const context = useFocusContext(exercise.data?.course_id, exercise.data?.node_id)
  const fallbackHref = practiceFallback(exercise.data?.course_id, exercise.data?.node_id)
  const goBack = useOriginBack(from, fallbackHref)
  const navigate = useNavigate()
  const [session, setSession] = useState<ExerciseSessionInfo | null>(null)
  const [answer, setAnswer] = useState('')
  const [structural, setStructural] = useState<StructuralResponse | null>(null)
  const [widgetState, setWidgetState] = useState<Record<string, unknown>>({})
  const [check, setCheck] = useState<StepCheck | null>(null)
  const [hints, setHints] = useState<HintResult[]>([])
  const [error, setError] = useState<string | null>(null)
  const [summaryNoteId, setSummaryNoteId] = useState<number | null>(null)

  const summary = useMutation({
    mutationFn: () => saveSessionSummaryNote(session!.id),
    onSuccess: (result) => setSummaryNoteId(result.note_id),
  })

  const start = useMutation({
    mutationFn: () => startExerciseSession(exerciseId),
    onSuccess: setSession,
  })

  const submit = useMutation({
    mutationFn: () => {
      const step = list[Math.min(session?.current_step_idx ?? 0, list.length - 1)]
      const payload = isStructuralInput(step.input) && structural !== null
        ? structural
        : answer
      const state = Object.keys(widgetState).length > 0 ? widgetState : undefined
      return state !== undefined
        ? submitStepAnswer(session!.id, payload, state)
        : submitStepAnswer(session!.id, payload)
    },
    onSuccess: (result) => {
      setError(null)
      setCheck(result)
    },
    onError: (err: Error) => setError(err.message),
  })

  const hint = useMutation({
    mutationFn: (level: number) => requestHint(session!.id, level, answer || null),
    onSuccess: (result) => setHints((current) => [...current, result]),
    onError: (err: Error) => setError(err.message),
  })

  const ask = useMutation({
    mutationFn: () => {
      const pending = answer.trim() || (structural !== null ? JSON.stringify(structural) : '')
      return askAboutExerciseSession(session!.id, pending || null)
    },
    onSuccess: (result) =>
      void navigate({ to: '/chat/$chatId', params: { chatId: result.public_id } }),
    onError: (err: Error) => setError(err.message),
  })

  if (steps.isLoading) {
    return <Loader2 className="animate-spin" aria-label={t('library.loading')} />
  }
  if (!session && !start.isPending) {
    start.mutate()
  }
  const list = steps.data ?? []

  if (session?.status === 'completed') {
    const score = session.independence_score ?? 0
    const percent = Math.round(score * 100)
    return (
      <FocusShell title={exercise.data?.title ?? t('exercises.title')} context={context} onClose={goBack}>
        <Card>
          <CardContent className="flex flex-col items-center gap-4 p-8">
            <Check className="text-success size-10" aria-hidden />
            <p className="text-lg font-semibold">{t('exercises.completedTitle')}</p>
            <p className="text-muted-foreground text-sm">
              {t('exercises.independence', { percent })}
            </p>
            <p className="text-muted-foreground max-w-sm text-center text-xs">
              {t('exercises.independenceHint')}
            </p>
            <div className="flex flex-wrap items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={summary.isPending}
                onClick={() => summary.mutate()}
              >
                {summary.isPending ? (
                  <Loader2 className="animate-spin" aria-hidden />
                ) : (
                  <StickyNote aria-hidden />
                )}
                {summaryNoteId !== null
                  ? t('exercises.summarySaved')
                  : t('exercises.saveSummary')}
              </Button>
              <Button variant="outline" size="sm" onClick={goBack}>
                {t('focus.back')}
              </Button>
            </div>
            {summaryNoteId !== null ? (
              <Link
                to="/note/$noteId"
                params={{ noteId: String(summaryNoteId) }}
                search={{ from }}
                className="text-primary text-xs hover:underline"
              >
                {t('exercises.openSummary')}
              </Link>
            ) : null}
            {summary.isError ? (
              <p className="text-warning text-xs">{(summary.error as Error).message}</p>
            ) : null}
          </CardContent>
        </Card>
      </FocusShell>
    )
  }

  if (list.length === 0) {
    return (
      <p className="text-muted-foreground p-8 text-center text-sm">{t('exercises.empty')}</p>
    )
  }

  const step = list[Math.min(session?.current_step_idx ?? 0, list.length - 1)]
  const structuralStep = isStructuralInput(step.input)
  const rubricStep =
    step.input != null &&
    (['essay', 'lines'].includes(step.input.widget) ||
      step.input.kind === 'correct_solution')
  const canSubmit = structuralStep
    ? structuralResponseComplete(step.input!, structural)
    : answer.trim().length > 0
  const nextHintLevel = Math.min(hints.length + 1, 5)

  return (
    <FocusShell
      title={exercise.data?.title ?? t('exercises.title')}
      context={context}
      onClose={goBack}
      meta={
        <>
          <span>{t('exercises.stepCount', { count: list.length })}</span>
          {exercise.data?.difficulty != null ? (
            <span>
              {t('exercises.difficulty')}: {exercise.data.difficulty}
            </span>
          ) : null}
          {session ? (
            <span>{session.socratic ? t('exercises.socraticOn') : t('exercises.socraticOff')}</span>
          ) : null}
        </>
      }
    >
      <div className="mb-6 space-y-2">
        <div className="text-muted-foreground text-xs">
          {t('exercises.stepProgress', {
            current: (session?.current_step_idx ?? 0) + 1,
            total: list.length,
          })}
        </div>
        <div className="bg-border h-1.5 overflow-hidden rounded-full">
          <div
            className="bg-primary h-full transition-all"
            style={{
              width: `${(((session?.current_step_idx ?? 0) + (check?.correct ? 1 : 0)) / list.length) * 100}%`,
            }}
          />
        </div>
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={step.id}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.18 }}
        >
          <Card>
            <CardContent className="space-y-4 p-6">
              <BlockRenderer
                blocks={step.prompt as Block[]}
                onWidgetStateChange={(id, state) =>
                  setWidgetState((prev) => ({ ...prev, [id]: state }))
                }
              />

              {structuralStep ? (
                <div
                  className={cn(
                    'space-y-2',
                    check && 'pointer-events-none opacity-70'
                  )}
                >
                  <ExerciseStructuralInput
                    input={step.input!}
                    value={structural}
                    onChange={setStructural}
                    disabled={check !== null}
                  />
                </div>
              ) : rubricStep ? (
                <RubricStepInput
                  input={step.input!}
                  value={answer}
                  onChange={setAnswer}
                  disabled={check !== null}
                />
              ) : (
                <div
                  className={cn(
                    'border-border rounded-md border p-2',
                    check && 'pointer-events-none opacity-70'
                  )}
                >
                  <MathInput value={answer} onChange={setAnswer} />
                </div>
              )}

              {hints.map((hintResult, index) => (
                <div
                  key={index}
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

              {check ? (
                <div
                  className={cn(
                    'rounded-lg border p-3',
                    check.correct
                      ? 'border-success/40 bg-success/10'
                      : 'border-danger/40 bg-danger/10'
                  )}
                >
                  {structuralStep || rubricStep ? (
                    <p className="text-muted-foreground mb-1 text-xs">{check.stage}</p>
                  ) : null}
                  <p className="flex items-center gap-2 text-sm font-medium">
                    {check.correct ? (
                      <>
                        <Check className="text-success size-4" aria-hidden />
                        {t('exercises.stepCorrect')}
                      </>
                    ) : (
                      <>
                        <X className="text-danger size-4" aria-hidden />
                        {t('exercises.stepIncorrect')}
                        {check.error_class ? (
                          <span className="text-muted-foreground ml-1 text-xs">
                            ({t(`exercises.errors.${check.error_class}`)})
                          </span>
                        ) : null}
                      </>
                    )}
                  </p>
                </div>
              ) : null}

              {error ? <p className="text-danger text-xs">{error}</p> : null}

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={hint.isPending || hints.length >= 5}
                    onClick={() => hint.mutate(nextHintLevel)}
                  >
                    {hint.isPending ? (
                      <Loader2 className="animate-spin" aria-hidden />
                    ) : (
                      <HelpCircle aria-hidden />
                    )}
                    {t('exercises.requestHint', { level: nextHintLevel })}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={ask.isPending}
                    title={t('exercises.askTutorHint')}
                    onClick={() => ask.mutate()}
                  >
                    {ask.isPending ? (
                      <Loader2 className="animate-spin" aria-hidden />
                    ) : (
                      <MessageSquare aria-hidden />
                    )}
                    {t('exercises.askTutor')}
                  </Button>
                </div>
                {check?.correct ? (
                  <Button
                    onClick={() => {
                      setSession(check.session)
                      setAnswer('')
                      setStructural(null)
                      setWidgetState({})
                      setCheck(null)
                      setHints([])
                    }}
                  >
                    {t('quiz.next')}
                    <ArrowRight aria-hidden />
                  </Button>
                ) : (
                  <Button
                    disabled={!canSubmit || submit.isPending}
                    onClick={() => submit.mutate()}
                  >
                    {submit.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                    {t('exercises.check')}
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

export function ExercisePlayerRoute() {
  const { exerciseId } = useParams({ from: '/exercises/$exerciseId' })
  return <Player exerciseId={Number(exerciseId)} />
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { BookOpen, CalendarClock, Flame, Layers, Loader2, MessageSquare, Sparkles, Target } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from '@tanstack/react-router'

import { useCurrentOrigin } from '@/lib/origin'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ui/error-banner'
import { useRequiredCourse } from '@/components/workspace/CoursePicker'
import { useWizardStore } from '@/features/onboarding/wizardStore'
import {
  createChatSession,
  createSampleCourse,
  generateQuiz,
  getHealth,
  getOverview,
  getExamStatus,
  getRecommendations,
  listCourses,
  listMaterials,
  setDailyGoal,
  type Recommendation,
} from '@/lib/api'

import { cn } from '@/lib/utils'

function BackendBadge() {
  const { t } = useTranslation()
  const health = useQuery({ queryKey: ['health'], queryFn: () => getHealth(), retry: 1, refetchOnWindowFocus: false })

  return (
    <span className="text-muted-foreground rounded-full border border-dashed px-3 py-1 text-xs">
      {health.data ? t('home.backendOnline', { version: health.data.version }) : t('home.backendOffline')}
    </span>
  )
}

function GoalRing({ done, goal }: { done: number; goal: number }) {
  const percent = Math.min(100, Math.round((done / Math.max(1, goal)) * 100))
  return (
    <div
      className="border-primary/30 text-primary relative flex size-20 items-center justify-center rounded-full border-8"
      role="progressbar"
      aria-valuenow={percent}
      style={{
        borderColor: `color-mix(in srgb, var(--primary) ${percent}%, var(--border))`,
      }}
    >
      <div className="text-center">
        <p className="text-sm leading-none font-bold">{percent}%</p>
        <p className="text-muted-foreground text-[10px]">
          {done}/{goal}
        </p>
      </div>
    </div>
  )
}

function ActionButton({
  kind,
  concept,
  skill,
}: {
  kind: string
  concept: string | null
  skill: string | null
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const queryClient = useQueryClient()
  const required = useRequiredCourse()
  const [error, setError] = useState<string | null>(null)

  const weakArea = useMutation({
    mutationFn: ({
      courseIdForBody,
      difficulty,
    }: {
      courseIdForBody: number
      difficulty: number
    }) =>
      generateQuiz({
        course_id: courseIdForBody,
        topic: concept ?? undefined,
        skill: skill ?? undefined,
        count: 8,
        difficulty,
      }),
    onSuccess: async (activity) => {
      await queryClient.invalidateQueries({ queryKey: ['quizzes'] })
      navigate({ to: '/quiz/$activityId', params: { activityId: String(activity.id) }, search: { from } })
    },
    onError: (err: Error) => setError(err.message),
  })

  const askTutor = useMutation({
    mutationFn: (courseId: number) =>
      createChatSession(courseId, null, concept ? `Ask about ${concept}` : undefined),
    onSuccess: async (session) => {
      await queryClient.invalidateQueries({ queryKey: ['chat-sessions'] })
      void navigate({ to: '/chat/$chatId', params: { chatId: session.public_id } })
    },
    onError: (err: Error) => setError(err.message),
  })

  if (kind === 'review') {
    return (
      <Button
        size="sm"
        variant="outline"
        onClick={() =>
          navigate(
            required.courseId !== null
              ? { to: '/courses/$courseId', params: { courseId: String(required.courseId) }, search: { tab: 'cards' } }
              : { to: '/courses' },
          )
        }
      >
        <Layers aria-hidden />
        {t('today.reviewNow')}
      </Button>
    )
  }
  if (kind === 'drill' || kind === 'challenge') {
    if (required.needsPicker) {
      return <ErrorBanner message={t('workspace.openCourseFirst')} />
    }
    return (
      <div className="flex flex-wrap items-center gap-1.5">
        <Button
          size="sm"
          variant="outline"
          disabled={weakArea.isPending || required.courseId === null}
          onClick={() => {
            if (required.courseId !== null) {
              weakArea.mutate({
                courseIdForBody: required.courseId,
                difficulty: kind === 'challenge' ? 4 : 2,
              })
            }
          }}
        >
          {weakArea.isPending ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : kind === 'challenge' ? (
            <Sparkles aria-hidden />
          ) : (
            <Target aria-hidden />
          )}
          {kind === 'challenge' ? t('today.challengeNow') : t('today.drillNow')}
        </Button>
        {concept ? (
          <Button
            size="sm"
            variant="ghost"
            disabled={askTutor.isPending || required.courseId === null}
            onClick={() => {
              if (required.courseId !== null) {
                askTutor.mutate(required.courseId)
              }
            }}
          >
            {askTutor.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <MessageSquare aria-hidden />
            )}
            {t('today.askTutor', { concept })}
          </Button>
        ) : null}
      </div>
    )
  }
  if (error) {
    return <ErrorBanner message={error} />
  }
  return (
    <Button size="sm" variant="outline" onClick={() => navigate({ to: '/library' })}>
      <BookOpen aria-hidden />
      {concept ? t('today.readAbout', { concept }) : t('today.readNow')}
    </Button>
  )
}

function evidenceLine(rec: Recommendation, t: (key: string, values?: Record<string, unknown>) => string): string {
  const { evidence, kind } = rec
  if (kind === 'review' && evidence.due_cards !== undefined) {
    return t('today.evidenceReview', { count: evidence.due_cards })
  }
  if (evidence.misses !== undefined && evidence.n !== undefined) {
    return t('today.evidenceWeak', {
      misses: evidence.misses,
      n: evidence.n,
      skill: rec.skill ?? '',
    })
  }
  if (evidence.accuracy !== undefined && evidence.n !== undefined) {
    return t('today.evidenceStale', { n: evidence.n })
  }
  return ''
}

function ExamCard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const exams = useQuery({ queryKey: ['exam-status'], queryFn: getExamStatus })
  const entries = exams.data ?? []
  if (exams.isLoading || entries.length === 0) {
    return null
  }
  return (
    <div className="space-y-2">
      {entries.map((entry) => {
        const covered =
          entry.total_nodes === 0
            ? 100
            : Math.round((entry.engaged_nodes / entry.total_nodes) * 100)
        return (
          <div
            key={entry.course_id}
            className="border-border flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border px-3 py-2.5"
          >
            <CalendarClock
              className={cn('size-4 shrink-0', entry.on_track ? 'text-primary' : 'text-danger')}
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {t('today.examCountdown', {
                  course: entry.course_title,
                  days: entry.days_left,
                  date: new Date(entry.exam_date).toLocaleDateString(),
                })}
              </p>
              <div className="bg-subtle mt-1 h-1.5 w-full max-w-56 overflow-hidden rounded-full">
                <div
                  className={cn('h-full rounded-full', entry.on_track ? 'bg-primary' : 'bg-danger')}
                  style={{ width: `${covered}%` }}
                />
              </div>
              <p
                className={cn('text-xs', entry.on_track ? 'text-muted-foreground' : 'text-danger')}
              >
                {t('today.examPace', {
                  engaged: entry.engaged_nodes,
                  total: entry.total_nodes,
                  pace: entry.nodes_per_day ?? 0,
                })}
              </p>
            </div>
            {entry.most_behind_node ? (
              <Button
                variant="outline"
                size="sm"
                title={entry.most_behind_node.title}
                onClick={() =>
                  void navigate({
                    to: '/courses/$courseId/n/$nodeId',
                    params: {
                      courseId: String(entry.course_id),
                      nodeId: String(entry.most_behind_node!.id),
                    },
                  })
                }
              >
                {t('today.examJump', { node: entry.most_behind_node.title })}
              </Button>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function NextBestActions() {
  const { t } = useTranslation()
  const recs = useQuery({ queryKey: ['recommendations'], queryFn: () => getRecommendations() })
  const list = recs.data ?? []
  if (recs.isLoading) {
    return null
  }
  if (list.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">{t('today.noRecommendations')}</p>
    )
  }
  return (
    <div className="space-y-2">
      {list.slice(0, 3).map((rec) => (
        <div
          key={`${rec.kind}-${rec.concept ?? 'any'}`}
          className="border-border flex items-center gap-3 rounded-lg border px-3 py-2.5"
        >
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">
              {t(`today.rec.${rec.kind}`)}
              {rec.concept ? <span className="text-primary"> {rec.concept}</span> : null}
            </p>
            <p className="text-muted-foreground text-xs">{evidenceLine(rec, t)}</p>
          </div>
          <ActionButton kind={rec.kind} concept={rec.concept} skill={rec.skill} />
        </div>
      ))}
    </div>
  )
}

function Heatmap({ days }: { days: { day: string; answers_n: number }[] }) {
  const { t } = useTranslation()
  const max = Math.max(1, ...days.map((entry) => entry.answers_n))
  return (
    <div className="flex flex-wrap gap-1" aria-label={t('today.heatmapLabel')}>
      {days.map((entry) => (
        <div
          key={entry.day}
          title={`${entry.day}: ${entry.answers_n}`}
          className={cn('rounded-sm', entry.answers_n === 0 && 'bg-subtle')}
          style={{
            width: 10,
            height: 10,
            backgroundColor:
              entry.answers_n > 0
                ? `color-mix(in srgb, var(--primary) ${Math.max(20, Math.round((entry.answers_n / max) * 100))}%, transparent)`
                : undefined,
          }}
        />
      ))}
    </div>
  )
}

export function HomePage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const overview = useQuery({ queryKey: ['overview'], queryFn: getOverview })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const materials = useQuery({ queryKey: ['materials', null], queryFn: () => listMaterials() })
  const openWizard = useWizardStore((state) => state.openWizard)
  const [goalEdit, setGoalEdit] = useState<number | null>(null)

  const sample = useMutation({
    mutationFn: () => createSampleCourse(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['courses'] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
    },
  })

  const saveGoal = useMutation({
    mutationFn: (value: number) => setDailyGoal(value),
    onSuccess: async () => {
      setGoalEdit(null)
      await queryClient.invalidateQueries({ queryKey: ['overview'] })
    },
  })

  const data = overview.data

  return (
    <div className="mx-auto max-w-4xl p-8">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">{t('home.title')}</h1>
        <BackendBadge />
      </header>
      <AnimatePresence initial={false}>
        <motion.div
          key="cards"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.18 }}
          className="grid gap-4 sm:grid-cols-3"
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Flame className="text-warning size-4" aria-hidden />
                {t('home.streak')}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex items-baseline gap-2">
              <span className="text-3xl font-bold">{data?.streak ?? 0}</span>
              <span className="text-muted-foreground text-xs">{t('today.days')}</span>
              <span className="text-muted-foreground ml-auto text-xs">
                {t('today.level', { level: data?.level ?? 1 })}
              </span>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Target className="size-4" aria-hidden />
                {t('home.dailyGoal')}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex items-center gap-3">
              <GoalRing done={data?.today?.answers_n ?? 0} goal={data?.goal ?? 20} />
              {goalEdit === null ? (
                <button
                  type="button"
                  className="text-muted-foreground hover:text-foreground text-xs underline"
                  onClick={() => setGoalEdit(data?.goal ?? 20)}                >
                  {t('today.changeGoal')}
                </button>
              ) : (
                <div className="flex flex-col gap-1">
                  <input
                    type="number"
                    min={1}
                    max={500}
                    className="bg-surface border-border w-20 rounded-md border px-2 py-1 text-xs"
                    value={goalEdit}
                    onChange={(event) => setGoalEdit(Number(event.target.value))}
                  />
                <button
                    type="button"
                    className="text-primary text-xs underline"
                    onClick={() => goalEdit && saveGoal.mutate(goalEdit)}
                  >
                    {t('today.saveGoal')}
                  </button>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Layers className="size-4" aria-hidden />
                {t('today.dueReviews')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold">{data?.due_cards ?? 0}</p>
              <CardDescription>{t('today.dueReviewsHint')}</CardDescription>
            </CardContent>
          </Card>
        </motion.div>
      </AnimatePresence>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-sm">{t('home.nextAction')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ExamCard />
          <NextBestActions />
          {(courses.data ?? []).length === 0 && (materials.data ?? []).length === 0 ? (
            <div className="border-border mt-3 space-y-2 rounded-lg border border-dashed p-4 text-center">
              <p className="text-muted-foreground mb-2 text-xs">{t('today.onboardingHint')}</p>
              <div className="flex justify-center gap-2">
                <Button size="sm" disabled={sample.isPending} onClick={() => openWizard()}>
                  {t('onboarding.runWizard')}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={sample.isPending}
                  onClick={() => sample.mutate()}
                >
                  {sample.isPending ? (
                    <Loader2 className="animate-spin" aria-hidden />
                  ) : (
                    <BookOpen aria-hidden />
                  )}
                  {t('today.createSample')}
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-sm">{t('today.consistency')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {data?.history && data.history.length > 0 ? (
            <Heatmap days={data.history} />
          ) : (
            <p className="text-muted-foreground text-sm">{t('today.noHistory')}</p>
          )}
          <p className="text-muted-foreground text-xs">
            {t('today.coursesCount', { count: courses.data?.length ?? 0 })}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

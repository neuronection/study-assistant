import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { useMotionPresets } from '@/lib/motion'
import { BookOpen, CalendarClock, Clock3, Flame, GraduationCap, Layers, Loader2, MessageSquare, NotebookPen, Sparkles, Target } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from '@tanstack/react-router'

import { useCurrentOrigin } from '@/lib/origin'
import { GenesisDialog } from '@/features/ai/GenesisDialog'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorBanner } from '@/components/ErrorBanner'
import { useRequiredCourse } from '@/components/workspace/CoursePicker'
import { useWizardStore } from '@/features/onboarding/wizardStore'
import { useCaptureStore } from '@/lib/capture-store'
import { useNotifications } from '@/components/layout/NotificationBell'
import {
  createChatSession,
  createSampleCourse,
  createTeachBack,
  generateQuiz,
  getHealth,
  getOverview,
  getExamStatus,
  getRecommendations,
  getScratchpad,
  listUpcomingItems,
  listCourses,
  listMaterials,
  listNotes,
  setDailyGoal,
  getStudyNext,
  type Recommendation,
} from '@/lib/api'

import { formatDate } from '@/lib/format'
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

function formatStudyMinutes(totalSeconds: number): string {
  const minutes = Math.round(totalSeconds / 60)
  const hours = Math.floor(minutes / 60)
  if (hours >= 1) {
    const rest = minutes % 60
    return rest > 0 ? `${hours} h ${rest} min` : `${hours} h`
  }
  return `${minutes} min`
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

  const teachBack = useMutation({
    mutationFn: (body: { course_id: number; concept: string | null }) =>
      createTeachBack({
        course_id: body.course_id,
        concept: body.concept,
      }),
    onSuccess: async (exercise) => {
      void navigate({
        to: '/exercises/$exerciseId',
        params: { exerciseId: String(exercise.id) },
      })
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
        onClick={() => void navigate({ to: '/review' })}
      >
        <Layers aria-hidden />
        {t('today.reviewNow')}
      </Button>
    )
  }
  if (kind === 'teachback') {
    if (required.needsPicker || required.courseId === null) {
      return <ErrorBanner message={t('workspace.openCourseFirst')} />
    }
    return (
      <Button
        size="sm"
        variant="outline"
        disabled={teachBack.isPending}
        onClick={() => {
          if (required.courseId !== null) {
            teachBack.mutate({
              course_id: required.courseId,
              concept: concept ?? null,
            })
          }
        }}
      >
        {teachBack.isPending ? (
          <Loader2 className="animate-spin" aria-hidden />
        ) : (
          <GraduationCap aria-hidden />
        )}
        {concept ? t('today.teachBackNow', { concept }) : t('today.teachBackNowPlain')}
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

function ReadinessRing({ score }: { score: number }) {
  const radius = 14
  const circumference = 2 * Math.PI * radius
  const filled = (Math.max(0, Math.min(100, score)) / 100) * circumference
  const color =
    score >= 70 ? 'text-success' : score >= 40 ? 'text-warning' : 'text-danger'
  return (
    <svg
      viewBox="0 0 36 36"
      className={cn('size-9 shrink-0 -rotate-90', color)}
      role="img"
      aria-label={`${score}`}
    >
      <circle cx="18" cy="18" r={radius} fill="none" stroke="currentColor" strokeOpacity={0.2} strokeWidth="4" />
      <circle
        cx="18"
        cy="18"
        r={radius}
        fill="none"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${circumference - filled}`}
      />
    </svg>
  )
}

function ExamCard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const exams = useQuery({ queryKey: ['exam-status'], queryFn: getExamStatus })
  const entries = exams.data ?? []
  if (exams.isLoading) {
    return (
      <div aria-busy="true" className="space-y-2">
        {[0, 1].map((index) => (
          <div
            key={index}
            className="border-border flex items-center gap-x-3 rounded-lg border px-3 py-2.5"
          >
            <Skeleton className="size-9 shrink-0 rounded-full" />
            <Skeleton className="h-4 min-w-0 flex-1" />
          </div>
        ))}
      </div>
    )
  }
  if (entries.length === 0) {
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
            {entry.readiness_state === 'ok' && entry.readiness !== null && entry.readiness !== undefined ? (
              <div className="relative shrink-0" title={t('today.readinessTitle')}>
                <ReadinessRing score={entry.readiness} />
                <span className="absolute inset-0 flex rotate-0 items-center justify-center text-[10px] font-semibold">
                  {entry.readiness}
                </span>
              </div>
            ) : null}
            <CalendarClock
              className={cn('size-4 shrink-0', entry.on_track ? 'text-primary' : 'text-danger')}
              aria-hidden
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {t('today.examCountdown', {
                  course: entry.course_title,
                  days: entry.days_left,
                  date: formatDate(entry.exam_date),
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
              {entry.readiness_state === 'ok' ? (
                <p className="text-muted-foreground mt-0.5 text-xs">
                  <span className="text-foreground font-medium">
                    {t('today.readiness')}
                    {entry.readiness !== null && entry.readiness !== undefined ? ` ${entry.readiness}` : ''}
                  </span>
                  {entry.trend ? (
                    <>
                      {' · '}
                      {t(`today.readinessTrend_${entry.trend}`)}
                    </>
                  ) : null}
                  {entry.weakest && entry.weakest.length > 0 ? (
                    <> · {t('today.weakest', { concepts: entry.weakest.join(', ') })}</>
                  ) : null}
                </p>
              ) : (
                <p className="text-muted-foreground mt-0.5 text-xs">
                  {t('today.readinessNoData')}
                </p>
              )}
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

function ReviewNudgeStrip() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { data } = useNotifications()
  if (!data || (data.due_cards === 0 && data.plan_overdue_count === 0)) {
    return null
  }
  return (
    <div className="border-primary/30 bg-primary/5 flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2">
      <Layers className="text-primary size-4 shrink-0" aria-hidden />
      <span className="text-foreground text-sm">
        {data.due_cards > 0
          ? t('home.cardsDue', { count: data.due_cards })
          : null}
        {data.due_cards > 0 && data.plan_overdue_count > 0
          ? t('home.stripJoin')
          : null}
        {data.plan_overdue_count > 0
          ? t('home.overdueTasks', { count: data.plan_overdue_count })
          : null}
      </span>
      <Button
        size="sm"
        variant="outline"
        className="ml-auto"
        onClick={() => void navigate({ to: '/review' })}
      >
        <Target aria-hidden />
        {t('today.reviewNow')}
      </Button>
    </div>
  )
}

function StudyNowCard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const next = useQuery({ queryKey: ['study-next'], queryFn: () => getStudyNext() })
  if (next.isLoading || next.isError || next.data === undefined) {
    return null
  }
  const data = next.data
  const nothing =
    data.due_cards === 0 && data.plan_rows.length === 0 && data.weak_cells.length === 0
  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Sparkles className="text-primary size-4" aria-hidden />
          {t('home.studyNow')}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-3">
        {nothing ? (
          <p className="text-muted-foreground text-sm">{t('home.studyNowAllClear')}</p>
        ) : (
          <span className="text-muted-foreground text-sm">
            {data.due_cards > 0 ? t('home.studyNowCards', { count: data.due_cards }) : null}
            {data.due_cards > 0 && data.plan_rows.length > 0 ? ' · ' : null}
            {data.plan_rows.length > 0
              ? t('home.studyNowPlan', { count: data.plan_rows.length })
              : null}
            {data.plan_rows.length > 0 && data.weak_cells.length > 0 ? ' · ' : null}
            {data.weak_cells.length > 0
              ? t('home.studyNowWeak', { count: data.weak_cells.length })
              : null}
          </span>
        )}
        <Button
          size="sm"
          className="ml-auto"
          disabled={nothing}
          onClick={() => void navigate({ to: '/study/session' })}
        >
          <Sparkles aria-hidden />
          {t('home.studyNowButton')}
        </Button>
      </CardContent>
    </Card>
  )
}

function NextBestActions() {
  const { t } = useTranslation()
  const recs = useQuery({ queryKey: ['recommendations'], queryFn: () => getRecommendations() })
  const list = recs.data ?? []
  if (recs.isLoading) {
    return (
      <div aria-busy="true" className="space-y-2">
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className="border-border flex items-center gap-3 rounded-lg border px-3 py-2.5"
          >
            <Skeleton className="h-4 min-w-0 flex-1" />
            <Skeleton className="h-8 w-20 shrink-0 rounded-md" />
          </div>
        ))}
      </div>
    )
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

function UpcomingPlanStrip() {
  const { t } = useTranslation()
  const upcoming = useQuery({
    queryKey: ['plan-upcoming'],
    queryFn: () => listUpcomingItems(7),
  })
  const items = Array.isArray(upcoming.data) ? upcoming.data : []
  if (upcoming.isLoading) {
    return (
      <div aria-busy="true" className="space-y-1">
        <Skeleton className="h-3 w-24" />
        {[0, 1, 2, 3].map((index) => (
          <div
            key={index}
            className="border-border flex items-center gap-2 rounded-lg border px-3 py-2"
          >
            <Skeleton className="h-3.5 w-16 shrink-0" />
            <Skeleton className="h-4 min-w-0 flex-1" />
          </div>
        ))}
      </div>
    )
  }
  if (items.length === 0) {
    return null
  }
  return (
    <div className="space-y-1">
      <p className="text-muted-foreground text-xs font-medium">{t('planner.upcomingTitle')}</p>
      {items.slice(0, 5).map((item) => (
        <div
          key={item.id}
          className="border-border flex items-center gap-2 rounded-lg border px-3 py-2"
        >
          <CalendarClock className="text-muted-foreground size-3.5 shrink-0" aria-hidden />
          <span className="text-muted-foreground text-xs">{formatDate(item.due_date)}</span>
          <span className="min-w-0 flex-1 truncate text-sm">{item.title}</span>
          <span className="text-muted-foreground hidden truncate text-xs sm:block">
            {item.course_title}
          </span>
        </div>
      ))}
    </div>
  )
}

function Heatmap({
  days,
}: {
  days: { day: string; answers_n: number; study_seconds: number }[]
}) {
  const { t } = useTranslation()
  const intensity = (entry: { answers_n: number; study_seconds: number }): number =>
    entry.answers_n + Math.round(entry.study_seconds / 60)
  const max = Math.max(1, ...days.map(intensity))
  return (
    <div className="flex flex-wrap gap-1" aria-label={t('today.heatmapLabel')}>
      {days.map((entry) => {
        const level = intensity(entry)
        return (
          <div
            key={entry.day}
            title={`${entry.day}: ${t('today.heatmapAnswers', { count: entry.answers_n })} · ${formatStudyMinutes(entry.study_seconds)}`}
            className={cn('rounded-sm', level === 0 && 'bg-subtle')}
            style={{
              width: 10,
              height: 10,
              backgroundColor:
                level > 0
                  ? `color-mix(in srgb, var(--primary) ${Math.max(20, Math.round((level / max) * 100))}%, transparent)`
                  : undefined,
            }}
          />
        )
      })}
    </div>
  )
}

export function HomePage() {
  const { t } = useTranslation()
  const presets = useMotionPresets()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const overview = useQuery({ queryKey: ['overview'], queryFn: getOverview })
  const courses = useQuery({ queryKey: ['courses'], queryFn: listCourses })
  const materials = useQuery({ queryKey: ['materials', null], queryFn: () => listMaterials() })
  const scratchpad = useQuery({ queryKey: ['scratchpad'], queryFn: getScratchpad })
  const captures = useQuery({
    queryKey: ['notes', 'scratchpad-captures'],
    queryFn: () => listNotes(undefined, scratchpad.data!.course.id, { limit: 3 }),
    enabled: scratchpad.data !== undefined,
  })
  const openCapture = useCaptureStore((state) => state.openCapture)
  const openWizard = useWizardStore((state) => state.openWizard)
  const [goalUnitEdit, setGoalUnitEdit] = useState<'answers' | 'minutes' | null>(null)
  const [goalValueEdit, setGoalValueEdit] = useState<number | null>(null)
  const [genesisOpen, setGenesisOpen] = useState(false)

  const sample = useMutation({
    mutationFn: () => createSampleCourse(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['courses'] })
      await queryClient.invalidateQueries({ queryKey: ['materials'] })
    },
  })

  const saveGoal = useMutation({
    mutationFn: (body: { unit: 'answers' | 'minutes'; value: number }) =>
      body.unit === 'minutes'
        ? setDailyGoal({ unit: 'minutes', minutes_per_day: body.value })
        : setDailyGoal({ unit: 'answers', answers_per_day: body.value }),
    onSuccess: async () => {
      setGoalUnitEdit(null)
      setGoalValueEdit(null)
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
          {...presets.enter}
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Flame className="text-warning size-4" aria-hidden />
                {t('home.streak')}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex items-baseline gap-2">
              {overview.isLoading ? (
                <Skeleton className="h-9 w-16" />
              ) : (
                <span className="text-3xl font-bold">{data?.streak ?? 0}</span>
              )}
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
              {overview.isLoading ? (
                <Skeleton className="size-14 shrink-0 rounded-full" />
              ) : data?.unit === 'minutes' ? (
                <GoalRing
                  done={Math.round((data?.today?.study_seconds ?? 0) / 60)}
                  goal={data?.minutes_per_day ?? 30}
                />
              ) : (
                <GoalRing done={data?.today?.answers_n ?? 0} goal={data?.answers_per_day ?? 20} />
              )}
              {goalUnitEdit === null || goalValueEdit === null ? (
                <button
                  type="button"
                  className="text-muted-foreground hover:text-foreground text-xs underline"
                  onClick={() => {
                    setGoalUnitEdit(data?.unit ?? 'answers')
                    setGoalValueEdit(
                      data?.unit === 'minutes'
                        ? (data?.minutes_per_day ?? 30)
                        : (data?.answers_per_day ?? 20)
                    )
                  }}
                >
                  {t('today.changeGoal')}
                </button>
              ) : (
                <div className="flex flex-col gap-1.5">
                  <div
                    className="border-border bg-subtle flex overflow-hidden rounded-md text-[10px] font-medium"
                    role="radiogroup"
                    aria-label={t('today.goalUnit')}
                  >
                    {(['answers', 'minutes'] as const).map((unitOption) => (
                      <button
                        key={unitOption}
                        type="button"
                        role="radio"
                        aria-checked={goalUnitEdit === unitOption}
                        className={cn(
                          'px-2 py-1 transition-colors',
                          goalUnitEdit === unitOption
                            ? 'bg-primary text-primary-foreground'
                            : 'text-muted-foreground hover:text-foreground'
                        )}
                        onClick={() => {
                          setGoalUnitEdit(unitOption)
                          setGoalValueEdit(
                            unitOption === 'minutes'
                              ? (data?.minutes_per_day ?? 30)
                              : (data?.answers_per_day ?? 20)
                          )
                        }}
                      >
                        {t(`today.goalUnit_${unitOption}`)}
                      </button>
                    ))}
                  </div>
                  <input
                    type="number"
                    min={1}
                    max={goalUnitEdit === 'minutes' ? 1440 : 500}
                    className="bg-surface border-border w-20 rounded-md border px-2 py-1 text-xs"
                    value={goalValueEdit}
                    onChange={(event) => setGoalValueEdit(Number(event.target.value))}
                    aria-label={t('today.goalValue')}
                  />
                  <button
                    type="button"
                    className="text-primary text-xs underline"
                    onClick={() =>
                      goalValueEdit > 0 && saveGoal.mutate({ unit: goalUnitEdit, value: goalValueEdit })
                    }
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
                <Clock3 className="text-primary size-4" aria-hidden />
                {t('home.studyTime')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {overview.isLoading ? (
                <Skeleton className="h-9 w-20" />
              ) : (
                <p className="text-3xl font-bold">
                  {formatStudyMinutes(data?.today?.study_seconds ?? 0)}
                </p>
              )}
              <CardDescription>
                {t('today.studyWeek', { time: formatStudyMinutes(data?.study_seconds_week ?? 0) })}
              </CardDescription>
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
              {overview.isLoading ? (
                <Skeleton className="h-9 w-16" />
              ) : (
                <p className="text-3xl font-bold">{data?.due_cards ?? 0}</p>
              )}
              <CardDescription className="flex items-center gap-1">
                {t('today.dueReviewsHint')}
                <button
                  type="button"
                  className="text-primary hover:underline"
                  onClick={() => void navigate({ to: '/review' })}
                >
                  {t('today.reviewNow')}
                </button>
              </CardDescription>
            </CardContent>
          </Card>
        </motion.div>
      </AnimatePresence>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle className="text-sm">{t('home.nextAction')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <ReviewNudgeStrip />
          <ExamCard />
          <StudyNowCard />
          <NextBestActions />
          <UpcomingPlanStrip />
          {(captures.data?.items ?? []).length > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-muted-foreground flex items-center gap-1 text-[11px]">
                <NotebookPen className="size-3.5" aria-hidden />
                {t('capture.recentTitle')}
              </span>
              {(captures.data?.items ?? []).map((note) => (
                <button
                  key={note.id}
                  type="button"
                  className="border-border hover:border-primary/50 hover:bg-subtle max-w-56 truncate rounded-full border px-2.5 py-1 text-xs transition-colors"
                  onClick={() =>
                    void navigate({
                      to: '/note/$noteId',
                      params: { noteId: String(note.id) },
                    })
                  }
                >
                  {note.title}
                </button>
              ))}
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground text-xs underline"
                onClick={openCapture}
              >
                {t('capture.paletteAction')}
              </button>
            </div>
          ) : null}
          {scratchpad.data !== undefined ? (
            <div className="flex flex-wrap justify-center gap-2">
              <Button
                size="sm"
                onClick={() => setGenesisOpen(true)}
              >
                <Sparkles aria-hidden />
                {t('home.genesisTopic')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  void navigate({
                    to: '/courses/$courseId',
                    params: { courseId: String(scratchpad.data!.course.id) },
                  })
                }
              >
                {t('home.exploreTopic')}
              </Button>
            </div>
          ) : null}
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
          {overview.isLoading ? (
            <Skeleton className="h-24 w-full rounded-md" />
          ) : data?.history && data.history.length > 0 ? (
            <Heatmap days={data.history} />
          ) : (
            <p className="text-muted-foreground text-sm">{t('today.noHistory')}</p>
          )}
          <p className="text-muted-foreground text-xs">
            {t('today.coursesCount', { count: courses.data?.length ?? 0 })}
          </p>
        </CardContent>
      </Card>
      {genesisOpen ? <GenesisDialog onClose={() => setGenesisOpen(false)} /> : null}
    </div>
  )
}

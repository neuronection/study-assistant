import { useQuery } from '@tanstack/react-query'
import { BookX, Grid3x3, History, Lightbulb } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'

import { useCurrentOrigin } from '@/lib/origin'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { WorkspaceGate } from '@/components/workspace/WorkspaceGate'
import {
  getDiagnostics,
  getRecommendations,
  listMistakes,
  listQuizAttempts,
  type MatrixCell,
} from '@/lib/api'
import { useWorkspaceStore } from '@/lib/workspace-store'

import { cn } from '@/lib/utils'

const TABS = ['history', 'diagnostics', 'recommendations', 'mistakes'] as const
type Tab = (typeof TABS)[number]

function accuracyColor(accuracy: number): string {
  if (accuracy >= 0.8) return 'var(--success)'
  if (accuracy >= 0.5) return 'var(--warning)'
  return 'var(--danger)'
}

function WeaknessMatrix() {
  const { t } = useTranslation()
  const courseId = useWorkspaceStore((state) => state.courseId)
  const diagnostics = useQuery({
    queryKey: ['diagnostics', courseId],
    queryFn: () => getDiagnostics(courseId ?? undefined),
  })
  const data = diagnostics.data
  if (diagnostics.isLoading) {
    return <p className="text-muted-foreground text-sm">{t('library.loading')}</p>
  }
  const cells = data?.weakness_matrix ?? []
  if (cells.length === 0) {
    return <p className="text-muted-foreground text-sm">{t('scores.diagnosticsEmpty')}</p>
  }
  const concepts = Array.from(new Set(cells.map((cell) => cell.concept)))
  const skills = data?.skills ?? []
  const byKey = new Map(cells.map((cell) => [`${cell.concept}:${cell.skill}`, cell]))

  const renderCell = (concept: string, skill: string) => {
    const cell: MatrixCell | undefined = byKey.get(`${concept}:${skill}`)
    if (!cell) {
      return <div className="bg-subtle rounded-md p-1 text-center text-xs opacity-40">·</div>
    }
    return (
      <div
        className={cn('rounded-md p-1 text-center text-xs font-medium', !cell.enough_data && 'opacity-50')}
        style={{
          backgroundColor:
            cell.enough_data && cell.accuracy < 0.5
              ? `color-mix(in srgb, var(--danger) ${Math.round((1 - cell.accuracy) * 40)}%, transparent)`
              : cell.enough_data
                ? `color-mix(in srgb, var(--success) ${Math.round(cell.accuracy * 30)}%, transparent)`
                : 'var(--subtle)',
          color: cell.enough_data ? accuracyColor(cell.accuracy) : undefined,
        }}
        title={`${concept} × ${skill}: ${Math.round(cell.accuracy * 100)}% (${cell.n})`}
      >
        {cell.enough_data ? `${Math.round(cell.accuracy * 100)}%` : `~${cell.n}`}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="grid gap-1" style={{ gridTemplateColumns: `140px repeat(${skills.length}, minmax(64px, 1fr))` }}>
        <div />
        {skills.map((skill) => (
          <div key={skill} className="text-muted-foreground truncate text-center text-[11px]">
            {t(`scores.skill.${skill}`)}
          </div>
        ))}
        {concepts.map((concept) => (
          <div key={concept} className="contents">
            <div className="text-muted-foreground truncate text-xs" title={concept}>
              {concept}
            </div>
            {skills.map((skill) => (
              <div key={`${concept}-${skill}`}>{renderCell(concept, skill)}</div>
            ))}
          </div>
        ))}
      </div>
      <p className="text-muted-foreground text-[11px]">{t('scores.matrixLegend')}</p>
    </div>
  )
}

function ErrorProfile() {
  const { t } = useTranslation()
  const courseId = useWorkspaceStore((state) => state.courseId)
  const diagnostics = useQuery({
    queryKey: ['diagnostics', courseId],
    queryFn: () => getDiagnostics(courseId ?? undefined),
  })
  const profile = diagnostics.data?.error_profile ?? []
  if (profile.length === 0) {
    return <p className="text-muted-foreground text-sm">{t('scores.noErrorTags')}</p>
  }
  return (
    <div className="space-y-1">
      {profile.slice(0, 10).map((entry) => (
        <div key={entry.tag} className="flex items-center gap-3 text-sm">
          <span className="bg-danger/15 text-danger rounded-full px-2 py-0.5 text-[11px]">
            {entry.tag}
          </span>
          <span className="text-muted-foreground text-xs">
            {t('scores.tagCount', { total: entry.total })}
          </span>
          <span
            className={cn(
              'ml-auto text-xs',
              entry.trend > 0 ? 'text-danger' : entry.trend < 0 ? 'text-success' : 'text-muted-foreground'
            )}
          >
            {entry.trend > 0
              ? t('scores.trendUp', { count: entry.trend })
              : entry.trend < 0
                ? t('scores.trendDown', { count: -entry.trend })
                : t('scores.trendFlat')}
          </span>
        </div>
      ))}
    </div>
  )
}

function SpeedAccuracy() {
  const { t } = useTranslation()
  const courseId = useWorkspaceStore((state) => state.courseId)
  const diagnostics = useQuery({
    queryKey: ['diagnostics', courseId],
    queryFn: () => getDiagnostics(courseId ?? undefined),
  })
  const entries = diagnostics.data?.speed_accuracy ?? []
  if (entries.length === 0) {
    return <p className="text-muted-foreground text-sm">{t('scores.noTimingData')}</p>
  }
  return (
    <div className="space-y-1">
      {entries.map((entry) => (
        <div key={entry.concept} className="flex items-center gap-3 text-sm">
          <span className="min-w-0 flex-1 truncate">{entry.concept}</span>
          <span className="text-muted-foreground text-xs">
            {t('scores.speedLine', {
              accuracy: Math.round(entry.accuracy * 100),
              ratio: entry.avg_time_ratio,
            })}
          </span>
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-[11px]',
              entry.quadrant === 'fluent' && 'bg-success/15 text-success',
              entry.quadrant === 'rushing' && 'bg-warning/15 text-warning',
              entry.quadrant === 'effortful' && 'bg-primary/10 text-primary',
              entry.quadrant === 'struggling' && 'bg-danger/15 text-danger'
            )}
          >
            {t(`scores.quadrant.${entry.quadrant}`)}
          </span>
        </div>
      ))}
    </div>
  )
}

function Recommendations() {
  const { t } = useTranslation()
  const courseId = useWorkspaceStore((state) => state.courseId)
  const recs = useQuery({
    queryKey: ['recommendations', courseId],
    queryFn: () => getRecommendations(courseId ?? undefined),
  })
  const list = recs.data ?? []
  if (recs.isLoading) {
    return <p className="text-muted-foreground text-sm">{t('library.loading')}</p>
  }
  if (list.length === 0) {
    return <p className="text-muted-foreground text-sm">{t('scores.noRecommendations')}</p>
  }
  return (
    <div className="space-y-2">
      {list.map((rec) => (
        <div
          key={`${rec.kind}-${rec.concept ?? 'any'}`}
          className="border-border flex items-center gap-3 rounded-lg border px-3 py-2.5"
        >
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">
              {t(`scores.rec.${rec.kind}`)}
              {rec.concept ? <span className="text-primary"> {rec.concept}</span> : null}
            </p>
            <p className="text-muted-foreground text-xs">
              {rec.kind === 'review' && rec.evidence.due_cards !== undefined
                ? t('today.evidenceReview', { count: rec.evidence.due_cards })
                : rec.evidence.misses !== undefined && rec.evidence.n !== undefined
                  ? t('today.evidenceWeak', {
                      misses: rec.evidence.misses,
                      n: rec.evidence.n,
                      skill: rec.skill ?? '',
                    })
                  : t('today.evidenceStale', { n: rec.evidence.n ?? 0 })}
            </p>
          </div>
          <Link
            to={
              rec.kind === 'review'
                ? '/courses'
                : rec.kind === 'drill' || rec.kind === 'challenge'
                  ? '/courses'
                  : '/library'
            }
            className="text-primary shrink-0 text-xs underline"
          >
            {t('scores.go')}
          </Link>
        </div>
      ))}
    </div>
  )
}

export function ScoresPage() {
  const { t } = useTranslation()
  const courseId = useWorkspaceStore((state) => state.courseId)
  const navigate = useNavigate()
  const from = useCurrentOrigin()
  const search = useSearch({ strict: false }) as { tab?: string }
  const raw = search.tab
  const tab: Tab = (TABS as readonly string[]).includes(raw ?? '')
    ? (raw as Tab)
    : 'history'
  const attempts = useQuery({
    queryKey: ['quiz-attempts', courseId],
    queryFn: () => listQuizAttempts(courseId ?? undefined),
  })
  const mistakes = useQuery({
    queryKey: ['mistakes', courseId],
    queryFn: () => listMistakes(courseId ?? undefined),
  })

  return (
    <WorkspaceGate>
      <div className="mx-auto max-w-3xl space-y-6 p-8">
      <h1 className="text-2xl font-semibold">{t('scores.title')}</h1>

      <div className="flex gap-1">
        {TABS.map((entry) => (
          <button
            key={entry}
            type="button"
            aria-current={tab === entry ? 'page' : undefined}
            onClick={() => void navigate({ to: '/scores', search: { tab: entry } })}
            className={cn(
              'rounded-md px-3 py-1.5 text-sm transition-colors',
              tab === entry
                ? 'bg-surface text-foreground font-medium shadow-sm'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {t(`scores.tab.${entry}`)}
          </button>
        ))}
      </div>

      {tab === 'history' ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <History className="size-4" aria-hidden />
              {t('scores.history')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {(attempts.data ?? []).map((attempt) => {
              const percent =
                attempt.score !== null ? Math.round(attempt.score * 100) : null
              return (
                <Link
                  key={attempt.id}
                  to="/quiz/$activityId"
                  params={{ activityId: String(attempt.activity_id) }}
                  search={{ from }}
                  className="hover:bg-subtle flex items-center gap-3 rounded-md px-2 py-2 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate">{attempt.title}</span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {new Date(attempt.started_at).toLocaleDateString()}
                  </span>
                  <span className="bg-subtle text-muted-foreground shrink-0 rounded-full px-2 py-0.5 text-[11px]">
                    {attempt.mode}
                  </span>
                  <span
                    className={cn(
                      'w-12 shrink-0 text-right font-medium',
                      percent === null
                        ? 'text-muted-foreground'
                        : percent >= 70
                          ? 'text-success'
                          : percent >= 40
                            ? 'text-warning'
                            : 'text-danger'
                    )}
                  >
                    {percent === null ? '—' : `${percent}%`}
                  </span>
                </Link>
              )
            })}
            {attempts.data && attempts.data.length === 0 ? (
              <EmptyState title={t('scores.emptyHistory')} />
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      {tab === 'diagnostics' ? (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Grid3x3 className="size-4" aria-hidden />
                {t('scores.weaknessMatrix')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <WeaknessMatrix />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t('scores.errorProfile')}</CardTitle>
            </CardHeader>
            <CardContent>
              <ErrorProfile />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t('scores.speedAccuracy')}</CardTitle>
            </CardHeader>
            <CardContent>
              <SpeedAccuracy />
            </CardContent>
          </Card>
        </div>
      ) : null}

      {tab === 'recommendations' ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Lightbulb className="size-4" aria-hidden />
              {t('scores.recommendations')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Recommendations />
          </CardContent>
        </Card>
      ) : null}

      {tab === 'mistakes' ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <BookX className="size-4" aria-hidden />
              {t('scores.mistakes')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {(mistakes.data ?? []).map((mistake) => (
              <div key={mistake.id} className="rounded-md px-2 py-2 text-sm">
                <p className="truncate">{mistake.stem_excerpt}</p>
                <p className="text-muted-foreground mt-0.5 flex items-center gap-2 text-xs">
                  <span className="truncate">{mistake.activity_title}</span>
                  {mistake.error_tags.map((tag) => (
                    <span
                      key={tag}
                      className="bg-danger/15 text-danger shrink-0 rounded-full px-2 py-0.5 text-[11px]"
                    >
                      {tag}
                    </span>
                  ))}
                </p>
              </div>
            ))}
            {mistakes.data && mistakes.data.length === 0 ? (
              <EmptyState title={t('scores.emptyMistakes')} />
            ) : null}
          </CardContent>
        </Card>
      ) : null}
      </div>
    </WorkspaceGate>
  )
}

import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { SegmentedTabs } from '@/components/ui/segmented-tabs'
import {
  getRetrievalOverview,
  getRetrievalQuality,
  getRetrievalQueryHealth,
  getRetrievalRuns,
  getRetrievalSpaces,
  getRetrievalUsage,
} from '@/lib/api'
import { getCurrentUser } from '@/lib/auth-session'

import {
  QualityDetailDrawer,
  RunDetailDrawer,
  SpaceDetailDrawer,
} from './RetrievalObservationDrawers'
import {
  ObservationFailures,
  ObservationOverview,
  ObservationQuality,
  ObservationQueryHealth,
  ObservationRuns,
  ObservationSpaces,
  ObservationUsage,
} from './RetrievalObservationSections'
import {
  OBSERVATION_SECTIONS,
  OBSERVATION_WINDOWS,
  collectFailureGroups,
  detailParam,
  observationSectionKey,
  observationWindowKey,
  parseObservationSection,
  parseObservationWindow,
  parseRetrievalDetail,
} from './retrievalObservation'
import type {
  ObservationSection,
  ObservationWindow,
  RetrievalDetail,
} from './retrievalObservation'

type SettingsSearch = {
  tab?: string
  section?: string
  obs?: string
  detail?: string
}

function RetrievalObservationPanelInner() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as SettingsSearch
  const [window, setWindow] = useState<ObservationWindow>('24h')

  const section = parseObservationSection(search.obs)
  const detail = parseRetrievalDetail(search.detail)
  const detailKind = detail?.kind ?? null
  const qualityDetailCandidate =
    detailKind === 'quality'
      ? detail?.id ?? null
      : detailKind === 'run' && section === 'quality'
        ? detail?.id ?? null
        : null

  const needsRuns = section === 'runs' || section === 'failures' || detailKind === 'run'
  const needsQuality =
    section === 'quality' ||
    section === 'failures' ||
    detailKind === 'quality' ||
    qualityDetailCandidate !== null
  const needsHealth = section === 'query-health' || section === 'failures'
  const needsUsage = section === 'usage' || section === 'overview'
  const needsSpaces =
    section === 'spaces' ||
    section === 'quality' ||
    section === 'failures' ||
    detailKind === 'space'

  const overview = useQuery({
    queryKey: ['retrieval-overview', window],
    queryFn: () => getRetrievalOverview(window),
    enabled: section === 'overview',
    retry: false,
    staleTime: 30_000,
  })
  const spaces = useQuery({
    queryKey: ['retrieval-spaces'],
    queryFn: getRetrievalSpaces,
    enabled: needsSpaces,
    retry: false,
    staleTime: 15_000,
  })
  const runs = useQuery({
    queryKey: ['retrieval-runs'],
    queryFn: getRetrievalRuns,
    enabled: needsRuns,
    retry: false,
    staleTime: 15_000,
  })
  const qualitySpaceId = qualityDetailCandidate ?? undefined
  const quality = useQuery({
    queryKey: ['retrieval-quality', qualitySpaceId ?? 'active'],
    queryFn: () => getRetrievalQuality(qualitySpaceId),
    enabled: needsQuality,
    retry: false,
    staleTime: 15_000,
  })
  const health = useQuery({
    queryKey: ['retrieval-query-health', window],
    queryFn: () => getRetrievalQueryHealth(window),
    enabled: needsHealth,
    retry: false,
    staleTime: 15_000,
  })
  const usage = useQuery({
    queryKey: ['retrieval-usage', window],
    queryFn: () => getRetrievalUsage(window),
    enabled: needsUsage,
    retry: false,
    staleTime: 30_000,
  })

  const go = (next: { section?: ObservationSection; detail?: string | null }) => {
    const nextSection = next.section ?? section
    const nextDetail =
      next.detail === undefined ? search.detail : next.detail
    const params: SettingsSearch = { tab: 'tools', section: 'indexing' }
    if (nextSection !== 'overview') params.obs = nextSection
    if (nextDetail) params.detail = nextDetail
    void navigate({ to: '/settings', search: params })
  }

  const openDetail = (next: RetrievalDetail) => go({ detail: detailParam(next) })
  const closeDetail = () => go({ detail: null })

  const isLoading =
    (section === 'overview' && overview.isLoading) ||
    (section === 'spaces' && spaces.isLoading) ||
    (section === 'quality' && (spaces.isLoading || quality.isLoading)) ||
    (section === 'runs' && runs.isLoading) ||
    (section === 'query-health' && health.isLoading) ||
    (section === 'usage' && usage.isLoading) ||
    (section === 'failures' &&
      (runs.isLoading || health.isLoading || spaces.isLoading || quality.isLoading))

  const isError =
    (section === 'overview' && overview.isError) ||
    (section === 'spaces' && spaces.isError) ||
    (section === 'runs' && runs.isError) ||
    (section === 'quality' && quality.isError) ||
    (section === 'query-health' && health.isError) ||
    (section === 'usage' && usage.isError) ||
    (section === 'failures' &&
      (runs.isError || health.isError || spaces.isError || quality.isError))

  const failureGroups = collectFailureGroups({
    runs: runs.data?.runs ?? [],
    spaces: spaces.data?.spaces ?? [],
    quality: quality.data ?? null,
    health: health.data ?? null,
  })

  const knownSpaceIds = new Set(
    (spaces.data?.spaces ?? []).map((entry) => entry.space_id)
  )
  const rawDetailId = detail?.id ?? null
  const spaceDetailId =
    detailKind === 'space'
      ? rawDetailId
      : detailKind === 'run' && section === 'spaces' && rawDetailId
        ? rawDetailId
        : null
  const qualityDetailId =
    detailKind === 'quality'
      ? rawDetailId
      : detailKind === 'run' &&
          section === 'quality' &&
          rawDetailId &&
          knownSpaceIds.has(rawDetailId)
        ? rawDetailId
        : null
  const runDetailId =
    detailKind === 'run' && spaceDetailId === null && qualityDetailId === null
      ? rawDetailId
      : null

  return (
    <Card id="retrieval-observation">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle className="text-sm">
              {t('settings.retrievalObsTitle')}
            </CardTitle>
            <CardDescription>
              {t('settings.retrievalObsDescription')}
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{t('settings.retrievalObsReadOnly')}</Badge>
            <a
              href="#retrieval-management"
              className="text-primary text-xs font-medium hover:underline"
            >
              {t('settings.retrievalObsManage')}
            </a>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0 max-w-full overflow-x-auto">
            <SegmentedTabs
              ariaLabel={t('settings.retrievalObsSectionsAria')}
              items={OBSERVATION_SECTIONS.map((item) => ({
                value: item,
                label: t(observationSectionKey(item) as never),
              }))}
              value={section}
              onValueChange={(next) =>
                go({ section: next as ObservationSection, detail: null })
              }
            />
          </div>
          <label className="text-muted-foreground flex items-center gap-2 text-xs">
            {t('settings.retrievalObsWindow')}
            <select
              aria-label={t('settings.retrievalObsWindow')}
              value={window}
              onChange={(event) =>
                setWindow(parseObservationWindow(event.target.value))
              }
              className="border-border bg-surface rounded-md border px-2 py-1 text-xs"
            >
              {OBSERVATION_WINDOWS.map((value) => (
                <option key={value} value={value}>
                  {t(observationWindowKey(value) as never)}
                </option>
              ))}
            </select>
          </label>
        </div>

        {isLoading ? (
          <span className="text-muted-foreground flex items-center gap-2 text-xs">
            <Loader2 className="animate-spin" aria-hidden />
            {t('settings.retrievalObsLoading')}
          </span>
        ) : null}
        {isError ? (
          <p role="alert" className="text-muted-foreground text-xs">
            {t('settings.retrievalObsUnavailable')}
          </p>
        ) : null}

        {section === 'overview' ? (
          <ObservationOverview overview={overview.data} usage={usage.data} />
        ) : null}
        {section === 'spaces' ? (
          <ObservationSpaces
            spaces={spaces.data}
            onOpenSpace={(spaceId) =>
              openDetail({ kind: 'space', id: spaceId })
            }
          />
        ) : null}
        {section === 'runs' ? (
          <ObservationRuns
            runs={runs.data}
            onOpenRun={(runId) => openDetail({ kind: 'run', id: runId })}
          />
        ) : null}
        {section === 'quality' ? (
          <ObservationQuality
            quality={quality.data}
            spaces={spaces.data}
            onOpenQuality={(spaceId) =>
              openDetail({ kind: 'quality', id: spaceId })
            }
          />
        ) : null}
        {section === 'query-health' ? (
          <ObservationQueryHealth data={health.data} />
        ) : null}
        {section === 'failures' ? (
          <ObservationFailures
            groups={failureGroups}
            onOpenRun={(runId) => openDetail({ kind: 'run', id: runId })}
          />
        ) : null}
        {section === 'usage' ? <ObservationUsage data={usage.data} /> : null}
      </CardContent>

      <RunDetailDrawer
        runId={runDetailId}
        loading={Boolean(runDetailId) && runs.isLoading}
        entry={
          runDetailId
            ? (runs.data?.runs ?? []).find(
                (entry) => entry.run.run_id === runDetailId
              ) ?? null
            : null
        }
        onClose={closeDetail}
      />
      <SpaceDetailDrawer
        spaceId={spaceDetailId}
        loading={Boolean(spaceDetailId) && spaces.isLoading}
        space={
          spaceDetailId
            ? (spaces.data?.spaces ?? []).find(
                (space) => space.space_id === spaceDetailId
              ) ?? null
            : null
        }
        onClose={closeDetail}
      />
      <QualityDetailDrawer
        spaceId={qualityDetailId}
        quality={qualityDetailId ? quality.data : undefined}
        loading={Boolean(qualityDetailId) && quality.isLoading}
        onClose={closeDetail}
      />
    </Card>
  )
}

/** Admin-only read surface; the wrapper keeps router hooks out of the
 * non-admin render path entirely. */
export function RetrievalObservationPanel() {
  const isAdmin = getCurrentUser()?.is_admin ?? false
  if (!isAdmin) return null
  return <RetrievalObservationPanelInner />
}

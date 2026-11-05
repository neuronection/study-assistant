import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import type {
  RetrievalOverview,
  RetrievalQuality,
  RetrievalQueryHealth,
  RetrievalRuns,
  RetrievalSpaces,
  RetrievalUsage,
} from '@/lib/api'

import {
  FAILURE_KIND_KEYS,
  FAILURE_REASON_KEYS,
  USAGE_KIND_KEYS,
  formatMs,
  formatNumber,
  formatPercent,
  formatRate,
  formatWhen,
  queryHealthReasons,
  queryHealthViews,
  runStatusKey,
  runTypeKey,
  shortId,
  spaceStatusKey,
  stateKey,
} from './retrievalObservation'
import type { FailureGroup } from './retrievalObservation'
import { RetrievalProgress, RetrievalTokenizerLabel } from './RetrievalProgress'

const TH_CLASS =
  'px-2 py-1.5 text-left text-[10px] font-medium uppercase tracking-wide text-muted-foreground'
const TD_CLASS = 'px-2 py-1.5 align-top text-xs'
const TABLE_SHELL =
  'overflow-x-auto rounded-md border border-border'

function StateNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="border-border bg-surface text-muted-foreground rounded-md border px-3 py-2 text-xs">
      {children}
    </p>
  )
}

function Tile({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="border-border bg-surface rounded-md border px-3 py-2">
      <dt className="text-muted-foreground text-[10px] uppercase tracking-wide">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium">{value}</dd>
      {hint ? <p className="text-muted-foreground mt-0.5 text-[11px]">{hint}</p> : null}
    </div>
  )
}

export function ObservationOverview({
  overview,
  usage,
}: {
  overview: RetrievalOverview | undefined
  usage: RetrievalUsage | undefined
}) {
  const { t } = useTranslation()
  if (!overview) {
    return <StateNote>{t('settings.retrievalObsUnavailable')}</StateNote>
  }
  const health = overview.query_health.health
  const space = overview.space
  const coverage = overview.coverage
  const calls = (usage?.rows ?? []).reduce((total, row) => total + row.calls, 0)
  const tokensIn = (usage?.rows ?? []).reduce(
    (total, row) => total + (row.tokens_in ?? 0),
    0
  )
  const tokensRecorded = usage?.tokens_available ?? false

  return (
    <div className="space-y-3" data-testid="retrieval-observation-overview">
      <div className="flex flex-wrap items-center gap-2">
        <Badge
          variant={
            overview.state === 'ready'
              ? 'success'
              : overview.state === 'degraded'
                ? 'danger'
                : 'secondary'
          }
        >
          {t(`settings.${stateKey(overview.state)}`)}
        </Badge>
        <span className="text-muted-foreground text-xs">
          {overview.backend_label ?? t('settings.retrievalBackendUnknown')}
        </span>
        {coverage.as_of === null ? (
          <Badge variant="warning">{t('settings.retrievalStateCold')}</Badge>
        ) : null}
      </div>

      <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label={t('settings.retrievalObsActiveSpace')}
          value={space ? space.name : t('settings.retrievalObsNoSpace')}
          hint={
            space
              ? t('settings.retrievalObsModelDim', {
                  model: space.model,
                  dim: space.dim,
                })
              : undefined
          }
        />
        <Tile
          label={t('settings.retrievalObsCoverage')}
          value={
            coverage.coverage === null
              ? t('settings.retrievalObsCoverageCold')
              : formatPercent(coverage.coverage)
          }
          hint={
            space
              ? t('settings.retrievalObsCounts', {
                  documents: space.documents,
                  records: space.records,
                })
              : undefined
          }
        />
        <Tile
          label={t('settings.retrievalObsP50')}
          value={formatMs(health.p50_ms)}
          hint={t('settings.retrievalObsQueries', {
            count: formatNumber(health.query_count),
          })}
        />
        <Tile label={t('settings.retrievalObsP95')} value={formatMs(health.p95_ms)} />
        <Tile
          label={t('settings.retrievalObsDegraded')}
          value={formatRate(health.degraded_rate)}
        />
        <Tile
          label={t('settings.retrievalObsZeroResult')}
          value={formatRate(health.zero_result_rate)}
        />
        <Tile
          label={t('settings.retrievalObsEmbedCalls')}
          value={formatNumber(usage ? calls : undefined)}
        />
        <Tile
          label={t('settings.retrievalObsEmbedTokens')}
          value={
            tokensRecorded ? formatNumber(tokensIn) : t('settings.retrievalObsNotRecorded')
          }
        />
      </dl>

      {coverage.as_of === null ? (
        <StateNote>{t('settings.retrievalObsCoverageColdHint')}</StateNote>
      ) : null}
      {(overview.notes ?? []).length > 0 ? (
        <ul className="text-muted-foreground space-y-1 text-[11px]">
          {(overview.notes ?? []).map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

export function ObservationSpaces({
  spaces,
  onOpenSpace,
}: {
  spaces: RetrievalSpaces | undefined
  onOpenSpace: (spaceId: string) => void
}) {
  const { t } = useTranslation()
  const rows = spaces?.spaces ?? []
  if (rows.length === 0) {
    return (
      <div className="space-y-2" data-testid="retrieval-observation-spaces-empty">
        <StateNote>{t('settings.retrievalObsSpacesEmpty')}</StateNote>
      </div>
    )
  }

  return (
    <div className="space-y-2" data-testid="retrieval-observation-spaces">
      <p className="text-muted-foreground text-[11px]">
        {t('settings.retrievalObsSpacesHint')}
      </p>
      <div className={TABLE_SHELL}>
        <table className="w-full">
          <thead className="border-border border-b">
            <tr>
              <th className={TH_CLASS}>{t('settings.retrievalObsSpaceName')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsSpaceStatus')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsModel')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsCoverage')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsSpaceQuality')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsSpaceLastReindex')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((space) => {
              const active = space.space_id === spaces?.active_space_id
              return (
                <tr
                  key={space.space_id}
                  className="border-border hover:bg-surface cursor-pointer border-b last:border-0"
                  onClick={() => onOpenSpace(space.space_id)}
                  data-testid={`retrieval-observation-space-${space.space_id}`}
                >
                  <td className={TD_CLASS}>
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">{space.name}</span>
                      {active ? <Badge variant="success">{t('settings.retrievalSpaceActiveLabel')}</Badge> : null}
                    </span>
                    <span className="text-muted-foreground block font-mono text-[10px]">
                      {space.space_id}
                    </span>
                  </td>
                  <td className={TD_CLASS}>
                    {t(`settings.${spaceStatusKey(space.status)}` as const)}
                  </td>
                  <td className={TD_CLASS}>
                    {space.model}
                    <span className="text-muted-foreground block">
                      {t('settings.retrievalObsModelDim', {
                        model: space.backend,
                        dim: space.dim,
                      })}
                    </span>
                    <RetrievalTokenizerLabel
                      tokenAware={space.token_aware}
                      tokenizer={space.tokenizer}
                      chunk={space.chunk}
                      compact
                    />
                  </td>
                  <td className={TD_CLASS}>
                    {space.coverage === null || space.coverage === undefined
                      ? t('settings.retrievalObsNever')
                      : formatPercent(space.coverage)}
                  </td>
                  <td className={TD_CLASS}>
                    {space.quality_state ?? 'not_sampled'} · {space.quality_gate ?? 'unknown'}
                  </td>
                  <td className={TD_CLASS}>
                    {space.last_reindex_at
                      ? formatWhen(space.last_reindex_at)
                      : t('settings.retrievalObsNever')}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ObservationRuns({
  runs,
  onOpenRun,
}: {
  runs: RetrievalRuns | undefined
  onOpenRun: (runId: string) => void
}) {
  const { t } = useTranslation()
  const rows = runs?.runs ?? []
  if (rows.length === 0) {
    return (
      <div data-testid="retrieval-observation-runs-empty">
        <StateNote>{t('settings.retrievalObsRunsEmpty')}</StateNote>
      </div>
    )
  }
  return (
    <div className="space-y-2" data-testid="retrieval-observation-runs">
      <p className="text-muted-foreground text-[11px]">
        {t('settings.retrievalObsRunsHint')}
      </p>
      <div className={TABLE_SHELL}>
        <table className="w-full">
          <thead className="border-border border-b">
            <tr>
              <th className={TH_CLASS}>{t('settings.retrievalObsRun')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsSpaceName')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsRunStatus')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsRunScannedEmbeddedFailed')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsRunStarted')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((entry) => {
              const result = entry.result
              return (
                <tr
                  key={entry.run.run_id}
                  className="border-border hover:bg-surface cursor-pointer border-b last:border-0"
                  onClick={() => onOpenRun(entry.run.run_id)}
                  data-testid={`retrieval-observation-run-${entry.run.run_id}`}
                >
                  <td className={TD_CLASS}>
                    <span className="font-medium">{t(`settings.${runTypeKey(entry.run.job_type)}`)}</span>
                    <span className="text-muted-foreground block font-mono text-[10px]">
                      {shortId(entry.run.run_id)}
                    </span>
                  </td>
                  <td className={TD_CLASS}>{entry.run.space_id}</td>
                  <td className={TD_CLASS}>
                    {t(`settings.${runStatusKey(entry.run.status)}`)}
                    {entry.run.status === 'running' ? ` · ${entry.run.progress}%` : ''}
                    {entry.run.progress_detail ? (
                      <RetrievalProgress
                        detail={entry.run.progress_detail}
                        compact
                        testId={`retrieval-observation-progress-${entry.run.run_id}`}
                      />
                    ) : null}
                  </td>
                  <td className={TD_CLASS}>
                    {result
                      ? `${result.scanned} / ${result.embedded} / ${result.failed}`
                      : '—'}
                  </td>
                  <td className={TD_CLASS}>
                    {formatWhen(entry.run.started_at ?? entry.run.created_at)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ObservationQuality({
  quality,
  spaces,
  onOpenQuality,
}: {
  quality: RetrievalQuality | undefined
  spaces: RetrievalSpaces | undefined
  onOpenQuality: (spaceId: string) => void
}) {
  const { t } = useTranslation()
  const rows = spaces?.spaces ?? []
  return (
    <div className="space-y-3" data-testid="retrieval-observation-quality">
      <p className="text-muted-foreground text-[11px]">
        {t('settings.retrievalObsQualityHint')}
      </p>
      {quality ? (
        <div className="space-y-1 text-xs" data-testid="retrieval-observation-quality-summary">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={quality.activation_gate === 'pass' ? 'success' : quality.activation_gate === 'fail' ? 'danger' : 'secondary'}>
              {t('settings.retrievalQualityGate', { state: quality.activation_gate })}
            </Badge>
            <span className="text-muted-foreground">{quality.name || quality.space_id}</span>
          </div>
          {quality.set ? (
            <p className="text-muted-foreground">
              {t('settings.retrievalQualitySet', {
                version: quality.set.set_version,
                k: quality.set.k,
                count: quality.set.query_count,
              })}
            </p>
          ) : (
            <p className="text-warning">{t('settings.retrievalQualityStateNoSet')}</p>
          )}
          {quality.quality ? (
            <p className={quality.quality.passed ? 'text-success' : 'text-destructive'}>
              {t('settings.retrievalObsQualityScores', {
                recall: formatPercent(quality.quality.recall_at_k),
                precision: formatPercent(quality.quality.precision_at_k),
                recallFloor: formatPercent(quality.quality.floor_recall),
                precisionFloor: formatPercent(quality.quality.floor_precision),
              })}
            </p>
          ) : (
            <p className="text-muted-foreground">
              {quality.state === 'stale_compare'
                ? t('settings.retrievalQualityStateStale')
                : t('settings.retrievalQualityStateNotSampled')}
            </p>
          )}
        </div>
      ) : (
        <StateNote>{t('settings.retrievalObsQualityEmpty')}</StateNote>
      )}

      {rows.length > 0 ? (
        <div className={TABLE_SHELL}>
          <table className="w-full">
            <thead className="border-border border-b">
              <tr>
                <th className={TH_CLASS}>{t('settings.retrievalObsSpaceName')}</th>
                <th className={TH_CLASS}>{t('settings.retrievalObsQualityState')}</th>
                <th className={TH_CLASS}>{t('settings.retrievalObsQualityGate')}</th>
                <th className={TH_CLASS}>{t('settings.retrievalObsQualityBadMatches')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((space) => (
                <tr key={space.space_id} className="border-border border-b last:border-0">
                  <td className={TD_CLASS}>
                    <span className="font-medium">{space.name}</span>
                  </td>
                  <td className={TD_CLASS}>{space.quality_state ?? 'not_sampled'}</td>
                  <td className={TD_CLASS}>{space.quality_gate ?? 'unknown'}</td>
                  <td className={TD_CLASS}>
                    <button
                      type="button"
                      className="text-primary text-xs font-medium hover:underline"
                      onClick={() => onOpenQuality(space.space_id)}
                    >
                      {t('settings.retrievalObsQualityOpen')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}

export function ObservationQueryHealth({
  data,
}: {
  data: RetrievalQueryHealth | undefined
}) {
  const { t } = useTranslation()
  const health = data?.health
  const reasons = queryHealthReasons(health)
  const views = queryHealthViews(health)

  if (!health || data.query_count === 0) {
    return (
      <div data-testid="retrieval-observation-query-empty">
        <StateNote>{t('settings.retrievalObsQueryEmpty')}</StateNote>
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid="retrieval-observation-query-health">
      <p className="text-muted-foreground text-[11px]">
        {t('settings.retrievalObsQueryHint')}
      </p>
      <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <Tile
          label={t('settings.retrievalObsP50')}
          value={formatMs(health.p50_ms)}
          hint={t('settings.retrievalObsQueries', {
            count: formatNumber(data.query_count),
          })}
        />
        <Tile label={t('settings.retrievalObsP95')} value={formatMs(health.p95_ms)} />
        <Tile
          label={t('settings.retrievalObsCandidates')}
          value={
            data.candidates_avg === null || data.candidates_avg === undefined
              ? '—'
              : data.candidates_avg.toFixed(2)
          }
        />
        <Tile
          label={t('settings.retrievalObsZeroResult')}
          value={formatRate(health.zero_result_rate)}
        />
        <Tile
          label={t('settings.retrievalObsDegraded')}
          value={formatRate(health.degraded_rate)}
        />
        <Tile
          label={t('settings.retrievalObsAnnRecall')}
          value={health.sampled ? formatRate(health.ann_recall) : t('settings.retrievalObsAnnNotSampled')}
          hint={
            health.sampled
              ? t('settings.retrievalObsAnnSampled', {
                  k: health.ann_recall_k ?? 0,
                  probes: health.probe_size ?? 0,
                })
              : undefined
          }
        />
      </dl>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="border-border rounded-md border p-3">
          <h3 className="text-muted-foreground mb-1 text-[10px] uppercase tracking-wide">
            {t('settings.retrievalObsDegradedReasons')}
          </h3>
          {reasons.length === 0 ? (
            <p className="text-muted-foreground text-xs">
              {t('settings.retrievalObsNoDegradedReasons')}
            </p>
          ) : (
            <ul className="space-y-1 text-xs">
              {reasons.map(([reason, count]) => (
                <li key={reason} className="flex items-center justify-between gap-2">
                  <code className="font-mono text-[11px]">{reason}</code>
                  <span>{formatNumber(count)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="border-border rounded-md border p-3">
          <h3 className="text-muted-foreground mb-1 text-[10px] uppercase tracking-wide">
            {t('settings.retrievalObsViewHits')}
          </h3>
          {views.length === 0 ? (
            <p className="text-muted-foreground text-xs">
              {t('settings.retrievalObsNoViewHits')}
            </p>
          ) : (
            <ul className="space-y-1 text-xs">
              {views.map(([view, count]) => (
                <li key={view} className="flex items-center justify-between gap-2">
                  <span>{view}</span>
                  <span>{formatNumber(count)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

export function ObservationFailures({
  groups,
  onOpenRun,
}: {
  groups: FailureGroup[]
  onOpenRun: (runId: string) => void
}) {
  const { t } = useTranslation()
  if (groups.length === 0) {
    return (
      <div data-testid="retrieval-observation-failures-empty">
        <StateNote>{t('settings.retrievalObsFailuresEmpty')}</StateNote>
      </div>
    )
  }
  return (
    <div className="space-y-2" data-testid="retrieval-observation-failures">
      <p className="text-muted-foreground text-[11px]">
        {t('settings.retrievalObsFailuresHint')}
      </p>
      <ul className="space-y-2">
        {groups.map((group) => (
          <li
            key={group.id}
            className="border-border rounded-md border px-3 py-2 text-xs"
            data-testid={`retrieval-observation-failure-${group.id}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {t(`settings.${FAILURE_KIND_KEYS[group.kind]}`)}
              </span>
              <Badge variant="danger">
                {t('settings.retrievalObsFailureCount', {
                  count: formatNumber(group.count),
                })}
              </Badge>
              <Badge variant="secondary">
                {t(`settings.${FAILURE_REASON_KEYS[group.reason] ?? 'retrievalObsReasonUnknown'}`)}
              </Badge>
              {group.retryable ? (
                <Badge variant="warning">{t('settings.retrievalObsFailureRetryable')}</Badge>
              ) : null}
            </div>
            <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-3">
              <span>
                {t('settings.retrievalObsFailureSpace')}: {group.spaceId}
              </span>
              {group.lastSeen ? (
                <span>
                  {t('settings.retrievalObsFailureLastSeen', {
                    when: formatWhen(group.lastSeen),
                  })}
                </span>
              ) : null}
              {group.runId ? (
                <button
                  type="button"
                  className="text-primary font-medium hover:underline"
                  onClick={() => onOpenRun(group.runId!)}
                >
                  {t('settings.retrievalObsFailureOpenRun')}
                </button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function ObservationUsage({ data }: { data: RetrievalUsage | undefined }) {
  const { t } = useTranslation()
  if (!data || (data.rows ?? []).length === 0) {
    return (
      <div data-testid="retrieval-observation-usage-empty">
        <StateNote>{t('settings.retrievalObsUsageEmpty')}</StateNote>
      </div>
    )
  }
  return (
    <div className="space-y-2" data-testid="retrieval-observation-usage">
      <p className="text-muted-foreground text-[11px]">
        {t('settings.retrievalObsUsageHint')}
      </p>
      <div className={TABLE_SHELL}>
        <table className="w-full">
          <thead className="border-border border-b">
            <tr>
              <th className={TH_CLASS}>{t('settings.retrievalObsUsageDay')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsUsageSpace')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsUsageKind')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsUsageCalls')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsUsageReindex')}</th>
              <th className={TH_CLASS}>{t('settings.retrievalObsUsageTokens')}</th>
            </tr>
          </thead>
          <tbody>
            {(data.rows ?? []).map((row) => (
              <tr
                key={`${row.day}-${row.space_id}-${row.kind}`}
                className="border-border border-b last:border-0"
              >
                <td className={TD_CLASS}>{row.day}</td>
                <td className={TD_CLASS}>{row.space_id}</td>
                <td className={TD_CLASS}>
                  {t(`settings.${USAGE_KIND_KEYS[row.kind] ?? 'retrievalObsKindUnknown'}`)}
                </td>
                <td className={`${TD_CLASS} tabular-nums`}>{formatNumber(row.calls)}</td>
                <td className={`${TD_CLASS} tabular-nums`}>
                  {formatNumber(row.reindex_calls)}
                </td>
                <td className={`${TD_CLASS} tabular-nums`}>
                  {data.tokens_available
                    ? `${formatNumber(row.tokens_in)} / ${formatNumber(row.tokens_out)}`
                    : t('settings.retrievalObsNotRecorded')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(data.notes ?? []).length > 0 ? (
        <div>
          <h3 className="text-muted-foreground mb-1 text-[10px] uppercase tracking-wide">
            {t('settings.retrievalObsUsageNotes')}
          </h3>
          <ul className="text-muted-foreground space-y-1 text-[11px]">
            {(data.notes ?? []).map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

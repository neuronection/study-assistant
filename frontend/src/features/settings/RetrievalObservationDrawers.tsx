import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { PanelModal } from '@/components/ui/modal'
import type {
  RetrievalQuality,
  RetrievalRuns,
  RetrievalSpaces,
} from '@/lib/api'

import {
  formatNumber,
  formatPercent,
  formatWhen,
  runStatusKey,
  runTypeKey,
  spaceStatusKey,
} from './retrievalObservation'
import { RetrievalProgress, RetrievalTokenizerLabel } from './RetrievalProgress'

type RunEntry = NonNullable<RetrievalRuns['runs']>[number]
type SpaceEntry = NonNullable<RetrievalSpaces['spaces']>[number]

const FAILED_ID_LIMIT = 100

function MetaRow({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-xs">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words text-right font-medium">{children}</dd>
    </div>
  )
}

export function RunDetailDrawer({
  runId,
  loading,
  entry,
  onClose,
}: {
  runId: string | null
  loading: boolean
  entry: RunEntry | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  const run = entry?.run ?? null
  const result = entry?.result ?? null
  const failedIds = result?.failed_ids ?? []
  const shownIds = failedIds.slice(0, FAILED_ID_LIMIT)
  const truncated = Boolean(result?.failed_ids_truncated) || failedIds.length > FAILED_ID_LIMIT

  return (
    <PanelModal
      open={runId !== null}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      size="lg"
      title={t('settings.retrievalObsRunDrawerTitle')}
      data-testid="retrieval-observation-run-drawer"
    >
      {loading ? (
        <p className="text-muted-foreground text-sm">
          {t('settings.retrievalObsLoading')}
        </p>
      ) : !run ? (
        <p className="text-muted-foreground text-sm">
          {t('settings.retrievalObsDetailNotFound')}
        </p>
      ) : (
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={
                run.status === 'succeeded'
                  ? 'success'
                  : run.status === 'failed'
                    ? 'danger'
                    : 'secondary'
              }
            >
              {t(`settings.${runStatusKey(run.status)}`)}
            </Badge>
            <span className="text-muted-foreground text-xs">
              {t(`settings.${runTypeKey(run.job_type)}`)}
            </span>
            <span className="text-muted-foreground font-mono text-[11px]">
              {run.run_id}
            </span>
            {run.cancel_requested ? (
              <Badge variant="warning">{t('settings.retrievalObsRunCancelRequested')}</Badge>
            ) : null}
          </div>

          <dl className="space-y-1">
            <MetaRow label={t('settings.retrievalObsSpaceName')}>{run.space_id}</MetaRow>
            <MetaRow label={t('settings.retrievalObsRunStatus')}>
              {t(`settings.${runStatusKey(run.status)}`)}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsRunStage')}>
              {run.stage ?? '—'}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsRunProgress')}>{run.progress ?? 0}%</MetaRow>
            <MetaRow label={t('settings.retrievalObsRunScope')}>
              {[
                run.scope?.kind,
                run.scope?.view,
                run.scope?.since
                  ? `${t('settings.retrievalObsRunSince')} ${run.scope.since}`
                  : null,
              ]
                .filter(Boolean)
                .join(' · ') || '—'}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsRunGate')}>
              {result?.gate ?? '—'}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsRunStarted')}>
              {formatWhen(run.started_at ?? run.created_at)}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsRunFinished')}>
              {formatWhen(run.finished_at)}
            </MetaRow>
          </dl>

          <div className="border-border rounded-md border px-3 py-2">
            <h3 className="text-muted-foreground mb-1 text-[10px] uppercase tracking-wide">
              {t('settings.retrievalObsRunLiveProgress')}
            </h3>
            <RetrievalProgress
              detail={run.progress_detail}
              testId="retrieval-observation-run-progress"
            />
          </div>

          <div className="border-border rounded-md border px-3 py-2">
            <h3 className="text-muted-foreground mb-1 text-[10px] uppercase tracking-wide">
              {t('settings.retrievalObsRunTokenizer')}
            </h3>
            <RetrievalTokenizerLabel
              tokenAware={run.token_aware}
              tokenizer={run.tokenizer}
              chunk={run.chunk}
            />
          </div>

          <div className="border-border rounded-md border px-3 py-2">
            <h3 className="text-muted-foreground mb-1 text-[10px] uppercase tracking-wide">
              {t('settings.retrievalObsRunResult')}
            </h3>
            {result ? (
              <p className="text-xs">
                {t('settings.retrievalObsRunCounters', {
                  scanned: formatNumber(result.scanned),
                  embedded: formatNumber(result.embedded),
                  skipped: formatNumber(result.skipped),
                  failed: formatNumber(result.failed),
                })}
              </p>
            ) : (
              <p className="text-muted-foreground text-xs">
                {t('settings.retrievalObsRunNoResult')}
              </p>
            )}
          </div>

          <div>
            <h3 className="text-muted-foreground mb-1 text-[10px] uppercase tracking-wide">
              {t('settings.retrievalObsRunFailedIds', { count: failedIds.length })}
            </h3>
            {shownIds.length === 0 ? (
              <p className="text-muted-foreground text-xs">
                {t('settings.retrievalObsRunFailedIdsNone')}
              </p>
            ) : (
              <ul className="flex max-h-40 flex-wrap gap-1 overflow-y-auto">
                {shownIds.map((id: string) => (
                  <li
                    key={id}
                    className="bg-surface rounded px-2 py-0.5 font-mono text-[11px]"
                  >
                    {id}
                  </li>
                ))}
              </ul>
            )}
            {truncated ? (
              <p className="text-muted-foreground mt-1 text-[11px]">
                {t('settings.retrievalObsRunTruncated')}
              </p>
            ) : null}
          </div>
          <p className="text-muted-foreground text-[11px]">
            {t('settings.retrievalObsRunReadOnly')}
          </p>
        </div>
      )}
    </PanelModal>
  )
}

export function SpaceDetailDrawer({
  spaceId,
  loading,
  space,
  onClose,
}: {
  spaceId: string | null
  loading: boolean
  space: SpaceEntry | null
  onClose: () => void
}) {
  const { t } = useTranslation()
  return (
    <PanelModal
      open={spaceId !== null}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      size="lg"
      title={t('settings.retrievalObsSpaceDrawerTitle')}
      data-testid="retrieval-observation-space-drawer"
    >
      {loading ? (
        <p className="text-muted-foreground text-sm">
          {t('settings.retrievalObsLoading')}
        </p>
      ) : !space ? (
        <p className="text-muted-foreground text-sm">
          {t('settings.retrievalObsDetailNotFound')}
        </p>
      ) : (
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={
                space.status === 'active'
                  ? 'success'
                  : space.status === 'retired'
                    ? 'danger'
                    : 'warning'
              }
            >
              {t(`settings.${spaceStatusKey(space.status)}` as const)}
            </Badge>
            <span className="font-medium">{space.name}</span>
            <span className="text-muted-foreground font-mono text-[11px]">
              {space.space_id}
            </span>
          </div>
          <dl className="space-y-1">
            <MetaRow label={t('settings.retrievalObsModel')}>{space.model}</MetaRow>
            <MetaRow label={t('settings.retrievalObsDim')}>{space.dim}</MetaRow>
            <MetaRow label={t('settings.retrievalObsBackend')}>{space.backend}</MetaRow>
            <MetaRow label={t('settings.retrievalObsSpaceTable')}>
              {space.index_table ?? '—'}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsSpaceDocs')}>
              {formatNumber(space.documents)} / {formatNumber(space.records)}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsCoverage')}>
              {space.coverage === null || space.coverage === undefined
                ? t('settings.retrievalObsNever')
                : formatPercent(space.coverage)}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsSpaceGate')}>{space.gate}</MetaRow>
            <MetaRow label={t('settings.retrievalObsSpaceQuality')}>
              {space.quality_state ?? 'not_sampled'} · {space.quality_gate ?? 'unknown'}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsSpaceFailed')}>
              {formatNumber(space.failed)}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsSpaceLastReindex')}>
              {space.last_reindex_at ? formatWhen(space.last_reindex_at) : t('settings.retrievalObsNever')}
            </MetaRow>
            <MetaRow label={t('settings.retrievalObsSpaceAsOf')}>
              {space.as_of ? formatWhen(space.as_of) : t('settings.retrievalObsNever')}
            </MetaRow>
          </dl>
          <div className="border-border rounded-md border px-3 py-2">
            <h3 className="text-muted-foreground mb-1 text-[10px] uppercase tracking-wide">
              {t('settings.retrievalObsRunTokenizer')}
            </h3>
            <RetrievalTokenizerLabel
              tokenAware={space.token_aware}
              tokenizer={space.tokenizer}
              chunk={space.chunk}
            />
          </div>
          <p className="text-muted-foreground text-[11px]">
            {t('settings.retrievalObsSpaceReadOnly')}
          </p>
        </div>
      )}
    </PanelModal>
  )
}

export function QualityDetailDrawer({
  spaceId,
  quality,
  loading,
  onClose,
}: {
  spaceId: string | null
  quality: RetrievalQuality | undefined
  loading: boolean
  onClose: () => void
}) {
  const { t } = useTranslation()
  const badMatches = quality?.bad_matches ?? []
  return (
    <PanelModal
      open={spaceId !== null}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      size="lg"
      title={t('settings.retrievalObsQualityDrawerTitle')}
      data-testid="retrieval-observation-quality-drawer"
    >
      {loading ? (
        <p className="text-muted-foreground text-sm">
          {t('settings.retrievalQualityLoading')}
        </p>
      ) : !quality ? (
        <p className="text-muted-foreground text-sm">
          {t('settings.retrievalObsDetailNotFound')}
        </p>
      ) : (
        <div className="space-y-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{quality.name || quality.space_id}</span>
            <Badge
              variant={
                quality.activation_gate === 'pass'
                  ? 'success'
                  : quality.activation_gate === 'fail'
                    ? 'danger'
                    : 'secondary'
              }
            >
              {t('settings.retrievalObsQualityGateValue', {
                state: quality.activation_gate,
              })}
            </Badge>
            <span className="text-muted-foreground text-xs">{quality.state}</span>
          </div>

          {quality.set ? (
            <p className="text-muted-foreground text-xs">
              {t('settings.retrievalQualitySet', {
                version: quality.set.set_version,
                k: quality.set.k,
                count: quality.set.query_count,
              })}
            </p>
          ) : (
            <p className="text-warning text-xs">
              {t('settings.retrievalQualityStateNoSet')}
            </p>
          )}

          {quality.quality ? (
            <p
              className={`text-xs ${quality.quality.passed ? 'text-success' : 'text-destructive'}`}
            >
              {t('settings.retrievalObsQualityScores', {
                recall: formatPercent(quality.quality.recall_at_k),
                precision: formatPercent(quality.quality.precision_at_k),
                recallFloor: formatPercent(quality.quality.floor_recall),
                precisionFloor: formatPercent(quality.quality.floor_precision),
              })}
            </p>
          ) : null}

          {quality.compare ? (
            <p className="text-muted-foreground text-xs">
              {t('settings.retrievalQualityCompareScores', {
                oldRecall: formatPercent(quality.compare.old_recall_at_k),
                newRecall: formatPercent(quality.compare.new_recall_at_k),
                oldPrecision: formatPercent(quality.compare.old_precision_at_k),
                newPrecision: formatPercent(quality.compare.new_precision_at_k),
              })}
            </p>
          ) : null}

          <div>
            <h3 className="text-muted-foreground mb-1 text-[10px] uppercase tracking-wide">
              {t('settings.retrievalObsQualityBadMatches')}
            </h3>
            {badMatches.length === 0 ? (
              <p className="text-muted-foreground text-xs">
                {t('settings.retrievalObsQualityNoBad')}
              </p>
            ) : (
              <ul className="space-y-2">
                {badMatches.map((entry) => (
                  <li
                    key={entry.query_id}
                    className="border-border rounded-md border px-2 py-1.5"
                  >
                    <p className="text-xs font-medium">{entry.query_id}</p>
                    <p className="text-muted-foreground text-[11px]">
                      {t('settings.retrievalObsQualityMissing', {
                        ids: (entry.missing_document_ids ?? []).join(', ') || '—',
                      })}
                    </p>
                    <ul className="text-muted-foreground font-mono text-[11px]">
                      {(entry.hits ?? []).slice(0, 5).map((hit) => (
                        <li key={`${entry.query_id}-${String(hit.chunk_id)}`}>
                          {t('settings.retrievalQualityHit', {
                            chunk: String(hit.chunk_id ?? '—'),
                            doc: String(hit.document_id ?? '—'),
                            view: String(hit.view ?? '—'),
                            score:
                              typeof hit.score === 'number'
                                ? hit.score.toFixed(3)
                                : '—',
                          })}
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="text-muted-foreground text-[11px]">
            {t('settings.retrievalObsQualityReadOnly')}
          </p>
        </div>
      )}
    </PanelModal>
  )
}

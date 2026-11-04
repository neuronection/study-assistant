import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  activateRetrievalSpace,
  cancelRetrievalRun,
  dropRetrievalSpace,
  getRetrievalOverview,
  getRetrievalRuns,
  getRetrievalSpaces,
  postRetrievalBuildSpace,
  postRetrievalCutover,
  postRetrievalMaintenance,
  postRetrievalReindex,
  retireRetrievalSpace,
  retryRetrievalRun,
} from '@/lib/api'
import type {
  RetrievalAction,
  RetrievalMaintenanceRequest,
  RetrievalOverview,
  RetrievalSpaces,
} from '@/lib/api'
import { getCurrentUser } from '@/lib/auth-session'

type MaintenanceAction = NonNullable<RetrievalMaintenanceRequest['action']>

const MAINTENANCE_ACTIONS: MaintenanceAction[] = [
  'orphan-sweep',
  'vacuum',
  'index-rebuild',
  'retry-failed',
]

function stateKey(state: string) {
  if (state === 'ready') return 'retrievalStateReady'
  if (state === 'degraded') return 'retrievalStateDegraded'
  if (state === 'cold') return 'retrievalStateCold'
  return 'retrievalStateEmpty'
}

function runStatusKey(status: string | null | undefined) {
  if (status === 'running') return 'retrievalRunRunning'
  if (status === 'succeeded') return 'retrievalRunSucceeded'
  if (status === 'failed') return 'retrievalRunFailed'
  if (status === 'cancelled') return 'retrievalRunCancelled'
  return 'retrievalRunQueued'
}

function runTypeKey(jobType: string) {
  if (jobType === 'VECTOR_MAINTENANCE') return 'retrievalRunTypeMaintenance'
  if (jobType === 'VECTOR_CUTOVER') return 'retrievalRunTypeCutover'
  return 'retrievalRunTypeReindex'
}

function maintenanceKey(action: MaintenanceAction) {
  if (action === 'vacuum') return 'retrievalMaintenanceVacuum'
  if (action === 'index-rebuild') return 'retrievalMaintenanceIndexRebuild'
  if (action === 'retry-failed') return 'retrievalMaintenanceRetryFailed'
  return 'retrievalMaintenanceOrphanSweep'
}

function newIdempotencyKey() {
  const cryptoApi = globalThis.crypto
  if (typeof cryptoApi?.randomUUID === 'function') {
    return cryptoApi.randomUUID()
  }
  return `retrieval-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function RetrievalStatusCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const isAdmin = getCurrentUser()?.is_admin ?? false
  const [notice, setNotice] = useState<string | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [maintenanceAction, setMaintenanceAction] =
    useState<MaintenanceAction>('orphan-sweep')
  const [dryRun, setDryRun] = useState(false)
  const [candidateName, setCandidateName] = useState('content-candidate')
  const [confirmations, setConfirmations] = useState<Record<string, string>>({})

  const overview = useQuery({
    queryKey: ['retrieval-overview'],
    queryFn: getRetrievalOverview,
    enabled: isAdmin,
    retry: false,
    staleTime: 30_000,
  })
  const runsQuery = useQuery({
    queryKey: ['retrieval-runs'],
    queryFn: getRetrievalRuns,
    enabled: isAdmin,
    retry: false,
    staleTime: 15_000,
  })
  const spacesQuery = useQuery({
    queryKey: ['retrieval-spaces'],
    queryFn: getRetrievalSpaces,
    enabled: isAdmin,
    retry: false,
    staleTime: 15_000,
  })

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['retrieval-overview'] })
    void queryClient.invalidateQueries({ queryKey: ['retrieval-runs'] })
    void queryClient.invalidateQueries({ queryKey: ['retrieval-spaces'] })
  }
  const accepted = (data: RetrievalAction) => {
    setProblem(null)
    setNotice(
      data.deduplicated
        ? t('settings.retrievalActionDedup')
        : t('settings.retrievalActionQueued')
    )
    refresh()
  }
  const refused = (error: unknown) => {
    setNotice(null)
    setProblem(
      error instanceof Error && error.message
        ? error.message
        : t('settings.retrievalActionFailed')
    )
  }

  const reindex = useMutation({
    mutationFn: (force: boolean) =>
      postRetrievalReindex(
        { force, limit: 500, batch_size: 32 },
        newIdempotencyKey()
      ),
    onSuccess: accepted,
    onError: refused,
  })
  const cancel = useMutation({
    mutationFn: (runId: string) => cancelRetrievalRun(runId),
    onSuccess: accepted,
    onError: refused,
  })
  const retry = useMutation({
    mutationFn: (runId: string) => retryRetrievalRun(runId, newIdempotencyKey()),
    onSuccess: accepted,
    onError: refused,
  })
  const maintenance = useMutation({
    mutationFn: (body: RetrievalMaintenanceRequest) =>
      postRetrievalMaintenance(body, newIdempotencyKey()),
    onSuccess: accepted,
    onError: refused,
  })
  const buildSpace = useMutation({
    mutationFn: (body: {
      name: string
      provider: string
      model: string
      dim: number
      normalize: boolean
    }) => postRetrievalBuildSpace(body, newIdempotencyKey()),
    onSuccess: accepted,
    onError: refused,
  })
  const activateSpace = useMutation({
    mutationFn: (spaceId: string) =>
      activateRetrievalSpace(spaceId, newIdempotencyKey()),
    onSuccess: accepted,
    onError: refused,
  })
  const retireSpace = useMutation({
    mutationFn: (input: { spaceId: string; name: string }) =>
      retireRetrievalSpace(input.spaceId, input.name, newIdempotencyKey()),
    onSuccess: accepted,
    onError: refused,
  })
  const dropSpace = useMutation({
    mutationFn: (input: { spaceId: string; name: string }) =>
      dropRetrievalSpace(input.spaceId, input.name, newIdempotencyKey()),
    onSuccess: accepted,
    onError: refused,
  })
  const cutover = useMutation({
    mutationFn: (spaceId: string) =>
      postRetrievalCutover(
        { space_id: spaceId, limit: 5000, batch_size: 32, force: false },
        newIdempotencyKey()
      ),
    onSuccess: accepted,
    onError: refused,
  })

  if (!isAdmin) return null

  const data: RetrievalOverview | undefined = overview.data
  const spacesData: RetrievalSpaces | undefined = spacesQuery.data
  const coverage = data?.coverage.coverage
  const runs = runsQuery.data?.runs ?? []
  const activeRun = runs.find(
    (entry) => entry.run.status === 'queued' || entry.run.status === 'running'
  )
  const latestFailedIds =
    runs.find((entry) => (entry.result?.failed_ids?.length ?? 0) > 0)?.result
      ?.failed_ids ?? []
  const busy =
    reindex.isPending ||
    cancel.isPending ||
    retry.isPending ||
    maintenance.isPending ||
    buildSpace.isPending ||
    activateSpace.isPending ||
    retireSpace.isPending ||
    dropSpace.isPending ||
    cutover.isPending
  const spaces = spacesData?.spaces ?? []
  const activeSpace =
    spaces.find((entry) => entry.space_id === spacesData?.active_space_id) ??
    data?.space ??
    null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t('settings.retrievalStatusTitle')}</CardTitle>
        <CardDescription>{t('settings.retrievalStatusDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {overview.isLoading ? (
          <span className="text-muted-foreground flex items-center gap-2">
            <Loader2 className="animate-spin" aria-hidden />
            {t('settings.retrievalStatusLoading')}
          </span>
        ) : null}
        {overview.isError ? (
          <p className="text-muted-foreground">{t('settings.retrievalStatusUnavailable')}</p>
        ) : null}

        {data ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>{t(`settings.${stateKey(data.state)}`)}</span>
              <span className="text-muted-foreground text-xs">
                {data.backend_label ?? t('settings.retrievalBackendUnknown')}
              </span>
            </div>
            {data.space ? (
              <p className="text-muted-foreground text-xs">
                {t('settings.retrievalCounts', {
                  documents: data.space.documents,
                  records: data.space.records,
                })}
              </p>
            ) : null}
            {coverage !== null && coverage !== undefined ? (
              <p className="text-muted-foreground text-xs">
                {t('settings.retrievalCoverage', {
                  percent: Math.round(coverage * 100),
                })}
              </p>
            ) : null}
            {(data.notes ?? []).slice(0, 2).map((note) => (
              <p key={note} className="text-muted-foreground text-[11px]">
                {note}
              </p>
            ))}
            <p className="text-warning text-[11px]">
              {t('settings.retrievalLegacyWarning')}
            </p>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            size="sm"
            disabled={busy || overview.isError || Boolean(activeRun)}
            onClick={() => reindex.mutate(false)}
          >
            {reindex.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t('settings.retrievalReindex')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy || overview.isError || Boolean(activeRun)}
            onClick={() => reindex.mutate(true)}
          >
            {t('settings.retrievalReindexForce')}
          </Button>
          {activeRun ? (
            <span className="text-muted-foreground text-xs">
              {t('settings.retrievalRunActiveHint')}
            </span>
          ) : null}
        </div>

        {notice ? (
          <p role="status" className="text-success text-[11px]">
            {notice}
          </p>
        ) : null}
        {problem ? (
          <p role="alert" className="text-[11px] text-destructive">
            {problem}
          </p>
        ) : null}

        <div className="space-y-2 border-t pt-3">
          <h3 className="text-xs font-medium">{t('settings.retrievalRunsTitle')}</h3>
          {runsQuery.isLoading ? (
            <span className="text-muted-foreground flex items-center gap-2 text-xs">
              <Loader2 className="animate-spin" aria-hidden />
              {t('settings.retrievalRunsLoading')}
            </span>
          ) : null}
          {!runsQuery.isLoading && runs.length === 0 ? (
            <p className="text-muted-foreground text-xs">
              {t('settings.retrievalRunsEmpty')}
            </p>
          ) : null}
          <ul className="space-y-2">
            {runs.slice(0, 6).map((entry) => {
              const run = entry.run
              const result = entry.result
              const isActive =
                run.status === 'queued' || run.status === 'running'
              const canRetry =
                run.status === 'failed' || run.status === 'cancelled'
              return (
                <li
                  key={run.run_id}
                  className="border-border flex flex-wrap items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-xs"
                >
                  <div className="min-w-0 space-y-0.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">
                        {t(`settings.${runTypeKey(run.job_type)}`)}
                      </span>
                      <span className="text-muted-foreground">
                        {t(`settings.${runStatusKey(run.status)}`)}
                      </span>
                      {run.status === 'running' ? (
                        <span className="text-muted-foreground">
                          {run.progress}%
                        </span>
                      ) : null}
                    </div>
                    {run.stage ? (
                      <p className="text-muted-foreground truncate">{run.stage}</p>
                    ) : null}
                    {result ? (
                      <p className="text-muted-foreground">
                        {t('settings.retrievalRunCounts', {
                          scanned: result.scanned,
                          embedded: result.embedded,
                          failed: result.failed,
                        })}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-1">
                    {isActive ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={busy || cancel.isPending}
                        onClick={() => cancel.mutate(run.run_id)}
                      >
                        {t('settings.retrievalCancel')}
                      </Button>
                    ) : null}
                    {canRetry ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={busy || retry.isPending || Boolean(activeRun)}
                        onClick={() => retry.mutate(run.run_id)}
                      >
                        {t('settings.retrievalRetry')}
                      </Button>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>

        <div className="space-y-2 border-t pt-3">
          <h3 className="text-xs font-medium">
            {t('settings.retrievalSpacesTitle')}
          </h3>
          <p className="text-muted-foreground text-[11px]">
            {t('settings.retrievalSpacesHint')}
          </p>
          <p className="text-warning text-[11px]">
            {t('settings.retrievalQualityNotSampled')}
          </p>
          <ul className="space-y-2">
            {spaces.map((space) => {
              const isActive = space.space_id === spacesData?.active_space_id
              const isBuilding = space.status === 'building'
              const isRetired = space.status === 'retired'
              const typed = confirmations[space.space_id] ?? ''
              const confirmed = typed === space.name
              return (
                <li
                  key={space.space_id}
                  className="border-border space-y-1 rounded-md border px-2 py-1.5 text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">{space.name}</span>
                    <span className="text-muted-foreground">
                      {t(`settings.retrievalSpace${space.status}` as const)}
                    </span>
                  </div>
                  <p className="text-muted-foreground">
                    {t('settings.retrievalSpaceMeta', {
                      model: space.model,
                      dim: space.dim,
                      table: space.index_table ?? '',
                    })}
                  </p>
                  {isBuilding ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        type="button"
                        size="sm"
                        disabled={busy || Boolean(activeRun)}
                        onClick={() => cutover.mutate(space.space_id)}
                      >
                        {t('settings.retrievalCutover')}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={busy || !confirmed}
                        onClick={() =>
                          retireSpace.mutate({
                            spaceId: space.space_id,
                            name: space.name,
                          })
                        }
                      >
                        {t('settings.retrievalRetire')}
                      </Button>
                    </div>
                  ) : null}
                  {isBuilding || isRetired ? (
                    <input
                      aria-label={t('settings.retrievalTypeSpaceName', {
                        name: space.name,
                      })}
                      placeholder={t('settings.retrievalTypeSpaceName', {
                        name: space.name,
                      })}
                      value={typed}
                      disabled={busy}
                      onChange={(event) =>
                        setConfirmations((current) => ({
                          ...current,
                          [space.space_id]: event.target.value,
                        }))
                      }
                      className="border-border bg-surface w-full rounded-md border px-2 py-1 text-xs"
                    />
                  ) : null}
                  {isRetired ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      disabled={busy || !confirmed}
                      onClick={() =>
                        dropSpace.mutate({
                          spaceId: space.space_id,
                          name: space.name,
                        })
                      }
                    >
                      {t('settings.retrievalDrop')}
                    </Button>
                  ) : null}
                  {isActive ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled
                    >
                      {t('settings.retrievalSpaceActiveLabel')}
                    </Button>
                  ) : null}
                </li>
              )
            })}
          </ul>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-muted-foreground flex flex-col gap-1 text-[11px]">
              {t('settings.retrievalCandidateName')}
              <input
                aria-label={t('settings.retrievalCandidateName')}
                value={candidateName}
                disabled={busy}
                onChange={(event) => setCandidateName(event.target.value)}
                className="border-border bg-surface w-48 rounded-md border px-2 py-1 text-xs"
              />
            </label>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={
                busy ||
                !activeSpace ||
                candidateName.trim().length === 0 ||
                Boolean(activeRun)
              }
              onClick={() => {
                if (!activeSpace) return
                buildSpace.mutate({
                  name: candidateName.trim(),
                  provider: activeSpace.provider,
                  model: activeSpace.model,
                  dim: activeSpace.dim,
                  normalize: true,
                })
              }}
            >
              {t('settings.retrievalBuildCandidate')}
            </Button>
          </div>
        </div>

        <div className="space-y-2 border-t pt-3">
          <h3 className="text-xs font-medium">
            {t('settings.retrievalMaintenanceTitle')}
          </h3>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-xs">
              {t('settings.retrievalMaintenanceAction')}
              <select
                aria-label={t('settings.retrievalMaintenanceAction')}
                value={maintenanceAction}
                disabled={busy}
                onChange={(event) => {
                  const next = event.target.value as MaintenanceAction
                  setMaintenanceAction(next)
                  if (next !== 'orphan-sweep') setDryRun(false)
                }}
                className="border-border bg-surface rounded-md border px-2 py-1 text-xs"
              >
                {MAINTENANCE_ACTIONS.map((action) => (
                  <option key={action} value={action}>
                    {t(`settings.${maintenanceKey(action)}`)}
                  </option>
                ))}
              </select>
            </label>
            {maintenanceAction === 'orphan-sweep' ? (
              <label className="flex items-center gap-1.5 text-xs">
                <input
                  type="checkbox"
                  checked={dryRun}
                  disabled={busy}
                  onChange={(event) => setDryRun(event.target.checked)}
                />
                {t('settings.retrievalDryRun')}
              </label>
            ) : null}
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={
                busy ||
                Boolean(activeRun) ||
                (maintenanceAction === 'retry-failed' && latestFailedIds.length === 0)
              }
              onClick={() =>
                maintenance.mutate({
                  action: maintenanceAction,
                  dry_run: maintenanceAction === 'orphan-sweep' ? dryRun : false,
                  chunk_ids:
                    maintenanceAction === 'retry-failed'
                      ? latestFailedIds
                      : undefined,
                })
              }
            >
              {maintenance.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : null}
              {t('settings.retrievalRunMaintenance')}
            </Button>
          </div>
          {maintenanceAction === 'retry-failed' ? (
            <p className="text-muted-foreground text-[11px]">
              {latestFailedIds.length > 0
                ? t('settings.retrievalRetryFailedHint', {
                    count: latestFailedIds.length,
                  })
                : t('settings.retrievalRetryFailedNone')}
            </p>
          ) : null}
          {maintenanceAction === 'orphan-sweep' && dryRun ? (
            <p className="text-muted-foreground text-[11px]">
              {t('settings.retrievalDryRunHint')}
            </p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

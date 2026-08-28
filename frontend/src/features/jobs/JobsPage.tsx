import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowDownWideNarrow,
  ArrowUpNarrowWide,
  CircleAlert,
  ClipboardList,
  FileText,
  Inbox,
  Layers,
  Loader2,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'

import { ErrorBanner } from '@/components/ui/error-banner'
import { PopoverMenu, type PopoverMenuItem } from '@/components/ui/popover-menu'
import { SearchInput } from '@/components/ui/SearchInput'
import {
  deleteFailedJobs,
  deleteJob,
  listJobTypes,
  listJobs,
  retryFailedJobs,
  retryJob,
  type JobInfo,
} from '@/lib/api'

import { cn } from '@/lib/utils'

const STATUS_TABS = ['failed', 'running', 'queued', 'done'] as const
type StatusTab = 'all' | (typeof STATUS_TABS)[number]
type SortKey = 'created' | 'started' | 'finished'

const SORT_KEYS: { key: SortKey; labelKey: string }[] = [
  { key: 'finished', labelKey: 'jobs.sortFinished' },
  { key: 'started', labelKey: 'jobs.sortStarted' },
  { key: 'created', labelKey: 'jobs.sortCreated' },
]

const TYPE_ICONS: Record<string, typeof Inbox> = {
  ingest: FileText,
  postprocess: Layers,
  chat_turn: ClipboardList,
}

function TypeChip({ type }: { type: string }) {
  const Icon = TYPE_ICONS[type] ?? Inbox
  return (
    <span className="bg-subtle text-muted-foreground flex w-fit shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px]">
      <Icon className="size-3" aria-hidden />
      {type}
    </span>
  )
}

const STATUS_STYLES: Record<string, string> = {
  failed: 'bg-danger/15 text-danger',
  running: 'bg-primary/15 text-primary',
  queued: 'bg-warning/15 text-warning',
  done: 'bg-success/15 text-success',
}

function formatDateTime(iso: string | null): string {
  if (iso === null) {
    return '—'
  }
  return new Date(iso).toLocaleString()
}

function JobRow({
  job,
  onRetry,
  onDelete,
}: {
  job: JobInfo
  onRetry: (jobId: number) => void
  onDelete: (jobId: number) => void
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const title = job.label
  return (
    <li className={cn('border-border bg-surface rounded-lg border', job.stale && 'opacity-70')}>
      <div className="flex items-start gap-3 p-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            {job.material_id !== null ? (
              <Link
                to="/library/$materialId"
                params={{ materialId: String(job.material_id) }}
                search={{}}
                className="min-w-0 truncate text-sm font-medium hover:underline"
              >
                {title}
              </Link>
            ) : (
              <span className="min-w-0 truncate text-sm font-medium">{title}</span>
            )}
            <TypeChip type={job.type} />
            <span
              className={cn(
                'rounded-full px-2 py-0.5 text-[10px] font-medium',
                STATUS_STYLES[job.status] ?? 'bg-subtle text-muted-foreground'
              )}
            >
              {job.stage && job.status !== 'done' ? `${job.status} · ${job.stage}` : job.status}
            </span>
            {job.stale ? (
              <span className="bg-danger/10 text-danger rounded-full px-2 py-0.5 text-[10px] font-medium">
                {t('jobs.sourceRemoved')}
              </span>
            ) : null}
          </div>
          {job.error ? (
            <p
              className={cn(
                'text-danger cursor-pointer text-xs',
                !expanded && 'line-clamp-2'
              )}
              role="button"
              tabIndex={0}
              title={expanded ? t('jobs.collapseError') : job.error}
              onClick={() => setExpanded((current) => !current)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  setExpanded((current) => !current)
                }
              }}
            >
              {job.error}
            </p>
          ) : null}
          <p className="text-muted-foreground text-[11px]">
            #{job.id} ·{' '}
            {t('jobs.startedWhen', { time: formatDateTime(job.started_at ?? job.created_at) })} ·{' '}
            {t('jobs.finishedWhen', { time: formatDateTime(job.finished_at) })}
          </p>
        </div>
        {job.retriable && !job.stale ? (
          <button
            type="button"
            onClick={() => onRetry(job.id)}
            title={t('jobs.retry')}
            aria-label={`${t('jobs.retry')}: ${title}`}
            className="focus-visible:outline-ring hover:bg-danger/15 text-muted-foreground hover:text-danger flex size-8 shrink-0 items-center justify-center rounded-md transition-colors focus-visible:outline-2 focus-visible:outline-offset-1"
          >
            <RotateCcw className="size-4" aria-hidden />
          </button>
        ) : null}
        {job.status === 'failed' || job.status === 'done' ? (
          <button
            type="button"
            onClick={() => onDelete(job.id)}
            title={t('jobs.deleteOne')}
            aria-label={`${t('jobs.deleteOne')}: ${title}`}
            className="focus-visible:outline-ring hover:bg-danger/15 text-muted-foreground hover:text-danger flex size-8 shrink-0 items-center justify-center rounded-md transition-colors focus-visible:outline-2 focus-visible:outline-offset-1"
          >
            <Trash2 className="size-4" aria-hidden />
          </button>
        ) : null}
      </div>
    </li>
  )
}

function sortTimestamp(job: JobInfo, key: SortKey): number {
  const iso =
    key === 'created'
      ? (job.created_at ?? '')
      : key === 'started'
        ? (job.started_at ?? job.created_at ?? '')
        : (job.finished_at ?? job.started_at ?? job.created_at ?? '')
  const time = Date.parse(iso)
  return Number.isNaN(time) ? 0 : time
}

export function JobsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const search = useSearch({ strict: false }) as {
    status?: string
    type?: string
    sort?: string
    dir?: string
  }
  const statusTab: StatusTab = STATUS_TABS.find((entry) => entry === search.status) ?? 'all'
  const setParam = (patch: Record<string, string | undefined>) => {
    void navigate({ to: '/jobs', search: (prev: Record<string, unknown>) => ({ ...prev, ...patch }) })
  }
  const sortKey: SortKey = SORT_KEYS.some((entry) => entry.key === search.sort)
    ? (search.sort as SortKey)
    : 'finished'
  const descending = search.dir !== 'asc'

  const [query, setQuery] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [retryError, setRetryError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const jobs = useQuery({
    queryKey: ['jobs-list', statusTab],
    queryFn: () =>
      listJobs({ status: statusTab === 'all' ? undefined : statusTab, limit: 200 }),
    refetchInterval: 5000,
  })
  const types = useQuery({
    queryKey: ['job-types'],
    queryFn: listJobTypes,
    staleTime: 60_000,
  })

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['jobs-summary'] })
    await queryClient.invalidateQueries({ queryKey: ['jobs-list'] })
  }

  const retryOne = useMutation({
    mutationFn: (jobId: number) => retryJob(jobId),
    onSuccess: async () => {
      setRetryError(null)
      await invalidate()
    },
    onError: (error: Error) => setRetryError(error.message),
  })
  const retryAll = useMutation({
    mutationFn: () => retryFailedJobs(),
    onSuccess: async () => {
      setRetryError(null)
      await invalidate()
      await queryClient.invalidateQueries({ queryKey: ['jobs-list'] })
    },
    onError: (error: Error) => setRetryError(error.message),
  })
  const deleteOne = useMutation({
    mutationFn: (jobId: number) => deleteJob(jobId),
    onSuccess: async () => {
      setDeleteError(null)
      await invalidate()
    },
    onError: (error: Error) => setDeleteError(error.message),
  })
  const deleteAllFailed = useMutation({
    mutationFn: (options?: { types?: string[]; staleOnly?: boolean }) =>
      deleteFailedJobs(options),
    onSuccess: async () => {
      setDeleteError(null)
      await invalidate()
    },
    onError: (error: Error) => setDeleteError(error.message),
  })

  const needle = submitted.trim().toLowerCase()
  const all = [...(jobs.data ?? [])].sort((a, b) => {
    const delta = sortTimestamp(a, sortKey) - sortTimestamp(b, sortKey)
    return descending ? -delta : delta
  })
  const visible = all.filter((job) =>
    needle ? job.label.toLowerCase().includes(needle) || String(job.id).includes(needle) : true
  )
  const counts = (jobs.data ?? []).reduce<Record<string, number>>((acc, job) => {
    acc[job.status] = (acc[job.status] ?? 0) + 1
    acc.all = (acc.all ?? 0) + 1
    return acc
  }, {})
  const retryableTypes = types.data ?? []

  const failedJobs = (jobs.data ?? []).filter((job) => job.status === 'failed')
  const failedInScope = failedJobs.filter(
    (job) => !search.type || job.type === search.type
  )
  const staleCount = failedJobs.filter((job) => job.stale).length
  const deleteMenuItems: PopoverMenuItem[] = [
    {
      key: 'delete-failed',
      label: search.type
        ? t('jobs.deleteAllFiltered', { type: search.type })
        : t('jobs.deleteAllPlain'),
      icon: Trash2,
      danger: true,
      disabled: deleteAllFailed.isPending || failedInScope.length === 0,
      onSelect: () => {
        const count = failedInScope.length
        if (window.confirm(t('jobs.confirmDeleteFailed', { count }))) {
          deleteAllFailed.mutate(search.type ? { types: [search.type] } : undefined)
        }
      },
    },
    {
      key: 'delete-stale',
      label: t('jobs.deleteStale', { count: staleCount }),
      icon: Trash2,
      danger: true,
      disabled: deleteAllFailed.isPending || staleCount === 0,
      onSelect: () => {
        if (
          window.confirm(
            t('jobs.confirmDeleteStale', { count: staleCount })
          )
        ) {
          deleteAllFailed.mutate({ staleOnly: true })
        }
      },
    },
  ]

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-8">
      <header className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{t('jobs.pageTitle')}</h1>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            disabled={retryAll.isPending}
            onClick={() => retryAll.mutate()}
            className="focus-visible:outline-ring bg-danger/10 text-danger hover:bg-danger/20 flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 disabled:opacity-50"
          >
            {retryAll.isPending ? (
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
            ) : (
              <RotateCcw className="size-3.5" aria-hidden />
            )}
            {t('jobs.retryAllPlain')}
          </button>
          <PopoverMenu
            label={t('jobs.deleteMenu')}
            trigger={
              <>
                <Trash2 className="size-3.5" aria-hidden />
                {t('jobs.deleteMenu')}
              </>
            }
            triggerClassName="focus-visible:outline-ring bg-surface border-border text-muted-foreground hover:text-foreground flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-1"
            items={deleteMenuItems}
          />
        </div>
      </header>

      <ErrorBanner message={retryError} />
      <ErrorBanner message={deleteError} />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1" role="tablist" aria-label={t('jobs.filterLabel')}>
          {(['all', ...STATUS_TABS] as StatusTab[]).map((entry) => (
            <Link
              key={entry}
              to="/jobs"
              search={(prev: Record<string, unknown>) => ({
                ...prev,
                status: entry === 'all' ? undefined : entry,
              })}
              role="tab"
              aria-selected={statusTab === entry}
              className={cn(
                'rounded-full px-3 py-1 text-xs transition-colors',
                statusTab === entry
                  ? 'bg-primary/15 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-subtle hover:text-foreground'
              )}
            >
              {t(`jobs.tab_${entry}`)}
              {counts?.[entry] ? ` (${counts[entry]})` : ''}
            </Link>
          ))}
        </div>
        <SearchInput
          value={query}
          onChange={setQuery}
          onSubmit={() => setSubmitted(query.trim())}
          placeholder={t('jobs.searchPlaceholder')}
          ariaLabel={t('jobs.searchPlaceholder')}
          clearLabel={t('common.clearSearch')}
        />
      </div>

      <div className="border-border flex flex-wrap items-center gap-x-4 gap-y-2 border-b pb-3">
        <label className="text-muted-foreground flex items-center gap-2 text-xs">
          {t('jobs.typeFilter')}
          <select
            className="bg-surface border-border rounded-md border px-2 py-1 text-xs"
            value={search.type ?? ''}
            aria-label={t('jobs.typeFilter')}
            onChange={(event) =>
              setParam({ type: event.target.value === '' ? undefined : event.target.value })
            }
          >
            <option value="">{t('jobs.allTypes')}</option>
            {retryableTypes.map((entry) => (
              <option key={entry.type} value={entry.type}>
                {entry.label}
              </option>
            ))}
          </select>
        </label>
        <div className="ml-auto flex items-center gap-1" role="group" aria-label={t('jobs.sortLabel')}>
          {SORT_KEYS.map((entry) => (
            <button
              key={entry.key}
              type="button"
              role="tab"
              aria-selected={sortKey === entry.key}
              onClick={() => setParam({ sort: entry.key })}
              className={cn(
                'rounded-full px-2.5 py-1 text-xs transition-colors',
                sortKey === entry.key
                  ? 'bg-surface text-foreground border-border font-medium'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {t(entry.labelKey)}
            </button>
          ))}
          <button
            type="button"
            title={descending ? t('jobs.sortDesc') : t('jobs.sortAsc')}
            aria-label={descending ? t('jobs.sortAsc') : t('jobs.sortDesc')}
            className="focus-visible:outline-ring text-muted-foreground hover:bg-subtle hover:text-foreground ml-1 flex size-7 items-center justify-center rounded-md transition-colors focus-visible:outline-2 focus-visible:outline-offset-1"
            onClick={() => setParam({ dir: descending ? 'asc' : undefined })}
          >
            {descending ? (
              <ArrowDownWideNarrow className="size-3.5" aria-hidden />
            ) : (
              <ArrowUpNarrowWide className="size-3.5" aria-hidden />
            )}
          </button>
        </div>
      </div>

      {jobs.isLoading ? (
        <Loader2 className="text-muted-foreground m-8 animate-spin" aria-label={t('library.loading')} />
      ) : visible.length === 0 ? (
        <p className="text-muted-foreground py-12 text-center text-sm">{t('jobs.empty')}</p>
      ) : (
        <ul className="space-y-2">
          {visible.map((job) => (
            <JobRow
              key={job.id}
              job={job}
              onRetry={(id) => retryOne.mutate(id)}
              onDelete={(id) => {
                if (window.confirm(t('jobs.confirmDeleteOne'))) {
                  deleteOne.mutate(id)
                }
              }}
            />
          ))}
        </ul>
      )}

      <p className="text-muted-foreground flex items-center justify-center gap-1.5 text-[11px]">
        <CircleAlert className="size-3" aria-hidden />
        {t('jobs.autoRefreshHint')}
      </p>
    </div>
  )
}

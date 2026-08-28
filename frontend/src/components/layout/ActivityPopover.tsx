import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, CircleAlert, Loader2, RotateCcw, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from '@tanstack/react-router'

import {
  deleteFailedJobs,
  deleteJob,
  getJobsSummary,
  listJobs,
  retryFailedJobs,
  retryJob,
  type JobInfo,
} from '@/lib/api'

import { cn } from '@/lib/utils'

function relativeTime(iso: string | null): string {
  if (iso === null) {
    return ''
  }
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (seconds < 60) {
    return `${seconds}s`
  }
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m`
  }
  const hours = Math.round(minutes / 60)
  if (hours < 24) {
    return `${hours}h`
  }
  return `${Math.round(hours / 24)}d`
}

function ProgressTrack({ job }: { job: JobInfo }) {
  return (
    <div className="bg-subtle h-1 w-full overflow-hidden rounded-full">
      <div
        className="bg-primary h-full rounded-full transition-all"
        style={{ width: `${job.progress}%` }}
      />
    </div>
  )
}

function FailedRow({
  job,
  onRetry,
  onDelete,
}: {
  job: JobInfo
  onRetry: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation()
  return (
    <li
      className={cn(
        'border-danger/30 bg-danger/5 rounded-md border px-2 py-1.5',
        job.stale && 'opacity-70'
      )}
    >
      <div className="flex items-center gap-2 text-xs">
        <CircleAlert className="text-danger size-3.5 shrink-0" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-medium">{job.label}</span>
        {job.stale ? (
          <span className="text-muted-foreground shrink-0 text-[10px]">
            {t('jobs.sourceRemoved')}
          </span>
        ) : null}
        <span className="text-muted-foreground shrink-0 text-[10px]">
          {relativeTime(job.finished_at ?? job.created_at)}
        </span>
        {job.retriable && !job.stale ? (
          <button
            type="button"
            onClick={onRetry}
            title={t('jobs.retry')}
            aria-label={`${t('jobs.retry')}: ${job.label}`}
            className="focus-visible:outline-ring hover:bg-danger/15 text-muted-foreground hover:text-danger flex size-6 shrink-0 items-center justify-center rounded-md focus-visible:outline-2 focus-visible:outline-offset-1"
          >
            <RotateCcw className="size-3.5" aria-hidden />
          </button>
        ) : null}
        <button
          type="button"
          onClick={onDelete}
          title={t('jobs.deleteOne')}
          aria-label={`${t('jobs.deleteOne')}: ${job.label}`}
          className="focus-visible:outline-ring hover:bg-danger/15 text-muted-foreground hover:text-danger flex size-6 shrink-0 items-center justify-center rounded-md focus-visible:outline-2 focus-visible:outline-offset-1"
        >
          <Trash2 className="size-3.5" aria-hidden />
        </button>
      </div>
      {job.error ? (
        <p
          className="text-muted-foreground mt-0.5 line-clamp-2 pl-[22px] text-[10px]"
          title={job.error}
        >
          {job.error}
        </p>
      ) : null}
    </li>
  )
}

function ActiveRow({ job }: { job: JobInfo }) {
  return (
    <li className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs">
      <Loader2 className="text-primary size-3.5 shrink-0 animate-spin" aria-hidden />
      <span className="min-w-0 flex-1 truncate">{job.label}</span>
      {job.stage ? (
        <span className="text-muted-foreground max-w-32 shrink-0 truncate text-[10px]">
          {job.stage}
        </span>
      ) : null}
      {job.status === 'running' ? (
        <span className="w-12 shrink-0">
          <ProgressTrack job={job} />
        </span>
      ) : null}
    </li>
  )
}

function DoneRow({ job }: { job: JobInfo }) {
  return (
    <li className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs">
      <Activity className="text-muted-foreground size-3.5 shrink-0 opacity-50" aria-hidden />
      <span className="text-muted-foreground min-w-0 flex-1 truncate">{job.label}</span>
      <span className="text-muted-foreground shrink-0 text-[10px] opacity-70">
        {relativeTime(job.finished_at ?? job.created_at)}
      </span>
    </li>
  )
}

export function ActivityButton() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const [retryError, setRetryError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      return
    }
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const summary = useQuery({
    queryKey: ['jobs-summary'],
    queryFn: getJobsSummary,
    refetchInterval: open ? 2000 : 10000,
  })
  const jobs = useQuery({
    queryKey: ['jobs-list'],
    queryFn: () => listJobs({ limit: 60 }),
    enabled: open,
    refetchInterval: 2000,
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
    },
    onError: (error: Error) => setRetryError(error.message),
  })
  const [deleteError, setDeleteError] = useState<string | null>(null)
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

  const allJobs = jobs.data ?? []
  const failed = allJobs.filter((job) => job.status === 'failed')
  const active = allJobs.filter(
    (job) => job.status === 'running' || job.status === 'queued'
  )
  const done = allJobs.filter((job) => job.status === 'done').slice(0, 8)
  const failedCount = summary.data?.failed ?? 0
  const staleCount = summary.data?.failed_stale ?? 0

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        className={cn(
          'focus-visible:outline-ring relative flex size-9 items-center justify-center rounded-md transition-colors focus-visible:outline-2 focus-visible:outline-offset-1',
          open ? 'bg-surface text-foreground' : 'text-muted-foreground hover:text-foreground'
        )}
        title={t('jobs.title')}
        aria-label={t('jobs.title')}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
      >
        <Activity
          className={cn('size-4', failedCount > 0 && !open ? 'text-danger' : '')}
          aria-hidden
        />
        {failedCount > 0 ? (
          <span
            className={cn(
              'absolute -top-0.5 -right-0.5 flex min-w-4 items-center justify-center rounded-full px-1 text-[9px] font-semibold',
              open ? 'bg-border text-foreground' : 'bg-danger text-white'
            )}
          >
            {failedCount > 99 ? '99+' : failedCount}
          </span>
        ) : null}
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label={t('jobs.title')}
          tabIndex={-1}
          className="bg-surface border-border animate-in fade-in absolute bottom-full left-0 z-50 mb-2 w-80 rounded-lg border p-3 shadow-lg outline-none"
        >
          <div className="space-y-2.5">
            <div className="flex items-center gap-2">
              <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">
                {t('jobs.title')}
              </h2>
              {(summary.data?.failed_retryable ?? 0) > 0 ? (
                <button
                  type="button"
                  disabled={retryAll.isPending}
                  onClick={() => retryAll.mutate()}
                  className="focus-visible:outline-ring bg-danger/10 text-danger hover:bg-danger/20 flex shrink-0 items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-1"
                >
                  {retryAll.isPending ? (
                    <Loader2 className="size-3.5 animate-spin" aria-hidden />
                  ) : (
                    <RotateCcw className="size-3.5" aria-hidden />
                  )}
                  {t('jobs.retryAll', { count: summary.data?.failed_retryable ?? 0 })}
                </button>
              ) : null}
            </div>

            {retryError ? (
              <p className="text-danger flex items-center gap-1 text-xs" role="alert">
                {retryError}
              </p>
            ) : null}
            {deleteError ? (
              <p className="text-danger flex items-center gap-1 text-xs" role="alert">
                {deleteError}
              </p>
            ) : null}

            {failed.length > 0 ? (
              <section className="space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-danger/80 text-[10px] font-medium tracking-wide uppercase">
                    {t('jobs.sectionFailed', { count: failed.length })}
                  </p>
                  {failedCount > 0 ? (
                    <button
                      type="button"
                      disabled={deleteAllFailed.isPending}
                      title={t('jobs.deleteAllPlain')}
                      aria-label={t('jobs.deleteAllPlain')}
                      className="focus-visible:outline-ring hover:bg-danger/15 text-muted-foreground hover:text-danger flex size-6 shrink-0 items-center justify-center rounded-md focus-visible:outline-2 focus-visible:outline-offset-1 disabled:opacity-50"
                      onClick={() => {
                        if (window.confirm(t('jobs.confirmDeleteFailed', { count: failedCount }))) {
                          deleteAllFailed.mutate(undefined)
                        }
                      }}
                    >
                      {deleteAllFailed.isPending ? (
                        <Loader2 className="size-3.5 animate-spin" aria-hidden />
                      ) : (
                        <Trash2 className="size-3.5" aria-hidden />
                      )}
                    </button>
                  ) : null}
                </div>
                <ul className="space-y-1">
                  {failed.slice(0, 8).map((job) => (
                    <FailedRow
                      key={job.id}
                      job={job}
                      onRetry={() => retryOne.mutate(job.id)}
                      onDelete={() => {
                        if (window.confirm(t('jobs.confirmDeleteOne'))) {
                          deleteOne.mutate(job.id)
                        }
                      }}
                    />
                  ))}
                </ul>
                {staleCount > 0 ? (
                  <button
                    type="button"
                    disabled={deleteAllFailed.isPending}
                    onClick={() => {
                      if (window.confirm(t('jobs.confirmDeleteStale', { count: staleCount }))) {
                        deleteAllFailed.mutate({ staleOnly: true })
                      }
                    }}
                    className="focus-visible:outline-ring hover:bg-danger/15 text-danger/90 mx-2 rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 disabled:opacity-50"
                  >
                    {t('jobs.deleteStale', { count: staleCount })}
                  </button>
                ) : null}
                {failed.length > 8 ? (
                  <p className="text-muted-foreground px-2 text-[10px]">
                    {t('jobs.moreFailed', { count: failed.length - 8 })}
                  </p>
                ) : null}
              </section>
            ) : null}

            {active.length > 0 ? (
              <section className="space-y-1">
                <p className="text-muted-foreground text-[10px] font-medium tracking-wide uppercase">
                  {t('jobs.sectionActive')}
                </p>
                <ul>
                  {active.slice(0, 6).map((job) => (
                    <ActiveRow key={job.id} job={job} />
                  ))}
                </ul>
              </section>
            ) : null}

            {!jobs.isLoading && allJobs.length === 0 ? (
              <p className="text-muted-foreground py-4 text-center text-xs">{t('jobs.empty')}</p>
            ) : done.length > 0 && active.length + failed.length < 10 ? (
              <section className="border-border space-y-1 border-t pt-2">
                <p className="text-muted-foreground text-[10px] font-medium tracking-wide uppercase">
                  {t('jobs.sectionRecent')}
                </p>
                <ul>{done.map((job) => <DoneRow key={job.id} job={job} />)}</ul>
              </section>
            ) : null}

            <p className="text-muted-foreground border-border border-t pt-2 text-center text-[10px]">
              <Link
                to="/jobs"
                className="hover:text-foreground inline-flex items-center gap-1"
                onClick={() => setOpen(false)}
              >
                {t('jobs.openAll')}
              </Link>
              {' · '}
              {t('jobs.liveHint')}
            </p>
          </div>
        </div>
      ) : null}
    </div>
  )
}

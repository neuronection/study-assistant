import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { useMotionPresets } from '@/lib/motion'
import {
  AlarmClock,
  AlertTriangle,
  Bell,
  CalendarClock,
  Inbox,
  Layers,
  MessagesSquare,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import { EmptyState } from '@/components/ui/empty-state'
import { Popover } from '@/components/ui/popover'
import {
  getNotifications,
  type Notifications,
  type PlanEntry,
} from '@/lib/api'
import { storageKeys, WsTopic } from '@/lib/constants'
import { getWsClient } from '@/lib/ws-client'
import { useNavigate } from '@tanstack/react-router'
import { cn } from '@/lib/utils'

const REFRESH_INTERVAL_MS = 5 * 60 * 1000

export function useNotificationSeen(total: number | null) {
  const [seen, setSeen] = useState(() => {
    try {
      const raw = window.localStorage.getItem(storageKeys.notificationsSeen)
      const value = raw === null ? 0 : Number(raw)
      return Number.isFinite(value) ? value : 0
    } catch {
      return 0
    }
  })

  const markSeen = useCallback(
    (current: number) => {
      setSeen(current)
      try {
        window.localStorage.setItem(storageKeys.notificationsSeen, String(current))
      } catch {
        return
      }
    },
    []
  )

  useEffect(() => {
    if (total !== null && total < seen) {
      markSeen(total)
    }
  }, [total, seen, markSeen])

  return { seen, markSeen }
}

export function useNotifications() {
  return useQuery({
    queryKey: ['notifications'],
    queryFn: getNotifications,
    refetchInterval: REFRESH_INTERVAL_MS,
  })
}

export function actionableTotal(data: Notifications | undefined): number | null {
  if (!data) {
    return null
  }
  return (
    data.due_cards +
    data.plan_today.length +
    data.pending_proposals +
    (data.staged_imports?.length ?? 0) +
    (data.alerts?.length ?? 0)
  )
}

function SectionLabel({ icon: Icon, label }: { icon: typeof Bell; label: string }) {
  return (
    <p className="text-muted-foreground flex items-center gap-1.5 text-[11px] font-semibold">
      <Icon className="size-3" aria-hidden />
      {label}
    </p>
  )
}

export function NotificationBell() {
  const { t } = useTranslation()
  const presets = useMotionPresets()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data } = useNotifications()
  const total = actionableTotal(data)
  const { seen, markSeen } = useNotificationSeen(total)
  const showDot = total !== null && total > seen

  useEffect(
    () =>
      getWsClient().subscribe(WsTopic.inbox(), () => {
        void queryClient.invalidateQueries({ queryKey: ['notifications'] })
      }),
    [queryClient]
  )

  const handleOpenChange = (open: boolean) => {
    if (!open && total !== null) {
      markSeen(total)
    }
  }

  const openReview = () => void navigate({ to: '/review' })
  const openChat = () => void navigate({ to: '/chat' })
  const openPlanner = (courseId: string) =>
    void navigate({
      to: '/courses/$courseId',
      params: { courseId: String(courseId) },
      search: { tab: 'planner' },
    })
  const openAlert = (link: string) => {
    const url = new URL(link, window.location.origin)
    void navigate({
      to: '/settings',
      search: {
        tab: url.searchParams.get('tab') ?? undefined,
        section: url.searchParams.get('section') ?? undefined,
      },
    })
  }

  const empty =
    data !== undefined &&
    data.due_cards === 0 &&
    data.plan_today.length === 0 &&
    data.exams.length === 0 &&
    data.pending_proposals === 0 &&
    (data.staged_imports?.length ?? 0) === 0 &&
    (data.alerts?.length ?? 0) === 0

  return (
    <Popover
      label={t('notifications.label')}
      align="end"
      side="right"
      panelClassName="w-80 p-3"
      onOpenChange={handleOpenChange}
      triggerClassName={cn(
        'relative rounded-md p-2 transition-colors',
        showDot
          ? 'bg-surface text-foreground'
          : 'text-muted-foreground hover:text-foreground'
      )}
      trigger={
        <>
          <Bell className="size-4" aria-hidden />
          <span className="sr-only">{t('notifications.label')}</span>
          <AnimatePresence>
            {showDot ? (
              <motion.span
                {...presets.panel}
                className="bg-danger absolute right-0.5 top-0.5 flex items-center justify-center"
              >
                <Badge
                  variant="danger"
                  className="min-w-4 rounded-full px-1 py-0 text-[9px] leading-4 tabular-nums"
                >
                  {total > 99 ? '99+' : total}
                </Badge>
              </motion.span>
            ) : null}
          </AnimatePresence>
        </>
      }
    >
      {empty ? (
        <EmptyState icon={Bell} title={t('notifications.empty')} compact />
      ) : (
        <div className="space-y-3" aria-live="polite">
          {data && (data.alerts?.length ?? 0) > 0 ? (
            <motion.section {...presets.enter} className="space-y-1.5">
              <SectionLabel icon={AlertTriangle} label={t('notifications.alerts')} />
              {data.alerts.map((alert) => (
                <button
                  key={alert.id}
                  type="button"
                  className="hover:bg-subtle flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors"
                  onClick={() => openAlert(alert.link)}
                >
                  <AlertTriangle
                    className={cn(
                      'mt-0.5 size-3.5 shrink-0',
                      alert.severity === 'error'
                        ? 'text-danger'
                        : alert.severity === 'warning'
                          ? 'text-warning'
                          : 'text-primary'
                    )}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1">
                    <span className="text-foreground block truncate font-medium">
                      {alert.title}
                    </span>
                    {alert.body ? (
                      <span className="text-muted-foreground block line-clamp-2 text-[10px]">
                        {alert.body}
                      </span>
                    ) : null}
                  </span>
                </button>
              ))}
            </motion.section>
          ) : null}

          {data && data.due_cards > 0 ? (
            <motion.section {...presets.enter} className="space-y-1.5">
              <SectionLabel icon={Layers} label={t('notifications.dueNow')} />
              <button
                type="button"
                className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors"
                onClick={openReview}
              >
                <Layers className="text-primary size-3.5 shrink-0" aria-hidden />
                <span className="text-foreground flex-1 font-medium">
                  {t('notifications.dueCards', { count: data.due_cards })}
                </span>
                {data.due_reviews.length > 0 ? (
                  <span className="text-muted-foreground truncate text-[10px]">
                    {data.due_reviews[0].course_title}
                  </span>
                ) : null}
              </button>
            </motion.section>
          ) : null}

          {data && data.plan_today.length > 0 ? (
            <motion.section {...presets.enter} className="space-y-1.5">
              <SectionLabel icon={AlarmClock} label={t('notifications.plan')} />
              {data.plan_today.slice(0, 5).map((item: PlanEntry) => (
                <button
                  key={item.item_id}
                  type="button"
                  className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors"
                  onClick={() => openPlanner(item.course_id)}
                >
                  <span
                    className={cn(
                      'size-1.5 shrink-0 rounded-full',
                      item.overdue ? 'bg-danger' : 'bg-primary'
                    )}
                    aria-hidden
                  />
                  <span
                    className={cn(
                      'flex-1 truncate',
                      item.overdue ? 'text-danger font-medium' : 'text-foreground'
                    )}
                  >
                    {item.title}
                  </span>
                  <span className="text-muted-foreground hidden truncate text-[10px] sm:block">
                    {item.course_title}
                  </span>
                </button>
              ))}
              {data.plan_overdue_count > data.plan_today.filter((item) => item.overdue).length ? (
                <p className="text-muted-foreground px-2 text-[10px]">
                  {t('notifications.moreOverdue', { count: data.plan_overdue_count })}
                </p>
              ) : null}
            </motion.section>
          ) : null}

          {data && data.pending_proposals > 0 ? (
            <motion.section {...presets.enter} className="space-y-1.5">
              <SectionLabel
                icon={MessagesSquare}
                label={t('notifications.pendingProposals')}
              />
              <button
                type="button"
                className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors"
                onClick={openChat}
              >
                <MessagesSquare
                  className="text-primary size-3.5 shrink-0"
                  aria-hidden
                />
                <span className="text-foreground flex-1 font-medium">
                  {t('notifications.pendingProposalsCount', {
                    count: data.pending_proposals,
                  })}
                </span>
              </button>
            </motion.section>
          ) : null}

          {data && (data.staged_imports?.length ?? 0) > 0 ? (
            <motion.section {...presets.enter} className="space-y-1.5">
              <SectionLabel icon={Inbox} label={t('notifications.stagedImports')} />
              {data.staged_imports.map((entry) => (
                <button
                  key={entry.filename}
                  type="button"
                  className="hover:bg-subtle flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors"
                  onClick={() => void navigate({ to: '/courses' })}
                >
                  <Inbox
                    className={cn(
                      'size-3.5 shrink-0',
                      entry.ok ? 'text-primary' : 'text-danger'
                    )}
                    aria-hidden
                  />
                  <span className="text-foreground flex-1 truncate">{entry.filename}</span>
                  <span className="text-muted-foreground shrink-0 text-[10px]">
                    {entry.ok
                      ? t('notifications.stagedImportReady', {
                          count: entry.question_count,
                        })
                      : t('notifications.stagedImportInvalid')}
                  </span>
                </button>
              ))}
            </motion.section>
          ) : null}

          {data && data.exams.length > 0 ? (
            <motion.section {...presets.enter} className="space-y-1.5">
              <SectionLabel icon={CalendarClock} label={t('notifications.exams')} />
              <div className="flex flex-wrap gap-1.5">
                {data.exams.map((exam) => (
                  <Badge
                    key={exam.course_id}
                    variant={exam.days_left <= 7 ? 'danger' : 'secondary'}
                    className="max-w-40 gap-1 truncate"
                  >
                    <CalendarClock className="size-3 shrink-0" aria-hidden />
                    <span className="truncate">{exam.course_title}</span>
                    <span className="tabular-nums">{t('notifications.daysLeft', { days: exam.days_left })}</span>
                  </Badge>
                ))}
              </div>
            </motion.section>
          ) : null}
        </div>
      )}
    </Popover>
  )
}

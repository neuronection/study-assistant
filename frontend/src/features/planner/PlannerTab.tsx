import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, Check, Loader2, Plus, Printer, Sparkles, Trash2, TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Spinner } from '@/components/ui/spinner'
import { getExamStatus } from '@/lib/api'
import { Stagger, StaggerItem } from '@/components/motion/Stagger'
import { PlannerWeekSheet } from './PlannerWeekSheet'
import {
  createPlanItem,
  deletePlanItem,
  generatePlan,
  listPlanItems,
  updatePlanItem,
  type PlanItem,
} from '@/lib/api'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'

const KIND_STYLES: Record<string, string> = {
  study: 'bg-primary/10 text-primary',
  practice: 'bg-warning/15 text-warning',
  review: 'bg-success/15 text-success',
  milestone: 'bg-danger/15 text-danger',
}

function todayIso(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset()
  return new Date(now.getTime() - offset * 60000).toISOString().slice(0, 10)
}

function shiftIso(iso: string, days: number): string {
  const base = new Date(`${iso}T00:00:00`)
  base.setDate(base.getDate() + days)
  return base.toISOString().slice(0, 10)
}

function dayLabel(iso: string, t: (key: string) => string): string {
  const today = todayIso()
  if (iso === today) {
    return t('planner.today')
  }
  if (iso === shiftIso(today, 1)) {
    return t('planner.tomorrow')
  }
  return formatDate(iso)
}

export function PlannerTab({ courseId }: { courseId: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDate, setNewDate] = useState(todayIso())
  const [error, setError] = useState<string | null>(null)
  const [printing, setPrinting] = useState(false)

  const plan = useQuery({
    queryKey: ['plan', courseId],
    queryFn: () => listPlanItems(Number(courseId)),
  })
  const examEntry = useQuery({
    queryKey: ['exam-status'],
    queryFn: getExamStatus,
  })
  const readiness = (examEntry.data ?? []).find(
    (entry) => entry.course_id === Number(courseId)
  )

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['plan', courseId] })
    await queryClient.invalidateQueries({ queryKey: ['plan-upcoming'] })
  }

  const generate = useMutation({
    mutationFn: () => generatePlan(Number(courseId)),
    onSuccess: () => void refresh(),
    onError: (err: Error) => setError(err.message),
  })
  const toggleDone = useMutation({
    mutationFn: ({ item, done }: { item: PlanItem; done: boolean }) =>
      updatePlanItem(Number(courseId), item.id, { done }),
    onSuccess: () => void refresh(),
  })
  const reschedule = useMutation({
    mutationFn: ({ item, dueDate }: { item: PlanItem; dueDate: string }) =>
      updatePlanItem(Number(courseId), item.id, { due_date: dueDate }),
    onSuccess: () => void refresh(),
  })
  const pushDay = (item: PlanItem) =>
    reschedule.mutate({ item, dueDate: shiftIso(item.due_date, 1) })
  const promote = useMutation({
    mutationFn: (item: PlanItem) =>
      updatePlanItem(Number(courseId), item.id, {
        title: item.title,
        due_date: item.due_date,
        kind: item.kind,
      }),
    onSuccess: () => void refresh(),
  })
  const remove = useMutation({
    mutationFn: (item: PlanItem) => deletePlanItem(Number(courseId), item.id),
    onSuccess: () => void refresh(),
  })
  const add = useMutation({
    mutationFn: () =>
      createPlanItem(Number(courseId), {
        title: newTitle.trim(),
        kind: 'study',
        due_date: newDate,
      }),
    onSuccess: async () => {
      setNewTitle('')
      setAdding(false)
      await refresh()
    },
  })

  const grouped = useMemo(() => {
    const items = plan.data ?? []
    const open = items.filter((item) => !item.done_at)
    const done = items.filter((item) => item.done_at)
    const byDay = new Map<string, PlanItem[]>()
    for (const item of open) {
      const list = byDay.get(item.due_date) ?? []
      list.push(item)
      byDay.set(item.due_date, list)
    }
    const days = [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b))
    return { days, done }
  }, [plan.data])

  return (
    <div className="space-y-4">
      {printing ? (
        <PlannerWeekSheet
          items={plan.data ?? []}
          autoPrint={false}
          onBack={() => setPrinting(false)}
        />
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground text-sm">{t('planner.hint')}</p>
        <div className="flex items-center gap-2">
          {readiness?.readiness_state === 'ok' && readiness.readiness !== null ? (
            <span
              className={cn(
                'flex items-center gap-1 rounded-full px-2 py-0.5 text-xs',
                readiness.trend === 'improving'
                  ? 'bg-success/15 text-success'
                  : readiness.trend === 'declining'
                    ? 'bg-danger/15 text-danger'
                    : 'bg-subtle text-muted-foreground'
              )}
              title={t('today.readinessTitle')}
            >
              {readiness.trend === 'improving' ? (
                <TrendingUp className="size-3.5" aria-hidden />
              ) : readiness.trend === 'declining' ? (
                <TrendingDown className="size-3.5" aria-hidden />
              ) : (
                <Minus className="size-3.5" aria-hidden />
              )}
              {t('today.readiness')} {readiness.readiness}
            </span>
          ) : null}
          <Button variant="outline" size="sm" onClick={() => setPrinting(true)}>
            <Printer aria-hidden />
            {t('planner.printWeek')}
          </Button>
          <Button variant="outline" size="sm" onClick={() => setAdding((v) => !v)}>
            <Plus aria-hidden />
            {t('planner.addItem')}
          </Button>
          <Button
            size="sm"
            disabled={generate.isPending}
            onClick={() => generate.mutate()}
          >
            {generate.isPending ? <Spinner /> : <Sparkles aria-hidden />}
            {t('planner.generate')}
          </Button>
        </div>
      </div>
      {error !== null ? (
        <p className="text-destructive text-xs" role="alert">
          {error}
        </p>
      ) : null}
      {adding ? (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-2 p-3">
            <input
              autoFocus
              className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1.5 text-sm"
              placeholder={t('planner.itemTitle')}
              value={newTitle}
              onChange={(event) => setNewTitle(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && newTitle.trim()) {
                  add.mutate()
                }
              }}
            />
            <input
              type="date"
              className="bg-surface border-border rounded-md border px-2 py-1.5 text-sm"
              value={newDate}
              onChange={(event) => setNewDate(event.target.value)}
              aria-label={t('planner.dueDate')}
            />
            <Button
              size="sm"
              disabled={!newTitle.trim() || add.isPending}
              onClick={() => add.mutate()}
            >
              {t('planner.saveItem')}
            </Button>
          </CardContent>
        </Card>
      ) : null}
      {plan.isLoading ? (
        <Spinner label={t('library.loading')} />
      ) : grouped.days.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t('planner.empty')}</p>
      ) : (
        <div className="space-y-4">
          {grouped.days.map(([day, items]) => (
            <section
              key={day}
              data-testid="plan-day"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                const id = Number(event.dataTransfer.getData('text/plan-item'))
                const item = (plan.data ?? []).find((entry) => entry.id === id)
                if (item !== undefined && item.due_date !== day) {
                  reschedule.mutate({ item, dueDate: day })
                }
              }}
            >
              <h3 className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs font-medium">
                <CalendarClock className="size-3.5" aria-hidden />
                {dayLabel(day, t)}
              </h3>
              <Stagger className="space-y-1.5">
                {items.map((item) => (
                  <StaggerItem
                    key={item.id}
                    draggable
                    onDragStart={(event) =>
                      event.dataTransfer.setData('text/plan-item', String(item.id))
                    }
                    className={cn(
                      'border-border bg-surface flex items-center gap-2 rounded-md border px-3 py-2 text-sm',
                      item.origin === 'draft' && 'border-dashed'
                    )}
                  >
                    <button
                      type="button"
                      aria-label={t('planner.checkOff')}
                      className="border-primary text-primary hover:bg-primary/10 size-4 shrink-0 rounded-full border"
                      onClick={() => toggleDone.mutate({ item, done: true })}
                    >
                      <Check className="size-3" aria-hidden />
                    </button>
                    <span
                      className={cn(
                        'rounded-full px-2 py-0.5 text-[11px]',
                        KIND_STYLES[item.kind] ?? 'bg-subtle text-muted-foreground'
                      )}
                    >
                      {t(`planner.kind_${item.kind}`)}
                    </span>
                    <span className="min-w-0 flex-1 truncate" title={item.detail ?? undefined}>
                      {item.title}
                    </span>
                    {item.origin === 'draft' ? (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => promote.mutate(item)}
                        >
                          {t('planner.keep')}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t('planner.discard')}
                          onClick={() => remove.mutate(item)}
                        >
                          <Trash2 className="size-4" aria-hidden />
                        </Button>
                      </>
                    ) : (
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={t('planner.pushOneDay')}
                        onClick={() => pushDay(item)}
                      >
                        <CalendarClock className="size-4" aria-hidden />
                      </Button>
                    )}
                  </StaggerItem>
                ))}
              </Stagger>
            </section>
          ))}
        </div>
      )}
      {grouped.done.length > 0 ? (
        <div className="space-y-1">
          <h3 className="text-muted-foreground text-xs font-medium">
            {t('planner.doneTitle')}
          </h3>
          {grouped.done.map((item) => (
            <StaggerItem
              key={item.id}
              className="border-border bg-subtle/50 flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm"
            >
              <button
                type="button"
                aria-label={t('planner.uncheck')}
                className="bg-primary text-primary-fg flex size-4 shrink-0 items-center justify-center rounded-full"
                onClick={() => toggleDone.mutate({ item, done: false })}
              >
                <Check className="size-3" aria-hidden />
              </button>
              <span className="text-muted-foreground line-through">{item.title}</span>
              <span className="ml-auto" />
              <Button
                variant="ghost"
                size="icon"
                aria-label={t('planner.delete')}
                onClick={() => remove.mutate(item)}
              >
                <Trash2 className="size-4" aria-hidden />
              </Button>
            </StaggerItem>
          ))}
        </div>
      ) : null}
      {generate.isPending ? (
        <p className="text-muted-foreground flex items-center gap-2 text-xs">
          <Loader2 className="size-3 animate-spin" aria-hidden />
          {t('planner.generating')}
        </p>
      ) : null}
    </div>
  )
}

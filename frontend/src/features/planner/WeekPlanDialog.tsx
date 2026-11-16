import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarPlus, Check, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  commitWeekPlan,
  getPlannerCapacity,
  previewWeekPlan,
  updatePlannerCapacity,
  type PlannerCapacity,
} from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

function dayLabel(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(new Date(`${iso}T12:00:00`))
}

export function WeekPlanDialog({ onClose }: { onClose: () => void }) {
  useCloseFloatings()
  const { t, i18n } = useTranslation()
  const queryClient = useQueryClient()
  const preview = useQuery({ queryKey: ['week-plan-preview'], queryFn: () => previewWeekPlan() })
  const capacity = useQuery({ queryKey: ['planner-capacity'], queryFn: getPlannerCapacity })
  const [capacityOpen, setCapacityOpen] = useState(false)
  const [draft, setDraft] = useState<PlannerCapacity | null>(null)
  const [committed, setCommitted] = useState<{ created: number; replaced: number } | null>(null)

  const saveCapacity = useMutation({
    mutationFn: (body: PlannerCapacity) => updatePlannerCapacity(body),
    onSuccess: async () => {
      setCapacityOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['planner-capacity'] })
      await queryClient.invalidateQueries({ queryKey: ['week-plan-preview'] })
    },
  })
  const commit = useMutation({
    mutationFn: () => commitWeekPlan(),
    onSuccess: async (result) => {
      setCommitted(result)
      await queryClient.invalidateQueries({ queryKey: ['plan'] })
      await queryClient.invalidateQueries({ queryKey: ['upcoming'] })
    },
  })

  const current = draft ?? capacity.data ?? null
  const locale = i18n.language

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={t('plan.weekTitle')}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose()
        }
      }}
    >
      <div className="bg-surface border-border flex max-h-[85vh] w-full max-w-2xl flex-col rounded-lg border shadow-[var(--as-shadow-3)]">
        <header className="border-border flex items-center justify-between border-b px-4 py-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <CalendarPlus className="text-primary size-4" aria-hidden />
            {t('plan.weekTitle')}
          </h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            {t('captureInbox.close')}
          </Button>
        </header>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          <p className="text-muted-foreground text-xs">{t('plan.weekDescription')}</p>

          {capacityOpen && current !== null ? (
            <div className="border-border rounded-md border p-3">
              <p className="mb-2 text-xs font-medium">{t('plan.capacityTitle')}</p>
              <div className="grid grid-cols-7 gap-1">
                {current.minutes.map((minutes, index) => (
                  <label key={index} className="space-y-1">
                    <span className="text-muted-foreground block text-[10px]">
                      {new Intl.DateTimeFormat(locale, { weekday: 'short' }).format(
                        new Date(2026, 10, 9 + index)
                      )}
                    </span>
                    <input
                      type="number"
                      min={0}
                      max={720}
                      value={minutes}
                      onChange={(event) => {
                        const next = [...current.minutes]
                        next[index] = Number(event.target.value)
                        setDraft({ ...current, minutes: next })
                      }}
                      className="bg-surface border-border w-full rounded-md border px-1 py-0.5 text-xs"
                      aria-label={t('plan.minutesFor', { day: index + 1 })}
                    />
                  </label>
                ))}
              </div>
              <div className="mt-2 flex items-center gap-3">
                <label className="flex items-center gap-1 text-xs">
                  <input
                    type="checkbox"
                    checked={current.light_week}
                    onChange={(event) =>
                      setDraft({ ...current, light_week: event.target.checked })
                    }
                  />
                  {t('plan.lightWeek')}
                </label>
                <Button
                  size="sm"
                  disabled={saveCapacity.isPending}
                  onClick={() => saveCapacity.mutate(current)}
                >
                  {t('plan.saveCapacity')}
                </Button>
              </div>
            </div>
          ) : null}

          {preview.data === undefined ? (
            <div className="flex justify-center py-8">
              <Loader2 className="text-muted-foreground size-5 animate-spin" aria-hidden />
            </div>
          ) : (
            <div className="space-y-2">
              {preview.data.days.map((day) => (
                <div key={day.day} className="border-border rounded-md border">
                  <div className="border-border flex items-center justify-between border-b px-3 py-1.5">
                    <span className="text-xs font-medium">{dayLabel(day.day, locale)}</span>
                    <span className="text-muted-foreground text-[11px] tabular-nums">
                      {t('plan.dayMinutes', { minutes: day.minutes })}
                    </span>
                  </div>
                  <ul className="divide-border divide-y">
                    {day.items.length === 0 ? (
                      <li className="text-muted-foreground px-3 py-2 text-[11px]">
                        {t('plan.free')}
                      </li>
                    ) : (
                      day.items.map((item, index) => (
                        <li
                          key={`${item.title}-${index}`}
                          className="flex items-start gap-2 px-3 py-2"
                        >
                          <span
                            className={`mt-0.5 rounded-full px-1.5 py-0.5 text-[10px] ${
                              item.fixed
                                ? 'bg-subtle text-muted-foreground'
                                : 'bg-primary/10 text-primary'
                            }`}
                          >
                            {item.kind}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-xs">{item.title}</p>
                            <p className="text-muted-foreground text-[11px]">
                              {item.course_title} · {item.evidence}
                            </p>
                          </div>
                          <span className="text-muted-foreground text-[11px] tabular-nums">
                            {t('plan.itemMinutes', { minutes: item.minutes })}
                          </span>
                        </li>
                      ))
                    )}
                  </ul>
                </div>
              ))}
              {preview.data.overflow > 0 ? (
                <p className="text-warning text-xs">
                  {t('plan.overflow', { count: preview.data.overflow })}
                </p>
              ) : null}
            </div>
          )}
        </div>
        <footer className="border-border flex items-center gap-2 border-t px-4 py-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setDraft(capacity.data ?? null)
              setCapacityOpen((previous) => !previous)
            }}
          >
            {t('plan.capacityAction')}
          </Button>
          <div className="ml-auto flex items-center gap-2">
            {committed !== null ? (
              <span className="text-success flex items-center gap-1 text-xs" role="status">
                <Check className="size-3.5" aria-hidden />
                {t('plan.committed', { count: committed.created })}
              </span>
            ) : null}
            <Button
              size="sm"
              disabled={commit.isPending || preview.data === undefined}
              onClick={() => commit.mutate()}
            >
              {commit.isPending ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}
              {t('plan.commit')}
            </Button>
          </div>
        </footer>
      </div>
    </div>
  )
}

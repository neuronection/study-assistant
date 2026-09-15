import { motion } from 'framer-motion'
import { CalendarClock, Check } from 'lucide-react'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import type { PlanItem } from '@/lib/api'
import { cn } from '@/lib/utils'

export const PLAN_DRAG_TYPE = 'text/plan-item'

export function weekDays(todayIso: string): string[] {
  const base = new Date(`${todayIso}T00:00:00`)
  const weekday = (base.getDay() + 6) % 7
  base.setDate(base.getDate() - weekday)
  const days: string[] = []
  for (let index = 0; index < 7; index += 1) {
    const day = new Date(base)
    day.setDate(base.getDate() + index)
    const offset = day.getTimezoneOffset()
    days.push(new Date(day.getTime() - offset * 60000).toISOString().slice(0, 10))
  }
  return days
}

const WEEKDAY_KEYS = [
  'planner.weekday_mon',
  'planner.weekday_tue',
  'planner.weekday_wed',
  'planner.weekday_thu',
  'planner.weekday_fri',
  'planner.weekday_sat',
  'planner.weekday_sun',
]

export function PlannerWeekView({
  items,
  todayIso,
  onMove,
  onToggleDone,
}: {
  items: PlanItem[]
  todayIso: string
  onMove: (item: PlanItem, day: string) => void
  onToggleDone: (item: PlanItem) => void
}) {
  const { t } = useTranslation()
  const days = useMemo(() => weekDays(todayIso), [todayIso])
  const daySet = useMemo(() => new Set(days), [days])

  const byDay = useMemo(() => {
    const map = new Map<string, PlanItem[]>()
    for (const item of items) {
      if (!daySet.has(item.due_date)) {
        continue
      }
      const list = map.get(item.due_date) ?? []
      list.push(item)
      map.set(item.due_date, list)
    }
    return map
  }, [items, daySet])

  return (
    <div className="overflow-x-auto pb-1">
      <div
        className="grid min-w-[42rem] grid-cols-7 gap-2"
        role="grid"
        aria-label={t('planner.weekView')}
      >
        {days.map((day, index) => {
          const dayItems = byDay.get(day) ?? []
          const isToday = day === todayIso
          return (
            <div
              key={day}
              role="gridcell"
              data-testid="week-day"
              data-day={day}
              aria-label={day}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                const id = Number(event.dataTransfer.getData(PLAN_DRAG_TYPE))
                const item = items.find((entry) => entry.id === id)
                if (item !== undefined && item.due_date !== day) {
                  onMove(item, day)
                }
              }}
              className={cn(
                'border-border min-h-28 rounded-lg border p-1.5 transition-colors',
                isToday ? 'border-primary bg-primary/5' : 'bg-surface'
              )}
            >
              <p
                className={cn(
                  'mb-1.5 flex items-center gap-1 text-[11px] font-medium',
                  isToday ? 'text-primary' : 'text-muted-foreground'
                )}
              >
                {isToday ? <CalendarClock className="size-3" aria-hidden /> : null}
                {t(WEEKDAY_KEYS[index])}
                <span className="tabular-nums">{day.slice(8)}</span>
              </p>
              <motion.div layout className="space-y-1.5">
                {dayItems.map((item) => {
                  const done = item.done_at !== null
                  const overdue = !done && item.due_date < todayIso
                  return (
                    <motion.div
                      key={item.id}
                      layout
                      draggable
                      onDragStart={(event) => {
                        const transfer = (event as unknown as React.DragEvent).dataTransfer
                        transfer?.setData(PLAN_DRAG_TYPE, String(item.id))
                      }}
                      className={cn(
                        'border-border bg-surface cursor-grab rounded-md border px-2 py-1.5 text-xs shadow-sm transition-colors',
                        overdue && 'border-l-warning border-l-4',
                        done && 'opacity-60'
                      )}
                    >
                      <div className="flex items-start gap-1.5">
                        <button
                          type="button"
                          aria-label={done ? t('planner.uncheck') : t('planner.checkOff')}
                          className={cn(
                            'mt-0.5 flex size-3.5 shrink-0 items-center justify-center rounded-full border',
                            done
                              ? 'bg-primary border-primary text-primary-fg'
                              : 'border-primary text-primary hover:bg-primary/10'
                          )}
                          onClick={() => onToggleDone(item)}
                        >
                          <Check className="size-2.5" aria-hidden />
                        </button>
                        <span
                          className={cn(
                            'min-w-0 flex-1 break-words',
                            done && 'text-muted-foreground line-through'
                          )}
                        >
                          {item.title}
                        </span>
                      </div>
                    </motion.div>
                  )
                })}
              </motion.div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

import { useMemo } from 'react'
import { ArrowLeft, Printer } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { PrintDoc, useAutoPrint } from '@/components/print/PrintDoc'
import { Button } from '@/components/ui/button'
import type { PlanItem } from '@/lib/api'
import { formatWeekdayLong } from '@/lib/format'

function mondayOf(date: Date): Date {
  const copy = new Date(date)
  const day = (copy.getDay() + 6) % 7
  copy.setDate(copy.getDate() - day)
  copy.setHours(0, 0, 0, 0)
  return copy
}

function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10)
}

export function PlannerWeekSheet({
  items,
  autoPrint = true,
  onBack,
}: {
  items: PlanItem[]
  autoPrint?: boolean
  onBack?: () => void
}) {
  const { t } = useTranslation()
  useAutoPrint(autoPrint)

  const days = useMemo(() => {
    const monday = mondayOf(new Date())
    return Array.from({ length: 7 }, (_, index) => {
      const date = new Date(monday)
      date.setDate(monday.getDate() + index)
      const key = isoDay(date)
      return {
        key,
        date,
        items: items.filter((item) => item.due_date === key),
      }
    })
  }, [items])

  return (
    <PrintDoc
      title={t('print.weekSheet', { week: isoDay(mondayOf(new Date())) })}
      contextLine={t('print.generatedBy')}
      toolbar={
        <div className="flex gap-2">
          {onBack ? (
            <Button variant="outline" size="sm" onClick={onBack}>
              <ArrowLeft aria-hidden />
              {t('common.back')}
            </Button>
          ) : null}
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer aria-hidden />
            {t('library.printDoc')}
          </Button>
        </div>
      }
    >
      {days.map((day) => (
        <div key={day.key} className="print-question">
          <h2 className="mb-1 text-sm font-semibold">{formatWeekdayLong(day.date)}</h2>
          {day.items.length === 0 ? (
            <p className="text-muted-foreground text-xs">—</p>
          ) : (
            <ul className="ml-4 list-disc">
              {day.items.map((item) => (
                <li key={item.id}>
                  {item.title}
                  <span className="text-muted-foreground text-xs"> · {item.kind}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </PrintDoc>
  )
}

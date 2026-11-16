import { useQuery } from '@tanstack/react-query'
import { Activity, CalendarClock, TrendingUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getRetention, getWorkload } from '@/lib/api'

function percent(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}

export function RetentionTab() {
  const { t } = useTranslation()
  const retention = useQuery({ queryKey: ['analytics-retention'], queryFn: () => getRetention(90) })
  const workload = useQuery({ queryKey: ['analytics-workload'], queryFn: () => getWorkload(30) })
  const report = retention.data
  const peak = Math.max(1, ...(workload.data?.days.map((day) => day.due) ?? [1]))

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <TrendingUp className="size-4" aria-hidden />
            {t('scores.retention.title')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {report === undefined || report.reviews === 0 ? (
            <p className="text-muted-foreground text-sm">{t('scores.retention.empty')}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-end gap-6">
                <div>
                  <p className="text-muted-foreground text-xs">{t('scores.retention.actual')}</p>
                  <p className="text-3xl font-semibold tabular-nums">
                    {percent(report.retention)}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">{t('scores.retention.target')}</p>
                  <p className="text-lg tabular-nums">{percent(report.target)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">{t('scores.retention.reviews')}</p>
                  <p className="text-lg tabular-nums">{report.reviews}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs">{t('scores.retention.lapses')}</p>
                  <p className="text-lg tabular-nums">{report.lapses}</p>
                </div>
              </div>
              <div className="space-y-2">
                {report.buckets.map((bucket) => (
                  <div key={bucket.key} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span>{t(`scores.retention.bucket.${bucket.key}`)}</span>
                      <span className="text-muted-foreground tabular-nums">
                        {percent(bucket.retention)} · {bucket.reviews}
                      </span>
                    </div>
                    <div className="bg-subtle h-1.5 overflow-hidden rounded-full">
                      <div
                        className="bg-primary h-full rounded-full"
                        style={{ width: `${Math.round(bucket.retention * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="text-muted-foreground text-xs">{t('scores.retention.hint')}</p>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <CalendarClock className="size-4" aria-hidden />
            {t('scores.workload.title')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {workload.data === undefined ? (
            <p className="text-muted-foreground text-sm">{t('scores.workload.loading')}</p>
          ) : (
            <>
              <div className="flex items-end gap-1" aria-hidden>
                {workload.data.days.map((day) => (
                  <div
                    key={day.day}
                    title={`${day.day}: ${day.due}`}
                    className="bg-primary/70 min-h-0.5 flex-1 rounded-sm"
                    style={{ height: `${Math.max(2, (day.due / peak) * 48)}px` }}
                  />
                ))}
              </div>
              <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
                <span>
                  {t('scores.workload.total', { count: workload.data.total })}
                </span>
                <span>
                  {t('scores.workload.new', { count: workload.data.new_available })}
                </span>
                {workload.data.peak_day !== null ? (
                  <span>
                    {t('scores.workload.peak', {
                      count: workload.data.peak_count,
                      day: workload.data.peak_day,
                    })}
                  </span>
                ) : null}
              </div>
              <p className="text-muted-foreground flex items-center gap-1 text-[11px]">
                <Activity className="size-3" aria-hidden />
                {t('scores.workload.hint')}
              </p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

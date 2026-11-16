import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock3 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { CheckIndicator } from '@/components/ui/CheckIndicator'
import { getProfilePreferences, updateProfilePreferences } from '@/lib/api'

export function DailyBriefCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const prefs = useQuery({ queryKey: ['profile-preferences'], queryFn: getProfilePreferences })
  const [enabled, setEnabled] = useState(false)
  const [time, setTime] = useState('07:00')
  const [length, setLength] = useState(5)
  useEffect(() => {
    if (prefs.data?.daily_brief) {
      setEnabled(Boolean(prefs.data.daily_brief.enabled))
      setTime(prefs.data.daily_brief.time || '07:00')
      setLength(prefs.data.daily_brief.length_minutes || 5)
    }
  }, [prefs.data?.daily_brief])
  const save = useMutation({
    mutationFn: () =>
      updateProfilePreferences({
        daily_brief: { enabled, time, length_minutes: length },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['profile-preferences'] })
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Clock3 className="text-primary size-4" aria-hidden />
          {t('settings.dailyBriefTitle')}
        </CardTitle>
        <CardDescription>{t('settings.dailyBriefDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="max-w-md space-y-3">
        <div className="flex items-center gap-2">
          <CheckIndicator
            checked={enabled}
            label={t('settings.dailyBriefToggle')}
            onToggle={() => setEnabled((value) => !value)}
          />
          <span className="text-foreground text-xs">{t('settings.dailyBriefToggle')}</span>
        </div>
        <label className="flex items-center justify-between gap-2 text-xs">
          <span className="text-muted-foreground">{t('settings.dailyBriefTime')}</span>
          <input
            type="time"
            value={time}
            onChange={(event) => setTime(event.target.value)}
            className="bg-surface border-border rounded-md border px-2 py-1"
          />
        </label>
        <label className="flex items-center justify-between gap-2 text-xs">
          <span className="text-muted-foreground">{t('settings.dailyBriefLength')}</span>
          <select
            value={length}
            onChange={(event) => setLength(Number(event.target.value))}
            className="bg-surface border-border rounded-md border px-2 py-1"
          >
            {[5, 10, 20].map((value) => (
              <option key={value} value={value}>
                {t('settings.dailyBriefMinutes', { count: value })}
              </option>
            ))}
          </select>
        </label>
        <p className="text-muted-foreground text-[11px]">{t('settings.dailyBriefHint')}</p>
        <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
          {t('settings.dailyBriefSave')}
        </Button>
        {save.isError ? (
          <p className="text-danger text-xs">{(save.error as Error).message}</p>
        ) : null}
      </CardContent>
    </Card>
  )
}

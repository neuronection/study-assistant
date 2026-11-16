import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Gauge, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { CheckIndicator } from '@/components/ui/CheckIndicator'
import {
  getFsrsSettings,
  updateFsrsSettings,
  type FsrsSettings,
  type FsrsSettingsInput,
} from '@/lib/api'

const PRESETS: Record<'light' | 'standard' | 'intense', Partial<FsrsSettings>> = {
  light: { desired_retention: 0.85, new_per_day: 10, reviews_per_day: 100 },
  standard: { desired_retention: 0.9, new_per_day: 20, reviews_per_day: 200 },
  intense: { desired_retention: 0.95, new_per_day: 40, reviews_per_day: 400 },
}

export function FsrsSettingsCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['fsrs-settings'], queryFn: getFsrsSettings })
  const [draft, setDraft] = useState<FsrsSettings | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (settings.data !== undefined) {
      setDraft(settings.data)
    }
  }, [settings.data])

  const save = useMutation({
    mutationFn: (body: FsrsSettingsInput) => updateFsrsSettings(body),
    onSuccess: async (data) => {
      setDraft(data)
      setSaved(true)
      await queryClient.invalidateQueries({ queryKey: ['fsrs-settings'] })
    },
  })

  if (draft === null) {
    return null
  }
  const update = (patch: Partial<FsrsSettings>) => {
    setSaved(false)
    setDraft((previous) => (previous === null ? previous : { ...previous, ...patch }))
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Gauge className="text-primary size-4" aria-hidden />
          {t('settings.studyPaceTitle')}
        </CardTitle>
        <CardDescription>{t('settings.studyPaceDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="max-w-md space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {(['light', 'standard', 'intense'] as const).map((preset) => (
            <Button
              key={preset}
              size="sm"
              variant={draft.desired_retention === PRESETS[preset].desired_retention ? 'default' : 'outline'}
              onClick={() => update(PRESETS[preset])}
            >
              {t(`settings.studyPace.${preset}`)}
            </Button>
          ))}
        </div>

        <label className="block space-y-1">
          <span className="flex items-center justify-between text-xs">
            <span>{t('settings.retentionTarget')}</span>
            <span className="text-muted-foreground tabular-nums">
              {Math.round(draft.desired_retention * 100)}%
            </span>
          </span>
          <input
            type="range"
            min={70}
            max={97}
            value={Math.round(draft.desired_retention * 100)}
            onChange={(event) =>
              update({ desired_retention: Number(event.target.value) / 100 })
            }
            className="accent-primary w-full"
            aria-label={t('settings.retentionTarget')}
          />
          <span className="text-muted-foreground block text-[11px]">
            {t('settings.retentionHint')}
          </span>
        </label>

        <details className="text-xs">
          <summary className="cursor-pointer select-none">
            {t('settings.studyPaceAdvanced')}
          </summary>
          <div className="grid grid-cols-2 gap-2 pt-2">
            <label className="space-y-1">
              <span className="text-muted-foreground">{t('settings.maxInterval')}</span>
              <input
                type="number"
                min={30}
                max={3650}
                value={draft.maximum_interval_days}
                onChange={(event) =>
                  update({ maximum_interval_days: Number(event.target.value) })
                }
                className="bg-surface border-border w-full rounded-md border px-2 py-1"
              />
            </label>
            <label className="space-y-1">
              <span className="text-muted-foreground">{t('settings.newPerDay')}</span>
              <input
                type="number"
                min={0}
                max={999}
                value={draft.new_per_day}
                onChange={(event) => update({ new_per_day: Number(event.target.value) })}
                className="bg-surface border-border w-full rounded-md border px-2 py-1"
              />
            </label>
            <label className="space-y-1">
              <span className="text-muted-foreground">{t('settings.reviewsPerDay')}</span>
              <input
                type="number"
                min={0}
                max={9999}
                value={draft.reviews_per_day}
                onChange={(event) =>
                  update({ reviews_per_day: Number(event.target.value) })
                }
                className="bg-surface border-border w-full rounded-md border px-2 py-1"
              />
            </label>
            <label className="space-y-1">
              <span className="text-muted-foreground">{t('settings.leechThreshold')}</span>
              <input
                type="number"
                min={1}
                max={20}
                value={draft.leech_threshold}
                onChange={(event) =>
                  update({ leech_threshold: Number(event.target.value) })
                }
                className="bg-surface border-border w-full rounded-md border px-2 py-1"
              />
            </label>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <CheckIndicator
              checked={draft.bury_siblings}
              label={t('settings.burySiblings')}
              onToggle={() => update({ bury_siblings: !draft.bury_siblings })}
            />
            <span>{t('settings.burySiblings')}</span>
          </div>
          <div className="mt-1 flex items-center gap-2">
            <CheckIndicator
              checked={draft.load_balance}
              label={t('settings.loadBalance')}
              onToggle={() => update({ load_balance: !draft.load_balance })}
            />
            <span>{t('settings.loadBalance')}</span>
          </div>
        </details>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            disabled={save.isPending}
            onClick={() =>
              save.mutate({
                desired_retention: draft.desired_retention,
                maximum_interval_days: draft.maximum_interval_days,
                new_per_day: draft.new_per_day,
                reviews_per_day: draft.reviews_per_day,
                leech_threshold: draft.leech_threshold,
                leech_action: draft.leech_action as 'tag' | 'suspend' | 'none',
                bury_siblings: draft.bury_siblings,
                load_balance: draft.load_balance,
              })
            }
          >
            <Save className="size-3.5" aria-hidden />
            {t('settings.studyPaceSave')}
          </Button>
          {saved ? (
            <span className="text-success text-xs" role="status">
              {t('settings.studyPaceSaved')}
            </span>
          ) : null}
          {save.isError ? (
            <span className="text-danger text-xs" role="alert">
              {t('settings.studyPaceFailed')}
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

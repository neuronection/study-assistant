import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Sparkles, Trash2 } from 'lucide-react'
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
import { loadInstanceConfig } from '@/components/layout/DemoBanner'
import { clearFirstEventKeys } from '@/lib/activation-events'
import {
  clearActivation,
  exportActivation,
  getActivationSummary,
} from '@/lib/api'
import { getLastSessionScope } from '@/lib/session-scope'

export function UsageInsightsCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [identityMode, setIdentityMode] = useState<string | undefined>(undefined)
  const summary = useQuery({
    queryKey: ['activation-summary'],
    queryFn: getActivationSummary,
  })
  const clear = useMutation({
    mutationFn: async () => {
      const scope = getLastSessionScope()
      await clearActivation()
      clearFirstEventKeys(scope)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['activation-summary'] })
    },
  })
  const download = useMutation({
    mutationFn: exportActivation,
    onSuccess: (payload) => {
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'activation-events.json'
      anchor.click()
      URL.revokeObjectURL(url)
    },
  })
  const data = summary.data

  useEffect(() => {
    let alive = true
    void loadInstanceConfig().then((config) => {
      if (alive) setIdentityMode(config?.identity_mode)
    })
    return () => {
      alive = false
    }
  }, [])

  const disclosure =
    identityMode === undefined
      ? null
      : identityMode === 'desktop'
        ? t('settings.usageInsightsStorageDevice')
        : t('settings.usageInsightsStorageServer')

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Sparkles className="text-primary size-4" aria-hidden />
          {t('settings.usageInsightsTitle')}
        </CardTitle>
        <CardDescription>{t('settings.usageInsightsDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="max-w-md space-y-2">
        {disclosure ? (
          <p className="text-muted-foreground text-xs">{disclosure}</p>
        ) : null}
        {data ? (
          <>
            <p className="text-sm">
              {t('settings.usageInsightsTotal', { count: data.total })}
            </p>
            <ul className="space-y-1">
              {data.counts.slice(0, 6).map((row) => (
                <li key={row.event} className="flex justify-between text-xs">
                  <span>{row.event}</span>
                  <span className="text-muted-foreground">{row.count}</span>
                </li>
              ))}
            </ul>
          </>
        ) : null}
        <div className="flex flex-wrap gap-1">
          <Button
            size="sm"
            variant="outline"
            disabled={download.isPending || (data?.total ?? 0) === 0}
            onClick={() => download.mutate()}
          >
            <Download className="size-3.5" aria-hidden />
            {t('settings.usageInsightsExport')}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={clear.isPending || (data?.total ?? 0) === 0}
            onClick={() => clear.mutate()}
          >
            <Trash2 className="size-3.5" aria-hidden />
            {t('settings.usageInsightsClear')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

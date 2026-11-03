import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { getRetrievalOverview } from '@/lib/api'
import { getCurrentUser } from '@/lib/auth-session'

function stateKey(state: string) {
  if (state === 'ready') return 'retrievalStateReady'
  if (state === 'degraded') return 'retrievalStateDegraded'
  if (state === 'cold') return 'retrievalStateCold'
  return 'retrievalStateEmpty'
}

export function RetrievalStatusCard() {
  const { t } = useTranslation()
  const isAdmin = getCurrentUser()?.is_admin ?? false
  const overview = useQuery({
    queryKey: ['retrieval-overview'],
    queryFn: getRetrievalOverview,
    enabled: isAdmin,
    retry: false,
    staleTime: 60_000,
  })

  if (!isAdmin) return null

  const data = overview.data
  const coverage = data?.coverage.coverage

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t('settings.retrievalStatusTitle')}</CardTitle>
        <CardDescription>{t('settings.retrievalStatusDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        {overview.isLoading ? (
          <span className="text-muted-foreground flex items-center gap-2">
            <Loader2 className="animate-spin" aria-hidden />
            {t('settings.retrievalStatusLoading')}
          </span>
        ) : null}
        {overview.isError ? (
          <p className="text-muted-foreground">{t('settings.retrievalStatusUnavailable')}</p>
        ) : null}
        {data ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>{t(`settings.${stateKey(data.state)}`)}</span>
              <span className="text-muted-foreground text-xs">
                {data.backend_label ?? t('settings.retrievalBackendUnknown')}
              </span>
            </div>
            {data.space ? (
              <p className="text-muted-foreground text-xs">
                {t('settings.retrievalCounts', {
                  documents: data.space.documents,
                  records: data.space.records,
                })}
              </p>
            ) : null}
            {coverage !== null && coverage !== undefined ? (
              <p className="text-muted-foreground text-xs">
                {t('settings.retrievalCoverage', {
                  percent: Math.round(coverage * 100),
                })}
              </p>
            ) : null}
            {data.notes?.[0] ? (
              <p className="text-muted-foreground text-[11px]">{data.notes[0]}</p>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

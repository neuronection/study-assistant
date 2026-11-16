import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  ConnectionTestRow,
  type ConnectionTestStatus,
} from '@/components/ui/connection-test-row'
import { getStorageStatus } from '@/lib/api'
import { getCurrentUser } from '@/lib/auth-session'
import { desktopBridge } from '@/lib/desktop-bridge'
import { formatDateTime } from '@/lib/format'

const QUERY_KEY = ['storage-status'] as const

/** Read-only deployment storage facts (plan 55 P4b2).
 *
 * Object storage is instance configuration, not a user setting: there is no
 * credential field, no provider tile and no backend switcher. The card shows
 * what the process resolved plus a live, cached health row; changing the
 * backend is a verified migration, not a save. Desktop (and non-admins)
 * render nothing. */
export function StorageStatusCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const isAdmin = getCurrentUser()?.is_admin ?? false
  const isDesktop = desktopBridge() !== undefined

  const status = useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => getStorageStatus(false),
    enabled: isAdmin && !isDesktop,
    retry: false,
    staleTime: 30_000,
  })

  const test = useMutation({
    mutationFn: () => getStorageStatus(true),
    onSuccess: (fresh) => {
      queryClient.setQueryData(QUERY_KEY, fresh)
    },
  })

  if (!isAdmin || isDesktop || status.data?.entrypoint === 'desktop') {
    return null
  }

  const data = status.data
  const error = test.error ?? status.error
  const connectionStatus: ConnectionTestStatus = test.isPending || status.isPending
    ? 'testing'
    : error
      ? 'fail'
      : data
        ? data.status === 'ok'
          ? 'ok'
          : 'fail'
        : 'idle'
  const target = data?.bucket ?? data?.container
  const location =
    data === undefined
      ? null
      : data.backend === 'local'
        ? t('settings.storage.localVolume')
        : [data.region, data.endpoint_host].filter(Boolean).join(' · ') ||
          t('settings.storage.providerDefault')
  const failureLabel =
    data?.status === 'degraded'
      ? t('settings.storage.degraded')
      : t('settings.storage.unavailable')

  return (
    <Card data-testid="storage-status-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          {t('settings.storage.title')}
          {data ? (
            <Badge variant="outline" className="font-mono text-xs">
              {data.backend}
            </Badge>
          ) : null}
        </CardTitle>
        <CardDescription>{t('settings.storage.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {status.isPending ? (
          <p className="text-muted-foreground text-xs" role="status">
            {t('settings.storage.loading')}
          </p>
        ) : null}
        {error ? (
          <p className="text-danger text-xs" role="alert">
            {error instanceof Error && error.message
              ? error.message
              : t('settings.storage.error')}
          </p>
        ) : null}
        {data ? (
          <>
            <dl className="border-border divide-border divide-y rounded-md border text-xs">
              <div className="flex items-center justify-between gap-3 px-3 py-2">
                <dt className="text-muted-foreground">{t('settings.storage.backend')}</dt>
                <dd className="font-mono">{data.backend}</dd>
              </div>
              <div className="flex items-center justify-between gap-3 px-3 py-2">
                <dt className="text-muted-foreground">{t('settings.storage.target')}</dt>
                <dd className="truncate font-mono">
                  {target ?? (data.backend === 'local'
                    ? t('settings.storage.localVolume')
                    : t('settings.storage.none'))}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3 px-3 py-2">
                <dt className="text-muted-foreground">{t('settings.storage.prefix')}</dt>
                <dd className="truncate font-mono">
                  {data.prefix || t('settings.storage.none')}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3 px-3 py-2">
                <dt className="text-muted-foreground">{t('settings.storage.location')}</dt>
                <dd className="truncate text-right font-mono">{location}</dd>
              </div>
              <div className="flex items-center justify-between gap-3 px-3 py-2">
                <dt className="text-muted-foreground">{t('settings.storage.sse')}</dt>
                <dd className="font-mono">
                  {data.sse === 'n/a' ? t('settings.storage.notApplicable') : data.sse}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3 px-3 py-2">
                <dt className="text-muted-foreground">{t('settings.storage.maxObject')}</dt>
                <dd className="font-mono">
                  {t('settings.storage.megabytes', { value: data.max_object_mb })}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3 px-3 py-2">
                <dt className="text-muted-foreground">{t('settings.storage.presignTtl')}</dt>
                <dd className="font-mono">
                  {t('settings.storage.seconds', { value: data.presign_ttl_seconds })}
                </dd>
              </div>
            </dl>
            <ConnectionTestRow
              variant="inline"
              label={t('settings.storage.health')}
              status={connectionStatus}
              testLabel={t('settings.storage.test')}
              okLabel={t('settings.storage.healthy')}
              failLabel={failureLabel}
              idleLabel={t('settings.storage.notChecked')}
              errorMessage={data.detail}
              meta={
                data.checked_at
                  ? t('settings.storage.checkedAt', {
                      time: formatDateTime(data.checked_at),
                    })
                  : null
              }
              onTest={() => test.mutate()}
              disabled={test.isPending}
            />
            <p className="text-muted-foreground text-xs">
              {t('settings.storage.readOnly')}
            </p>
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}

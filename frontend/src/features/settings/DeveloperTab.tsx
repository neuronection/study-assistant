import { useMutation, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { getHealth } from '@/lib/api'
import {
  clearAllScopedAudioCaches,
  getAudioCacheDiagnostics,
} from '@/lib/audio-offline'
import packageJson from '../../../package.json'

export function DeveloperTab() {
  const { t } = useTranslation()
  const health = useQuery({ queryKey: ['health'], queryFn: () => getHealth() })
  const audioCache = useQuery({
    queryKey: ['audio-cache-diagnostics'],
    queryFn: getAudioCacheDiagnostics,
  })
  const clearAudioCache = useMutation({
    mutationFn: clearAllScopedAudioCaches,
    onSuccess: async () => {
      await audioCache.refetch()
    },
  })
  const cache = audioCache.data

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-sm font-medium">{t('developer.title')}</h2>
        <p className="text-muted-foreground mt-1 text-xs">{t('developer.subtitle')}</p>
      </header>
      <dl className="border-border divide-border divide-y rounded-md border text-xs">
        <div className="flex items-center justify-between px-3 py-2">
          <dt className="text-muted-foreground">{t('developer.version')}</dt>
          <dd className="font-mono">{packageJson.version}</dd>
        </div>
        <div className="flex items-center justify-between px-3 py-2">
          <dt className="text-muted-foreground">{t('developer.backend')}</dt>
          <dd className="font-mono">
            {health.isPending
              ? t('developer.checking')
              : health.data?.status === 'ok'
                ? t('developer.online')
                : t('developer.offline')}
          </dd>
        </div>
        {health.data ? (
          <div className="flex items-center justify-between px-3 py-2">
            <dt className="text-muted-foreground">{t('developer.build')}</dt>
            <dd className="font-mono">{health.data.version}</dd>
          </div>
        ) : null}
      </dl>

      <section aria-label={t('developer.audioCacheTitle')} className="space-y-2">
        <div>
          <h3 className="text-sm font-medium">{t('developer.audioCacheTitle')}</h3>
          <p className="text-muted-foreground text-xs">
            {t('developer.audioCacheDescription')}
          </p>
        </div>
        <dl className="border-border divide-border divide-y rounded-md border text-xs">
          <div className="flex items-center justify-between px-3 py-2">
            <dt className="text-muted-foreground">{t('developer.audioCacheStatus')}</dt>
            <dd>
              {cache?.supported
                ? t('developer.audioCacheSupported')
                : t('developer.audioCacheUnsupported')}
            </dd>
          </div>
          <div className="flex items-center justify-between px-3 py-2">
            <dt className="text-muted-foreground">{t('developer.audioCacheScopes')}</dt>
            <dd className="font-mono">{cache?.scopes.length ?? 0}</dd>
          </div>
          {cache?.lastError ? (
            <div className="flex items-center justify-between gap-3 px-3 py-2">
              <dt className="text-muted-foreground">{t('developer.audioCacheLastError')}</dt>
              <dd className="text-danger truncate font-mono">{cache.lastError}</dd>
            </div>
          ) : null}
        </dl>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={clearAudioCache.isPending || !cache?.supported}
            onClick={() => clearAudioCache.mutate()}
          >
            {t('developer.audioCacheClear')}
          </Button>
          {clearAudioCache.isSuccess ? (
            <p className="text-muted-foreground text-xs">
              {t('developer.audioCacheCleared')}
            </p>
          ) : null}
          {clearAudioCache.isError ? (
            <p className="text-danger text-xs">{t('developer.audioCacheClearFailed')}</p>
          ) : null}
        </div>
      </section>
    </div>
  )
}

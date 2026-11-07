import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { getHealth } from '@/lib/api'
import packageJson from '../../../package.json'

export function DeveloperTab() {
  const { t } = useTranslation()
  const health = useQuery({ queryKey: ['health'], queryFn: () => getHealth() })

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
    </div>
  )
}

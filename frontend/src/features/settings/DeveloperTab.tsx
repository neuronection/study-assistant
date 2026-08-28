import { useTranslation } from 'react-i18next'

import { SpikeContent } from '@/features/spike/SpikePage'

export function DeveloperTab() {
  const { t } = useTranslation()
  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-sm font-medium">{t('spike.title')}</h2>
        <p className="text-muted-foreground mt-1 text-xs">{t('spike.subtitle')}</p>
      </header>
      <SpikeContent />
    </div>
  )
}
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { listProviders } from '@/lib/api'
import { ProviderSetupConnect } from '@/features/settings/provider-setup/ProviderSetupConnect'

export function ProviderStep({
  hasProvider,
  onDone,
}: {
  hasProvider: boolean
  onDone: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const providers = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const configured = (providers.data ?? [])
    .map((provider) => provider.preset_key)
    .filter((key): key is string => Boolean(key))

  const handleConnected = () => {
    void queryClient.invalidateQueries({ queryKey: ['onboarding-state'] })
    onDone()
  }

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">{t('onboarding.providerHint')}</p>
      {hasProvider ? (
        <p className="border-border bg-subtle rounded-md border px-3 py-2 text-xs">
          {t('onboarding.providerAlready')}
        </p>
      ) : null}
      <ProviderSetupConnect
        showName={false}
        showHosting={false}
        showCountry={false}
        showSteps={false}
        bindDefaults
        configured={configured}
        onConnected={handleConnected}
      />
    </div>
  )
}

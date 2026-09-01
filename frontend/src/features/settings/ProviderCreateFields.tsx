import { useTranslation } from 'react-i18next'

import { ProviderForm } from '@/components/ui/provider-form'
import { COUNTRIES } from '@/lib/countries'

import { CUSTOM_PRESET, PROVIDER_PRESET_ORDER, type ProviderCreateState } from './useProviderCreate'

export function ProviderCreateFields({ state }: { state: ProviderCreateState }) {
  const { t } = useTranslation()
  const custom = state.presetKey === CUSTOM_PRESET
  return (
    <>
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">{t('settings.providerPreset')}</span>
        <select
          className="bg-surface border-border w-full rounded-md border px-3 py-2"
          value={state.presetKey}
          onChange={(event) => state.applyPreset(event.target.value)}
        >
          {PROVIDER_PRESET_ORDER.map((key) => (
            <option key={key} value={key}>
              {state.presets.data?.[key]?.name ?? key}
            </option>
          ))}
          <option value={CUSTOM_PRESET}>{t('settings.presetCustom')}</option>
        </select>
      </label>
      <ProviderForm
        name={state.name}
        onNameChange={state.setName}
        baseUrl={state.baseUrl}
        onBaseUrlChange={state.setBaseUrl}
        apiKey={state.apiKey}
        onApiKeyChange={state.setApiKey}
        nameLabel={t('settings.providerName')}
        baseUrlLabel={t('settings.baseUrl')}
        baseUrlPlaceholder={custom ? 'http://localhost:11434/v1' : undefined}
        hideBaseUrl={state.selectedType !== 'openai_compatible'}
        apiKeyLabel={t('settings.apiKey')}
        apiKeyHelp={t('settings.apiKeyOptional')}
        showLocationKind
        locationKind={state.isLocal ? 'local' : 'cloud'}
        onLocationKindChange={(kind) => state.setIsLocal(kind === 'local')}
        locationLabel={t('settings.hosting')}
        localLabel={t('settings.localKind')}
        cloudLabel={t('settings.cloudKind')}
        showCountry
        country={state.country}
        onCountryChange={state.setCountry}
        countryLabel={t('settings.country')}
        countryPlaceholder={t('settings.countryPlaceholder')}
        countryOptions={COUNTRIES.map((entry) => ({
          value: entry.code,
          label: `${entry.flag} ${entry.name}`,
        }))}
        error={state.error ?? undefined}
      >
        {custom && !state.baseUrl.trim() ? (
          <p className="text-warning text-[11px]">{t('settings.baseUrlRequired')}</p>
        ) : null}
      </ProviderForm>
    </>
  )
}

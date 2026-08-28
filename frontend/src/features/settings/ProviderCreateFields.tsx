import { useTranslation } from 'react-i18next'

import { CUSTOM_PRESET, PROVIDER_PRESET_ORDER, type ProviderCreateState } from './useProviderCreate'

export function ProviderCreateFields({ state }: { state: ProviderCreateState }) {
  const { t } = useTranslation()
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
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">{t('settings.providerName')}</span>
        <input
          className="bg-surface border-border w-full rounded-md border px-3 py-2"
          value={state.name}
          onChange={(event) => state.setName(event.target.value)}
        />
      </label>
      {state.selectedType === 'openai_compatible' ? (
        <label className="block space-y-1 text-sm">
          <span className="text-muted-foreground">{t('settings.baseUrl')}</span>
          <input
            className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono text-xs"
            value={state.baseUrl}
            onChange={(event) => state.setBaseUrl(event.target.value)}
            placeholder={
              state.presetKey === CUSTOM_PRESET ? 'http://localhost:11434/v1' : undefined
            }
          />
          {state.presetKey === CUSTOM_PRESET && !state.baseUrl.trim() ? (
            <span className="text-warning text-[11px]">{t('settings.baseUrlRequired')}</span>
          ) : null}
        </label>
      ) : null}
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">{t('settings.apiKey')}</span>
        <input
          type="password"
          className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono text-xs"
          value={state.apiKey}
          onChange={(event) => state.setApiKey(event.target.value)}
          placeholder={t('settings.apiKeyOptional')}
        />
      </label>
      {state.error ? <p className="text-danger text-xs">{state.error}</p> : null}
    </>
  )
}

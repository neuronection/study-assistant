import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { HardDriveDownload, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  ProviderSetupForm,
  type ProviderSetupFormValue,
} from '@/components/ui/provider-setup-form'
import {
  ProviderSetupManualTile,
  ProviderSetupTiles,
} from '@/components/ui/provider-setup-tiles'
import { SetupSteps } from '@/components/ui/setup-steps'
import { LocalEngines } from '@/features/settings/LocalEngines'
import { ERROR_CODES, SetupErrorPanel } from '@/features/settings/setupErrors'
import {
  createProvider,
  listPresets,
  setupErrorDetail,
  setupProviderPreset,
  type Provider,
  type ProviderPreset,
  type ProviderSetupErrorDetail,
  type ProviderSetupResult,
} from '@/lib/api'

import { CountrySelect, HostingToggle } from './providerSetupExtras'
import {
  chipsForPreset,
  orderedPresetKeys,
  presetToFormPreset,
} from './providerSetupPresets'

export type ProviderConnectPhase = 'tiles' | 'form' | 'manual' | 'local'

export interface ProviderConnectValues {
  name: string
  apiKey: string
  baseUrl: string
  isLocal: boolean
  country: string
}

export interface ProviderConnectOutcome {
  mode: 'preset' | 'manual' | 'local'
  presetKey: string | null
  preset: ProviderPreset | null
  provider: Provider
  result: ProviderSetupResult | null
  values: ProviderConnectValues
}

export interface ProviderSetupConnectProps {
  showName?: boolean
  showHosting?: boolean
  showCountry?: boolean
  showSteps?: boolean
  bindDefaults?: boolean
  configured?: string[]
  onConnected: (outcome: ProviderConnectOutcome) => void
  onPhaseChange?: (phase: ProviderConnectPhase, presetName: string | null) => void
}

const BIND_LESS = {
  bind_chat: false,
  bind_vision: false,
  bind_stt: false,
  bind_embeddings: false,
  bind_decision: false,
}

function valuesFrom(
  name: string,
  apiKey: string,
  baseUrl: string,
  isLocal: boolean,
  country: string
): ProviderConnectValues {
  return {
    name: name.trim(),
    apiKey: apiKey.trim(),
    baseUrl: baseUrl.trim(),
    isLocal,
    country: country.trim(),
  }
}

export function ProviderSetupConnect({
  showName = true,
  showHosting = true,
  showCountry = true,
  showSteps = true,
  bindDefaults = false,
  configured,
  onConnected,
  onPhaseChange,
}: ProviderSetupConnectProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const presets = useQuery({ queryKey: ['presets'], queryFn: listPresets })
  const [phase, setPhase] = useState<ProviderConnectPhase>('tiles')
  const [presetKey, setPresetKey] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [advancedBase, setAdvancedBase] = useState('')
  const [isLocal, setIsLocal] = useState(false)
  const [country, setCountry] = useState('')
  const [error, setError] = useState<ProviderSetupErrorDetail | null>(null)
  const [plainError, setPlainError] = useState<string | null>(null)

  const order = orderedPresetKeys(presets.data)
  const preset = presetKey !== null ? presets.data?.[presetKey] ?? null : null

  const notifyPhase = (next: ProviderConnectPhase, nextPreset: string | null) => {
    setPhase(next)
    onPhaseChange?.(next, nextPreset)
  }

  const openForm = (key: string) => {
    const nextPreset = presets.data?.[key]
    setPresetKey(key)
    setName('')
    setApiKey('')
    setAdvancedBase(nextPreset?.base_url ?? '')
    setIsLocal(nextPreset?.local ?? false)
    setCountry('')
    setError(null)
    setPlainError(null)
    notifyPhase('form', nextPreset?.name ?? key)
  }

  const openManual = () => {
    setPresetKey(null)
    setName('')
    setAdvancedBase('')
    setApiKey('')
    setIsLocal(false)
    setCountry('')
    setError(null)
    setPlainError(null)
    notifyPhase('manual', null)
  }

  const openLocal = () => {
    setError(null)
    setPlainError(null)
    notifyPhase('local', null)
  }

  const backToTiles = () => {
    setPresetKey(null)
    setError(null)
    setPlainError(null)
    notifyPhase('tiles', null)
  }

  const baseEdited =
    preset !== null &&
    !preset.fixed_base &&
    advancedBase.trim() !== '' &&
    advancedBase.trim() !== preset.base_url
  const forcedManual =
    preset !== null &&
    (baseEdited || (!preset.local && isLocal) || country.trim() !== '')

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['providers'] })
    await queryClient.invalidateQueries({ queryKey: ['models'] })
    await queryClient.invalidateQueries({ queryKey: ['tasks'] })
    await queryClient.invalidateQueries({ queryKey: ['task-defaults'] })
  }

  const connect = useMutation({
    mutationFn: async (): Promise<ProviderConnectOutcome> => {
      if (preset === null || presetKey === null) {
        throw new Error('no preset selected')
      }
      const values = valuesFrom(name, apiKey, advancedBase, isLocal, country)
      if (forcedManual) {
        const provider = await createProvider({
          name: values.name || preset.name,
          type: preset.type,
          base_url: preset.fixed_base ? null : values.baseUrl || preset.base_url,
          api_key: values.apiKey || null,
          is_local: values.isLocal,
          country: values.country || null,
        })
        return {
          mode: 'manual',
          presetKey: null,
          preset: null,
          provider,
          result: null,
          values,
        }
      }
      const result = await setupProviderPreset(presetKey, {
        api_key: preset.local ? null : values.apiKey || null,
        name: values.name || null,
        options: bindDefaults
          ? {
              bind_chat: true,
              bind_vision: true,
              bind_stt: true,
              bind_embeddings: true,
              bind_decision: true,
            }
          : BIND_LESS,
      })
      return {
        mode: 'preset',
        presetKey,
        preset,
        provider: result.provider,
        result,
        values,
      }
    },
    onSuccess: async (outcome) => {
      await invalidate()
      onConnected(outcome)
    },
    onError: (err: { detail?: unknown; message?: string }) => {
      setError(setupErrorDetail(err.detail))
      setPlainError(setupErrorDetail(err.detail) ? null : err.message ?? String(err))
    },
  })

  const connectManual = useMutation({
    mutationFn: async (): Promise<ProviderConnectOutcome> => {
      const values = valuesFrom(name, apiKey, advancedBase, isLocal, country)
      const provider = await createProvider({
        name: values.name,
        type: 'openai_compatible',
        base_url: values.baseUrl || null,
        api_key: values.apiKey || null,
        is_local: values.isLocal,
        country: values.country || null,
      })
      return {
        mode: 'manual',
        presetKey: null,
        preset: null,
        provider,
        result: null,
        values,
      }
    },
    onSuccess: async (outcome) => {
      await invalidate()
      onConnected(outcome)
    },
    onError: (err: Error) => setPlainError(err.message),
  })

  const handleLocalCreated = (provider: Provider) => {
    void invalidate()
    onConnected({
      mode: 'local',
      presetKey: null,
      preset: null,
      provider,
      result: null,
      values: valuesFrom(provider.name, '', provider.base_url ?? '', true, ''),
    })
  }

  const errorLabels = {
    ...Object.fromEntries(ERROR_CODES.map((code) => [code, t(`settings.setup.errors.${code}`)])),
    unknown: plainError ?? t('settings.setup.errors.unknown'),
  }
  const formError = error
    ? { code: error.code, suspectedVendor: error.suspected_vendor ?? null }
    : plainError
      ? { code: 'unknown' }
      : null

  return (
    <div className="space-y-3">
      {showSteps ? (
        <SetupSteps
          steps={[
            { id: 'connect', label: t('settings.setup.step.connect') },
            { id: 'defaults', label: t('settings.setup.step.defaults') },
          ]}
          current={0}
          label={t('settings.setup.step.progress')}
        />
      ) : null}

      {phase === 'tiles' ? (
        <ProviderSetupTiles
          presets={order.map((key) => {
            const entry = presets.data?.[key]
            if (!entry) return { key, name: key }
            return {
              key,
              name: entry.name,
              local: entry.local,
              chips: chipsForPreset(entry, t),
            }
          })}
          configured={configured}
          onSelect={openForm}
          label={t('settings.setup.title')}
          localLabel={t('settings.setup.local')}
        >
          <ProviderSetupManualTile onClick={openManual}>
            {t('settings.setup.custom')}
          </ProviderSetupManualTile>
          <ProviderSetupManualTile icon={HardDriveDownload} onClick={openLocal}>
            {t('settings.setup.localEngines')}
          </ProviderSetupManualTile>
        </ProviderSetupTiles>
      ) : null}

      {phase === 'form' && preset ? (
        <ProviderSetupForm
          preset={presetToFormPreset(presetKey ?? '', preset)}
          value={{ name, apiKey, baseUrl: advancedBase }}
          onChange={(value: ProviderSetupFormValue) => {
            setName(value.name)
            setApiKey(value.apiKey)
            setAdvancedBase(value.baseUrl ?? '')
          }}
          testing={connect.isPending}
          error={formError}
          errorLabels={errorLabels}
          suspectedVendorHint={t('settings.setup.errors.suspectedVendor', {
            vendor: error?.suspected_vendor ?? '',
          })}
          hideName={!showName}
          advancedExtra={
            showHosting || showCountry ? (
              <>
                {showHosting ? (
                  <HostingToggle local={isLocal} onChange={setIsLocal} disabled={preset.local} />
                ) : null}
                {showCountry ? <CountrySelect country={country} onChange={setCountry} /> : null}
              </>
            ) : undefined
          }
          copyLabel={t('common.copy')}
          getKeyLabel={t('settings.setup.getKey')}
          nameLabel={t('settings.setup.connectionName')}
          apiKeyLabel={t('settings.apiKey')}
          noKeyLabel={t('settings.setup.noKeyNeeded')}
          advancedLabel={t('settings.setup.advanced')}
          baseUrlLabel={t('settings.baseUrl')}
          baseUrlHint={t('settings.setup.baseEditHint')}
          submitLabel={t('settings.setup.automatically')}
          cancelLabel={t('settings.setup.chooseAnother')}
          onSubmit={() => connect.mutate()}
          onCancel={backToTiles}
        />
      ) : null}

      {phase === 'manual' ? (
        <div className="space-y-3">
          <p className="text-muted-foreground flex items-center gap-2 text-xs">
            {t('settings.setup.manualHint')}
          </p>
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">{t('settings.providerName')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">{t('settings.baseUrl')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono"
              value={advancedBase}
              placeholder="https://api.example.com/v1"
              onChange={(event) => setAdvancedBase(event.target.value)}
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">{t('settings.apiKey')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
            <span className="text-muted-foreground block text-[11px]">
              {t('settings.apiKeyOptional')}
            </span>
          </label>
          {showHosting ? <HostingToggle local={isLocal} onChange={setIsLocal} /> : null}
          {showCountry ? <CountrySelect country={country} onChange={setCountry} /> : null}
          <SetupErrorPanel error={null} plainError={plainError} />
          <div className="flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={backToTiles}>
              {t('settings.setup.chooseAnother')}
            </Button>
            <Button
              size="sm"
              disabled={
                name.trim().length === 0 ||
                advancedBase.trim().length === 0 ||
                connectManual.isPending
              }
              onClick={() => connectManual.mutate()}
            >
              {connectManual.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : null}
              {t('settings.add')}
            </Button>
          </div>
        </div>
      ) : null}

      {phase === 'local' ? (
        <div className="space-y-3">
          <div>
            <h3 className="text-sm font-semibold">{t('settings.setup.localEnginesTitle')}</h3>
            <p className="text-muted-foreground text-xs">
              {t('settings.setup.localEnginesHint')}
            </p>
          </div>
          <LocalEngines auto bindDefaults={bindDefaults} onCreated={handleLocalCreated} />
          <div className="flex justify-start">
            <Button variant="ghost" size="sm" onClick={backToTiles}>
              {t('settings.setup.chooseAnother')}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

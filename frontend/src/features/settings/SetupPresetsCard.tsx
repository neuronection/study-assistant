import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ExternalLink, Loader2, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  listPresets,
  setupErrorDetail,
  setupProviderPreset,
  type ProviderPreset,
  type ProviderSetupErrorDetail,
  type ProviderSetupResult,
} from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

const SETUP_TILE_ORDER = [
  'openai',
  'gemini',
  'openrouter',
  'anthropic',
  'groq',
  'mistral',
  'deepseek',
  'ollama',
] as const

const ERROR_CODES = [
  'invalid_key',
  'insufficient_credit',
  'new_user_quota',
  'region_unavailable',
  'timeout',
  'local_not_running',
  'unknown',
] as const

function setupErrorLabel(code: string): string {
  return (ERROR_CODES as readonly string[]).includes(code) ? code : 'unknown'
}

function freeStepText(text: string, url: string): string {
  return text.replace('{url}', url)
}

function SetupForm({
  presetKey,
  preset,
  onConnected,
  onClose,
}: {
  presetKey: string
  preset: ProviderPreset
  onConnected: (result: ProviderSetupResult) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [error, setError] = useState<ProviderSetupErrorDetail | null>(null)

  const connect = useMutation({
    mutationFn: () =>
      setupProviderPreset(presetKey, {
        api_key: preset.local ? null : apiKey.trim() || null,
        name: name.trim() || null,
      }),
    onSuccess: async (data) => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
      await queryClient.invalidateQueries({ queryKey: ['models'] })
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
      await queryClient.invalidateQueries({ queryKey: ['task-defaults'] })
      onConnected(data)
    },
    onError: (err: { detail?: unknown }) =>
      setError(setupErrorDetail(err.detail)),
  })

  return (
    <CardContent className="space-y-3">
      {preset.steps && preset.steps.length > 0 ? (
        <ol className="text-muted-foreground list-decimal space-y-1 pl-5 text-xs">
          {preset.steps.map((step, index) => (
            <li key={index}>{freeStepText(step, preset.key_url ?? '')}</li>
          ))}
        </ol>
      ) : null}
      {preset.free_tier_note ? (
        <p className="text-muted-foreground flex items-start gap-1.5 text-xs">
          <ShieldCheck className="text-success mt-0.5 size-3.5 shrink-0" aria-hidden />
          {preset.free_tier_note}
        </p>
      ) : null}
      {preset.key_url ? (
        <a
          className="text-primary inline-flex items-center gap-1 text-xs underline"
          href={preset.key_url}
          target="_blank"
          rel="noreferrer"
        >
          <ExternalLink className="size-3" aria-hidden />
          {t('settings.setup.getKey')}
        </a>
      ) : null}
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">{t('settings.providerName')}</span>
        <input
          className="bg-surface border-border w-full rounded-md border px-3 py-2"
          value={name}
          placeholder={preset.name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      {!preset.local ? (
        <label className="block space-y-1 text-sm">
          <span className="text-muted-foreground">{t('settings.apiKey')}</span>
          <input
            className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono"
            type="password"
            value={apiKey}
            autoComplete="off"
            onChange={(event) => setApiKey(event.target.value)}
            autoFocus
          />
        </label>
      ) : null}
      {error ? (
        <div className="text-danger space-y-1 rounded-md border border-dashed border-current/40 px-3 py-2 text-xs">
          <p>{t(`settings.setup.errors.${setupErrorLabel(error.code)}`)}</p>
          {error.suspected_vendor ? (
            <p>
              {t('settings.setup.errors.suspectedVendor', { vendor: error.suspected_vendor })}
            </p>
          ) : null}
          {error.detail ? <p className="text-muted-foreground break-words">{error.detail}</p> : null}
        </div>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>
          {t('settings.cancel')}
        </Button>
        <Button
          size="sm"
          disabled={(!preset.local && apiKey.trim().length === 0) || connect.isPending}
          onClick={() => connect.mutate()}
        >
          {connect.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}
          {t('settings.setup.connect')}
        </Button>
      </div>
    </CardContent>
  )
}

function SetupResult({
  result,
  presetName,
  onClose,
}: {
  result: ProviderSetupResult
  presetName: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const assigned = [
    ['chat', result.assigned_chat_model],
    ['vision', result.assigned_vision_model],
    ['stt', result.assigned_stt_model],
  ].filter((entry): entry is [string, string] => entry[1] !== null)
  return (
    <CardContent className="space-y-3">
      <p className="flex items-center gap-2 text-sm font-medium">
        <Check className="text-success size-4" aria-hidden />
        {t('settings.setup.done', { name: presetName })}
      </p>
      <p className="text-muted-foreground text-xs">
        {t('settings.setup.modelsPersisted', { count: result.catalog_count })}
      </p>
      {assigned.length > 0 ? (
        <ul className="text-muted-foreground space-y-1 text-xs">
          {assigned.map(([slot, model]) => (
            <li key={slot}>
              {t(`settings.setup.slot.${slot}`)}: <span className="font-mono">{model}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-muted-foreground text-xs">{t('settings.setup.noDefaults')}</p>
      )}
      {result.curated_missed ? (
        <p className="text-warning text-xs">{t('settings.setup.curatedMissed')}</p>
      ) : null}
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={onClose}>
          {t('common.close')}
        </Button>
      </div>
    </CardContent>
  )
}

export function SetupPresetsCard() {
  const { t } = useTranslation()
  const [presetKey, setPresetKey] = useState<string | null>(null)
  const [result, setResult] = useState<{ presetKey: string; result: ProviderSetupResult } | null>(
    null
  )
  useCloseFloatings()
  const presets = useQuery({ queryKey: ['presets'], queryFn: listPresets })
  const order = SETUP_TILE_ORDER.filter((key) => key in (presets.data ?? {}))
  const selected = presetKey !== null ? presets.data?.[presetKey] : null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('settings.setup.title')}</CardTitle>
        <CardDescription>{t('settings.setup.hint')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {order.map((key) => {
            const preset = presets.data?.[key]
            if (!preset) return null
            return (
              <button
                key={key}
                type="button"
                className="bg-surface border-border hover:bg-subtle flex flex-col items-start gap-0.5 rounded-lg border px-3 py-2 text-left"
                onClick={() => {
                  setResult(null)
                  setPresetKey(key)
                }}
              >
                <span className="truncate text-sm font-medium">{preset.name}</span>
                <span className="text-muted-foreground text-[11px]">
                  {preset.local ? t('settings.setup.local') : t('settings.setup.cloud')}
                </span>
              </button>
            )
          })}
        </div>
        {result ? (
          <SetupResult
            result={result.result}
            presetName={presets.data?.[result.presetKey]?.name ?? result.presetKey}
            onClose={() => {
              setResult(null)
              setPresetKey(null)
            }}
          />
        ) : null}
        {presetKey !== null && selected ? (
          <SetupForm
            presetKey={presetKey}
            preset={selected}
            onConnected={(data) => setResult({ presetKey, result: data })}
            onClose={() => setPresetKey(null)}
          />
        ) : null}
      </CardContent>
    </Card>
  )
}

export { setupErrorLabel }

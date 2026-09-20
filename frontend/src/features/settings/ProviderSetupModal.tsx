import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Banknote, Check, Copy, ExternalLink, House, Loader2, Settings2, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ModelPicker, type ModelPickerProvider } from '@/components/ui/model-picker'
import {
  assignTaskDefault,
  createProvider,
  listModels,
  listPresets,
  listTaskDefaults,
  setupErrorDetail,
  setupProviderPreset,
  type ProviderPreset,
  type ProviderSetupErrorDetail,
  type ProviderSetupResult,
} from '@/lib/api'
import { COUNTRIES } from '@/lib/countries'
import { useCloseFloatings } from '@/lib/ui-overlays'

import { ProviderLogo } from './ProviderLogo'

const TILE_ORDER = [
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

function errorLabel(code: string): string {
  return (ERROR_CODES as readonly string[]).includes(code) ? code : 'unknown'
}

type Phase = 'tiles' | 'form' | 'manual' | 'done'

function ModalShell({
  title,
  description,
  onClose,
  children,
}: {
  title: string
  description: string
  onClose: () => void
  children: React.ReactNode
}) {
  const { t } = useTranslation()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[90vh] w-full max-w-lg overflow-y-auto">
        <CardContent className="space-y-3 p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="space-y-1">
              <h2 className="text-base font-semibold">{title}</h2>
              <p className="text-muted-foreground text-xs">{description}</p>
            </div>
            <Button variant="ghost" size="icon" aria-label={t('common.close')} onClick={onClose}>
              <X className="size-4" aria-hidden />
            </Button>
          </div>
          {children}
        </CardContent>
      </Card>
    </div>
  )
}

function HostingToggle({
  local,
  onChange,
  disabled,
}: {
  local: boolean
  onChange: (local: boolean) => void
  disabled?: boolean
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-1">
      <span className="text-muted-foreground block text-sm">{t('settings.hosting')}</span>
      <div className="grid grid-cols-2 gap-2" role="group" aria-label={t('settings.hosting')}>
        {(
          [
            [true, t('settings.localKind'), House],
            [false, t('settings.cloudKind'), Banknote],
          ] as const
        ).map(([value, label, Icon]) => (
          <button
            key={label}
            type="button"
            aria-pressed={local === value}
            disabled={disabled}
            onClick={() => onChange(value)}
            className={`flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
              local === value
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-surface text-muted-foreground hover:bg-subtle'
            }`}
          >
            <Icon className="size-4" aria-hidden />
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

function CountrySelect({ country, onChange }: { country: string; onChange: (c: string) => void }) {
  const { t } = useTranslation()
  return (
    <label className="block space-y-1 text-sm">
      <span className="text-muted-foreground">{t('settings.country')}</span>
      <select
        className="bg-surface border-border w-full rounded-md border px-3 py-2"
        aria-label={t('settings.country')}
        value={country}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{t('settings.countryPlaceholder')}</option>
        {COUNTRIES.map((entry) => (
          <option key={entry.code} value={entry.code}>
            {entry.flag} {entry.name}
          </option>
        ))}
      </select>
    </label>
  )
}

function ErrorPanel({ error, plainError }: { error: ProviderSetupErrorDetail | null; plainError: string | null }) {
  const { t } = useTranslation()
  if (error) {
    return (
      <div className="text-danger space-y-1 rounded-md border border-dashed border-current/40 px-3 py-2 text-xs">
        <p>{t(`settings.setup.errors.${errorLabel(error.code)}`)}</p>
        {error.suspected_vendor ? (
          <p>{t('settings.setup.errors.suspectedVendor', { vendor: error.suspected_vendor })}</p>
        ) : null}
        {error.detail ? <p className="text-muted-foreground break-words">{error.detail}</p> : null}
      </div>
    )
  }
  if (plainError) {
    return <p className="text-danger text-xs">{plainError}</p>
  }
  return null
}

function SuccessDefaults({
  providerId,
  providerName,
  result,
}: {
  providerId: number
  providerName: string
  result: ProviderSetupResult
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const defaults = useQuery({ queryKey: ['task-defaults'], queryFn: listTaskDefaults })
  const [error, setError] = useState<string | null>(null)

  const providerModels = (models.data ?? []).filter(
    (model) => model.provider_id === providerId && model.enabled
  )
  const catalog: ModelPickerProvider[] = [
    {
      id: String(providerId),
      name: providerName,
      models: providerModels.map((model) => ({
        id: String(model.id),
        name: model.label || model.external_id,
        capabilities: model.caps,
      })),
    },
  ]
  const externalToId = new Map(providerModels.map((model) => [model.external_id, String(model.id)]))
  const defaultByCap = new Map((defaults.data ?? []).map((entry) => [entry.requires, entry]))

  const bind = useMutation({
    mutationFn: ({ requires, modelId }: { requires: string; modelId: string }) => {
      const fallback = defaultByCap.get(requires)?.fallback_model_id ?? null
      return assignTaskDefault(requires, Number(modelId), fallback)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
      await queryClient.invalidateQueries({ queryKey: ['task-defaults'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const slotValue = (requires: string, assignedExternal: string | null): string => {
    const fromExternal = assignedExternal ? externalToId.get(assignedExternal) : undefined
    if (fromExternal !== undefined) return fromExternal
    const entry = defaultByCap.get(requires)
    return entry?.model_id != null ? String(entry.model_id) : ''
  }

  const hasCap = (cap: string) => providerModels.some((model) => model.caps.includes(cap))
  const rows = [
    { requires: 'text', label: t('settings.setup.slot.chat'), assigned: result.assigned_chat_model },
    ...(hasCap('vision')
      ? [{ requires: 'vision', label: t('settings.setup.slot.vision'), assigned: result.assigned_vision_model }]
      : []),
    ...(hasCap('stt')
      ? [{ requires: 'stt', label: t('settings.setup.slot.stt'), assigned: result.assigned_stt_model }]
      : []),
  ]

  if (providerModels.length === 0) {
    return <p className="text-muted-foreground text-xs">{t('settings.setup.noDefaults')}</p>
  }

  return (
    <div className="border-border space-y-2 rounded-md border p-3">
      <h3 className="text-sm font-semibold">{t('settings.defaultModelsTitle')}</h3>
      {rows.map((row) => (
        <ModelPicker
          key={row.requires}
          providers={catalog}
          value={slotValue(row.requires, row.assigned)}
          onChange={(modelId) => {
            setError(null)
            bind.mutate({ requires: row.requires, modelId })
          }}
          clearable={false}
          label={row.label}
        />
      ))}
      {error ? <p className="text-danger text-xs">{error}</p> : null}
    </div>
  )
}

function SuccessPanel({
  result,
  presetName,
}: {
  result: ProviderSetupResult
  presetName: string
}) {
  const { t } = useTranslation()
  return (
    <div className="space-y-2">
      <p className="flex items-center gap-2 text-sm font-medium">
        <Check className="text-success size-4" aria-hidden />
        {t('settings.setup.done', { name: presetName })}
      </p>
      <p className="text-muted-foreground text-xs">
        {t('settings.setup.modelsPersisted', { count: result.catalog_count })}
      </p>
      {result.curated_missed ? (
        <p className="text-warning text-xs">{t('settings.setup.curatedMissed')}</p>
      ) : null}
      <SuccessDefaults
        providerId={result.provider.id}
        providerName={result.provider.name}
        result={result}
      />
    </div>
  )
}

export function ProviderSetupModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  useCloseFloatings()

  const presets = useQuery({ queryKey: ['presets'], queryFn: listPresets })
  const [phase, setPhase] = useState<Phase>('tiles')
  const [presetKey, setPresetKey] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [advancedBase, setAdvancedBase] = useState('')
  const [isLocal, setIsLocal] = useState(false)
  const [country, setCountry] = useState('')
  const [error, setError] = useState<ProviderSetupErrorDetail | null>(null)
  const [plainError, setPlainError] = useState<string | null>(null)
  const [result, setResult] = useState<ProviderSetupResult | null>(null)
  const [resultName, setResultName] = useState('')

  const order = TILE_ORDER.filter((key) => key in (presets.data ?? {}))
  const preset: ProviderPreset | null = presetKey !== null ? presets.data?.[presetKey] ?? null : null

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['providers'] })
    await queryClient.invalidateQueries({ queryKey: ['models'] })
    await queryClient.invalidateQueries({ queryKey: ['tasks'] })
    await queryClient.invalidateQueries({ queryKey: ['task-defaults'] })
  }

  const openForm = (key: string) => {
    setPresetKey(key)
    setName('')
    setApiKey('')
    setAdvancedBase(presets.data?.[key]?.base_url ?? '')
    setIsLocal(presets.data?.[key]?.local ?? false)
    setCountry('')
    setError(null)
    setPlainError(null)
    setPhase('form')
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
    setPhase('manual')
  }

  const backToTiles = () => {
    setPhase('tiles')
    setPresetKey(null)
    setError(null)
    setPlainError(null)
  }

  const baseEdited =
    preset !== null &&
    !preset.fixed_base &&
    advancedBase.trim() !== '' &&
    advancedBase.trim() !== preset.base_url
  const forcedManual = preset !== null && (baseEdited || (!preset.local && isLocal) || country.trim() !== '')

  const connectForm = useMutation({
    mutationFn: () => {
      if (preset === null) throw new Error('no preset selected')
      if (forcedManual) {
        return createProvider({
          name: name.trim() || preset.name,
          type: preset.type,
          base_url: preset.fixed_base ? null : advancedBase.trim() || preset.base_url,
          api_key: apiKey.trim() || null,
          is_local: isLocal,
          country: country.trim() || null,
        }).then((provider) => ({
          ok: true,
          provider: { ...provider, preset_key: null },
          catalog_count: provider.status?.model_count ?? 0,
          curated_missed: false,
          assigned_chat_model: null,
          assigned_vision_model: null,
          assigned_stt_model: null,
        }))
      }
      return setupProviderPreset(presetKey ?? '', {
        api_key: preset.local ? null : apiKey.trim() || null,
        name: name.trim() || null,
      })
    },
    onSuccess: async (data) => {
      await invalidate()
      setResultName(name.trim() || preset?.name || '')
      setResult(data)
      setPhase('done')
    },
    onError: (err: { detail?: unknown; message?: string }) => {
      setError(setupErrorDetail(err.detail))
      setPlainError(setupErrorDetail(err.detail) ? null : (err.message ?? String(err)))
    },
  })

  const connectManual = useMutation({
    mutationFn: () =>
      createProvider({
        name: name.trim(),
        type: 'openai_compatible',
        base_url: advancedBase.trim() || null,
        api_key: apiKey.trim() || null,
        is_local: isLocal,
        country: country.trim() || null,
      }),
    onSuccess: async () => {
      await invalidate()
      onClose()
    },
    onError: (err: Error) => setPlainError(err.message),
  })

  if (phase === 'done' && result) {
    return (
      <ModalShell
        title={t('settings.setup.title')}
        description={t('settings.setup.hint')}
        onClose={onClose}
      >
        <SuccessPanel result={result} presetName={resultName} />
        <div className="flex justify-end">
          <Button size="sm" variant="outline" onClick={onClose}>
            {t('common.close')}
          </Button>
        </div>
      </ModalShell>
    )
  }

  return (
    <ModalShell
      title={phase === 'form' && preset ? t('settings.setup.formTitle', { name: preset.name }) : t('settings.setup.title')}
      description={t('settings.setup.modalHint')}
      onClose={onClose}
    >
      {phase === 'tiles' ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" role="group" aria-label={t('settings.setup.title')}>
          {order.map((key) => {
            const presetTile = presets.data?.[key]
            if (!presetTile) return null
            return (
              <button
                key={key}
                type="button"
                className="border-border bg-surface hover:bg-subtle flex h-auto flex-col items-center gap-2 rounded-lg border px-3 py-4"
                onClick={() => openForm(key)}
              >
                <ProviderLogo presetKey={key} label={presetTile.name} />
                <span className="w-full truncate text-center text-sm font-medium">{presetTile.name}</span>
                {presetTile.local ? (
                  <span className="text-muted-foreground text-[11px]">{t('settings.setup.local')}</span>
                ) : null}
              </button>
            )
          })}
          <button
            type="button"
            className="border-border bg-surface hover:bg-subtle flex h-auto flex-col items-center gap-2 rounded-lg border px-3 py-4"
            onClick={openManual}
          >
            <Settings2 className="text-muted-foreground size-5" aria-hidden />
            <span className="w-full truncate text-center text-sm font-medium">{t('settings.setup.custom')}</span>
          </button>
        </div>
      ) : null}

      {phase === 'form' && preset ? (
        <div className="space-y-3">
          {preset.steps && preset.steps.length > 0 ? (
            <ol className="list-decimal space-y-1 pl-5 text-xs">
              {preset.steps.map((step, index) => (
                <li key={index} className="text-muted-foreground flex items-start justify-between gap-2">
                  <span>{step.replace('{url}', preset.key_url ?? '')}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-6 shrink-0"
                    aria-label={t('common.copy')}
                    title={t('common.copy')}
                    onClick={() => void navigator.clipboard.writeText(step)}
                  >
                    <Copy className="size-3" aria-hidden />
                  </Button>
                </li>
              ))}
            </ol>
          ) : null}
          {preset.free_tier_note ? (
            <p className="text-muted-foreground text-xs">{preset.free_tier_note}</p>
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
            <span className="text-muted-foreground">{t('settings.setup.connectionName')}</span>
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
                autoComplete="off"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                autoFocus
              />
            </label>
          ) : (
            <p className="text-muted-foreground text-xs">{t('settings.setup.noKeyNeeded')}</p>
          )}
          <details className="border-border rounded-md border px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium">{t('settings.setup.advanced')}</summary>
            <div className="space-y-3 pt-2">
              <label className="block space-y-1 text-sm">
                <span className="text-muted-foreground">{t('settings.baseUrl')}</span>
                <input
                  className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono data-readonly:opacity-80"
                  value={advancedBase}
                  readOnly={preset.fixed_base}
                  onChange={(event) => setAdvancedBase(event.target.value)}
                />
              </label>
              {!preset.fixed_base ? (
                <p className="text-muted-foreground text-[11px]">{t('settings.setup.baseEditHint')}</p>
              ) : null}
              <HostingToggle local={isLocal} onChange={setIsLocal} disabled={preset.local} />
              <CountrySelect country={country} onChange={setCountry} />
            </div>
          </details>
          <ErrorPanel error={error} plainError={plainError} />
          <div className="flex items-center justify-between gap-2">
            <Button variant="ghost" size="sm" onClick={backToTiles}>
              {t('settings.setup.chooseAnother')}
            </Button>
            <Button
              size="sm"
              disabled={(!preset.local && apiKey.trim().length === 0) || connectForm.isPending}
              onClick={() => connectForm.mutate()}
            >
              {connectForm.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}
              {t('settings.setup.automatically')}
            </Button>
          </div>
        </div>
      ) : null}

      {phase === 'manual' ? (
        <div className="space-y-3">
          <p className="text-muted-foreground flex items-center gap-2 text-xs">
            <Settings2 className="size-3.5" aria-hidden />
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
            <span className="text-muted-foreground block text-[11px]">{t('settings.apiKeyOptional')}</span>
          </label>
          <HostingToggle local={isLocal} onChange={setIsLocal} />
          <CountrySelect country={country} onChange={setCountry} />
          <ErrorPanel error={null} plainError={plainError} />
          <div className="flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={backToTiles}>
              {t('settings.setup.chooseAnother')}
            </Button>
            <Button
              size="sm"
              disabled={name.trim().length === 0 || advancedBase.trim().length === 0 || connectManual.isPending}
              onClick={() => connectManual.mutate()}
            >
              {connectManual.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />}
              {t('settings.add')}
            </Button>
          </div>
        </div>
      ) : null}
    </ModalShell>
  )
}

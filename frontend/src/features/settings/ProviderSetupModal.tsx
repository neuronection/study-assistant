import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Banknote, Check, House, Loader2, Settings2, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ModelPicker, type ModelPickerProvider } from '@/components/ui/model-picker'
import {
  ProviderSetupForm,
  type ProviderSetupFormValue,
} from '@/components/ui/provider-setup-form'
import {
  ProviderSetupTiles,
  ProviderSetupManualTile,
} from '@/components/ui/provider-setup-tiles'
import { SetupReview, type SetupReviewOptions } from '@/components/ui/setup-review'
import { SetupAssignments } from '@/components/ui/setup-assignments'
import { SetupSteps } from '@/components/ui/setup-steps'
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
import { COUNTRIES, countryDisplayName } from '@neuronection/assistant-ui/countries'
import { Combobox } from '@/components/ui/combobox'
import { useCloseFloatings } from '@/lib/ui-overlays'
import type { ProviderSetupTileChip } from '@neuronection/assistant-ui/provider-setup-tiles'

import { CAP_ICONS, guessCaps } from './ReRunSetupDialog'
import { ERROR_CODES, SetupErrorPanel } from './setupErrors'

const TILE_ORDER = [
  'openai',
  'gemini',
  'openrouter',
  'typesafe',
  'anthropic',
  'groq',
  'mistral',
  'deepseek',
  'ollama',
] as const

/**
 * Capability chips for a preset tile (plan 26 §13.3 follow-up): derived
 * from the API preset data — chat type → chat (+ vision where the
 * preferred model carries it, + stt where stt_model exists),
 * decision_models → decision, keyless-local → local. Labels via i18n.
 */
function chipsForPreset(
  preset: { type: string; local: boolean; preferred_model: { caps: string[] } | null; stt_model: string | null; decision_models: unknown[] | null },
  t: (key: string) => string,
): ProviderSetupTileChip[] {
  const chips: ProviderSetupTileChip[] = []
  if (preset.type !== 'decision') {
    chips.push({ key: 'chat', label: t('settings.setup.chipChat') })
    if (preset.preferred_model?.caps.includes('vision')) {
      chips.push({ key: 'vision', label: t('settings.setup.chipVision') })
    }
    if (preset.stt_model) {
      chips.push({ key: 'stt', label: t('settings.setup.chipStt') })
    }
  }
  if (preset.decision_models && preset.decision_models.length > 0) {
    chips.push({ key: 'decision', label: t('settings.setup.chipDecision') })
  }
  if (preset.local) {
    chips.push({ key: 'local', label: t('settings.setup.chipLocal') })
  }
  return chips
}

type Phase = 'tiles' | 'form' | 'manual' | 'review' | 'done'

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
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage ?? 'en'
  const options = COUNTRIES.map((entry) => ({
    value: entry.code,
    label: `${entry.flag} ${countryDisplayName(entry.code, locale)}`,
  }))
  return (
    <Combobox
      options={options}
      value={country}
      onChange={onChange}
      label={t('settings.country')}
      placeholder={t('settings.countryPlaceholder')}
      searchPlaceholder={t('settings.countrySearch')}
      searchLabel={t('settings.countrySearch')}
      emptyLabel={t('settings.countryEmpty')}
      clearable
      clearLabel={t('settings.countryClear')}
    />
  )
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

  const decisionModels = providerModels.filter(
    (model) => Boolean(model.decision_transport) || model.caps.includes('decision')
  )
  const decisionCatalog: ModelPickerProvider[] =
    decisionModels.length > 0
      ? [
          {
            id: String(providerId),
            name: providerName,
            models: decisionModels.map((model) => ({
              id: String(model.id),
              name: model.label || model.external_id,
              capabilities: model.caps,
            })),
          },
        ]
      : []

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
  // ADR-0036 §3: setup binds the `decision` default slot only — one
  // assignment, one review row; the kind slots inherit.
  const decisionRows =
    decisionModels.length > 0
      ? [
          {
            requires: 'decision',
            label: t('settings.decisionDefaultLabel'),
            assigned: result.assigned_decision_slots?.['decision'] ?? null,
          },
        ]
      : []

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
      {decisionRows.map((row) => (
        <ModelPicker
          key={row.requires}
          providers={decisionCatalog}
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
  // Review step (parity with the re-run dialog): connect binds nothing —
  // what registers and what fills the empty defaults is chosen here.
  const [reviewOptions, setReviewOptions] = useState<SetupReviewOptions>({
    curatedIds: [],
    bindChat: true,
    bindVision: true,
    bindStt: true,
    bindDecision: true,
  })
  const [applyError, setApplyError] = useState<ProviderSetupErrorDetail | null>(null)
  const [applyPlainError, setApplyPlainError] = useState<string | null>(null)
  // Live "now:" context for the review's assignment rows — what each
  // default currently points at (the response ships the model labels).
  const defaults = useQuery({
    queryKey: ['task-defaults'],
    queryFn: listTaskDefaults,
    enabled: phase === 'review',
  })

  const order = TILE_ORDER.filter((key) => key in (presets.data ?? {}))
  const preset: ProviderPreset | null = presetKey !== null ? presets.data?.[presetKey] ?? null : null
  // Decision models never ride the curated cards (ADR-0036 §3: one
  // default slot, kinds inherit) — the switch binds the preset's
  // `decision_default` only, so a decision section without one stays
  // hidden (it could not bind anything).
  const decisionCandidate =
    preset?.decision_models?.find((entry) => entry.id === preset.decision_default) ?? null
  const decisionDeclared = decisionCandidate !== null
  const defaultByCap = new Map((defaults.data ?? []).map((entry) => [entry.requires, entry]))

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
          assigned_embeddings_model: null,
          assigned_decision_slots: null,
        }))
      }
      return setupProviderPreset(presetKey ?? '', {
        api_key: preset.local ? null : apiKey.trim() || null,
        name: name.trim() || null,
        // Connect + register only — binds stay off so the review step
        // decides what fills the defaults (same contract as re-setup).
        options: {
          bind_chat: false,
          bind_vision: false,
          bind_stt: false,
          bind_embeddings: false,
          bind_decision: false,
        },
      })
    },
    onSuccess: async (data) => {
      await invalidate()
      setResultName(name.trim() || preset?.name || '')
      setResult(data)
      if (forcedManual) {
        // Manual hand-off registers no catalog — no review to make.
        setPhase('done')
        return
      }
      setReviewOptions({
        curatedIds: preset?.curated_models ?? [],
        bindChat: true,
        bindVision: true,
        bindStt: true,
        bindDecision: decisionDeclared,
      })
      setApplyError(null)
      setApplyPlainError(null)
      setPhase('review')
    },
    onError: (err: { detail?: unknown; message?: string }) => {
      setError(setupErrorDetail(err.detail))
      setPlainError(setupErrorDetail(err.detail) ? null : (err.message ?? String(err)))
    },
  })

  /** Apply the reviewed choices (second pass over the same preset): the
   * curated "models to add" selection plus the per-capability fill-empty
   * switches. Binding stays gap-fill backend-side — only empty defaults
   * are filled, nothing existing is ever removed. */
  const applyReview = useMutation({
    mutationFn: () => {
      if (preset === null || presetKey === null) throw new Error('no preset selected')
      return setupProviderPreset(presetKey, {
        api_key: preset.local ? null : apiKey.trim() || null,
        name: name.trim() || null,
        options: {
          curated_ids: preset.curated_models ? reviewOptions.curatedIds : undefined,
          bind_chat: reviewOptions.bindChat,
          bind_vision: reviewOptions.bindVision,
          bind_stt: reviewOptions.bindStt,
          bind_decision: reviewOptions.bindDecision && decisionDeclared,
        },
      })
    },
    onSuccess: async (data) => {
      await invalidate()
      setResult(data)
      setPhase('done')
    },
    onError: (err: { detail?: unknown; message?: string }) => {
      setApplyError(setupErrorDetail(err.detail))
      setApplyPlainError(setupErrorDetail(err.detail) ? null : (err.message ?? String(err)))
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

  if (phase === 'review' && result && preset) {
    // Effective candidates mirror the backend's gap-fill resolution:
    // preferred model (when its card stays selected) → first selected
    // curated text model; vision rides the same model when capable, else
    // the first selected vision-capable card; stt must keep its card.
    const selectedCurated = (preset.curated_models ?? []).filter((id) =>
      reviewOptions.curatedIds.includes(id),
    )
    const preferredId = preset.preferred_model?.id ?? null
    const textCandidate =
      (preferredId !== null && selectedCurated.includes(preferredId) ? preferredId : null) ??
      selectedCurated.find((id) => guessCaps(id).includes('text')) ??
      selectedCurated[0] ??
      null
    const visionCandidate =
      (textCandidate !== null && guessCaps(textCandidate).includes('vision') ? textCandidate : null) ??
      selectedCurated.find((id) => guessCaps(id).includes('vision')) ??
      null
    const sttCandidate =
      preset.stt_model && selectedCurated.includes(preset.stt_model) ? preset.stt_model : null

    const nowLabel = (requires: string) => {
      const label = defaultByCap.get(requires)?.model_label
      return t('settings.setup.review.now', { model: label ?? t('settings.setup.review.unset') })
    }
    const fillsLabel = (candidate: string | null, requires: string) =>
      candidate === null
        ? t('settings.setup.review.noCandidate')
        : `${nowLabel(requires)} · ${t('settings.setup.review.fills', { model: candidate })}`

    const assignmentRows = [
      ...(preset.type !== 'decision'
        ? [
            {
              id: 'chat',
              label: t('settings.setup.slot.chat'),
              sub: fillsLabel(textCandidate, 'text'),
              candidate: textCandidate,
              bind: reviewOptions.bindChat,
              set: (next: boolean) =>
                setReviewOptions((current) => ({ ...current, bindChat: next })),
            },
            {
              id: 'vision',
              label: t('settings.setup.slot.vision'),
              sub: fillsLabel(visionCandidate, 'vision'),
              candidate: visionCandidate,
              bind: reviewOptions.bindVision,
              set: (next: boolean) =>
                setReviewOptions((current) => ({ ...current, bindVision: next })),
            },
            ...(preset.stt_model
              ? [
                  {
                    id: 'stt',
                    label: t('settings.setup.slot.stt'),
                    sub: fillsLabel(sttCandidate, 'stt'),
                    candidate: sttCandidate,
                    bind: reviewOptions.bindStt,
                    set: (next: boolean) =>
                      setReviewOptions((current) => ({ ...current, bindStt: next })),
                  },
                ]
              : []),
          ]
        : []),
      ...(decisionCandidate !== null
        ? [
            {
              id: 'decision',
              label: t('settings.decisionDefaultLabel'),
              sub: fillsLabel(decisionCandidate.name, 'decision'),
              candidate: decisionCandidate.name,
              bind: reviewOptions.bindDecision,
              set: (next: boolean) =>
                setReviewOptions((current) => ({ ...current, bindDecision: next })),
            },
          ]
        : []),
    ]

    return (
      <ModalShell
        title={t('settings.setup.title')}
        description={t('settings.setup.review.intro', {
          name: resultName || preset.name,
          count: result.catalog_count,
        })}
        onClose={onClose}
      >
        <SetupSteps
          steps={[
            { id: 'connect', label: t('settings.setup.step.connect') },
            { id: 'defaults', label: t('settings.setup.step.defaults') },
          ]}
          current={1}
          label={t('settings.setup.step.progress')}
        />

        {(preset.curated_models ?? []).length > 0 ? (
          <section className="space-y-2">
            <div>
              <h3 className="text-sm font-semibold">{t('settings.setup.review.modelsTitle')}</h3>
              <p className="text-muted-foreground text-xs">
                {t('settings.setup.review.modelsHint')}
              </p>
            </div>
            <SetupReview
              models={(preset.curated_models ?? []).map((modelId) => ({
                id: modelId,
                name: modelId,
                caps: guessCaps(modelId),
                selected: reviewOptions.curatedIds.includes(modelId),
              }))}
              slots={[]}
              capIcons={CAP_ICONS}
              modelsLabel={t('settings.setup.review.modelsTitle')}
              footnote={t('settings.setup.review.modelsFootnote')}
              onOptionsChange={(options) =>
                setReviewOptions((current) => ({ ...current, curatedIds: options.curatedIds }))
              }
            />
          </section>
        ) : null}

        <SetupAssignments
          title={t('settings.setup.review.assignmentsTitle')}
          hint={t('settings.setup.review.assignmentsHint')}
          rows={assignmentRows.map((row) => ({
            id: row.id,
            label: row.label,
            hint: row.sub,
            checked: row.bind,
            disabled: row.candidate === null,
            onCheckedChange: row.set,
          }))}
        />

        <SetupErrorPanel error={applyError} plainError={applyPlainError} />
        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            disabled={applyReview.isPending}
            onClick={() => setPhase('form')}
          >
            {t('common.back')}
          </Button>
          <Button size="sm" disabled={applyReview.isPending} onClick={() => applyReview.mutate()}>
            {applyReview.isPending ? (
              <Loader2 className="animate-spin" aria-hidden />
            ) : (
              <Check aria-hidden />
            )}
            {t('settings.setup.review.apply')}
          </Button>
        </div>
      </ModalShell>
    )
  }

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
      <SetupSteps
        steps={[
          { id: 'connect', label: t('settings.setup.step.connect') },
          { id: 'defaults', label: t('settings.setup.step.defaults') },
        ]}
        current={0}
        label={t('settings.setup.step.progress')}
      />
      {phase === 'tiles' ? (
        <ProviderSetupTiles
          presets={order.map((key) => {
            const presetTile = presets.data?.[key]
            if (!presetTile) return { key, name: key }
            return {
              key,
              name: presetTile.name,
              chips: chipsForPreset(presetTile, t),
            }
          })}
          onSelect={openForm}
          label={t('settings.setup.title')}
          localLabel={t('settings.setup.local')}
        >
          <ProviderSetupManualTile onClick={openManual}>
            {t('settings.setup.custom')}
          </ProviderSetupManualTile>
        </ProviderSetupTiles>
      ) : null}

      {phase === 'form' && preset ? (
        <ProviderSetupForm
          preset={{
            key: presetKey ?? undefined,
            name: preset.name,
            keyUrl: preset.key_url ?? undefined,
            steps: preset.steps ?? undefined,
            freeTierNote: preset.free_tier_note ?? undefined,
            fixedBase: preset.fixed_base,
            baseUrl: preset.base_url,
            local: preset.local,
          }}
          value={{ name, apiKey, baseUrl: advancedBase }}
          onChange={(value: ProviderSetupFormValue) => {
            setName(value.name)
            setApiKey(value.apiKey)
            setAdvancedBase(value.baseUrl ?? '')
          }}
          testing={connectForm.isPending}
          error={
            error
              ? { code: error.code, suspectedVendor: error.suspected_vendor ?? null }
              : plainError
                ? { code: 'unknown' }
                : null
          }
          errorLabels={{
            ...Object.fromEntries(ERROR_CODES.map((code) => [code, t(`settings.setup.errors.${code}`)])),
            unknown: plainError ?? t('settings.setup.errors.unknown'),
          }}
          suspectedVendorHint={t('settings.setup.errors.suspectedVendor', {
            vendor: error?.suspected_vendor ?? '',
          })}
          advancedExtra={
            <>
              <HostingToggle local={isLocal} onChange={setIsLocal} disabled={preset.local} />
              <CountrySelect country={country} onChange={setCountry} />
            </>
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
          onSubmit={() => connectForm.mutate()}
          onCancel={backToTiles}
        />
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
          <SetupErrorPanel error={null} plainError={plainError} />
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

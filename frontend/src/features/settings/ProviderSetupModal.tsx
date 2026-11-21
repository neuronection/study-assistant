import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ModelPicker, type ModelPickerProvider } from '@/components/ui/model-picker'
import { SetupReview, type SetupReviewOptions } from '@/components/ui/setup-review'
import { SetupAssignments } from '@/components/ui/setup-assignments'
import { SetupSteps } from '@/components/ui/setup-steps'
import {
  assignTaskDefault,
  listModels,
  listTaskDefaults,
  setupErrorDetail,
  setupProviderPreset,
  type ProviderSetupErrorDetail,
  type ProviderSetupResult,
} from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

import { CAP_ICONS, guessCaps } from './ReRunSetupDialog'
import { SetupErrorPanel } from './setupErrors'
import {
  ProviderSetupConnect,
  type ProviderConnectOutcome,
  type ProviderConnectPhase,
} from './provider-setup/ProviderSetupConnect'

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

function SuccessDefaults({
  providerId,
  providerName,
  result,
  onContinueToTasks,
  onOpenModels,
  onClose,
}: {
  providerId: string
  providerName: string
  result: ProviderSetupResult
  onContinueToTasks?: () => void
  onOpenModels?: () => void
  onClose?: () => void
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
  const externalToId = new Map(
    providerModels.map((model) => [model.external_id, String(model.id)])
  )
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
      return assignTaskDefault(requires, modelId, fallback)
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
      ? [
          {
            requires: 'vision',
            label: t('settings.setup.slot.vision'),
            assigned: result.assigned_vision_model,
          },
        ]
      : []),
    ...(hasCap('stt')
      ? [
          {
            requires: 'stt',
            label: t('settings.setup.slot.stt'),
            assigned: result.assigned_stt_model,
          },
        ]
      : []),
    ...(hasCap('embeddings') || result.assigned_embeddings_model
      ? [
          {
            requires: 'embeddings',
            label: t('settings.setup.slot.embeddings'),
            assigned: result.assigned_embeddings_model ?? null,
          },
        ]
      : []),
  ]
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

  const finishActions = (
    <div className="flex flex-wrap justify-end gap-2 pt-1">
      {onClose ? (
        <Button size="sm" variant="outline" onClick={onClose}>
          {t('common.close')}
        </Button>
      ) : null}
      <Button size="sm" disabled={!onContinueToTasks} onClick={onContinueToTasks}>
        {t('settings.setup.continueToTasks')}
      </Button>
    </div>
  )

  if (models.isLoading) return null

  if (providerModels.length === 0) {
    return (
      <div
        className="space-y-2 rounded-md border border-warning/40 bg-warning/10 p-3"
        data-testid="setup-assign-models"
      >
        <h3 className="text-sm font-semibold">{t('settings.setup.assignModelsTitle')}</h3>
        <p className="text-xs text-muted-foreground">{t('settings.setup.assignModelsHint')}</p>
        {onOpenModels ? (
          <Button size="sm" variant="outline" onClick={onOpenModels}>
            {t('settings.setup.openModels')}
          </Button>
        ) : null}
        <p className="text-xs text-muted-foreground">{t('settings.setup.advancedHandoff')}</p>
        {finishActions}
      </div>
    )
  }

  const hasDefault =
    rows.some((row) => Boolean(slotValue(row.requires, row.assigned ?? null))) ||
    decisionRows.some((row) => Boolean(slotValue(row.requires, row.assigned ?? null)))

  return (
    <div className="border-border space-y-2 rounded-md border p-3">
      <h3 className="text-sm font-semibold">{t('settings.defaultModelsTitle')}</h3>
      {!hasDefault ? (
        <p className="text-warning text-xs">{t('settings.setup.assignModelsHint')}</p>
      ) : null}
      {rows.map((row) => (
        <ModelPicker
          key={row.requires}
          providers={catalog}
          value={slotValue(row.requires, row.assigned ?? null)}
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
      <p className="text-xs text-muted-foreground">{t('settings.setup.advancedHandoff')}</p>
      {finishActions}
    </div>
  )
}

function SuccessPanel({
  result,
  presetName,
  onContinueToTasks,
  onOpenModels,
  onClose,
}: {
  result: ProviderSetupResult
  presetName: string
  onContinueToTasks?: () => void
  onOpenModels?: () => void
  onClose?: () => void
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
        onContinueToTasks={onContinueToTasks}
        onOpenModels={onOpenModels}
        onClose={onClose}
      />
    </div>
  )
}

export function ProviderSetupModal({
  onClose,
  onContinueToTasks,
  onOpenModels,
}: {
  onClose: () => void
  onContinueToTasks?: () => void
  onOpenModels?: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  useCloseFloatings()

  const [phase, setPhase] = useState<'connect' | 'review' | 'done'>('connect')
  const [connectPhase, setConnectPhase] = useState<ProviderConnectPhase>('tiles')
  const [connectPresetName, setConnectPresetName] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<ProviderConnectOutcome | null>(null)
  const [result, setResult] = useState<ProviderSetupResult | null>(null)
  const [resultName, setResultName] = useState('')
  const [reviewOptions, setReviewOptions] = useState<SetupReviewOptions>({
    curatedIds: [],
    bindChat: true,
    bindVision: true,
    bindStt: true,
    bindDecision: true,
  })
  const [applyError, setApplyError] = useState<ProviderSetupErrorDetail | null>(null)
  const [applyPlainError, setApplyPlainError] = useState<string | null>(null)

  const preset = outcome?.preset ?? null
  const decisionCandidate =
    preset?.decision_models?.find((entry) => entry.id === preset.decision_default) ?? null
  const decisionDeclared = decisionCandidate !== null
  const defaults = useQuery({
    queryKey: ['task-defaults'],
    queryFn: listTaskDefaults,
    enabled: phase === 'review',
  })
  const defaultByCap = new Map((defaults.data ?? []).map((entry) => [entry.requires, entry]))

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['providers'] })
    await queryClient.invalidateQueries({ queryKey: ['models'] })
    await queryClient.invalidateQueries({ queryKey: ['tasks'] })
    await queryClient.invalidateQueries({ queryKey: ['task-defaults'] })
  }

  const handleConnected = async (next: ProviderConnectOutcome) => {
    setOutcome(next)
    setResult(next.result)
    setResultName(next.values.name || next.preset?.name || next.provider.name)
    await invalidate()
    if (next.mode === 'preset' && next.preset && next.result) {
      const nextDecisionDeclared =
        next.preset.decision_models?.some(
          (entry) => entry.id === next.preset?.decision_default
        ) ?? false
      setReviewOptions({
        curatedIds: next.preset.curated_models ?? [],
        bindChat: true,
        bindVision: true,
        bindStt: true,
        bindDecision: nextDecisionDeclared,
      })
      setApplyError(null)
      setApplyPlainError(null)
      setPhase('review')
      return
    }
    setPhase('done')
  }

  const applyReview = useMutation({
    mutationFn: () => {
      if (outcome?.presetKey == null || outcome.preset == null) {
        throw new Error('no preset selected')
      }
      return setupProviderPreset(outcome.presetKey, {
        api_key: outcome.values.apiKey || null,
        name: outcome.values.name || null,
        options: {
          curated_ids: outcome.preset.curated_models ? reviewOptions.curatedIds : undefined,
          bind_chat: reviewOptions.bindChat,
          bind_vision: reviewOptions.bindVision,
          bind_stt: reviewOptions.bindStt,
          bind_embeddings: true,
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
      setApplyPlainError(setupErrorDetail(err.detail) ? null : err.message ?? String(err))
    },
  })

  if (phase === 'review' && result && preset) {
    const selectedCurated = (preset.curated_models ?? []).filter((id) =>
      reviewOptions.curatedIds.includes(id)
    )
    const preferredId = preset.preferred_model?.id ?? null
    const textCandidate =
      (preferredId !== null && selectedCurated.includes(preferredId) ? preferredId : null) ??
      selectedCurated.find((id) => guessCaps(id).includes('text')) ??
      selectedCurated[0] ??
      null
    const visionCandidate =
      (textCandidate !== null && guessCaps(textCandidate).includes('vision')
        ? textCandidate
        : null) ??
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
              sub: fillsLabel(decisionCandidate.name ?? null, 'decision'),
              candidate: decisionCandidate.name ?? '',
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
            { id: 'tasks', label: t('settings.setup.step.tasks') },
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
            onClick={() => setPhase('connect')}
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

  if (phase === 'done') {
    return (
      <ModalShell
        title={t('settings.setup.title')}
        description={t('settings.setup.hint')}
        onClose={onClose}
      >
        <SetupSteps
          steps={[
            { id: 'connect', label: t('settings.setup.step.connect') },
            { id: 'defaults', label: t('settings.setup.step.defaults') },
            { id: 'tasks', label: t('settings.setup.step.tasks') },
          ]}
          current={2}
          label={t('settings.setup.step.progress')}
        />
        {result && outcome?.mode === 'preset' ? (
          <SuccessPanel
            result={result}
            presetName={resultName}
            onContinueToTasks={onContinueToTasks}
            onOpenModels={onOpenModels}
            onClose={onClose}
          />
        ) : (
          <div className="space-y-2">
            <p className="flex items-center gap-2 text-sm font-medium">
              <Check className="text-success size-4" aria-hidden />
              {t('settings.setup.done', { name: resultName })}
            </p>
            <p className="text-xs text-muted-foreground">{t('settings.setup.assignModelsHint')}</p>
            <div className="flex flex-wrap justify-end gap-2">
              {onOpenModels ? (
                <Button size="sm" variant="outline" onClick={onOpenModels}>
                  {t('settings.setup.openModels')}
                </Button>
              ) : null}
              <Button size="sm" variant="outline" onClick={onClose}>
                {t('common.close')}
              </Button>
              <Button size="sm" disabled={!onContinueToTasks} onClick={onContinueToTasks}>
                {t('settings.setup.continueToTasks')}
              </Button>
            </div>
          </div>
        )}
      </ModalShell>
    )
  }

  return (
    <ModalShell
      title={
        connectPhase === 'form' && connectPresetName
          ? t('settings.setup.formTitle', { name: connectPresetName })
          : t('settings.setup.title')
      }
      description={t('settings.setup.modalHint')}
      onClose={onClose}
    >
      <ProviderSetupConnect
        showSteps
        onPhaseChange={(next, name) => {
          setConnectPhase(next)
          setConnectPresetName(name)
        }}
        onConnected={handleConnected}
      />
    </ModalShell>
  )
}

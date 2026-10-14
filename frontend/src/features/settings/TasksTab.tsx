import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AudioLines,
  Database,
  FileText,
  Eye,
  Languages,
  ListChecks,
  MessageSquare,
  Network,
  PenLine,
  Puzzle,
  ScanText,
  ShieldCheck,
  Sparkles,
  Star,
  Tag,
  Volume2,
  Wrench,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { beautifyId } from '@neuronection/assistant-ui/fuzzy'
import type { LucideIcon } from 'lucide-react'
import type { ModelPickerProvider } from '@/components/ui/model-picker'
import { ModelPicker } from '@/components/ui/model-picker'
import { InfoButton } from '@/components/ui/InfoButton'
import {
  TaskAssignmentPicker,
  type TaskAssignmentSection,
} from '@/components/ui/task-assignment-picker'
import {
  assignTask,
  assignTaskDefault,
  getCosts,
  listModels,
  listProviders,
  listPresets,
  listTaskDefaults,
  listTasks,
} from '@/lib/api'
import { formatMonth, formatNumber } from '@/lib/format'

const CONSEQUENCE: Record<string, string> = {
  embeddings: 'semantic search is off (FTS-only)',
  concepts: 'concept extraction is unavailable',
}

const CAP_ORDER = ['text', 'vision', 'embeddings', 'stt', 'tts'] as const
const DEFAULT_PREFIX = 'default:'
const DECISION_SLOTS = [
  'decision:tool-dispatch',
  'decision:boolean-gate',
  'decision:choice',
  'decision:score',
] as const
const DECISION_ICONS = {
  'decision:tool-dispatch': Wrench,
  'decision:boolean-gate': ShieldCheck,
  'decision:choice': Languages,
  'decision:score': Tag,
} as const
const CAP_ICONS = { text: FileText, vision: Eye, tools: Wrench, embeddings: Database, stt: AudioLines, tts: Volume2, decision: Sparkles }
const TASK_ICONS: Record<string, typeof ListChecks> = {
  quizgen: ListChecks,
  exgen: Puzzle,
  chat: MessageSquare,
  ocr: ScanText,
  drawing_ocr: ScanText,
  image_ocr: ScanText,
  embeddings: Database,
  concepts: Network,
  description: FileText,
  compose: PenLine,
  editor_transform: Sparkles,
  transcribe: AudioLines,
}

interface DecisionKindRowProps {
  slot: string
  label: string
  description: string
  icon: LucideIcon
  catalog: ModelPickerProvider[]
  modelValue: string | null
  fallbackValue: string | null
  inheritLabel: string
  fallbackLabel: string
  primaryLabel: string
  primaryInfo: string
  fallbackInfo: string
  clearLabel: string
  disabled: boolean
  onAssign: (slot: string, modelId: string | null) => void
  onAssignFallback: (slot: string, modelId: string | null) => void
}

/**
 * One Decision defaults card kind row (plan 29 / ADR-0036 D3/D4): the row
 * shape users already know (icon tile, fallback + primary pickers, X
 * clears), but the primary picker's option list LEADS with the labeled
 * null entry — "Inherits — {resolved default model}" — and choosing it
 * assigns null, which *is* the inherit state. Composed app-side from the
 * library `ModelPicker nullOption` primitive; `TaskAssignmentPicker` is
 * untouched.
 */
function DecisionKindRow({
  slot,
  label,
  description,
  icon: Icon,
  catalog,
  modelValue,
  fallbackValue,
  inheritLabel,
  fallbackLabel,
  primaryLabel,
  primaryInfo,
  fallbackInfo,
  clearLabel,
  disabled,
  onAssign,
  onAssignFallback,
}: DecisionKindRowProps) {
  return (
    <div className="flex flex-col gap-2 rounded-[var(--as-radius-lg)] border border-[var(--as-border)] bg-[var(--as-surface-raised)] p-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-[var(--as-radius)] bg-[var(--as-muted)] text-[var(--as-muted-fg)]">
          <Icon className="size-4" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[var(--as-fg)]">{label}</p>
          <p className="truncate text-xs text-[var(--as-muted-fg)]">{description}</p>
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-start gap-2 self-center">
        <div className="flex items-center gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-full bg-[var(--as-muted)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--as-muted-fg)]">
            {fallbackLabel}
          </span>
          <ModelPicker
            providers={catalog}
            value={fallbackValue ?? ''}
            onChange={(modelId) => onAssignFallback(slot, modelId)}
            disabled={disabled}
            clearable={false}
            label={`${fallbackLabel} — ${label}`}
            hideLabel
            className="w-52"
          />
          {fallbackInfo ? (
            <InfoButton
              label={`${fallbackLabel} — ${label}`}
              showOnHover={false}
              openOnHover={false}
            >
              {fallbackInfo}
            </InfoButton>
          ) : null}
          {fallbackValue ? (
            <button
              type="button"
              aria-label={`${clearLabel} — ${fallbackLabel} ${label}`}
              disabled={disabled}
              onClick={() => onAssignFallback(slot, null)}
              className="cursor-pointer rounded-[var(--as-radius-sm)] p-1.5 text-[var(--as-muted-fg)] transition-colors hover:bg-[var(--as-muted)] hover:text-[var(--as-fg)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--as-focus-ring)] disabled:pointer-events-none disabled:opacity-50"
            >
              <X className="size-4" aria-hidden />
            </button>
          ) : null}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-flex items-center gap-1 rounded-full bg-[var(--as-muted)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--as-muted-fg)]">
            <Star className="size-2.5" aria-hidden />
            {primaryLabel}
          </span>
          <ModelPicker
            providers={catalog}
            value={modelValue ?? ''}
            nullOption={{ label: inheritLabel }}
            onChange={(modelId: string | null) => onAssign(slot, modelId)}
            disabled={disabled}
            clearable={false}
            label={label}
            hideLabel
            className="w-52"
          />
          {primaryInfo ? (
            <InfoButton
              label={`${primaryLabel} — ${label}`}
              showOnHover={false}
              openOnHover={false}
            >
              {primaryInfo}
            </InfoButton>
          ) : null}
          {modelValue ? (
            <button
              type="button"
              aria-label={`${clearLabel} — ${label}`}
              disabled={disabled}
              onClick={() => onAssign(slot, null)}
              className="cursor-pointer rounded-[var(--as-radius-sm)] p-1.5 text-[var(--as-muted-fg)] transition-colors hover:bg-[var(--as-muted)] hover:text-[var(--as-fg)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--as-focus-ring)] disabled:pointer-events-none disabled:opacity-50"
            >
              <X className="size-4" aria-hidden />
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export function TasksTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const providersQ = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const tasks = useQuery({ queryKey: ['tasks'], queryFn: listTasks })
  const defaults = useQuery({ queryKey: ['task-defaults'], queryFn: listTaskDefaults })
  const costs = useQuery({ queryKey: ['costs'], queryFn: getCosts })
  const presetsQ = useQuery({ queryKey: ['presets'], queryFn: listPresets })
  const [error, setError] = useState<string | null>(null)

  // The family's basic decision default: the first canonical preset (in
  // presetOrder) declaring one — a display-level suggestion for the empty
  // decision default, never an assignment.
  const decisionSuggestion = (() => {
    for (const preset of Object.values(presetsQ.data ?? {})) {
      if (preset.decision_default) {
        return { model: preset.decision_default, provider: preset.name }
      }
    }
    return null
  })()

  const enabledModels = (models.data ?? []).filter(
    (model) => model.enabled && !model.missing
  )
  const providerNames = new Map(
    (providersQ.data ?? []).map((provider) => [provider.id, provider.name])
  )
  const modelLabels = new Map(
    (models.data ?? []).map((model) => [String(model.id), model.label || model.external_id])
  )
  const catalog = Object.values(
    enabledModels.reduce<Record<number, ModelPickerProvider>>((acc, model) => {
      acc[model.provider_id] = acc[model.provider_id] ?? {
        id: String(model.provider_id),
        name: providerNames.get(model.provider_id) ?? `#${model.provider_id}`,
        models: [],
      }
      acc[model.provider_id].models.push({
        id: String(model.id),
        name: model.label || model.external_id,
        capabilities: model.caps,
      })
      return acc
    }, {})
  )
  // Decision pickers offer only decision-declaring models (slot
  // separation, ADR-0032 D4).
  const decisionCatalog = catalog
    .map((provider) => ({
      ...provider,
      models: provider.models.filter((model) => model.capabilities?.includes('decision')),
    }))
    .filter((provider) => provider.models.length > 0)

  const assign = useMutation({
    mutationFn: ({ task, modelId }: { task: string; modelId: number | null }) =>
      assignTask(task, modelId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: (err: Error) => setError(err.message),
  })
  const assignDefault = useMutation({
    mutationFn: ({
      requires,
      modelId,
      fallbackModelId,
    }: {
      requires: string
      modelId: number | null
      fallbackModelId: number | null
    }) => assignTaskDefault(requires, modelId, fallbackModelId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
      await queryClient.invalidateQueries({ queryKey: ['task-defaults'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const costByTask = new Map(
    (costs.data?.per_task ?? []).map((entry) => [entry.task, entry])
  )
  const defaultByCap = new Map(
    (defaults.data ?? []).map((entry) => [entry.requires, entry])
  )

  const value: Record<string, string | null> = {}
  const secondaryValue: Record<string, string | null> = {}
  // ADR-0037: capability defaults are single-slot — the kind rows carry
  // the only fallback wiring on default-backed rows.
  for (const slot of DECISION_SLOTS) {
    const entry = defaultByCap.get(slot)
    value[slot] = entry?.model_id != null ? String(entry.model_id) : null
    secondaryValue[slot] = entry?.fallback_model_id != null ? String(entry.fallback_model_id) : null
  }
  const decisionDefaultEntry = defaultByCap.get('decision')
  value[`${DEFAULT_PREFIX}decision`] =
    decisionDefaultEntry?.model_id != null ? String(decisionDefaultEntry.model_id) : null
  for (const task of tasks.data ?? []) {
    value[task.task] = task.model_id != null ? String(task.model_id) : null
  }

  const handleAssign = (taskId: string, modelId: string | null) => {
    setError(null)
    const id = modelId ? Number(modelId) : null
    if (taskId.startsWith(DEFAULT_PREFIX) || taskId.startsWith('decision:')) {
      const requires = taskId.startsWith(DEFAULT_PREFIX)
        ? taskId.slice(DEFAULT_PREFIX.length)
        : taskId
      const entry = defaultByCap.get(requires)
      assignDefault.mutate({
        requires,
        modelId: id,
        fallbackModelId:
          entry?.fallback_model_id != null ? Number(entry.fallback_model_id) : null,
      })
    } else {
      assign.mutate({ task: taskId, modelId: id })
    }
  }

  const handleAssignSecondary = (taskId: string, modelId: string | null) => {
    setError(null)
    const requires = taskId.startsWith(DEFAULT_PREFIX)
      ? taskId.slice(DEFAULT_PREFIX.length)
      : taskId
    const entry = defaultByCap.get(requires)
    assignDefault.mutate({
      requires,
      modelId: entry?.model_id ?? null,
      fallbackModelId: modelId ? Number(modelId) : null,
    })
  }

  // ADR-0036 §4: what a kind's labeled null option names — the resolved
  // inherit model (the `decision` default's resolution for that kind),
  // surfaced by the API; honestly bare "Inherits" when nothing resolves.
  const inheritLabelFor = (slot: string): string => {
    const resolved = defaultByCap.get(slot)?.resolved_inherit_label ?? null
    return resolved
      ? t('settings.decisionInheritsLabel', { model: resolved })
      : t('settings.decisionInheritsEmpty')
  }

  // D7 "Simplify": only when all four kinds resolve to one model and the
  // default is empty — a suggestion, never automatic.
  const simplifyModelId = (() => {
    if (decisionDefaultEntry?.model_id != null) return null
    let resolved: string | null = null
    for (const slot of DECISION_SLOTS) {
      const entry = defaultByCap.get(slot)
      const kindModel =
        entry?.model_id != null
          ? String(entry.model_id)
          : entry?.fallback_model_id != null
            ? String(entry.fallback_model_id)
            : null
      if (kindModel === null) return null
      if (resolved === null) {
        resolved = kindModel
      } else if (resolved !== kindModel) {
        return null
      }
    }
    return resolved
  })()

  const sharedPickerProps = {
    providers: catalog,
    value,
    onAssign: handleAssign,
    primaryLabel: t('settings.primaryPicker'),
    primaryInfo: t('settings.primaryInfo'),
    fallbackInfo: t('settings.fallbackInfo'),
    clearLabel: t('settings.clearAssignment'),
    disabled: assign.isPending || assignDefault.isPending,
  } as const

  const defaultsSection: TaskAssignmentSection = {
    id: 'defaults',
    label: t('settings.defaultModelsTitle'),
    description: t('settings.defaultModelsHint'),
    // ADR-0037: capability defaults are single-slot — one picker per row,
    // no fallback pickers (the Decision kinds group keeps its own).
    tasks: [
      ...CAP_ORDER.map((cap) => ({
        id: `${DEFAULT_PREFIX}${cap}`,
        label: beautifyId(t(`settings.caps.${cap}`)),
        requires: cap,
        icon: CAP_ICONS[cap],
      })),
      // The decision default rides the uniform section like every other
      // capability default (ADR-0036 §4, post-landing owner ruling): same
      // row machinery, same endpoint, same `default:` id convention —
      // the picker's own `requires` filter narrows it to decision-capable
      // models.
      {
        id: `${DEFAULT_PREFIX}decision`,
        label: t('settings.decisionDefaultLabel'),
        requires: 'decision',
        icon: CAP_ICONS.decision,
      },
    ],
  }

  const overridesSection: TaskAssignmentSection = {
    id: 'overrides',
    label: t('settings.taskOverrides'),
    tasks: (tasks.data ?? []).map((task) => ({
      id: task.task,
      label: beautifyId(task.task),
      description: task.description,
      requires: task.requires,
      icon: TASK_ICONS[task.task],
    })),
  }

  const decisionDefaultEmpty = decisionDefaultEntry?.model_id == null

  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-sm">{t('settings.tasksHint')}</p>
      {costs.data && costs.data.total_usd > 0 ? (
        <p className="text-muted-foreground text-xs">
          {t('settings.costSummary', {
            total: formatNumber(costs.data.total_usd, 2),
            month: formatMonth(costs.data.month),
          })}
        </p>
      ) : null}
      {error ? <p className="text-danger text-xs">{error}</p> : null}
      <TaskAssignmentPicker
        sections={[defaultsSection]}
        {...sharedPickerProps}
        renderMeta={(task) => {
          // Per-row context for the decision default row only: the
          // empty-default hint + the canonical preset suggestion, and the
          // D7 "Simplify" chip — a suggestion, never automatic.
          if (task.id !== `${DEFAULT_PREFIX}decision`) {
            return null
          }
          return (
            <div className="space-y-1">
              {decisionDefaultEmpty ? (
                <p className="text-xs text-[var(--as-muted-fg)]">
                  {t('settings.decisionDefaultsEmptyHint')}
                  {decisionSuggestion
                    ? ' ' +
                      t('settings.suggestedDecisionDefault', {
                        model: decisionSuggestion.model,
                        provider: decisionSuggestion.provider,
                      })
                    : ''}
                </p>
              ) : null}
              {simplifyModelId !== null ? (
                <button
                  type="button"
                  className="justify-self-start rounded-full bg-subtle px-2.5 py-1 text-[11px] text-[var(--as-fg)] transition-colors hover:bg-[var(--as-muted)] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--as-focus-ring)] disabled:opacity-50"
                  disabled={assignDefault.isPending}
                  onClick={() => {
                    setError(null)
                    assignDefault.mutate({
                      requires: 'decision',
                      modelId: Number(simplifyModelId),
                      fallbackModelId: null,
                    })
                  }}
                >
                  {t('settings.decisionSimplifyUseAsDefault', {
                    model: modelLabels.get(simplifyModelId) ?? simplifyModelId,
                  })}
                </button>
              ) : null}
            </div>
          )
        }}
      />
      <div className="flex flex-col gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--as-muted-fg)]">
            {t('settings.decisionKindsTitle')}
          </p>
          <p className="mt-0.5 text-xs text-[var(--as-muted-fg)]">
            {t('settings.decisionGroupPrivacy')}
          </p>
        </div>
        {DECISION_SLOTS.map((slot) => (
          <DecisionKindRow
            key={slot}
            slot={slot}
            label={t(`settings.decisionSlots.${slot.slice('decision:'.length)}`)}
            description={t(
              `settings.decisionSlots.${slot.slice('decision:'.length)}Description`
            )}
            icon={DECISION_ICONS[slot]}
            catalog={decisionCatalog}
            modelValue={value[slot] ?? null}
            fallbackValue={secondaryValue[slot] ?? null}
            inheritLabel={inheritLabelFor(slot)}
            fallbackLabel={t('settings.defaultFallbackLabel')}
            primaryLabel={t('settings.primaryPicker')}
            primaryInfo={t('settings.primaryInfo')}
            fallbackInfo={t('settings.fallbackInfo')}
            clearLabel={t('settings.clearAssignment')}
            disabled={assign.isPending || assignDefault.isPending}
            onAssign={handleAssign}
            onAssignFallback={handleAssignSecondary}
          />
        ))}
      </div>
      <TaskAssignmentPicker
        sections={[overridesSection]}
        {...sharedPickerProps}
        renderMeta={(task) => {
          const info = (tasks.data ?? []).find((entry) => entry.task === task.id)
          if (!info) {
            return null
          }
          const cost = costByTask.get(info.task)
          const effectivelyUnassigned =
            info.model_id === null && info.default_model_label === null
          return (
            <div className="space-y-0.5">
              <p>
                <span className="text-muted-foreground rounded-full bg-subtle px-2 py-0.5 text-[11px]">
                  {info.requires}
                </span>
              </p>
              {info.inherits_default && info.default_model_label ? (
                <p className="text-muted-foreground text-[11px]">
                  {t('settings.inheritedFromDefault', { label: info.default_model_label })}
                </p>
              ) : null}
              {effectivelyUnassigned && CONSEQUENCE[info.task] ? (
                <p className="text-warning text-[11px]">
                  {t('settings.unassignedNudge', { consequence: CONSEQUENCE[info.task] })}
                </p>
              ) : null}
              {cost && cost.calls > 0 ? (
                <p className="text-[11px] text-muted-foreground">
                  {t('settings.taskSpend', {
                    cost: formatNumber(cost.cost_usd, 3),
                    calls: cost.calls,
                  })}
                </p>
              ) : null}
            </div>
          )
        }}
      />
    </div>
  )
}

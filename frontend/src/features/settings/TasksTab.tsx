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
  Tag,
  Volume2,
  Wrench,
} from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { beautifyId } from '@neuronection/assistant-ui/fuzzy'
import type { ModelPickerProvider } from '@/components/ui/model-picker'
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
  // presetOrder) declaring one — a display-level suggestion for empty
  // decision slots, never an assignment.
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
  for (const cap of CAP_ORDER) {
    const entry = defaultByCap.get(cap)
    value[`${DEFAULT_PREFIX}${cap}`] = entry?.model_id != null ? String(entry.model_id) : null
    secondaryValue[`${DEFAULT_PREFIX}${cap}`] =
      entry?.fallback_model_id != null ? String(entry.fallback_model_id) : null
  }
  for (const slot of DECISION_SLOTS) {
    const entry = defaultByCap.get(slot)
    value[slot] = entry?.model_id != null ? String(entry.model_id) : null
    secondaryValue[slot] = entry?.fallback_model_id != null ? String(entry.fallback_model_id) : null
  }
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
        fallbackModelId: entry?.fallback_model_id ?? null,
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

  const sections: TaskAssignmentSection[] = [
    {
      id: 'defaults',
      label: t('settings.defaultModelsTitle'),
      description: t('settings.defaultModelsHint'),
      secondary: true,
      tasks: CAP_ORDER.map((cap) => ({
        id: `${DEFAULT_PREFIX}${cap}`,
        label: beautifyId(t(`settings.caps.${cap}`)),
        requires: cap,
        icon: CAP_ICONS[cap],
      })),
    },
    {
      id: 'decision',
      label: t('settings.decisionGroupTitle'),
      description: t('settings.decisionGroupPrivacy'),
      secondary: true,
      tasks: DECISION_SLOTS.map((slot) => ({
        id: slot,
        label: t(`settings.decisionSlots.${slot.slice('decision:'.length)}`),
        description: t(
          `settings.decisionSlots.${slot.slice('decision:'.length)}Description`
        ),
        requires: 'decision',
        icon: DECISION_ICONS[slot],
        secondary: true,
      })),
    },
    {
      id: 'overrides',
      label: t('settings.taskOverrides'),
      tasks: (tasks.data ?? []).map((task) => ({
        id: task.task,
        label: beautifyId(task.task),
        description: task.description,
        requires: task.requires,
        icon: TASK_ICONS[task.task],
      })),
    },
  ]

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
        sections={sections}
        providers={catalog}
        value={value}
        secondaryValue={secondaryValue}
        onAssign={handleAssign}
        onAssignSecondary={handleAssignSecondary}
        secondaryLabel={t('settings.defaultFallbackLabel')}
        primaryLabel={t('settings.primaryPicker')}
        primaryInfo={t('settings.primaryInfo')}
        fallbackInfo={t('settings.fallbackInfo')}
        clearLabel={t('settings.clearAssignment')}
        disabled={assign.isPending || assignDefault.isPending}
        renderMeta={(task) => {
          if (task.id.startsWith(DEFAULT_PREFIX)) {
            return null
          }
          if (task.id.startsWith('decision:') && !value[task.id]) {
            const suggestion = decisionSuggestion
            if (suggestion) {
              return (
                <p className="text-[11px] text-muted-foreground">
                  {t('settings.suggestedDecisionDefault', {
                    model: suggestion.model,
                    provider: suggestion.provider,
                  })}
                </p>
              )
            }
            return null
          }
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

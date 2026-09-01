import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

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
  listTaskDefaults,
  listTasks,
  setTaskBudget,
} from '@/lib/api'
import { cn } from '@/lib/utils'

const CONSEQUENCE: Record<string, string> = {
  embeddings: 'semantic search is off (FTS-only)',
  concepts: 'concept extraction is unavailable',
}

const CAP_ORDER = ['text', 'vision', 'embeddings', 'audio'] as const
const DEFAULT_PREFIX = 'default:'

export function TasksTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const providersQ = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const tasks = useQuery({ queryKey: ['tasks'], queryFn: listTasks })
  const defaults = useQuery({ queryKey: ['task-defaults'], queryFn: listTaskDefaults })
  const costs = useQuery({ queryKey: ['costs'], queryFn: getCosts })
  const [error, setError] = useState<string | null>(null)

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
  const budget = useMutation({
    mutationFn: ({ task, cap }: { task: string; cap: number | null }) =>
      setTaskBudget(task, cap),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['costs'] })
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
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
  for (const task of tasks.data ?? []) {
    value[task.task] = task.model_id != null ? String(task.model_id) : null
  }

  const handleAssign = (taskId: string, modelId: string | null) => {
    setError(null)
    const id = modelId ? Number(modelId) : null
    if (taskId.startsWith(DEFAULT_PREFIX)) {
      const cap = taskId.slice(DEFAULT_PREFIX.length)
      const entry = defaultByCap.get(cap)
      assignDefault.mutate({
        requires: cap,
        modelId: id,
        fallbackModelId: entry?.fallback_model_id ?? null,
      })
    } else {
      assign.mutate({ task: taskId, modelId: id })
    }
  }

  const handleAssignSecondary = (taskId: string, modelId: string | null) => {
    setError(null)
    const cap = taskId.slice(DEFAULT_PREFIX.length)
    const entry = defaultByCap.get(cap)
    assignDefault.mutate({
      requires: cap,
      modelId: entry?.model_id ?? null,
      fallbackModelId: modelId ? Number(modelId) : null,
    })
  }

  const sections: TaskAssignmentSection[] = [
    {
      id: 'defaults',
      label: t('settings.defaultModelsTitle'),
      secondary: true,
      tasks: CAP_ORDER.map((cap) => ({
        id: `${DEFAULT_PREFIX}${cap}`,
        label: t('settings.defaultModelLabel', { cap: t(`settings.caps.${cap}`) }),
        description: t('settings.defaultModelHint', { cap: t(`settings.caps.${cap}`) }),
        requires: cap,
      })),
    },
    {
      id: 'overrides',
      label: t('settings.taskOverrides'),
      tasks: (tasks.data ?? []).map((task) => ({
        id: task.task,
        label: task.task,
        description: task.description,
        requires: task.requires,
      })),
    },
  ]

  return (
    <div className="space-y-2">
      <p className="text-muted-foreground text-sm">{t('settings.tasksHint')}</p>
      {costs.data && costs.data.total_usd > 0 ? (
        <p className="text-muted-foreground text-xs">
          {t('settings.costSummary', {
            total: costs.data.total_usd.toFixed(2),
            month: costs.data.month,
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
        unassignedLabel={t('settings.unassigned')}
        clearLabel={t('settings.unassigned')}
        modelLabel={t('settings.model')}
        disabled={assign.isPending || assignDefault.isPending}
        renderMeta={(task) => {
          if (task.id.startsWith(DEFAULT_PREFIX)) {
            return null
          }
          const info = (tasks.data ?? []).find((entry) => entry.task === task.id)
          if (!info) {
            return null
          }
          const cost = costByTask.get(info.task)
          const overBudget =
            cost && cost.monthly_cap_usd !== null && cost.cost_usd >= cost.monthly_cap_usd
          const effectivelyUnassigned =
            info.model_id === null && info.default_model_label === null
          return (
            <div className="space-y-0.5">
              <p>
                <span className="text-muted-foreground rounded-full bg-subtle px-2 py-0.5 text-[11px]">
                  {info.requires}
                </span>
                {overBudget ? (
                  <span className="bg-danger/15 text-danger ml-2 rounded-full px-2 py-0.5 text-[11px]">
                    {t('settings.budgetHit')}
                  </span>
                ) : null}
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
                <p
                  className={cn(
                    'text-[11px]',
                    overBudget ? 'text-danger' : 'text-muted-foreground'
                  )}
                >
                  {t('settings.taskSpend', {
                    cost: cost.cost_usd.toFixed(3),
                    calls: cost.calls,
                  })}
                </p>
              ) : null}
              <input
                type="number"
                min={0}
                step="0.5"
                className="bg-surface border-border w-20 rounded-md border px-2 py-1 text-xs"
                placeholder={t('settings.budgetPlaceholder')}
                defaultValue={info.monthly_cap_usd ?? ''}
                key={`${info.task}-${info.monthly_cap_usd ?? 'none'}`}
                onBlur={(event) => {
                  const raw = event.target.value.trim()
                  budget.mutate({ task: info.task, cap: raw === '' ? null : Number(raw) })
                }}
                aria-label={t('settings.budgetLabel', { task: info.task })}
              />
            </div>
          )
        }}
      />
    </div>
  )
}

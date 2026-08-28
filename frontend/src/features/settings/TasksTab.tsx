import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  assignTask,
  assignTaskDefault,
  getCosts,
  listModels,
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

export function TasksTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const tasks = useQuery({ queryKey: ['tasks'], queryFn: listTasks })
  const defaults = useQuery({ queryKey: ['task-defaults'], queryFn: listTaskDefaults })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const costs = useQuery({ queryKey: ['costs'], queryFn: getCosts })
  const enabledModels = (models.data ?? []).filter((model) => model.enabled && !model.missing)

  const assign = useMutation({
    mutationFn: ({ task, modelId }: { task: string; modelId: number | null }) =>
      assignTask(task, modelId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })
  const assignDefault = useMutation({
    mutationFn: ({ requires, modelId, fallbackModelId }: { requires: string; modelId: number | null; fallbackModelId: number | null }) =>
      assignTaskDefault(requires, modelId, fallbackModelId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
      await queryClient.invalidateQueries({ queryKey: ['task-defaults'] })
    },
  })
  const budget = useMutation({
    mutationFn: ({ task, cap }: { task: string; cap: number | null }) =>
      setTaskBudget(task, cap),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
      await queryClient.invalidateQueries({ queryKey: ['costs'] })
    },
  })
  const [error, setError] = useState<string | null>(null)

  const assignable = (requires: string) =>
    enabledModels.filter((model) => model.caps.includes(requires))

  const costByTask = new Map((costs.data?.per_task ?? []).map((entry) => [entry.task, entry]))
  const defaultByCap = new Map(
    (defaults.data ?? []).map((entry) => [entry.requires, entry])
  )

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
      <div className="border-border space-y-2 rounded-md border p-3">
        <div>
          <p className="text-sm font-medium">{t('settings.defaultModelsTitle')}</p>
          <p className="text-muted-foreground text-xs">{t('settings.defaultModelsHint')}</p>
        </div>
        {CAP_ORDER.map((requires) => {
          const capLabel = t(`settings.caps.${requires}`)
          const entry = defaultByCap.get(requires)
          const options = assignable(requires)
          return (
            <div key={requires} className="flex flex-wrap items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{t('settings.defaultModelLabel', { cap: capLabel })}</p>
                <p className="text-muted-foreground text-xs">
                  {t('settings.defaultModelHint', { cap: capLabel })}
                </p>
              </div>
              <select
                className="bg-surface border-border max-w-52 rounded-md border px-2 py-1.5 text-xs"
                value={entry?.model_id ?? ''}
                onChange={(event) => {
                  const value = event.target.value
                  setError(null)
                  assignDefault.mutate(
                    {
                      requires,
                      modelId: value === '' ? null : Number(value),
                      fallbackModelId: entry?.fallback_model_id ?? null,
                    },
                    { onError: (err: Error) => setError(err.message) }
                  )
                }}
                aria-label={t('settings.defaultModelLabel', { cap: capLabel })}
              >
                <option value="">{t('settings.unassigned')}</option>
                {options.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </select>
              <select
                className="bg-surface border-border max-w-52 rounded-md border px-2 py-1.5 text-xs"
                value={entry?.fallback_model_id ?? ''}
                onChange={(event) => {
                  const value = event.target.value
                  setError(null)
                  assignDefault.mutate(
                    {
                      requires,
                      modelId: entry?.model_id ?? null,
                      fallbackModelId: value === '' ? null : Number(value),
                    },
                    { onError: (err: Error) => setError(err.message) }
                  )
                }}
                aria-label={`${t('settings.defaultModelLabel', { cap: capLabel })} — ${t('settings.defaultFallbackLabel')}`}
              >
                <option value="">{t('settings.unassigned')}</option>
                {options.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.label}
                  </option>
                ))}
              </select>
            </div>
          )
        })}
      </div>
      {(tasks.data ?? []).map((task) => {
        const cost = costByTask.get(task.task)
        const overBudget =
          cost && cost.monthly_cap_usd !== null && cost.cost_usd >= cost.monthly_cap_usd
        const effectivelyUnassigned =
          task.model_id === null && task.default_model_label === null
        return (
          <div
            key={task.task}
            className="border-border flex items-center gap-3 rounded-md border px-3 py-2"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">
                {task.task}
                <span className="text-muted-foreground ml-2 rounded-full bg-subtle px-2 py-0.5 text-[11px]">
                  {task.requires}
                </span>
                {overBudget ? (
                  <span className="bg-danger/15 text-danger ml-2 rounded-full px-2 py-0.5 text-[11px]">
                    {t('settings.budgetHit')}
                  </span>
                ) : null}
              </p>
              <p className="text-muted-foreground truncate text-xs">{task.description}</p>
              {task.inherits_default && task.default_model_label ? (
                <p className="text-muted-foreground text-[11px]">
                  {t('settings.inheritedFromDefault', { label: task.default_model_label })}
                </p>
              ) : null}
              {effectivelyUnassigned && CONSEQUENCE[task.task] ? (
                <p className="text-warning text-[11px]">
                  {t('settings.unassignedNudge', { consequence: CONSEQUENCE[task.task] })}
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
            </div>
            <input
              type="number"
              min={0}
              step="0.5"
              className="bg-surface border-border w-20 rounded-md border px-2 py-1 text-xs"
              placeholder={t('settings.budgetPlaceholder')}
              defaultValue={task.monthly_cap_usd ?? ''}
              key={`${task.task}-${task.monthly_cap_usd ?? 'none'}`}
              onBlur={(event) => {
                const raw = event.target.value.trim()
                const cap = raw === '' ? null : Number(raw)
                budget.mutate({ task: task.task, cap })
              }}
              aria-label={t('settings.budgetLabel', { task: task.task })}
            />
            <select
              className="bg-surface border-border max-w-52 rounded-md border px-2 py-1.5 text-xs"
              value={task.model_id ?? ''}
              onChange={(event) => {
                const value = event.target.value
                setError(null)
                assign.mutate(
                  { task: task.task, modelId: value === '' ? null : Number(value) },
                  {
                    onError: (err: Error) =>
                      setError(`${task.task}: ${err.message}`),
                  }
                )
              }}
            >
              <option value="">
                {task.default_model_label !== null
                  ? t('settings.inheritDefault')
                  : t('settings.unassigned')}
              </option>
              {assignable(task.requires).map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label}
                </option>
              ))}
            </select>
          </div>
        )
      })}
    </div>
  )
}
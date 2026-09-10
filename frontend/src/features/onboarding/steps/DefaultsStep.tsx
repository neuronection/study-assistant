import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { assignTaskDefault, listModels, listProviders, listTaskDefaults } from '@/lib/api'

const CAP_ORDER = ['text', 'vision', 'embeddings', 'audio'] as const

export function DefaultsStep() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const defaults = useQuery({ queryKey: ['task-defaults'], queryFn: listTaskDefaults })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const providers = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const [error, setError] = useState<string | null>(null)

  const providersList = providers.data ?? []
  const allLocal =
    providersList.length > 0 && providersList.every((provider) => provider.is_local)

  const enabledModels = (models.data ?? []).filter(
    (model) => model.enabled && !model.missing
  )
  const defaultByCap = new Map(
    (defaults.data ?? []).map((entry) => [entry.requires, entry])
  )

  const assign = useMutation({
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
      await queryClient.invalidateQueries({ queryKey: ['task-defaults'] })
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
      await queryClient.invalidateQueries({ queryKey: ['onboarding-state'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">{t('onboarding.defaultsHint')}</p>
      {allLocal ? (
        <p className="border-success/30 bg-success/10 text-success rounded-md border px-3 py-2 text-xs">
          {t('settings.localOnlyHint')}
        </p>
      ) : null}
      {error ? <p className="text-danger text-xs">{error}</p> : null}
      {enabledModels.length === 0 ? (
        <p className="text-muted-foreground py-4 text-center text-sm">
          {t('onboarding.defaultsNone')}
        </p>
      ) : (
        <div className="border-border space-y-2 rounded-md border p-3">
          {CAP_ORDER.map((requires) => {
            const entry = defaultByCap.get(requires)
            const options = enabledModels.filter((model) => model.caps.includes(requires))
            return (
              <div key={requires} className="flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">
                    {t('settings.defaultModelLabel', {
                      cap: t(`settings.caps.${requires}`),
                    })}
                  </p>
                </div>
                <select
                  className="bg-surface border-border max-w-52 rounded-md border px-2 py-1.5 text-xs"
                  value={entry?.model_id ?? ''}
                  onChange={(event) => {
                    const value = event.target.value
                    setError(null)
                    assign.mutate(
                      {
                        requires,
                        modelId: value === '' ? null : Number(value),
                        fallbackModelId: entry?.fallback_model_id ?? null,
                      },
                      { onError: (err: Error) => setError(err.message) }
                    )
                  }}
                  aria-label={t('settings.defaultModelLabel', {
                    cap: t(`settings.caps.${requires}`),
                  })}
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
      )}
    </div>
  )
}

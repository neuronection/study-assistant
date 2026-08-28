import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { listModels, updateModel } from '@/lib/api'

import { cn } from '@/lib/utils'

export function ModelsStep() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const [error, setError] = useState<string | null>(null)

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      updateModel(id, { enabled }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['models'] })
      await queryClient.invalidateQueries({ queryKey: ['onboarding-state'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const list = models.data ?? []
  const disabledModels = list.filter((model) => !model.enabled)
  const enabledCount = list.length - disabledModels.length

  const enableAll = () => {
    for (const model of disabledModels) {
      toggle.mutate({ id: model.id, enabled: true })
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-muted-foreground text-sm">{t('onboarding.modelsHint')}</p>
        {disabledModels.length > 0 ? (
          <Button variant="outline" size="sm" onClick={enableAll}>
            {t('onboarding.enableAll')}
          </Button>
        ) : null}
      </div>
      {error ? <p className="text-danger text-xs">{error}</p> : null}
      {list.length === 0 ? (
        <p className="text-muted-foreground py-4 text-center text-sm">
          {t('onboarding.modelsNone')}
        </p>
      ) : (
        <ul className="border-border divide-border divide-y rounded-md border">
          {list.map((model) => (
            <li key={model.id}>
              <label className="hover:bg-subtle flex cursor-pointer items-center gap-3 px-3 py-2">
                <input
                  type="checkbox"
                  checked={model.enabled}
                  onChange={(event) =>
                    toggle.mutate({ id: model.id, enabled: event.target.checked })
                  }
                />
                <span className="min-w-0 flex-1 truncate text-sm">{model.label}</span>
                <span className="flex shrink-0 gap-1">
                  {model.caps.map((cap) => (
                    <span
                      key={cap}
                      className={cn(
                        'rounded-full px-2 py-0.5 text-[10px]',
                        model.enabled
                          ? 'bg-primary/10 text-primary'
                          : 'bg-subtle text-muted-foreground'
                      )}
                    >
                      {cap}
                    </span>
                  ))}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
      {list.length > 0 ? (
        <p className="text-muted-foreground text-xs">
          {t('onboarding.enabledCount', { count: enabledCount })}
        </p>
      ) : null}
    </div>
  )
}

import { useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { ProviderCreateFields } from '@/features/settings/ProviderCreateFields'
import { useProviderCreate } from '@/features/settings/useProviderCreate'

export function ProviderStep({
  hasProvider,
  onDone,
}: {
  hasProvider: boolean
  onDone: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const state = useProviderCreate({
    onCreated: () => {
      void queryClient.invalidateQueries({ queryKey: ['onboarding-state'] })
      onDone()
    },
  })
  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">{t('onboarding.providerHint')}</p>
      {hasProvider ? (
        <p className="border-border bg-subtle rounded-md border px-3 py-2 text-xs">
          {t('onboarding.providerAlready')}
        </p>
      ) : null}
      <ProviderCreateFields state={state} />
      <div className="flex justify-end">
        <Button size="sm" disabled={!state.canSave || state.submitting} onClick={state.submit}>
          {state.submitting ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : (
            <Plus aria-hidden />
          )}
          {t('onboarding.providerCreate')}
        </Button>
      </div>
    </div>
  )
}

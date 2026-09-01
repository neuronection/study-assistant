import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { House, Pencil, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { ConnectionTestRow } from '@/components/ui/connection-test-row'
import { deleteProvider, listProviders, testProvider, type Provider } from '@/lib/api'
import { getCountryFlag } from '@/lib/countries'
import { useWizardStore } from '@/features/onboarding/wizardStore'

import { LocalEngines } from './LocalEngines'
import { useConfirm } from '@/lib/use-confirm'
import { ProviderFormDialog } from './ProviderFormDialog'

export function ProvidersTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const openWizard = useWizardStore((state) => state.openWizard)
  const providers = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const [form, setForm] = useState<{ provider: Provider | null } | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [confirm, confirmElement] = useConfirm()

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['providers'] })

  const test = useMutation({
    mutationFn: (id: number) => testProvider(id),
    onMutate: (id) => setBusyId(id),
    onSettled: () => {
      setBusyId(null)
      void refresh()
    },
  })
  const remove = useMutation({
    mutationFn: (id: number) => deleteProvider(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
      await queryClient.invalidateQueries({ queryKey: ['models'] })
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground text-sm">{t('settings.providersHint')}</p>
        <Button size="sm" onClick={() => setForm({ provider: null })}>
          <Plus aria-hidden />
          {t('settings.addProvider')}
        </Button>
      </div>
      {(providers.data ?? []).map((provider) => (
        <Card key={provider.id}>
          <CardContent className="flex items-center gap-3 p-4">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {provider.name} <span className="text-muted-foreground">· {provider.type}</span>
                {provider.is_local ? (
                  <span className="bg-primary/10 text-primary ml-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]">
                    <House className="size-3" aria-hidden />
                    {t('settings.localKind')}
                  </span>
                ) : provider.country ? (
                  <span className="ml-2 text-xs">{getCountryFlag(provider.country)}</span>
                ) : null}
                {!provider.enabled ? (
                  <span className="text-muted-foreground ml-2 text-xs">
                    {t('settings.disabled')}
                  </span>
                ) : null}
              </p>
              <p className="text-muted-foreground truncate font-mono text-xs">
                {provider.base_url} · {provider.masked_key ?? t('settings.noKey')}
              </p>
              <ConnectionTestRow
                variant="inline"
                className="mt-1"
                label={t('settings.connection')}
                status={
                  busyId === provider.id
                    ? 'testing'
                    : provider.status
                      ? provider.status.ok
                        ? 'ok'
                        : 'fail'
                      : 'idle'
                }
                errorMessage={provider.status?.error ?? null}
                meta={
                  provider.status?.model_count !== null &&
                  provider.status?.model_count !== undefined
                    ? `${provider.status.model_count} ${t('settings.modelsCount')}`
                    : undefined
                }
                testLabel={t('settings.test')}
                okLabel={t('settings.testOk')}
                failLabel={t('settings.testFail')}
                onTest={() => test.mutate(provider.id)}
                disabled={busyId === provider.id}
              />
            </div>
            <Button
              variant="ghost"
              size="icon"
              title={t('settings.editProvider')}
              onClick={() => setForm({ provider })}
            >
              <Pencil className="size-4" aria-hidden />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              title={t('settings.deleteProvider')}
              onClick={async () => {
                const ok = await confirm({
                  title: t('settings.deleteProvider'),
                  description: t('settings.confirmDeleteProvider'),
                  confirmLabel: t('settings.deleteProvider'),
                  cancelLabel: t('common.cancel'),
                  destructive: true,
                })
                if (ok) remove.mutate(provider.id)
              }}
            >
              <Trash2 className="size-4" aria-hidden />
            </Button>
          </CardContent>
        </Card>
      ))}
      {providers.data && providers.data.length === 0 ? (
        <div className="space-y-2 py-8 text-center">
          <p className="text-muted-foreground text-sm">{t('settings.noProviders')}</p>
          <div className="flex justify-center gap-2">
            <Button variant="outline" size="sm" onClick={() => openWizard()}>
              <Sparkles aria-hidden />
              {t('onboarding.runWizard')}
            </Button>
          </div>
          <div className="mx-auto max-w-sm pt-2 text-left">
            <LocalEngines />
          </div>
        </div>
      ) : null}
      {form ? (
        <ProviderFormDialog provider={form.provider} onClose={() => setForm(null)} />
      ) : null}
      {confirmElement}
    </div>
  )
}


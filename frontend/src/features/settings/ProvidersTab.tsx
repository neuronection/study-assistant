import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, PlugZap, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import type { ConnectionTestStatus } from '@/components/ui/connection-test-row'
import { ProviderCard } from '@/components/ui/provider-card'
import {
  deleteProvider,
  listModels,
  listProviders,
  testProvider,
  type Provider,
} from '@/lib/api'
import { getCountryFlag } from '@neuronection/assistant-ui/countries'
import { useWizardStore } from '@/features/onboarding/wizardStore'

import { LocalEngines } from './LocalEngines'
import { ProviderSetupModal } from './ProviderSetupModal'
import { ReRunSetupDialog } from './ReRunSetupDialog'
import { useConfirm } from '@/lib/use-confirm'
import { ProviderFormDialog } from './ProviderFormDialog'

export function ProvidersTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const openWizard = useWizardStore((state) => state.openWizard)
  const providers = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const [form, setForm] = useState<{ provider: Provider } | null>(null)
  const [setupOpen, setSetupOpen] = useState(false)
  const [reSetupProvider, setReSetupProvider] = useState<Provider | null>(null)
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

  const hasRegisteredModel = (providerId: number) =>
    (models.data ?? []).some((model) => model.provider_id === providerId)

  // Live count from the models query — `status.model_count` is only a
  // snapshot written by catalog-fetching flows, so manually added models
  // (or hand-edited catalogs) never showed on the card.
  const modelCount = (providerId: number) =>
    (models.data ?? []).filter((model) => model.provider_id === providerId).length

  const runDelete = async (provider: Provider) => {
    const ok = await confirm({
      title: t('settings.deleteProvider'),
      description: t('settings.confirmDeleteProvider'),
      confirmLabel: t('settings.deleteProvider'),
      cancelLabel: t('common.cancel'),
      destructive: true,
    })
    if (ok) remove.mutate(provider.id)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground text-sm">{t('settings.providersHint')}</p>
        <Button size="sm" onClick={() => setSetupOpen(true)}>
          <Plus aria-hidden />
          {t('settings.addProvider')}
        </Button>
      </div>
      {(providers.data ?? []).map((provider) => {
        const testing = busyId === provider.id
        const status: ConnectionTestStatus = testing
          ? 'testing'
          : provider.status
            ? provider.status.ok
              ? 'ok'
              : 'fail'
            : 'idle'
        const actions = [
          ...(provider.preset_key
            ? [
                {
                  key: 'setup',
                  label: t('settings.setup.automatically'),
                  icon: Sparkles,
                  onSelect: () => setReSetupProvider(provider),
                },
              ]
            : []),
          {
            key: 'edit',
            label: t('settings.edit'),
            icon: Pencil,
            onSelect: () => setForm({ provider }),
          },
          ...(hasRegisteredModel(provider.id)
            ? [
                {
                  key: 'test',
                  label: t('settings.test'),
                  icon: PlugZap,
                  disabled: testing,
                  pending: testing,
                  onSelect: () => test.mutate(provider.id),
                },
              ]
            : []),
          {
            key: 'delete',
            label: t('settings.deleteProvider'),
            icon: Trash2,
            danger: true,
            onSelect: () => void runDelete(provider),
          },
        ]
        return (
          <ProviderCard
            key={provider.id}
            name={provider.name}
            logoPreset={provider.preset_key ?? undefined}
            nameTitle={provider.base_url}
            subtitle={provider.base_url}
            status={status}
            idleLabel={t('settings.notTested')}
            okLabel={t('settings.testOk')}
            failLabel={t('settings.testFail')}
            errorMessage={provider.status?.error ?? null}
            meta={`${modelCount(provider.id)} ${t('settings.modelsCount')}`}
            badges={[
              { key: 'type', label: provider.type },
              ...(provider.is_local != null
                ? [
                    {
                      key: 'hosting',
                      label: provider.is_local
                        ? t('settings.localKind')
                        : t('settings.cloudKind'),
                      testId: `provider-hosting-${provider.id}`,
                    },
                  ]
                : []),
              ...(provider.country
                ? [
                    {
                      key: 'country',
                      label: `${getCountryFlag(provider.country)} ${provider.country}`,
                      title: provider.country,
                      testId: `provider-country-${provider.id}`,
                    },
                  ]
                : []),
              ...(!provider.masked_key
                ? [
                    {
                      key: 'key',
                      label: t('settings.noKey'),
                      danger: true,
                      testId: `provider-key-${provider.id}`,
                    },
                  ]
                : []),
              ...(!provider.enabled
                ? [
                    {
                      key: 'inactive',
                      label: t('settings.disabled'),
                      danger: true,
                    },
                  ]
                : []),
            ]}
            actions={actions}
            actionsLabel={t('settings.actionsAria', { name: provider.name })}
          />
        )
      })}
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
      {setupOpen ? <ProviderSetupModal onClose={() => setSetupOpen(false)} /> : null}
      {reSetupProvider ? (
        <ReRunSetupDialog provider={reSetupProvider} onClose={() => setReSetupProvider(null)} />
      ) : null}
      {form ? (
        <ProviderFormDialog provider={form.provider} onClose={() => setForm(null)} />
      ) : null}
      {confirmElement}
    </div>
  )
}

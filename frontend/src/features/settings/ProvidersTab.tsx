import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Pencil, Plus, Trash2, Zap } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { deleteProvider, listProviders, testProvider, type Provider } from '@/lib/api'

import { cn } from '@/lib/utils'
import { ProviderFormDialog } from './ProviderFormDialog'

export function ProvidersTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const providers = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const [form, setForm] = useState<{ provider: Provider | null } | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)

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
            <span
              className={cn(
                'inline-block size-2.5 shrink-0 rounded-full',
                provider.status?.ok ? 'bg-success' : provider.status ? 'bg-danger' : 'bg-warning'
              )}
              title={provider.status?.error ?? provider.status?.ok ? undefined : t('settings.notTested')}
            />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {provider.name} <span className="text-muted-foreground">· {provider.type}</span>
                {!provider.enabled ? (
                  <span className="text-muted-foreground ml-2 text-xs">
                    {t('settings.disabled')}
                  </span>
                ) : null}
              </p>
              <p className="text-muted-foreground truncate font-mono text-xs">
                {provider.base_url} · {provider.masked_key ?? t('settings.noKey')}
                {provider.status?.model_count !== null && provider.status?.model_count !== undefined
                  ? ` · ${provider.status.model_count} ${t('settings.modelsCount')}`
                  : ''}
              </p>
              {provider.status?.error ? (
                <p className="text-danger truncate text-xs">{provider.status.error}</p>
              ) : null}
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={busyId === provider.id}
              onClick={() => test.mutate(provider.id)}
            >
              {busyId === provider.id ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Zap aria-hidden />
              )}
              {t('settings.test')}
            </Button>
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
              onClick={() => {
                if (window.confirm(t('settings.confirmDeleteProvider'))) {
                  remove.mutate(provider.id)
                }
              }}
            >
              <Trash2 className="size-4" aria-hidden />
            </Button>
          </CardContent>
        </Card>
      ))}
      {providers.data && providers.data.length === 0 ? (
        <p className="text-muted-foreground py-8 text-center text-sm">
          {t('settings.noProviders')}
        </p>
      ) : null}
      {form ? (
        <ProviderFormDialog provider={form.provider} onClose={() => setForm(null)} />
      ) : null}
    </div>
  )
}

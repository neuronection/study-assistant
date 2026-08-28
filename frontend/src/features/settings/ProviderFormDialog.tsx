import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Save } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { updateProvider, type Provider } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

import { ProviderCreateFields } from './ProviderCreateFields'
import { useProviderCreate } from './useProviderCreate'

function ProviderCreateForm({
  onSaved,
  onClose,
}: {
  onSaved?: () => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const state = useProviderCreate({
    onCreated: () => {
      onSaved?.()
      onClose()
    },
  })
  return (
    <CardContent className="space-y-3">
      <ProviderCreateFields state={state} />
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>
          {t('settings.cancel')}
        </Button>
        <Button
          size="sm"
          disabled={!state.canSave || state.submitting}
          onClick={state.submit}
        >
          {state.submitting ? <Loader2 className="animate-spin" aria-hidden /> : <Plus aria-hidden />}
          {t('settings.add')}
        </Button>
      </div>
    </CardContent>
  )
}

function ProviderEditForm({
  provider,
  onSaved,
  onClose,
}: {
  provider: Provider
  onSaved?: () => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [name, setName] = useState(provider.name)
  const [baseUrl, setBaseUrl] = useState(provider.base_url ?? '')
  const [apiKey, setApiKey] = useState('')
  const [enabled, setEnabled] = useState(provider.enabled)
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: () => {
      const trimmedKey = apiKey.trim()
      return updateProvider(provider.id, {
        name: name.trim(),
        base_url: provider.type === 'openai_compatible' ? baseUrl.trim() || null : undefined,
        enabled,
        ...(trimmedKey ? { api_key: trimmedKey } : {}),
      })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
      await queryClient.invalidateQueries({ queryKey: ['models'] })
      onSaved?.()
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  return (
    <CardContent className="space-y-3">
      <div className="space-y-1 text-sm">
        <span className="text-muted-foreground">{t('settings.providerType')}</span>
        <p className="bg-subtle text-muted-foreground rounded-md px-3 py-2 text-xs">
          {t(`settings.types.${provider.type}`)}
        </p>
      </div>
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">{t('settings.providerName')}</span>
        <input
          className="bg-surface border-border w-full rounded-md border px-3 py-2"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      {provider.type === 'openai_compatible' ? (
        <label className="block space-y-1 text-sm">
          <span className="text-muted-foreground">{t('settings.baseUrl')}</span>
          <input
            className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono text-xs"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
          />
        </label>
      ) : null}
      <label className="block space-y-1 text-sm">
        <span className="text-muted-foreground">{t('settings.apiKey')}</span>
        <input
          type="password"
          className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono text-xs"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder={provider.masked_key ?? t('settings.apiKeyOptional')}
        />
        {provider.masked_key ? (
          <span className="text-muted-foreground text-[11px]">{t('settings.apiKeyKeepHint')}</span>
        ) : null}
      </label>
      <label className="flex cursor-pointer items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => setEnabled(event.target.checked)}
        />
        {t('settings.providerEnabled')}
      </label>
      {error ? <p className="text-danger text-xs">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onClose}>
          {t('settings.cancel')}
        </Button>
        <Button
          size="sm"
          disabled={name.trim().length === 0 || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Save aria-hidden />}
          {t('settings.save')}
        </Button>
      </div>
    </CardContent>
  )
}

export function ProviderFormDialog({
  provider,
  onSaved,
  onClose,
}: {
  provider: Provider | null
  onSaved?: () => void
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const editing = provider !== null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="max-h-[90vh] w-full max-w-md overflow-y-auto">
        <CardHeader>
          <CardTitle className="text-base">
            {editing ? t('settings.editProvider') : t('settings.addProvider')}
          </CardTitle>
          <CardDescription>
            {editing ? t('settings.editProviderHint') : t('settings.addProviderHint')}
          </CardDescription>
        </CardHeader>
        {editing ? (
          <ProviderEditForm provider={provider} onSaved={onSaved} onClose={onClose} />
        ) : (
          <ProviderCreateForm onSaved={onSaved} onClose={onClose} />
        )}
      </Card>
    </div>
  )
}

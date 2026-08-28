import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Save } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { createProvider, listPresets, updateProvider, type Provider } from '@/lib/api'
import { useCloseFloatings } from '@/lib/ui-overlays'

const CUSTOM = 'custom'
const PRESET_ORDER = ['google', 'openai', 'anthropic', 'ollama'] as const
const PRESET_TYPES: Record<string, string> = {
  google: 'google',
  anthropic: 'anthropic',
  openai: 'openai_compatible',
  ollama: 'openai_compatible',
  [CUSTOM]: 'openai_compatible',
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
  const queryClient = useQueryClient()
  const editing = provider !== null
  const presets = useQuery({
    queryKey: ['presets'],
    queryFn: listPresets,
    enabled: !editing,
  })
  const [presetKey, setPresetKey] = useState<string>('google')
  const [name, setName] = useState(provider?.name ?? '')
  const [nameDirty, setNameDirty] = useState(provider !== null)
  const [type] = useState(provider?.type ?? 'google')
  const [baseUrl, setBaseUrl] = useState(
    provider?.type === 'openai_compatible' ? (provider.base_url ?? '') : ''
  )
  const [apiKey, setApiKey] = useState('')
  const [enabled, setEnabled] = useState(provider?.enabled ?? true)
  const [error, setError] = useState<string | null>(null)

  const presetNames = Object.values(presets.data ?? {}).map((preset) => preset.name)
  const selectedType = editing ? type : (PRESET_TYPES[presetKey] ?? 'openai_compatible')

  const applyPreset = (key: string) => {
    setPresetKey(key)
    const preset = presets.data?.[key]
    if (preset && (!nameDirty || presetNames.includes(name))) {
      setName(preset.name)
    }
    setBaseUrl(key === 'openai' || key === 'ollama' ? (preset?.base_url ?? '') : '')
  }

  const save = useMutation({
    mutationFn: () => {
      const trimmedKey = apiKey.trim()
      if (editing) {
        return updateProvider(provider.id, {
          name: name.trim(),
          base_url:
            type === 'openai_compatible' ? baseUrl.trim() || null : undefined,
          enabled,
          ...(trimmedKey ? { api_key: trimmedKey } : {}),
        })
      }
      return createProvider({
        name,
        type: selectedType,
        base_url:
          selectedType === 'openai_compatible' ? baseUrl.trim() || null : null,
        api_key: apiKey || null,
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

  const canSave = editing
    ? name.trim().length > 0
    : name.trim().length > 0 && !(presetKey === CUSTOM && !baseUrl.trim())

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
        <CardContent className="space-y-3">
          {editing ? (
            <div className="space-y-1 text-sm">
              <span className="text-muted-foreground">{t('settings.providerType')}</span>
              <p className="bg-subtle text-muted-foreground rounded-md px-3 py-2 text-xs">
                {t(`settings.types.${type}`)}
              </p>
            </div>
          ) : (
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">{t('settings.providerPreset')}</span>
              <select
                className="bg-surface border-border w-full rounded-md border px-3 py-2"
                value={presetKey}
                onChange={(event) => applyPreset(event.target.value)}
              >
                {PRESET_ORDER.map((key) => (
                  <option key={key} value={key}>
                    {presets.data?.[key]?.name ?? key}
                  </option>
                ))}
                <option value={CUSTOM}>{t('settings.presetCustom')}</option>
              </select>
            </label>
          )}
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">{t('settings.providerName')}</span>
            <input
              className="bg-surface border-border w-full rounded-md border px-3 py-2"
              value={name}
              onChange={(event) => {
                setName(event.target.value)
                setNameDirty(true)
              }}
            />
          </label>
          {selectedType === 'openai_compatible' ? (
            <label className="block space-y-1 text-sm">
              <span className="text-muted-foreground">{t('settings.baseUrl')}</span>
              <input
                className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono text-xs"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
                placeholder={
                  presetKey === CUSTOM ? 'http://localhost:11434/v1' : undefined
                }
              />
              {presetKey === CUSTOM && !baseUrl.trim() ? (
                <span className="text-warning text-[11px]">
                  {t('settings.baseUrlRequired')}
                </span>
              ) : null}
            </label>
          ) : null}
          <label className="block space-y-1 text-sm">
            <span className="text-muted-foreground">{t('settings.apiKey')}</span>
            <input
              type="password"
              className="bg-surface border-border w-full rounded-md border px-3 py-2 font-mono text-xs"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={
                editing
                  ? provider.masked_key ?? t('settings.apiKeyOptional')
                  : t('settings.apiKeyOptional')
              }
            />
            {editing && provider.masked_key ? (
              <span className="text-muted-foreground text-[11px]">
                {t('settings.apiKeyKeepHint')}
              </span>
            ) : null}
          </label>
          {editing ? (
            <label className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />
              {t('settings.providerEnabled')}
            </label>
          ) : null}
          {error ? <p className="text-danger text-xs">{error}</p> : null}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              {t('settings.cancel')}
            </Button>
            <Button size="sm" disabled={!canSave || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : editing ? (
                <Save aria-hidden />
              ) : (
                <Plus aria-hidden />
              )}
              {editing ? t('settings.save') : t('settings.add')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Globe } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  clearSearchProvider,
  getSearchProvider,
  updateSearchProvider,
} from '@/lib/api'

export function SearchProviderCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const provider = useQuery({ queryKey: ['search-provider'], queryFn: getSearchProvider })
  const [baseUrl, setBaseUrl] = useState('')
  const [flavor, setFlavor] = useState('tavily')
  const [apiKey, setApiKey] = useState('')
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    if (provider.data?.assigned) {
      setBaseUrl(provider.data.base_url ?? '')
      setFlavor(provider.data.flavor ?? 'tavily')
    }
  }, [provider.data])

  const save = useMutation({
    mutationFn: () =>
      updateSearchProvider({
        base_url: baseUrl.trim(),
        flavor,
        api_key: apiKey.trim() === '' ? null : apiKey.trim(),
      }),
    onSuccess: async () => {
      setApiKey('')
      setNotice(null)
      await queryClient.invalidateQueries({ queryKey: ['search-provider'] })
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const remove = useMutation({
    mutationFn: () => clearSearchProvider(),
    onSuccess: async () => {
      setBaseUrl('')
      setFlavor('tavily')
      setApiKey('')
      setNotice(null)
      await queryClient.invalidateQueries({ queryKey: ['search-provider'] })
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const assigned = provider.data?.assigned ?? false
  const keySet = provider.data?.key_set ?? false

  return (
    <Card>
      <CardHeader className="pb-0">
        <CardTitle className="flex items-center gap-2 text-base">
          <Globe className="size-4" aria-hidden />
          {t('settings.searchProviderTitle')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 p-4">
        <p className="text-muted-foreground text-xs">{t('settings.searchProviderHint')}</p>
        <div className="flex flex-wrap gap-2">
          <input
            className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1.5 text-sm"
            placeholder={t('settings.searchProviderUrl')}
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
          />
          <select
            className="bg-surface border-border rounded-md border px-2 py-1.5 text-sm"
            value={flavor}
            onChange={(event) => setFlavor(event.target.value)}
            aria-label={t('settings.searchProviderFlavor')}
          >
            <option value="tavily">{t('settings.searchProviderFlavorTavily')}</option>
            <option value="searxng">{t('settings.searchProviderFlavorSearxng')}</option>
          </select>
          <input
            type="password"
            className="bg-surface border-border w-48 rounded-md border px-2 py-1.5 text-sm"
            placeholder={
              keySet ? t('settings.searchProviderKeySet') : t('settings.searchProviderKey')
            }
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
          />
        </div>
        {notice !== null ? (
          <p className="text-destructive text-xs" role="alert">
            {notice}
          </p>
        ) : null}
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            disabled={!baseUrl.trim() || save.isPending}
            onClick={() => save.mutate()}
          >
            {t('settings.searchProviderSave')}
          </Button>
          {assigned ? (
            <Button
              variant="outline"
              size="sm"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              {t('settings.searchProviderRemove')}
            </Button>
          ) : null}
          {assigned ? (
            <span className="text-success text-xs">{t('settings.searchProviderActive')}</span>
          ) : (
            <span className="text-muted-foreground text-xs">
              {t('settings.searchProviderInactive')}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

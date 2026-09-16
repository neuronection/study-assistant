import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  getProfilePreferences,
  getSearchProvider,
  updateProfilePreferences,
  type DiscoverySitePreset,
} from '@/lib/api'

const DISCOVERY_KINDS = ['video', 'course', 'article', 'exercise', 'other'] as const

type EditableSite = DiscoverySitePreset & { enabled: boolean }

export function DiscoveryCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const preferences = useQuery({
    queryKey: ['profile-preferences'],
    queryFn: getProfilePreferences,
  })
  const searchProvider = useQuery({ queryKey: ['search-provider'], queryFn: getSearchProvider })

  const [webEnabled, setWebEnabled] = useState(true)
  const [youtubeEnabled, setYoutubeEnabled] = useState(true)
  const [sites, setSites] = useState<EditableSite[]>([])
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    const discovery = preferences.data?.discovery
    if (!discovery) return
    setWebEnabled(discovery.enabled.includes('web'))
    setYoutubeEnabled(discovery.enabled.includes('youtube'))
    setSites(
      (discovery.sites ?? []).map((entry) => ({
        ...entry,
        enabled: discovery.enabled.includes(`site:${entry.site}`),
      })),
    )
  }, [preferences.data])

  const save = useMutation({
    mutationFn: () =>
      updateProfilePreferences({
        discovery: {
          enabled: [
            ...(webEnabled ? ['web'] : []),
            ...(youtubeEnabled ? ['youtube'] : []),
            ...sites
              .filter((entry) => entry.enabled && entry.site.trim() !== '')
              .map((entry) => `site:${entry.site.trim()}`),
          ],
          sites: sites
            .filter((entry) => entry.site.trim() !== '')
            .map((entry) => ({
              site: entry.site.trim(),
              label: entry.label?.trim() ? entry.label.trim() : null,
              kind: entry.kind,
            })),
        },
      }),
    onSuccess: async (data) => {
      setNotice(null)
      queryClient.setQueryData(['profile-preferences'], data)
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const searchAssigned = searchProvider.data?.assigned ?? false
  const sitePresetsActive = searchAssigned

  const updateSite = (index: number, patch: Partial<EditableSite>) => {
    setSites((current) =>
      current.map((entry, position) => (position === index ? { ...entry, ...patch } : entry)),
    )
  }

  return (
    <Card data-testid="discovery-card">
      <CardHeader>
        <CardTitle className="text-sm">{t('settings.discoveryTitle')}</CardTitle>
        <CardDescription>{t('settings.discoveryDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={webEnabled && searchAssigned}
            disabled={!searchAssigned || preferences.isLoading || save.isPending}
            onChange={(event) => setWebEnabled(event.target.checked)}
          />
          {t('settings.discoveryWeb')}
          {!searchAssigned ? (
            <span className="text-muted-foreground text-[11px]">
              {t('settings.discoveryWebNeedsProvider')}
            </span>
          ) : null}
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={youtubeEnabled}
            disabled={preferences.isLoading || save.isPending}
            onChange={(event) => setYoutubeEnabled(event.target.checked)}
          />
          {t('settings.discoveryYoutube')}
        </label>
        <div className="space-y-1" data-testid="discovery-sites">
          <p className="text-muted-foreground text-xs">
            {sitePresetsActive
              ? t('settings.discoverySitesHint')
              : t('settings.discoverySitesNeedProvider')}
          </p>
          {sites.map((entry, index) => (
            <div key={index} className="flex flex-wrap items-center gap-2">
              <input
                type="checkbox"
                checked={entry.enabled}
                aria-label={t('settings.discoverySiteEnabled')}
                disabled={!sitePresetsActive}
                onChange={(event) => updateSite(index, { enabled: event.target.checked })}
              />
              <input
                className="bg-surface border-border w-40 rounded-md border px-2 py-1 text-xs"
                placeholder={t('settings.discoverySiteDomain')}
                value={entry.site}
                disabled={!sitePresetsActive}
                onChange={(event) => updateSite(index, { site: event.target.value })}
              />
              <input
                className="bg-surface border-border w-40 rounded-md border px-2 py-1 text-xs"
                placeholder={t('settings.discoverySiteLabel')}
                value={entry.label ?? ''}
                disabled={!sitePresetsActive}
                onChange={(event) => updateSite(index, { label: event.target.value })}
              />
              <select
                className="bg-surface border-border rounded-md border px-2 py-1 text-xs"
                value={entry.kind}
                disabled={!sitePresetsActive}
                onChange={(event) => updateSite(index, { kind: event.target.value })}
                aria-label={t('settings.discoverySiteKind')}
              >
                {DISCOVERY_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {t(`discovery.kind.${kind}`)}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground"
                aria-label={t('settings.discoverySiteRemove')}
                disabled={!sitePresetsActive}
                onClick={() => setSites((current) => current.filter((_, position) => position !== index))}
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </div>
          ))}
          <Button
            size="sm"
            variant="ghost"
            disabled={!sitePresetsActive}
            onClick={() =>
              setSites((current) => [
                ...current,
                { site: '', label: null, kind: 'course', enabled: true },
              ])
            }
          >
            <Plus aria-hidden />
            {t('settings.discoverySiteAdd')}
          </Button>
        </div>
        {notice !== null ? (
          <p className="text-destructive text-xs" role="alert">
            {notice}
          </p>
        ) : null}
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            disabled={preferences.isLoading || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t('settings.discoverySave')}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

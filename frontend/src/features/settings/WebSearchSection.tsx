import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronUp, Globe, Loader2, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  createSearchProvider,
  deleteSearchProvider,
  getSearchProviderCatalog,
  listSearchProviders,
  moveSearchProvider,
  testSearchProvider,
  updateSearchProvider,
  type SearchProvider,
} from '@/lib/api'
import { useConfirm } from '@/lib/use-confirm'

// Tools → web search (ADR-0033 domain tools.web-search): the family
// multi-provider shape (ADR-0035 / plan 28) — an ordered list; the first
// enabled provider that answers wins. The form renders from the vendored
// catalog (labels, base-URL rules, extra fields).
type Draft = {
  id: string | null
  type: string
  name: string
  base_url: string
  google_cx: string
  api_key: string
}

const PROBE_LABEL_KEYS: Record<string, string> = {
  ok: 'settings.webSearchProbeOk',
  unreachable: 'settings.webSearchProbeUnreachable',
  auth: 'settings.webSearchProbeAuth',
  rate_limit: 'settings.webSearchProbeRateLimited',
  json_disabled: 'settings.webSearchProbeJsonDisabled',
  error: 'settings.webSearchProbeError',
}

export function WebSearchSection() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const providers = useQuery({
    queryKey: ['search-providers'],
    queryFn: listSearchProviders,
  })
  const catalog = useQuery({
    queryKey: ['search-provider-catalog'],
    queryFn: getSearchProviderCatalog,
  })
  const [draft, setDraft] = useState<Draft | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [probe, setProbe] = useState<Record<string, { status: string; error: string | null; latency_ms: number }>>({})
  const [testing, setTesting] = useState<string | null>(null)
  const [confirm, confirmElement] = useConfirm()

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['search-providers'] })
  }

  const save = useMutation({
    mutationFn: (form: Draft) => {
      const body = {
        type: form.type,
        name: form.name.trim() || null,
        base_url: form.base_url.trim() || null,
        google_cx: form.google_cx.trim() || null,
        // empty input keeps the stored key (update) / stores none (create)
        api_key: form.api_key.trim() === '' ? null : form.api_key.trim(),
      }
      return form.id ? updateSearchProvider(form.id, body) : createSearchProvider(body)
    },
    onSuccess: async () => {
      setDraft(null)
      setNotice(null)
      await refresh()
    },
    onError: (error: Error) => setNotice(error.message),
  })

  const toggle = useMutation({
    mutationFn: (provider: SearchProvider) =>
      updateSearchProvider(provider.id, { enabled: !provider.enabled }),
    onSuccess: () => void refresh(),
  })

  const move = useMutation({
    mutationFn: ({ id, direction }: { id: string; direction: 'up' | 'down' }) =>
      moveSearchProvider(id, direction),
    onSuccess: () => void refresh(),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteSearchProvider(id),
    onSuccess: () => void refresh(),
  })

  const runTest = async (provider: SearchProvider) => {
    setTesting(provider.id)
    try {
      const result = await testSearchProvider(provider.id)
      setProbe((current) => ({
        ...current,
        [provider.id]: {
          status: result.status,
          error: result.error,
          latency_ms: result.latency_ms,
        },
      }))
    } catch (error) {
      setProbe((current) => ({
        ...current,
        [provider.id]: { status: 'error', error: (error as Error).message, latency_ms: 0 },
      }))
    } finally {
      setTesting(null)
    }
  }

  const catalogEntry = (type: string) => catalog.data?.providers[type]

  const openAdd = () =>
    setDraft({
      id: null,
      type: catalog.data?.providerOrder[0] ?? 'searxng',
      name: '',
      base_url: '',
      google_cx: '',
      api_key: '',
    })

  const openEdit = (provider: SearchProvider) =>
    setDraft({
      id: provider.id,
      type: provider.type,
      name: provider.name,
      base_url: provider.base_url ?? '',
      google_cx: provider.google_cx ?? '',
      api_key: '',
    })

  const entry = draft ? catalogEntry(draft.type) : undefined
  const keyRequired = entry?.requiresKey ?? false
  const baseUrlRequired = entry?.baseUrlRequired ?? false

  return (
    <Card>
      <CardHeader className="pb-0">
        <CardTitle className="flex items-center gap-2 text-base">
          <Globe className="size-4" aria-hidden />
          {t('settings.webSearchProvidersTitle')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <p className="text-muted-foreground text-xs">{t('settings.webSearchHint')}</p>
          {draft === null ? (
            <Button size="sm" variant="outline" onClick={openAdd}>
              <Plus aria-hidden />
              {t('settings.webSearchAdd')}
            </Button>
          ) : null}
        </div>

        {(providers.data ?? []).map((provider, index) => {
          const result = probe[provider.id]
          const probeLabel =
            result &&
            (result.status === 'error' && result.error
              ? result.error
              : t(PROBE_LABEL_KEYS[result.status] ?? 'settings.webSearchProbeError'))
          return (
            <div
              key={provider.id}
              data-testid={`web-search-provider-${provider.type}`}
              className="border-border space-y-1 rounded-md border p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
                  <input
                    type="checkbox"
                    checked={provider.enabled}
                    aria-label={t('settings.webSearchEnabledAria', { name: provider.name })}
                    onChange={() => toggle.mutate(provider)}
                  />
                  {provider.name}
                </label>
                <span className="bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[11px]">
                  {catalogEntry(provider.type)?.label ?? provider.type}
                </span>
                {provider.base_url ? (
                  <span className="text-muted-foreground truncate font-mono text-xs">
                    {provider.base_url}
                  </span>
                ) : null}
                <span className="text-muted-foreground ml-auto text-xs">
                  {provider.key_set
                    ? provider.key_hint ?? t('settings.searchProviderKeySet')
                    : t('settings.webSearchNoKey')}
                </span>
              </div>
              {result ? (
                <p
                  className={`text-xs ${result.status === 'ok' ? 'text-success' : 'text-destructive'}`}
                  data-testid={`web-search-probe-${provider.id}`}
                >
                  {probeLabel}
                  {result.status === 'ok' ? ` · ${result.latency_ms} ms` : ''}
                </p>
              ) : null}
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={testing === provider.id}
                  onClick={() => void runTest(provider)}
                >
                  {testing === provider.id ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                  ) : null}
                  {t('settings.test')}
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  title={t('settings.webSearchMoveUp')}
                  disabled={index === 0 || move.isPending}
                  onClick={() => move.mutate({ id: provider.id, direction: 'up' })}
                >
                  <ChevronUp className="size-4" aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  title={t('settings.webSearchMoveDown')}
                  disabled={index === (providers.data?.length ?? 0) - 1 || move.isPending}
                  onClick={() => move.mutate({ id: provider.id, direction: 'down' })}
                >
                  <ChevronDown className="size-4" aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  title={t('settings.webSearchEdit')}
                  onClick={() => openEdit(provider)}
                >
                  <Pencil className="size-4" aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  title={t('settings.webSearchDelete')}
                  onClick={async () => {
                    const ok = await confirm({
                      title: t('settings.webSearchDelete'),
                      description: t('settings.webSearchConfirmDelete', {
                        name: provider.name,
                      }),
                      confirmLabel: t('settings.webSearchDelete'),
                      cancelLabel: t('common.cancel'),
                      destructive: true,
                    })
                    if (ok) remove.mutate(provider.id)
                  }}
                >
                  <Trash2 className="size-4" aria-hidden />
                </Button>
                {!provider.enabled ? (
                  <span className="text-muted-foreground text-xs">
                    {t('settings.webSearchDisabled')}
                  </span>
                ) : null}
              </div>
            </div>
          )
        })}

        {providers.data && providers.data.length === 0 && draft === null ? (
          <p className="text-muted-foreground py-4 text-center text-sm">
            {t('settings.webSearchEmpty')}
          </p>
        ) : null}

        {draft !== null ? (
          <form
            className="border-border space-y-2 rounded-md border p-3"
            data-testid="web-search-form"
            onSubmit={(event) => {
              event.preventDefault()
              save.mutate(draft)
            }}
          >
            <div className="flex flex-wrap gap-2">
              <select
                className="bg-surface border-border rounded-md border px-2 py-1.5 text-sm"
                value={draft.type}
                disabled={draft.id !== null}
                onChange={(event) => setDraft({ ...draft, type: event.target.value })}
                aria-label={t('settings.webSearchType')}
              >
                {(catalog.data?.providerOrder ?? []).map((type) => (
                  <option key={type} value={type}>
                    {catalogEntry(type)?.label ?? type}
                  </option>
                ))}
              </select>
              <input
                className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1.5 text-sm"
                placeholder={t('settings.webSearchName')}
                value={draft.name}
                onChange={(event) => setDraft({ ...draft, name: event.target.value })}
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <input
                className="bg-surface border-border min-w-0 flex-1 rounded-md border px-2 py-1.5 text-sm"
                placeholder={
                  baseUrlRequired
                    ? t('settings.webSearchBaseUrlRequired')
                    : (entry?.baseUrlHint ?? t('settings.webSearchBaseUrl'))
                }
                value={draft.base_url}
                onChange={(event) => setDraft({ ...draft, base_url: event.target.value })}
              />
              {entry?.fields?.some((field) => field.id === 'google_cx') ? (
                <input
                  className="bg-surface border-border w-48 rounded-md border px-2 py-1.5 text-sm"
                  placeholder={t('settings.webSearchEngineId')}
                  value={draft.google_cx}
                  onChange={(event) => setDraft({ ...draft, google_cx: event.target.value })}
                />
              ) : null}
              <input
                type="password"
                className="bg-surface border-border w-48 rounded-md border px-2 py-1.5 text-sm"
                placeholder={
                  draft.id
                    ? t('settings.searchProviderKeySet')
                    : keyRequired
                      ? t('settings.webSearchKey')
                      : t('settings.webSearchKeyOptional')
                }
                value={draft.api_key}
                onChange={(event) => setDraft({ ...draft, api_key: event.target.value })}
              />
            </div>
            {entry?.notes ? (
              <p className="text-muted-foreground text-[11px]">{entry.notes}</p>
            ) : null}
            {notice !== null ? (
              <p className="text-destructive text-xs" role="alert">
                {notice}
              </p>
            ) : null}
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                type="submit"
                disabled={
                  save.isPending ||
                  (baseUrlRequired && draft.base_url.trim() === '') ||
                  (draft.id === null && keyRequired && draft.api_key.trim() === '')
                }
              >
                {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
                {t('settings.webSearchSave')}
              </Button>
              <Button size="sm" variant="ghost" type="button" onClick={() => setDraft(null)}>
                {t('common.cancel')}
              </Button>
            </div>
          </form>
        ) : null}
      </CardContent>
      {confirmElement}
    </Card>
  )
}

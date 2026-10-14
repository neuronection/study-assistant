import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { WebSearchProvidersPanel } from '@neuronection/assistant-ui'
import type {
  WebSearchProviderProbeView,
  WebSearchProviderSaveInput,
} from '@neuronection/assistant-ui'
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
// multi-provider shape (ADR-0035 / plan 28) rendered by the library panel
// (plan 28 Phase 2). Study is the thin app shell: data + handlers here,
// presentation in @neuronection/assistant-ui.

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
  const [probes, setProbes] = useState<Record<string, WebSearchProviderProbeView>>({})
  const [testingId, setTestingId] = useState<string | null>(null)
  const [confirm, confirmElement] = useConfirm()

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['search-providers'] })
  }

  const save = useMutation({
    mutationFn: (input: WebSearchProviderSaveInput) => {
      const body = {
        type: input.type,
        name: input.name ?? null,
        base_url: input.baseUrl ?? null,
        google_cx: input.googleCx ?? null,
        api_key: input.apiKey ?? null,
      }
      return input.id ? updateSearchProvider(input.id, body) : createSearchProvider(body)
    },
    onSuccess: () => refresh(),
  })

  const toggle = useMutation({
    mutationFn: (provider: SearchProvider) =>
      updateSearchProvider(provider.id, { enabled: !provider.enabled }),
    onSuccess: () => refresh(),
  })

  const move = useMutation({
    mutationFn: ({ id, direction }: { id: string; direction: 'up' | 'down' }) =>
      moveSearchProvider(id, direction),
    onSuccess: () => refresh(),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteSearchProvider(id),
    onSuccess: () => refresh(),
  })

  const handleDelete = async (id: string) => {
    const provider = providers.data?.find((entry) => entry.id === id)
    const ok = await confirm({
      title: t('settings.webSearchDelete'),
      description: t('settings.webSearchConfirmDelete', {
        name: provider?.name ?? id,
      }),
      confirmLabel: t('settings.webSearchDelete'),
      cancelLabel: t('common.cancel'),
      destructive: true,
    })
    if (ok) remove.mutate(id)
  }

  const test = async (id: string) => {
    setTestingId(id)
    try {
      const result = await testSearchProvider(id)
      // The panel's probe view narrows the wire status to its closed set;
      // unknown statuses degrade to 'error' (fail-honest).
      const KNOWN = new Set([
        'ok',
        'unreachable',
        'auth',
        'rate_limit',
        'json_disabled',
        'error',
      ])
      const status = (KNOWN.has(result.status) ? result.status : 'error') as WebSearchProviderProbeView['status']
      setProbes((current) => ({
        ...current,
        [id]: { status, latencyMs: result.latency_ms, error: result.error },
      }))
    } finally {
      setTestingId(null)
    }
  }

  return (
    <>
      {save.error ? (
        <p className="text-destructive text-xs" role="alert">
          {String(save.error)}
        </p>
      ) : null}
      <WebSearchProvidersPanel
        providers={(providers.data ?? []).map((provider) => ({
          id: provider.id,
          name: provider.name,
          type: provider.type,
          enabled: provider.enabled,
          baseUrl: provider.base_url,
          googleCx: provider.google_cx,
          keyHint: provider.key_hint,
          keySet: provider.key_set,
        }))}
        catalog={{
          order: catalog.data?.providerOrder ?? [],
          entries: catalog.data?.providers ?? {},
        }}
        probes={probes}
        testingId={testingId}
        busy={save.isPending || toggle.isPending || move.isPending || remove.isPending}
        labels={{
          title: t('settings.webSearchProvidersTitle'),
          hint: t('settings.webSearchHint'),
          addLabel: t('settings.webSearchAdd'),
          emptyLabel: t('settings.webSearchEmpty'),
          nameLabel: t('settings.webSearchName'),
          typeLabel: t('settings.webSearchType'),
          baseUrlLabel: t('settings.webSearchBaseUrl'),
          baseUrlRequiredLabel: t('settings.webSearchBaseUrlRequired'),
          keyLabel: t('settings.webSearchKey'),
          keyOptionalLabel: t('settings.webSearchKeyOptional'),
          keyStoredLabel: t('settings.searchProviderKeySet'),
          noKeyLabel: t('settings.webSearchNoKey'),
          saveLabel: t('settings.webSearchSave'),
          cancelLabel: t('common.cancel'),
          editLabel: t('settings.webSearchEdit'),
          deleteLabel: t('settings.webSearchDelete'),
          moveUpLabel: t('settings.webSearchMoveUp'),
          moveDownLabel: t('settings.webSearchMoveDown'),
          enabledAriaLabel: t('settings.webSearchEnabledProviderAria'),
          disabledBadge: t('settings.webSearchDisabled'),
          testLabel: t('settings.test'),
          probeLabels: {
            ok: t('settings.webSearchProbeOk'),
            unreachable: t('settings.webSearchProbeUnreachable'),
            auth: t('settings.webSearchProbeAuth'),
            rate_limit: t('settings.webSearchProbeRateLimited'),
            json_disabled: t('settings.webSearchProbeJsonDisabled'),
            error: t('settings.webSearchProbeError'),
          },
        }}
        onSave={save.mutate}
        onDelete={(id) => void handleDelete(id)}
        onMove={(id, direction) => move.mutate({ id, direction })}
        onToggle={(id) => {
          const provider = providers.data?.find((entry) => entry.id === id)
          if (provider) toggle.mutate(provider)
        }}
        onTest={(id) => void test(id)}
      />
      {confirmElement}
    </>
  )
}

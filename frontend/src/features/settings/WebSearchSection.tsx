import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Modal, ModalContent } from '@/components/ui/modal'
import { ModalDescription, ModalHeader, ModalTitle } from '@neuronection/assistant-ui'
import {
  WebSearchProviderSettingsForm,
  WebSearchProvidersList,
  WebSearchProviderWizard,
  type WebSearchProviderCatalogField,
  type WebSearchProviderFormValue,
  type WebSearchProviderProbeView,
  type WebSearchProviderSaveInput,
  type WebSearchProviderView,
} from '@neuronection/assistant-ui/web-search-providers'
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
// multi-provider shape (ADR-0035 / plan 28) in the AI-providers pattern
// (library 0.74 web-search-providers): configured instances as
// ProviderCards with a `⋯` management menu, add = tiles → settings-form
// wizard in a modal, edit = the settings form in a modal. Study is the
// thin app shell: data + handlers here, presentation in
// @neuronection/assistant-ui.

interface EditState {
  provider: SearchProvider
  value: WebSearchProviderFormValue
}

type SearchProviderBody = Parameters<typeof createSearchProvider>[0]

const toFormValue = (provider: SearchProvider): WebSearchProviderFormValue => ({
  name: provider.name,
  apiKey: '',
  baseUrl: provider.base_url ?? '',
  fields: {
    google_cx: provider.google_cx ?? '',
    timeout_ms: String(provider.timeout_ms ?? ''),
    max_results: String(provider.max_results ?? ''),
  },
})

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
  const [adding, setAdding] = useState(false)
  const [wizardError, setWizardError] = useState<string | null>(null)
  const [editing, setEditing] = useState<EditState | null>(null)
  const [editError, setEditError] = useState<string | null>(null)
  const [confirm, confirmElement] = useConfirm()

  const catalogEntries = catalog.data?.providers ?? {}
  const limits = catalog.data?.limits

  // App-declared tuning fields from the catalog limits — rendered by the
  // library settings form's Advanced disclosure (timeout, result count).
  const extraFields: WebSearchProviderCatalogField[] = limits
    ? [
        {
          id: 'timeout_ms',
          label: t('settings.webSearchTimeout'),
          required: false,
          type: 'number',
          advanced: true,
          placeholder: String(limits.timeoutMs.default),
        },
        {
          id: 'max_results',
          label: t('settings.webSearchMaxResults'),
          required: false,
          type: 'number',
          advanced: true,
          placeholder: String(limits.maxResults.default),
        },
      ]
    : []

  // Connection name auto-seed: catalog label, numbered when already taken.
  const defaultName = (type: string): string | null => {
    const base = catalogEntries[type]?.label ?? type
    const taken = new Set((providers.data ?? []).map((entry) => entry.name))
    if (!taken.has(base)) return base
    let n = 2
    while (taken.has(`${base} ${n}`)) n += 1
    return `${base} ${n}`
  }

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['search-providers'] })
  }

  // Library save payload → API body. Endpoint overrides persist only when
  // they deviate from the catalog default ("" resets to it — the backend
  // normalize stores a total config, so a cleared tuning field maps to the
  // catalog default); `api_key: null` keeps the stored key.
  const toBody = (input: WebSearchProviderSaveInput): SearchProviderBody => {
    const entry = catalogEntries[input.type]
    const fields = input.fields ?? {}
    const numberField = (id: string) => {
      const raw = (fields[id] ?? '').trim()
      if (raw === '') return limits ? (id === 'timeout_ms' ? limits.timeoutMs.default : limits.maxResults.default) : null
      const parsed = Number(raw)
      return Number.isFinite(parsed) ? parsed : null
    }
    const baseUrl = input.baseUrl?.trim() ?? ''
    return {
      type: input.type,
      name: (input.name ?? '').trim() || entry?.label || input.type,
      base_url: baseUrl !== '' && baseUrl !== (entry?.baseUrl ?? null) ? baseUrl : '',
      google_cx: (input.googleCx ?? '').trim() || '',
      timeout_ms: numberField('timeout_ms'),
      max_results: numberField('max_results'),
      api_key: input.apiKey ?? null,
    }
  }

  const save = useMutation({
    mutationFn: ({ id, body }: { id?: string; body: SearchProviderBody }) =>
      id ? updateSearchProvider(id, body) : createSearchProvider(body),
    onSuccess: () => refresh(),
  })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateSearchProvider(id, { enabled }),
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

  const saveWizard = (input: WebSearchProviderSaveInput) => {
    save.mutate(
      { body: toBody(input) },
      {
        onSuccess: () => {
          setAdding(false)
          setWizardError(null)
        },
        onError: (error: Error) => setWizardError(error.message),
      },
    )
  }

  const openEdit = (view: WebSearchProviderView) => {
    const provider = (providers.data ?? []).find((entry) => entry.id === view.id)
    if (!provider) return
    setEditError(null)
    setEditing({ provider, value: toFormValue(provider) })
  }

  const saveEdit = (value: WebSearchProviderFormValue) => {
    if (!editing) return
    save.mutate(
      {
        id: editing.provider.id,
        body: toBody({
          id: editing.provider.id,
          type: editing.provider.type,
          name: value.name,
          baseUrl: value.baseUrl,
          googleCx: value.fields['google_cx'] ?? '',
          apiKey: value.apiKey.trim() === '' ? null : value.apiKey,
          fields: value.fields,
        }),
      },
      {
        onSuccess: () => {
          setEditing(null)
          setEditError(null)
        },
        onError: (error: Error) => setEditError(error.message),
      },
    )
  }

  const clearStoredKey = () => {
    if (!editing) return
    save.mutate(
      { id: editing.provider.id, body: { api_key: '' } },
      {
        onSuccess: () => {
          setEditing(null)
          setEditError(null)
        },
        onError: (error: Error) => setEditError(error.message),
      },
    )
  }

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
      // The list's probe view narrows the wire status to its closed set;
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

  const wizardLabels = {
    chooseStepLabel: t('settings.webSearchStepChoose'),
    configureStepLabel: t('settings.webSearchStepConfigure'),
    stepsLabel: t('settings.webSearchStepsAria'),
    tilesLabel: t('settings.webSearchTilesLabel'),
    backLabel: t('settings.webSearchBack'),
    keyChipLabel: t('settings.webSearchChipKey'),
    keylessChipLabel: t('settings.webSearchChipKeyless'),
    cloudChipLabel: t('settings.webSearchChipCloud'),
    selfHostedChipLabel: t('settings.webSearchChipSelfHosted'),
    nameLabel: t('settings.webSearchName'),
    apiKeyLabel: t('settings.webSearchKey'),
    keyOptionalLabel: t('settings.webSearchKeyOptional'),
    keyStoredLabel: t('settings.searchProviderKeySet'),
    noKeyLabel: t('settings.webSearchNoKeyNeeded'),
    baseUrlLabel: t('settings.webSearchBaseUrl'),
    baseUrlRequiredLabel: t('settings.webSearchBaseUrlRequired'),
    advancedLabel: t('settings.webSearchAdvanced'),
    getKeyLabel: t('settings.webSearchGetKey'),
    saveLabel: t('settings.webSearchSave'),
    cancelLabel: t('settings.cancel'),
  }

  const listLabels = {
    emptyLabel: t('settings.webSearchEmpty'),
    orderLabel: (position: number) => t('settings.webSearchPriority', { position }),
    disabledBadge: t('settings.webSearchDisabled'),
    noKeyLabel: t('settings.webSearchNoKey'),
    keyStoredLabel: t('settings.searchProviderKeySet'),
    enableLabel: t('settings.webSearchEnable'),
    disableLabel: t('settings.webSearchDisable'),
    moveUpLabel: t('settings.webSearchMoveUp'),
    moveDownLabel: t('settings.webSearchMoveDown'),
    editLabel: t('settings.webSearchEdit'),
    deleteLabel: t('settings.webSearchDelete'),
    testLabel: t('settings.test'),
    idleLabel: t('settings.notTested'),
    okLabel: t('settings.testOk'),
    failLabel: t('settings.testFail'),
    actionsLabel: (name: string) => t('settings.webSearchActionsAria', { name }),
  }

  return (
    <>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">{t('settings.webSearchProvidersTitle')}</p>
          <p className="text-muted-foreground mt-0.5 text-xs">{t('settings.webSearchHint')}</p>
        </div>
        {!adding && !editing ? (
          <Button
            variant="outline"
            size="sm"
            disabled={!catalog.data}
            onClick={() => {
              setWizardError(null)
              setAdding(true)
            }}
          >
            <Plus aria-hidden />
            {t('settings.webSearchAdd')}
          </Button>
        ) : null}
      </div>
      <WebSearchProvidersList
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
          entries: catalogEntries,
        }}
        probes={probes}
        testingId={testingId}
        busy={save.isPending || toggle.isPending || move.isPending || remove.isPending}
        labels={listLabels}
        onToggle={(id, enabled) => toggle.mutate({ id, enabled })}
        onMove={(id, direction) => move.mutate({ id, direction })}
        onTest={(id) => void test(id)}
        onEdit={openEdit}
        onDelete={(id) => void handleDelete(id)}
      />

      {adding ? (
        <Modal open onOpenChange={(next) => !next && setAdding(false)}>
          <ModalContent size="md" closeLabel={t('common.close')}>
            <ModalHeader>
              <ModalTitle className="text-base">{t('settings.webSearchAdd')}</ModalTitle>
              <ModalDescription>{t('settings.webSearchAddHint')}</ModalDescription>
            </ModalHeader>
            <div className="px-6 pb-6">
              <WebSearchProviderWizard
                catalog={{
                  order: catalog.data?.providerOrder ?? [],
                  entries: catalogEntries,
                }}
                defaultName={defaultName}
                extraFields={extraFields}
                busy={save.isPending}
                error={wizardError}
                labels={wizardLabels}
                onCancel={() => setAdding(false)}
                onSave={saveWizard}
              />
            </div>
          </ModalContent>
        </Modal>
      ) : null}

      {editing && catalogEntries[editing.provider.type] ? (
        <Modal open onOpenChange={(next) => !next && setEditing(null)}>
          <ModalContent size="md" closeLabel={t('common.close')}>
            <ModalHeader>
              <ModalTitle className="text-base">{t('settings.webSearchEdit')}</ModalTitle>
              <ModalDescription>
                {catalogEntries[editing.provider.type]?.label ?? editing.provider.type}
              </ModalDescription>
            </ModalHeader>
            <div className="space-y-2 px-6 pb-6">
              <WebSearchProviderSettingsForm
                type={editing.provider.type}
                entry={catalogEntries[editing.provider.type]}
                mode="edit"
                value={editing.value}
                onChange={(value) => setEditing({ ...editing, value })}
                onSubmit={saveEdit}
                onCancel={() => setEditing(null)}
                storedKeyHint={editing.provider.key_hint}
                error={editError}
                extraFields={extraFields}
                labels={wizardLabels}
              />
              {editing.provider.key_set ? (
                <div className="flex justify-start">
                  <Button variant="ghost" size="sm" onClick={clearStoredKey}>
                    {t('settings.webSearchClearKey')}
                  </Button>
                </div>
              ) : null}
            </div>
          </ModalContent>
        </Modal>
      ) : null}
      {confirmElement}
    </>
  )
}

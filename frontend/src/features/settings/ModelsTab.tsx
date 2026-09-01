import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, Eye, FileText, AudioLines, Wrench } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { CapabilityDescriptor } from '@/components/ui/capability-chips'
import {
  ModelRegistry,
  type ModelRegistryDraft,
  type ModelRegistryModel,
  type ModelRegistryPatch,
} from '@/components/ui/model-registry'
import {
  createModel,
  deleteModel,
  listModels,
  listProviders,
  listRemoteModels,
  updateModel,
} from '@/lib/api'
import { useConfirm } from '@/lib/use-confirm'

const MODEL_CAPS = ['text', 'vision', 'tools', 'embeddings', 'audio'] as const
const REASONING_EFFORT_OPTIONS = ['none', 'low', 'medium', 'high', 'max', 'xhigh'] as const
const CAP_ICONS = {
  text: FileText,
  vision: Eye,
  tools: Wrench,
  embeddings: Database,
  audio: AudioLines,
} as const

export function ModelsTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const providers = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const [expandedProviderId, setExpandedProviderId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirm, confirmElement] = useConfirm()
  const autoExpanded = useRef(false)

  useEffect(() => {
    if (!autoExpanded.current && !expandedProviderId && providers.data?.length) {
      autoExpanded.current = true
      setExpandedProviderId(String(providers.data[0].id))
    }
  }, [expandedProviderId, providers.data])

  const providerId = expandedProviderId !== null ? Number(expandedProviderId) : null
  const remote = useQuery({
    queryKey: ['remote-models', expandedProviderId],
    queryFn: () => listRemoteModels(providerId!),
    enabled: providerId !== null,
    retry: false,
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['models'] })
    await queryClient.invalidateQueries({ queryKey: ['tasks'] })
  }

  const handleAdd = async (pid: string, draft: ModelRegistryDraft) => {
    setError(null)
    try {
      await createModel({
        provider_id: Number(pid),
        external_id: draft.externalId,
        label: draft.label ?? null,
        caps: draft.caps,
        enabled: true,
        reasoning_effort: draft.reasoningEffort || null,
      })
      await refresh()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const handleAddAll = async (pid: string, drafts: ModelRegistryDraft[]) => {
    setError(null)
    const BATCH = 20
    try {
      for (let offset = 0; offset < drafts.length; offset += BATCH) {
        await Promise.all(
          drafts.slice(offset, offset + BATCH).map((draft) =>
            createModel({
              provider_id: Number(pid),
              external_id: draft.externalId,
              caps: draft.caps,
              enabled: true,
            })
          )
        )
      }
      await refresh()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const handleUpdate = async (model: ModelRegistryModel, patch: ModelRegistryPatch) => {
    setError(null)
    try {
      await updateModel(Number(model.id), {
        ...(patch.label !== undefined ? { label: patch.label } : {}),
        ...(patch.caps !== undefined ? { caps: patch.caps } : {}),
        ...(patch.enabled !== undefined ? { enabled: patch.enabled } : {}),
        ...(patch.reasoningEffort !== undefined
          ? { reasoning_effort: patch.reasoningEffort || null }
          : {}),
      })
      await refresh()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const handleDelete = async (model: ModelRegistryModel) => {
    const ok = await confirm({
      title: t('settings.deleteModel'),
      description: t('settings.confirmDeleteModel'),
      confirmLabel: t('settings.deleteModel'),
      cancelLabel: t('common.cancel'),
      destructive: true,
    })
    if (!ok) {
      return
    }
    setError(null)
    try {
      await deleteModel(Number(model.id))
      await refresh()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const capDescriptors: CapabilityDescriptor[] = MODEL_CAPS.map((cap) => ({
    value: cap,
    label: t(`settings.caps.${cap}`),
    icon: CAP_ICONS[cap],
  }))
  const registryProviders = (providers.data ?? []).map((provider) => ({
    id: String(provider.id),
    name: provider.name,
    type: provider.type,
    baseUrl: provider.base_url ?? undefined,
  }))
  const registryModels: ModelRegistryModel[] = (models.data ?? [])
    .filter((model) => model.enabled)
    .map((model) => ({
      id: String(model.id),
      providerId: String(model.provider_id),
      externalId: model.external_id,
      label: model.label || undefined,
      caps: model.caps,
      enabled: model.enabled,
      reasoningEffort: model.reasoning_effort ?? undefined,
      missing: model.missing,
    }))

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">{t('settings.modelsHint')}</p>
      <ModelRegistry
        providers={registryProviders}
        models={registryModels}
        caps={capDescriptors}
        expandedProviderId={expandedProviderId}
        onExpandedProviderChange={setExpandedProviderId}
        remoteModels={remote.data?.map((remoteModel) => ({
          id: remoteModel.external_id,
          caps: remoteModel.caps,
        }))}
        remoteState={
          remote.fetchStatus === 'fetching'
            ? 'loading'
            : remote.isError
              ? 'error'
              : 'ready'
        }
        remoteError={remote.isError ? remote.error.message : null}
        onRetryRemote={() => void remote.refetch()}
        onAddModel={(pid, draft) => void handleAdd(pid, draft)}
        onAddAll={(pid, drafts) => void handleAddAll(pid, drafts)}
        onUpdateModel={(model, patch) => void handleUpdate(model, patch)}
        onDeleteModel={(model) => void handleDelete(model)}
        reasoningEffortOptions={[...REASONING_EFFORT_OPTIONS]}
        addLabel={t('settings.addShort')}
        addAllLabel={t('settings.addAllShort')}
        browseLabel={t('settings.addModel')}
        configureLabel={t('settings.configure')}
        editLabel={t('settings.editModel')}
        removeLabel={t('settings.deleteModel')}
        missingLabel={t('settings.missing')}
        capsLabel={t('settings.modelCaps')}
        searchPlaceholder={t('settings.searchModels')}
        searchLabel={t('settings.searchModels')}
        capFilterLabel={t('settings.capFilter')}
        unclassifiedLabel={t('settings.unclassified')}
        emptyProviderLabel={t('settings.noModels')}
        remoteEmptyLabel={t('settings.noModelMatches')}
        remoteLoadingLabel={t('settings.loadingModels')}
        retryLabel={t('settings.retry')}
        manualAddLabel={t('settings.addManually')}
        externalIdLabel={t('settings.manualIdLabel')}
        labelLabel={t('settings.modelLabel')}
        reasoningEffortLabel={t('settings.modelReasoningEffort')}
        reasoningEffortPlaceholder={t('settings.modelReasoningEffortPlaceholder')}
        saveLabel={t('settings.save')}
        cancelLabel={t('settings.cancel')}
        addDraftLabel={t('settings.addModel')}
        providersEmptyLabel={t('settings.noProvidersFirst')}
      />
      {error ? <p className="text-danger text-xs">{error}</p> : null}
      {confirmElement}
    </div>
  )
}

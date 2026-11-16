import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AudioLines,
  Database,
  Eye,
  FileText,
  Volume2,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { ModelPickerProvider } from '@/components/ui/model-picker'
import {
  TaskAssignmentPicker,
  type TaskAssignmentSection,
} from '@/components/ui/task-assignment-picker'
import { assignTaskDefault, listModels, listProviders, listTaskDefaults } from '@/lib/api'

const CAP_ORDER = ['text', 'vision', 'embeddings', 'stt', 'tts'] as const
const DEFAULT_PREFIX = 'default:'
const CAP_ICONS: Record<(typeof CAP_ORDER)[number], LucideIcon> = {
  text: FileText,
  vision: Eye,
  embeddings: Database,
  stt: AudioLines,
  tts: Volume2,
}

export function DefaultsStep() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const defaults = useQuery({ queryKey: ['task-defaults'], queryFn: listTaskDefaults })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const providers = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const [error, setError] = useState<string | null>(null)
  const autoAssigned = useRef(new Set<string>())

  const providersList = providers.data ?? []
  const allLocal =
    providersList.length > 0 && providersList.every((provider) => provider.is_local)

  const enabledModels = useMemo(
    () => (models.data ?? []).filter((model) => model.enabled && !model.missing),
    [models.data]
  )
  const defaultByCap = useMemo(
    () => new Map((defaults.data ?? []).map((entry) => [entry.requires, entry])),
    [defaults.data]
  )
  const providerNames = new Map(
    providersList.map((provider) => [provider.id, provider.name])
  )
  const catalog = Object.values(
    enabledModels.reduce<Record<string, ModelPickerProvider>>((acc, model) => {
      acc[model.provider_id] = acc[model.provider_id] ?? {
        id: String(model.provider_id),
        name: providerNames.get(model.provider_id) ?? `#${model.provider_id}`,
        models: [],
      }
      acc[model.provider_id].models.push({
        id: String(model.id),
        name: model.label || model.external_id,
        capabilities: model.caps,
      })
      return acc
    }, {})
  )

  const assign = useMutation({
    mutationFn: ({
      requires,
      modelId,
      fallbackModelId,
    }: {
      requires: string
      modelId: string | null
      fallbackModelId: string | null
    }) => assignTaskDefault(requires, modelId, fallbackModelId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['task-defaults'] })
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
      await queryClient.invalidateQueries({ queryKey: ['onboarding-state'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  useEffect(() => {
    if (!defaults.data || !models.data) {
      return
    }
    for (const cap of CAP_ORDER) {
      if (autoAssigned.current.has(cap)) {
        continue
      }
      const entry = defaultByCap.get(cap)
      if (entry?.model_id != null) {
        continue
      }
      const candidate = enabledModels.find((model) => model.caps.includes(cap))
      if (!candidate) {
        continue
      }
      autoAssigned.current.add(cap)
      assign.mutate({
        requires: cap,
        modelId: candidate.id,
        fallbackModelId: entry?.fallback_model_id ?? null,
      })
    }
  }, [assign, defaultByCap, defaults.data, enabledModels, models.data])

  const value: Record<string, string | null> = {}
  for (const cap of CAP_ORDER) {
    const entry = defaultByCap.get(cap)
    value[`${DEFAULT_PREFIX}${cap}`] =
      entry?.model_id != null ? String(entry.model_id) : null
  }

  const handleAssign = (taskId: string, modelId: string | null) => {
    if (!taskId.startsWith(DEFAULT_PREFIX)) {
      return
    }
    const requires = taskId.slice(DEFAULT_PREFIX.length)
    setError(null)
    assign.mutate({
      requires,
      modelId,
      fallbackModelId: defaultByCap.get(requires)?.fallback_model_id ?? null,
    })
  }

  const section: TaskAssignmentSection = {
    id: 'defaults',
    label: t('settings.defaultModelsTitle'),
    tasks: CAP_ORDER.map((cap) => ({
      id: `${DEFAULT_PREFIX}${cap}`,
      label: t(`settings.caps.${cap}`),
      requires: cap,
      icon: CAP_ICONS[cap],
    })),
  }

  return (
    <div className="space-y-3">
      <p className="text-muted-foreground text-sm">{t('onboarding.defaultsHint')}</p>
      {allLocal ? (
        <p className="border-success/30 bg-success/10 text-success rounded-md border px-3 py-2 text-xs">
          {t('settings.localOnlyHint')}
        </p>
      ) : null}
      {error ? <p className="text-danger text-xs">{error}</p> : null}
      {enabledModels.length === 0 ? (
        <p className="text-muted-foreground py-4 text-center text-sm">
          {t('onboarding.defaultsNone')}
        </p>
      ) : (
        <TaskAssignmentPicker
          sections={[section]}
          providers={catalog}
          value={value}
          onAssign={handleAssign}
          primaryLabel={t('settings.primaryPicker')}
          primaryInfo={t('settings.primaryInfo')}
          fallbackInfo={t('settings.fallbackInfo')}
          clearLabel={t('settings.clearAssignment')}
          placeholder={t('settings.unassigned')}
          disabled={assign.isPending}
        />
      )}
    </div>
  )
}

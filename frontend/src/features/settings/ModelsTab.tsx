import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  deleteModel,
  listModels,
  listProviders,
  type AiModel,
  type Provider,
} from '@/lib/api'

import { useConfirm } from '@/lib/use-confirm'
import { cn } from '@/lib/utils'
import { AddModelDialog } from './AddModelDialog'
import { EditModelDialog } from './EditModelDialog'

function CapBadge({ cap }: { cap: string }) {
  return (
    <span className="bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[11px]">
      {cap}
    </span>
  )
}

function ModelRow({
  model,
  onEdit,
}: {
  model: AiModel
  onEdit: (model: AiModel) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [confirm, confirmElement] = useConfirm()
  const remove = useMutation({
    mutationFn: () => deleteModel(model.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['models'] })
      await queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
  })

  return (
    <div
      className={cn(
        'hover:bg-subtle flex items-center gap-3 rounded-md px-2 py-1.5 text-sm',
        model.missing && 'opacity-50'
      )}
    >
      <span className="min-w-0 flex-1 truncate font-mono text-xs" title={model.label}>
        {model.external_id}
      </span>
      {model.missing ? (
        <span className="text-warning text-[11px]">{t('settings.missing')}</span>
      ) : null}
      <span className="hidden shrink-0 gap-1 sm:flex">
        {model.caps.map((cap) => (
          <CapBadge key={cap} cap={cap} />
        ))}
      </span>
      <Button
        variant="ghost"
        size="icon"
        className="size-7 shrink-0"
        title={t('settings.editModel')}
        onClick={() => onEdit(model)}
      >
        <Pencil className="size-3.5" aria-hidden />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="size-7 shrink-0"
        title={t('settings.deleteModel')}
        disabled={remove.isPending}
        onClick={async () => {
          const ok = await confirm({
            title: t('settings.deleteModel'),
            description: t('settings.confirmDeleteModel'),
            confirmLabel: t('settings.deleteModel'),
            cancelLabel: t('common.cancel'),
            destructive: true,
          })
          if (ok) remove.mutate()
        }}
      >
        {remove.isPending ? (
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
        ) : (
          <Trash2 className="size-3.5" aria-hidden />
        )}
      </Button>
      {confirmElement}
    </div>
  )
}

export function ModelsTab() {
  const { t } = useTranslation()
  const providers = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const models = useQuery({ queryKey: ['models'], queryFn: listModels })
  const [addTo, setAddTo] = useState<Provider | null>(null)
  const [editing, setEditing] = useState<AiModel | null>(null)

  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">{t('settings.modelsHint')}</p>
      {(providers.data ?? []).map((provider) => {
        const providerModels = (models.data ?? []).filter(
          (model) => model.provider_id === provider.id
        )
        const selected = providerModels.filter((model) => model.enabled)
        return (
          <Card key={provider.id}>
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle className="text-sm">
                {provider.name}
                <span className="text-muted-foreground ml-2 text-xs font-normal">
                  {t('settings.selectedCount', { count: selected.length })}
                </span>
              </CardTitle>
              <div className="flex gap-2">
                <Button size="sm" onClick={() => setAddTo(provider)}>
                  <Plus aria-hidden />
                  {t('settings.addModel')}
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-1">
              {selected.length === 0 ? (
                <p className="text-muted-foreground text-xs">{t('settings.noModels')}</p>
              ) : null}
              {selected.map((model) => (
                <ModelRow key={model.id} model={model} onEdit={(next) => setEditing(next)} />
              ))}
            </CardContent>
          </Card>
        )
      })}
      {providers.data && providers.data.length === 0 ? (
        <p className="text-muted-foreground py-8 text-center text-sm">
          {t('settings.noProvidersFirst')}
        </p>
      ) : null}
      {addTo ? (
        <AddModelDialog
          provider={addTo}
          existingModels={(models.data ?? []).filter((model) => model.provider_id === addTo.id)}
          onClose={() => setAddTo(null)}
        />
      ) : null}
      {editing ? <EditModelDialog model={editing} onClose={() => setEditing(null)} /> : null}
    </div>
  )
}

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { HardDriveDownload, Plus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import {
  createProvider,
  detectLocalEngines,
  type LocalEngineHit,
  type Provider,
} from '@/lib/api'

export function LocalEngines({
  auto = false,
  onCreated,
}: {
  auto?: boolean
  onCreated?: (provider: Provider) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [armed, setArmed] = useState(auto)
  const [addingId, setAddingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const detection = useQuery({
    queryKey: ['local-engines'],
    queryFn: detectLocalEngines,
    enabled: armed,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
    retry: false,
  })

  const add = useMutation({
    mutationFn: (hit: LocalEngineHit) =>
      createProvider({
        name: hit.name,
        type: 'openai_compatible',
        base_url: hit.base_url,
        api_key: null,
        is_local: true,
      }),
    onSuccess: async (provider) => {
      await queryClient.invalidateQueries({ queryKey: ['providers'] })
      await queryClient.invalidateQueries({ queryKey: ['models'] })
      onCreated?.(provider)
    },
    onError: (err: Error) => setError(err.message),
  })

  const addHit = (hit: LocalEngineHit) => {
    setAddingId(hit.preset_id)
    setError(null)
    add.mutate(hit, { onSettled: () => setAddingId(null) })
  }

  const probing = detection.isFetching
  const hits = detection.data ?? []
  const done = armed && !probing

  return (
    <div className="space-y-2" data-as="local-engines">
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={probing}
          onClick={() => setArmed(true)}
        >
          {probing ? <Spinner className="size-4" /> : <HardDriveDownload aria-hidden />}
          {probing ? t('settings.detectingLocal') : t('settings.detectLocal')}
        </Button>
        {done && hits.length > 0 ? (
          <span className="text-muted-foreground text-xs">{t('settings.localFound')}</span>
        ) : null}
      </div>
      {done && hits.length === 0 ? (
        <p className="text-muted-foreground text-xs">{t('settings.noLocalEngines')}</p>
      ) : null}
      {hits.map((hit) => (
        <div
          key={hit.base_url}
          className="border-border bg-surface flex items-center gap-3 rounded-md border px-3 py-2"
        >
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{hit.name}</p>
            <p className="text-muted-foreground truncate font-mono text-xs">
              {hit.base_url} · {t('settings.localEngineModels', { count: hit.models.length })}
            </p>
          </div>
          <Button
            size="sm"
            disabled={addingId === hit.preset_id}
            onClick={() => addHit(hit)}
          >
            {addingId === hit.preset_id ? (
              <Spinner className="size-4" />
            ) : (
              <Plus aria-hidden />
            )}
            {t('settings.addEngine', { name: hit.name })}
          </Button>
        </div>
      ))}
      {error ? <p className="text-danger text-xs">{error}</p> : null}
    </div>
  )
}

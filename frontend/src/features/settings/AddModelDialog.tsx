import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Loader2, Pencil, Plus } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { SearchInput } from '@/components/ui/SearchInput'
import { createModel, listRemoteModels, type AiModel, type Provider } from '@/lib/api'
import { fuzzyFilter, fuzzyScore } from '@/lib/fuzzy'

import { MODEL_CAPS } from './EditModelDialog'
import { ProviderFormDialog } from './ProviderFormDialog'
import { useCloseFloatings } from '@/lib/ui-overlays'

const PAGE_SIZE = 30

function CapBadge({ cap }: { cap: string }) {
  return (
    <span className="bg-subtle text-muted-foreground rounded-full px-2 py-0.5 text-[11px]">
      {cap}
    </span>
  )
}

function CapChips({
  caps,
  onToggle,
}: {
  caps: string[]
  onToggle: (cap: string) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap gap-1.5">
      {MODEL_CAPS.map((cap) => (
        <button
          key={cap}
          type="button"
          aria-pressed={caps.includes(cap)}
          onClick={() => onToggle(cap)}
          className={
            caps.includes(cap)
              ? 'border-primary bg-primary/10 text-primary rounded-full border px-2.5 py-0.5 text-[11px]'
              : 'border-border text-muted-foreground rounded-full border px-2.5 py-0.5 text-[11px]'
          }
        >
          {t(`settings.caps.${cap}`)}
        </button>
      ))}
    </div>
  )
}

export function AddModelDialog({
  provider,
  existingModels,
  onClose,
}: {
  provider: Provider
  existingModels: AiModel[]
  onClose: () => void
}) {
  useCloseFloatings()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [addedNote, setAddedNote] = useState<string | null>(null)
  const [editProviderOpen, setEditProviderOpen] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [manualId, setManualId] = useState('')
  const [manualLabel, setManualLabel] = useState('')
  const [manualCaps, setManualCaps] = useState<string[]>(['text'])
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const sentinelRef = useRef<HTMLDivElement>(null)

  const remote = useQuery({
    queryKey: ['remote-models', provider.id],
    queryFn: () => listRemoteModels(provider.id),
    retry: false,
  })

  useEffect(() => {
    setVisibleCount(PAGE_SIZE)
  }, [query])

  const matches = useMemo(() => {
    const items = remote.data ?? []
    const needle = query.trim()
    if (!needle) {
      return items
    }
    const ranked = fuzzyFilter(items, needle, (model) => model.external_id)
    const rankedSet = new Set(ranked)
    const capMatches = items.filter(
      (model) =>
        !rankedSet.has(model) &&
        model.caps.some((cap) => fuzzyScore(needle, cap) !== null)
    )
    return [...ranked, ...capMatches]
  }, [remote.data, query])

  const visible = matches.slice(0, visibleCount)

  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel || typeof IntersectionObserver === 'undefined') {
      return
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisibleCount((current) => current + PAGE_SIZE)
      }
    })
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [visibleCount, matches.length])

  const add = useMutation({
    mutationFn: (body: {
      external_id: string
      caps?: string[] | null
      label?: string | null
    }) => createModel({ provider_id: provider.id, enabled: true, ...body }),
    onSuccess: async (_result, variables) => {
      setError(null)
      setAddedNote(variables.external_id)
      await queryClient.invalidateQueries({ queryKey: ['models'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const addAll = useMutation({
    mutationFn: async (targets: { external_id: string; caps?: string[] | null }[]) => {
      const BATCH = 20
      for (let offset = 0; offset < targets.length; offset += BATCH) {
        await Promise.all(
          targets.slice(offset, offset + BATCH).map((target) =>
            createModel({
              provider_id: provider.id,
              enabled: true,
              ...target,
            })
          )
        )
      }
    },
    onSuccess: async (_result, targets) => {
      setError(null)
      setAddedNote(t('settings.bulkAdded', { count: targets.length }))
      await queryClient.invalidateQueries({ queryKey: ['models'] })
    },
    onError: (err: Error) => setError(err.message),
  })

  const addAllMatches = () => {
    if (matches.length > 20 && !window.confirm(t('settings.confirmAddAll', { count: matches.length }))) {
      return
    }
    addAll.mutate(
      matches.map((model) => ({ external_id: model.external_id, caps: model.caps }))
    )
  }

  const existingByExternal = new Map(
    existingModels.map((model) => [model.external_id, model])
  )

  const toggleManualCap = (cap: string) => {
    setManualCaps((current) =>
      current.includes(cap) ? current.filter((entry) => entry !== cap) : [...current, cap]
    )
  }

  const submitManual = () => {
    const id = manualId.trim()
    if (!id) {
      return
    }
    add.mutate(
      {
        external_id: id,
        label: manualLabel.trim() || null,
        caps: manualCaps,
      },
      {
        onSuccess: () => {
          setManualId('')
          setManualLabel('')
        },
      }
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <Card className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden">
        <CardHeader>
          <CardTitle className="text-base">
            {t('settings.addModelTitle', { provider: provider.name })}
          </CardTitle>
          <CardDescription>{t('settings.addModelHint')}</CardDescription>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
          <SearchInput
            autoFocus
            value={query}
            onChange={setQuery}
            placeholder={t('settings.searchModels')}
            ariaLabel={t('settings.searchModels')}
          />

          {remote.isError ? (
            <div className="border-danger/40 bg-danger/10 space-y-2 rounded-md border p-3">
              <p className="text-danger text-xs">{remote.error.message}</p>
              <p className="text-muted-foreground text-[11px]">
                {t('settings.discoveryFailedHint')}
              </p>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => void remote.refetch()}>
                  {t('settings.retry')}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setEditProviderOpen(true)}
                >
                  <Pencil aria-hidden />
                  {t('settings.editProvider')}
                </Button>
              </div>
            </div>
          ) : null}

          <div className="min-h-0 flex-1 space-y-1 overflow-y-auto">
            {remote.isLoading ? (
              <p className="text-muted-foreground flex items-center justify-center gap-2 py-6 text-xs">
                <Loader2 className="animate-spin" aria-hidden />
                {t('settings.loadingModels')}
              </p>
            ) : null}
            {remote.data !== undefined && visible.length === 0 ? (
              <p className="text-muted-foreground py-6 text-center text-xs">
                {t('settings.noModelMatches')}
              </p>
            ) : null}
            {visible.map((model) => {
              const existing = existingByExternal.get(model.external_id)
              const added = existing?.enabled
              return (
                <div
                  key={model.external_id}
                  className="border-border flex items-center gap-2 rounded-md border px-3 py-2"
                >
                  <span className="min-w-0 flex-1 truncate font-mono text-xs">
                    {model.external_id}
                  </span>
                  <span className="hidden shrink-0 gap-1 sm:flex">
                    {model.caps.map((cap) => (
                      <CapBadge key={cap} cap={cap} />
                    ))}
                  </span>
                  {added ? (
                    <span className="text-muted-foreground flex shrink-0 items-center gap-1 text-[11px]">
                      <Check className="size-3" aria-hidden />
                      {t('settings.modelAdded')}
                    </span>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      className="shrink-0"
                      disabled={add.isPending}
                      onClick={() =>
                        add.mutate({ external_id: model.external_id, caps: model.caps })
                      }
                    >
                      <Plus aria-hidden />
                      {existing ? t('settings.readd') : t('settings.addShort')}
                    </Button>
                  )}
                </div>
              )
            })}
            {visibleCount < matches.length ? (
              <div ref={sentinelRef} className="flex justify-center py-3">
                <Loader2 className="text-muted-foreground size-4 animate-spin" aria-hidden />
                <span className="text-muted-foreground sr-only">
                  {t('settings.loadingModels')}
                </span>
              </div>
            ) : null}
          </div>

          {matches.length > visibleCount ? (
            <p className="text-muted-foreground text-[11px]">
              {t('settings.showingCount', {
                shown: visible.length,
                total: matches.length,
              })}
            </p>
          ) : null}

          <div className="border-border border-t pt-3">
            {manualOpen ? (
              <div className="border-border space-y-2 rounded-md border border-dashed p-3">
                <p className="text-muted-foreground text-[11px]">
                  {t('settings.manualHint')}
                </p>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <label className="min-w-0 flex-1 space-y-1 text-xs">
                    <span className="text-muted-foreground">
                      {t('settings.manualIdLabel')}
                    </span>
                    <input
                      className="bg-surface border-border w-full rounded-md border px-2 py-1.5 font-mono text-xs"
                      placeholder={t('settings.manualIdPlaceholder')}
                      value={manualId}
                      onChange={(event) => setManualId(event.target.value)}
                    />
                  </label>
                  <label className="min-w-0 flex-1 space-y-1 text-xs">
                    <span className="text-muted-foreground">{t('settings.modelLabel')}</span>
                    <input
                      className="bg-surface border-border w-full rounded-md border px-2 py-1.5 text-xs"
                      value={manualLabel}
                      onChange={(event) => setManualLabel(event.target.value)}
                    />
                  </label>
                </div>
                <CapChips caps={manualCaps} onToggle={toggleManualCap} />
                <div className="flex items-center justify-between">
                  {addedNote ? (
                    <p className="text-muted-foreground text-[11px]">
                      {t('settings.manualAdded', { id: addedNote })}
                    </p>
                  ) : (
                    <span />
                  )}
                  <Button
                    size="sm"
                    disabled={!manualId.trim() || add.isPending}
                    onClick={submitManual}
                  >
                    {add.isPending ? (
                      <Loader2 className="animate-spin" aria-hidden />
                    ) : (
                      <Plus aria-hidden />
                    )}
                    {t('settings.addShort')}
                  </Button>
                </div>
              </div>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => setManualOpen(true)}>
                <Plus aria-hidden />
                {t('settings.addManually')}
              </Button>
            )}
          </div>

          {error ? <p className="text-danger text-xs">{error}</p> : null}
          <div className="flex items-center justify-between">
            <Button
              variant="outline"
              size="sm"
              disabled={remote.data === undefined || matches.length === 0 || addAll.isPending}
              title={t('settings.addAllHint')}
              onClick={addAllMatches}
            >
              {addAll.isPending ? (
                <Loader2 className="animate-spin" aria-hidden />
              ) : (
                <Plus aria-hidden />
              )}
              {t('settings.addAll', { count: matches.length })}
            </Button>
            <Button size="sm" onClick={onClose}>
              {t('settings.done')}
            </Button>
          </div>
        </CardContent>
      </Card>
      {editProviderOpen ? (
        <ProviderFormDialog
          provider={provider}
          onSaved={() => {
            void queryClient.invalidateQueries({
              queryKey: ['remote-models', provider.id],
            })
          }}
          onClose={() => setEditProviderOpen(false)}
        />
      ) : null}
    </div>
  )
}

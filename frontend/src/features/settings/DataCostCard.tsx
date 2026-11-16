import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ErrorBanner } from '@/components/ErrorBanner'
import {
  deletePrice,
  getCosts,
  getPrices,
  savePrice,
  type PriceOverrideInput,
} from '@/lib/api/analytics'

function usd(micros: number | null | undefined): string {
  if (micros === null || micros === undefined) {
    return '—'
  }
  return `$${(micros / 1_000_000).toFixed(4)}`
}

const emptyDraft: PriceOverrideInput = {
  provider_key: '',
  provider_ref: '',
  model: '',
  match: 'exact',
  input_micros_per_million: 0,
  output_micros_per_million: 0,
  metering: 'tokens',
}

export function DataCostCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<PriceOverrideInput>(emptyDraft)

  const costs = useQuery({ queryKey: ['costs'], queryFn: getCosts })
  const prices = useQuery({ queryKey: ['prices'], queryFn: getPrices })

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['costs'] })
    await queryClient.invalidateQueries({ queryKey: ['prices'] })
  }

  const save = useMutation({
    mutationFn: (body: PriceOverrideInput) => savePrice(body),
    onSuccess: async () => {
      setDraft(emptyDraft)
      setError(null)
      await invalidate()
    },
    onError: (err: Error) => setError(err.message),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deletePrice(id),
    onSuccess: async () => {
      setError(null)
      await invalidate()
    },
    onError: (err: Error) => setError(err.message),
  })

  const number = (value: string): number => {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed >= 0 ? Math.round(parsed * 1_000_000) : 0
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t('settings.dataCostTitle')}</CardTitle>
        <CardDescription>{t('settings.dataCostHint')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error ? <ErrorBanner message={error} /> : null}
        {costs.isLoading || prices.isLoading ? (
          <Loader2 className="text-muted-foreground animate-spin" aria-label={t('library.loading')} />
        ) : null}

        <section aria-label={t('settings.dataCostOverview')} className="space-y-2">
          <h4 className="text-sm font-semibold">{t('settings.dataCostOverview')}</h4>
          <p className="text-2xl font-semibold">{usd(costs.data?.total_micros)}</p>
          <p className="text-muted-foreground text-xs">
            {t('settings.dataCostMonth', { month: costs.data?.month ?? '—' })}
          </p>
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-border opacity-70">
                <tr>
                  <th className="px-2 py-1 font-medium">{t('settings.dataCostTask')}</th>
                  <th className="px-2 py-1 font-medium">{t('settings.dataCostCalls')}</th>
                  <th className="px-2 py-1 font-medium">{t('settings.dataCostTokens')}</th>
                  <th className="px-2 py-1 text-right font-medium">{t('settings.dataCostCost')}</th>
                </tr>
              </thead>
              <tbody>
                {(costs.data?.per_task ?? []).filter((row) => row.calls > 0).map((row) => (
                  <tr key={row.task} className="border-b border-border last:border-0">
                    <td className="px-2 py-1">{row.task}</td>
                    <td className="px-2 py-1">{row.calls}</td>
                    <td className="px-2 py-1">
                      {row.tokens_in} / {row.tokens_out}
                    </td>
                    <td className="px-2 py-1 text-right">{usd(row.cost_micros)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section aria-label={t('settings.dataCostPrices')} className="space-y-2">
          <h4 className="text-sm font-semibold">{t('settings.dataCostPrices')}</h4>
          <p className="text-muted-foreground text-[11px]">{t('settings.dataCostDisclaimer')}</p>
          <p className="text-muted-foreground text-xs">{t('settings.dataCostBuiltin')}</p>
          <div className="space-y-1">
            {(prices.data?.effective ?? []).map((row) => (
              <div
                key={`${row.provider_id ?? row.provider ?? 'any'}:${row.model}`}
                className="grid gap-2 text-xs sm:grid-cols-[1fr_1fr_auto]"
              >
                <span className="truncate">
                  <span className="text-muted-foreground">{row.provider ?? '—'}</span> ·{' '}
                  <span className="font-mono">{row.model}</span>
                </span>
                <span>
                  {row.source === 'unknown'
                    ? t('settings.dataCostUnpriced')
                    : `${usd(row.input_micros_per_million)} / ${usd(row.output_micros_per_million)} · ${row.source}`}
                </span>
                <span className="text-muted-foreground">
                  {row.reviewed_at ? t('settings.dataCostChecked', { date: row.reviewed_at }) : ''}
                </span>
              </div>
            ))}
          </div>

          <div className="space-y-2 border-t border-border pt-3">
            <h5 className="text-xs font-semibold">{t('settings.dataCostOverrides')}</h5>
            {(prices.data?.overrides ?? []).map((row) => (
              <div
                key={row.id}
                className="grid gap-2 text-xs sm:grid-cols-[1fr_1fr_1fr_auto]"
              >
                <span className="truncate font-mono">{row.model}</span>
                <span className="text-muted-foreground">
                  {row.provider_key ?? row.provider_ref ?? t('settings.dataCostAnyProvider')}
                </span>
                <span>
                  {usd(row.input_micros_per_million)} / {usd(row.output_micros_per_million)}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={t('settings.dataCostRemove', { model: row.model })}
                  onClick={() => remove.mutate(row.id)}
                >
                  <Trash2 className="size-3.5" aria-hidden />
                </Button>
              </div>
            ))}
            {!prices.data?.overrides.length ? (
              <p className="text-muted-foreground text-xs">{t('settings.dataCostNoOverrides')}</p>
            ) : null}

            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <label className="space-y-1 text-xs">
                <span className="text-muted-foreground">{t('settings.dataCostProviderKey')}</span>
                <input
                  className="bg-surface border-border w-full rounded-md border px-2 py-1"
                  value={draft.provider_key ?? ''}
                  onChange={(event) => setDraft({ ...draft, provider_key: event.target.value })}
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="text-muted-foreground">{t('settings.dataCostProviderRef')}</span>
                <input
                  className="bg-surface border-border w-full rounded-md border px-2 py-1"
                  value={draft.provider_ref ?? ''}
                  onChange={(event) => setDraft({ ...draft, provider_ref: event.target.value })}
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="text-muted-foreground">{t('settings.dataCostModel')}</span>
                <input
                  className="bg-surface border-border w-full rounded-md border px-2 py-1"
                  value={draft.model}
                  onChange={(event) => setDraft({ ...draft, model: event.target.value })}
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="text-muted-foreground">{t('settings.dataCostMatch')}</span>
                <select
                  className="bg-surface border-border w-full rounded-md border px-2 py-1"
                  value={draft.match}
                  onChange={(event) =>
                    setDraft({ ...draft, match: event.target.value as 'exact' | 'prefix' })
                  }
                >
                  <option value="exact">{t('settings.dataCostExact')}</option>
                  <option value="prefix">{t('settings.dataCostPrefix')}</option>
                </select>
              </label>
              <label className="space-y-1 text-xs">
                <span className="text-muted-foreground">{t('settings.dataCostInput')}</span>
                <input
                  type="number"
                  min={0}
                  step="0.000001"
                  className="bg-surface border-border w-full rounded-md border px-2 py-1"
                  value={draft.input_micros_per_million / 1_000_000}
                  onChange={(event) =>
                    setDraft({ ...draft, input_micros_per_million: number(event.target.value) })
                  }
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="text-muted-foreground">{t('settings.dataCostOutput')}</span>
                <input
                  type="number"
                  min={0}
                  step="0.000001"
                  className="bg-surface border-border w-full rounded-md border px-2 py-1"
                  value={draft.output_micros_per_million / 1_000_000}
                  onChange={(event) =>
                    setDraft({ ...draft, output_micros_per_million: number(event.target.value) })
                  }
                />
              </label>
              <label className="space-y-1 text-xs">
                <span className="text-muted-foreground">{t('settings.dataCostMetering')}</span>
                <select
                  className="bg-surface border-border w-full rounded-md border px-2 py-1"
                  value={draft.metering}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      metering: event.target.value as PriceOverrideInput['metering'],
                    })
                  }
                >
                  <option value="tokens">{t('settings.dataCostTokensOption')}</option>
                  <option value="input_only">{t('settings.dataCostInputOnly')}</option>
                  <option value="output_only">{t('settings.dataCostOutputOnly')}</option>
                </select>
              </label>
            </div>
            <Button
              size="sm"
              disabled={!draft.model.trim() || save.isPending}
              onClick={() =>
                save.mutate({
                  ...draft,
                  provider_key: draft.provider_key?.trim() || null,
                  provider_ref: draft.provider_ref?.trim() || null,
                })
              }
            >
              <Plus className="size-3.5" aria-hidden />
              {t('settings.dataCostAdd')}
            </Button>
            <p className="text-muted-foreground text-[11px]">{t('settings.dataCostOverrideHint')}</p>
          </div>
        </section>

        <section aria-label={t('settings.dataCostRecent')} className="space-y-2">
          <h4 className="text-sm font-semibold">{t('settings.dataCostRecent')}</h4>
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-border opacity-70">
                <tr>
                  <th className="px-2 py-1 font-medium">{t('settings.dataCostWhen')}</th>
                  <th className="px-2 py-1 font-medium">{t('settings.dataCostTask')}</th>
                  <th className="px-2 py-1 font-medium">{t('settings.dataCostModel')}</th>
                  <th className="px-2 py-1 font-medium">{t('settings.dataCostTokens')}</th>
                  <th className="px-2 py-1 text-right font-medium">{t('settings.dataCostCost')}</th>
                </tr>
              </thead>
              <tbody>
                {(costs.data?.recent ?? []).map((row) => (
                  <tr key={row.id} className="border-b border-border last:border-0">
                    <td className="whitespace-nowrap px-2 py-1">
                      {new Date(row.created_at).toLocaleString()}
                    </td>
                    <td className="px-2 py-1">{row.task ?? '—'}</td>
                    <td className="px-2 py-1 font-mono">{row.resolved_model ?? row.model ?? '—'}</td>
                    <td className="px-2 py-1">
                      {row.input_tokens ?? '—'} / {row.output_tokens ?? '—'}
                    </td>
                    <td className="px-2 py-1 text-right">
                      {row.cost_micros === null ? t('settings.dataCostUnpriced') : usd(row.cost_micros)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </CardContent>
    </Card>
  )
}

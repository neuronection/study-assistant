import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import {
  getRetrievalQuality,
  postRetrievalQualityCompare,
} from '@/lib/api'
import type {
  RetrievalAction,
  RetrievalQuality,
  RetrievalQualityCompareRequest,
} from '@/lib/api'

type BadMatch = NonNullable<RetrievalQuality['bad_matches']>[number]

function newIdempotencyKey() {
  const cryptoApi = globalThis.crypto
  if (typeof cryptoApi?.randomUUID === 'function') {
    return cryptoApi.randomUUID()
  }
  return `retrieval-quality-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function percent(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value * 100)}%`
}

export function RetrievalQualityPanel({
  spaceId,
  activeSpaceId,
  onChanged,
  onNotice,
  onProblem,
}: {
  spaceId: string | null
  activeSpaceId: string | null
  onChanged: () => void
  onNotice: (message: string) => void
  onProblem: (message: string) => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [result, setResult] = useState<RetrievalAction | null>(null)

  const query = useQuery({
    queryKey: ['retrieval-quality', spaceId],
    queryFn: () => getRetrievalQuality(spaceId ?? undefined),
    enabled: spaceId !== null,
    retry: false,
    staleTime: 15_000,
  })

  const compare = useMutation({
    mutationFn: (body: RetrievalQualityCompareRequest) =>
      postRetrievalQualityCompare(body, newIdempotencyKey()),
    onSuccess: (action) => {
      setResult(action)
      setDrawerOpen(false)
      onNotice(
        action.gate === 'pass'
          ? t('settings.retrievalQualityComparePassed')
          : t('settings.retrievalQualityCompareFailed')
      )
      void queryClient.invalidateQueries({ queryKey: ['retrieval-quality'] })
      onChanged()
    },
    onError: (error: unknown) => {
      setResult(null)
      onProblem(
        error instanceof Error && error.message
          ? error.message
          : t('settings.retrievalQualityCompareRefused')
      )
    },
  })

  const data: RetrievalQuality | undefined = query.data
  const canCompare =
    spaceId !== null &&
    activeSpaceId !== null &&
    activeSpaceId !== spaceId
  const quality = data?.quality ?? result?.quality ?? null
  const compareDto = data?.compare ?? result?.quality_compare ?? null
  const badMatches: BadMatch[] =
    data?.bad_matches ?? result?.bad_matches ?? []
  const state = data?.state ?? (result ? 'sampled' : 'not_sampled')
  const set = data?.set ?? null
  const gate = data?.activation_gate ?? result?.gate ?? 'unknown'

  return (
    <div className="space-y-2 border-t pt-3">
      <h3 className="text-xs font-medium">
        {t('settings.retrievalQualityTitle')}
      </h3>
      {query.isLoading ? (
        <span className="text-muted-foreground flex items-center gap-2 text-xs">
          <Loader2 className="animate-spin" aria-hidden />
          {t('settings.retrievalQualityLoading')}
        </span>
      ) : null}
      {data || result ? (
        <div className="space-y-1 text-xs">
          {set ? (
            <p className="text-muted-foreground">
              {t('settings.retrievalQualitySet', {
                version: set.set_version,
                k: set.k,
                count: set.query_count,
              })}
            </p>
          ) : null}
          {state === 'no_golden_set' ? (
            <p className="text-warning">
              {t('settings.retrievalQualityStateNoSet')}
            </p>
          ) : null}
          {state === 'not_sampled' && !result ? (
            <p className="text-muted-foreground">
              {t('settings.retrievalQualityStateNotSampled')}
            </p>
          ) : null}
          {state === 'stale_compare' ? (
            <p className="text-warning">
              {t('settings.retrievalQualityStateStale')}
            </p>
          ) : null}
          {quality ? (
            <p
              className={
                quality.passed ? 'text-success' : 'text-destructive'
              }
            >
              {quality.passed
                ? t('settings.retrievalQualityAboveFloor')
                : t('settings.retrievalQualityBelowFloor')}
            </p>
          ) : null}
          {quality ? (
            <p className="text-muted-foreground">
              {t('settings.retrievalQualityScores', {
                recall: percent(quality.recall_at_k),
                recallFloor: percent(quality.floor_recall),
                precision: percent(quality.precision_at_k),
                precisionFloor: percent(quality.floor_precision),
              })}
            </p>
          ) : null}
          {compareDto ? (
            <p className="text-muted-foreground">
              {t('settings.retrievalQualityCompareScores', {
                oldRecall: percent(compareDto.old_recall_at_k),
                newRecall: percent(compareDto.new_recall_at_k),
                oldPrecision: percent(compareDto.old_precision_at_k),
                newPrecision: percent(compareDto.new_precision_at_k),
              })}
            </p>
          ) : null}
          <p className="text-muted-foreground">
            {t('settings.retrievalQualityGate', { state: gate })}
          </p>
          {badMatches.length > 0 ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setDrawerOpen((open) => !open)}
            >
              {drawerOpen
                ? t('settings.retrievalQualityHideBadMatches')
                : t('settings.retrievalQualityShowBadMatches')}
            </Button>
          ) : quality && quality.passed ? (
            <p className="text-muted-foreground">
              {t('settings.retrievalQualityNoBadMatches')}
            </p>
          ) : null}
          {drawerOpen ? (
            <ul className="border-border space-y-2 rounded-md border px-2 py-1.5">
              {badMatches.map((entry) => {
                const missing = entry.missing_document_ids ?? []
                const hits = entry.hits ?? []
                return (
                <li key={`${entry.query_id}-${missing.join('-')}`}>
                  <p className="font-medium">{entry.query_id}</p>
                  <p className="text-muted-foreground">
                    {t('settings.retrievalQualityMissing', {
                      ids: missing.join(', '),
                    })}
                  </p>
                  <ul className="text-muted-foreground">
                    {hits.slice(0, 5).map((hit) => (
                      <li
                        key={`${entry.query_id}-${String(hit.chunk_id)}`}
                        className="font-mono text-[11px]"
                      >
                        {t('settings.retrievalQualityHit', {
                          chunk: String(hit.chunk_id ?? ''),
                          doc: String(hit.document_id ?? ''),
                          view: String(hit.view ?? ''),
                          score:
                            typeof hit.score === 'number'
                              ? hit.score.toFixed(3)
                              : '—',
                        })}
                      </li>
                    ))}
                  </ul>
                </li>
                )
              })}
            </ul>
          ) : null}
        </div>
      ) : null}
      {canCompare ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={compare.isPending}
          onClick={() => {
            if (!spaceId || !activeSpaceId) return
            compare.mutate({
              space_id: spaceId,
              compare_space_id: activeSpaceId,
            })
          }}
        >
          {compare.isPending ? (
            <Loader2 className="animate-spin" aria-hidden />
          ) : null}
          {t('settings.retrievalQualityCompare')}
        </Button>
      ) : null}
    </div>
  )
}

import { useTranslation } from 'react-i18next'

import { Badge } from '@/components/ui/badge'
import type { RetrievalRunProgress } from '@/lib/api'

import { formatNumber } from './retrievalObservation'

type TokenizerShape = {
  kind?: unknown
  identifier?: unknown
  exact?: unknown
  source?: unknown
  max_input_tokens?: unknown
}

type ChunkShape = {
  max_chunk_tokens?: unknown
  overlap_tokens?: unknown
}

function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function textOrNull(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

/**
 * The live indexing bar for one vector run (plan 52 T5c).
 *
 * Documents are exact at scan start; chunk totals are cumulative or
 * estimated, so the bar is driven by processed/total documents and the chunk
 * remainder is always labelled. Compact mode keeps the Settings run row and
 * the observation table narrow; the drawer uses the full counter set.
 */
export function RetrievalProgress({
  detail,
  compact = false,
  testId = 'retrieval-progress',
}: {
  detail: RetrievalRunProgress | null | undefined
  compact?: boolean
  testId?: string
}) {
  const { t } = useTranslation()
  if (!detail) {
    return compact ? (
      <span className="text-muted-foreground" data-testid={`${testId}-empty`}>
        —
      </span>
    ) : (
      <p className="text-muted-foreground text-xs" data-testid={`${testId}-empty`}>
        {t('settings.retrievalProgressUnavailable')}
      </p>
    )
  }

  const total = Math.max(detail.total_documents, 0)
  const processed = Math.min(
    Math.max(detail.processed_documents, 0),
    total || Number.MAX_SAFE_INTEGER
  )
  const percent =
    total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : detail.done ? 100 : 0
  const tokens = detail.tokens

  return (
    <div className="min-w-0 space-y-1" data-testid={testId}>
      <div
        className="bg-subtle h-1.5 w-full overflow-hidden rounded-full"
        role="progressbar"
        aria-label={t('settings.retrievalProgressAria', { percent })}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        data-testid={`${testId}-bar`}
      >
        <div
          className="bg-primary h-full rounded-full transition-[width] duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px]">
        <span
          className="text-foreground font-medium tabular-nums"
          data-testid={`${testId}-documents`}
        >
          {total > 0
            ? t('settings.retrievalProgressDocuments', {
                processed: formatNumber(processed),
                total: formatNumber(total),
              })
            : t('settings.retrievalProgressDocumentsNoTotal', {
                processed: formatNumber(processed),
              })}
        </span>
        {detail.done ? (
          <Badge variant="success" data-testid={`${testId}-done`}>
            {t('settings.retrievalProgressDone')}
          </Badge>
        ) : null}
        {detail.chunks_estimated && !detail.done ? (
          <span data-testid={`${testId}-estimated`}>
            {t('settings.retrievalProgressEstimated')}
          </span>
        ) : null}
        {detail.pending_chunks > 0 ? (
          <span className="tabular-nums" data-testid={`${testId}-pending`}>
            {t('settings.retrievalProgressPendingChunks', {
              count: formatNumber(detail.pending_chunks),
            })}
          </span>
        ) : null}
        {!compact ? (
          <>
            <span className="tabular-nums" data-testid={`${testId}-embedded`}>
              {t('settings.retrievalProgressEmbedded', {
                documents: formatNumber(detail.embedded_documents),
                chunks: formatNumber(detail.embedded_chunks),
              })}
            </span>
            {detail.skipped_documents > 0 || detail.skipped_chunks > 0 ? (
              <span className="tabular-nums" data-testid={`${testId}-skipped`}>
                {t('settings.retrievalProgressSkipped', {
                  count: formatNumber(detail.skipped_documents),
                })}
              </span>
            ) : null}
            {detail.failed_documents > 0 || detail.failed_chunks > 0 ? (
              <span className="text-danger tabular-nums" data-testid={`${testId}-failed`}>
                {t('settings.retrievalProgressFailed', {
                  count: formatNumber(detail.failed_documents),
                })}
              </span>
            ) : null}
            {tokens !== null && tokens !== undefined ? (
              <span className="tabular-nums" data-testid={`${testId}-tokens`}>
                {detail.tokens_estimated
                  ? t('settings.retrievalProgressTokensApprox', {
                      count: formatNumber(tokens),
                    })
                  : t('settings.retrievalProgressTokens', {
                      count: formatNumber(tokens),
                    })}
              </span>
            ) : null}
            {detail.embed_calls > 0 ? (
              <span className="tabular-nums" data-testid={`${testId}-calls`}>
                {t('settings.retrievalProgressEmbedCalls', {
                  count: formatNumber(detail.embed_calls),
                })}
              </span>
            ) : null}
            <span className="tabular-nums" data-testid={`${testId}-phase`}>
              {t('settings.retrievalProgressPhase', { phase: detail.phase })}
            </span>
            <span className="tabular-nums" data-testid={`${testId}-tokenizer`}>
              {detail.exact_tokenizer
                ? t('settings.retrievalProgressExactTokenizer')
                : t('settings.retrievalProgressApproxTokenizer')}
            </span>
          </>
        ) : null}
      </p>
    </div>
  )
}

/**
 * The read-only token-aware/legacy label for a space or run (plan 52 T5c).
 *
 * The label comes from the persisted space identity and never re-resolves a
 * model name: a legacy space says so, a v2 space names the tokenizer, its
 * selection source and whether the count is exact.
 */
export function RetrievalTokenizerLabel({
  tokenAware,
  tokenizer,
  chunk,
  compact = false,
}: {
  tokenAware: boolean | null | undefined
  tokenizer: TokenizerShape | null | undefined
  chunk?: ChunkShape | null
  compact?: boolean
}) {
  const { t } = useTranslation()
  if (!tokenAware || !tokenizer) {
    return (
      <span
        className="text-muted-foreground text-[11px]"
        data-testid="retrieval-tokenizer-label"
      >
        {t('settings.retrievalTokenizerLegacy')}
      </span>
    )
  }
  const identifier = textOrNull(tokenizer.identifier)
  const source = textOrNull(tokenizer.source)
  const exact = tokenizer.exact === true
  const maxChunk = numberOrNull(chunk?.max_chunk_tokens)
  const overlap = numberOrNull(chunk?.overlap_tokens)
  const maxInput = numberOrNull(tokenizer.max_input_tokens)

  return (
    <span
      className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px]"
      data-testid="retrieval-tokenizer-label"
    >
      <Badge variant={exact ? 'success' : 'warning'} data-testid="retrieval-tokenizer-status">
        {exact
          ? t('settings.retrievalTokenizerExact')
          : t('settings.retrievalTokenizerApprox')}
      </Badge>
      <span data-testid="retrieval-tokenizer-aware">
        {t('settings.retrievalTokenizerAware')}
      </span>
      {identifier ? (
        <span className="font-mono" data-testid="retrieval-tokenizer-identifier">
          {identifier}
        </span>
      ) : null}
      {source ? (
        <span data-testid="retrieval-tokenizer-source">
          {t('settings.retrievalTokenizerSource', { source })}
        </span>
      ) : null}
      {!compact && maxChunk !== null && overlap !== null ? (
        <span data-testid="retrieval-tokenizer-chunk">
          {t('settings.retrievalTokenizerChunk', {
            max: formatNumber(maxChunk),
            overlap: formatNumber(overlap),
          })}
        </span>
      ) : null}
      {!compact && maxInput !== null ? (
        <span data-testid="retrieval-tokenizer-limit">
          {t('settings.retrievalTokenizerLimit', { max: formatNumber(maxInput) })}
        </span>
      ) : null}
    </span>
  )
}

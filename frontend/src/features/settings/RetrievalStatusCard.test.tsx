import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { RetrievalStatusCard } from './RetrievalStatusCard'

const getRetrievalOverview = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getRetrievalOverview: () => getRetrievalOverview(),
  }
})

vi.mock('@/lib/auth-session', () => ({
  getCurrentUser: () => ({ is_admin: true }),
}))

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <RetrievalStatusCard />
    </QueryClientProvider>
  )
}

describe('RetrievalStatusCard', () => {
  beforeEach(() => {
    getRetrievalOverview.mockReset()
  })

  test('shows a cold store honestly and never invents coverage', async () => {
    getRetrievalOverview.mockResolvedValue({
      state: 'cold',
      cold: true,
      backend: 'sqlite_vec',
      backend_label: 'SQLite sqlite-vec',
      space: {
        space_id: 'legacy-chunk-vecs',
        name: 'content (legacy chunk_vecs)',
        status: 'active',
        provider: 'openai',
        model: 'text-embedding-3-small',
        dim: 1536,
        backend: 'sqlite_vec',
        metric: 'cosine',
        index_table: 'chunk_vecs',
        documents: 3,
        records: 12,
        coverage: null,
        stale: null,
        failed: null,
        created_at: null,
        activated_at: null,
        retired_at: null,
        last_reindex_at: null,
        last_error: null,
        gate: 'unknown',
        as_of: null,
      },
      coverage: {
        space_id: 'legacy-chunk-vecs',
        as_of: null,
        total: 0,
        missing: 0,
        stale: 0,
        failed: 0,
        embedded: 0,
        coverage: null,
        gate: 'unknown',
        ann_recall: null,
        ann_recall_k: null,
        probe_size: null,
      },
      recent_runs: [],
      query_health: {
        window: '24h',
        window_start: null,
        window_end: null,
        query_count: 0,
        candidates_avg: null,
        health: {
          space_id: 'legacy-chunk-vecs',
          window_start: '2026-11-03T00:00:00Z',
          window_end: '2026-11-04T00:00:00Z',
          p50_ms: null,
          p95_ms: null,
          candidate_p50: null,
          candidate_p95: null,
          zero_result_rate: null,
          degraded_rate: null,
          degraded_reasons: {},
          per_view_hits: {},
          ann_recall: null,
          ann_recall_k: null,
          probe_size: null,
          sampled: false,
          sample_size: 0,
          query_count: 0,
        },
      },
      notes: ['Never reconciled — run a vector reindex to publish coverage.'],
    })
    renderCard()
    expect(await screen.findByText(/not reconciled yet/i)).toBeInTheDocument()
    expect(screen.getByText(/3 documents · 12 vectors/i)).toBeInTheDocument()
    expect(screen.queryByText(/coverage:/i)).not.toBeInTheDocument()
    expect(screen.getByText(/never reconciled/i)).toBeInTheDocument()
  })
})

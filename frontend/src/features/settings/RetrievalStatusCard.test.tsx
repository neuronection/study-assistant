import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { RetrievalStatusCard } from './RetrievalStatusCard'

const getRetrievalOverview = vi.fn()
const getRetrievalRuns = vi.fn()
const postRetrievalReindex = vi.fn()
const postRetrievalMaintenance = vi.fn()
const cancelRetrievalRun = vi.fn()
const retryRetrievalRun = vi.fn()

vi.mock('@/lib/api', () => ({
  getRetrievalOverview: () => getRetrievalOverview(),
  getRetrievalRuns: () => getRetrievalRuns(),
  postRetrievalReindex: (body: unknown, key: string) =>
    postRetrievalReindex(body, key),
  postRetrievalMaintenance: (body: unknown, key: string) =>
    postRetrievalMaintenance(body, key),
  cancelRetrievalRun: (runId: string) => cancelRetrievalRun(runId),
  retryRetrievalRun: (runId: string, key: string) =>
    retryRetrievalRun(runId, key),
}))

vi.mock('@/lib/auth-session', () => ({
  getCurrentUser: () => ({ is_admin: true }),
}))

function overview(overrides: Record<string, unknown> = {}) {
  return {
    state: 'ready',
    cold: false,
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
      coverage: 1,
      stale: null,
      failed: 0,
      created_at: null,
      activated_at: null,
      retired_at: null,
      last_reindex_at: null,
      last_error: null,
      gate: 'pass',
      as_of: '2026-11-04T00:00:00Z',
    },
    coverage: {
      space_id: 'legacy-chunk-vecs',
      as_of: '2026-11-04T00:00:00Z',
      total: 12,
      missing: 0,
      stale: 0,
      failed: 0,
      embedded: 12,
      coverage: 1,
      gate: 'pass',
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
      health: {},
    },
    notes: [],
    ...overrides,
  }
}

function run(
  status: string,
  runId: string,
  result: Record<string, unknown> | null = null
) {
  return {
    run: {
      run_id: runId,
      space_id: 'legacy-chunk-vecs',
      job_type: 'VECTOR_REINDEX',
      status,
      progress: status === 'running' ? 42 : 0,
      stage: status === 'running' ? 'reindex 3/10' : null,
      scope: { kind: null, view: null, since: null },
      budget_tokens: null,
      created_at: '2026-11-04T00:00:00Z',
      started_at: null,
      finished_at: null,
      heartbeat_at: null,
      error: null,
      cancel_requested: false,
      idempotency_key: 'key-0000001',
      lock_key: 'vector_space:legacy-chunk-vecs',
    },
    result,
    duration_seconds: null,
  }
}

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
    getRetrievalRuns.mockReset()
    postRetrievalReindex.mockReset()
    postRetrievalMaintenance.mockReset()
    cancelRetrievalRun.mockReset()
    retryRetrievalRun.mockReset()
    getRetrievalRuns.mockResolvedValue({ runs: [] })
  })

  test('shows a cold store honestly and never invents coverage', async () => {
    getRetrievalOverview.mockResolvedValue(
      overview({
        state: 'cold',
        cold: true,
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
        notes: ['Never reconciled — run a vector reindex to publish coverage.'],
      })
    )
    renderCard()
    expect(await screen.findByText(/not reconciled yet/i)).toBeInTheDocument()
    expect(screen.getByText(/3 documents · 12 vectors/i)).toBeInTheDocument()
    expect(screen.queryByText(/coverage:/i)).not.toBeInTheDocument()
    expect(screen.getByText(/never reconciled/i)).toBeInTheDocument()
    expect(
      screen.getByText(/chunk_vecs remains the compatibility fallback/i)
    ).toBeInTheDocument()
  })

  test('starts a force reindex with an idempotency key', async () => {
    getRetrievalOverview.mockResolvedValue(overview())
    postRetrievalReindex.mockResolvedValue({
      action: 'reindex',
      accepted: true,
      deduplicated: false,
      status: 'queued',
      run_id: 'run-new',
    })
    renderCard()

    fireEvent.click(await screen.findByRole('button', { name: /force re-embed/i }))
    await waitFor(() => expect(postRetrievalReindex).toHaveBeenCalled())
    const [body, key] = postRetrievalReindex.mock.calls[0]
    expect(body).toMatchObject({ force: true, limit: 500, batch_size: 32 })
    expect(typeof key).toBe('string')
    expect(key.length).toBeGreaterThanOrEqual(8)
    expect(await screen.findByRole('status')).toHaveTextContent(/queued/i)
  })

  test('cancels a queued run', async () => {
    getRetrievalOverview.mockResolvedValue(overview())
    getRetrievalRuns.mockResolvedValue({ runs: [run('queued', 'run-q')] })
    cancelRetrievalRun.mockResolvedValue({ accepted: true, status: 'cancelled' })
    renderCard()

    const cancel = await screen.findByRole('button', { name: /^cancel$/i })
    fireEvent.click(cancel)
    await waitFor(() => expect(cancelRetrievalRun).toHaveBeenCalledWith('run-q'))
  })

  test('retries a failed run with an idempotency key', async () => {
    getRetrievalOverview.mockResolvedValue(overview())
    getRetrievalRuns.mockResolvedValue({
      runs: [
        run('failed', 'run-f', {
          scanned: 10,
          embedded: 8,
          skipped: 0,
          failed: 2,
          failed_ids: ['chunk-1', 'chunk-2'],
          failed_ids_truncated: false,
          gate: 'fail',
        }),
      ],
    })
    retryRetrievalRun.mockResolvedValue({ accepted: true, status: 'queued' })
    renderCard()

    const retry = await screen.findByRole('button', { name: /^retry$/i })
    fireEvent.click(retry)
    await waitFor(() => expect(retryRetrievalRun).toHaveBeenCalled())
    const [runId, key] = retryRetrievalRun.mock.calls[0]
    expect(runId).toBe('run-f')
    expect(typeof key).toBe('string')
  })

  test('runs an orphan-sweep maintenance dry run', async () => {
    getRetrievalOverview.mockResolvedValue(overview())
    postRetrievalMaintenance.mockResolvedValue({ accepted: true })
    renderCard()

    fireEvent.click(await screen.findByLabelText(/dry run/i))
    fireEvent.click(screen.getByRole('button', { name: /run maintenance/i }))
    await waitFor(() => expect(postRetrievalMaintenance).toHaveBeenCalled())
    const [body, key] = postRetrievalMaintenance.mock.calls[0]
    expect(body).toMatchObject({ action: 'orphan-sweep', dry_run: true })
    expect(typeof key).toBe('string')
  })

  test('surfaces a structured 409 refusal instead of pretending success', async () => {
    getRetrievalOverview.mockResolvedValue(overview())
    postRetrievalReindex.mockRejectedValue(
      new Error('a vector run is already active (VECTOR_REINDEX, running)')
    )
    renderCard()

    fireEvent.click(await screen.findByRole('button', { name: /reindex index/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /already active/i
    )
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})

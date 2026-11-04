import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { RetrievalStatusCard } from './RetrievalStatusCard'

const getRetrievalOverview = vi.fn()
const getRetrievalRuns = vi.fn()
const getRetrievalSpaces = vi.fn()
const getRetrievalQuality = vi.fn()
const postRetrievalQualityCompare = vi.fn()
const postRetrievalReindex = vi.fn()
const postRetrievalMaintenance = vi.fn()
const postRetrievalBuildSpace = vi.fn()
const postRetrievalCutover = vi.fn()
const activateRetrievalSpace = vi.fn()
const retireRetrievalSpace = vi.fn()
const dropRetrievalSpace = vi.fn()
const cancelRetrievalRun = vi.fn()
const retryRetrievalRun = vi.fn()

const { MockApiError } = vi.hoisted(() => {
  class MockApiError extends Error {
    status = 409
    detail: unknown

    constructor(message: string, detail?: unknown) {
      super(message)
      this.detail = detail
    }
  }
  return { MockApiError }
})

vi.mock('@/lib/api', () => ({
  ApiError: MockApiError,
  getRetrievalOverview: () => getRetrievalOverview(),
  getRetrievalRuns: () => getRetrievalRuns(),
  getRetrievalSpaces: () => getRetrievalSpaces(),
  getRetrievalQuality: (space?: string) => getRetrievalQuality(space),
  postRetrievalQualityCompare: (body: unknown, key: string) =>
    postRetrievalQualityCompare(body, key),
  postRetrievalReindex: (body: unknown, key: string) =>
    postRetrievalReindex(body, key),
  postRetrievalMaintenance: (body: unknown, key: string) =>
    postRetrievalMaintenance(body, key),
  postRetrievalBuildSpace: (body: unknown, key: string) =>
    postRetrievalBuildSpace(body, key),
  postRetrievalCutover: (body: unknown, key: string) =>
    postRetrievalCutover(body, key),
  activateRetrievalSpace: (spaceId: string, key: string) =>
    activateRetrievalSpace(spaceId, key),
  retireRetrievalSpace: (spaceId: string, name: string, key: string) =>
    retireRetrievalSpace(spaceId, name, key),
  dropRetrievalSpace: (spaceId: string, name: string, key: string, force: boolean) =>
    dropRetrievalSpace(spaceId, name, key, force),
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
    getRetrievalSpaces.mockReset()
    getRetrievalQuality.mockReset()
    postRetrievalQualityCompare.mockReset()
    postRetrievalReindex.mockReset()
    postRetrievalMaintenance.mockReset()
    postRetrievalBuildSpace.mockReset()
    postRetrievalCutover.mockReset()
    activateRetrievalSpace.mockReset()
    retireRetrievalSpace.mockReset()
    dropRetrievalSpace.mockReset()
    cancelRetrievalRun.mockReset()
    retryRetrievalRun.mockReset()
    getRetrievalRuns.mockResolvedValue({ runs: [] })
    getRetrievalSpaces.mockResolvedValue({
      spaces: [],
      cold: true,
      active_space_id: null,
      notes: [],
    })
    getRetrievalQuality.mockResolvedValue({
      state: 'no_golden_set',
      space_id: 'legacy-chunk-vecs',
      name: 'content',
      sampled: false,
      set: null,
      quality: null,
      compare: null,
      bad_matches: [],
      compare_run_id: null,
      compare_set_version: null,
      activation_gate: 'unknown',
      reason: 'no_golden_set',
      notes: [],
    })
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

  test('builds a candidate space and gates destructive actions on the typed name', async () => {
    getRetrievalOverview.mockResolvedValue(overview())
    getRetrievalSpaces.mockResolvedValue({
      spaces: [
        {
          space_id: 'legacy-chunk-vecs',
          name: 'content',
          status: 'active',
          provider: 'openai',
          model: 'text-embedding-3-small',
          dim: 1536,
          backend: 'sqlite_vec',
          index_table: 'vec_dfbcce9b',
          documents: 3,
          records: 12,
          coverage: 1,
        },
        {
          space_id: 'space-new',
          name: 'content-v2',
          status: 'building',
          provider: 'openai',
          model: 'text-embedding-3-large',
          dim: 3072,
          backend: 'sqlite_vec',
          index_table: 'vec_12345678',
          documents: 0,
          records: 0,
          coverage: null,
        },
      ],
      cold: false,
      active_space_id: 'legacy-chunk-vecs',
      notes: [],
    })
    postRetrievalBuildSpace.mockResolvedValue({ accepted: true })
    retireRetrievalSpace.mockResolvedValue({ accepted: true })
    renderCard()

    expect(
      await screen.findByText(/no versioned golden-query set is recorded/i)
    ).toBeInTheDocument()
    expect(await screen.findByText('content-v2')).toBeInTheDocument()
    fireEvent.click(
      screen.getByRole('button', { name: /build candidate space/i })
    )
    await waitFor(() => expect(postRetrievalBuildSpace).toHaveBeenCalled())
    const [body, key] = postRetrievalBuildSpace.mock.calls[0]
    expect(body).toMatchObject({
      name: 'content-candidate',
      model: 'text-embedding-3-small',
      dim: 1536,
    })
    expect(typeof key).toBe('string')

    const retire = screen.getByRole('button', { name: /^retire$/i })
    expect(retire).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/type content-v2 to confirm/i), {
      target: { value: 'content-v2' },
    })
    expect(retire).toBeEnabled()
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

  test('shows the activation gate reasons and quality evidence on refusal', async () => {
    getRetrievalOverview.mockResolvedValue(overview())
    getRetrievalSpaces.mockResolvedValue({
      spaces: [
        {
          space_id: 'legacy-chunk-vecs',
          name: 'content',
          status: 'active',
          provider: 'openai',
          model: 'text-embedding-3-small',
          dim: 1536,
          backend: 'sqlite_vec',
          index_table: 'vec_dfbcce9b',
          documents: 3,
          records: 12,
          coverage: 1,
          quality_state: 'sampled',
          quality_gate: 'pass',
        },
        {
          space_id: 'space-new',
          name: 'content-v2',
          status: 'building',
          provider: 'openai',
          model: 'text-embedding-3-large',
          dim: 3072,
          backend: 'sqlite_vec',
          index_table: 'vec_12345678',
          documents: 3,
          records: 12,
          coverage: 1,
          quality_state: 'sampled',
          quality_gate: 'fail',
        },
      ],
      cold: false,
      active_space_id: 'legacy-chunk-vecs',
      notes: [],
    })
    activateRetrievalSpace.mockRejectedValue(
      new MockApiError('activation refused', {
        reason: 'quality_gate_failed',
        activation_gate: {
          quality: 'fail',
          allowed: false,
          reasons: ['coverage_pass', 'quality_below_floor'],
        },
      })
    )
    getRetrievalQuality.mockResolvedValue({
      state: 'sampled',
      space_id: 'space-new',
      name: 'content-v2',
      sampled: true,
      set: {
        space_id: 'space-new',
        set_version: 1,
        k: 5,
        floor_recall: 0.8,
        floor_precision: 0.5,
        query_count: 1,
        query_ids: ['q-1'],
        revision_key: 'space-new:v1',
      },
      quality: {
        space_id: 'space-new',
        set_version: 1,
        k: 5,
        recall_at_k: 0.4,
        precision_at_k: 0.4,
        passed: false,
        queries: [],
        floor_recall: 0.8,
        floor_precision: 0.5,
      },
      compare: null,
      bad_matches: [
        {
          space_id: 'space-new',
          query_id: 'q-1',
          missing_document_ids: ['doc-a'],
          hits: [
            {
              chunk_id: 'chunk-1',
              document_id: 'doc-b',
              view: 'body',
              distance: 0.4,
              score: 0.6,
            },
          ],
        },
      ],
      compare_run_id: 'run-q',
      compare_set_version: 1,
      activation_gate: 'fail',
      reason: null,
      notes: [],
    })
    renderCard()

    expect(await screen.findByText(/quality gate: fail/i)).toBeInTheDocument()
    expect(
      await screen.findByText(/quality: sampled · gate fail/i)
    ).toBeInTheDocument()
    fireEvent.click(
      await screen.findByRole('button', { name: /show bad matches/i })
    )
    expect(await screen.findByText(/missing document ids: doc-a/i)).toBeInTheDocument()
    expect(
      screen.getByText(/chunk chunk-1 · document doc-b · body · score 0.600/i)
    ).toBeInTheDocument()

    fireEvent.click(
      screen.getByRole('button', { name: /compare with active space/i })
    )
    await waitFor(() => expect(postRetrievalQualityCompare).toHaveBeenCalled())
    const [body, key] = postRetrievalQualityCompare.mock.calls[0]
    expect(body).toMatchObject({
      space_id: 'space-new',
      compare_space_id: 'legacy-chunk-vecs',
    })
    expect(typeof key).toBe('string')
  })

  test('renders the gate reasons returned by a refused activation', async () => {
    getRetrievalOverview.mockResolvedValue(overview())
    getRetrievalSpaces.mockResolvedValue({
      spaces: [
        {
          space_id: 'legacy-chunk-vecs',
          name: 'content',
          status: 'active',
          provider: 'openai',
          model: 'text-embedding-3-small',
          dim: 1536,
          backend: 'sqlite_vec',
          index_table: 'vec_dfbcce9b',
          documents: 3,
          records: 12,
          coverage: 1,
          quality_state: 'sampled',
          quality_gate: 'pass',
        },
        {
          space_id: 'space-new',
          name: 'content-v2',
          status: 'building',
          provider: 'openai',
          model: 'text-embedding-3-large',
          dim: 3072,
          backend: 'sqlite_vec',
          index_table: 'vec_12345678',
          documents: 3,
          records: 12,
          coverage: 1,
          quality_state: 'not_sampled',
          quality_gate: 'unknown',
        },
      ],
      cold: false,
      active_space_id: 'legacy-chunk-vecs',
      notes: [],
    })
    activateRetrievalSpace.mockRejectedValue(
      new MockApiError('activation refused', {
        reason: 'quality_gate_failed',
        activation_gate: {
          quality: 'fail',
          allowed: false,
          reasons: ['quality_below_floor'],
        },
      })
    )
    renderCard()

    expect(
      await screen.findByText(/no versioned golden-query set is recorded/i)
    ).toBeInTheDocument()
    fireEvent.click(
      await screen.findByRole('button', { name: /activate space/i })
    )
    await waitFor(() => expect(activateRetrievalSpace).toHaveBeenCalled())
    expect(
      await screen.findByText('quality_below_floor')
    ).toBeInTheDocument()
  })
})

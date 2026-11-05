import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  createMemoryHistory,
  createRootRoute,
  createRoute,
  createRouter,
  Outlet,
  RouterProvider,
} from '@tanstack/react-router'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { RetrievalObservationPanel } from './RetrievalObservationPanel'

const getRetrievalOverview = vi.fn()
const getRetrievalSpaces = vi.fn()
const getRetrievalRuns = vi.fn()
const getRetrievalQuality = vi.fn()
const getRetrievalQueryHealth = vi.fn()
const getRetrievalUsage = vi.fn()

vi.mock('@/lib/api', () => ({
  getRetrievalOverview: (window?: string) => getRetrievalOverview(window),
  getRetrievalSpaces: () => getRetrievalSpaces(),
  getRetrievalRuns: () => getRetrievalRuns(),
  getRetrievalQuality: (space?: string) => getRetrievalQuality(space),
  getRetrievalQueryHealth: (window?: string) => getRetrievalQueryHealth(window),
  getRetrievalUsage: (window?: string) => getRetrievalUsage(window),
}))

const { authState } = vi.hoisted(() => ({ authState: { admin: true } }))

vi.mock('@/lib/auth-session', () => ({
  getCurrentUser: () => ({ is_admin: authState.admin }),
}))

function coverage(overrides: Record<string, unknown> = {}) {
  return {
    space_id: 'space-a',
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
    ...overrides,
  }
}

function space(overrides: Record<string, unknown> = {}) {
  return {
    space_id: 'space-a',
    name: 'content',
    status: 'active',
    provider: 'openai',
    model: 'text-embedding-3-small',
    dim: 1536,
    backend: 'sqlite_vec',
    metric: 'cosine',
    index_table: 'vec_dfbcce9b',
    documents: 3,
    records: 12,
    coverage: 1,
    stale: null,
    failed: 0,
    created_at: null,
    activated_at: null,
    retired_at: null,
    last_reindex_at: '2026-11-04T00:00:00Z',
    last_error: null,
    gate: 'pass',
    as_of: '2026-11-04T00:00:00Z',
    quality_state: 'sampled',
    quality_gate: 'pass',
    ...overrides,
  }
}

function run(
  status: string,
  runId: string,
  overrides: Record<string, unknown> = {}
) {
  return {
    run: {
      run_id: runId,
      space_id: 'space-a',
      job_type: 'VECTOR_REINDEX',
      status,
      progress: 100,
      stage: 'embedding 10/10',
      scope: { kind: 'material', view: 'body', since: null },
      budget_tokens: null,
      created_at: '2026-11-04T00:00:00Z',
      started_at: '2026-11-04T00:00:10Z',
      finished_at: '2026-11-04T00:02:00Z',
      heartbeat_at: null,
      error: 'RAW DOCUMENT TEXT SHOULD NEVER RENDER',
      cancel_requested: false,
      idempotency_key: null,
      lock_key: null,
      ...(overrides.run as Record<string, unknown> | undefined),
    },
    result: 'result' in overrides ? overrides.result : null,
    duration_seconds: null,
  }
}

function overview(overrides: Record<string, unknown> = {}) {
  return {
    state: 'ready',
    cold: false,
    backend: 'sqlite_vec',
    backend_label: 'SQLite sqlite-vec',
    space: space(),
    coverage: coverage(),
    recent_runs: [],
    query_health: {
      window: '24h',
      window_start: '2026-11-03T00:00:00Z',
      window_end: '2026-11-04T00:00:00Z',
      query_count: 40,
      candidates_avg: 8.5,
      health: {
        space_id: 'space-a',
        window_start: '2026-11-03T00:00:00Z',
        window_end: '2026-11-04T00:00:00Z',
        p50_ms: 12,
        p95_ms: 44,
        zero_result_rate: 0.025,
        degraded_rate: 0.05,
        degraded_reasons: { embed_failed: 2 },
        per_view_hits: { body: 30 },
        sampled: false,
        sample_size: 40,
        query_count: 40,
      },
    },
    spaces: [space()],
    notes: [],
    ...overrides,
  }
}

function quality(overrides: Record<string, unknown> = {}) {
  return {
    state: 'sampled',
    space_id: 'space-a',
    name: 'content',
    sampled: true,
    set: {
      space_id: 'space-a',
      set_version: 2,
      k: 5,
      floor_recall: 0.7,
      floor_precision: 0.5,
      query_count: 3,
      query_ids: ['q-1', 'q-2', 'q-3'],
      revision_key: 'rev',
    },
    quality: {
      space_id: 'space-a',
      set_version: 2,
      k: 5,
      recall_at_k: 0.82,
      precision_at_k: 0.64,
      passed: true,
      queries: [],
      floor_recall: 0.7,
      floor_precision: 0.5,
      generated_at: '2026-11-04T00:00:00Z',
    },
    compare: null,
    bad_matches: [],
    compare_run_id: null,
    compare_set_version: null,
    activation_gate: 'pass',
    reason: null,
    notes: [],
    ...overrides,
  }
}

function health(overrides: Record<string, unknown> = {}) {
  return {
    window: '24h',
    window_start: '2026-11-03T00:00:00Z',
    window_end: '2026-11-04T00:00:00Z',
    query_count: 40,
    candidates_avg: 8.5,
    health: {
      space_id: 'space-a',
      window_start: '2026-11-03T00:00:00Z',
      window_end: '2026-11-04T00:00:00Z',
      p50_ms: 12,
      p95_ms: 44,
      zero_result_rate: 0.025,
      degraded_rate: 0.05,
      degraded_reasons: { embed_failed: 2 },
      per_view_hits: { body: 30 },
      sampled: false,
      sample_size: 40,
      query_count: 40,
      ...overrides,
    },
  }
}

async function renderPanel(initial = '/settings?tab=tools&section=indexing') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const rootRoute = createRootRoute({ component: () => <Outlet /> })
  const settingsRoute = createRoute({
    getParentRoute: () => rootRoute,
    path: '/settings',
    validateSearch: (search: Record<string, unknown>) => ({
      tab: typeof search.tab === 'string' ? search.tab : undefined,
      section: typeof search.section === 'string' ? search.section : undefined,
      obs: typeof search.obs === 'string' ? search.obs : undefined,
      detail: typeof search.detail === 'string' ? search.detail : undefined,
    }),
    component: () => <RetrievalObservationPanel />,
  })
  const router = createRouter({
    routeTree: rootRoute.addChildren([settingsRoute]),
    history: createMemoryHistory({ initialEntries: [initial] }),
  })
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
  await screen.findByLabelText(/window/i)
  return router
}

describe('RetrievalObservationPanel', () => {
  beforeEach(() => {
    authState.admin = true
    getRetrievalOverview.mockReset()
    getRetrievalSpaces.mockReset()
    getRetrievalRuns.mockReset()
    getRetrievalQuality.mockReset()
    getRetrievalQueryHealth.mockReset()
    getRetrievalUsage.mockReset()
    getRetrievalOverview.mockResolvedValue(overview())
    getRetrievalSpaces.mockResolvedValue({
      spaces: [space()],
      cold: false,
      active_space_id: 'space-a',
      notes: [],
    })
    getRetrievalRuns.mockResolvedValue({ runs: [] })
    getRetrievalQuality.mockResolvedValue(quality())
    getRetrievalQueryHealth.mockResolvedValue(health())
    getRetrievalUsage.mockResolvedValue({
      window: '24h',
      window_start: null,
      window_end: null,
      rows: [
        {
          day: '2026-11-04',
          space_id: 'space-a',
          kind: 'material',
          calls: 4,
          tokens_in: 120,
          tokens_out: null,
          reindex_calls: 4,
        },
      ],
      tokens_available: true,
      errors_available: false,
      budget: null,
      notes: [],
    })
  })

  test('shows a cold store honestly and never invents a coverage percentage', async () => {
    getRetrievalOverview.mockResolvedValue(
      overview({
        state: 'cold',
        cold: true,
        coverage: coverage({ as_of: null, coverage: null }),
        space: space({ coverage: null, as_of: null }),
        query_health: {
          window: '24h',
          window_start: null,
          window_end: null,
          query_count: 0,
          candidates_avg: null,
          health: {
            space_id: 'space-a',
            window_start: '',
            window_end: '',
            p50_ms: null,
            p95_ms: null,
            zero_result_rate: null,
            degraded_rate: null,
            degraded_reasons: {},
            per_view_hits: {},
            sampled: false,
            sample_size: 0,
            query_count: 0,
          },
        },
      })
    )
    getRetrievalUsage.mockResolvedValue({
      window: '24h',
      window_start: null,
      window_end: null,
      rows: [],
      tokens_available: false,
      errors_available: false,
      budget: null,
      notes: [],
    })

    await renderPanel()

    expect((await screen.findAllByText(/not reconciled/i)).length).toBeGreaterThan(0)
    expect(screen.getByText(/no coverage snapshot exists yet/i)).toBeInTheDocument()
    expect(screen.getByText(/3 documents · 12 vectors/i)).toBeInTheDocument()
    expect(screen.queryByText(/^100%$/)).not.toBeInTheDocument()
    expect(screen.getByText(/not recorded/i)).toBeInTheDocument()
  })

  test('renders a degraded store with the shared vocabulary and query health', async () => {
    getRetrievalOverview.mockResolvedValue(
      overview({
        state: 'degraded',
        notes: ['The provisioned vector backend reports a problem.'],
      })
    )
    getRetrievalQueryHealth.mockResolvedValue(
      health({ degraded_rate: 0.12, degraded_reasons: { embed_failed: 3, index_missing: 1 } })
    )

    const router = await renderPanel()

    expect(await screen.findByText(/index needs attention/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /query health/i }))

    expect(
      await screen.findByTestId('retrieval-observation-query-health')
    ).toBeInTheDocument()
    expect(screen.getByText('embed_failed')).toBeInTheDocument()
    expect(screen.getByText('index_missing')).toBeInTheDocument()
    expect(screen.getByText('12.0%')).toBeInTheDocument()
    expect(screen.getByText(/44 ms/)).toBeInTheDocument()
    expect(router.state.location.search).toMatchObject({
      tab: 'tools',
      section: 'indexing',
      obs: 'query-health',
    })
  })

  test('switches observation sections through the URL and clears the detail', async () => {
    getRetrievalRuns.mockResolvedValue({ runs: [run('succeeded', 'run-ok')] })
    const router = await renderPanel(
      '/settings?tab=tools&section=indexing&obs=spaces'
    )

    expect(await screen.findByTestId('retrieval-observation-spaces')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: /runs/i }))

    expect(await screen.findByTestId('retrieval-observation-runs')).toBeInTheDocument()
    expect(router.state.location.search).toMatchObject({
      tab: 'tools',
      section: 'indexing',
      obs: 'runs',
    })
    expect(router.state.location.search).not.toHaveProperty('detail')
  })

  test('opens a run drawer from detail=<run_id> with failed ids and no raw error text', async () => {
    getRetrievalRuns.mockResolvedValue({
      runs: [
        run('failed', 'run-f', {
          result: {
            scanned: 10,
            embedded: 8,
            skipped: 0,
            failed: 2,
            failed_ids: ['chunk-1', 'chunk-2'],
            failed_ids_truncated: false,
            gate: 'fail',
          },
        }),
      ],
    })

    await renderPanel('/settings?tab=tools&section=indexing&detail=run-f')

    const drawer = await screen.findByTestId('retrieval-observation-run-drawer')
    expect(drawer).toBeInTheDocument()
    expect(await screen.findByText('chunk-1')).toBeInTheDocument()
    expect(screen.getByText('chunk-2')).toBeInTheDocument()
    expect(
      screen.getByText(/scanned 10 · embedded 8 · skipped 0 · failed 2/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/RAW DOCUMENT TEXT/i)).not.toBeInTheDocument()
  })

  test('renders live progress and the tokenizer identity in the run drawer', async () => {
    getRetrievalRuns.mockResolvedValue({
      runs: [
        run('running', 'run-p', {
          run: {
            progress_detail: {
              phase: 'embedding',
              processed_documents: 3,
              total_documents: 9,
              processed_chunks: 7,
              pending_chunks: 14,
              total_chunks: 21,
              chunks_estimated: true,
              embedded_chunks: 5,
              skipped_chunks: 2,
              failed_chunks: 0,
              embedded_documents: 2,
              skipped_documents: 1,
              failed_documents: 0,
              tokens: 512,
              tokens_estimated: true,
              embed_calls: 2,
              exact_tokenizer: false,
              done: false,
            },
            token_aware: true,
            tokenizer: {
              kind: 'tiktoken',
              identifier: 'cl100k_base',
              exact: true,
              source: 'curated',
              max_input_tokens: 8191,
            },
            chunk: { max_chunk_tokens: 512, overlap_tokens: 64, max_chars: 2400 },
          },
        }),
      ],
    })

    await renderPanel('/settings?tab=tools&section=indexing&obs=runs&detail=run-p')

    const drawer = await screen.findByTestId('retrieval-observation-run-drawer')
    const bar = await within(drawer).findByTestId('retrieval-observation-run-progress-bar')
    expect(bar).toHaveAttribute('role', 'progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '33')
    expect(
      within(drawer).getByTestId('retrieval-observation-run-progress-documents').textContent
    ).toContain('3 / 9 documents')
    expect(
      within(drawer).getByTestId('retrieval-observation-run-progress-pending').textContent
    ).toContain('14')
    expect(
      within(drawer).getByTestId('retrieval-observation-run-progress-estimated')
    ).toBeInTheDocument()
    expect(
      within(drawer).getByTestId('retrieval-observation-run-progress-tokens').textContent
    ).toContain('~512')
    const label = within(drawer).getByTestId('retrieval-tokenizer-label')
    expect(label.textContent).toContain('cl100k_base')
    expect(label.textContent).toContain('curated')
  })

  test('opens a space drawer with model, dimension, coverage and health', async () => {
    await renderPanel(
      '/settings?tab=tools&section=indexing&obs=spaces&detail=space:space-a'
    )

    const drawer = await screen.findByTestId('retrieval-observation-space-drawer')
    expect(drawer).toBeInTheDocument()
    expect(within(drawer).getByText('text-embedding-3-small')).toBeInTheDocument()
    expect(within(drawer).getByText('1536')).toBeInTheDocument()
    expect(within(drawer).getByText('vec_dfbcce9b')).toBeInTheDocument()
    expect(within(drawer).getByText('100%')).toBeInTheDocument()
  })

  test('opens quality evidence with bad-match ids and scores only', async () => {
    getRetrievalQuality.mockResolvedValue(
      quality({
        bad_matches: [
          {
            space_id: 'space-a',
            query_id: 'q-2',
            missing_document_ids: ['doc-9'],
            hits: [
              {
                chunk_id: 'chunk-4',
                document_id: 'doc-8',
                view: 'body',
                score: 0.41,
              },
            ],
          },
        ],
      })
    )

    await renderPanel(
      '/settings?tab=tools&section=indexing&obs=quality&detail=quality:space-a'
    )

    const drawer = await screen.findByTestId('retrieval-observation-quality-drawer')
    expect(drawer).toBeInTheDocument()
    expect(await screen.findByText('q-2')).toBeInTheDocument()
    expect(screen.getByText(/missing document ids: doc-9/i)).toBeInTheDocument()
    expect(screen.getByText(/chunk-4 · document doc-8 · body · score 0.410/i)).toBeInTheDocument()
    expect(getRetrievalQuality).toHaveBeenCalledWith('space-a')
  })

  test('groups failures by structured reason without raw run errors', async () => {
    getRetrievalRuns.mockResolvedValue({
      runs: [
        run('failed', 'run-f', {
          result: {
            scanned: 10,
            embedded: 8,
            skipped: 0,
            failed: 2,
            failed_ids: ['chunk-1'],
            failed_ids_truncated: false,
            gate: 'fail',
          },
        }),
      ],
    })
    getRetrievalQuality.mockResolvedValue(
      quality({
        activation_gate: 'fail',
        quality: {
          space_id: 'space-a',
          set_version: 2,
          k: 5,
          recall_at_k: 0.4,
          precision_at_k: 0.3,
          passed: false,
          queries: [],
          floor_recall: 0.7,
          floor_precision: 0.5,
          generated_at: '2026-11-04T00:00:00Z',
        },
      })
    )

    await renderPanel('/settings?tab=tools&section=indexing&obs=failures')

    expect(await screen.findByTestId('retrieval-observation-failures')).toBeInTheDocument()
    expect(screen.getAllByText(/quality gate failed/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/embedding failed/i)).toBeInTheDocument()
    expect(screen.getByText(/quality gate below floor/i)).toBeInTheDocument()
    expect(
      screen.getByTestId('retrieval-observation-failure-embed_provider:space-a:none:embed_failed')
    ).toBeInTheDocument()
    expect(screen.queryByText(/RAW DOCUMENT TEXT/i)).not.toBeInTheDocument()
  })

  test('usage reports calls and keeps unavailable gaps explicit', async () => {
    getRetrievalUsage.mockResolvedValue({
      window: '24h',
      window_start: null,
      window_end: null,
      rows: [
        {
          day: '2026-11-04',
          space_id: 'unattributed',
          kind: 'unknown',
          calls: 2,
          tokens_in: null,
          tokens_out: null,
          reindex_calls: 0,
        },
      ],
      tokens_available: false,
      errors_available: false,
      budget: null,
      notes: ['No embedding token counts are recorded in this window.'],
    })

    await renderPanel('/settings?tab=tools&section=indexing&obs=usage')

    expect(await screen.findByTestId('retrieval-observation-usage')).toBeInTheDocument()
    expect(screen.getByText('unattributed')).toBeInTheDocument()
    expect(screen.getByText(/no embedding token counts are recorded/i)).toBeInTheDocument()
    expect(screen.getAllByText(/not recorded/i).length).toBeGreaterThan(0)
  })

  test('renders an honest empty runs state', async () => {
    await renderPanel('/settings?tab=tools&section=indexing&obs=runs')
    expect(
      await screen.findByTestId('retrieval-observation-runs-empty')
    ).toBeInTheDocument()
    expect(screen.getByText(/no vector runs in this window/i)).toBeInTheDocument()
  })

  test('is admin-only: a non-admin renders nothing and fetches nothing', () => {
    authState.admin = false
    const { container } = render(<RetrievalObservationPanel />)
    expect(container).toBeEmptyDOMElement()
    expect(getRetrievalOverview).not.toHaveBeenCalled()
    expect(getRetrievalSpaces).not.toHaveBeenCalled()
  })

  test('the observation surface never imports or renders a write action', () => {
    const root = join(__dirname)
    const files = [
      'RetrievalObservationPanel.tsx',
      'RetrievalObservationSections.tsx',
      'RetrievalObservationDrawers.tsx',
      'retrievalObservation.ts',
    ]
    const forbidden = [
      'postRetrieval',
      'cancelRetrievalRun',
      'retryRetrievalRun',
      'activateRetrievalSpace',
      'retireRetrievalSpace',
      'dropRetrievalSpace',
      'postRetrievalCutover',
      'postRetrievalQualityCompare',
    ]
    for (const file of files) {
      const source = readFileSync(join(root, file), 'utf8')
      for (const token of forbidden) {
        expect(source).not.toContain(token)
      }
    }
  })
})

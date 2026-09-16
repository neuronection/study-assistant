import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { DiscoverDialog } from './DiscoverDialog'

const searchDiscovery = vi.fn()
const listDiscoverySuggestions = vi.fn()
const saveDiscoverySuggestion = vi.fn()
const patchDiscoverySuggestion = vi.fn()
const deleteDiscoverySuggestion = vi.fn()
const createLinkMaterial = vi.fn()
const parseLinkMaterial = vi.fn()
const getJob = vi.fn()
const getProfilePreferences = vi.fn()
const navigate = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    searchDiscovery: (...args: Parameters<typeof actual.searchDiscovery>) =>
      searchDiscovery(...args),
    listDiscoverySuggestions: (params: unknown) => listDiscoverySuggestions(params),
    saveDiscoverySuggestion: (body: unknown) => saveDiscoverySuggestion(body),
    patchDiscoverySuggestion: (id: number, body: unknown) =>
      patchDiscoverySuggestion(id, body),
    deleteDiscoverySuggestion: (id: number) => deleteDiscoverySuggestion(id),
    createLinkMaterial: (body: unknown) => createLinkMaterial(body),
    parseLinkMaterial: (id: number) => parseLinkMaterial(id),
    getJob: (id: number) => getJob(id),
    getProfilePreferences: () => getProfilePreferences(),
  }
})

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigate,
}))

const PREFS = {
  use_embeddings: true,
  ocr_image_max_edge: 1568,
  discovery: {
    enabled: ['web', 'youtube'],
    sites: [],
  },
}

const RESULT = {
  provider: 'youtube',
  title: 'Chain rule intuition',
  url: 'https://youtube.com/watch?v=abc',
  kind: 'video',
  description: 'A visual take on the chain rule.',
  meta: { channel: 'Math Academy' },
  suggestion: null,
}

function renderDialog(props: Partial<Parameters<typeof DiscoverDialog>[0]> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <DiscoverDialog
        open
        onClose={() => undefined}
        courseId={7}
        nodeId={12}
        defaultQuery="derivatives"
        {...props}
      />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  searchDiscovery.mockReset()
  listDiscoverySuggestions.mockReset()
  saveDiscoverySuggestion.mockReset()
  patchDiscoverySuggestion.mockReset()
  deleteDiscoverySuggestion.mockReset()
  createLinkMaterial.mockReset()
  parseLinkMaterial.mockReset()
  getJob.mockReset()
  getProfilePreferences.mockReset()
  navigate.mockReset()

  getProfilePreferences.mockResolvedValue(PREFS)
  listDiscoverySuggestions.mockResolvedValue({ items: [], next_cursor: null })
})

async function runSearch() {
  fireEvent.change(await screen.findByPlaceholderText(/search topic/i), {
    target: { value: 'chain rule' },
  })
  fireEvent.click(screen.getByRole('button', { name: /^search$/i }))
  await screen.findByTestId('discover-results')
}

describe('DiscoverDialog', () => {
  test('search renders annotated result rows with provider and kind', async () => {
    searchDiscovery.mockResolvedValue({ results: [RESULT], errors: [] })
    renderDialog()
    await runSearch()
    expect(searchDiscovery).toHaveBeenCalledWith({
      query: 'chain rule',
      providers: null,
      cap: 10,
    })
    const row = screen.getByText('Chain rule intuition').closest('div') as HTMLElement
    expect(within(row).getByText('youtube')).toBeInTheDocument()
    expect(within(row).getByText('video')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /save for later/i }),
    ).toBeInTheDocument()
  })

  test('save for later persists the result and shows the saved state', async () => {
    searchDiscovery.mockResolvedValue({ results: [RESULT], errors: [] })
    saveDiscoverySuggestion.mockResolvedValue({
      suggestion: { ...RESULT, id: 5, status: 'saved', material_id: null },
      created: true,
    })
    renderDialog()
    await runSearch()
    fireEvent.click(screen.getByRole('button', { name: /save for later/i }))
    await waitFor(() =>
      expect(saveDiscoverySuggestion).toHaveBeenCalledWith(
        expect.objectContaining({
          provider: 'youtube',
          url: 'https://youtube.com/watch?v=abc',
          kind: 'video',
          course_id: 7,
          node_id: 12,
        }),
      ),
    )
  })

  test('attach as link creates the material and links the suggestion', async () => {
    searchDiscovery.mockResolvedValue({ results: [RESULT], errors: [] })
    saveDiscoverySuggestion.mockResolvedValue({
      suggestion: { ...RESULT, id: 5, status: 'saved', material_id: null },
      created: true,
    })
    createLinkMaterial.mockResolvedValue({
      material: { id: 44, title: 'Chain rule intuition' },
      deduped: false,
      job_id: null,
    })
    patchDiscoverySuggestion.mockResolvedValue({
      id: 5,
      status: 'saved',
      material_id: 44,
    })
    renderDialog()
    await runSearch()
    fireEvent.click(screen.getByRole('button', { name: /attach as link/i }))
    await waitFor(() =>
      expect(createLinkMaterial).toHaveBeenCalledWith({
        course_id: 7,
        url: 'https://youtube.com/watch?v=abc',
        title: 'Chain rule intuition',
        node_id: 12,
      }),
    )
    await waitFor(() =>
      expect(patchDiscoverySuggestion).toHaveBeenCalledWith(5, { material_id: 44 }),
    )
  })

  test('import & parse runs the parse job and attaches the material', async () => {
    searchDiscovery.mockResolvedValue({ results: [RESULT], errors: [] })
    saveDiscoverySuggestion.mockResolvedValue({
      suggestion: { ...RESULT, id: 5, status: 'saved', material_id: null },
      created: true,
    })
    createLinkMaterial.mockResolvedValue({
      material: { id: 44, title: 'Chain rule intuition' },
      deduped: false,
      job_id: null,
    })
    parseLinkMaterial.mockResolvedValue({ job_id: 9 })
    getJob.mockResolvedValue({ status: 'done', error: null })
    patchDiscoverySuggestion.mockResolvedValue({ id: 5, status: 'saved' })
    renderDialog()
    await runSearch()
    fireEvent.click(screen.getByRole('button', { name: /import & parse/i }))
    await waitFor(() => expect(parseLinkMaterial).toHaveBeenCalledWith(44))
    await waitFor(() =>
      expect(patchDiscoverySuggestion).toHaveBeenCalledWith(5, { material_id: 44 }),
    )
  })

  test('a known result shows its state instead of save/dismiss verbs', async () => {
    searchDiscovery.mockResolvedValue({
      results: [
        {
          ...RESULT,
          suggestion: { id: 5, status: 'dismissed', material_id: null },
        },
      ],
      errors: [],
    })
    renderDialog()
    await runSearch()
    expect(screen.getByText('Dismissed')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /save for later/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /restore/i })).toBeInTheDocument()
  })

  test('saved section lists suggestions with statuses and restore works', async () => {
    listDiscoverySuggestions.mockResolvedValue({
      items: [
        {
          id: 3,
          course_id: 7,
          node_id: null,
          provider: 'web',
          url: 'https://example.com/x',
          url_norm: 'https://example.com/x',
          title: 'A saved page',
          snippet: '',
          kind: 'article',
          meta: {},
          status: 'dismissed',
          material_id: null,
          created_at: '2026-09-16T00:00:00Z',
          updated_at: '2026-09-16T00:00:00Z',
        },
      ],
      next_cursor: null,
    })
    patchDiscoverySuggestion.mockResolvedValue({ id: 3, status: 'suggested' })
    searchDiscovery.mockResolvedValue({ results: [], errors: [] })
    renderDialog()
    expect(await screen.findByText('A saved page')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /restore/i }))
    await waitFor(() =>
      expect(patchDiscoverySuggestion).toHaveBeenCalledWith(3, { status: 'suggested' }),
    )
  })

  test('provider chips reflect preferences and toggling narrows the request', async () => {
    searchDiscovery.mockResolvedValue({ results: [], errors: [] })
    renderDialog()
    const youtube = await screen.findByRole('button', { name: 'YouTube' })
    fireEvent.click(youtube)
    await runSearch()
    await waitFor(() =>
      expect(searchDiscovery).toHaveBeenLastCalledWith({
        query: 'chain rule',
        providers: ['web'],
        cap: 10,
      }),
    )
  })
})

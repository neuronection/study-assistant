import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { WebSearchSection } from './WebSearchSection'

const listSearchProviders = vi.fn()
const getSearchProviderCatalog = vi.fn()
const createSearchProvider = vi.fn()
const updateSearchProvider = vi.fn()
const deleteSearchProvider = vi.fn()
const moveSearchProvider = vi.fn()
const testSearchProvider = vi.fn()

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    listSearchProviders: () => listSearchProviders(),
    getSearchProviderCatalog: () => getSearchProviderCatalog(),
    createSearchProvider: (body: unknown) => createSearchProvider(body),
    updateSearchProvider: (id: string, body: unknown) => updateSearchProvider(id, body),
    deleteSearchProvider: (id: string) => deleteSearchProvider(id),
    moveSearchProvider: (id: string, direction: string) => moveSearchProvider(id, direction),
    testSearchProvider: (id: string) => testSearchProvider(id),
  }
})

const CATALOG = {
  schema: 1,
  contract: 'search-providers',
  updated: '2026-10-14',
  purpose: 'test',
  providerOrder: ['searxng', 'tavily', 'brave'],
  providers: {
    searxng: {
      label: 'SearXNG',
      requiresKey: false,
      keyUrl: null,
      baseUrl: null,
      baseUrlRequired: true,
      baseUrlHint: 'https://searx.example.org',
      notes: null,
      hosting: 'self-hosted',
    },
    tavily: {
      label: 'Tavily',
      requiresKey: true,
      keyUrl: 'https://app.tavily.com',
      baseUrl: 'https://api.tavily.com',
      baseUrlRequired: false,
      baseUrlHint: 'https://api.tavily.com',
      notes: null,
      hosting: 'cloud',
    },
    brave: {
      label: 'Brave Search',
      requiresKey: true,
      keyUrl: 'https://api-dashboard.search.brave.com',
      baseUrl: 'https://api.search.brave.com/res/v1',
      baseUrlRequired: false,
      baseUrlHint: null,
      notes: null,
      hosting: 'cloud',
    },
  },
  limits: {
    maxResults: { default: 5, min: 1, max: 10 },
    timeoutMs: { default: 8000, min: 500, max: 30000 },
  },
}

const provider = (overrides: Partial<Record<string, unknown>>) => ({
  id: 'p1',
  name: 'Tavily',
  type: 'tavily',
  enabled: true,
  base_url: null,
  google_cx: null,
  key_hint: '••••cret',
  timeout_ms: 8000,
  max_results: 5,
  key_set: true,
  ...overrides,
})

const TAVILY = provider({})
const SEARXNG = provider({
  id: 'p2',
  name: 'SearXNG',
  type: 'searxng',
  base_url: 'https://searx.example.org',
  key_hint: null,
  key_set: false,
})

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <WebSearchSection />
    </QueryClientProvider>,
  )
}

const openMenu = async (name: string) => {
  const row = await waitFor(() => {
    const el = document.querySelector(`li[data-testid="wsp-row-${name}"]`) as HTMLElement | null
    if (!el) throw new Error(`row ${name} not rendered yet`)
    return el
  })
  const trigger = within(row).getByRole('button', { name: new RegExp(`Actions for`) })
  fireEvent.pointerDown(trigger)
  return await screen.findByRole('menu')
}

/** The section header Add button sits disabled until the catalog query
 * resolves — wait for the enabled state before clicking. */
const openAddWizard = async () => {
  const button = await screen.findByRole('button', { name: 'Add provider' })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
}

beforeEach(() => {
  listSearchProviders.mockReset().mockResolvedValue([TAVILY, SEARXNG])
  getSearchProviderCatalog.mockReset().mockResolvedValue(CATALOG)
  createSearchProvider.mockReset().mockResolvedValue(TAVILY)
  updateSearchProvider.mockReset().mockResolvedValue(TAVILY)
  deleteSearchProvider.mockReset().mockResolvedValue(undefined)
  moveSearchProvider.mockReset().mockResolvedValue({ providers: [TAVILY, SEARXNG] })
  testSearchProvider.mockReset().mockResolvedValue({ status: 'ok', latency_ms: 42 })
})

describe('WebSearchSection', () => {
  test('renders configured instances as provider cards with priority and key badges', async () => {
    renderSection()
    expect(await screen.findByText('priority 1')).toBeInTheDocument()
    expect(screen.getByText('priority 2')).toBeInTheDocument()
    expect(screen.getByTestId('wsp-row-p1')).toBeInTheDocument()
    expect(screen.getByTestId('wsp-row-p2')).toBeInTheDocument()
    // SearXNG needs no key in the catalog — no danger badge anywhere.
    expect(screen.queryByText(/no key/i)).not.toBeInTheDocument()
  })

  test('marks a configured provider missing its required key', async () => {
    listSearchProviders.mockResolvedValue([{ ...TAVILY, key_set: false }])
    renderSection()
    expect(await screen.findByTestId('wsp-key-p1')).toBeInTheDocument()
  })

  test('keeps every management action in the card overflow menu', async () => {
    renderSection()
    const menu = await openMenu('p1')
    const item = (label: string) => within(menu).getByRole('menuitem', { name: label })
    expect(item('Disable')).toBeInTheDocument()
    expect(item('Move up')).toHaveAttribute('data-disabled')
    expect(item('Move down')).not.toHaveAttribute('data-disabled')
    expect(item('Test')).toBeInTheDocument()
    expect(item('Edit provider')).toBeInTheDocument()
    expect(item('Delete provider')).toBeInTheDocument()

    fireEvent.click(item('Disable'))
    await waitFor(() =>
      expect(updateSearchProvider).toHaveBeenCalledWith('p1', { enabled: false }),
    )
  })

  test('add flow: tiles → form, default connection name seeded and numbered when taken', async () => {
    renderSection()
    await openAddWizard()
    const tiles = await screen.findByRole('group', { name: 'Choose a search provider' })
    fireEvent.click(within(tiles).getByRole('button', { name: /Tavily/ }))

    // The connection name lives under the Advanced disclosure, seeded from
    // the catalog label — numbered because "Tavily" is already taken.
    fireEvent.click(screen.getByText('Advanced'))
    expect(screen.getByLabelText('Name (optional)')).toHaveValue('Tavily 2')
    // The base URL is prefilled with the catalog default.
    expect(screen.getByLabelText('Base URL (optional)')).toHaveValue('https://api.tavily.com')

    const key = screen.getByLabelText('API key')
    expect((screen.getByRole('button', { name: 'Save provider' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(key, { target: { value: 'tvly-new' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save provider' }))

    await waitFor(() =>
      expect(createSearchProvider).toHaveBeenCalledWith({
        type: 'tavily',
        name: 'Tavily 2',
        base_url: '',
        google_cx: '',
        timeout_ms: 8000,
        max_results: 5,
        api_key: 'tvly-new',
      }),
    )
  })

  test('edit prefills the stored config and keeps the key when the field stays empty', async () => {
    renderSection()
    const menu = await openMenu('p1')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Edit provider' }))

    const dialog = await screen.findByRole('dialog')
    expect(await within(dialog).findByText('••••cret')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save provider' }))

    await waitFor(() =>
      expect(updateSearchProvider).toHaveBeenCalledWith('p1', {
        type: 'tavily',
        name: 'Tavily',
        base_url: '',
        google_cx: '',
        timeout_ms: 8000,
        max_results: 5,
        api_key: null,
      }),
    )
  })

  test('an endpoint override persists only when it deviates from the catalog default', async () => {
    renderSection()
    const menu = await openMenu('p1')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Edit provider' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Base URL (optional)'), {
      target: { value: 'https://tavily.example.com' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save provider' }))
    await waitFor(() => expect(updateSearchProvider).toHaveBeenCalled())
    expect(updateSearchProvider.mock.calls[0][1].base_url).toBe('https://tavily.example.com')
  })

  test('offers clearing the stored key of an edit dialog', async () => {
    renderSection()
    const menu = await openMenu('p1')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Edit provider' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Clear stored key' }))
    await waitFor(() =>
      expect(updateSearchProvider).toHaveBeenCalledWith('p1', { api_key: '' }),
    )
  })

  test('delete goes through the app-owned confirmation', async () => {
    renderSection()
    const menu = await openMenu('p2')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Delete provider' }))

    const dialog = await screen.findByRole('dialog')
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Delete provider' }),
    )
    await waitFor(() => expect(deleteSearchProvider).toHaveBeenCalledWith('p2'))
  })

  test('reorder emits the family move event', async () => {
    renderSection()
    const menu = await openMenu('p2')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Move up' }))
    await waitFor(() => expect(moveSearchProvider).toHaveBeenCalledWith('p2', 'up'))
  })

  test('probe results narrow unknown statuses to error (fail-honest)', async () => {
    testSearchProvider.mockResolvedValue({
      status: 'some_future_kind',
      latency_ms: 12,
      result_count: null,
      error: 'boom',
    })
    renderSection()
    const menu = await openMenu('p1')
    fireEvent.click(within(menu).getByRole('menuitem', { name: 'Test' }))

    expect(await screen.findByText('Failed')).toBeInTheDocument()
    expect(screen.getByText('boom')).toBeInTheDocument()
    expect(testSearchProvider).toHaveBeenCalledWith('p1')
  })
})

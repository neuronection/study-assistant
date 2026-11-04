import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { IndexingSection } from './IndexingSection'

const getProfilePreferences = vi.fn()
const updateProfilePreferences = vi.fn()

vi.mock('@/lib/api', () => ({
  getProfilePreferences: () => getProfilePreferences(),
  updateProfilePreferences: (prefs: Record<string, unknown>) =>
    updateProfilePreferences(prefs),
  getRetrievalOverview: () =>
    Promise.resolve({
      state: 'empty',
      cold: true,
      backend: null,
      backend_label: null,
      space: null,
      coverage: { coverage: null },
      recent_runs: [],
      query_health: {},
      notes: [],
    }),
  getRetrievalRuns: () => Promise.resolve({ runs: [] }),
  getRetrievalSpaces: () =>
    Promise.resolve({
      spaces: [],
      cold: true,
      active_space_id: null,
      notes: [],
    }),
  postRetrievalReindex: vi.fn(),
  postRetrievalMaintenance: vi.fn(),
  cancelRetrievalRun: vi.fn(),
  retryRetrievalRun: vi.fn(),
}))

vi.mock('@/lib/auth-session', () => ({
  getCurrentUser: () => ({ is_admin: false }),
}))

function renderTab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <IndexingSection />
    </QueryClientProvider>
  )
}

describe('IndexingSection', () => {
  beforeEach(() => {
    getProfilePreferences.mockClear()
    updateProfilePreferences.mockClear()
  })

  test('shows the current OCR image max edge and saves changes', async () => {
    getProfilePreferences.mockResolvedValue({
      use_embeddings: true,
      ocr_image_max_edge: 1568,
    })
    updateProfilePreferences.mockImplementation(async (prefs) => ({
      use_embeddings: true,
      ocr_image_max_edge: 0,
      ...prefs,
    }))
    renderTab()

    const select = await screen.findByLabelText(/max long edge/i)
    await waitFor(() => expect(select).toHaveValue('1568'))

    expect(screen.queryByText(/retrieval observation/i)).not.toBeInTheDocument()
    fireEvent.change(select, { target: { value: '1024' } })
    await waitFor(() =>
      expect(updateProfilePreferences).toHaveBeenCalledWith({ ocr_image_max_edge: 1024 })
    )
  })

  test('offers the off preset', async () => {
    getProfilePreferences.mockResolvedValue({
      use_embeddings: true,
      ocr_image_max_edge: 0,
    })
    renderTab()

    const select = await screen.findByLabelText(/max long edge/i)
    await waitFor(() => expect(select).toHaveValue('0'))
    expect(
      screen.getByRole('option', { name: /off \(send as-is\)/i })
    ).toBeInTheDocument()
  })
})
